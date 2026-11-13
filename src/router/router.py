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
from .templates import ANSWER_TYPE, monthly_revenue, run_template


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
        if intent in I.MONTHLY_INTENTS:
            return self._monthly(qid, intent, s, res, as_of_d, conn, blocked_spans)
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
        elif intent == "cust_group_rev":
            groups = [r[0] for r in conn.execute("SELECT DISTINCT customer_group FROM v_valid_orders WHERE customer_group IS NOT NULL")]
            g, why = I.match_group(groups, s)
            if g is None:
                return RouteDecision("llm", why, intent, params=params)
            kw["item"] = (None, g)
            params["group"] = g
        elif intent in ("payment_method_rev", "channel_rev"):
            col = "payment_method" if intent == "payment_method_rev" else "channel"
            raw = [r[0] for r in conn.execute(f"SELECT DISTINCT {col} FROM v_valid_orders WHERE {col} IS NOT NULL")]
            vals, why = (I.match_payment if intent == "payment_method_rev" else I.match_channel)(raw, s)
            if vals is None:
                return RouteDecision("llm", why, intent, params=params)
            kw["values"] = vals
            params["values"] = vals
        elif intent == "unit_total_qty":
            unit = I.unit_for_total(s)
            bases = [r[0] for r in conn.execute("SELECT DISTINCT base_unit FROM v_items WHERE base_unit IS NOT NULL")]
            vals = [b for b in bases if unit and I.item_match_key(b) == I.item_match_key(unit)]
            catalog = conn.execute("SELECT item_code, item_name, name_aliases, base_unit FROM v_items").fetchall()
            if I.match_item(catalog, s)[0] is not None:   # a named item: the question is about that item, not all items
                return RouteDecision("llm", "item_named", intent, params=params)
            if not vals:
                return RouteDecision("llm", "unit_not_a_base_unit", intent, params=params)
            kw["values"] = vals
            params["values"] = vals
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

    def _monthly(self, qid, intent, s, res, as_of_d, conn, blocked_spans):
        """best_month / monthly_series / streak_bool: months named by the question, revenue of each month (valid orders)."""
        if res.comparison is not None or not res.periods:
            return RouteDecision("llm", "period_missing" if not res.periods else "period_count", intent)
        months: list[tuple[dt.date, dt.date]] = []
        for p in res.periods:
            if p.start is None or p.granularity not in ("month", "month_series"):
                return RouteDecision("llm", "period_not_months", intent)
            y, m = p.start.year, p.start.month
            while (y, m) <= (p.end.year, p.end.month):
                first = dt.date(y, m, 1)
                last = dt.date(y + (m == 12), (m % 12) + 1, 1) - dt.timedelta(days=1)
                months.append((first, min(last, as_of_d)))
                y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        if not 2 <= len(months) <= 24 or len({a for a, _ in months}) != len(months):
            return RouteDecision("llm", "month_count", intent)
        params: dict[str, Any] = {"months": [a.isoformat()[:7] for a, _ in months]}
        for a, b in months:
            if blocked_spans and blocked_by_spans(blocked_spans, a.isoformat(), b.isoformat()):
                return RouteDecision("abstain", "period_overlaps_unparsed_dates", intent, params=params)
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='v_valid_orders'").fetchone():
            return RouteDecision("llm", "no_views", intent, params=params)
        min_date = conn.execute("SELECT MIN(order_date) FROM v_orders").fetchone()[0]
        if min_date and any(b.isoformat() < min_date for _, b in months):
            return RouteDecision("llm", "month_before_data_start", intent, params=params)
        win = [(a.isoformat(), b.isoformat()) for a, b in months]
        rev = monthly_revenue(conn, win)
        ordered = sorted(zip([a for a, _ in months], rev))           # chronological
        if intent == "monthly_series":
            value: Any = [v for _, v in ordered]
        elif intent == "streak_bool":
            seq = [v for _, v in zip([a for a, _ in months], rev)]     # months in the order the question names them
            value = all(x < y for x, y in zip(seq, seq[1:]))
        else:
            top = max(rev)
            if rev.count(top) != 1 or top <= 0:
                return RouteDecision("llm", "best_month_tie_or_empty", intent, params=params)
            value = months[rev.index(top)][0].isoformat()[:7]
        bad_answer = sanity.check_monthly(intent, value, months)
        if bad_answer:
            return RouteDecision("abstain", f"sanity:{bad_answer}", intent, params=params)
        return RouteDecision("template", "ok", intent, {"id": qid, "type": ANSWER_TYPE[intent], "answer": value}, params)
