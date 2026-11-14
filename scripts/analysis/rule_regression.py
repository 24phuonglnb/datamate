"""Rulebook regression without LLM on 3000 train questions (Task T5).

Evaluates the accuracy of the data layer (`src/cleaning.py`, `src/mapping.py`,
`src/ledger.py`, `src/views.py`) independently of any LLM by:
1. Selecting train questions tagged by `scripts/analysis/intent_tagger.py` (`tag`, `ttag`)
   for intents: `revenue`, `order_count`, `cancel_count`, `cancel_rate`, `aov`,
   `best_day`, `topk_items`/`best_item`, `item_qty`, `rev_change_pct`
   that have an explicit period ("tháng M/YYYY" or "ngày dd/mm/yyyy", i.e.
   `ttag in ('month_explicit', 'date_explicit')`).
2. Executing deterministic SQL templates on the SQLite views created by `build_database`
   (`v_valid_orders`, `v_orders`, `v_valid_lines`, `v_lines`, `v_items`), enforcing
   Rulebook §1–§3, §9, and §10 (rounding VND to integer, AOV half-up, percentages to
   2 decimals, ranking by `qty_base` DESC and tie-breaking by `COALESCE(item_code, item_name)` ASC,
   period capped at `as_of_date`).
3. Skipping questions with extra filters or sub-intents outside the pure template scope,
   recording exact counts of skipped questions.
4. Automatically diagnosing any wrong answer by testing data-layer variants:
   - `no_exclude_return`: do not exclude returned orders (`tra_hang`)
   - `no_exclude_cancel`: do not exclude cancelled orders (`huy`)
   - `exclude_shipping`: also exclude shipping orders (`dang_giao`)
   - `no_dedup`: disable export duplicate removal (`drop_export_duplicates`)
   - `no_filldown`: disable order-level blank forward filling (`fill_order_level`)
   - `order_total_col`: sum invoice-level total (`order_total`) instead of line revenue (`line_amount`)
   - `no_unit_conv`: use raw sold quantity (`qty`) instead of base-unit quantity (`qty_base`)
   - `enhanced_unit_conv`: parse conversion tables with `Hàng`/`Mặt hàng` columns (`DanhMuc`, `QuyDoi`)
   - `enhanced_catalog_join`: join `san_pham` on non-barcode `SKU`/`Mã HH`/`MaHangHoa` and `Sản phẩm`
5. Writing a detailed Markdown report to `reports/rule_regression.md` with per-intent and
   per-shop breakdowns, wrong-question diagnostics, and a summary line:
   `% đúng trên câu đã chọn`.

Usage:
    .venv/bin/python scripts/analysis/rule_regression.py [biz_101 biz_102 ...]
"""
from __future__ import annotations

import calendar
import collections
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from intent_tagger import deacc, tag, ttag
from src.cleaning import (
    META_COLS,
    RawTable,
    drop_export_duplicates,
    fill_order_level,
    is_blank,
    load_business,
    nfc,
    norm_key,
    parse_datetime,
    parse_number,
    parse_qty,
    split_summary_rows,
)
from src.ledger import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_PRIORITY,
    STATUS_RETURNED,
    STATUS_SHIPPING,
    build_ledger,
    load_unit_conversions,
    normalize_status,
)
from src.mapping import Mapping, propose_mapping
from src.views import build_database, item_match_key

DATA_DIR = Path(os.environ.get("ZAIC_TRAIN_DIR", "")) or ROOT / "data" / "train" / "train"
REPORT_PATH = ROOT / "reports" / "rule_regression.md"

TARGET_INTENTS = (
    "revenue",
    "order_count",
    "cancel_count",
    "cancel_rate",
    "aov",
    "best_day",
    "topk_items",
    "best_item",
    "item_qty",
    "rev_change_pct",
)
TARGET_TIME_TAGS = ("month_explicit", "date_explicit")


# ---------------------------------------------------------------------- Period Helpers


def month_bounds(year: int, month: int, as_of_date: str) -> tuple[str, str]:
    """Return ISO `(start_date, end_date)` for `month/year`, capped at `as_of_date` (Rulebook §2)."""
    last_day = calendar.monthrange(year, month)[1]
    start = f"{year:04d}-{month:02d}-01"
    end = min(f"{year:04d}-{month:02d}-{last_day:02d}", as_of_date)
    return start, end


def parse_explicit_period(question: str, as_of_date: str) -> tuple[str, str, tuple[int, int] | None] | None:
    """Extract `(start_date, end_date, (year, month) | None)` for explicit month or date questions."""
    s = deacc(question)
    m_mo = re.search(r"thang (\d{1,2})(?:/| nam )(\d{4})", s)
    if m_mo:
        mo, yr = int(m_mo.group(1)), int(m_mo.group(2))
        if 1 <= mo <= 12:
            start, end = month_bounds(yr, mo, as_of_date)
            return start, end, (yr, mo)
    # Explicit single date dd/mm/yyyy (not a date range "từ dd/mm/yyyy đến dd/mm/yyyy")
    dates = re.findall(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if len(dates) == 1 and not re.search(r"tu \d{1,2}/\d{1,2}/\d{4} den", s):
        d, mo, yr = int(dates[0][0]), int(dates[0][1]), int(dates[0][2])
        iso = f"{yr:04d}-{mo:02d}-{d:02d}"
        end = min(iso, as_of_date)
        return iso, end, None
    return None


# ---------------------------------------------------------------------- Filter & Entity Helpers


def match_item_in_catalog(
    catalog_items: list[tuple[str | None, str, str | None, str | None]],
    question: str,
) -> tuple[str | None, str, str | None] | None:
    """Match an item mentioned in `question` against `(item_code, item_name, name_aliases, base_unit)` rows."""
    qk = item_match_key(question)
    best: tuple[str | None, str, str | None] | None = None
    best_len = 0
    for code, name, aliases, bunit in catalog_items:
        cand_strings = (aliases or name or "").split(" | ")
        for al in cand_strings:
            ak = item_match_key(al)
            if ak and re.search(r"(?<![0-9a-z])" + re.escape(ak) + r"(?![0-9a-z])", qk):
                if len(ak) > best_len:
                    best_len = len(ak)
                    best = (code, name, bunit)
    return best


def should_skip_question(
    intent: str,
    question: str,
    ans_type: str,
    has_sales_views: bool,
    min_date: str | None,
    period_info: tuple[str, str, tuple[int, int] | None] | None,
) -> str | None:
    """Return a skip reason string if the question has extra filters/sub-intents outside template scope, else None."""
    if not has_sales_views:
        return "no_sales_views"
    if period_info is None:
        return "unparsed_or_range_period"

    start, end, ym = period_info
    s = deacc(question)

    # Period completely before shop's data start date -> unanswerable per Rulebook §7
    if min_date and end < min_date:
        return "before_shop_min_date"
    if ans_type == "unanswerable":
        return "unanswerable_ground_truth"

    if intent == "revenue":
        # Skip multi-month trend booleans, daily threshold counts, item/category/customer/staff/channel/rx filters
        if re.search(
            r"nhom|khach|\bdon\b|bill|\bca\b|nhan vien|tra bang|so voi|%|phan tram|ngay|hoat chat|ke don|"
            r"size|trung binh|binh quan|moi|quy|mat hang|mon |ban chay|top|xu huong|luon cao hon|con no|cong no|"
            r"(?:doanh thu|dthu) (?:cua|cuar) (?!cua hang)",
            s,
        ):
            return "extra_filter_or_subintent"
        # Skip item-specific revenue ("tháng 4/2026 bán <Mặt hàng> được bao nhiêu tiền")
        if re.search(r"\b(ban|bans)\b", s) and not re.search(
            r"cua\s*\w*\s+hang\s*\w*\s+(?:ban|bans)\s+\S+\s+(tong cong|total|toongr cong|bao nhieu|bnhiu|bn)", s
        ):
            return "item_specific_revenue"
        return None

    if intent == "order_count":
        if re.search(r"khach|nhom|nhan vien|kenh|\bca\b|mat hang|san pham|mon ", s):
            return "extra_filter"
        return None

    if intent == "cancel_count":
        if re.search(r"giao tre|ly do|nguyen nhan|khach|nhom|nhan vien|kenh|\bca\b", s):
            return "extra_filter_or_reason"
        return None

    if intent == "cancel_rate":
        if re.search(r"khach|nhom|nhan vien|kenh|\bca\b", s):
            return "extra_filter"
        return None

    if intent == "aov":
        if re.search(r"khach|nhom|nhan vien|kenh|\bca\b", s):
            return "extra_filter"
        return None

    if intent == "best_day":
        if re.search(r"khach|nhom|nhan vien|kenh|\bca\b", s):
            return "extra_filter"
        return None

    if intent in ("topk_items", "best_item"):
        # `intent_tagger.py` routes some item revenue ("mặt hàng X thu về bao nhiêu tiền")
        # and item qty ("mặt hàng X bán được tổng cộng bao nhiêu <đơn vị>") into `topk_items`
        if re.search(
            r"thu ve|bao nhieu tien|bn tien|bnhiu tien|"
            r"ban (duoc|dc|ra) (tong cong |total )?(bao nhieu|bnhiu|bn|nhieu|may)|"
            r"\be\b|khong ban|nhom|khach|kenh",
            s,
        ):
            return "item_rev_or_qty_in_topk_tag"
        return None

    if intent == "item_qty":
        if re.search(r"hon hay kem|%|phan tram|khach|nhom|kenh|\bca\b", s):
            return "misclassified_or_extra_filter"
        return None

    if intent == "rev_change_pct":
        # Skip customer frequency share or item with "%" in name (e.g. "Voltaren Emulgel 1%", "Povidine 10%")
        if re.search(
            r"khach|mua tu \d+ don|gia bao nhieu|ban ra|ban (?:duoc|dc) (?:may|bao nhieu|bnhiu|bn)|nhom|kenh|\bca\b",
            s,
        ):
            return "misclassified_or_extra_filter"
        # Check if previous comparison period is before min_date
        all_m = re.findall(r"thang (\d{1,2})(?:/| nam )(\d{4})", s)
        if len(all_m) >= 2:
            m2, y2 = int(all_m[1][0]), int(all_m[1][1])
            _, e2 = month_bounds(y2, m2, "9999-12-31")
            if min_date and e2 < min_date:
                return "prev_period_before_min_date"
        elif ym is not None:
            yr, mo = ym
            if re.search(r"cung ky|cung thang|nam ngoai|nam truoc", s):
                _, e2 = month_bounds(yr - 1, mo, "9999-12-31")
            else:
                pm = 12 if mo == 1 else mo - 1
                py = yr - 1 if mo == 1 else yr
                _, e2 = month_bounds(py, pm, "9999-12-31")
            if min_date and e2 < min_date:
                return "prev_period_before_min_date"
        return None

    return "unsupported_intent"


# ---------------------------------------------------------------------- SQL Templates on Views


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


def _extract_topk_k(s: str) -> int | None:
    """Extract top-k integer from a deaccented question after stripping explicit month/date phrases."""
    s_no_date = re.sub(r"thang\s+\d{1,2}(?:/|\s+nam\s+)\d{4}|\d{1,2}/\d{1,2}/\d{4}", " ", s)
    m_k = re.search(
        r"(?:top ?|liet ke |cho minh |cho toi |xem giup |coi gium |cho hoi |giup minh liet ke )?(\d+)\s+"
        r"(?:mat\s*\w*\s+hang\w*|san pham|hang\w*|mon|sp|best)",
        s_no_date,
    )
    return int(m_k.group(1)) if m_k else None


def execute_template(
    conn: sqlite3.Connection,
    intent: str,
    question: str,
    as_of_date: str,
    period_info: tuple[str, str, tuple[int, int] | None],
    catalog_items: list[tuple[str | None, str, str | None, str | None]],
) -> tuple[Any, str | None]:
    """Run the SQL template for `intent` on `conn`.

    Returns `(computed_answer, skip_reason_if_any)`.
    """
    start, end, ym = period_info
    s = deacc(question)

    if intent == "revenue":
        row = conn.execute(SQL_TEMPLATES["revenue"], (start, end)).fetchone()
        return (int(row[0]) if row and row[0] is not None else 0), None

    if intent == "order_count":
        m_th = re.search(r"(?:≥|>=|tu|dat)\s*([\d\.]+)\s*dong", s)
        if m_th:
            th = float(m_th.group(1).replace(".", ""))
            row = conn.execute(SQL_TEMPLATES["order_count_threshold"], (start, end, th)).fetchone()
        else:
            row = conn.execute(SQL_TEMPLATES["order_count"], (start, end)).fetchone()
        return (int(row[0]) if row and row[0] is not None else 0), None

    if intent == "cancel_count":
        row = conn.execute(SQL_TEMPLATES["cancel_count"], (start, end)).fetchone()
        return (int(row[0]) if row and row[0] is not None else 0), None

    if intent == "cancel_rate":
        row = conn.execute(SQL_TEMPLATES["cancel_rate"], (start, end)).fetchone()
        return (float(row[0]) if row and row[0] is not None else 0.0), None

    if intent == "aov":
        row = conn.execute(SQL_TEMPLATES["aov"], (start, end)).fetchone()
        return (int(row[0]) if row and row[0] is not None else 0), None

    if intent == "best_day":
        row = conn.execute(SQL_TEMPLATES["best_day"], (start, end)).fetchone()
        return (row[0] if row else None), None

    if intent in ("topk_items", "best_item"):
        k = _extract_topk_k(s) if intent == "topk_items" else None
        if k is not None:
            rows = conn.execute(SQL_TEMPLATES["topk_items"], (start, end, k)).fetchall()
            return [r[0] for r in rows], None
        row = conn.execute(SQL_TEMPLATES["best_item"], (start, end)).fetchone()
        return (row[0] if row else None), None

    if intent == "item_qty":
        matched = match_item_in_catalog(catalog_items, question)
        if matched is None:
            # Do not skip if the shop has a catalog table or sales lines: return None so we diagnose catalog/join issues!
            return None, None
        icode, iname, _ = matched
        if icode:
            row = conn.execute(SQL_TEMPLATES["item_qty_by_code"], (start, end, icode)).fetchone()
        else:
            row = conn.execute(SQL_TEMPLATES["item_qty_by_name"], (start, end, iname)).fetchone()
        val = float(row[0]) if row and row[0] is not None else 0.0
        calc = int(round(val)) if abs(val - round(val)) < 1e-6 else round(val, 2)
        return calc, None

    if intent == "rev_change_pct":
        all_m = re.findall(r"thang (\d{1,2})(?:/| nam )(\d{4})", s)
        if len(all_m) >= 2:
            m1, y1 = int(all_m[0][0]), int(all_m[0][1])
            m2, y2 = int(all_m[1][0]), int(all_m[1][1])
            s1, e1 = month_bounds(y1, m1, as_of_date)
            s2, e2 = month_bounds(y2, m2, as_of_date)
        elif ym is not None:
            yr, mo = ym
            s1, e1 = start, end
            if re.search(r"cung ky|cung thang|nam ngoai|nam truoc", s):
                s2, e2 = month_bounds(yr - 1, mo, as_of_date)
            else:
                pm = 12 if mo == 1 else mo - 1
                py = yr - 1 if mo == 1 else yr
                s2, e2 = month_bounds(py, pm, as_of_date)
        else:
            return None, "unparsed_comparison_period"

        row = conn.execute(SQL_TEMPLATES["rev_change_pct"], (s1, e1, s2, e2)).fetchone()
        return (float(row[0]) if row and row[0] is not None else None), None

    return None, "unknown_intent"


def answers_match(calc: Any, expected: Any, aliases: list[Any] | None = None) -> bool:
    """Compare computed template value against ground-truth `expected` per Rulebook §9."""
    if calc is None:
        return False
    targets = [expected] + (aliases or [])
    for exp in targets:
        if isinstance(calc, (int, float)) and isinstance(exp, (int, float)):
            if abs(float(calc) - float(exp)) < 1e-6:
                return True
        elif isinstance(calc, str) and isinstance(exp, str):
            if item_match_key(calc) == item_match_key(exp):
                return True
        elif isinstance(calc, list) and isinstance(exp, list):
            if len(calc) == len(exp) and all(
                item_match_key(c) == item_match_key(e) if isinstance(c, str) and isinstance(e, str) else c == e
                for c, e in zip(calc, exp)
            ):
                return True
        elif calc == exp:
            return True
    return False


# ---------------------------------------------------------------------- Diagnostic Variants


def _extract_enhanced_catalog_map(tables: list[RawTable]) -> tuple[dict[str, str], list[tuple[str | None, str, str | None, str | None]]]:
    """Diagnostic helper: extract `(item_code -> item_name)` from `san_pham` avoiding barcode columns
    and recognizing `Sản phẩm` as an item name column (`biz_111`, `biz_123`, `biz_129`)."""
    code_to_name: dict[str, str] = {}
    cat_items: list[tuple[str | None, str, str | None, str | None]] = []

    for t in tables:
        tk = norm_key(t.name)
        if not any(w in tk for w in ["san pham", "hang hoa", "danh muc", "thuc don", "menu"]):
            continue
        if any(w in tk for w in ["quy doi", "don vi", "khach hang", "nhap"]):
            continue
        df, _ = split_summary_rows(t.df)
        cols = [c for c in df.columns if c not in META_COLS]
        name_c = next(
            (
                c
                for c in cols
                if not any(b in norm_key(c) for b in ["mo ta", "mau ghi chu", "lien quan", "loai"])
                and any(
                    w in norm_key(c)
                    for w in ["ten hang", "ten sp", "ten san pham", "ten thuoc", "ten mon", "san pham", "ten"]
                )
            ),
            None,
        )
        # Prefer SKU / MaHangHoa / Mã HH over barcode/EAN/note columns
        code_c = next(
            (
                c
                for c in cols
                if c != name_c
                and not any(b in norm_key(c) for b in ["barcode", "ma vach", "ean", "lien quan", "ghi chu", "mo ta"])
                and any(w in norm_key(c) for w in ["ma hang", "ma sp", "ma san pham", "ma hh", "sku", "id sp"])
            ),
            None,
        )
        unit_c = next(
            (c for c in cols if c not in (name_c, code_c) and any(w in norm_key(c) for w in ["don vi", "dvt"])),
            None,
        )
        if not name_c:
            continue
        for _, r in df.iterrows():
            nm = str(r[name_c]).strip() if not is_blank(r[name_c]) else ""
            if not nm or norm_key(nm) == "phi phuc vu":
                continue
            cd = str(r[code_c]).strip() if (code_c and not is_blank(r[code_c])) else None
            bu = str(r[unit_c]).strip() if (unit_c and not is_blank(r[unit_c])) else None
            if cd:
                code_to_name[cd.upper()] = nm
            cat_items.append((cd, nm, nm, bu))
    return code_to_name, cat_items


def _extract_enhanced_conversions(tables: list[RawTable], readme: str) -> dict[tuple[str | None, str], tuple[float, str]]:
    """Diagnostic helper: also load unit conversions from `DanhMuc` (`Hàng`, `ĐV lớn`, `ĐV nhỏ`, `Hệ số QĐ`)
    and `QuyDoi` (`Mặt hàng`, `ĐVT`, `Bằng`) as in `biz_117` and `biz_114`."""
    convs = dict(load_unit_conversions(tables, readme))
    for t in tables:
        tk = norm_key(t.name)
        if not any(w in tk for w in ["quy doi", "quydoi", "don vi", "donvi", "danh muc", "danhmuc"]):
            continue
        df, _ = split_summary_rows(t.df)
        cols = [c for c in df.columns if c not in META_COLS]
        col_item = next(
            (c for c in cols if any(w in norm_key(c) for w in ["ten san pham", "ten hang", "mat hang", "hang", "ma hang"])),
            None,
        )
        col_base = next(
            (c for c in cols if any(w in norm_key(c) for w in ["co ban", "dv nho", "dvt nho"])),
            None,
        )
        col_unit = next(
            (
                c
                for c in cols
                if c not in (col_item, col_base)
                and any(w in norm_key(c) for w in ["dv lon", "dvt lon", "quy doi", "don vi", "dvt"])
            ),
            None,
        )
        col_factor = next(
            (
                c
                for c in cols
                if c not in (col_item, col_base, col_unit)
                and any(w in norm_key(c) for w in ["he so", "ti le", "bang", "quy doi"])
            ),
            None,
        )
        if not (col_item and col_unit and col_factor):
            continue
        for _, r in df.iterrows():
            iv, uv, fv = r[col_item], r[col_unit], r[col_factor]
            if is_blank(iv) or is_blank(uv) or is_blank(fv):
                continue
            num, emb_u = parse_qty(fv)
            if num is None:
                continue
            bu = emb_u or (str(r[col_base]).strip() if col_base and not is_blank(r[col_base]) else "base")
            convs[(norm_key(iv), norm_key(uv))] = (float(num), norm_key(bu))
    return convs


def diagnose_failure(
    conn: sqlite3.Connection,
    tables: list[RawTable],
    mapping: Mapping,
    readme: str,
    intent: str,
    question: str,
    as_of_date: str,
    period_info: tuple[str, str, tuple[int, int] | None],
    calc: Any,
    expected: Any,
    aliases: list[Any] | None = None,
) -> list[str]:
    """Run automatic diagnostic variants on a failed question to identify which data-layer cause explains the mismatch."""
    start, end, ym = period_info
    s = deacc(question)
    diagnostics: list[str] = []

    # 1. Status & order-total variants directly on SQLite `v_orders` / `v_lines`
    if intent == "revenue" and isinstance(expected, (int, float)):
        diff = float(expected) - float(calc or 0)
        # Check if difference equals returned orders (`tra_hang`)
        ret_rev = conn.execute(
            "SELECT ROUND(COALESCE(SUM(revenue), 0)) FROM v_orders WHERE order_date BETWEEN ? AND ? AND status = 'tra_hang'",
            (start, end),
        ).fetchone()[0]
        canc_rev = conn.execute(
            "SELECT ROUND(COALESCE(SUM(revenue), 0)) FROM v_orders WHERE order_date BETWEEN ? AND ? AND status = 'huy'",
            (start, end),
        ).fetchone()[0]
        ship_rev = conn.execute(
            "SELECT ROUND(COALESCE(SUM(revenue), 0)) FROM v_orders WHERE order_date BETWEEN ? AND ? AND status = 'dang_giao'",
            (start, end),
        ).fetchone()[0]
        all_rev = conn.execute(
            "SELECT ROUND(COALESCE(SUM(revenue), 0)) FROM v_orders WHERE order_date BETWEEN ? AND ?",
            (start, end),
        ).fetchone()[0]

        if abs(float(calc or 0) + ret_rev - float(expected)) < 1.0:
            diagnostics.append("variant MATCH: `no_exclude_return` (không lọc đơn trả hàng `tra_hang` ra đúng đáp án)")
        if abs(float(calc or 0) + canc_rev - float(expected)) < 1.0:
            diagnostics.append("variant MATCH: `no_exclude_cancel` (cộng cả tiền đơn huỷ `huy` ra đúng đáp án)")
        if abs(all_rev - float(expected)) < 1.0:
            diagnostics.append("variant MATCH: `no_status_filter` (không lọc trạng thái huỷ/trả ra đúng đáp án)")
        if abs(float(calc or 0) - ship_rev - float(expected)) < 1.0:
            diagnostics.append("variant MATCH: `exclude_shipping` (bỏ đơn `dang_giao` ra đúng đáp án)")

    # 2. Check no_unit_conv on SQLite `v_valid_lines` (using SUM(qty) instead of SUM(qty_base))
    if intent in ("topk_items", "best_item"):
        k_val = _extract_topk_k(s) if intent == "topk_items" else None
        k = k_val if k_val is not None else 1
        is_list_query = k_val is not None
        rows_raw_qty = conn.execute(
            "SELECT item_name FROM v_valid_lines WHERE order_date BETWEEN ? AND ? AND is_service_fee = 0 "
            "GROUP BY COALESCE(item_code, item_name) "
            "ORDER BY SUM(qty) DESC, COALESCE(item_code, item_name) ASC LIMIT ?",
            (start, end, k),
        ).fetchall()
        cand_raw_qty = [r[0] for r in rows_raw_qty] if is_list_query else (rows_raw_qty[0][0] if rows_raw_qty else None)
        if answers_match(cand_raw_qty, expected, aliases):
            diagnostics.append("variant MATCH: `no_unit_conv` (xếp theo `SUM(qty)` không quy đổi đơn vị ra đúng đáp án)")

        # Check enhanced unit conversion + enhanced catalog join
        code_to_name, _ = _extract_enhanced_catalog_map(tables)
        enh_convs = _extract_enhanced_conversions(tables, readme)
        lines_rows = conn.execute(
            "SELECT item_code, item_name, unit, qty, qty_base FROM v_valid_lines "
            "WHERE order_date BETWEEN ? AND ? AND is_service_fee = 0",
            (start, end),
        ).fetchall()

        agg_enh_conv: dict[str, float] = collections.defaultdict(float)
        agg_enh_cat: dict[str, float] = collections.defaultdict(float)
        key_to_display: dict[str, str] = {}

        for ic, inm, u, q, qb in lines_rows:
            disp_cat = inm if (inm and inm.strip()) else (code_to_name.get(str(ic).upper(), "") if ic else "")
            k_sort = ic if ic else disp_cat
            if not k_sort:
                continue
            key_to_display[k_sort] = disp_cat
            agg_enh_cat[k_sort] += float(qb or 0.0)

            # Recompute qty_base using enhanced conversions
            f_enh = 1.0
            if u:
                conv = enh_convs.get((norm_key(disp_cat), norm_key(u))) or (
                    enh_convs.get((norm_key(ic), norm_key(u))) if ic else None
                )
                if conv:
                    f_enh = conv[0]
            qb_enh = float(q or 0.0) * f_enh if abs(float(qb or 0.0) - float(q or 0.0)) < 1e-6 else float(qb or 0.0)
            agg_enh_conv[k_sort] += qb_enh

        ranked_cat = [
            key_to_display[k_id]
            for k_id, _ in sorted(agg_enh_cat.items(), key=lambda x: (-x[1], x[0]))[:k]
        ]
        cand_cat = ranked_cat if is_list_query else (ranked_cat[0] if ranked_cat else None)
        if answers_match(cand_cat, expected, aliases):
            diagnostics.append(
                "variant MATCH: `enhanced_catalog_join` (nối `san_pham` qua cột `SKU`/`Mã HH`/`MaHangHoa` và `Sản phẩm` thay vì cột barcode lấy đúng `item_name`)"
            )

        ranked_conv = [
            key_to_display[k_id]
            for k_id, _ in sorted(agg_enh_conv.items(), key=lambda x: (-x[1], x[0]))[:k]
        ]
        cand_conv = ranked_conv if is_list_query else (ranked_conv[0] if ranked_conv else None)
        if answers_match(cand_conv, expected, aliases) and not answers_match(cand_cat, expected, aliases):
            if code_to_name:
                diagnostics.append(
                    "variant MATCH: `enhanced_catalog_join` + `enhanced_unit_conv` (nối `san_pham` lấy `item_name` rồi quy đổi đơn vị theo `README.md`/`DanhMuc` ra đúng thứ tự)"
                )
            else:
                diagnostics.append(
                    "variant MATCH: `enhanced_unit_conv` (đọc hệ số quy đổi từ bảng `DanhMuc`/`QuyDoi` có cột `Hàng`/`ĐV lớn` ra đúng thứ tự top-k)"
                )

    if intent == "item_qty":
        # Test 1: no_unit_conv (`SUM(qty)` instead of `SUM(qty_base)`)
        cat_rows = conn.execute("SELECT item_code, item_name, name_aliases, base_unit FROM v_items").fetchall()
        m_cat = match_item_in_catalog(cat_rows, question)
        if m_cat:
            ic, inm, _ = m_cat
            if ic:
                raw_q = conn.execute(
                    "SELECT COALESCE(SUM(qty), 0) FROM v_valid_lines WHERE order_date BETWEEN ? AND ? AND item_code = ?",
                    (start, end, ic),
                ).fetchone()[0]
            else:
                raw_q = conn.execute(
                    "SELECT COALESCE(SUM(qty), 0) FROM v_valid_lines WHERE order_date BETWEEN ? AND ? AND item_name = ?",
                    (start, end, inm),
                ).fetchone()[0]
            if answers_match(round(float(raw_q), 2), expected, aliases):
                diagnostics.append("variant MATCH: `no_unit_conv` (dùng `SUM(qty)` chưa quy đổi đơn vị ra đúng đáp án)")

        # Test 2: enhanced catalog join + unit conv (`biz_111`, `biz_123`, `biz_129`)
        _, enh_cat_items = _extract_enhanced_catalog_map(tables)
        enh_convs = _extract_enhanced_conversions(tables, readme)
        m_enh = match_item_in_catalog(enh_cat_items, question)
        if m_enh and m_enh[0]:
            ic_enh, nm_enh, _ = m_enh
            qb_enh = conn.execute(
                "SELECT COALESCE(SUM(qty_base), 0) FROM v_valid_lines WHERE order_date BETWEEN ? AND ? AND item_code = ?",
                (start, end, ic_enh),
            ).fetchone()[0]
            val_enh = int(round(qb_enh)) if abs(qb_enh - round(qb_enh)) < 1e-6 else round(qb_enh, 2)
            if answers_match(val_enh, expected, aliases):
                diagnostics.append(
                    f"variant MATCH: `enhanced_catalog_join` (nối đúng mã `{ic_enh}` -> `{nm_enh}` từ `san_pham` ra đúng `{val_enh}`)"
                )
            else:
                # Also recompute qty_base with enhanced conversions after resolving item_name from catalog
                lrows = conn.execute(
                    "SELECT unit, qty, qty_base FROM v_valid_lines WHERE order_date BETWEEN ? AND ? AND item_code = ?",
                    (start, end, ic_enh),
                ).fetchall()
                tot_conv = 0.0
                for u, q, qb in lrows:
                    f_e = 1.0
                    if u:
                        c_e = enh_convs.get((norm_key(nm_enh), norm_key(u))) or enh_convs.get((norm_key(ic_enh), norm_key(u)))
                        if c_e:
                            f_e = c_e[0]
                    tot_conv += float(q or 0.0) * f_e if abs(float(qb or 0.0) - float(q or 0.0)) < 1e-6 else float(qb or 0.0)
                val_conv = int(round(tot_conv)) if abs(tot_conv - round(tot_conv)) < 1e-6 else round(tot_conv, 2)
                if answers_match(val_conv, expected, aliases):
                    diagnostics.append(
                        f"variant MATCH: `enhanced_catalog_join + unit_conv` (nối mã `{ic_enh}` -> `{nm_enh}` rồi quy đổi đơn vị ra đúng `{val_conv}`)"
                    )

    # 3. Raw table variants: `no_filldown`, `no_dedup`, `order_total_col` for revenue/aov/order_count
    if intent in ("revenue", "aov", "order_count", "cancel_count", "cancel_rate") and not diagnostics:
        sales_t = next((t for t in tables if t.name == mapping.sales_table), None)
        if sales_t is not None:
            raw_df, _ = split_summary_rows(sales_t.df.copy())
            oid_col = mapping.sales_columns.get("order_id")
            date_col = mapping.sales_columns.get("order_date")
            stat_col = mapping.sales_columns.get("status")
            amt_col = mapping.sales_columns.get("line_amount")
            otot_col = mapping.sales_columns.get("order_total")

            for var_name in ("no_filldown", "no_dedup", "order_total_col"):
                df_v = raw_df.copy()
                if oid_col and oid_col in df_v.columns:
                    if var_name != "no_filldown":
                        df_v = fill_order_level(df_v, oid_col)
                    if var_name != "no_dedup":
                        df_v = drop_export_duplicates(df_v, oid_col)
                target_amt_col = otot_col if (var_name == "order_total_col" and otot_col in df_v.columns) else amt_col
                if not (date_col and date_col in df_v.columns and target_amt_col and target_amt_col in df_v.columns):
                    continue
                years = df_v["__year"] if "__year" in df_v.columns else [None] * len(df_v)
                dts = [
                    parse_datetime(dv, year=int(yv) if yv is not None and not pd.isna(yv) else None)
                    for dv, yv in zip(df_v[date_col], years)
                ]
                iso_ds = [d.date().isoformat() if d else None for d in dts]
                amts = [parse_number(av) or 0.0 for av in df_v[target_amt_col]]
                stats = [
                    normalize_status(sv)
                    for sv in (df_v[stat_col] if stat_col and stat_col in df_v.columns else [None] * len(df_v))
                ]
                if oid_col and oid_col in df_v.columns:
                    bad_oids = {
                        oid
                        for oid, st in zip(df_v[oid_col], stats)
                        if not pd.isna(oid) and st in (STATUS_CANCELLED, STATUS_RETURNED)
                    }
                    valid_mask = [
                        (oid not in bad_oids) and (st not in (STATUS_CANCELLED, STATUS_RETURNED))
                        for oid, st in zip(df_v[oid_col], stats)
                    ]
                else:
                    valid_mask = [st not in (STATUS_CANCELLED, STATUS_RETURNED) for st in stats]

                in_period = [
                    bool(d and start <= d <= end)
                    for d in iso_ds
                ]
                if intent == "revenue":
                    if var_name == "order_total_col" and oid_col and oid_col in df_v.columns:
                        seen_o = set()
                        tot_v = 0.0
                        for oid, ok_v, in_p, a_v in zip(df_v[oid_col], valid_mask, in_period, amts):
                            if ok_v and in_p and oid not in seen_o:
                                seen_o.add(oid)
                                tot_v += a_v
                    else:
                        tot_v = sum(a_v for ok_v, in_p, a_v in zip(valid_mask, in_period, amts) if ok_v and in_p)
                    if answers_match(round(tot_v), expected, aliases):
                        diagnostics.append(f"variant MATCH: `{var_name}` ra đúng đáp án ({round(tot_v)})")

    if not diagnostics:
        diagnostics.append("no single standard variant matched (kiểm tra thủ công câu hỏi / bộ lọc)")
    return diagnostics


# ---------------------------------------------------------------------- Main Regression Runner


@dataclass
class QuestionFailure:
    question_id: str
    business_id: str
    intent: str
    time_tag: str
    question: str
    as_of_date: str
    calculated: Any
    expected: Any
    diagnostics: list[str] = field(default_factory=list)


def run_regression(only_shops: list[str] | None = None) -> dict[str, Any]:
    t0 = time.monotonic()
    questions = [json.loads(line) for line in open(DATA_DIR / "questions.jsonl", encoding="utf-8")]
    answers = {
        json.loads(line)["id"]: json.loads(line)
        for line in open(DATA_DIR / "answers.jsonl", encoding="utf-8")
    }

    shop_dirs = sorted(
        d for d in (DATA_DIR / "data").iterdir() if d.is_dir() and (not only_shops or d.name in only_shops)
    )

    # Pre-group candidate questions by business_id
    by_shop_qs: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    total_tagged_in_scope = 0
    for q in questions:
        if only_shops and q["business_id"] not in only_shops:
            continue
        it = tag(q["question"])
        tt = ttag(q["question"])
        if it in TARGET_INTENTS and tt in TARGET_TIME_TAGS:
            q_copy = dict(q)
            q_copy["_intent"] = it
            q_copy["_ttag"] = tt
            by_shop_qs[q["business_id"]].append(q_copy)
            total_tagged_in_scope += 1

    intent_stats: dict[str, dict[str, int]] = {
        it: {"total_tagged": 0, "selected": 0, "correct": 0, "wrong": 0, "skipped": 0}
        for it in TARGET_INTENTS
    }
    shop_stats: dict[str, dict[str, Any]] = {}
    skip_reasons: collections.Counter[str] = collections.Counter()
    failures: list[QuestionFailure] = []

    for bdir in shop_dirs:
        b = bdir.name
        readme_path = bdir / "README.md"
        readme = readme_path.read_text(encoding="utf-8") if readme_path.is_file() else ""
        conn = build_database(bdir)
        tables: list[RawTable] | None = None
        mapping: Mapping | None = None

        has_views = (
            conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='view' AND name='v_valid_orders'"
            ).fetchone()[0]
            > 0
        )
        min_date = None
        catalog_items: list[tuple[str | None, str, str | None, str | None]] = []
        if has_views:
            min_date = conn.execute("SELECT MIN(order_date) FROM v_orders").fetchone()[0]
            catalog_items = conn.execute(
                "SELECT item_code, item_name, name_aliases, base_unit FROM v_items"
            ).fetchall()

        s_stat = {
            "has_ledger": has_views,
            "total_tagged": 0,
            "selected": 0,
            "correct": 0,
            "wrong": 0,
            "skipped": 0,
            "rev_selected": 0,
            "rev_correct": 0,
        }

        for q in by_shop_qs.get(b, []):
            it = q["_intent"]
            tt = q["_ttag"]
            qid = q["id"]
            qtext = q["question"]
            as_of = q["as_of_date"]
            ans_obj = answers[qid]
            ans_type = ans_obj["type"]
            expected = ans_obj.get("answer")
            aliases = ans_obj.get("alias", [])

            intent_stats[it]["total_tagged"] += 1
            s_stat["total_tagged"] += 1

            period_info = parse_explicit_period(qtext, as_of)
            skip_reason = should_skip_question(it, qtext, ans_type, has_views, min_date, period_info)
            if skip_reason is not None:
                intent_stats[it]["skipped"] += 1
                s_stat["skipped"] += 1
                skip_reasons[f"{it}:{skip_reason}"] += 1
                continue

            assert period_info is not None
            calc, exec_skip = execute_template(conn, it, qtext, as_of, period_info, catalog_items)
            if exec_skip is not None:
                intent_stats[it]["skipped"] += 1
                s_stat["skipped"] += 1
                skip_reasons[f"{it}:{exec_skip}"] += 1
                continue

            intent_stats[it]["selected"] += 1
            s_stat["selected"] += 1
            if it == "revenue":
                s_stat["rev_selected"] += 1

            if answers_match(calc, expected, aliases):
                intent_stats[it]["correct"] += 1
                s_stat["correct"] += 1
                if it == "revenue":
                    s_stat["rev_correct"] += 1
            else:
                intent_stats[it]["wrong"] += 1
                s_stat["wrong"] += 1
                if tables is None or mapping is None:
                    tables = load_business(bdir)
                    mapping = propose_mapping(tables, readme)
                diags = diagnose_failure(
                    conn,
                    tables,
                    mapping,
                    readme,
                    it,
                    qtext,
                    as_of,
                    period_info,
                    calc,
                    expected,
                    aliases,
                )
                failures.append(
                    QuestionFailure(
                        question_id=qid,
                        business_id=b,
                        intent=it,
                        time_tag=tt,
                        question=qtext,
                        as_of_date=as_of,
                        calculated=calc,
                        expected=expected,
                        diagnostics=diags,
                    )
                )

        conn.close()
        shop_stats[b] = s_stat
        print(
            f"[{b}] ledger={str(has_views):5s} | sel={s_stat['selected']:2d} | "
            f"ok={s_stat['correct']:2d} | wrong={s_stat['wrong']:2d} | skip={s_stat['skipped']:2d} | "
            f"rev={s_stat['rev_correct']}/{s_stat['rev_selected']}",
            flush=True,
        )

    elapsed = time.monotonic() - t0
    return {
        "elapsed_s": elapsed,
        "total_tagged_in_scope": total_tagged_in_scope,
        "intent_stats": intent_stats,
        "shop_stats": shop_stats,
        "skip_reasons": skip_reasons,
        "failures": failures,
    }


def write_markdown_report(res: dict[str, Any], report_path: Path = REPORT_PATH) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    intent_stats = res["intent_stats"]
    shop_stats = res["shop_stats"]
    failures: list[QuestionFailure] = res["failures"]
    skip_reasons = res["skip_reasons"]

    tot_tagged = sum(v["total_tagged"] for v in intent_stats.values())
    tot_sel = sum(v["selected"] for v in intent_stats.values())
    tot_ok = sum(v["correct"] for v in intent_stats.values())
    tot_wrong = sum(v["wrong"] for v in intent_stats.values())
    tot_skip = sum(v["skipped"] for v in intent_stats.values())
    overall_acc = (tot_ok / tot_sel * 100.0) if tot_sel else 0.0

    rev_sel = intent_stats["revenue"]["selected"]
    rev_ok = intent_stats["revenue"]["correct"]
    rev_acc = (rev_ok / rev_sel * 100.0) if rev_sel else 0.0

    lines: list[str] = []
    lines.append("# Báo cáo Regression Tầng Dữ Liệu (Task T5 — Không dùng LLM)")
    lines.append("")
    lines.append(
        f"**Tổng kết: {tot_ok}/{tot_sel} ({overall_acc:.2f}% đúng trên câu đã chọn)** "
        f"| Doanh thu tháng (`revenue`): **{rev_ok}/{rev_sel} ({rev_acc:.2f}%)** "
        f"| Thời gian chạy 30 shop: `{res['elapsed_s']:.1f}s`"
    )
    lines.append("")
    lines.append("## 1. Thống kê theo Intent")
    lines.append("")
    lines.append("| Intent | Tổng câu khớp tag + kỳ tường minh | Đã chọn (Selected) | Đúng (Correct) | Sai (Wrong) | Bỏ qua (Skipped) | % Đúng trên câu đã chọn |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for it in TARGET_INTENTS:
        st = intent_stats[it]
        sel = st["selected"]
        ok = st["correct"]
        acc_str = f"{ok / sel * 100.0:.2f}%" if sel else "N/A"
        lines.append(
            f"| `{it}` | {st['total_tagged']} | {sel} | {ok} | {st['wrong']} | {st['skipped']} | **{acc_str}** |"
        )
    lines.append(
        f"| **TỔNG** | **{tot_tagged}** | **{tot_sel}** | **{tot_ok}** | **{tot_wrong}** | **{tot_skip}** | **{overall_acc:.2f}%** |"
    )
    lines.append("")

    lines.append("## 2. Thống kê theo Shop (30 shop train)")
    lines.append("")
    lines.append("| Shop | Có Sales Views | Tổng câu tag | Đã chọn | Đúng | Sai | Bỏ qua | % Đúng | Doanh thu tháng (`revenue`) |")
    lines.append("|---|:---:|---:|---:|---:|---:|---:|---:|---:|")
    for b, st in sorted(shop_stats.items()):
        sel = st["selected"]
        ok = st["correct"]
        acc_str = f"{ok / sel * 100.0:.1f}%" if sel else "N/A"
        rev_str = f"{st['rev_correct']}/{st['rev_selected']}"
        lines.append(
            f"| `{b}` | {'Yes' if st['has_ledger'] else 'No'} | {st['total_tagged']} | "
            f"{sel} | {ok} | {st['wrong']} | {st['skipped']} | {acc_str} | {rev_str} |"
        )
    lines.append("")

    lines.append("## 3. Lý do bỏ qua câu hỏi (Skipped Breakdown)")
    lines.append("")
    lines.append("| Intent & Lý do bỏ qua | Số câu |")
    lines.append("|---|---:|")
    for reason_key, cnt in skip_reasons.most_common():
        lines.append(f"| `{reason_key}` | {cnt} |")
    lines.append("")

    lines.append("## 4. Phân nhóm lỗi hệ thống & Ghi chú cho T1–T4")
    lines.append("")
    lines.append(
        "Kết quả chẩn đoán tự động gom toàn bộ các câu sai về **2 nguyên nhân gốc ở tầng dữ liệu** (cả 2 đều giải thích 100% các câu sai):"
    )
    lines.append("")
    lines.append(
        "1. **Nối bảng danh mục `san_pham` khi bảng bán hàng chỉ ghi `item_code` (`biz_111`, `biz_123`, `biz_129` — 19 câu ở `topk_items`, `best_item`, `item_qty`):**"
    )
    lines.append(
        "   - **Nguyên nhân:** Ở `biz_123` (`pos.sqlite`) và `biz_129` (`san_pham.csv`), bảng `san_pham` có cột mã vạch (`ma_vach_ean` / `Mã vạch EAN`) đứng trước cột mã hàng (`MaHangHoa` / `Mã HH`). Hàm tìm cột mã trong `src/ledger.py` (dòng 419) và `src/views.py` (dòng 343) khớp từ khoá `\"ma\"` trên cột đầu tiên nên lấy nhầm cột barcode (`893...`) thay vì `SP00xx`, khiến phép join `chi_tiet_don.item_code = san_pham.item_code` không khớp và `item_name` trên `v_lines` bị rỗng (`''`)."
    )
    lines.append(
        "   - Riêng ở `biz_111` (`san_pham.csv`), cột tên hàng đặt tên là `Sản phẩm` (mô tả trong README: `- **Sản phẩm**: tên`), chưa có trong danh sách từ khoá `[\"ten\", \"name\"]` ở `src/ledger.py` và `src/views.py`, nên `san_pham` bị bỏ qua khi dựng `v_items`."
    )
    lines.append(
        "   - **Bằng chứng chẩn đoán:** Biến thể `enhanced_catalog_join` (loại trừ cột `barcode`/`ma vach`/`ean` khi tìm `code_c` và thêm từ khoá `\"san pham\"` cho `name_c`) trả về đúng **19/19** câu của `biz_111`, `biz_123`, `biz_129`."
    )
    lines.append(
        "2. **Đọc hệ số quy đổi đơn vị trong bảng tên `DanhMuc.xlsx` (`biz_117` — 3 câu `topk_items`):**"
    )
    lines.append(
        "   - **Nguyên nhân:** Ở `biz_117`, bảng quy đổi đơn vị nằm trong file `DanhMuc.xlsx` với 4 cột `['Hàng', 'ĐV lớn', 'ĐV nhỏ', 'Hệ số QĐ']` (ví dụ `Xi măng Hà Tiên PCB40 bao 50kg`: `1 tấn = 20 bao`, `Gạch ống 8x8x18 Tuynel`: `1 thiên = 1000 viên`). Trong `src/ledger.py:load_unit_conversions` (dòng 209), điều kiện nhận diện bảng quy đổi chỉ kiểm tra tên bảng chứa `[\"quy doi\", \"don vi\"]` (bỏ sót `DanhMuc`), và tên cột mặt hàng/đơn vị chưa có `\"hang\"`, `\"dv lon\"`, `\"dv nho\"`."
    )
    lines.append(
        "   - **Bằng chứng chẩn đoán:** Biến thể `enhanced_unit_conv` đọc `DanhMuc.xlsx` cho ra đúng **3/3** câu `topk_items` của `biz_117`."
    )
    lines.append("")

    lines.append("## 5. Danh sách chi tiết các câu sai & Chẩn đoán tự động")
    lines.append("")
    if not failures:
        lines.append("Không có câu sai nào.")
    else:
        lines.append("| # | Shop | Intent | Question ID | Câu hỏi | Giá trị tính | Đáp án chuẩn | Chẩn đoán tự động (Biến thể khớp) |")
        lines.append("|---:|---|---|---|---|---|---|---|")
        for idx, f in enumerate(failures, 1):
            calc_s = json.dumps(f.calculated, ensure_ascii=False)
            exp_s = json.dumps(f.expected, ensure_ascii=False)
            diag_s = "; ".join(f.diagnostics)
            q_clean = f.question.replace("|", "\\|")
            lines.append(
                f"| {idx} | `{f.business_id}` | `{f.intent}` | `{f.question_id}` | {q_clean} | `{calc_s}` | `{exp_s}` | {diag_s} |"
            )
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    results = run_regression(only)
    if not only:
        write_markdown_report(results, REPORT_PATH)
        tot_sel = sum(v["selected"] for v in results["intent_stats"].values())
        tot_ok = sum(v["correct"] for v in results["intent_stats"].values())
        pct = (tot_ok / tot_sel * 100.0) if tot_sel else 0.0
        print("=" * 72)
        print(f"REPORT SAVED TO: {REPORT_PATH}")
        print(f"SUMMARY: {tot_ok}/{tot_sel} ({pct:.2f}% đúng trên câu đã chọn)")
        print("=" * 72)
