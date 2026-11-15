"""Route a question to a deterministic template over the rulebook views, or hand it to the LLM agent.

Safety rule: the template answers only when intent, period and parameters are all certain. Anything else is
routed to "llm" with a reason (route "unanswerable" = period entirely before the shop's data, rulebook section 7; "abstain" is not produced yet).
No logic on shop or question identifiers; valid-order definition, statuses and unit conversion come from the views.
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from . import intents as I
from . import sanity
from .invariants import blocked_by_spans
from .templates import ANSWER_TYPE, SQL_TEMPLATES, monthly_revenue, run_template


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
        days_th = I.days_over_threshold(s) if intent == "revenue" else None
        if days_th is not None:
            intent = "days_over_threshold"   # same rulebook rows as revenue (checked above)
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
        try:
            as_of_d = dt.date.fromisoformat(as_of[:10])
        except ValueError:
            return RouteDecision("llm", "no_as_of", intent)
        if intent == "shift":
            return self._shift(qid, s, res, as_of_d, conn, blocked_spans)
        if res.part_of_day:
            return RouteDecision("llm", "part_of_day", intent)
        if intent == "price_effect":
            return self._price_effect(qid, s, res, as_of_d, conn, blocked_spans)
        if intent in I.MONTHLY_INTENTS:
            return self._monthly(qid, intent, s, res, as_of_d, conn, blocked_spans)
        if intent in I.INVENTORY_INTENTS:
            return self._inventory(qid, intent, s, res, as_of_d, conn)
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
            if unit is None:
                return RouteDecision("llm", "unit_mismatch", intent, params=params)
            if I.item_match_key(unit) != I.item_match_key(m[2] or ""):
                fac = {f for _, k, f in conn.execute(SQL_TEMPLATES["item_unit_factors"], (m[0], m[1])) if k == I.item_match_key(unit)}
                if len(fac) != 1 or next(iter(fac)) <= 1 or not self._has_view(conn, "v_item_units"):
                    return RouteDecision("llm", "unit_mismatch", intent, params=params)
                kw["divisor"] = float(next(iter(fac)))
                params["unit"] = unit
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
        elif intent == "ingredient_revenue":
            vals = [r[0] for r in conn.execute("SELECT DISTINCT active_ingredient FROM v_items WHERE active_ingredient IS NOT NULL")]
            if not vals:   # the shop's drug table has no ingredient column: not recorded -> unanswerable (rulebook section 7)
                return self._unanswerable(qid, "Cửa hàng không ghi hoạt chất của mặt hàng (rulebook mục 7).", "no_active_ingredient", intent, params)
            g, why = I.match_ingredient(vals, s)
            if g is None:
                return RouteDecision("llm", why, intent, params=params)
            kw["item"] = (None, g)
            params["ingredient"] = g
        elif intent in ("rx_nonrx_revenue", "rx_share"):
            if not conn.execute("SELECT 1 FROM v_items WHERE is_prescription IS NOT NULL LIMIT 1").fetchone():
                return self._unanswerable(qid, "Cửa hàng không ghi thuốc kê đơn (rulebook mục 7).", "no_prescription_info", intent, params)
            if intent == "rx_nonrx_revenue":
                pol = I.rx_polarity(s)
                if pol is None:
                    return RouteDecision("llm", "rx_polarity_unclear", intent, params=params)
                kw["values"] = [pol]
                params["rx"] = pol
        elif intent == "days_over_threshold":
            kw["threshold"] = days_th
            params["threshold"] = days_th
        elif intent == "category_share":
            cats = [r[0] for r in conn.execute("SELECT DISTINCT category FROM v_items WHERE category IS NOT NULL")]
            c, why = I.match_category(cats, I.strip_dates(s))
            if c is None:
                return RouteDecision("llm", why, intent, params=params)
            kw["item"] = (None, c)
            params["category"] = c
        elif intent == "size_qty":
            letter = I.size_letter(s)
            if letter is None:
                return RouteDecision("llm", "size_not_named", intent, params=params)
            kw["values"] = [f"%({letter})"]
            params["size"] = letter
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
        if intent == "unsold_count":
            params["before"] = start
        value = run_template(conn, intent, start, end, **kw)
        if value is None:
            return RouteDecision("llm", "empty_result", intent, params=params)
        bad_answer = sanity.check(intent, value, conn, start, end)
        if bad_answer:
            return RouteDecision("abstain", f"sanity:{bad_answer}", intent, params=params)
        ans = {"id": qid, "type": ANSWER_TYPE[intent], "answer": value}
        return RouteDecision("template", "ok", intent, ans, params)

    @staticmethod
    def _unanswerable(qid, reason, code, intent, params):
        return RouteDecision("unanswerable", code, intent, {"id": qid, "type": "unanswerable", "reason": reason}, params)

    @staticmethod
    def _has_view(conn, name):
        return conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (name,)).fetchone() is not None

    def _inventory(self, qid, intent, s, res, as_of_d, conn):
        """Purchases (v_valid_purchase_lines), stock (v_stock, v_stock_card, v_item_units) and lots (v_lots).

        The views exist only for shops that record that information (docs/VIEWS.md 3.8, 3.9): a missing view, or a
        purchase book without amounts, is "not recorded" -> unanswerable (rulebook section 7, same as the train answers);
        SQL is never run against a view that is not there."""
        params: dict[str, Any] = {}
        if res.comparison is not None or len(res.periods) > (2 if intent == "expiry_list" else 1):
            return RouteDecision("llm", "period_count", intent)
        cur = res.periods[-1] if res.periods else None
        if len(res.periods) == 2 and not (res.periods[0].granularity == "day" and res.periods[0].end == as_of_d):
            return RouteDecision("llm", "period_count", intent)   # only "<as-of day>, ... from now to the end of E" is read as one range
        if intent in ("purchase_total", "supplier_top", "purchase_avg_price"):
            return self._purchases(qid, intent, s, cur, as_of_d, conn, params)
        if intent == "expiry_nearest_lot":
            return self._expiry_nearest(qid, intent, s, as_of_d, conn, params)
        if intent == "expiry_list":
            return self._expiry(qid, intent, s, cur, as_of_d, conn, params)
        return self._stock(qid, intent, s, cur, as_of_d, conn, params)

    def _purchases(self, qid, intent, s, cur, as_of_d, conn, params):
        if cur is None or cur.start is None:
            return RouteDecision("llm", "period_missing" if cur is None else "period_open", intent)
        ok = {"purchase_total": I.purchase_total_ok, "supplier_top": I.supplier_top_ok}.get(intent, lambda _: True)
        if not ok(s):
            return RouteDecision("llm", "purchase_pattern", intent)
        start, end = cur.start.isoformat(), min(cur.end, as_of_d).isoformat()
        params.update({"start": start, "end": end})
        if not self._has_view(conn, "v_valid_purchase_lines"):
            return self._unanswerable(qid, "Cửa hàng không có sổ nhập hàng (rulebook mục 7).", "no_purchase_book", intent, params)
        n_amount, lo, hi = conn.execute("SELECT COUNT(line_amount), MIN(receipt_date), MAX(receipt_date) FROM v_valid_purchase_lines").fetchone()
        if not n_amount:   # quantities only: no purchase money recorded (VIEWS.md 3.8 rule 3)
            return self._unanswerable(qid, "Sổ nhập hàng không ghi giá/tiền nhập (rulebook mục 7).", "no_purchase_amount", intent, params)
        if lo and end < lo:
            return self._unanswerable(qid, "Kỳ được hỏi nằm trước phiếu nhập đầu tiên của cửa hàng (rulebook mục 7).", "before_purchase_start", intent, params)
        if hi and start > hi:
            return RouteDecision("llm", "after_last_receipt", intent, params=params)
        if intent == "purchase_total":
            total, n = conn.execute(SQL_TEMPLATES["purchase_total"], (start, end)).fetchone()
            if not n:
                return RouteDecision("llm", "no_receipt_in_period", intent, params=params)
            value: Any = int(total + 0.5) if total >= 0 else None
            bad = None if value is not None else "negative_purchase_total"
        elif intent == "supplier_top":
            rows = conn.execute(SQL_TEMPLATES["supplier_top"], (start, end)).fetchall()
            if not rows:
                return RouteDecision("llm", "no_receipt_in_period", intent, params=params)
            if len(rows) > 1 and rows[0][1] == rows[1][1]:
                return RouteDecision("llm", "supplier_tie", intent, params=params)
            value, bad = rows[0][0], None
        else:
            cat = conn.execute("SELECT item_code, item_name, name_aliases, base_unit FROM v_items").fetchall()
            m, why = I.match_item(cat, I.strip_dates(s))
            if m is None:
                return RouteDecision("llm", why, intent, params=params)
            asked = I.asked_unit_after_mot(s)
            units = [r[0] for r in conn.execute(
                "SELECT DISTINCT unit FROM v_valid_purchase_lines WHERE COALESCE(item_code, item_name) = COALESCE(?, ?) AND unit IS NOT NULL",
                (m[0], m[1]))]
            use = [u for u in units if asked and I.item_match_key(u) == I.item_match_key(asked)]
            if len(use) != 1:
                return RouteDecision("llm", "unit_not_an_import_unit", intent, params=params)
            key = "purchase_avg_price_by_code" if m[0] else "purchase_avg_price_by_name"
            avg, n_amt, n_all = conn.execute(SQL_TEMPLATES[key], (start, end, m[0] or m[1], use[0])).fetchone()
            params.update({"item": m[1], "unit": use[0]})
            if not n_all:
                return RouteDecision("llm", "no_receipt_in_period", intent, params=params)
            if not n_amt or avg is None:
                return RouteDecision("llm", "purchase_price_missing", intent, params=params)
            value, bad = int(avg + 0.5), None
        if bad:
            return RouteDecision("abstain", f"sanity:{bad}", intent, params=params)
        return RouteDecision("template", "ok", intent, {"id": qid, "type": ANSWER_TYPE[intent], "answer": value}, params)

    def _stock_item(self, conn, s, intent, params):
        """Item named in the question, found in v_items; -> (match, None) or (None, decision)."""
        cat = conn.execute("SELECT item_code, item_name, name_aliases, base_unit FROM v_items").fetchall()
        m, why = I.match_item(cat, I.strip_dates(s))
        if m is None:
            return None, RouteDecision("llm", why, intent, params=params)
        params["item"] = m[1]
        return m, None

    def _stock_qty_at(self, conn, m, day, as_of_d):
        """Base-unit stock of item *m* at the end of *day*: v_stock for the end of the data, v_stock_card for earlier days
        (VIEWS.md 3.9).  -> (value, reason): value None when the views cannot give it exactly."""
        stock_date = conn.execute("SELECT MAX(stock_date) FROM v_stock").fetchone()[0]
        if day >= (stock_date or as_of_d.isoformat()):
            row = conn.execute(SQL_TEMPLATES["stock_qty"], (m[0], m[1])).fetchall()
            return (float(row[0][0]), "ok") if len(row) == 1 and row[0][0] is not None else (None, "item_not_in_stock")
        if not self._has_view(conn, "v_stock_card"):
            return None, "stock_past_no_card"
        rows = conn.execute(SQL_TEMPLATES["stock_card_at"], (m[0], m[1], day)).fetchall()
        if not rows:
            return None, "no_movement_before_day"
        if len(rows) > 1 and rows[0][1] == rows[1][1]:   # two movements with the same timestamp: the last one is not decidable here
            return None, "stock_card_tie"
        return float(rows[0][0]), "ok"

    def _stock(self, qid, intent, s, cur, as_of_d, conn, params):
        if cur is None or cur.granularity not in ("day", "cumulative"):
            return RouteDecision("llm", "stock_needs_day", intent)
        day = cur.end.isoformat()
        params["day"] = day
        if cur.end > as_of_d:
            return RouteDecision("llm", "stock_future_day", intent, params=params)
        if not self._has_view(conn, "v_stock"):
            return self._unanswerable(qid, "Cửa hàng không có dữ liệu tồn kho (rulebook mục 7).", "no_stock_data", intent, params)
        stock_date = conn.execute("SELECT MAX(stock_date) FROM v_stock").fetchone()[0] or as_of_d.isoformat()
        if intent == "stock_value":
            if day < stock_date:
                return RouteDecision("llm", "stock_value_past_day", intent, params=params)
            total, n, n_null = conn.execute(SQL_TEMPLATES["stock_value"]).fetchone()
            if not n:
                return RouteDecision("llm", "empty_stock", intent, params=params)
            if n_null == n:
                return self._unanswerable(qid, "Danh mục không ghi giá vốn (rulebook mục 7).", "no_cost_price", intent, params)
            if n_null:
                return RouteDecision("llm", "cost_price_partial", intent, params=params)
            value: Any = int(total + 0.5)
        else:
            m, bad = self._stock_item(conn, s, intent, params)
            if bad:
                return bad
            qty, why = self._stock_qty_at(conn, m, day, as_of_d)
            if qty is None:
                return RouteDecision("llm", why, intent, params=params)
            if intent == "stock_qty":
                unit = I.asked_unit(s)
                if unit is None or I.item_match_key(unit) != I.item_match_key(m[2] or ""):
                    return RouteDecision("llm", "unit_mismatch", intent, params=params)
                value = int(round(qty)) if abs(qty - round(qty)) < 1e-6 else round(qty, 2)
            else:   # stock_large_unit: [whole big units, base units left over] (rulebook section 5)
                bigs, small = I.large_units(s)
                if not bigs or not small or I.item_match_key(small) != I.item_match_key(m[2] or ""):
                    return RouteDecision("llm", "large_unit_pattern", intent, params=params)
                keys = {I.item_match_key(b) for b in bigs}
                rows = [(k, f) for _, k, f in conn.execute(SQL_TEMPLATES["item_unit_factors"], (m[0], m[1])) if k in keys]
                fac = {f for _, f in rows}
                big = bigs[-1] if any(k == I.item_match_key(bigs[-1]) for k, _ in rows) else bigs[0]
                if len(fac) != 1 or next(iter(fac)) <= 1 or qty < 0 or abs(qty - round(qty)) > 1e-6:
                    return RouteDecision("llm", "large_unit_factor", intent, params=params)
                f = next(iter(fac))
                if abs(f - round(f)) > 1e-9:
                    return RouteDecision("llm", "large_unit_factor", intent, params=params)
                n_big = int(round(qty) // int(round(f)))
                value = [n_big, int(round(qty)) - n_big * int(round(f))]
                params["unit"] = big
        bad_answer = sanity.check_inventory(intent, value)
        if bad_answer:
            return RouteDecision("abstain", f"sanity:{bad_answer}", intent, params=params)
        return RouteDecision("template", "ok", intent, {"id": qid, "type": ANSWER_TYPE[intent], "answer": value}, params)

    def _expiry(self, qid, intent, s, cur, as_of_d, conn, params):
        """Lots still in stock that expire from today D to the end of E (rulebook section 6): a count of lots or the products."""
        kind = I.expiry_kind(s)
        if kind is None or cur is None or cur.start not in (as_of_d, None) or (cur.start is None and not re.search(r"\btu nay\b", s)):
            return RouteDecision("llm", "expiry_pattern", intent)
        start, end = as_of_d.isoformat(), cur.end.isoformat()
        params.update({"start": start, "end": end, "kind": kind})
        if not self._has_view(conn, "v_lots"):
            return self._unanswerable(qid, "Cửa hàng không có dữ liệu lô/hạn dùng (rulebook mục 7).", "no_lot_data", intent, params)
        if kind == "count":
            value: Any = int(conn.execute(SQL_TEMPLATES["expiry_count"], (start, end)).fetchone()[0])
            atype = "number"
        else:
            value = [r[0] for r in conn.execute(SQL_TEMPLATES["expiry_items"], (start, end))]
            atype = "list"
        bad_answer = sanity.check_inventory(intent, value)
        if bad_answer:
            return RouteDecision("abstain", f"sanity:{bad_answer}", intent, params=params)
        return RouteDecision("template", "ok", intent, {"id": qid, "type": atype, "answer": value}, params)

    def _expiry_nearest(self, qid, intent, s, as_of_d, conn, params):
        if not self._has_view(conn, "v_lots"):
            return self._unanswerable(qid, "Cửa hàng không có dữ liệu lô/hạn dùng (rulebook mục 7).", "no_lot_data", intent, params)
        m, bad = self._stock_item(conn, s, intent, params)
        if bad:
            return bad
        key = "expiry_nearest_by_code" if m[0] else "expiry_nearest_by_name"
        value = conn.execute(SQL_TEMPLATES[key], (m[0] or m[1], as_of_d.isoformat())).fetchone()[0]
        if value is None:
            return RouteDecision("llm", "no_lot_in_stock", intent, params=params)
        return RouteDecision("template", "ok", intent, {"id": qid, "type": "date", "answer": value}, params)

    def _shift(self, qid, s, res, as_of_d, conn, blocked_spans):
        """Revenue / orders of the morning or afternoon shift, or afternoon vs morning in percent (rulebook section 2:
        06:00-13:59 and 14:00-21:59 by the hour the order was created; the baseline of a comparison is the morning)."""
        intent = "shift"
        pod = res.part_of_day
        if not pod or res.ambiguous or res.comparison is not None or len(res.periods) != 1:
            return RouteDecision("llm", "shift_period_or_shift_unclear", intent)
        cur = res.periods[0]
        if cur.start is None:
            return RouteDecision("llm", "period_open", intent)
        shifts = [k for k in ("sang", "chieu") if k in pod]
        measure = I.shift_measure(s)
        pct = bool(re.search(r"%|phan tram", s))
        if measure is None or not shifts or (pct and shifts != ["sang", "chieu"]) or (not pct and len(shifts) != 1):
            return RouteDecision("llm", "shift_pattern", intent)
        if pct and pod.get("baseline") != "sang":
            return RouteDecision("llm", "shift_baseline", intent)
        start, end = cur.start.isoformat(), min(cur.end, as_of_d).isoformat()
        params: dict[str, Any] = {"start": start, "end": end, "shifts": shifts, "measure": measure}
        if blocked_spans and blocked_by_spans(blocked_spans, start, end):
            return RouteDecision("abstain", "period_overlaps_unparsed_dates", intent, params=params)
        if not self._has_view(conn, "v_valid_orders"):
            return RouteDecision("llm", "no_views", intent, params=params)
        min_date = conn.execute("SELECT MIN(order_date) FROM v_orders").fetchone()[0]
        if min_date and end < min_date:
            return self._unanswerable(qid, "Kỳ được hỏi nằm hoàn toàn trước ngày đầu tiên có dữ liệu của cửa hàng (rulebook mục 7).", "before_data_start", intent, params)
        if conn.execute(SQL_TEMPLATES["shift_time_missing"], (start, end)).fetchone()[0]:
            return RouteDecision("llm", "order_time_missing", intent, params=params)   # the hour of some orders is not recorded
        sql = SQL_TEMPLATES["shift_revenue" if measure == "money" else "shift_orders"]

        def one(shift):
            v = conn.execute(sql, (start, end, *pod[shift])).fetchone()[0]
            return float(v) if v is not None else 0.0

        if pct:
            base, other = one("sang"), one("chieu")
            if base <= 0:
                return RouteDecision("llm", "empty_baseline_shift", intent, params=params)
            value: Any = float(conn.execute("SELECT ROUND((? - ?) * 100.0 / ?, 2)", (other, base, base)).fetchone()[0])
            atype = "percent"
            if not -100 <= value <= 100000:
                return RouteDecision("abstain", "sanity:shift_percent_implausible", intent, params=params)
        else:
            v = one(shifts[0])
            value, atype = int(round(v)), "number"
        return RouteDecision("template", "ok", intent, {"id": qid, "type": atype, "answer": value}, params)

    def _price_effect(self, qid, s, res, as_of_d, conn, blocked_spans):
        """Change (%) of the base-unit quantity of an item: N days from day D (D included) vs the N days right before D
        (rulebook section 5); both ranges use valid orders only.  Ranges come from the shared Period resolver."""
        intent = "price_effect"
        if res.comparison is None:
            return RouteDecision("llm", "price_no_comparison", intent)
        cur_ps = [p for p in res.periods if p.granularity == "range" and p.start is not None and "ke tu" in p.source]
        if len(cur_ps) != 1:
            return RouteDecision("llm", "price_range_missing", intent)
        cur, prv = cur_ps[0], res.comparison
        n = (cur.end - cur.start).days + 1
        if prv.start is None or (prv.end - prv.start).days + 1 != n or prv.end != cur.start - dt.timedelta(days=1) or cur.end > as_of_d:
            return RouteDecision("llm", "price_ranges_inconsistent", intent)
        params: dict[str, Any] = {"start": cur.start.isoformat(), "end": cur.end.isoformat(),
                                  "prev": [prv.start.isoformat(), prv.end.isoformat()]}
        if blocked_spans and (blocked_by_spans(blocked_spans, *params["prev"]) or blocked_by_spans(blocked_spans, params["start"], params["end"])):
            return RouteDecision("abstain", "period_overlaps_unparsed_dates", intent, params=params)
        cat = conn.execute("SELECT item_code, item_name, name_aliases, base_unit FROM v_items").fetchall()
        m, why = I.match_item(cat, I.strip_dates(s))
        if m is None:
            return RouteDecision("llm", why, intent, params=params)
        params["item"] = m[1]
        key = "qty_by_code" if m[0] else "qty_by_name"
        ident = m[0] or m[1]
        now = float(conn.execute(SQL_TEMPLATES[key], (params["start"], params["end"], ident)).fetchone()[0])
        before = float(conn.execute(SQL_TEMPLATES[key], (*params["prev"], ident)).fetchone()[0])
        if before <= 0:
            return RouteDecision("llm", "empty_previous_range", intent, params=params)
        value = float(conn.execute("SELECT ROUND((? - ?) * 100.0 / ?, 2)", (now, before, before)).fetchone()[0])
        if not -100 <= value <= 100000:
            return RouteDecision("abstain", "sanity:price_effect_percent_implausible", intent, params=params)
        return RouteDecision("template", "ok", intent, {"id": qid, "type": "percent", "answer": value}, params)

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
