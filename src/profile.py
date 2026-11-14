"""Shop profile builder for unanswerable and abstain decisions (Task T7).

Produces a machine-readable JSON-compatible profile for each shop indicating:
1. README data end date vs actual table date bounds.
2. Exact date ranges and row counts per table role (sales, purchases, inventory, etc.).
3. Semantic capability flags (`has.*`) indicating presence of data dimensions:
   - Core tables: sales, purchases, inventory, debt, expenses, delivery, catalog, unit_conversion, price_history
   - Core attributes: order_id, customer_code, customer_name, customer_group, staff, channel, payment_method, order_time, category, cost_price, lots_expiry
   - Auxiliary flags: customer_address, customer_gender, return_reason, purchase_price
4. period_coverage(profile, table_role, start, end) -> "full" | "partial" | "none"

Public API
----------
build_profile(business_dir, mapping=None, tables=None, readme=None) -> dict
period_coverage(profile, table_role, start, end) -> "full" | "partial" | "none"
extract_readme_data_end(readme_text) -> str | None
detect_has_flags(mapping, tables, readme="", business_dir=None) -> dict[str, bool]
"""
from __future__ import annotations

import calendar
import datetime as dt
import re
from pathlib import Path
from typing import Any

import pandas as pd

from src.cleaning import (
    META_COLS,
    RawTable,
    load_business,
    norm_key,
    parse_date,
    strip_accents,
)
from src.ledger import load_unit_conversions
from src.mapping import Mapping, propose_mapping
from src.views import can_build_ledger

# Regex pattern for extracting data end date from README
_README_END_DATE_PATTERNS = [
    re.compile(r"dữ liệu có đến hết\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", re.I),
    re.compile(r"đến hết\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", re.I),
    re.compile(r"đến ngày\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", re.I),
    re.compile(r"(?:đến|tính đến)\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", re.I),
    re.compile(r"dữ liệu có đến hết\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", re.I),
    re.compile(r"đến hết\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", re.I),
]

_README_EMPTY_COLS_PATTERN = re.compile(
    r"\*\*([^\*]+)\*\*:\s*cột trống,\s*không có dữ liệu", re.I
)


def extract_readme_data_end(readme_text: str | None) -> str | None:
    """Extract data end date mentioned in README (e.g. 'Dữ liệu có đến hết 24/08/2026.').

    Returns ISO date string 'YYYY-MM-DD' or None if not found.
    """
    if not readme_text:
        return None

    for pat in _README_END_DATE_PATTERNS:
        m = pat.search(readme_text)
        if m:
            raw = m.group(1).strip()
            if "/" in raw:
                d, mo, y = raw.split("/")
                return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            return raw
    return None


def _find_readme_empty_columns(readme_text: str | None) -> set[str]:
    """Find column names that the README explicitly marks as empty / no data."""
    if not readme_text:
        return set()
    empty_cols = set()
    for m in _README_EMPTY_COLS_PATTERN.finditer(readme_text):
        empty_cols.add(norm_key(m.group(1)))
    return empty_cols


def extract_table_date_range(
    table: RawTable, date_col: str | None = None
) -> tuple[str | None, str | None]:
    """Fast extraction of min and max dates from a RawTable using unique values."""
    if table.df.empty:
        return None, None

    col_to_use = None
    if date_col and date_col in table.df.columns:
        col_to_use = date_col
    else:
        # Search for any candidate date column
        for c in table.df.columns:
            if c in META_COLS:
                continue
            k = norm_key(c)
            if any(w in k for w in ["ngay", "date", "thoi gian", "thoi diem"]):
                col_to_use = c
                break

    if not col_to_use:
        return None, None

    series = table.df[col_to_use].dropna()
    if series.empty:
        return None, None

    # Performance optimization: parse unique values only
    uniq_vals = series.unique()
    parsed_dates = []
    for val in uniq_vals:
        d = parse_date(val)
        if d is not None:
            parsed_dates.append(d)

    if not parsed_dates:
        return None, None

    return min(parsed_dates).isoformat(), max(parsed_dates).isoformat()


def detect_has_flags(
    mapping: Mapping,
    tables: list[RawTable],
    readme: str = "",
    business_dir: Path | None = None,
) -> dict[str, bool]:
    """Infer semantic capability flags for a business.

    Strict rulebook-based criteria:
    - Independent of business_id or question id.
    - Directly derived from table roles, column roles, and cell schemas.
    """
    empty_readme_cols = _find_readme_empty_columns(readme)

    def _col_valid(col_name: str | None) -> bool:
        if not col_name:
            return False
        return norm_key(col_name) not in empty_readme_cols

    # 1. sales: Valid line-item sales ledger present
    has_sales = can_build_ledger(tables, mapping, readme)

    # 2. order_id: Real order ID present (not row-level synthetic fallback)
    oid_col = mapping.get_column("order_id")
    has_order_id = _col_valid(oid_col) and not str(oid_col).startswith("ROW_")

    # 3. customer_code
    cc_col = mapping.get_column("customer_code")
    has_customer_code = _col_valid(cc_col) or any(
        any(
            re.search(r"\b(ma khach|ma khach hang|ma kh|customer id|so kh)\b", norm_key(c))
            for c in t.columns
            if _col_valid(c)
        )
        for t in tables
    )

    # 4. customer_name
    cn_col = mapping.get_column("customer_name")
    has_customer_name = _col_valid(cn_col) or any(
        any(
            re.search(r"\b(ten khach|ten khach hang|khach hang|ben mua|doi tac)\b", norm_key(c))
            for c in t.columns
            if _col_valid(c)
        )
        for t in tables
        if any(w in norm_key(t.name) for w in ["khach", "don hang", "hoa don", "ban hang"])
    )

    # 5. customer_group: explicit customer tier / group column (nhóm khách)
    # Note: exclude 'loai hinh khach' (individual vs company) which is not a customer group (§1).
    has_customer_group = any(
        any(
            re.search(r"\b(nhom khach|nhom khach hang|nhom kh|doi tuong kh|phan loai kh)\b", norm_key(c))
            for c in t.columns
            if _col_valid(c)
        )
        for t in tables
    )

    # 6. staff: salesperson / employee / technician column
    st_col = mapping.get_column("staff")
    has_staff = _col_valid(st_col) or any(
        any(
            re.search(r"\b(nhan vien|nguoi ban|ma nv|tho|tho lam phieu)\b", norm_key(c))
            for c in t.columns
            if _col_valid(c)
        )
        for t in tables
    )

    # 7. channel: sales channel / order source
    ch_col = mapping.get_column("channel")
    has_channel = _col_valid(ch_col) or any(
        any(
            re.search(r"\b(kenh ban|kenh dat|nguon don|nguon|ban qua)\b", norm_key(c))
            for c in t.columns
            if _col_valid(c)
        )
        for t in tables
    )

    # 8. payment_method: payment method column
    pm_col = mapping.get_column("payment_method")
    has_payment_method = _col_valid(pm_col) or any(
        any(
            re.search(r"\b(hinh thuc thanh toan|phuong thuc thanh toan|phuong thuc tt|pttt|httt|loai tt|thanh toan bang|tra bang)\b", norm_key(c))
            for c in t.columns
            if _col_valid(c)
        )
        for t in tables
    )

    # 9. order_time: time of order (HH:MM:SS)
    ot_col = mapping.get_column("order_time")
    has_order_time = _col_valid(ot_col)
    if not has_order_time:
        od_col = mapping.get_column("order_date")
        if od_col:
            # Check if order_date column contains time strings
            sales_t = next((t for t in tables if t.name == mapping.sales_table), None)
            df_to_check = None
            if sales_t and od_col in sales_t.df.columns:
                df_to_check = sales_t.df
            elif mapping.orders_table:
                ord_t = next((t for t in tables if t.name == mapping.orders_table), None)
                if ord_t and od_col in ord_t.df.columns:
                    df_to_check = ord_t.df
            if df_to_check is not None and not df_to_check.empty:
                s_sample = df_to_check[od_col].dropna().astype(str).head(100)
                if any(re.search(r"\d{1,2}:\d{2}", val) for val in s_sample):
                    has_order_time = True

    # 10. catalog: product catalog / menu table
    has_catalog = any(
        aux.role == "catalog" for aux in mapping.auxiliary_tables.values()
    ) or any(
        any(w in norm_key(t.name) for w in ["danh muc", "san pham", "hang hoa", "menu", "thuoc"])
        for t in tables
    )

    # 11. category: product category / category column in sales, orders or catalog
    has_category = any(
        any(
            re.search(r"\b(nhom hang|nganh hang|loai hang|nhom sp|phan loai|danh muc|category)\b", norm_key(c))
            for c in t.columns
            if _col_valid(c)
        )
        for t in tables
    )

    # 12. unit_conversion: conversion table or README conversion rules
    has_unit_conversion = any(
        aux.role == "unit_conversion" for aux in mapping.auxiliary_tables.values()
    )
    if not has_unit_conversion:
        conversions = load_unit_conversions(tables, readme)
        has_unit_conversion = len(conversions) > 0

    # 13. cost_price: cost price on sales line items (§5)
    cp_col = mapping.get_column("cost_price")
    has_cost_price = _col_valid(cp_col) or any(
        any(
            re.search(r"\b(gia von|gia von luc ban)\b", norm_key(c))
            for c in t.columns
            if _col_valid(c)
        )
        for t in tables
        if t.name == mapping.sales_table or (mapping.orders_table and t.name == mapping.orders_table)
    )

    # 14. purchases: purchase orders / receiving slips
    has_purchases = any(
        aux.role == "purchases" for aux in mapping.auxiliary_tables.values()
    ) or any(
        any(w in norm_key(t.name) for w in ["nhap hang", "phieu nhap", "nhap"])
        for t in tables
    )

    # 15. inventory: stock / inventory balance table
    has_inventory = any(
        aux.role == "inventory" for aux in mapping.auxiliary_tables.values()
    ) or any(
        any(w in norm_key(t.name) for w in ["ton kho", "the kho", "ton"])
        for t in tables
    )

    # 16. debt: accounts receivable / debt tracking with balances
    # Must have explicit debt balance column (con_no, no_hien_tai, du_no)
    # Payment due terms alone (e.g. biz_117 Han tra) without balances do not constitute debt balance tracking.
    has_debt = False
    for t in tables:
        t_k = norm_key(t.name)
        if any(w in t_k for w in ["cong no", "so no", "so han no", "han no"]):
            # Check if table has balance column
            if any(
                re.search(r"\b(con no|so tien no|du no|no hien tai|tien no|chua tra)\b", norm_key(c))
                for c in t.columns
                if _col_valid(c)
            ):
                has_debt = True
                break
        elif any(
            re.search(r"\b(con no|no hien tai|du no)\b", norm_key(c))
            for c in t.columns
            if _col_valid(c)
        ):
            has_debt = True
            break

    # 17. expenses: expense log / operational expense table
    has_expenses = any(
        aux.role == "expenses" for aux in mapping.auxiliary_tables.values()
    ) or any(
        any(w in norm_key(t.name) for w in ["chi phi", "so chi phi"])
        for t in tables
    )

    # 18. lots_expiry: lot batch numbers and expiration dates
    has_lots_expiry = any(
        any(
            re.search(r"\b(han dung|han su dung|hsd|ngay het han|lo hang|so lo|ma lo)\b", norm_key(c))
            for c in t.columns
            if _col_valid(c)
        )
        for t in tables
    ) or any(
        any(w in norm_key(t.name) for w in ["lo hang", "chi tiet don lo", "don hang lo"])
        for t in tables
    )

    # 19. price_history: price changes / price book over time
    has_price_history = any(
        aux.role == "price_history" for aux in mapping.auxiliary_tables.values()
    ) or any(
        any(w in norm_key(t.name) for w in ["lich su gia", "bang gia"])
        for t in tables
    )

    # 20. delivery: delivery slips / shipping records
    has_delivery = any(
        aux.role == "delivery" for aux in mapping.auxiliary_tables.values()
    ) or any(
        any(w in norm_key(t.name) for w in ["giao hang", "van chuyen", "ship"])
        for t in tables
    )

    # Additional informative flags for question filtering
    # 21. customer_address: customer address / street info
    has_customer_address = any(
        any(
            re.search(r"\b(dia chi|duong|khu vuc|quan huyen|tinh thanh)\b", norm_key(c))
            for c in t.columns
            if _col_valid(c)
        )
        for t in tables
    )

    # 22. customer_gender: customer gender info (must not be empty in README)
    has_customer_gender = any(
        any(
            re.search(r"\b(gioi tinh)\b", norm_key(c))
            for c in t.columns
            if _col_valid(c)
        )
        for t in tables
    )

    # 23. return_reason: cancellation / return reason column
    has_return_reason = any(
        any(
            re.search(r"\b(ly do tra|ly do huy|ghi chu tra|ly do)\b", norm_key(c))
            for c in t.columns
            if _col_valid(c)
        )
        for t in tables
    )

    # 24. purchase_price: purchase unit price in purchases table
    has_purchase_price = False
    if has_purchases:
        for t in tables:
            t_k = norm_key(t.name)
            if any(w in t_k for w in ["nhap", "nhap hang"]):
                if any(
                    re.search(r"\b(don gia nhap|gia nhap|tien nhap|don gia|gia mua)\b", norm_key(c))
                    for c in t.columns
                    if _col_valid(c)
                ):
                    has_purchase_price = True
                    break

    return {
        "sales": has_sales,
        "order_id": has_order_id,
        "customer_code": has_customer_code,
        "customer_name": has_customer_name,
        "customer_group": has_customer_group,
        "staff": has_staff,
        "channel": has_channel,
        "payment_method": has_payment_method,
        "order_time": has_order_time,
        "catalog": has_catalog,
        "category": has_category,
        "unit_conversion": has_unit_conversion,
        "cost_price": has_cost_price,
        "purchases": has_purchases,
        "inventory": has_inventory,
        "debt": has_debt,
        "expenses": has_expenses,
        "lots_expiry": has_lots_expiry,
        "price_history": has_price_history,
        "delivery": has_delivery,
        "customer_address": has_customer_address,
        "customer_gender": has_customer_gender,
        "return_reason": has_return_reason,
        "purchase_price": has_purchase_price,
    }


def build_profile(
    business_dir: str | Path,
    mapping: Mapping | None = None,
    tables: list[RawTable] | None = None,
    readme: str | None = None,
) -> dict[str, Any]:
    """Build a complete machine-readable profile for a shop.

    Args:
        business_dir: Directory of the business (e.g. 'data/train/data/biz_101').
        mapping: Optional precomputed Mapping object. Inferred if None.
        tables: Optional preloaded list of RawTable. Loaded if None.
        readme: Optional README content string. Read from disk if None.

    Returns:
        JSON-serializable dictionary with structure:
        {
          "business_id": "biz_103",
          "data_end_readme": "2026-07-09",
          "tables": {
            "sales": {"date_min": "2025-04-01", "date_max": "2026-07-09", "rows": 45534, "table_name": "..."},
            "purchases": {...}
          },
          "has": {...},
          "notes": [...]
        }
    """
    bpath = Path(business_dir)
    biz_id = bpath.name

    if readme is None:
        rm_file = bpath / "README.md"
        readme = rm_file.read_text(encoding="utf-8") if rm_file.is_file() else ""

    if tables is None:
        tables = load_business(bpath)

    if mapping is None:
        mapping = propose_mapping(tables, readme)

    data_end_readme = extract_readme_data_end(readme)

    tables_profile: dict[str, dict[str, Any]] = {}
    notes: list[str] = []

    # 1. Primary sales / transaction table
    sales_t = next((t for t in tables if t.name == mapping.sales_table), None)
    if sales_t is not None:
        date_col = mapping.get_column("order_date")
        d_min, d_max = None, None
        if date_col and date_col in sales_t.df.columns:
            d_min, d_max = extract_table_date_range(sales_t, date_col)
        elif mapping.orders_table:
            ord_t = next((t for t in tables if t.name == mapping.orders_table), None)
            if ord_t is not None and date_col and date_col in ord_t.df.columns:
                d_min, d_max = extract_table_date_range(ord_t, date_col)

        tables_profile["sales"] = {
            "date_min": d_min,
            "date_max": d_max,
            "rows": len(sales_t.df),
            "table_name": sales_t.name,
        }

        # Check README discrepancy
        if data_end_readme and d_max and data_end_readme != d_max:
            notes.append(
                f"Discrepancy: README data_end ({data_end_readme}) != actual sales date_max ({d_max})"
            )

    # 2. Auxiliary tables grouped by semantic role
    for aux in mapping.auxiliary_tables.values():
        raw_t = next((t for t in tables if t.name == aux.name), None)
        if raw_t is None:
            continue

        d_min, d_max = extract_table_date_range(raw_t)
        role = aux.role

        if role not in tables_profile:
            tables_profile[role] = {
                "date_min": d_min,
                "date_max": d_max,
                "rows": len(raw_t.df),
                "table_name": raw_t.name,
            }
        else:
            # Aggregate stats across multiple tables of the same role
            existing = tables_profile[role]
            all_mins = [m for m in (existing.get("date_min"), d_min) if m]
            all_maxs = [m for m in (existing.get("date_max"), d_max) if m]
            tables_profile[role] = {
                "date_min": min(all_mins) if all_mins else None,
                "date_max": max(all_maxs) if all_maxs else None,
                "rows": existing["rows"] + len(raw_t.df),
                "table_name": f"{existing['table_name']}, {raw_t.name}",
            }

        # Also map debt role specifically if table pertains to debt
        if any(w in norm_key(raw_t.name) for w in ["cong no", "so no", "so han no", "han no"]):
            if "debt" not in tables_profile:
                tables_profile["debt"] = {
                    "date_min": d_min,
                    "date_max": d_max,
                    "rows": len(raw_t.df),
                    "table_name": raw_t.name,
                }

    # 3. Semantic capability flags
    has_flags = detect_has_flags(mapping, tables, readme, business_dir=bpath)

    return {
        "business_id": biz_id,
        "data_end_readme": data_end_readme,
        "tables": tables_profile,
        "has": has_flags,
        "notes": notes,
    }


def _normalize_iso_date(val: str | dt.date | dt.datetime, is_end: bool = False) -> str | None:
    """Normalize input date parameter to 'YYYY-MM-DD'."""
    if val is None:
        return None
    if isinstance(val, (dt.date, dt.datetime)):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    if not s:
        return None

    # Handle month format 'YYYY-MM'
    m_month = re.fullmatch(r"(\d{4})-(\d{1,2})", s)
    if m_month:
        y, mo = int(m_month.group(1)), int(m_month.group(2))
        if is_end:
            last_day = calendar.monthrange(y, mo)[1]
            return f"{y:04d}-{mo:02d}-{last_day:02d}"
        return f"{y:04d}-{mo:02d}-01"

    # Handle full date 'YYYY-MM-DD'
    m_iso = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m_iso:
        return m_iso.group(1)

    # Fallback to parse_date
    parsed = parse_date(s)
    if parsed:
        return parsed.isoformat()
    return None


def period_coverage(
    profile: dict[str, Any],
    table_role: str,
    start: str | dt.date | dt.datetime,
    end: str | dt.date | dt.datetime,
) -> str:
    """Check whether a query period is covered by the shop's data for `table_role`.

    Returns:
    - 'full': query period is entirely within [date_min, date_max]
    - 'partial': query period partially overlaps with [date_min, date_max]
    - 'none': query period lies entirely outside [date_min, date_max], or table has no date range

    Per Rulebook §7:
    - Period completely outside -> unanswerable
    - Period partially inside -> answerable calculated over the overlapping portion
    """
    tbl_info = profile.get("tables", {}).get(table_role)
    if not tbl_info:
        return "none"

    t_min = tbl_info.get("date_min")
    t_max = tbl_info.get("date_max")
    if not t_min or not t_max:
        return "none"

    s_str = _normalize_iso_date(start, is_end=False)
    e_str = _normalize_iso_date(end, is_end=True)
    if not s_str or not e_str:
        return "none"

    if s_str > e_str:
        s_str, e_str = e_str, s_str

    # Completely outside
    if e_str < t_min or s_str > t_max:
        return "none"

    # Completely covered
    if s_str >= t_min and e_str <= t_max:
        return "full"

    # Partial overlap
    return "partial"
