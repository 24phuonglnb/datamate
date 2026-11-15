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

# Templates written for the router (NOT from rule_regression.py; need review by the data-layer author).
SQL_TEMPLATES.update({
    "item_revenue_by_code": (
        "SELECT CAST(ROUND(COALESCE(SUM(line_amount), 0)) AS INTEGER) FROM v_valid_lines "
        "WHERE order_date BETWEEN ? AND ? AND is_service_fee = 0 AND item_code = ?"
    ),
    "item_revenue_by_name": (
        "SELECT CAST(ROUND(COALESCE(SUM(line_amount), 0)) AS INTEGER) FROM v_valid_lines "
        "WHERE order_date BETWEEN ? AND ? AND is_service_fee = 0 AND item_name = ?"
    ),
    "category_revenue": (
        "SELECT CAST(ROUND(COALESCE(SUM(line_amount), 0)) AS INTEGER) FROM v_valid_lines "
        "WHERE order_date BETWEEN ? AND ? AND is_service_fee = 0 AND category = ?"
    ),
    # list price per base unit on a day: every line of that day, any order status (rulebook section 5, "Giá bán X ngày D")
    "price_on_day_by_code": "SELECT DISTINCT ROUND(unit_price_base, 2) FROM v_lines WHERE order_date = ? AND item_code = ?",
    "price_on_day_by_name": "SELECT DISTINCT ROUND(unit_price_base, 2) FROM v_lines WHERE order_date = ? AND item_name = ?",
})

SQL_TEMPLATES.update({
    "group_revenue": (
        "SELECT CAST(ROUND(COALESCE(SUM(revenue), 0)) AS INTEGER) FROM v_valid_orders "
        "WHERE order_date BETWEEN ? AND ? AND customer_group = ?"
    ),
    # IN (...) lists are filled by run_template (placeholders only, values are bound parameters)
    "payment_revenue": (
        "SELECT CAST(ROUND(COALESCE(SUM(revenue), 0)) AS INTEGER) FROM v_valid_orders "
        "WHERE order_date BETWEEN ? AND ? AND payment_method IN ({ph})"
    ),
    "channel_revenue": (
        "SELECT CAST(ROUND(COALESCE(SUM(revenue), 0)) AS INTEGER) FROM v_valid_orders "
        "WHERE order_date BETWEEN ? AND ? AND channel IN ({ph})"
    ),
    "unit_total_qty": (
        "SELECT COALESCE(SUM(qty_base), 0) FROM v_valid_lines "
        "WHERE order_date BETWEEN ? AND ? AND is_service_fee = 0 AND base_unit IN ({ph})"
    ),
})

# Pharmacy / purchases / stock templates (docs/VIEWS.md 3.5, 3.8, 3.9 example SQL; the period filter is on the date range
# resolved by the shared Period resolver instead of order_month / receipt_month).
_RX_JOIN = ("FROM v_valid_lines l LEFT JOIN v_items i "
            "ON l.is_service_fee = 0 AND COALESCE(l.item_code, l.item_name) = COALESCE(i.item_code, i.item_name) "
            "WHERE l.order_date BETWEEN ? AND ?")
SQL_TEMPLATES.update({
    "ingredient_revenue": (
        "SELECT CAST(ROUND(COALESCE(SUM(l.line_amount), 0)) AS INTEGER) "
        "FROM v_valid_lines l JOIN v_items i ON COALESCE(l.item_code, l.item_name) = COALESCE(i.item_code, i.item_name) "
        "WHERE l.is_service_fee = 0 AND l.order_date BETWEEN ? AND ? AND i.active_ingredient = ?"
    ),
    "rx_revenue": ("SELECT CAST(ROUND(COALESCE(SUM(CASE WHEN i.is_prescription = '1' THEN l.line_amount ELSE 0 END), 0)) AS INTEGER) "
                   + _RX_JOIN),
    "nonrx_revenue": ("SELECT CAST(ROUND(COALESCE(SUM(CASE WHEN i.is_prescription = '1' THEN 0 ELSE l.line_amount END), 0)) AS INTEGER) "
                      + _RX_JOIN),
    "rx_share": ("SELECT ROUND(SUM(CASE WHEN i.is_prescription = '1' THEN l.line_amount ELSE 0 END) * 100.0 "
                 "/ NULLIF(SUM(l.line_amount), 0), 2) " + _RX_JOIN),
    "purchase_total": ("SELECT SUM(line_amount), COUNT(line_amount) FROM v_valid_purchase_lines "
                       "WHERE receipt_date BETWEEN ? AND ?"),
    "supplier_top": ("SELECT supplier, SUM(line_amount) AS spend FROM v_valid_purchase_lines "
                     "WHERE receipt_date BETWEEN ? AND ? AND supplier IS NOT NULL AND line_amount IS NOT NULL "
                     "GROUP BY supplier ORDER BY spend DESC, supplier ASC LIMIT 2"),
    "purchase_avg_price_by_code": ("SELECT SUM(line_amount) * 1.0 / NULLIF(SUM(qty), 0), COUNT(line_amount), COUNT(*) "
                                   "FROM v_valid_purchase_lines WHERE receipt_date BETWEEN ? AND ? AND item_code = ? AND unit = ?"),
    "purchase_avg_price_by_name": ("SELECT SUM(line_amount) * 1.0 / NULLIF(SUM(qty), 0), COUNT(line_amount), COUNT(*) "
                                   "FROM v_valid_purchase_lines WHERE receipt_date BETWEEN ? AND ? AND item_name = ? AND unit = ?"),
    "stock_qty": "SELECT stock_qty_base FROM v_stock WHERE COALESCE(item_code, item_name) = COALESCE(?, ?)",
    "stock_value": "SELECT SUM(stock_value), COUNT(*), SUM(CASE WHEN stock_value IS NULL THEN 1 ELSE 0 END) FROM v_stock WHERE stock_qty_base > 0",
    "expiry_count": ("SELECT COUNT(*) FROM v_lots WHERE qty_remaining > 0 AND expiry_date BETWEEN ? AND ?"),
    "expiry_items": ("SELECT item_name FROM v_lots WHERE qty_remaining > 0 AND expiry_date BETWEEN ? AND ? "
                     "GROUP BY COALESCE(item_code, item_name) "
                     "ORDER BY MIN(expiry_date) ASC, COALESCE(item_code, item_name) ASC"),
    "expiry_nearest_by_code": ("SELECT MIN(expiry_date) FROM v_lots WHERE item_code = ? AND qty_remaining > 0 AND expiry_date >= ?"),
    "expiry_nearest_by_name": ("SELECT MIN(expiry_date) FROM v_lots WHERE item_name = ? AND qty_remaining > 0 AND expiry_date >= ?"),
    "stock_card_at": ("SELECT stock_after, moved_at FROM v_stock_card WHERE COALESCE(item_code, item_name) = COALESCE(?, ?) "
                      "AND moved_date <= ? ORDER BY moved_at DESC LIMIT 2"),
    "item_unit_factors": "SELECT unit, unit_key, factor FROM v_item_units WHERE COALESCE(item_code, item_name) = COALESCE(?, ?)",
})

# router-expansion templates (rulebook section 2 shifts, 5 price effect, 3 category share, 6 size, 5 unsold)
SQL_TEMPLATES.update({
    "cust_freq": ("SELECT COUNT(*), SUM(CASE WHEN n >= ? THEN 1 ELSE 0 END) FROM (SELECT customer_key, COUNT(*) AS n FROM v_valid_orders "
                  "WHERE order_date BETWEEN ? AND ? AND customer_key IS NOT NULL GROUP BY customer_key)"),
    "customers_recorded": "SELECT COUNT(customer_key) FROM v_valid_orders",
    "staff_revenue": ("SELECT CAST(ROUND(COALESCE(SUM(revenue), 0)) AS INTEGER) FROM v_valid_orders "
                      "WHERE order_date BETWEEN ? AND ? AND UPPER(staff) = ?"),
    "days_over_threshold": ("SELECT COUNT(*) FROM (SELECT order_date FROM v_valid_orders WHERE order_date BETWEEN ? AND ? "
                            "GROUP BY order_date HAVING SUM(revenue) >= ?)"),
    "shift_revenue": ("SELECT SUM(revenue) FROM v_valid_orders WHERE order_date BETWEEN ? AND ? "
                      "AND substr(order_time, 1, 5) BETWEEN ? AND ?"),
    "shift_orders": ("SELECT COUNT(*) FROM v_valid_orders WHERE order_date BETWEEN ? AND ? "
                     "AND substr(order_time, 1, 5) BETWEEN ? AND ?"),
    "shift_time_missing": "SELECT COUNT(*) FROM v_valid_orders WHERE order_date BETWEEN ? AND ? AND (order_time IS NULL OR order_time = '')",
    "qty_by_code": ("SELECT COALESCE(SUM(qty_base), 0) FROM v_valid_lines WHERE is_service_fee = 0 "
                    "AND order_date BETWEEN ? AND ? AND item_code = ?"),
    "qty_by_name": ("SELECT COALESCE(SUM(qty_base), 0) FROM v_valid_lines WHERE is_service_fee = 0 "
                    "AND order_date BETWEEN ? AND ? AND item_name = ?"),
    "category_share": ("SELECT ROUND(100.0 * (SELECT SUM(line_amount) FROM v_valid_lines WHERE is_service_fee = 0 "
                       "AND order_date BETWEEN ? AND ? AND category = ?) / NULLIF((SELECT SUM(revenue) FROM v_valid_orders "
                       "WHERE order_date BETWEEN ? AND ?), 0), 2)"),
    "size_qty": ("SELECT COALESCE(SUM(qty_base), 0) FROM v_valid_lines WHERE is_service_fee = 0 "
                 "AND order_date BETWEEN ? AND ? AND LOWER(TRIM(item_name)) LIKE ?"),
    "unsold_count": ("SELECT COUNT(*) FROM (SELECT DISTINCT COALESCE(item_code, item_name) AS k FROM v_valid_lines "
                     "WHERE is_service_fee = 0 AND order_date < ?) WHERE k NOT IN (SELECT COALESCE(item_code, item_name) "
                     "FROM v_valid_lines WHERE is_service_fee = 0 AND order_date BETWEEN ? AND ?)"),
})

# answer type per intent (rulebook section 9)
ANSWER_TYPE = {
    "revenue": "number", "order_count": "number", "cancel_count": "number", "aov": "number",
    "item_qty": "number", "cancel_rate": "percent", "rev_change_pct": "percent",
    "best_day": "date", "best_item": "string", "topk_items": "list",
    "item_revenue": "number", "category_rev": "number", "sell_price_on_day": "number",
    "cust_group_rev": "number", "payment_method_rev": "number", "channel_rev": "number", "unit_total_qty": "number",
    "best_month": "date", "monthly_series": "list", "streak_bool": "boolean",
    "ingredient_revenue": "number", "rx_nonrx_revenue": "number", "rx_share": "percent",
    "purchase_total": "number", "supplier_top": "string", "purchase_avg_price": "number",
    "stock_qty": "number", "stock_large_unit": "list", "stock_value": "number",
    "cust_freq_count": "number", "cust_freq_share": "percent", "staff_revenue": "number",
    "days_over_threshold": "number", "shift": "number", "price_effect": "percent", "category_share": "percent", "size_qty": "number", "unsold_count": "number",
    "expiry_list": "number", "expiry_nearest_lot": "date",   # expiry_list: "number" (lot count) or "list" (products), set per question
}


def run_template(conn: sqlite3.Connection, intent: str, start: str, end: str, *,
                 k: int | None = None, item: tuple[str | None, str] | None = None,
                 prev: tuple[str, str] | None = None, threshold: float | None = None,
                 values: list[str] | None = None, divisor: float | None = None) -> Any:
    """Execute the template of *intent*; returns the answer value (None when the template has no result)."""
    if intent == "rev_change_pct":
        assert prev is not None
        row = conn.execute(SQL_TEMPLATES[intent], (start, end, prev[0], prev[1])).fetchone()
        return float(row[0]) if row and row[0] is not None else None
    if intent == "topk_items":
        assert k is not None
        return [r[0] for r in conn.execute(SQL_TEMPLATES[intent], (start, end, k)).fetchall()] or None
    if intent == "item_revenue":
        assert item is not None
        code, name = item
        row = (conn.execute(SQL_TEMPLATES["item_revenue_by_code"], (start, end, code)).fetchone() if code
               else conn.execute(SQL_TEMPLATES["item_revenue_by_name"], (start, end, name)).fetchone())
        return int(row[0]) if row and row[0] is not None else None
    if intent == "category_rev":
        assert item is not None
        row = conn.execute(SQL_TEMPLATES["category_revenue"], (start, end, item[1])).fetchone()
        return int(row[0]) if row and row[0] is not None else None
    if intent == "sell_price_on_day":
        assert item is not None
        code, name = item
        rows = (conn.execute(SQL_TEMPLATES["price_on_day_by_code"], (start, code)).fetchall() if code
                else conn.execute(SQL_TEMPLATES["price_on_day_by_name"], (start, name)).fetchall())
        vals = {r[0] for r in rows if r[0] is not None}
        if len(vals) != 1:  # no sale that day, or several prices: not decidable by the template
            return None
        v = float(next(iter(vals)))
        return int(v) if abs(v - round(v)) < 1e-9 else v
    if intent == "days_over_threshold":
        assert threshold is not None
        return int(conn.execute(SQL_TEMPLATES["days_over_threshold"], (start, end, threshold)).fetchone()[0])
    if intent == "category_share":
        assert item is not None
        row = conn.execute(SQL_TEMPLATES["category_share"], (start, end, item[1], start, end)).fetchone()
        return float(row[0]) if row and row[0] is not None else None
    if intent == "size_qty":
        assert values
        v = float(conn.execute(SQL_TEMPLATES["size_qty"], (start, end, values[0])).fetchone()[0] or 0)
        return int(round(v)) if abs(v - round(v)) < 1e-6 else round(v, 2)
    if intent == "unsold_count":
        return int(conn.execute(SQL_TEMPLATES["unsold_count"], (start, start, end)).fetchone()[0])
    if intent == "ingredient_revenue":
        assert item is not None
        row = conn.execute(SQL_TEMPLATES["ingredient_revenue"], (start, end, item[1])).fetchone()
        return int(row[0]) if row and row[0] is not None else None
    if intent == "rx_nonrx_revenue":
        assert values and values[0] in ("rx", "nonrx")
        row = conn.execute(SQL_TEMPLATES[values[0] + "_revenue"], (start, end)).fetchone()
        return int(row[0]) if row and row[0] is not None else None
    if intent == "rx_share":
        row = conn.execute(SQL_TEMPLATES["rx_share"], (start, end)).fetchone()
        return float(row[0]) if row and row[0] is not None else None
    if intent == "cust_group_rev":
        assert item is not None
        row = conn.execute(SQL_TEMPLATES["group_revenue"], (start, end, item[1])).fetchone()
        return int(row[0]) if row and row[0] is not None else None
    if intent in ("payment_method_rev", "channel_rev", "unit_total_qty"):
        assert values
        sql = SQL_TEMPLATES[{"payment_method_rev": "payment_revenue", "channel_rev": "channel_revenue",
                             "unit_total_qty": "unit_total_qty"}[intent]].format(ph=",".join("?" * len(values)))
        row = conn.execute(sql, (start, end, *values)).fetchone()
        if row is None or row[0] is None:
            return None
        if intent == "unit_total_qty":
            v = float(row[0])
            return int(round(v)) if abs(v - round(v)) < 1e-6 else round(v, 2)
        return int(row[0])
    if intent == "item_qty":
        assert item is not None
        code, name = item
        row = (conn.execute(SQL_TEMPLATES["item_qty_by_code"], (start, end, code)).fetchone() if code
               else conn.execute(SQL_TEMPLATES["item_qty_by_name"], (start, end, name)).fetchone())
        val = float(row[0]) if row and row[0] is not None else 0.0
        if divisor:
            val = val / divisor
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


def monthly_revenue(conn: sqlite3.Connection, months: list[tuple[str, str]]) -> list[int]:
    """Revenue (valid orders, rounded to an integer) of each (start, end) month window, in the given order."""
    return [int(conn.execute(SQL_TEMPLATES["revenue"], (a, b)).fetchone()[0] or 0) for a, b in months]
