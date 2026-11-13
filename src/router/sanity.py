"""Generic plausibility checks on a template answer (no gold, no per-shop knowledge).  A violation makes the router
abstain: an implausible number means the views or the question reading are wrong for this question.

  number   revenue / counts are finite and >= 0; cancel_count <= all orders of the period
  percent  cancel_rate in [0, 100]; percent change >= -100 (revenue cannot fall below zero) and <= 1000
  aov      within [min, max] of the valid orders' revenue in the period
  date     ISO date inside the asked period
  names    every returned item name exists in v_items
"""
from __future__ import annotations

import datetime as dt
import math
import re
import sqlite3
from typing import Any


def check(intent: str, value: Any, conn: sqlite3.Connection, start: str, end: str) -> str | None:
    """-> violated rule or None."""
    if intent in ("revenue", "order_count", "cancel_count", "item_qty", "aov", "item_revenue", "category_rev", "sell_price_on_day",
                  "cust_group_rev", "payment_method_rev", "channel_rev", "unit_total_qty"):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
            return "number_not_finite_nonnegative"
    if intent == "cancel_count":
        total = conn.execute("SELECT COUNT(*) FROM v_orders WHERE order_date BETWEEN ? AND ?", (start, end)).fetchone()[0]
        if value > total:
            return "cancel_count_exceeds_orders"
    if intent == "cancel_rate" and not (isinstance(value, (int, float)) and 0 <= value <= 100):
        return "cancel_rate_outside_0_100"
    if intent == "rev_change_pct" and not (isinstance(value, (int, float)) and -100 <= value <= 1000):
        return "percent_change_implausible"
    if intent == "aov":
        lo, hi = conn.execute("SELECT MIN(revenue), MAX(revenue) FROM v_valid_orders WHERE order_date BETWEEN ? AND ?",
                              (start, end)).fetchone()
        if lo is None or not (lo - 1e-9 <= value <= hi + 1e-9):
            return "aov_outside_order_range"
    if intent == "best_day":
        if not (isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)):
            return "date_format"
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            return "date_format"
        if not (start <= value <= end):
            return "date_outside_period"
    if intent in ("topk_items", "best_item"):
        names = value if isinstance(value, list) else [value]
        known = {r[0] for r in conn.execute("SELECT item_name FROM v_items")}
        if not known or any(n not in known for n in names):
            return "item_name_not_in_catalog"
    return None


def check_monthly(intent: str, value: Any, months: list) -> str | None:
    """best_month: 'YYYY-MM' of one of the named months; monthly_series: non-negative ints, one per month; streak_bool: bool."""
    if intent == "best_month":
        names = {a.isoformat()[:7] for a, _ in months}
        return None if isinstance(value, str) and value in names else "best_month_not_a_named_month"
    if intent == "monthly_series":
        ok = isinstance(value, list) and len(value) == len(months) and all(
            isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in value)
        return None if ok else "monthly_series_shape"
    if intent == "streak_bool":
        return None if isinstance(value, bool) else "streak_not_boolean"
    return None
