"""SQLite database builder, rulebook-compliant views, and prompt schema formatter (Task T4).

Builds an in-memory SQLite database for a single business directory containing:
1. Rulebook-compliant sales views (`v_valid_orders`, `v_valid_lines`, `v_orders`, `v_lines`, `v_items`)
   for businesses that have a sales ledger.
2. Cleaned tables (`<safe_table_name>`) with `snake_case` columns, parsed numbers, and ISO dates
   (`YYYY-MM-DD`) / datetimes (`YYYY-MM-DD HH:MM:SS`), with hand-written summary rows removed.
3. Uncleaned fallback tables (`raw_<safe_table_name>`) preserving original column names and cell values.
4. `calendar` table loaded from `calendar.csv` (solar/lunar dates, day of week, holidays).
5. `schema_text(conn)` producing a compact, LLM-ready description of views and tables.

Rulebook guarantees baked into views:
- §1 Orders & revenue: `v_valid_orders` and `v_valid_lines` exclude `huy` and `tra_hang` orders
  (and include `dang_giao` shipping orders). An order with ANY returned line is `tra_hang` as a whole.
  `v_orders.revenue` is the sum of `line_amount` of the order (excluding invoice-level voucher/ship rows).
  Order date is the placement date (`order_date`, `YYYY-MM-DD`).
- §3 Ranking & customers:
  - Service fee rows (`Phí phục vụ`) have `is_service_fee = 1` in `v_lines`/`v_valid_lines` (counted in
    order `revenue`, excluded from `v_items` and item rankings when filtering `is_service_fee = 0`).
  - Walk-in labels (`Khách lẻ`, `Lẻ`, `KL`, `Khách vãng lai`, `Vãng lai`, blank) have `customer_key = NULL`
    and `customer_name = NULL`. When a shop uses `customer_code`, orders without `customer_code` are walk-in
    (`customer_key = NULL`).
- §5 Price on day D: `v_lines` keeps all orders (including `huy` and `tra_hang`) and provides both
  `unit_price` (per sold unit) and `unit_price_base` (per converted base unit).
- §8 Messy files: blank continuation cells filled down within order, export duplicates dropped,
  summary rows removed, yearless dates resolved from sheet/file period hint, line-only ledgers without
  `order_id` given one synthetic order ID per row (`ROW_<line_id>`).
- §9 String matching: `v_items` collects all item spellings and abbreviations (`Ghi tắt`, `Tên gọi khác`,
  variant spacing/accents) into `name_aliases`, and `lines` uses canonical `item_name` and `item_code`.
- §10 Units: `qty_base` is pre-converted to the smallest base unit (`base_unit`).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.cleaning import (
    META_COLS,
    RawTable,
    drop_export_duplicates,
    infer_kinds,
    is_blank,
    load_business,
    name_has,
    nfc,
    norm_key,
    parse_date,
    parse_datetime,
    parse_number,
    parse_qty,
    split_summary_rows,
    strip_accents,
)
from src.ledger import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_RETURNED,
    STATUS_SHIPPING,
    build_ledger,
    load_unit_conversions,
    pick_catalog_columns,
)
from src.mapping import Mapping, propose_mapping

# Walk-in customer labels per Rulebook §3 ("Khách lẻ / Lẻ / KL / Khách vãng lai / Vãng lai / để trống")
_WALKIN_KEYS = {
    "",
    "khach le",
    "le",
    "kl",
    "khach vang lai",
    "vang lai",
    "khach",
    "khach mua le",
    "khach hang le",
    "none",
    "null",
    "nan",
}

_SQLITE_RESERVED = {
    "abort", "action", "add", "after", "all", "alter", "always", "analyze", "and", "as", "asc",
    "attach", "autoincrement", "before", "begin", "between", "by", "cascade", "case", "cast",
    "check", "collate", "column", "commit", "conflict", "constraint", "create", "cross", "current",
    "current_date", "current_time", "current_timestamp", "database", "default", "deferrable",
    "deferred", "delete", "desc", "detach", "distinct", "do", "drop", "each", "else", "end",
    "escape", "except", "exclude", "exclusive", "exists", "explain", "fail", "filter", "first",
    "following", "for", "foreign", "from", "full", "generated", "glob", "group", "groups",
    "having", "if", "ignore", "immediate", "in", "index", "indexed", "initially", "inner",
    "insert", "instead", "intersect", "into", "is", "isnull", "join", "key", "last", "left",
    "like", "limit", "match", "materialized", "natural", "no", "not", "nothing", "notnull",
    "null", "nulls", "of", "offset", "on", "or", "order", "others", "outer", "over", "partition",
    "plan", "pragma", "preceding", "primary", "query", "raise", "range", "recursive", "references",
    "regexp", "reindex", "release", "rename", "replace", "restrict", "returning", "right",
    "rollback", "row", "rows", "savepoint", "select", "set", "table", "temp", "temporary",
    "then", "ties", "to", "transaction", "trigger", "unbounded", "union", "unique", "update",
    "using", "vacuum", "values", "view", "virtual", "when", "where", "window", "with", "without",
}


def safe_identifier(name: Any, fallback: str = "col") -> str:
    """Convert an arbitrary table or column name into a safe lowercase ASCII snake_case SQLite identifier."""
    if name is None:
        return fallback
    s = strip_accents(nfc(str(name)))
    # Split CamelCase (e.g. SoSuaXe -> So_Sua_Xe, DanhSachTho -> Danh_Sach_Tho)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = s.lower()
    # Replace common symbols with meaningful tokens before stripping punctuation
    s = s.replace("%", " pct ").replace("#", " num ")
    s = re.sub(r"[^0-9a-z]+", "_", s).strip("_")
    s = re.sub(r"_+", "_", s)
    if not s:
        s = fallback
    if s[0].isdigit():
        s = f"{fallback}_{s}"
    if s in _SQLITE_RESERVED:
        s = f"{s}_col"
    return s


def _unique_identifiers(names: list[str], fallback: str = "col") -> dict[str, str]:
    """Map original column names to unique snake_case identifiers."""
    out: dict[str, str] = {}
    used: set[str] = set()
    for orig in names:
        base = safe_identifier(orig, fallback=fallback)
        cand = base
        k = 2
        while cand in used:
            cand = f"{base}_{k}"
            k += 1
        used.add(cand)
        out[orig] = cand
    return out


def item_match_key(s: Any) -> str:
    """Normalized key for matching item names across minor spacing/accent variations (e.g. '1000 mg' vs '1000mg')."""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return ""
    k = norm_key(s)
    # Normalize spaces between digits and letters: "1000 mg" -> "1000mg", "d 32" -> "d32"
    k = re.sub(r"(\d)\s+([a-z])", r"\1\2", k)
    return k


def customer_match_key(s: Any) -> str:
    """Key for customers identified by the name written on the order (rulebook §3: names that
    differ only in how they are written are one customer; different letters or digits are two).
    Digit groups are joined so a phone number copied as "0327 988 481" or "0327988481" matches."""
    k = norm_key(s) if s is not None else ""
    return re.sub(r"(?<=\d)\s+(?=\d)", "", k)


def _has_vietnamese_diacritics(s: str) -> bool:
    s_nfc = nfc(s)
    return any(ord(c) > 127 for c in s_nfc)


def _pick_best_display_name(candidates: list[str]) -> str:
    """Choose the best canonical display name among spelling variants (prefers clean spacing + Vietnamese diacritics)."""
    cleaned = []
    for c in candidates:
        if not c or not isinstance(c, str):
            continue
        # Collapse multiple internal spaces
        c_norm = re.sub(r"\s+", " ", nfc(c).strip())
        if c_norm:
            cleaned.append(c_norm)
    if not cleaned:
        return ""
    # Count frequencies of each cleaned spelling
    counts: dict[str, int] = {}
    for c in cleaned:
        counts[c] = counts.get(c, 0) + 1
    # Sort by: (has_diacritics, frequency, -length_diff_from_median, lexicographical)
    return sorted(
        counts.keys(),
        key=lambda x: (_has_vietnamese_diacritics(x), counts[x], len(x), x),
        reverse=True,
    )[0]


def can_build_ledger(
    tables: list[RawTable],
    mapping: Mapping | None = None,
    readme: str = "",
) -> bool:
    """Return True if the business has a valid sales/invoice table suitable for building SalesLedger & sales views.

    Shops like `dev_012` (motorbike repair log `SoSuaXe` + `DanhSachTho` with no product/item columns,
    no quantities, no unit prices, and no order IDs) return False so `build_database` only creates
    cleaned tables and `raw_*` tables without misleading sales views.
    """
    if not tables:
        return False
    if mapping is None:
        mapping = propose_mapping(tables, readme)
    if not mapping.sales_table:
        return False
    sales_t = next((t for t in tables if t.name == mapping.sales_table), None)
    if sales_t is None or sales_t.df.empty:
        return False

    has_date = mapping.get_column("order_date") is not None
    has_amount = (
        mapping.get_column("line_amount") is not None
        or (mapping.get_column("qty") is not None and mapping.get_column("unit_price") is not None)
    )
    has_item_or_order = any(
        mapping.get_column(r) is not None for r in ("item_name", "item_code", "order_id")
    )
    if not (has_date and has_amount and has_item_or_order):
        return False

    # Guard against service/repair logs that have neither item_name nor item_code nor qty/unit_price
    st_key = norm_key(mapping.sales_table)
    if ("sua xe" in st_key or "bao hanh" in st_key) and not (
        mapping.get_column("item_name") or mapping.get_column("item_code")
    ):
        return False

    return True


def _parse_readme_column_descriptions(readme: str) -> dict[str, str]:
    r"""Extract `- \`ColName\`: description` bullets from a shop's README.md."""
    out: dict[str, str] = {}
    if not readme:
        return out
    for m in re.finditer(r"^\s*[-*]\s*`([^`]+)`\s*:\s*(.+)$", readme, flags=re.M):
        col_name = nfc(m.group(1)).strip()
        desc = nfc(m.group(2)).strip()
        out[col_name] = desc
        out[norm_key(col_name)] = desc
    return out


def _clean_dataframe_for_sql(
    raw_table: RawTable,
) -> tuple[pd.DataFrame, dict[str, str], dict[str, str]]:
    """Clean a RawTable for SQLite storage.

    - Removes hand-written summary/subtotal rows via `split_summary_rows`.
    - Casts `number` columns to float, `date` columns to ISO `YYYY-MM-DD`, `datetime` columns to
      `YYYY-MM-DD HH:MM:SS` (using row's `__year` hint for yearless dates).
    - Converts column names to unique ASCII `snake_case`.

    Returns:
        (cleaned_df, orig_to_safe_col_map, safe_col_to_kind_map)
    """
    df, _ = split_summary_rows(raw_table.df)
    orig_cols = [c for c in df.columns if c not in META_COLS]
    col_map = _unique_identifiers(orig_cols, fallback="col")
    kinds = infer_kinds(df)

    years = df["__year"] if "__year" in df.columns else [None] * len(df)
    cleaned_cols: dict[str, list[Any]] = {}
    kind_map: dict[str, str] = {}

    for orig_c in orig_cols:
        safe_c = col_map[orig_c]
        ck = kinds.get(orig_c)
        k_str = ck.kind if ck else "text"
        kind_map[safe_c] = k_str
        series = df[orig_c]

        if k_str == "number":
            cleaned_cols[safe_c] = [parse_number(v) for v in series]
        elif k_str == "date":
            out_dates: list[str | None] = []
            for v, y in zip(series, years):
                y_int = int(y) if y is not None and not (isinstance(y, float) and np.isnan(y)) else None
                d = parse_date(v, year=y_int)
                out_dates.append(d.isoformat() if d is not None else (str(v).strip() if v is not None and not is_blank(v) else None))
            cleaned_cols[safe_c] = out_dates
        elif k_str == "datetime":
            out_dts: list[str | None] = []
            for v, y in zip(series, years):
                y_int = int(y) if y is not None and not (isinstance(y, float) and np.isnan(y)) else None
                dt_obj = parse_datetime(v, year=y_int)
                out_dts.append(
                    dt_obj.isoformat(sep=" ") if dt_obj is not None else (str(v).strip() if v is not None and not is_blank(v) else None)
                )
            cleaned_cols[safe_c] = out_dts
        else:
            cleaned_cols[safe_c] = [
                nfc(v).strip() if v is not None and not is_blank(v) else None for v in series
            ]

    return pd.DataFrame(cleaned_cols), col_map, kind_map


def _build_item_catalog_and_canonicalize_lines(
    tables: list[RawTable],
    ledger_df: pd.DataFrame,
    readme: str = "",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the canonical `items` catalog DataFrame (for `v_items`) and canonicalize item/customer fields on `ledger_df`.

    Handles:
    - Abbreviation tables (`Ghi tắt`, `Tên gọi tắt`, `Tên gọi khác` columns).
    - Catalog tables (`SanPham`, `HangHoa`, `DanhMuc`, `Menu`, `BangGia`).
    - Minor spelling/spacing/accent differences across sales lines (`item_match_key`).
    - Service fee lines (`Phí phục vụ` -> `is_service_fee = 1`, excluded from `v_items`).
    - Customer canonicalization (`customer_key`, `customer_group`, walk-in -> `NULL`).
    """
    df = ledger_df.copy()
    conversions = load_unit_conversions(tables, readme)

    # 1. Discover abbreviation mappings from `Ghi tắt` sheet or `Tên gọi khác` column
    alias_to_canonical_name: dict[str, str] = {}
    extra_aliases_by_mkey: dict[str, set[str]] = {}

    for t in tables:
        tk = norm_key(t.name)
        t_df, _ = split_summary_rows(t.df)
        cols = [c for c in t_df.columns if c not in META_COLS]
        if "ghi tat" in tk or "viet tat" in tk or "ten tat" in tk:
            short_col = next((c for c in cols if any(w in norm_key(c) for w in ["tat", "ngan", "short", "alias"])), None)
            full_col = next((c for c in cols if c != short_col and any(w in norm_key(c) for w in ["day du", "chuan", "ten hang", "ten sp", "ten"])), None)
            if short_col and full_col:
                for _, r in t_df.iterrows():
                    s_val, f_val = r[short_col], r[full_col]
                    if not is_blank(s_val) and not is_blank(f_val):
                        s_str = re.sub(r"\s+", " ", nfc(s_val).strip())
                        f_str = re.sub(r"\s+", " ", nfc(f_val).strip())
                        alias_to_canonical_name[item_match_key(s_str)] = f_str
                        mk_f = item_match_key(f_str)
                        extra_aliases_by_mkey.setdefault(mk_f, set()).update([s_str, f_str])

    # 2. Discover catalog table (if any) and extract item metadata
    catalog_records: list[dict[str, Any]] = []
    sales_item_codes = [x for x in df["item_code"].dropna().unique()] if "item_code" in df.columns else []
    for t in tables:
        tk = norm_key(t.name)
        if name_has(tk, ["quy doi", "don vi", "khach hang", "nha cung cap", "nhan vien", "chi phi", "thu chi", "ghi tat", "tra hang", "phieu nhap", "nhap kho", "ton kho", "kiem ke"]):
            continue
        if not name_has(tk, ["san pham", "hang hoa", "danh muc", "thuc don", "menu", "bang gia", " thuoc", "vat tu", "linh kien", "phu tung", "cay", "mon"]):
            continue
        t_df, _ = split_summary_rows(t.df)
        cols = [c for c in t_df.columns if c not in META_COLS]
        # Pick code / name columns from the contents (shuffled exports carry look-alikes such as
        # "Mã barcode", "Mã HH liên quan", "Mô tả sản phẩm"); fall back to header keywords.
        code_c, name_c = pick_catalog_columns(t_df, sales_item_codes)
        if not name_c:
            name_c = next((c for c in cols if any(w in norm_key(c) for w in ["ten hang", "ten sp", "ten san pham", "ten thuoc", "ten mon", "ten vat tu", "ten cay", "ten dịch vu", "ten"])), None)
        if not name_c:
            continue
        if not code_c:
            code_c = next((c for c in cols if c != name_c and not any(w in norm_key(c) for w in ["barcode", "ma vach", "ean", "lien quan"]) and any(w in norm_key(c) for w in ["ma hang", "ma sp", "ma san pham", "ma thuoc", "ma mon", "ma vat tu", "ma cay", "sku", "code", "ma"])), None)
        cat_c = next((c for c in cols if c not in (name_c, code_c) and not re.search(r"(^|\s)(dv|dvt|don vi)(\s|$)", norm_key(c)) and any(w in norm_key(c) for w in ["nhom", "loai", "danh muc", "nganh", "phan loai", "category"])), None)
        unit_c = next((c for c in cols if c not in (name_c, code_c, cat_c) and any(w in norm_key(c) for w in ["dvt co ban", "don vi co ban", "dvt", "don vi", "unit"])), None)
        alias_c = next((c for c in cols if c not in (name_c, code_c, cat_c, unit_c) and any(w in norm_key(c) for w in ["goi khac", "ten tat", "ghi tat", "biet duoc", "alias"])), None)
        sell_c = next((c for c in cols if any(w in norm_key(c) for w in ["gia ban", "don gia ban", "gia niem yet", "gia le", "don gia"])), None)
        cost_c = next((c for c in cols if any(w in norm_key(c) for w in ["gia von", "gia nhap", "gia goc"])), None)
        ing_c = next((c for c in cols if any(w in norm_key(c) for w in ["hoat chat", "thanh phan"])), None)
        rx_c = next((c for c in cols if any(w in norm_key(c) for w in ["ke don", "thuoc ke don", "rx"])), None)

        for _, r in t_df.iterrows():
            raw_nm = r[name_c]
            if is_blank(raw_nm):
                continue
            nm_str = re.sub(r"\s+", " ", nfc(raw_nm).strip())
            if norm_key(nm_str) == "phi phuc vu":
                continue
            code_str = re.sub(r"\s+", " ", nfc(r[code_c]).strip()) if (code_c and not is_blank(r[code_c])) else None
            cat_str = re.sub(r"\s+", " ", nfc(r[cat_c]).strip()) if (cat_c and not is_blank(r[cat_c])) else None
            unit_str = re.sub(r"\s+", " ", nfc(r[unit_c]).strip()) if (unit_c and not is_blank(r[unit_c])) else None
            sell_val = parse_number(r[sell_c]) if sell_c else None
            cost_val = parse_number(r[cost_c]) if cost_c else None
            ing_str = re.sub(r"\s+", " ", nfc(r[ing_c]).strip()) if (ing_c and not is_blank(r[ing_c])) else None
            rx_str = re.sub(r"\s+", " ", nfc(r[rx_c]).strip()) if (rx_c and not is_blank(r[rx_c])) else None

            mk = item_match_key(nm_str)
            aliases = {nm_str}
            if alias_c and not is_blank(r[alias_c]):
                for part in re.split(r"[,;/|]+", nfc(r[alias_c])):
                    p_clean = re.sub(r"\s+", " ", part.strip())
                    if p_clean:
                        aliases.add(p_clean)
                        alias_to_canonical_name[item_match_key(p_clean)] = nm_str
            extra_aliases_by_mkey.setdefault(mk, set()).update(aliases)

            catalog_records.append({
                "item_code": code_str,
                "item_name": nm_str,
                "mkey": mk,
                "category": cat_str,
                "base_unit": unit_str,
                "sell_price": sell_val,
                "cost_price": cost_val,
                "active_ingredient": ing_str,
                "is_prescription": rx_str,
            })

    # Build lookup maps from catalog
    code_to_cat_rec: dict[str, dict[str, Any]] = {}
    mkey_to_cat_rec: dict[str, dict[str, Any]] = {}
    for rec in catalog_records:
        if rec["item_code"]:
            code_to_cat_rec[rec["item_code"].upper()] = rec
        if rec["mkey"]:
            mkey_to_cat_rec[rec["mkey"]] = rec

    # Also check if sales lines have a category column from raw sales table
    line_cat_col = next(
        (c for c in df.columns if c not in META_COLS and any(w in norm_key(c) for w in ["nhom hang", "loai hang", "danh muc", "nhom sp", "phan loai", "nganh hang", "category"])),
        None,
    )
    raw_line_cats = df[line_cat_col] if line_cat_col else [None] * len(df)

    # 3. Group all sales lines by canonical item identity to unify spelling variants and missing item_codes
    # First resolve each line's mkey (applying abbreviation map if matched)
    line_raw_names = [nfc(x).strip() if x is not None and not is_blank(x) else "" for x in df["item_name"]]
    line_raw_codes = [nfc(x).strip() if x is not None and not is_blank(x) else None for x in df["item_code"]]
    line_cats = [nfc(x).strip() if x is not None and not is_blank(x) else None for x in raw_line_cats]

    # Link mkey <-> item_code from sales lines as well
    mkey_to_code: dict[str, str] = {mk: rec["item_code"] for mk, rec in mkey_to_cat_rec.items() if rec.get("item_code")}
    code_to_mkey: dict[str, str] = {rec["item_code"].upper(): mk for mk, rec in mkey_to_cat_rec.items() if rec.get("item_code")}

    for nm, cd in zip(line_raw_names, line_raw_codes):
        mk = item_match_key(nm)
        if mk in alias_to_canonical_name:
            mk = item_match_key(alias_to_canonical_name[mk])
        if cd:
            cd_u = cd.upper()
            if mk and mk not in mkey_to_code:
                mkey_to_code[mk] = cd
            if cd_u not in code_to_mkey and mk:
                code_to_mkey[cd_u] = mk

    # Collect all spellings, categories, base_units per canonical item key
    # Canonical item key is `code.upper()` if an item has a code, else `mkey`
    item_spellings: dict[str, set[str]] = {}
    item_raw_name_list: dict[str, list[str]] = {}
    item_code_map: dict[str, str | None] = {}
    item_cat_map: dict[str, str | None] = {}
    item_base_unit_map: dict[str, str | None] = {}
    item_extra_meta: dict[str, dict[str, Any]] = {}

    def _register_item(
        canon_key: str,
        code: str | None,
        name_spelling: str | None,
        cat: str | None,
        b_unit: str | None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        if not canon_key:
            return
        if code and not item_code_map.get(canon_key):
            item_code_map[canon_key] = code
        if name_spelling:
            item_spellings.setdefault(canon_key, set()).add(name_spelling)
            item_raw_name_list.setdefault(canon_key, []).append(name_spelling)
        if cat and not item_cat_map.get(canon_key):
            item_cat_map[canon_key] = cat
        if b_unit and b_unit != "cơ bản" and not item_base_unit_map.get(canon_key):
            item_base_unit_map[canon_key] = b_unit
        if meta:
            cur_m = item_extra_meta.setdefault(canon_key, {})
            for k, v in meta.items():
                if v is not None and cur_m.get(k) is None:
                    cur_m[k] = v

    # Register from catalog first (highest authority for canonical name, code, category, base_unit)
    for rec in catalog_records:
        mk = rec["mkey"]
        cd = rec["item_code"]
        ckey = f"CODE:{cd.upper()}" if cd else f"NAME:{mk}"
        _register_item(
            ckey,
            cd,
            rec["item_name"],
            rec["category"],
            rec["base_unit"],
            {
                "official_name": rec["item_name"],
                "sell_price": rec["sell_price"],
                "cost_price": rec["cost_price"],
                "active_ingredient": rec["active_ingredient"],
                "is_prescription": rec["is_prescription"],
            },
        )
        for al in extra_aliases_by_mkey.get(mk, set()):
            item_spellings.setdefault(ckey, set()).add(al)

    # Now iterate through sales lines to register & canonicalize
    line_canon_keys: list[str] = []
    line_is_service_fee: list[int] = []

    for nm, cd, cat, bu in zip(line_raw_names, line_raw_codes, line_cats, df["base_unit"]):
        if norm_key(nm) == "phi phuc vu":
            line_canon_keys.append("__SERVICE_FEE__")
            line_is_service_fee.append(1)
            continue
        line_is_service_fee.append(0)
        mk = item_match_key(nm)
        if mk in alias_to_canonical_name:
            canon_nm = alias_to_canonical_name[mk]
            mk = item_match_key(canon_nm)
        resolved_cd = cd or mkey_to_code.get(mk)
        if resolved_cd:
            ckey = f"CODE:{resolved_cd.upper()}"
        elif mk:
            ckey = f"NAME:{mk}"
        else:
            ckey = ""
        line_canon_keys.append(ckey)
        if ckey:
            _register_item(ckey, resolved_cd, nm, cat, str(bu) if bu else None)
            for al in extra_aliases_by_mkey.get(mk, set()):
                item_spellings.setdefault(ckey, set()).add(al)

    # Determine canonical display name for each item key
    canon_name_map: dict[str, str] = {}
    for ckey, spellings in item_spellings.items():
        meta = item_extra_meta.get(ckey, {})
        if meta.get("official_name"):
            canon_name_map[ckey] = meta["official_name"]
        else:
            canon_name_map[ckey] = _pick_best_display_name(item_raw_name_list.get(ckey, list(spellings)))

    # Re-check unit conversions on lines whose `item_name` was an abbreviation or variant spelling
    new_factors = list(df["factor"])
    new_qty_bases = list(df["qty_base"])
    new_base_units = list(df["base_unit"])
    qty_base_col_in_raw = any(norm_key(c) in ("sl quy doi", "so luong quy doi", "qty_base") for c in df.columns)

    for i, ckey in enumerate(line_canon_keys):
        if not ckey or ckey == "__SERVICE_FEE__":
            continue
        c_name = canon_name_map.get(ckey, line_raw_names[i])
        c_code = item_code_map.get(ckey, line_raw_codes[i])
        u_str = str(df["unit"].iloc[i] or "")
        k_unit = norm_key(u_str)
        if new_factors[i] == 1.0 and k_unit:
            k_nm = norm_key(c_name)
            k_cd = norm_key(c_code) if c_code else None
            conv = (
                conversions.get((k_nm, k_unit))
                or (conversions.get((k_cd, k_unit)) if k_cd else None)
                or conversions.get((None, k_unit))
            )
            if conv is not None:
                f, bu = conv
                new_factors[i] = f
                new_base_units[i] = bu
                if not qty_base_col_in_raw:
                    new_qty_bases[i] = float(df["qty"].iloc[i]) * f
                if bu and bu != "cơ bản":
                    item_base_unit_map[ckey] = bu

    df["factor"] = new_factors
    df["qty_base"] = new_qty_bases
    df["base_unit"] = [
        item_base_unit_map.get(ckey) or (bu if bu != "cơ bản" else None) or bu
        for ckey, bu in zip(line_canon_keys, new_base_units)
    ]

    # Apply canonical item_name, item_code, category, is_service_fee to lines
    df["item_name"] = [
        "Phí phục vụ" if ckey == "__SERVICE_FEE__" else canon_name_map.get(ckey, nm)
        for ckey, nm in zip(line_canon_keys, line_raw_names)
    ]
    df["item_code"] = [
        None if ckey == "__SERVICE_FEE__" else item_code_map.get(ckey, cd)
        for ckey, cd in zip(line_canon_keys, line_raw_codes)
    ]
    df["category"] = [
        None if ckey == "__SERVICE_FEE__" else (cat or item_cat_map.get(ckey))
        for ckey, cat in zip(line_canon_keys, line_cats)
    ]
    df["is_service_fee"] = line_is_service_fee

    # Compute effective unit_price and unit_price_base (per Rulebook §5: price per sold unit and per base unit)
    eff_unit_prices: list[float] = []
    unit_prices_base: list[float] = []
    for q_v, up_v, amt_v, f_v in zip(df["qty"], df["unit_price"], df["line_amount"], df["factor"]):
        up = float(up_v) if up_v is not None and not pd.isna(up_v) else 0.0
        q = float(q_v) if q_v is not None and not pd.isna(q_v) else 1.0
        amt = float(amt_v) if amt_v is not None and not pd.isna(amt_v) else 0.0
        f = float(f_v) if f_v is not None and not pd.isna(f_v) and f_v > 0 else 1.0
        if up == 0.0 and q > 0 and amt > 0:
            up = amt / q
        eff_unit_prices.append(up)
        unit_prices_base.append(up / f if f > 0 else up)

    df["unit_price"] = eff_unit_prices
    df["unit_price_base"] = unit_prices_base

    # Build `items_df` for `v_items`
    items_rows: list[dict[str, Any]] = []
    for ckey in sorted(item_spellings.keys()):
        if not ckey or ckey == "__SERVICE_FEE__":
            continue
        c_name = canon_name_map.get(ckey, "")
        if not c_name or norm_key(c_name) == "phi phuc vu":
            continue
        c_code = item_code_map.get(ckey)
        all_names = sorted(
            {re.sub(r"\s+", " ", s.strip()) for s in item_spellings[ckey] if s and s.strip()},
            key=lambda x: (0 if x == c_name else 1, x),
        )
        meta = item_extra_meta.get(ckey, {})
        items_rows.append({
            "item_code": c_code,
            "item_name": c_name,
            "name_aliases": " | ".join(all_names),
            "category": item_cat_map.get(ckey),
            "base_unit": item_base_unit_map.get(ckey) or "cơ bản",
            "sell_price": meta.get("sell_price"),
            "cost_price": meta.get("cost_price"),
            "active_ingredient": meta.get("active_ingredient"),
            "is_prescription": meta.get("is_prescription"),
        })

    items_df = pd.DataFrame(
        items_rows,
        columns=[
            "item_code",
            "item_name",
            "name_aliases",
            "category",
            "base_unit",
            "sell_price",
            "cost_price",
            "active_ingredient",
            "is_prescription",
        ],
    )
    if not items_df.empty:
        items_df = items_df.sort_values(
            by=["item_code", "item_name"],
            key=lambda s: s.fillna("~~~~"),
            kind="mergesort",
        ).reset_index(drop=True)

    # 4. Canonicalize customer fields (`customer_code`, `customer_name`, `customer_key`, `customer_group`) per Rulebook §3
    cust_group_map: dict[str, str] = {}
    cust_code_to_official_name: dict[str, str] = {}
    for t in tables:
        tk = norm_key(t.name)
        if name_has(tk, ["khach hang", "doi tac", "customer", "hoi vien"]):
            t_df, _ = split_summary_rows(t.df)
            cols = [c for c in t_df.columns if c not in META_COLS]
            c_code = next((c for c in cols if any(w in norm_key(c) for w in ["ma kh", "ma khach", "so kh", "customer id", "ma doi tac", "ma"])), None)
            c_name = next((c for c in cols if any(w in norm_key(c) for w in ["ten kh", "ho ten", "ten khach", "khach hang", "ten doi tac", "ten"])), None)
            c_grp = next((c for c in cols if any(w in norm_key(c) for w in ["nhom", "hang", "loai", "phan loai", "tier", "group", "vip"])), None)
            for _, r in t_df.iterrows():
                cd_v = nfc(r[c_code]).strip() if (c_code and not is_blank(r[c_code])) else None
                nm_v = re.sub(r"\s+", " ", nfc(r[c_name]).strip()) if (c_name and not is_blank(r[c_name])) else None
                gr_v = re.sub(r"\s+", " ", nfc(r[c_grp]).strip()) if (c_grp and not is_blank(r[c_grp])) else None
                if cd_v and nm_v and norm_key(nm_v) not in _WALKIN_KEYS:
                    cust_code_to_official_name[cd_v.upper()] = nm_v
                if gr_v:
                    if cd_v:
                        cust_group_map[f"CODE:{cd_v.upper()}"] = gr_v
                    if nm_v:
                        cust_group_map[f"NAME:{norm_key(nm_v)}"] = gr_v

    # Check if sales_df also has a customer group column directly
    sales_cgrp_col = next(
        (c for c in df.columns if c not in META_COLS and any(w in norm_key(c) for w in ["nhom kh", "hang kh", "loai kh", "phan loai kh", "hang the"])),
        None,
    )
    raw_cgrps = df[sales_cgrp_col] if sales_cgrp_col else [None] * len(df)

    raw_ccodes = [nfc(x).strip() if x is not None and not is_blank(x) else None for x in df["customer_code"]]
    raw_cnames = [re.sub(r"\s+", " ", nfc(x).strip()) if x is not None and not is_blank(x) else None for x in df["customer_name"]]

    # Clean walk-in codes and names
    clean_ccodes: list[str | None] = []
    clean_cnames: list[str | None] = []
    for cd, nm in zip(raw_ccodes, raw_cnames):
        cd_clean = None if (cd is None or norm_key(cd) in _WALKIN_KEYS) else cd
        nm_clean = None if (nm is None or norm_key(nm) in _WALKIN_KEYS) else nm
        # If customer_code is walk-in or customer_name explicitly says walk-in without a real code
        if nm is not None and norm_key(nm) in _WALKIN_KEYS and cd_clean is None:
            nm_clean = None
        clean_ccodes.append(cd_clean)
        clean_cnames.append(nm_clean)

    shop_uses_customer_code = any(c is not None for c in clean_ccodes) or bool(cust_code_to_official_name)

    # Group customer names by customer_key to pick canonical name (with full diacritics)
    ckey_to_names: dict[str, list[str]] = {}
    for cd, nm in zip(clean_ccodes, clean_cnames):
        if shop_uses_customer_code:
            if not cd:
                continue
            ck = cd.upper()
            if nm:
                ckey_to_names.setdefault(ck, []).append(nm)
        else:
            if not nm:
                continue
            ck = customer_match_key(nm)
            if ck:
                ckey_to_names.setdefault(ck, []).append(nm)

    canon_cust_name_map: dict[str, str] = {}
    for ck, nms in ckey_to_names.items():
        if ck in cust_code_to_official_name:
            canon_cust_name_map[ck] = cust_code_to_official_name[ck]
        else:
            canon_cust_name_map[ck] = _pick_best_display_name(nms)

    final_ccodes: list[str | None] = []
    final_cnames: list[str | None] = []
    final_ckeys: list[str | None] = []
    final_cgroups: list[str | None] = []

    for cd, nm, gr in zip(clean_ccodes, clean_cnames, raw_cgrps):
        gr_str = re.sub(r"\s+", " ", nfc(gr).strip()) if gr is not None and not is_blank(gr) else None
        if shop_uses_customer_code:
            # Rulebook §3: "Nếu tiệm có mã khách thì ghép theo mã (đơn không ghi mã là khách lẻ)"
            if not cd:
                final_ccodes.append(None)
                final_cnames.append(None)
                final_ckeys.append(None)
                final_cgroups.append(None)
            else:
                ck = cd.upper()
                c_nm = canon_cust_name_map.get(ck) or cust_code_to_official_name.get(ck) or nm
                c_gr = gr_str or cust_group_map.get(f"CODE:{ck}") or (cust_group_map.get(f"NAME:{norm_key(c_nm)}") if c_nm else None)
                final_ccodes.append(cd)
                final_cnames.append(c_nm)
                final_ckeys.append(cd)
                final_cgroups.append(c_gr)
        else:
            if not nm:
                final_ccodes.append(None)
                final_cnames.append(None)
                final_ckeys.append(None)
                final_cgroups.append(None)
            else:
                ck = customer_match_key(nm)
                c_nm = canon_cust_name_map.get(ck, nm)
                c_gr = gr_str or cust_group_map.get(f"NAME:{ck}")
                final_ccodes.append(None)
                final_cnames.append(c_nm)
                final_ckeys.append(ck)
                final_cgroups.append(c_gr)

    df["customer_code"] = final_ccodes
    df["customer_name"] = final_cnames
    df["customer_key"] = final_ckeys
    df["customer_group"] = final_cgroups

    return df, items_df


# ------------------------------------------------------------- payments / deliveries / due dates

# Column-name patterns (accent-free, lower case) for dates kept outside the sales ledger.
_DUE_COL = re.compile(r"\b(han thanh toan|han tra|han no|han gop|ngay den han|den han|ngay phai tra|phai tra|han)\b")
_PAY_COL = re.compile(r"\b(thoi gian thu|ngay thu|gio thu|ngay tt|thoi gian tt|ngay thanh toan|thoi gian thanh toan|ngay tra tien|ngay nop)\b")
_DELIV_COL = re.compile(r"\b(ngay giao hang|ngay giao|thoi gian giao|giao luc|ngay cho|ngay van chuyen|ngay ship|ngay xuat kho)\b")
_PAY_TABLE = ("so quy", "phieu thu", "thanh toan", "thu tien")
_DELIV_TABLE = ("giao hang", "so giao", "van chuyen", "cho hang", "phieu giao")
_ROUND_COL = re.compile(r"\b(lan giao|luot giao|dot giao|dot|lan|luot)\b")
_AMOUNT_COL = re.compile(r"\b(so tien|tien thu|so tien thu|gia tri|tien|thanh tien|amount)\b")
_METHOD_COL = re.compile(r"\b(phuong thuc|hinh thuc|pttt|httt)\b")

ORDER_EVENT_COLUMNS = (
    "first_paid_at", "last_paid_at", "paid_amount", "n_payments",
    "first_delivery_date", "last_delivery_date", "n_delivery_rounds", "due_date",
)


def _id_text(v: Any) -> str | None:
    if v is None or is_blank(v):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return s or None


def _find_order_link(df: pd.DataFrame, order_ids: set[str], skip: set[str]) -> str | None:
    """Column of `df` whose values are order IDs of the sales ledger (by content, not by name)."""
    best: tuple[float, str] | None = None
    for c in df.columns:
        if c in skip:
            continue
        vals = {x for x in (_id_text(v) for v in df[c].head(5000)) if x is not None}
        if len(vals) < 5:
            continue
        # Small integers (row numbers, rounds, quantities) overlap any numeric ID space by chance
        if all(x.isdigit() and len(x) <= 4 for x in vals):
            continue
        hit = len(vals & order_ids) / len(vals)
        if hit >= 0.8 and (best is None or hit > best[0]):
            best = (hit, c)
    return best[1] if best else None


def _build_order_events(
    conn: sqlite3.Connection,
    cleaned: list[tuple[str, str, pd.DataFrame, dict[str, str], dict[str, str]]],
    order_ids: set[str],
    skip_tables: set[str],
) -> dict[str, Any]:
    """Create `payments`, `deliveries`, `order_due` and the per-order `order_events` summary.

    Source tables are found by content: a column whose values are sales order IDs, plus a date column
    whose header names a payment, delivery or due date (or the only date column of a table named
    like a cash book / receipts / delivery book). Every source row is kept; no rulebook filter applied.
    """
    pay_rows: list[dict[str, Any]] = []
    deliv_rows: list[dict[str, Any]] = []
    due_rows: list[dict[str, Any]] = []
    sources: dict[str, list[str]] = {"payments": [], "deliveries": [], "order_due": []}

    for orig_name, clean_name, df, col_map, kind_map in cleaned:
        if orig_name in skip_tables or df.empty:
            continue
        t_key = norm_key(orig_name)
        safe_to_orig = {v: k for k, v in col_map.items()}
        date_cols = [c for c in df.columns if kind_map.get(c) in ("date", "datetime")]
        if not date_cols:
            continue
        link = _find_order_link(df, order_ids, skip=set(date_cols))
        if link is None:
            continue
        keys = {c: norm_key(safe_to_orig.get(c, c)) for c in df.columns}

        due_c = [c for c in date_cols if _DUE_COL.search(keys[c])]
        rest = [c for c in date_cols if c not in due_c]
        pay_c = [c for c in rest if _PAY_COL.search(keys[c])]
        deliv_c = [c for c in rest if _DELIV_COL.search(keys[c]) and "giao dich" not in keys[c]]
        if not pay_c and not deliv_c and len(rest) == 1:
            t_compact = re.sub(r"[\s_/]+", "", t_key)
            if any(w.replace(" ", "") in t_compact for w in _PAY_TABLE):
                pay_c = rest
            elif any(w.replace(" ", "") in t_compact for w in _DELIV_TABLE):
                deliv_c = rest

        oids = [_id_text(v) for v in df[link]]
        if due_c:
            for oid, d in zip(oids, df[due_c[0]]):
                if oid and d:
                    due_rows.append({"order_id": oid, "due_date": str(d)[:10], "src_table": clean_name})
            sources["order_due"].append(clean_name)
        if pay_c:
            pc = pay_c[0]
            amt_c = next((c for c in df.columns if kind_map.get(c) == "number" and _AMOUNT_COL.search(keys[c])), None)
            meth_c = next((c for c in df.columns if c != link and _METHOD_COL.search(keys[c])), None)
            amts = df[amt_c] if amt_c else [None] * len(df)
            meths = df[meth_c] if meth_c else [None] * len(df)
            for oid, d, a, m in zip(oids, df[pc], amts, meths):
                if oid and d:
                    s = str(d)
                    pay_rows.append({
                        "order_id": oid,
                        "paid_at": s if len(s) > 10 else s[:10],
                        "paid_date": s[:10],
                        "paid_time": s[11:19] if len(s) > 10 else None,
                        "amount": a if a is not None and not pd.isna(a) else None,
                        "method": m,
                        "src_table": clean_name,
                    })
            sources["payments"].append(clean_name)
        if deliv_c:
            dc = deliv_c[0]
            round_c = next((c for c in df.columns if c not in (link, dc) and _ROUND_COL.search(keys[c])), None)
            rounds = df[round_c] if round_c else [None] * len(df)
            for oid, d, r in zip(oids, df[dc], rounds):
                if oid and d:
                    deliv_rows.append({
                        "order_id": oid,
                        "delivery_date": str(d)[:10],
                        "delivery_round": _id_text(r),
                        "src_table": clean_name,
                    })
            sources["deliveries"].append(clean_name)

    conn.executescript(
        """
        DROP TABLE IF EXISTS payments;
        DROP TABLE IF EXISTS deliveries;
        DROP TABLE IF EXISTS order_due;
        DROP TABLE IF EXISTS order_events;
        CREATE TABLE payments (order_id TEXT, paid_at TEXT, paid_date TEXT, paid_time TEXT,
                               amount REAL, method TEXT, src_table TEXT);
        CREATE TABLE deliveries (order_id TEXT, delivery_date TEXT, delivery_round TEXT, src_table TEXT);
        CREATE TABLE order_due (order_id TEXT, due_date TEXT, src_table TEXT);
        """
    )
    if pay_rows:
        pd.DataFrame(pay_rows).to_sql("payments", conn, index=False, if_exists="append")
    if deliv_rows:
        pd.DataFrame(deliv_rows).to_sql("deliveries", conn, index=False, if_exists="append")
    if due_rows:
        pd.DataFrame(due_rows).to_sql("order_due", conn, index=False, if_exists="append")
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(order_id);
        CREATE INDEX IF NOT EXISTS idx_deliveries_order ON deliveries(order_id);
        CREATE INDEX IF NOT EXISTS idx_order_due_order ON order_due(order_id);
        CREATE TABLE order_events AS
        WITH ids AS (
            SELECT order_id FROM payments UNION SELECT order_id FROM deliveries UNION SELECT order_id FROM order_due
        ),
        p AS (
            SELECT order_id, MIN(paid_at) AS first_paid_at, MAX(paid_at) AS last_paid_at,
                   SUM(amount) AS paid_amount, COUNT(*) AS n_payments
            FROM payments GROUP BY order_id
        ),
        d AS (
            SELECT order_id, MIN(delivery_date) AS first_delivery_date, MAX(delivery_date) AS last_delivery_date,
                   COUNT(DISTINCT COALESCE(delivery_round, delivery_date)) AS n_delivery_rounds
            FROM deliveries GROUP BY order_id
        ),
        u AS (SELECT order_id, MAX(due_date) AS due_date FROM order_due GROUP BY order_id)
        SELECT ids.order_id, p.first_paid_at, p.last_paid_at, p.paid_amount, p.n_payments,
               d.first_delivery_date, d.last_delivery_date, d.n_delivery_rounds, u.due_date
        FROM ids
        LEFT JOIN p ON p.order_id = ids.order_id
        LEFT JOIN d ON d.order_id = ids.order_id
        LEFT JOIN u ON u.order_id = ids.order_id;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_order_events_order ON order_events(order_id);

        DROP VIEW IF EXISTS v_payments;
        DROP VIEW IF EXISTS v_deliveries;
        CREATE VIEW v_payments AS
        SELECT order_id, paid_at, paid_date, paid_time, SUBSTR(paid_date, 1, 7) AS paid_month,
               amount, method, src_table
        FROM payments;
        CREATE VIEW v_deliveries AS
        SELECT order_id, COALESCE(delivery_round, delivery_date) AS delivery_round, delivery_date,
               SUBSTR(delivery_date, 1, 7) AS delivery_month, COUNT(*) AS n_rows, MIN(src_table) AS src_table
        FROM deliveries
        GROUP BY order_id, COALESCE(delivery_round, delivery_date), delivery_date;
        """
    )
    return {
        "n_payments": len(pay_rows),
        "n_deliveries": len(deliv_rows),
        "n_due": len(due_rows),
        "sources": sources,
    }


def _count_rows(conn: sqlite3.Connection, name: str) -> int:
    try:
        return int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
    except sqlite3.Error:
        return 0


def _order_event_columns_text(n_pay: int, n_deliv: int, n_due: int) -> str:
    """Describe only the order-event columns of `v_orders` that hold data for this shop."""
    parts = []
    if n_pay:
        parts.append(
            "first_paid_at / last_paid_at (TEXT first/last receipt time of the order, see `v_payments`), "
            "paid_amount (REAL sum of receipts), n_payments (INT)"
        )
    if n_deliv:
        parts.append(
            "first_delivery_date / last_delivery_date (TEXT 'YYYY-MM-DD', see `v_deliveries`), n_delivery_rounds (INT)"
        )
    if n_due:
        parts.append("due_date (TEXT 'YYYY-MM-DD' payment due date of a credit order)")
    if not parts:
        return ""
    return ", " + ", ".join(parts) + " — NULL when the order has no such record"


def _create_sales_views(conn: sqlite3.Connection) -> None:
    """Create the 5 standard rulebook views (`v_lines`, `v_valid_lines`, `v_orders`, `v_valid_orders`, `v_items`)."""
    conn.executescript(
        """
        DROP VIEW IF EXISTS v_valid_orders;
        DROP VIEW IF EXISTS v_orders;
        DROP VIEW IF EXISTS v_valid_lines;
        DROP VIEW IF EXISTS v_lines;
        DROP VIEW IF EXISTS v_items;

        CREATE VIEW v_lines AS
        SELECT
            line_id,
            order_id,
            order_date,
            order_time,
            SUBSTR(order_date, 1, 7) AS order_month,
            status,
            item_code,
            item_name,
            category,
            is_service_fee,
            unit,
            qty,
            factor,
            qty_base,
            base_unit,
            unit_price,
            unit_price_base,
            line_amount,
            customer_code,
            customer_name,
            customer_key,
            customer_group,
            staff,
            channel,
            payment_method,
            src_file,
            src_sheet,
            src_row
        FROM lines;

        CREATE VIEW v_valid_lines AS
        SELECT *
        FROM v_lines
        WHERE status NOT IN ('huy', 'tra_hang');

        CREATE VIEW v_orders AS
        SELECT
            o.*,
            e.first_paid_at,
            e.last_paid_at,
            e.paid_amount,
            e.n_payments,
            e.first_delivery_date,
            e.last_delivery_date,
            e.n_delivery_rounds,
            e.due_date
        FROM (
        SELECT
            order_id,
            MIN(order_date) AS order_date,
            MIN(order_time) AS order_time,
            SUBSTR(MIN(order_date), 1, 7) AS order_month,
            MAX(status) AS status,
            SUM(line_amount) AS revenue,
            COUNT(*) AS n_lines,
            SUM(CASE WHEN is_service_fee = 0 THEN qty_base ELSE 0 END) AS total_qty_base,
            MAX(customer_code) AS customer_code,
            MAX(customer_name) AS customer_name,
            MAX(customer_key) AS customer_key,
            MAX(customer_group) AS customer_group,
            MAX(staff) AS staff,
            MAX(channel) AS channel,
            MAX(payment_method) AS payment_method
        FROM v_lines
        GROUP BY order_id
        ) AS o
        LEFT JOIN order_events AS e ON e.order_id = o.order_id;

        CREATE VIEW v_valid_orders AS
        SELECT *
        FROM v_orders
        WHERE status NOT IN ('huy', 'tra_hang');

        CREATE VIEW v_items AS
        SELECT
            item_code,
            item_name,
            name_aliases,
            category,
            base_unit,
            sell_price,
            cost_price,
            active_ingredient,
            is_prescription
        FROM items;
        """
    )


def enable_readonly(conn: sqlite3.Connection) -> None:
    """Switch an existing SQLite connection to read-only mode (`PRAGMA query_only = ON`) after views are created."""
    conn.execute("PRAGMA query_only = ON;")


def _find_calendar_path(business_dir: Path, calendar_path: str | Path | None = None) -> Path | None:
    if calendar_path is not None:
        p = Path(calendar_path)
        return p if p.is_file() else None
    for cand in (
        business_dir / "calendar.csv",
        business_dir.parent / "calendar.csv",
        business_dir.parent.parent / "calendar.csv",
    ):
        if cand.is_file():
            return cand
    return None


_DAY_NAME_VI = {1: "Thứ Hai", 2: "Thứ Ba", 3: "Thứ Tư", 4: "Thứ Năm", 5: "Thứ Sáu", 6: "Thứ Bảy", 7: "Chủ nhật"}
_TRUE_TEXT = {"1", "true", "t", "yes", "y", "co", "có", "x"}


def calendar_frame(cal_file: Path) -> pd.DataFrame:
    """Read `calendar.csv` and add derived solar columns for SQL JOINs.

    Source columns are kept as given (`date`, `weekday`, `lunar_*`, `holiday`); missing ones become NULL.
    Derived columns are computed from `date` only, so they hold whatever calendar file the run receives:
    `year`, `month`, `day`, `quarter`, `iso_year`, `iso_week`, `day_of_week` (1=Mon..7=Sun),
    `day_name_vi`, `is_weekend`, `holiday_vi` (alias of `holiday`).
    No rulebook period (Tết window, season…) is baked in: those are filtered in SQL on the lunar columns.
    """
    raw = pd.read_csv(cal_file, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    raw.columns = [str(c).strip() for c in raw.columns]
    dates = pd.to_datetime(raw.get("date", pd.Series([], dtype=str)).str.strip(), errors="coerce", format="mixed")
    df = pd.DataFrame({"date": dates.dt.strftime("%Y-%m-%d")})
    df["year"] = dates.dt.year
    df["month"] = dates.dt.month
    df["day"] = dates.dt.day
    df["quarter"] = dates.dt.quarter
    iso = dates.dt.isocalendar()
    df["iso_year"] = iso["year"]
    df["iso_week"] = iso["week"]
    df["day_of_week"] = dates.dt.dayofweek + 1
    df["day_name_vi"] = df["day_of_week"].map(_DAY_NAME_VI)
    df["is_weekend"] = (df["day_of_week"] >= 6).astype("Int64")

    def _int_col(name: str) -> pd.Series:
        if name not in raw.columns:
            return pd.Series([None] * len(raw), dtype="Int64")
        return pd.to_numeric(raw[name].str.strip(), errors="coerce").astype("Int64")

    df["weekday"] = _int_col("weekday") if "weekday" in raw.columns else df["day_of_week"]
    for c in ("lunar_year", "lunar_month", "lunar_day"):
        df[c] = _int_col(c)
    if "lunar_leap" in raw.columns:
        df["lunar_leap"] = raw["lunar_leap"].str.strip().str.lower().map(lambda v: 1 if v in _TRUE_TEXT else 0).astype("Int64")
    else:
        df["lunar_leap"] = pd.Series([None] * len(raw), dtype="Int64")
    hol_src = next((c for c in ("holiday", "holiday_vi") if c in raw.columns), None)
    hol = raw[hol_src].str.strip() if hol_src else pd.Series([""] * len(raw))
    df["holiday"] = hol.map(lambda v: nfc(v) if v else None)
    df["holiday_vi"] = df["holiday"]
    # Keep any extra columns a future calendar.csv might carry, without overwriting derived ones
    for c in raw.columns:
        if c not in df.columns:
            df[c] = raw[c].map(lambda v: v if v != "" else None)
    df = df[df["date"].notna()].reset_index(drop=True)
    return df


def build_database(
    business_dir: str | Path,
    calendar_path: str | Path | None = None,
    readonly: bool = False,
    db_path: str | Path = ":memory:",
) -> sqlite3.Connection:
    """Build a SQLite database with cleaned tables, `raw_*` tables, `calendar`, and rulebook views for one shop.

    Args:
        business_dir: Path to the shop folder (e.g. `data/train/biz_101`).
        calendar_path: Optional explicit path to `calendar.csv`. Auto-detected from parent directories if None.
        readonly: If True, enables `PRAGMA query_only = ON` after creating all tables and views.
        db_path: SQLite target (`":memory:"` by default, or path to a temporary `.sqlite` file).

    Returns:
        An open `sqlite3.Connection`.
    """
    business_dir = Path(business_dir)
    readme_path = business_dir / "README.md"
    readme = readme_path.read_text(encoding="utf-8") if readme_path.is_file() else ""
    readme_col_descs = _parse_readme_column_descriptions(readme)

    tables = load_business(business_dir)
    mapping = propose_mapping(tables, readme)
    has_ledger = can_build_ledger(tables, mapping, readme)

    conn = sqlite3.connect(str(db_path))

    # Track table metadata for `schema_text(conn)`
    meta_tables: list[dict[str, Any]] = []
    used_table_names: set[str] = {
        "lines",
        "items",
        "calendar",
        "_schema_meta",
        "v_lines",
        "v_valid_lines",
        "v_orders",
        "v_valid_orders",
        "v_items",
        "payments",
        "deliveries",
        "order_due",
        "order_events",
        "v_payments",
        "v_deliveries",
    }
    cleaned_frames: list[tuple[str, str, pd.DataFrame, dict[str, str], dict[str, str]]] = []

    # 1. Write `raw_<name>` and cleaned `<name>` for every table in the business
    for t in tables:
        base_tname = safe_identifier(t.name, fallback="table")
        clean_tname = base_tname
        k = 2
        while clean_tname in used_table_names:
            clean_tname = f"{base_tname}_{k}"
            k += 1
        used_table_names.add(clean_tname)
        raw_tname = f"raw_{clean_tname}"
        used_table_names.add(raw_tname)

        # Write raw table (all original columns except META_COLS, values as strings/numbers)
        orig_cols = [c for c in t.df.columns if c not in META_COLS]
        raw_df = t.df[orig_cols].copy()
        for c in orig_cols:
            raw_df[c] = [
                v.isoformat(sep=" ") if isinstance(v, dt.datetime)
                else (v.isoformat() if isinstance(v, dt.date) else (None if is_blank(v) else v))
                for v in raw_df[c]
            ]
        raw_df.to_sql(raw_tname, conn, index=False, if_exists="replace")

        # Write cleaned table with snake_case columns and parsed types
        cleaned_df, col_map, kind_map = _clean_dataframe_for_sql(t)
        cleaned_df.to_sql(clean_tname, conn, index=False, if_exists="replace")
        cleaned_frames.append((t.name, clean_tname, cleaned_df, col_map, kind_map))

        col_meta = []
        for orig_c in orig_cols:
            safe_c = col_map[orig_c]
            desc = readme_col_descs.get(orig_c) or readme_col_descs.get(norm_key(orig_c)) or ""
            col_meta.append({
                "safe_name": safe_c,
                "orig_name": orig_c,
                "kind": kind_map.get(safe_c, "text"),
                "description": desc,
            })

        is_primary_sales = has_ledger and (t.name == mapping.sales_table or t.name == mapping.orders_table)
        meta_tables.append({
            "clean_name": clean_tname,
            "raw_name": raw_tname,
            "orig_name": t.name,
            "sources": t.sources,
            "preamble": t.preamble[:2],
            "n_rows": len(cleaned_df),
            "n_raw_rows": len(raw_df),
            "is_primary_sales": is_primary_sales,
            "columns": col_meta,
        })

    # 2. If the shop has a valid sales ledger, build `lines`, `items`, and the 5 standard views
    ledger_meta: dict[str, Any] = {"has_ledger": has_ledger}
    if has_ledger:
        ledger_df, issues = build_ledger(tables, mapping, readme)
        ledger_df, items_df = _build_item_catalog_and_canonicalize_lines(tables, ledger_df, readme)

        # Assign 1-based line_id and synthetic order_id (`ROW_<line_id>`) when order_id is missing (Rulebook §8)
        n_rows = len(ledger_df)
        line_ids = list(range(1, n_rows + 1))
        raw_oids = list(ledger_df["order_id"])
        has_real_order_id = any(x is not None and not is_blank(x) for x in raw_oids)
        resolved_oids = [
            str(x).strip() if (x is not None and not is_blank(x)) else f"ROW_{lid}"
            for lid, x in zip(line_ids, raw_oids)
        ]

        # Format order_date as ISO YYYY-MM-DD and order_time as HH:MM:SS
        iso_dates = [
            d.isoformat() if isinstance(d, dt.date) else (str(d)[:10] if d is not None and not pd.isna(d) else None)
            for d in ledger_df["order_date"]
        ]
        iso_times = [
            t_val.strftime("%H:%M:%S") if isinstance(t_val, dt.time) else (str(t_val) if t_val is not None and not pd.isna(t_val) else None)
            for t_val in ledger_df["order_time"]
        ]

        lines_sql_df = pd.DataFrame({
            "line_id": line_ids,
            "order_id": resolved_oids,
            "order_date": iso_dates,
            "order_time": iso_times,
            "status": ledger_df["status"],
            "item_code": ledger_df["item_code"],
            "item_name": ledger_df["item_name"],
            "category": ledger_df["category"],
            "is_service_fee": ledger_df["is_service_fee"],
            "unit": [u if u else None for u in ledger_df["unit"]],
            "qty": ledger_df["qty"],
            "factor": ledger_df["factor"],
            "qty_base": ledger_df["qty_base"],
            "base_unit": ledger_df["base_unit"],
            "unit_price": ledger_df["unit_price"],
            "unit_price_base": ledger_df["unit_price_base"],
            "line_amount": ledger_df["line_amount"],
            "customer_code": ledger_df["customer_code"],
            "customer_name": ledger_df["customer_name"],
            "customer_key": ledger_df["customer_key"],
            "customer_group": ledger_df["customer_group"],
            "staff": ledger_df["staff"],
            "channel": ledger_df["channel"],
            "payment_method": ledger_df["payment_method"],
            "src_file": ledger_df["src_file"],
            "src_sheet": ledger_df["src_sheet"],
            "src_row": ledger_df["src_row"],
        })

        lines_sql_df.to_sql("lines", conn, index=False, if_exists="replace")
        items_df.to_sql("items", conn, index=False, if_exists="replace")

        # Create helpful indexes on `lines` and `items` for fast view queries
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_lines_order_id ON lines(order_id);
            CREATE INDEX IF NOT EXISTS idx_lines_order_date ON lines(order_date);
            CREATE INDEX IF NOT EXISTS idx_lines_status ON lines(status);
            CREATE INDEX IF NOT EXISTS idx_lines_item_name ON lines(item_name);
            CREATE INDEX IF NOT EXISTS idx_lines_item_code ON lines(item_code);
            CREATE INDEX IF NOT EXISTS idx_lines_customer_key ON lines(customer_key);
            CREATE INDEX IF NOT EXISTS idx_items_item_code ON items(item_code);
            CREATE INDEX IF NOT EXISTS idx_items_item_name ON items(item_name);
            """
        )

        events_meta = _build_order_events(
            conn, cleaned_frames, set(resolved_oids),
            skip_tables={mapping.sales_table, mapping.orders_table} - {None},
        )
        _create_sales_views(conn)

        valid_d = [d for d in iso_dates if d]
        ledger_meta.update({
            "sales_table": mapping.sales_table,
            "orders_table": mapping.orders_table,
            "has_real_order_id": has_real_order_id,
            "n_lines": len(lines_sql_df),
            "n_items": len(items_df),
            "min_date": min(valid_d) if valid_d else None,
            "max_date": max(valid_d) if valid_d else None,
            "issues": issues,
            "order_events": events_meta,
        })

    # 3. Load `calendar.csv` if available
    cal_file = _find_calendar_path(business_dir, calendar_path)
    has_calendar = False
    if cal_file is not None:
        cal_df = calendar_frame(cal_file)
        cal_df.to_sql("calendar", conn, index=False, if_exists="replace")
        if "date" in cal_df.columns:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_calendar_date ON calendar(date);")
        has_calendar = True

    # 4. Store schema metadata in `_schema_meta`
    meta_payload = {
        "business_id": business_dir.name,
        "readme": readme,
        "has_ledger": has_ledger,
        "has_calendar": has_calendar,
        "ledger_meta": ledger_meta,
        "tables": meta_tables,
    }
    conn.execute("CREATE TABLE IF NOT EXISTS _schema_meta (key TEXT PRIMARY KEY, value TEXT);")
    conn.execute(
        "INSERT OR REPLACE INTO _schema_meta (key, value) VALUES (?, ?);",
        ("meta", json.dumps(meta_payload, ensure_ascii=False)),
    )
    conn.commit()

    if readonly:
        enable_readonly(conn)

    return conn


# ---------------------------------------------------------------------- Prompt Schema Description


def _format_sample_rows(conn: sqlite3.Connection, relation: str, cols: list[str], limit: int = 2) -> list[str]:
    """Fetch up to `limit` sample rows from a view/table and format compactly."""
    if not cols:
        return []
    quoted_cols = ", ".join(f'"{c}"' for c in cols[:12])
    try:
        cur = conn.execute(f'SELECT {quoted_cols} FROM "{relation}" LIMIT {int(limit)}')
        rows = cur.fetchall()
    except sqlite3.Error:
        return []
    out = []
    for r in rows:
        pairs = []
        for c, val in zip(cols[:12], r):
            if val is None:
                continue
            s_val = str(val)
            if len(s_val) > 32:
                s_val = s_val[:29] + "..."
            pairs.append(f"{c}={s_val!r}")
        if pairs:
            out.append("    eg: " + ", ".join(pairs[:8]))
    return out


def schema_text(conn: sqlite3.Connection, max_chars: int = 13000) -> str:
    """Produce a prompt-ready description of views and tables in `conn` (capped at `max_chars`).

    Order of presentation:
    1. Business header & overview from README.
    2. If `has_ledger` is True:
       - Standard Rulebook Views (`v_valid_orders`, `v_valid_lines`, `v_orders`, `v_lines`, `v_items`)
         with exact column meanings, date range `[min_date .. max_date]`, status counts, and sample rows.
       - Cleaned auxiliary tables (non-sales tables, plus note on cleaned sales table).
    3. If `has_ledger` is False (e.g. `dev_012` repair shop):
       - Explicit notice that this shop has NO sales ledger / NO `v_*` views, followed by full details
         of every cleaned table (`so_sua_xe`, `danh_sach_tho`, etc.).
    4. `calendar` table summary and `raw_*` fallback tables notice.
    """
    try:
        row = conn.execute("SELECT value FROM _schema_meta WHERE key = 'meta'").fetchone()
        meta = json.loads(row[0]) if row else {}
    except sqlite3.Error:
        meta = {}

    biz_id = meta.get("business_id", "unknown")
    has_ledger = bool(meta.get("has_ledger", False))
    has_calendar = bool(meta.get("has_calendar", False))
    ledger_meta = meta.get("ledger_meta", {})
    tables_meta: list[dict[str, Any]] = meta.get("tables", [])
    readme = meta.get("readme", "")

    lines: list[str] = []
    lines.append(f"=== DATABASE SCHEMA FOR {biz_id} ===")

    # Include first paragraph / header of README for context
    if readme:
        readme_head = [ln.strip() for ln in readme.splitlines() if ln.strip()][:5]
        for ln in readme_head:
            lines.append(f"  {ln}")
        lines.append("")

    if has_ledger:
        min_d = ledger_meta.get("min_date")
        max_d = ledger_meta.get("max_date")
        has_real_oid = ledger_meta.get("has_real_order_id", True)

        # Query counts and status breakdown from views
        try:
            n_orders = conn.execute("SELECT COUNT(*) FROM v_orders").fetchone()[0]
            n_valid_orders = conn.execute("SELECT COUNT(*) FROM v_valid_orders").fetchone()[0]
            n_lines = conn.execute("SELECT COUNT(*) FROM v_lines").fetchone()[0]
            n_valid_lines = conn.execute("SELECT COUNT(*) FROM v_valid_lines").fetchone()[0]
            n_items = conn.execute("SELECT COUNT(*) FROM v_items").fetchone()[0]
            status_rows = conn.execute(
                "SELECT status, COUNT(*) FROM v_orders GROUP BY status ORDER BY COUNT(*) DESC"
            ).fetchall()
            status_summary = ", ".join(f"{st}={cnt}" for st, cnt in status_rows)
        except sqlite3.Error:
            n_orders = n_valid_orders = n_lines = n_valid_lines = n_items = 0
            status_summary = ""

        oid_note = (
            "1 row per order"
            if has_real_oid
            else "line-only ledger without order_id: each row is 1 order with synthetic order_id 'ROW_<line_id>' (§8)"
        )

        lines.append("=== 1. RULEBOOK SALES VIEWS (USE THESE FIRST FOR REVENUE, ORDERS, ITEMS, CUSTOMERS) ===")
        lines.append(
            f"Date range: [{min_d} .. {max_d}] | Orders by status: {status_summary}"
        )
        n_pay = _count_rows(conn, "payments")
        n_deliv = _count_rows(conn, "deliveries")
        n_due = _count_rows(conn, "order_due")
        n_deliv_rounds = _count_rows(conn, "v_deliveries") if n_deliv else 0
        lines.append(
            "- VIEW `v_valid_orders` "
            f"(rows={n_valid_orders}, {oid_note}, EXCLUDES 'huy' & 'tra_hang', INCLUDES 'hoan_thanh' & 'dang_giao' per §1):"
        )
        lines.append(
            "  Columns: order_id (TEXT), order_date (TEXT 'YYYY-MM-DD' placement date), order_time (TEXT 'HH:MM:SS'), "
            "order_month (TEXT 'YYYY-MM'), status (TEXT: 'hoan_thanh'|'dang_giao'), "
            "revenue (REAL: sum of line_amount for the order), n_lines (INT), total_qty_base (REAL), "
            "customer_code (TEXT), customer_name (TEXT, NULL for walk-in), customer_key (TEXT, unique customer ID for grouping/counting, NULL for walk-in §3), "
            "customer_group (TEXT), staff (TEXT), channel (TEXT), payment_method (TEXT)"
            + _order_event_columns_text(n_pay, n_deliv, n_due)
        )
        lines.extend(
            _format_sample_rows(
                conn,
                "v_valid_orders",
                ["order_id", "order_date", "status", "revenue", "customer_key", "customer_name", "channel", "payment_method"],
                limit=2,
            )
        )

        lines.append(
            f"- VIEW `v_valid_lines` (rows={n_valid_lines}, sold lines of valid orders where status NOT IN ('huy', 'tra_hang')):"
        )
        lines.append(
            "  Columns: line_id (INT), order_id (TEXT), order_date (TEXT 'YYYY-MM-DD'), order_time (TEXT), "
            "order_month (TEXT 'YYYY-MM'), status (TEXT), item_code (TEXT), item_name (TEXT canonical name), "
            "category (TEXT), is_service_fee (INT: 1 for 'Phí phục vụ', 0 for real items §3 — filter `is_service_fee = 0` when ranking/counting items), "
            "unit (TEXT sold unit), qty (REAL sold qty), factor (REAL conversion factor), "
            "qty_base (REAL qty converted to smallest base_unit §10 — use `SUM(qty_base)` for best-selling item quantity), "
            "base_unit (TEXT), unit_price (REAL price per sold unit), unit_price_base (REAL price per base_unit), "
            "line_amount (REAL after line discount), customer_code (TEXT), customer_name (TEXT), customer_key (TEXT), "
            "customer_group (TEXT), staff (TEXT), channel (TEXT), payment_method (TEXT)"
        )
        lines.extend(
            _format_sample_rows(
                conn,
                "v_valid_lines",
                ["order_id", "order_date", "item_code", "item_name", "qty", "unit", "qty_base", "base_unit", "line_amount"],
                limit=2,
            )
        )

        lines.append(
            f"- VIEW `v_orders` (rows={n_orders}, ALL orders across all statuses: 'hoan_thanh', 'dang_giao', 'huy', 'tra_hang'):"
        )
        lines.append(
            "  Use `v_orders` for total order counts, cancelled order counts (`status = 'huy'`), returned order counts (`status = 'tra_hang'`), and cancellation rate (`SUM(status = 'huy') * 100.0 / COUNT(*)`)."
        )

        lines.append(
            f"- VIEW `v_lines` (rows={n_lines}, ALL sales lines including 'huy' and 'tra_hang'):"
        )
        lines.append(
            "  Use `v_lines` when looking up an item's selling price on a given date D (`unit_price` or `unit_price_base`), because Rulebook §5 includes cancelled and returned orders when finding price on day D."
        )

        lines.append(
            f"- VIEW `v_items` (rows={n_items}, canonical item catalog & spelling aliases per §9):"
        )
        lines.append(
            "  Columns: item_code (TEXT), item_name (TEXT canonical), name_aliases (TEXT pipe-separated ' | ' list of all spellings/abbreviations), "
            "category (TEXT), base_unit (TEXT), sell_price (REAL), cost_price (REAL), active_ingredient (TEXT), is_prescription (TEXT)"
        )
        lines.extend(
            _format_sample_rows(
                conn,
                "v_items",
                ["item_code", "item_name", "name_aliases", "category", "base_unit", "sell_price", "cost_price"],
                limit=3,
            )
        )
        if n_pay:
            lines.append(
                f"- VIEW `v_payments` (rows={n_pay}, one row per money receipt linked to an order, every order status, "
                "taken as recorded in the shop's receipt/cash book):"
            )
            lines.append(
                "  Columns: order_id (TEXT), paid_at (TEXT 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DD'), paid_date (TEXT 'YYYY-MM-DD'), "
                "paid_time (TEXT 'HH:MM:SS' or NULL), paid_month (TEXT 'YYYY-MM'), amount (REAL), method (TEXT), src_table (TEXT). "
                "Revenue and order periods still follow the ORDER date (`v_orders.order_date`), not the payment date."
            )
            lines.extend(_format_sample_rows(conn, "v_payments", ["order_id", "paid_at", "amount", "method"], limit=2))
        if n_deliv:
            lines.append(
                f"- VIEW `v_deliveries` (rows={n_deliv_rounds}, one row per delivery round of an order, every order status, "
                "including rounds of orders later returned):"
            )
            lines.append(
                "  Columns: order_id (TEXT), delivery_round (TEXT round number, or the date when the shop records no round), "
                "delivery_date (TEXT 'YYYY-MM-DD'), delivery_month (TEXT 'YYYY-MM'), n_rows (INT item rows shipped in that round), src_table (TEXT). "
                "Count rounds in a month with `COUNT(*) FROM v_deliveries WHERE delivery_month = 'YYYY-MM'`."
            )
            lines.extend(_format_sample_rows(conn, "v_deliveries", ["order_id", "delivery_round", "delivery_date", "n_rows"], limit=2))
        lines.append("")
        lines.append("=== 2. CLEANED AUXILIARY & SOURCE TABLES ===")
    else:
        lines.append("=== NOTICE: NON-LEDGER BUSINESS (NO SALES VIEWS) ===")
        lines.append(
            "This business does NOT have a product sales ledger (for example, it is a repair/service log). "
            "Views `v_lines`, `v_valid_lines`, `v_orders`, `v_valid_orders`, `v_items` are NOT created. "
            "Query the cleaned tables below directly."
        )
        lines.append("")
        lines.append("=== 1. CLEANED TABLES ===")

    # Format cleaned tables: auxiliary tables first (full detail), then primary sales source tables (compact)
    sorted_tables = sorted(tables_meta, key=lambda x: (1 if x.get("is_primary_sales") else 0))
    for t_info in sorted_tables:
        c_name = t_info["clean_name"]
        r_name = t_info["raw_name"]
        orig_name = t_info["orig_name"]
        n_rows = t_info["n_rows"]
        is_primary = t_info.get("is_primary_sales", False)
        cols_info = t_info.get("columns", [])

        # Find date range if any date/datetime column exists
        date_range_str = ""
        for c_meta in cols_info:
            if c_meta["kind"] in ("date", "datetime"):
                sc = c_meta["safe_name"]
                try:
                    mn, mx = conn.execute(
                        f'SELECT MIN(SUBSTR("{sc}", 1, 10)), MAX(SUBSTR("{sc}", 1, 10)) FROM "{c_name}" WHERE "{sc}" IS NOT NULL'
                    ).fetchone()
                    if mn and mx:
                        date_range_str = f" | date_range ({sc})=[{mn} .. {mx}]"
                        break
                except sqlite3.Error:
                    pass

        role_tag = " (source of sales views; prefer v_* views unless querying extra columns)" if is_primary else ""
        lines.append(
            f"TABLE `{c_name}` (raw fallback: `{r_name}`, orig: {orig_name!r}, rows={n_rows}{date_range_str}){role_tag}:"
        )
        for c_meta in cols_info:
            sc = c_meta["safe_name"]
            oc = c_meta["orig_name"]
            kd = c_meta["kind"]
            desc = c_meta.get("description", "")
            desc_part = f" — {desc}" if desc else ""
            lines.append(f"  - `{sc}` ({kd}, orig: {oc!r}){desc_part}")

        sample_cols = [c_meta["safe_name"] for c_meta in cols_info[:8]]
        lines.extend(_format_sample_rows(conn, c_name, sample_cols, limit=1 if is_primary else 2))
        lines.append("")

    if has_calendar:
        lines.append("=== CALENDAR TABLE ===")
        lines.append(
            "TABLE `calendar` (one row per solar day; JOIN `calendar.date = v_orders.order_date`). Columns: "
            "`date` TEXT 'YYYY-MM-DD', `year` INT, `month` INT, `day` INT, `quarter` INT, `iso_year` INT, `iso_week` INT, "
            "`day_of_week` INT 1=Mon..7=Sun (same as `weekday`), `day_name_vi` TEXT ('Thứ Hai'..'Chủ nhật'), "
            "`is_weekend` INT 0/1, `lunar_year` INT, `lunar_month` INT (12 = tháng Chạp, 1 = tháng Giêng), `lunar_day` INT, "
            "`lunar_leap` INT 0/1 (leap lunar month), `holiday` TEXT (also `holiday_vi`, NULL on ordinary days)"
        )
        try:
            lo, hi = conn.execute("SELECT MIN(date), MAX(date) FROM calendar").fetchone()
            lines.append(f"  date_range=[{lo} .. {hi}]")
        except sqlite3.Error:
            pass
        lines.append("")

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[: max_chars - 40].rsplit("\n", 1)[0] + "\n... (schema truncated to fit budget)"
    return text
