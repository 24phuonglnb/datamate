"""Route a question to a deterministic template over the rulebook views, or hand it to the LLM agent.

Safety rule: the template answers only when intent, period and parameters are all certain. Anything else is
routed to "llm" with a reason (route "unanswerable" = period entirely before the shop's data, rulebook section 7; "abstain" is not produced yet).
No logic on shop or question identifiers; valid-order definition, statuses and unit conversion come from the views.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from . import intents as I
from . import sanity
from .invariants import blocked_by_spans
from .templates import ANSWER_TYPE, run_template


@dataclass
class RouteDecision:
    route: str                      # "template" | "unanswerable" | "llm" | "abstain"
    reason: str
    intent: str | None = None
    answer: dict[str, Any] | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def log(self) -> dict[str, Any]:
        return {"route": self.route, "reason": self.reason, "intent": self.intent, "params": self.params}


class Router:
    def __init__(self, rule_guard: Any = None):
        """rule_guard: rule_guard.RuleGuard comparing the running rulebook with the one the templates were written for."""
        self.rule_guard = rule_guard

    def route(self, question: dict[str, Any], nq: Any, conn: sqlite3.Connection,
              blocked_spans: list[list[str]] | None = None) -> RouteDecision:
        qid = str(question.get("id", ""))
        as_of = str(question.get("as_of_date", ""))
        if "residual_teencode" in nq.flags:
            return RouteDecision("llm", "normalizer_residual_teencode")
        s = I.prepare(nq.text)
        intent, why = I.recognise(s)
        if intent is None:
            return RouteDecision("llm", why)
        if self.rule_guard is not None:
            why = self.rule_guard.check(intent, s)
            if why:
                return RouteDecision("llm", why, intent)
        bad = I.extra_filter(intent, s)
        if bad:
            return RouteDecision("llm", bad, intent)
        if intent == "unans_subjective":  # rulebook section 7: opinions are not in the data
            ans = {"id": qid, "type": "unanswerable",
                   "reason": "Câu hỏi mang tính đánh giá chủ quan, dữ liệu cửa hàng không ghi nhận (rulebook mục 7)."}
            return RouteDecision("unanswerable", "subjective_question", intent, ans, {})
        res = nq.period
        if res.ambiguous:
            return RouteDecision("llm", "period_ambiguous", intent)
        if res.part_of_day:
            return RouteDecision("llm", "part_of_day", intent)
        try:
            as_of_d = dt.date.fromisoformat(as_of[:10])
        except ValueError:
            return RouteDecision("llm", "no_as_of", intent)
        prev = None
        if intent == "rev_change_pct":
            if len(res.periods) == 1 and res.comparison is not None:
                cur, pv = res.periods[0], res.comparison
            elif len(res.periods) == 2 and res.comparison is None:
                cur, pv = res.periods
            else:
                return RouteDecision("llm", "period_count", intent)
            if cur.start is None or pv.start is None:
                return RouteDecision("llm", "period_open", intent)
            prev = (pv.start.isoformat(), min(pv.end, as_of_d).isoformat())
        else:
            if len(res.periods) != 1 or res.comparison is not None:
                return RouteDecision("llm", "period_missing" if not res.periods else "period_count", intent)
            cur = res.periods[0]
            if cur.start is None:
                return RouteDecision("llm", "period_open", intent)
        start, end = cur.start.isoformat(), min(cur.end, as_of_d).isoformat()
        params: dict[str, Any] = {"start": start, "end": end}
        if prev:
            params["prev"] = list(prev)
        if blocked_spans:  # rows with unparsed dates may belong to this period: the question abstains
            hit = blocked_by_spans(blocked_spans, start, end) or (blocked_by_spans(blocked_spans, *prev) if prev else None)
            if hit:
                return RouteDecision("abstain", f"period_overlaps_unparsed_dates:{hit[0]}..{hit[1]}", intent, params=params)
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='v_valid_orders'").fetchone():
            return RouteDecision("llm", "no_views", intent, params=params)
        min_date = conn.execute("SELECT MIN(order_date) FROM v_orders").fetchone()[0]
        if min_date and end < min_date:
            # rulebook section 7: a period entirely outside the shop's data range is unanswerable, not 0
            ans = {"id": qid, "type": "unanswerable",
                   "reason": "Kỳ được hỏi nằm hoàn toàn trước ngày đầu tiên có dữ liệu của cửa hàng (rulebook mục 7)."}
            return RouteDecision("unanswerable", "before_data_start", intent, ans, params)
        kw: dict[str, Any] = {}
        if intent == "topk_items":
            k = I.topk_k(s)
            if not 1 <= k <= 50:
                return RouteDecision("llm", "topk_k_out_of_range", intent, params=params)
            kw["k"] = k
            params["k"] = k
        elif intent == "item_qty":
            cat = conn.execute("SELECT item_code, item_name, name_aliases, base_unit FROM v_items").fetchall()
            m, why = I.match_item(cat, s)
            if m is None:
                return RouteDecision("llm", why, intent, params=params)
            unit = I.asked_unit(s)
            if unit is None or I.item_match_key(unit) != I.item_match_key(m[2] or ""):
                return RouteDecision("llm", "unit_mismatch", intent, params=params)
            kw["item"] = (m[0], m[1])
            params["item"] = m[1]
        elif intent in ("item_revenue", "sell_price_on_day"):
            cat = conn.execute("SELECT item_code, item_name, name_aliases, base_unit FROM v_items").fetchall()
            m, why = I.match_item(cat, s)
            if m is None:
                return RouteDecision("llm", why, intent, params=params)
            if intent == "sell_price_on_day":
                if start != end:
                    return RouteDecision("llm", "price_needs_single_day", intent, params=params)
                unit = I.asked_unit_after_mot(s)
                if unit is None or I.item_match_key(unit) != I.item_match_key(m[2] or ""):
                    return RouteDecision("llm", "unit_mismatch", intent, params=params)
            kw["item"] = (m[0], m[1])
            params["item"] = m[1]
        elif intent == "category_rev":
            cats = [r[0] for r in conn.execute("SELECT DISTINCT category FROM v_items WHERE category IS NOT NULL")]
            c, why = I.match_category(cats, s)
            if c is None:
                return RouteDecision("llm", why, intent, params=params)
            kw["item"] = (None, c)
            params["category"] = c
        elif intent == "order_count":
            th, why = I.order_threshold(s)
            if why not in ("ok", "no_threshold"):
                return RouteDecision("llm", why, intent, params=params)
            if th is not None:
                kw["threshold"] = th
                params["threshold"] = th
        elif intent == "best_item" and I.topk_k(s) is not None:
            return RouteDecision("llm", "best_item_with_k", intent, params=params)
        if prev:
            kw["prev"] = prev
        value = run_template(conn, intent, start, end, **kw)
        if value is None:
            return RouteDecision("llm", "empty_result", intent, params=params)
        bad_answer = sanity.check(intent, value, conn, start, end)
        if bad_answer:
            return RouteDecision("abstain", f"sanity:{bad_answer}", intent, params=params)
        ans = {"id": qid, "type": ANSWER_TYPE[intent], "answer": value}
        return RouteDecision("template", "ok", intent, ans, params)
