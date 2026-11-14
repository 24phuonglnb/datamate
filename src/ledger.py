"""SalesLedger construction: order status normalization and unit conversion.

Converts messy business sales tables and mapping configurations into a unified,
rulebook-compliant `SalesLedger` DataFrame where each row represents a sold line item
with normalized order status and quantity converted to the base unit.

Rulebook references:
- §1 Orders & revenue: revenue includes non-cancelled, non-returned orders (including shipping).
  Orders with ANY return (even partial) are returned orders -> exclude ENTIRE order.
- §3 Ranking & §10 Units: best sellers and units ranked/counted by quantity converted to base unit.
  Units without conversion rules are base units with factor 1.
- §8 File conventions: fill down order-level blanks within order, drop export duplicates,
  single order status per order, yearless dates use sheet year.

Public API
----------
normalize_status(value, note=None) -> str
load_unit_conversions(tables, readme) -> dict[(item_key, unit_key), (factor, base_unit)]
build_ledger(tables, mapping=None, readme="") -> (pd.DataFrame, dict[str, Any])
verify_invariants(ledger_df, readme="") -> dict[str, dict[str, Any]]
"""
from __future__ import annotations

import copy
import datetime as dt
import re
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from src.cleaning import (
    META_COLS,
    RawTable,
    drop_export_duplicates,
    fill_order_level,
    infer_kinds,
    is_blank,
    name_has,
    norm_key,
    parse_date,
    parse_datetime,
    parse_number,
    parse_qty,
    split_summary_rows,
)
from src.mapping import Mapping, propose_mapping

# Standard canonical statuses according to Rulebook §8
STATUS_COMPLETED = "hoan_thanh"
STATUS_CANCELLED = "huy"
STATUS_RETURNED = "tra_hang"
STATUS_SHIPPING = "dang_giao"

VALID_STATUSES = {STATUS_COMPLETED, STATUS_CANCELLED, STATUS_RETURNED, STATUS_SHIPPING}

# Priority when resolving order-level status across multiple lines (§1, §8):
# 1. Any returned line (even partial) -> entire order is tra_hang
# 2. Cancelled line -> order is huy
# 3. Shipping line -> order is dang_giao
# 4. Otherwise -> order is hoan_thanh
STATUS_PRIORITY = {
    STATUS_RETURNED: 4,
    STATUS_CANCELLED: 3,
    STATUS_SHIPPING: 2,
    STATUS_COMPLETED: 1,
}

# Regex patterns for status normalization
_RE_HUY = re.compile(
    r"\b(huy|huỷ|cancel|cancelled|khong giao duoc|bung|da huy|da huỷ|khach huy|khach huỷ|khach bung)\b",
    re.I,
)
_RE_TRA = re.compile(
    r"(?<!kiem\s)(?<!dieu\s)\b(tra|return|returned|hoan hang|hoan tra|doi tra|tra lai|khach tra|hang tra ve|khach mang tra|khach tra lai|da tra hang|da hoan hang|doi\s+tra)\b",
    re.I,
)
_RE_GIAO = re.compile(
    r"\b(dang giao|cho giao|shipping|chua giao|dang van chuyen|dang xu ly|dang gui|dang ship|dang giao dich|dang)\b",
    re.I,
)
_RE_XONG = re.compile(
    r"\b(hoan thanh|thanh cong|xong|ok|da giao|da xong|da lay|completed)\b",
    re.I,
)


def normalize_status(value: Any, note: Any = None) -> str:
    """Normalize any raw status or note string into one of the 4 canonical values.

    Canonical statuses:
    - `hoan_thanh`: Hoàn thành, Thành công, Xong, ok, Đã giao, completed, or note without status.
    - `huy`: Huỷ, Hủy, Hủy đơn, khách hủy, cancel, cancelled, Không giao được, khách bùng.
    - `tra_hang`: Đổi trả, Hoàn trả, Trả hàng, trả lại, hàng trả về, khách trả, returned.
    - `dang_giao`: Đang giao, Chờ giao, chưa giao, Đang vận chuyển, Đang xử lý, shipping.

    If value is missing or does not state a status, checks `note`. If `note` also does
    not mention a status, returns `hoan_thanh` (Rulebook §8).
    """
    for raw in (value, note):
        if raw is None or (isinstance(raw, float) and np.isnan(raw)):
            continue
        s = norm_key(raw)
        if not s:
            continue

        if _RE_HUY.search(s):
            return STATUS_CANCELLED

        if _RE_TRA.search(s) and "hoan thanh" not in s:
            return STATUS_RETURNED

        if _RE_GIAO.search(s):
            return STATUS_SHIPPING

        if _RE_XONG.search(s):
            return STATUS_COMPLETED

    return STATUS_COMPLETED


# ---------------------------------------------------------------------- Unit Conversions

_BASE_UNIT_COL = re.compile(r"co ban|co so|(dv|dvt|don vi)( tinh)? (nho|le|goc)$|^(dv|dvt|don vi) (nho|le|goc)")
_CELL_CONV_RE = re.compile(r"^\s*([\d.,]+)\s*([^\d=]+?)\s*=\s*([\d.,]+)\s*([^\d=]+?)\s*$")

_README_CONV_RE = re.compile(
    r"^\s*[-*]\s+([^:\n]+):\s*(\d+(?:[.,]\d+)?)\s*([^=\n]+?)\s*=\s*(\d+(?:[.,]\d+)?)\s*([^\n]+?)\s*$",
    re.M,
)


def _resolve_multi_tier(
    raw_rules: list[tuple[str, str, float, str, str | None]]
) -> dict[tuple[str | None, str], tuple[float, str]]:
    """Chain and resolve multi-tier conversions (e.g. 1 box = 15 blister packs, 1 blister pack = 12 pills).

    Input: list of (item_key, from_unit, factor, to_unit, base_unit_hint)
    Output: dict of (item_key, unit) -> (factor_to_base, base_unit)
    """
    by_item: dict[str, dict[str, tuple[float, str]]] = {}
    base_hints: dict[str, str] = {}
    display: dict[str, str] = {}

    for item_key, u1, factor, u2, base_hint in raw_rules:
        k_item = norm_key(item_key)
        k_u1 = norm_key(u1)
        k_u2 = norm_key(u2)
        if not k_item or not k_u1 or not k_u2:
            continue
        if k_item not in by_item:
            by_item[k_item] = {}
        by_item[k_item][k_u1] = (factor, k_u2)
        # keep the spelling seen in the file ("viên", not "vien") for the base unit shown to users
        display.setdefault(k_u2, re.sub(r"\s+", " ", str(u2).strip()))
        if base_hint:
            base_hints[k_item] = norm_key(base_hint)

    resolved: dict[tuple[str | None, str], tuple[float, str]] = {}

    for k_item, convs in by_item.items():
        all_targets = {target for _, target in convs.values()}
        all_sources = set(convs.keys())
        base_candidates = all_targets - all_sources

        if k_item in base_hints and base_hints[k_item] in all_targets:
            base = base_hints[k_item]
        elif base_candidates:
            base = sorted(base_candidates)[0]
        else:
            base = sorted(all_targets)[0] if all_targets else ""

        for src in all_sources:
            cur = src
            factor = 1.0
            visited = set()
            while cur in convs and cur not in visited:
                visited.add(cur)
                f, nxt = convs[cur]
                factor *= f
                cur = nxt
            final_base = cur if cur == base or cur not in convs else base
            resolved[(k_item, src)] = (factor, final_base)

        if base:
            resolved[(k_item, base)] = (1.0, base)

    return {k: (f, display.get(b, b)) for k, (f, b) in resolved.items()}


def load_unit_conversions(
    tables: list[RawTable], readme: str = ""
) -> dict[tuple[str | None, str], tuple[float, str]]:
    """Extract unit conversion factors from conversion tables and README bullets.

    Returns:
        dict[(item_key, unit_key) -> (factor, base_unit)]
        Where:
        - `factor`: multiplier to convert from `unit` to `base_unit` (`qty_base = qty * factor`).
        - `base_unit`: normalized name of the smallest base unit.
    """
    raw_rules: list[tuple[str, str, float, str, str | None]] = []

    # 1. Parse conversion bullets from README
    if readme:
        for m in _README_CONV_RE.finditer(readme):
            item, q1_s, u1, q2_s, u2 = m.groups()
            q1 = parse_number(q1_s) or 1.0
            q2 = parse_number(q2_s) or 1.0
            factor = q2 / q1 if q1 else 1.0
            raw_rules.append((item.strip(), u1.strip(), factor, u2.strip(), u2.strip()))

    # 2. Parse conversion tables from business data
    for t in tables:
        t_spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", t.name)
        t_k = norm_key(t_spaced)
        df = t.df
        cols = t.columns
        col_keys = [norm_key(c) for c in cols]
        # A conversion table is named so, or is a small table with a factor column next to
        # large/small unit columns (e.g. "Hàng | ĐV lớn | ĐV nhỏ | Hệ số QĐ" in a file named DanhMuc).
        has_factor_col = any(k.startswith("he so") or "quy doi" in k or k.startswith("ti le") for k in col_keys)
        # two unit-like columns: one large unit, one base unit ("ĐV lớn | ĐV nhỏ", "Loại ĐV | ĐV gốc")
        unit_like = [k for k in col_keys if re.search(r"(^|\s)(dv|dvt|don vi)(\s|$)", k)]
        has_unit_pair = len(unit_like) >= 2 and any(_BASE_UNIT_COL.search(k) for k in unit_like)
        is_conv_table = name_has(t_k, ["quy doi", "don vi"]) or (
            has_factor_col and has_unit_pair and len(cols) <= 8)
        if not is_conv_table:
            continue
        if len(df) == 0:
            continue

        col_item = None
        col_unit = None
        col_factor = None
        col_base = None

        for c in cols:
            ck = norm_key(c)
            if not col_item and any(k in ck for k in ["ten san pham", "ten hang", "ten sp", "ten mon", "ten mat hang", "ten thuoc", "ma hang", "ma sp", "ma vach", "mahanghoa", "product"]):
                col_item = c
            elif not col_base and _BASE_UNIT_COL.search(ck):
                col_base = c
            elif not col_factor and (ck.startswith("he so") or ck.startswith("ti le")):
                col_factor = c
            elif not col_unit and (any(k in ck for k in ["quy doi", "don vi tinh", "don vi", "dvt", "quy cach", "donvitinh"])
                                   or re.search(r"(^|\s)dv(\s|$)", ck)):
                col_unit = c
            elif not col_factor and any(k in ck for k in ["ti le", "he so", "quy doi", "bang", "hesoquydoi"]):
                col_factor = c

        # Secondary pass if some columns were not matched
        if not col_unit:
            for c in cols:
                if c not in (col_item, col_base, col_factor) and any(k in norm_key(c) for k in ["don vi", "dvt"]):
                    col_unit = c
                    break
        if not col_factor:
            for c in cols:
                if c not in (col_item, col_base, col_unit) and any(k in norm_key(c) for k in ["bang", "so", "sl"]):
                    col_factor = c
                    break
        if not col_item:  # bare headers such as "Hàng", "Sản phẩm", "Mặt hàng", "Tên"
            for c in cols:
                if c not in (col_unit, col_base, col_factor) and norm_key(c) in (
                        "hang", "san pham", "mat hang", "ten", "hang hoa", "ten hang hoa", "mon", "thuoc"):
                    col_item = c
                    break

        if not (col_item and col_unit and col_factor):
            continue

        for _, row in df.iterrows():
            item_val = row[col_item]
            unit_val = row[col_unit]
            factor_val = row[col_factor]
            base_hint = row[col_base] if col_base else None

            if pd.isna(item_val) or pd.isna(unit_val) or pd.isna(factor_val):
                continue

            num, embedded_unit = parse_qty(factor_val)
            if num is None:
                continue

            target_unit = embedded_unit if embedded_unit else (str(base_hint).strip() if base_hint else "base")
            raw_rules.append((str(item_val).strip(), str(unit_val).strip(), float(num), target_unit, str(base_hint).strip() if base_hint else None))

    # 3. Conversions written inside a catalog cell: "1 thùng = 6 bịch" next to the item name
    for t in tables:
        df = t.df
        for c in t.columns:
            vals = df[c].dropna()
            hits = vals[vals.map(lambda v: isinstance(v, str) and bool(_CELL_CONV_RE.match(v)))]
            if len(hits) < 1 or len(hits) < 0.8 * len(vals):
                continue
            _, name_c = pick_catalog_columns(df.drop(columns=[c]))
            if not name_c:
                continue
            for idx, v in hits.items():
                item_val = df.at[idx, name_c]
                if is_blank(item_val):
                    continue
                q1_s, u1, q2_s, u2 = _CELL_CONV_RE.match(v).groups()
                q1, q2 = parse_number(q1_s) or 1.0, parse_number(q2_s) or 1.0
                raw_rules.append((str(item_val).strip(), u1.strip(), q2 / q1 if q1 else 1.0, u2.strip(), u2.strip()))

    return _resolve_multi_tier(raw_rules)


# ------------------------------------------------------------------ Catalog column picking

_NAME_HINTS = ("ten", "name", "san pham", "hang hoa", "mat hang", "hang", "mon", "thuoc", "dich vu")
_NOT_NAME = ("mo ta", "ghi chu", "nhom", "loai", "thuong hieu", "vi tri", "hinh anh", "thuoc tinh",
             "bao hanh", "don vi", "dvt", "danh muc", "lien quan", "barcode", "ma vach", "ean")


def pick_catalog_columns(c_df: pd.DataFrame, sales_codes: Iterable[Any] | None = None
                         ) -> tuple[str | None, str | None]:
    """Find (code column, name column) of an item catalog from its *contents*.

    Catalog exports shuffle their columns and carry look-alikes ("Mã barcode", "Mã HH liên
    quan", "Mô tả sản phẩm"), so the first column whose name contains "mã" / "tên" is often
    wrong. The code column is the one whose values cover the item codes used on the sales
    lines; the name column is a mostly-filled, mostly-unique text column, preferring
    name-like headers and never description / note / group columns."""
    cols = [c for c in c_df.columns if c not in META_COLS]
    if not cols or c_df.empty:
        return None, None

    def _vals(c: str) -> pd.Series:
        return c_df[c].dropna().map(lambda x: str(x).strip()).loc[lambda x: x != ""]

    code_c = None
    if sales_codes is not None:
        want = {str(x).strip().upper() for x in sales_codes if x is not None and not is_blank(x)}
        if want:
            best = 0.0
            for c in cols:
                have = {v.upper() for v in _vals(c).unique()}
                cover = len(want & have) / len(want)
                if cover > best:
                    best, code_c = cover, c
            if best < 0.5:
                code_c = None
    if code_c is None:
        for c in cols:
            ck = norm_key(c)
            if any(k in ck for k in ("barcode", "ma vach", "ean", "lien quan", "ghi chu", "mo ta")):
                continue
            if re.search(r"(^|\b)(ma|sku|code|id)(\b|$)", ck) or ck.startswith("ma"):
                code_c = c
                break

    n = len(c_df)
    scored: list[tuple[int, float, str]] = []
    for c in cols:
        if c == code_c:
            continue
        ck = norm_key(c)
        if any(k in ck for k in _NOT_NAME) or ck.startswith("ma ") or ck in ("ma", "sku", "id"):
            continue
        v = _vals(c)
        if len(v) < 0.9 * n or v.nunique() < 0.9 * len(v):
            continue
        if v.head(200).map(lambda x: parse_number(x) is not None).mean() > 0.5:
            continue
        hint = next((len(_NAME_HINTS) - i for i, k in enumerate(_NAME_HINTS) if k in ck), 0)
        scored.append((hint, float(v.map(len).mean()), c))
    name_c = max(scored)[2] if scored else None
    return code_c, name_c



# ---------------------------------------------------------------------- Build SalesLedger

CANONICAL_COLUMNS = [
    "order_id",
    "order_date",
    "order_time",
    "status",
    "item_name",
    "item_code",
    "unit",
    "qty",
    "factor",
    "qty_base",
    "base_unit",
    "unit_price",
    "line_amount",
    "customer_name",
    "customer_code",
    "staff",
    "channel",
    "payment_method",
    "src_file",
    "src_sheet",
    "src_row",
]


_NON_ITEM_ADJUSTMENT_RE = re.compile(
    r"^(voucher|phi ship|phi giao hang|phi van chuyen|dung \d+ diem|giam gia hoa don|chiet khau hoa don)$"
)


def build_ledger(
    tables: list[RawTable],
    mapping: Mapping | None = None,
    readme: str = "",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Construct standard SalesLedger DataFrame from cleaned tables and column mapping.

    Steps applied:
    1. Select sales_table and orders_table according to mapping.
    2. Split hand-written summary rows (split_summary_rows).
    3. Fill down order-level blanks within each order (fill_order_level) and drop export duplicates.
    4. Link orders header table if present (supporting different column names via left_on/right_on).
    5. Exclude invoice-level adjustment rows (voucher / shipping fee / loyalty points with blank qty).
    6. Enrich item_name from catalog and customer_name from customer table when only codes are in sales.
    7. Parse date/time, quantity, price, amount cells; unify order placement date per order_id.
    8. Normalize order status at line level, then enforce order-level priority (§1, §8).
    9. Convert quantity to base unit using conversion rules and cross-check with existing qty_base column.

    Returns:
        (ledger_df, issues)
    """
    issues: dict[str, Any] = {
        "summary_rows_dropped": 0,
        "duplicate_rows_dropped": 0,
        "adjustment_rows_dropped": 0,
        "order_level_filled": 0,
        "unparsed_dates": 0,
        "blank_date_cells": 0,
        "unparsed_date_cells": 0,
        "unparsed_amounts": 0,
        "unit_conv_mismatches": 0,
        "warnings": [],
    }

    if mapping is None:
        mapping = propose_mapping(tables, readme)
    else:
        mapping = copy.deepcopy(mapping)

    # 1. Locate sales_table
    sales_t = None
    for t in tables:
        if t.name == mapping.sales_table:
            sales_t = t
            break

    if sales_t is None:
        issues["warnings"].append(f"Sales table '{mapping.sales_table}' not found in tables.")
        return pd.DataFrame(columns=CANONICAL_COLUMNS), issues

    sales_df = sales_t.df.copy()

    # 2. Split summary rows on sales table
    sales_df, removed_summary = split_summary_rows(sales_df)
    issues["summary_rows_dropped"] += len(removed_summary)

    # 3. Fill down order-level blanks and drop export duplicates (§8)
    order_id_col = mapping.sales_columns.get("order_id")
    if order_id_col and order_id_col in sales_df.columns:
        n_before_fill = sales_df[order_id_col].isna().sum()
        sales_df = fill_order_level(sales_df, order_id_col)
        issues["order_level_filled"] = int(n_before_fill - sales_df[order_id_col].isna().sum())

        n_before_dedup = len(sales_df)
        sales_df = drop_export_duplicates(sales_df, order_id_col)
        issues["duplicate_rows_dropped"] = int(n_before_dedup - len(sales_df))

    # 4. Handle separate orders header table if present
    ord_df = None
    ord_oid_col = mapping.orders_columns.get("order_id") or mapping.order_join_key
    sales_oid_col = order_id_col or mapping.order_join_key
    if mapping.orders_table and ord_oid_col:
        ord_t = next((t for t in tables if t.name == mapping.orders_table), None)
        if ord_t is not None:
            ord_df = ord_t.df.copy()
            ord_df, removed_ord_summary = split_summary_rows(ord_df)
            issues["summary_rows_dropped"] += len(removed_ord_summary)
            if ord_oid_col in ord_df.columns:
                ord_df = fill_order_level(ord_df, ord_oid_col)
                ord_df = drop_export_duplicates(ord_df, ord_oid_col)

    if (
        ord_df is not None
        and sales_oid_col
        and ord_oid_col
        and sales_oid_col in sales_df.columns
        and ord_oid_col in ord_df.columns
    ):
        ord_cols_to_pull = {}
        for role, c in mapping.orders_columns.items():
            if c and c in ord_df.columns and c != ord_oid_col:
                if mapping.sales_columns.get(role) is None:
                    ord_cols_to_pull[c] = f"__ord_{role}"
                    mapping.sales_columns[role] = f"__ord_{role}"

        if ord_cols_to_pull:
            subset = ord_df[[ord_oid_col] + list(ord_cols_to_pull.keys())].drop_duplicates(subset=[ord_oid_col])
            subset = subset.rename(columns=ord_cols_to_pull)
            subset["__join_oid"] = subset[ord_oid_col].map(lambda x: str(x).strip() if pd.notna(x) else None)
            subset = subset.drop(columns=[ord_oid_col]).drop_duplicates(subset=["__join_oid"])
            sales_df["__join_oid"] = sales_df[sales_oid_col].map(lambda x: str(x).strip() if pd.notna(x) else None)
            sales_df = sales_df.merge(subset, on="__join_oid", how="left").drop(columns=["__join_oid"])

    # 4b. Exclude invoice-level adjustment rows (voucher / shipping fee / points with blank qty, Rulebook §1)
    item_name_col = mapping.sales_columns.get("item_name")
    qty_col = mapping.sales_columns.get("qty")
    if item_name_col and item_name_col in sales_df.columns and qty_col and qty_col in sales_df.columns:
        adj_mask = sales_df[qty_col].isna() & sales_df[item_name_col].map(
            lambda v: bool(v is not None and not pd.isna(v) and _NON_ITEM_ADJUSTMENT_RE.match(norm_key(v)))
        )
        if adj_mask.any():
            issues["adjustment_rows_dropped"] = int(adj_mask.sum())
            sales_df = sales_df.loc[~adj_mask].reset_index(drop=True)

    # 5. Fallback item_name from catalog table and customer_name from customer table if missing
    item_code_col = mapping.sales_columns.get("item_code")
    if (not item_name_col or item_name_col not in sales_df.columns) and (item_code_col and item_code_col in sales_df.columns):
        for t in tables:
            t_k = norm_key(t.name)
            if name_has(t_k, ["san pham", "hang hoa", "catalog", "danh muc"]):
                c_df = t.df
                cat_code_col, cat_name_col = pick_catalog_columns(c_df, sales_df[item_code_col].dropna().unique())
                if cat_code_col and cat_name_col:
                    cat_map = c_df[[cat_code_col, cat_name_col]].dropna().copy()
                    cat_map["__join_ic"] = cat_map[cat_code_col].map(lambda x: str(x).strip().upper())
                    cat_map = cat_map[["__join_ic", cat_name_col]].rename(columns={cat_name_col: "__item_name"})
                    cat_map = cat_map.drop_duplicates(subset=["__join_ic"])
                    sales_df["__join_ic"] = sales_df[item_code_col].map(
                        lambda x: str(x).strip().upper() if pd.notna(x) else None)
                    sales_df = sales_df.merge(cat_map, on="__join_ic", how="left").drop(columns=["__join_ic"])
                    mapping.sales_columns["item_name"] = "__item_name"
                    item_name_col = "__item_name"
                    break

    cust_name_col = mapping.sales_columns.get("customer_name")
    cust_code_col = mapping.sales_columns.get("customer_code")
    if (not cust_name_col or cust_name_col not in sales_df.columns) and (cust_code_col and cust_code_col in sales_df.columns):
        for t in tables:
            t_k = norm_key(t.name)
            if name_has(t_k, ["khach hang", "doi tac", "customer"]):
                c_df = t.df
                c_code = next((c for c in c_df.columns if any(k in norm_key(c) for k in ["ma kh", "ma khach", "so kh", "customer id", "ma doi tac", "ma"])), None)
                c_name = next((c for c in c_df.columns if any(k in norm_key(c) for k in ["ten kh", "ho ten", "ten khach", "khach hang", "ten doi tac", "ten"])), None)
                if c_code and c_name and c_code in c_df.columns and c_name in c_df.columns:
                    c_map = c_df[[c_code, c_name]].dropna().drop_duplicates(subset=[c_code]).copy()
                    c_map["__join_cc"] = c_map[c_code].map(lambda x: str(x).strip())
                    c_map = c_map[["__join_cc", c_name]].rename(columns={c_name: "__cust_name"}).drop_duplicates(subset=["__join_cc"])
                    sales_df["__join_cc"] = sales_df[cust_code_col].map(lambda x: str(x).strip() if pd.notna(x) else None)
                    sales_df = sales_df.merge(c_map, on="__join_cc", how="left").drop(columns=["__join_cc"])
                    mapping.sales_columns["customer_name"] = "__cust_name"
                    cust_name_col = "__cust_name"
                    break

    # 6. Parse date and time
    date_col = mapping.sales_columns.get("order_date")
    parsed_dates: list[dt.date | None] = []
    parsed_times: list[dt.time | None] = []

    time_col = mapping.sales_columns.get("order_time")
    has_time_col = time_col and time_col in sales_df.columns

    years = sales_df["__year"] if "__year" in sales_df.columns else [None] * len(sales_df)
    raw_dates = sales_df[date_col] if date_col and date_col in sales_df.columns else [None] * len(sales_df)
    raw_times = sales_df[time_col] if has_time_col else [None] * len(sales_df)

    for d_val, y_val, t_val in zip(raw_dates, years, raw_times):
        y_int = int(y_val) if y_val is not None and not (isinstance(y_val, float) and np.isnan(y_val)) else None
        dt_obj = parse_datetime(d_val, year=y_int)
        if dt_obj is not None:
            parsed_dates.append(dt_obj.date())
            if not has_time_col:
                parsed_times.append(dt_obj.time() if (dt_obj.hour or dt_obj.minute or dt_obj.second) else None)
        else:
            parsed_dates.append(None)
            if not has_time_col:
                parsed_times.append(None)

        if has_time_col:
            if isinstance(t_val, dt.time):
                parsed_times.append(t_val)
            elif isinstance(t_val, dt.datetime):
                parsed_times.append(t_val.time())
            elif isinstance(t_val, str) and ":" in t_val:
                # Full "date time" text: keep only the clock part
                m_dt = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$", t_val.strip())
                if m_dt and re.search(r"\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4}", t_val):
                    try:
                        parsed_times.append(dt.time(int(m_dt.group(1)), int(m_dt.group(2)), int(m_dt.group(3) or 0)))
                    except ValueError:
                        parsed_times.append(None)
                    continue
                try:
                    parts = [int(p) for p in re.findall(r"\d+", t_val)[:3]]
                    if len(parts) >= 2:
                        parsed_times.append(dt.time(parts[0], parts[1], parts[2] if len(parts) > 2 else 0))
                    else:
                        parsed_times.append(None)
                except ValueError:
                    parsed_times.append(None)
            else:
                parsed_times.append(None)

    # Cell-level counts before order-level resolution: blank continuation cells of multi-line orders are
    # normal (they take the order's date below); non-blank cells that fail to parse are real problems.
    issues["blank_date_cells"] = sum(d is None and is_blank(v) for d, v in zip(parsed_dates, raw_dates))
    issues["unparsed_date_cells"] = sum(d is None and not is_blank(v) for d, v in zip(parsed_dates, raw_dates))

    # 7. Parse quantities, units, prices, line amounts
    qty_col = mapping.sales_columns.get("qty")
    unit_col = mapping.sales_columns.get("unit")
    price_col = mapping.sales_columns.get("unit_price")
    amt_col = mapping.sales_columns.get("line_amount")

    parsed_qtys: list[float] = []
    parsed_units: list[str] = []
    parsed_prices: list[float] = []
    parsed_amts: list[float] = []

    raw_qtys = sales_df[qty_col] if qty_col and qty_col in sales_df.columns else [None] * len(sales_df)
    raw_units = sales_df[unit_col] if unit_col and unit_col in sales_df.columns else [None] * len(sales_df)
    raw_prices = sales_df[price_col] if price_col and price_col in sales_df.columns else [None] * len(sales_df)
    raw_amts = sales_df[amt_col] if amt_col and amt_col in sales_df.columns else [None] * len(sales_df)

    unparsed_amt_count = 0
    for q_v, u_v, p_v, a_v in zip(raw_qtys, raw_units, raw_prices, raw_amts):
        # Qty & embedded unit
        q_num, q_embedded_unit = parse_qty(q_v)
        unit_str = str(u_v).strip() if (u_v is not None and not pd.isna(u_v)) else (q_embedded_unit or "")
        parsed_qtys.append(float(q_num) if q_num is not None else 1.0)
        parsed_units.append(unit_str)

        # Unit price
        p_num = parse_number(p_v)
        parsed_prices.append(float(p_num) if p_num is not None else 0.0)

        # Line amount
        a_num = parse_number(a_v)
        if a_num is not None:
            parsed_amts.append(float(a_num))
        else:
            # Fallback line amount = qty * price
            calc = (q_num if q_num is not None else 1.0) * (p_num if p_num is not None else 0.0)
            parsed_amts.append(float(calc))
            if a_v is not None and not pd.isna(a_v):
                unparsed_amt_count += 1

    issues["unparsed_amounts"] = unparsed_amt_count

    # 8. Normalize order status at line level & enforce order-level priority (§1, §8)
    status_col = mapping.sales_columns.get("status")
    note_col = mapping.sales_columns.get("note")

    raw_statuses = sales_df[status_col] if status_col and status_col in sales_df.columns else [None] * len(sales_df)
    raw_notes = sales_df[note_col] if note_col and note_col in sales_df.columns else [None] * len(sales_df)

    line_statuses = [
        normalize_status(s_v, n_v) for s_v, n_v in zip(raw_statuses, raw_notes)
    ]

    # Resolve order-level status and placement date/time if order_id is present (§1, §8)
    raw_oids = sales_df[order_id_col] if order_id_col and order_id_col in sales_df.columns else [None] * len(sales_df)
    normalized_order_statuses = line_statuses.copy()

    if order_id_col and order_id_col in sales_df.columns:
        order_status_map: dict[Any, str] = {}
        order_date_map: dict[Any, dt.date] = {}
        order_time_map: dict[Any, dt.time] = {}

        for oid, st, d_val, t_val in zip(raw_oids, line_statuses, parsed_dates, parsed_times):
            if pd.isna(oid):
                continue
            cur = order_status_map.get(oid)
            if cur is None or STATUS_PRIORITY.get(st, 0) > STATUS_PRIORITY.get(cur, 0):
                order_status_map[oid] = st
            if d_val is not None:
                cur_d = order_date_map.get(oid)
                if cur_d is None or d_val < cur_d:
                    order_date_map[oid] = d_val
                    if t_val is not None:
                        order_time_map[oid] = t_val
            if t_val is not None and oid not in order_time_map:
                order_time_map[oid] = t_val

        # Overwrite all lines of each order with its resolved order-level status and placement date
        for i, oid in enumerate(raw_oids):
            if not pd.isna(oid):
                if oid in order_status_map:
                    normalized_order_statuses[i] = order_status_map[oid]
                if oid in order_date_map:
                    parsed_dates[i] = order_date_map[oid]
                if oid in order_time_map and parsed_times[i] is None:
                    parsed_times[i] = order_time_map[oid]

    # Rows still without a date after taking the order's date: these fall out of every period filter
    unparsed_date_count = sum(d is None for d in parsed_dates)
    issues["unparsed_dates"] = unparsed_date_count
    if unparsed_date_count > 0:
        issues["warnings"].append(f"{unparsed_date_count} rows have no order date after order-level resolution.")
    if issues["unparsed_date_cells"] > 0:
        issues["warnings"].append(f"{issues['unparsed_date_cells']} non-blank date cells could not be parsed.")

    # 9. Unit conversion and base unit calculation
    conversions = load_unit_conversions(tables, readme)

    raw_names = sales_df[item_name_col] if item_name_col and item_name_col in sales_df.columns else [""] * len(sales_df)
    raw_codes = sales_df[item_code_col] if item_code_col and item_code_col in sales_df.columns else [None] * len(sales_df)

    factors: list[float] = []
    base_units: list[str] = []
    computed_qty_bases: list[float] = []

    qty_base_col = mapping.sales_columns.get("qty_base")
    raw_qty_bases = sales_df[qty_base_col] if qty_base_col and qty_base_col in sales_df.columns else [None] * len(sales_df)

    unit_mismatch_count = 0

    for name_v, code_v, unit_v, qty_v, qb_raw in zip(raw_names, raw_codes, parsed_units, parsed_qtys, raw_qty_bases):
        k_name = norm_key(name_v) if name_v else None
        k_code = norm_key(code_v) if code_v else None
        k_unit = norm_key(unit_v) if unit_v else ""

        # Lookup conversion factor
        conv = None
        if k_name and (k_name, k_unit) in conversions:
            conv = conversions[(k_name, k_unit)]
        elif k_code and (k_code, k_unit) in conversions:
            conv = conversions[(k_code, k_unit)]
        elif (None, k_unit) in conversions:
            conv = conversions[(None, k_unit)]

        if conv is not None:
            f, bu = conv
        else:
            # Rulebook §10: units without conversion rule are base unit with factor 1
            f, bu = 1.0, unit_v or "cơ bản"

        factors.append(f)
        base_units.append(bu)
        expected_qb = qty_v * f

        # Cross-check with existing qty_base column if present
        actual_qb = parse_number(qb_raw)
        if actual_qb is not None:
            if abs(actual_qb - expected_qb) > 1e-3:
                unit_mismatch_count += 1
            computed_qty_bases.append(float(actual_qb))
        else:
            computed_qty_bases.append(float(expected_qb))

    issues["unit_conv_mismatches"] = unit_mismatch_count

    # 10. Assemble canonical SalesLedger DataFrame
    cust_name_col = mapping.sales_columns.get("customer_name")
    cust_code_col = mapping.sales_columns.get("customer_code")
    staff_col = mapping.sales_columns.get("staff")
    channel_col = mapping.sales_columns.get("channel")
    payment_col = mapping.sales_columns.get("payment_method")

    ledger_data = {
        "order_id": [str(x) if x is not None and not pd.isna(x) else None for x in raw_oids],
        "order_date": parsed_dates,
        "order_time": parsed_times,
        "status": normalized_order_statuses,
        "item_name": [str(x) if x is not None and not pd.isna(x) else "" for x in raw_names],
        "item_code": [str(x) if x is not None and not pd.isna(x) else None for x in raw_codes],
        "unit": parsed_units,
        "qty": parsed_qtys,
        "factor": factors,
        "qty_base": computed_qty_bases,
        "base_unit": base_units,
        "unit_price": parsed_prices,
        "line_amount": parsed_amts,
        "customer_name": [str(x) if x is not None and not pd.isna(x) else None for x in (sales_df[cust_name_col] if cust_name_col and cust_name_col in sales_df.columns else [None] * len(sales_df))],
        "customer_code": [str(x) if x is not None and not pd.isna(x) else None for x in (sales_df[cust_code_col] if cust_code_col and cust_code_col in sales_df.columns else [None] * len(sales_df))],
        "staff": [str(x) if x is not None and not pd.isna(x) else None for x in (sales_df[staff_col] if staff_col and staff_col in sales_df.columns else [None] * len(sales_df))],
        "channel": [str(x) if x is not None and not pd.isna(x) else None for x in (sales_df[channel_col] if channel_col and channel_col in sales_df.columns else [None] * len(sales_df))],
        "payment_method": [str(x) if x is not None and not pd.isna(x) else None for x in (sales_df[payment_col] if payment_col and payment_col in sales_df.columns else [None] * len(sales_df))],
        "src_file": sales_df["__file"].astype(str) if "__file" in sales_df.columns else ["" for _ in range(len(sales_df))],
        "src_sheet": sales_df["__sheet"] if "__sheet" in sales_df.columns else [None for _ in range(len(sales_df))],
        "src_row": sales_df["__row"] if "__row" in sales_df.columns else [i + 1 for i in range(len(sales_df))],
    }

    ledger_df = pd.DataFrame(ledger_data)

    # Retain remaining original columns under their original names
    already_used = set(CANONICAL_COLUMNS) | set(META_COLS)
    for c in sales_df.columns:
        if c not in already_used and not str(c).startswith("__ord_") and str(c) not in ledger_df.columns:
            ledger_df[c] = sales_df[c].values

    return ledger_df, issues


# ---------------------------------------------------------------------- Invariant Checks

_README_MAX_DATE_RE = re.compile(
    r"Dữ liệu có đến hết\s+(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", re.I
)


def verify_invariants(
    ledger_df: pd.DataFrame, readme: str = ""
) -> dict[str, dict[str, Any]]:
    """Verify data invariants on a constructed SalesLedger.

    Returns dict of invariant checks with status ("PASS", "FAIL", "N/A") and metrics:
    1. single_date_and_status_per_order
    2. arithmetic_line_amount (qty * unit_price ~= line_amount on >= 95% lines)
    3. constant_unit_factor (qty_base / qty is constant per item and unit)
    4. cancellation_rate (cancellation rate between 0% and 15%)
    5. date_range_matches_readme (max date <= README max date)
    """
    results: dict[str, dict[str, Any]] = {}

    n = len(ledger_df)
    if n == 0:
        return {
            "single_date_and_status_per_order": {"status": "N/A", "message": "empty ledger"},
            "arithmetic_line_amount": {"status": "N/A", "message": "empty ledger"},
            "constant_unit_factor": {"status": "N/A", "message": "empty ledger"},
            "cancellation_rate": {"status": "N/A", "message": "empty ledger"},
            "date_range_matches_readme": {"status": "N/A", "message": "empty ledger"},
        }

    # 1. Single date and status per order
    has_oid = ledger_df["order_id"].notna()
    if has_oid.any():
        grp = ledger_df[has_oid].groupby("order_id", sort=False)
        date_nun = grp["order_date"].nunique()
        stat_nun = grp["status"].nunique()

        single_date_ratio = (date_nun <= 1).mean()
        single_stat_ratio = (stat_nun <= 1).mean()

        passed = bool(single_date_ratio >= 0.99 and single_stat_ratio >= 0.999)
        results["single_date_and_status_per_order"] = {
            "status": "PASS" if passed else "FAIL",
            "single_date_ratio": float(single_date_ratio),
            "single_status_ratio": float(single_stat_ratio),
            "total_orders": int(len(grp)),
        }
    else:
        results["single_date_and_status_per_order"] = {
            "status": "N/A",
            "message": "No order_id in table (line-only ledger)",
        }

    # 2. Arithmetic line amount: qty * unit_price ~= line_amount on >= 95% of lines
    # For discounts or zero prices, allow line_amount <= qty * unit_price + 1e-3
    has_num = (ledger_df["qty"] > 0) & (ledger_df["unit_price"] > 0)
    if has_num.sum() >= 50:
        sub = ledger_df[has_num]
        expected = sub["qty"] * sub["unit_price"]
        actual = sub["line_amount"]
        # Match if exactly equal or line has discount (actual <= expected)
        arith_ok = (np.abs(expected - actual) <= 1.0) | ((actual <= expected + 1e-3) & (actual >= 0))
        ratio = float(arith_ok.mean())
        results["arithmetic_line_amount"] = {
            "status": "PASS" if ratio >= 0.95 else "FAIL",
            "match_ratio": ratio,
            "evaluated_lines": int(has_num.sum()),
        }
    else:
        results["arithmetic_line_amount"] = {
            "status": "N/A",
            "message": f"Too few lines with positive qty and price ({has_num.sum()} lines)",
        }

    # 3. Constant unit factor: qty_base / qty is constant per (item, unit)
    has_unit = ledger_df["unit"].astype(str).str.strip().ne("")
    valid_qty = (ledger_df["qty"] > 0) & has_unit
    if valid_qty.any():
        sub = ledger_df[valid_qty].copy()
        sub["_ratio"] = (sub["qty_base"] / sub["qty"]).round(4)
        item_ident = sub["item_name"].where(
            sub["item_name"].astype(str).str.strip() != "",
            sub["item_code"].fillna("item"),
        )
        sub["_item"] = item_ident
        grp_k = sub.groupby(["_item", "unit"], sort=False)["_ratio"].nunique()
        constant_ratio = float((grp_k <= 1).mean())
        results["constant_unit_factor"] = {
            "status": "PASS" if constant_ratio >= 0.95 else "FAIL",
            "constant_ratio": constant_ratio,
            "distinct_item_units": int(len(grp_k)),
        }
    else:
        results["constant_unit_factor"] = {"status": "N/A", "message": "No unit column present in table"}

    # 4. Cancellation rate in 0% - 15%
    cancelled_lines = (ledger_df["status"] == STATUS_CANCELLED).sum()
    cancel_ratio = float(cancelled_lines / n)
    results["cancellation_rate"] = {
        "status": "PASS" if 0.0 <= cancel_ratio <= 0.15 else "FAIL",
        "cancellation_rate": cancel_ratio,
        "cancelled_lines": int(cancelled_lines),
        "total_lines": int(n),
    }

    # 5. Date range matches README "Dữ liệu có đến hết dd/mm/yyyy"
    if readme:
        m = _README_MAX_DATE_RE.search(readme)
        valid_dates = [d for d in ledger_df["order_date"] if d is not None and not pd.isna(d)]
        if m and valid_dates:
            d_d, d_m, d_y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            readme_max_date = dt.date(d_y, d_m, d_d)
            actual_max_date = max(valid_dates)
            actual_min_date = min(valid_dates)

            # Max date should not exceed readme_max_date (or within a few days)
            diff_days = (actual_max_date - readme_max_date).days
            matched = diff_days <= 1  # allows at most 1 day drift if any
            results["date_range_matches_readme"] = {
                "status": "PASS" if matched else "FAIL",
                "readme_max_date": readme_max_date.isoformat(),
                "actual_max_date": actual_max_date.isoformat(),
                "actual_min_date": actual_min_date.isoformat(),
                "diff_days": diff_days,
            }
        else:
            results["date_range_matches_readme"] = {
                "status": "N/A",
                "message": "Could not find max date in README or no valid dates in ledger",
            }
    else:
        results["date_range_matches_readme"] = {"status": "N/A", "message": "No README text provided"}

    return results
