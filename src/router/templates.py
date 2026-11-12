"""SQL templates over the rulebook views and answer formatting.

SOURCE: the SQL strings in SQL_TEMPLATES are copied VERBATIM from
`scripts/analysis/rule_regression.py` (feat/p3-data-cleaning, author: Nghiep; `SQL_TEMPLATES`, lines ~265-325).
The surrounding Python (parameter plumbing, result typing, rounding) follows that file's `execute_template`.
NEEDS REVIEW/APPROVAL BY THE AUTHOR of the data layer: the SQL must stay identical to the source; if the source
changes, this copy has to follow (the scripts/ file is not importable as part of the package, hence the copy).

Only views are used (v_valid_orders, v_orders, v_valid_lines): the definition of a valid order, statuses and
unit conversion live in the views, nothing is re-implemented here.
"""
from __future__ import annotations

import sqlite3
from typing import Any

SQL_TEMPLATES: dict[str, str] = {
    "revenue": (
        "SELECT CAST(ROUND(COALESCE(SUM(revenue), 0)) AS INTEGER) "
        "FROM v_valid_orders WHERE order_date BETWEEN ? AND ?"
    ),
    "order_count": (
        "SELECT COUNT(*) FROM v_valid_orders WHERE order_date BETWEEN ? AND ?"
    ),
    "order_count_threshold": (
        "SELECT COUNT(*) FROM v_valid_orders "
        "WHERE order_date BETWEEN ? AND ? AND revenue >= ?"
    ),
    "cancel_count": (
        "SELECT COUNT(*) FROM v_orders "
        "WHERE order_date BETWEEN ? AND ? AND status = 'huy'"
    ),
    "cancel_rate": (
        "SELECT ROUND(SUM(CASE WHEN status = 'huy' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) "
        "FROM v_orders WHERE order_date BETWEEN ? AND ?"
    ),
    "aov": (
        "SELECT CAST(SUM(revenue) * 1.0 / COUNT(*) + 0.5 AS INTEGER) "
        "FROM v_valid_orders WHERE order_date BETWEEN ? AND ?"
    ),
    "best_day": (
        "SELECT order_date FROM v_valid_orders "
        "WHERE order_date BETWEEN ? AND ? "
        "GROUP BY order_date ORDER BY SUM(revenue) DESC, order_date ASC LIMIT 1"
    ),
    "topk_items": (
        "SELECT item_name FROM v_valid_lines "
        "WHERE order_date BETWEEN ? AND ? AND is_service_fee = 0 "
        "GROUP BY COALESCE(item_code, item_name) "
        "ORDER BY SUM(qty_base) DESC, COALESCE(item_code, item_name) ASC LIMIT ?"
    ),
    "best_item": (
        "SELECT item_name FROM v_valid_lines "
        "WHERE order_date BETWEEN ? AND ? AND is_service_fee = 0 "
        "GROUP BY COALESCE(item_code, item_name) "
        "ORDER BY SUM(qty_base) DESC, COALESCE(item_code, item_name) ASC LIMIT 1"
    ),
    "item_qty_by_code": (
        "SELECT COALESCE(SUM(qty_base), 0) FROM v_valid_lines "
        "WHERE order_date BETWEEN ? AND ? AND item_code = ?"
    ),
    "item_qty_by_name": (
        "SELECT COALESCE(SUM(qty_base), 0) FROM v_valid_lines "
        "WHERE order_date BETWEEN ? AND ? AND item_name = ?"
    ),
    "rev_change_pct": (
        "WITH cur AS ("
        "  SELECT COALESCE(SUM(revenue), 0) AS rev FROM v_valid_orders WHERE order_date BETWEEN ? AND ?"
        "), prev AS ("
        "  SELECT COALESCE(SUM(revenue), 0) AS rev FROM v_valid_orders WHERE order_date BETWEEN ? AND ?"
        ") "
        "SELECT ROUND((cur.rev - prev.rev) * 100.0 / prev.rev, 2) "
        "FROM cur, prev WHERE prev.rev > 0"
    ),
}

# answer type per intent (rulebook section 9)
ANSWER_TYPE = {
    "revenue": "number", "order_count": "number", "cancel_count": "number", "aov": "number",
    "item_qty": "number", "cancel_rate": "percent", "rev_change_pct": "percent",
    "best_day": "date", "best_item": "string", "topk_items": "list",
}


def run_template(conn: sqlite3.Connection, intent: str, start: str, end: str, *,
                 k: int | None = None, item: tuple[str | None, str] | None = None,
                 prev: tuple[str, str] | None = None, threshold: float | None = None) -> Any:
    """Execute the template of *intent*; returns the answer value (None when the template has no result)."""
    if intent == "rev_change_pct":
        assert prev is not None
        row = conn.execute(SQL_TEMPLATES[intent], (start, end, prev[0], prev[1])).fetchone()
        return float(row[0]) if row and row[0] is not None else None
    if intent == "topk_items":
        assert k is not None
        return [r[0] for r in conn.execute(SQL_TEMPLATES[intent], (start, end, k)).fetchall()] or None
    if intent == "item_qty":
        assert item is not None
        code, name = item
        row = (conn.execute(SQL_TEMPLATES["item_qty_by_code"], (start, end, code)).fetchone() if code
               else conn.execute(SQL_TEMPLATES["item_qty_by_name"], (start, end, name)).fetchone())
        val = float(row[0]) if row and row[0] is not None else 0.0
        return int(round(val)) if abs(val - round(val)) < 1e-6 else round(val, 2)
    if intent == "order_count" and threshold is not None:
        row = conn.execute(SQL_TEMPLATES["order_count_threshold"], (start, end, threshold)).fetchone()
    else:
        row = conn.execute(SQL_TEMPLATES[intent], (start, end)).fetchone()
    if row is None or row[0] is None:
        return None
    if intent in ("revenue", "order_count", "cancel_count", "aov"):
        return int(row[0])
    if intent == "cancel_rate":
        return float(row[0])
    return row[0]
