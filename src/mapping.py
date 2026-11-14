"""Automatic role mapping for business tables and columns.

Infers table roles and column roles from:
1. README column descriptions (section `## Cột trong ...` and `## Quy ước`)
2. POS column name conventions and patterns
3. Data types and distributions inferred from cell values
4. Arithmetic consistency constraints (qty * unit_price ~= line_amount)

Public API
----------
RoleAssignment              dataclass for a role mapped to a column with confidence and evidence
AuxiliaryTable              dataclass for auxiliary table role and join key
Mapping                     dataclass representing full mapping for a shop (JSON serializable)
parse_readme(text)          parse README markdown into {table_spec: {col: desc}}
role_from_description(desc) map a column description to (role, confidence)
role_from_column_name(col)  map a column name to (role, confidence)
propose_mapping(tables, readme) propose mapping for a business
llm_fallback(...)           hook returning None (for future LLM fallback)
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from src.cleaning import (
    META_COLS,
    RawTable,
    _family,
    infer_kinds,
    is_blank,
    norm_key,
    parse_datetime,
    parse_number,
    parse_qty,
)


@dataclass
class RoleAssignment:
    """Assignment of a semantic role to a column."""
    role: str
    column: str | None
    confidence: float
    evidence: str


@dataclass
class AuxiliaryTable:
    """Auxiliary table classification and join specification."""
    name: str
    role: str  # catalog, unit_conversion, customers, payments, purchases, inventory, price_history, expenses, delivery, orders, other
    join_key: str | None
    confidence: float
    evidence: str


@dataclass
class Mapping:
    """Full mapping for a business: sales ledger table, orders header table, and auxiliary tables."""
    sales_table: str
    sales_columns: dict[str, str | None]
    assignments: dict[str, RoleAssignment]
    orders_table: str | None = None
    orders_columns: dict[str, str | None] = field(default_factory=dict)
    orders_assignments: dict[str, RoleAssignment] = field(default_factory=dict)
    order_join_key: str | None = None
    auxiliary_tables: dict[str, AuxiliaryTable] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def get_column(self, role: str) -> str | None:
        """Get column name for a role, checking sales_table first, then orders_table."""
        col = self.sales_columns.get(role)
        if col is not None:
            return col
        if self.orders_columns:
            return self.orders_columns.get(role)
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize mapping to a JSON-serializable dictionary."""
        return {
            "sales_table": self.sales_table,
            "sales_columns": self.sales_columns,
            "assignments": {k: asdict(v) for k, v in self.assignments.items()},
            "orders_table": self.orders_table,
            "orders_columns": self.orders_columns,
            "orders_assignments": {k: asdict(v) for k, v in self.orders_assignments.items()},
            "order_join_key": self.order_join_key,
            "auxiliary_tables": {k: asdict(v) for k, v in self.auxiliary_tables.items()},
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Mapping:
        """Deserialize mapping from dictionary."""
        assignments = {k: RoleAssignment(**v) for k, v in d.get("assignments", {}).items()}
        orders_assignments = {k: RoleAssignment(**v) for k, v in d.get("orders_assignments", {}).items()}
        auxiliary_tables = {k: AuxiliaryTable(**v) for k, v in d.get("auxiliary_tables", {}).items()}
        return cls(
            sales_table=d["sales_table"],
            sales_columns=d.get("sales_columns", {}),
            assignments=assignments,
            orders_table=d.get("orders_table"),
            orders_columns=d.get("orders_columns", {}),
            orders_assignments=orders_assignments,
            order_join_key=d.get("order_join_key"),
            auxiliary_tables=auxiliary_tables,
            notes=d.get("notes", []),
        )


def _to_words(s: Any) -> str:
    """Normalize identifier converting CamelCase and symbols into space-separated lowercase words."""
    t = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", str(s))
    t = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", t)
    return norm_key(t)


# ---------------------------------------------------------------------- README parsing

def parse_readme(text: str) -> dict[str, dict[str, str]]:
    """Parse column descriptions from README markdown text.

    Extracts:
    1. Sections titled `## Cột trong <file/sheet>` with bullets `- **<cột>**: <mô tả>`
    2. Explicit table.column definitions in `## Quy ước` (e.g. `chi_tiet_don.TriGia là ...`)
    3. General conventions in `## Quy ước` (under key `__conventions__`)
    """
    if not text:
        return {}
    out: dict[str, dict[str, str]] = {}

    col_sec_re = re.compile(r"^##\s+Cột trong\s+(.+)$", re.M | re.I)
    bullet_re = re.compile(r"^\s*[-*]\s+\*\*([^*]+)\*\*:\s*(.+)$", re.M)

    matches = list(col_sec_re.finditer(text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        header_text = m.group(1).strip()
        body = text[start:end].split("##")[0]

        targets = set()
        clean_hdr = header_text.replace("`", "").replace('"', "").replace("'", "")

        sheet_match = re.search(r"sheet\s+([^,]+)", clean_hdr, re.I)
        sheet_name = sheet_match.group(1).strip() if sheet_match else None

        files_part = re.sub(r",?\s*sheet\s+[^,]+", "", clean_hdr, flags=re.I)
        raw_files = [f.strip() for f in files_part.split(",") if f.strip()]

        for rf in raw_files:
            stem = Path(rf).stem
            stem_clean = re.sub(r"<[^>]+>", "", stem).strip("_.- ")
            fam = _family(stem_clean)
            targets.add(rf)
            targets.add(stem)
            if stem_clean:
                targets.add(stem_clean)
                targets.add(fam)
            if sheet_name:
                targets.add(sheet_name)
                targets.add(f"{stem}/{sheet_name}")
                targets.add(f"{fam}/{sheet_name}")
                targets.add(f"{rf}[{sheet_name}]")

        cols: dict[str, str] = {}
        for bm in bullet_re.finditer(body):
            col_name = bm.group(1).strip()
            desc = bm.group(2).strip()
            cols[col_name] = desc

        for t in targets:
            if t not in out:
                out[t] = {}
            out[t].update(cols)

    # 2. Parse ## Quy ước
    if "## Quy ước" in text:
        qu_body = text.split("## Quy ước")[1].split("##")[0]
        # table.column là desc
        tbl_col_re = re.compile(r"[`\x27]?([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)[`\x27]?\s+là\s+([^;\n.]+)")
        for tm in tbl_col_re.finditer(qu_body):
            tbl, col, desc = tm.group(1).strip(), tm.group(2).strip(), tm.group(3).strip()
            if tbl not in out:
                out[tbl] = {}
            out[tbl][col] = desc

        conv: dict[str, str] = {}
        bold_re = re.compile(r"\*\*([^*]+)\*\*\s+là\s+([^;\n.]+)")
        for bm in bold_re.finditer(qu_body):
            c, desc = bm.group(1).strip(), bm.group(2).strip()
            conv[c] = desc
        if conv:
            out["__conventions__"] = conv

    return out


# ----------------------------------------------------------- Description vocabulary

DESC_RULES: list[tuple[str, str | None, float]] = [
    # Non-sales contexts to skip
    (r"phiếu nhập|nhập hàng|thẻ kho|phiếu thu", None, 0.0),
    # line_amount (rulebook §1: line-item revenue after line discount)
    (r"\b(thanh tien sau giam|thanh tien cua dong|tri gia cua dong|amount cua dong|thanh tien dong)\b", "line_amount", 1.0),
    (r"\bthanh tien cua dong voucher dung diem\b", "line_amount", 0.95),
    (r"\b(thanh tien|tri gia|amount|t tien)\b", "line_amount", 0.9),
    # order_total (order level, distinct from line_amount)
    (r"\b(tong thanh toan|khach phai tra cho ca don|khach can tra cho ca don|khach da tra cho ca don|tong sau giam gia|tong bill|phai thu|tong tien don|tong don|so khach phai tra cho ca don)\b", "order_total", 0.95),
    (r"\b(tong tien ca phieu|tong tien cua ca phieu)\b", "order_total", 0.9),
    (r"\b(tong tien hang cua ca don|tong tien hang cua don)\b", "order_total", 0.85),
    # order_id
    (r"\b(ma don|ma don hang|ma hoa don|ma hd|ma gd|ma phieu|ma bill|ma chung tu|so phieu|so hoa don|so chung tu|order id)\b", "order_id", 0.95),
    (r"\b(so thu tu don|stt don|so hoa don ghi o moi dong|cac dong cung stt la mot don)\b", "order_id", 0.9),
    # order_date
    (r"\b(ngay ban|ngay dat hang|ngay dat|ngay giao dich|ngay lap|ngay sua|ngay hd|ngay hoa don|thoi diem dat don|thoi gian dat don|thoi gian lap|thoi gian tao don)\b", "order_date", 0.95),
    (r"^(ngay|date)$", "order_date", 0.85),
    # order_time
    (r"\b(gio dat don|gio ban|gio tao don|gio lap)\b", "order_time", 0.9),
    (r"^(gio|time)$", "order_time", 0.8),
    # status
    (r"\b(trang thai don|trang thai don hang|trang thai xu ly|tinh trang don|status|tien do|tt don)\b", "status", 0.95),
    (r"^(ket qua|status|tinh trang)$", "status", 0.9),
    # item_name
    (r"\b(ten hang|ten san pham|ten mon|mat hang|hang ban|noi dung hang|ten hh)\b", "item_name", 0.95),
    (r"^(ten hang|hang ban|hang hoa|san pham|mat hang|noi dung|hang)$", "item_name", 0.9),
    # item_code
    (r"\b(ma hang|ma san pham|ma sp|ma hh|ma sku|id sp|ma barcode|ma vach)\b", "item_code", 0.95),
    # purchase_price (non-sales, do not map to sales unit_price)
    (r"\b(gia nhap|don gia nhap|gia mua)\b", "purchase_price", 0.95),
    # cost_price
    (r"\b(gia von|gia von mot don vi ban|gia von luc ban)\b", "cost_price", 0.95),
    # qty_base
    (r"\b(so luong da doi ra don vi co ban|quy ra dv le|sl quy doi|sl le|so luong le|sl co ban|don vi co ban|so luong ban lay tu lo don vi co ban|so luong thuc giao)\b", "qty_base", 0.95),
    # unit
    (r"\b(don vi tinh|dvt)\b|^(don vi|don vi co ban)$", "unit", 0.95),
    # qty
    (r"\b(so luong ban|sl ban|sluong|slg)\b", "qty", 0.95),
    (r"^(so luong|sl)$", "qty", 0.9),
    # unit_price
    (r"\b(don gia|gia ban|gia ban le|gia le|gia 1 dv|gia mot don vi|gia niem yet|gia ban hien tai)\b", "unit_price", 0.95),
    (r"^(gia|don gia)$", "unit_price", 0.85),
    # order_discount
    (r"\b(giam gia cua ca don|giam gia hd|chiet khau don|ck don|tien bot cho ca don|bot)\b", "order_discount", 0.9),
    # shipping_fee
    (r"\b(phi giao hang|phi giao|phi ship|phi van chuyen|tien ship)\b", "shipping_fee", 0.9),
    # vat
    (r"\b(thue gtgt|thue|vat)\b", "vat", 0.9),
    # customer_name
    (r"\b(ten khach|ten khach hang|khach hang mua|ho ten khach|ben mua|doi tac)\b", "customer_name", 0.95),
    (r"^(khach|khach hang)$", "customer_name", 0.9),
    # customer_code
    (r"\b(ma khach|ma khach hang|ma kh|customer id|ma nguoi mua|ma the)\b", "customer_code", 0.95),
    # staff
    (r"\b(nhan vien ban|nguoi ban|ma nv ban|ma nhan vien|tho lam phieu|ho ten tho)\b", "staff", 0.95),
    (r"^(tho)$", "staff", 0.9),
    # channel
    (r"\b(kenh ban|kenh dat|loai ban|nguon don|nguon)\b", "channel", 0.9),
    # payment_method
    (r"\b(hinh thuc thanh toan|phuong thuc thanh toan|pttt|loai tt|phuong thuc tt|thanh toan bang|tra bang)\b", "payment_method", 0.95),
    # note
    (r"\b(ghi chu cua don|ghi chu|luu y|note|dien giai)\b", "note", 0.85),
]


def role_from_description(desc: str) -> tuple[str, float] | None:
    """Infer column role and confidence from a description string."""
    if not desc:
        return None
    k = norm_key(desc)
    for pat, role, conf in DESC_RULES:
        if re.search(pat, k):
            if role is None:
                return None
            return role, conf
    return None


# ------------------------------------------------------------- Column name heuristics

COL_RULES: list[tuple[str, str, float]] = [
    # order_id
    (r"^(ma hoa don|ma hd|ma don hang|ma dh|ma don|ma giao dich|ma gd|ma phieu|ma bill|ma chung tu|so phieu|so hoa don|so hd|so giao dich|so don hang|so don|don so|so bill|order id|bill)$", "order_id", 0.9),
    (r"^(stt)$", "order_id", 0.7),  # multi-line tickets/orders, e.g. dev_014
    # order_date
    (r"^(ngay ban|ngay dat hang|ngay dat|ngay gd|ngay giao dich|ngay lap|ngay hd|ngay hoa don|ngay tao don|ngay sua|thoi gian|thoi gian lap|thoi gian tao|date)$", "order_date", 0.9),
    (r"^(ngay)$", "order_date", 0.85),
    # order_time
    (r"^(gio dat|gio ban|gio tao|gio lap|gio|time)$", "order_time", 0.85),
    # status
    (r"^(trang thai don hang|trang thai don|trang thai xu ly|trang thai giao|trang thai|status|tinh trang|ket qua|tien do|tt don|xu ly|ghi chu tt)$", "status", 0.9),
    # item_name
    (r"^(ten hang hoa|ten hang|ten mat hang|ten san pham|ten sp|ten mon|hang hoa|hang ban|san pham|mat hang|noi dung|chi tiet hang|item)$", "item_name", 0.85),
    (r"^(hang)$", "item_name", 0.8),
    # item_code
    (r"^(ma hang hoa|ma hang|ma san pham|ma sp|ma hh|ma sku|id sp|ma barcode|ma vach|barcode)$", "item_code", 0.9),
    # cost_price
    (r"^(gia von|gia von luc ban|gia von hien tai)$", "cost_price", 0.9),
    # unit
    (r"^(don vi tinh|donvitinh|dvt|don vi|donvi|unit|d vi)$", "unit", 0.9),
    # qty_base
    (r"^(quy ra dv le|sl quy doi|slquydoi|sl le|so luong le|so luong quy doi|sl co ban|sl thuc giao)$", "qty_base", 0.9),
    # qty
    (r"^(so luong ban|so luong|soluong|sl ban|slg|sluong|s l|so luong san pham)$", "qty", 0.85),
    (r"^(sl)$", "qty", 0.8),
    # unit_price
    (r"^(don gia|dongia|gia ban le|giabanle|gia ban|giaban|gia le|giale|gia 1 dv|gia san pham|gia niem yet|gia don vi|giadonvi)$", "unit_price", 0.85),
    (r"^(gia)$", "unit_price", 0.75),
    # line_amount
    (r"^(thanh tien sau giam|thanh tien d|thanh tien|thanhtien|tri gia|trigia|amount|t tien|ttien)$", "line_amount", 0.9),
    (r"^(tien|tri gia)$", "line_amount", 0.75),
    # order_total
    (r"^(tong sau giam gia|tong thanh toan|tongthanhtoan|tong bill|tong tien hang|khach phai tra|khach can tra|khach da tra|da tra|khach tra|phai thu|tong don)$", "order_total", 0.9),
    (r"^(tong tien|tongtien|tong)$", "order_total", 0.75),
    # order_discount
    (r"^(giam gia hd|giam gia ca don|tien bot|bot|ck)$", "order_discount", 0.85),
    (r"^(giam gia|chiet khau)$", "order_discount", 0.75),
    # shipping_fee
    (r"^(phi ship|phi van chuyen|phi giao|tien ship)$", "shipping_fee", 0.9),
    # vat
    (r"^(thue gtgt|thue|vat)$", "vat", 0.9),
    # customer_name
    (r"^(ten khach hang|ten khach|ten kh|khach hang|khach|doi tac|ben mua)$", "customer_name", 0.85),
    # customer_code
    (r"^(ma khach hang|ma khach|ma kh|customer id|so kh)$", "customer_code", 0.9),
    # staff
    (r"^(nhan vien ban|nguoi ban|ma nv ban|ma nhan vien|tho|tho lam phieu)$", "staff", 0.85),
    # channel
    (r"^(kenh ban|kenh dat|loai ban|nguon don|nguon|ban qua)$", "channel", 0.85),
    # payment_method
    (r"^(hinh thuc thanh toan|phuong thuc thanh toan|phuong thuc tt|pttt|httt|loai tt|thanh toan bang|tra bang)$", "payment_method", 0.9),
    # note
    (r"^(ghi chu|luu y|note|dien giai)$", "note", 0.8),
]


def role_from_column_name(col: str) -> tuple[str, float] | None:
    """Infer column role and confidence from a column name."""
    if not col:
        return None
    k = _to_words(col)
    for pat, role, conf in COL_RULES:
        if re.search(pat, k):
            return role, conf
    return None


# ------------------------------------------------------------- Arithmetic consistency

def check_arithmetic_consistency(
    df: pd.DataFrame,
    qty_col: str | None,
    price_col: str | None,
    amount_col: str | None,
    sample_size: int = 500,
) -> float:
    """Check how often qty * unit_price ~= line_amount (allowing for discounts)."""
    if not (qty_col and price_col and amount_col):
        return 0.0
    if qty_col not in df.columns or price_col not in df.columns or amount_col not in df.columns:
        return 0.0

    sub = df[[qty_col, price_col, amount_col]].dropna()
    if len(sub) == 0:
        return 0.0
    if len(sub) > sample_size:
        sub = sub.sample(sample_size, random_state=42)

    matches = 0
    total = 0
    for _, row in sub.iterrows():
        q_val, _ = parse_qty(row[qty_col])
        p_val = parse_number(row[price_col])
        a_val = parse_number(row[amount_col])
        if q_val is not None and p_val is not None and a_val is not None and q_val > 0 and p_val > 0 and a_val > 0:
            total += 1
            expected = q_val * p_val
            # Exact match or within 1 dong, or line amount <= expected (discount)
            if abs(expected - a_val) < 1.0 or (0.1 * expected <= a_val <= expected + 1.0):
                matches += 1

    if total == 0:
        return 0.0
    return matches / total


# ---------------------------------------------------------------- Mapping Proposal

def _find_table_readme(table_name: str, sources: list[str], parsed_readme: dict[str, dict[str, str]]) -> dict[str, str]:
    """Find column descriptions for a given table from parsed_readme."""
    # 1. Direct match on table_name
    if table_name in parsed_readme:
        return parsed_readme[table_name]

    # 2. Match on stem / family
    fam = _family(table_name)
    if fam in parsed_readme:
        return parsed_readme[fam]

    # 3. Match from sources
    for src in sources:
        base = src.split("[")[0].split(":")[0]
        stem = Path(base).stem
        if src in parsed_readme:
            return parsed_readme[src]
        if base in parsed_readme:
            return parsed_readme[base]
        if stem in parsed_readme:
            return parsed_readme[stem]
        fam_stem = _family(stem)
        if fam_stem in parsed_readme:
            return parsed_readme[fam_stem]
        if "[" in src:
            sheet = src.split("[")[1].rstrip("]")
            if sheet in parsed_readme:
                return parsed_readme[sheet]
            combo = f"{fam_stem}/{sheet}"
            if combo in parsed_readme:
                return parsed_readme[combo]
            combo2 = f"{stem}/{sheet}"
            if combo2 in parsed_readme:
                return parsed_readme[combo2]

    # 4. Normalized key match
    norm_tbl = norm_key(table_name)
    for k, v in parsed_readme.items():
        if k.startswith("__"):
            continue
        if norm_key(k) == norm_tbl:
            return v
    return {}


def find_time_column(
    df: pd.DataFrame, date_col: str, exclude: set[str] | None = None, sample_size: int = 400
) -> str | None:
    """Return a column holding the order's clock time, judged by content only.

    A candidate must parse as a datetime with a non-midnight time on most sampled rows and fall on the
    same calendar day as `date_col` on nearly all of them (so payment or delivery times on later days
    are not taken). Returns None when no column qualifies.
    """
    exclude = exclude or set()
    if date_col not in df.columns:
        return None
    sample = df.head(sample_size)
    base_dates = [parse_datetime(v) for v in sample[date_col]]
    best: tuple[float, str] | None = None
    for c in df.columns:
        if c == date_col or c in exclude or str(c).startswith("__"):
            continue
        n = n_dt = n_time = n_same = 0
        for v, bd in zip(sample[c], base_dates):
            if is_blank(v):
                continue
            n += 1
            d = parse_datetime(v)
            if d is None:
                continue
            n_dt += 1
            if d.hour or d.minute or d.second:
                n_time += 1
            if bd is not None and d.date() == bd.date():
                n_same += 1
        if n < 10 or n_dt / n < 0.9 or n_time / n_dt < 0.5 or n_same / n_dt < 0.95:
            continue
        score = n_same / n_dt + n_time / n_dt
        if best is None or score > best[0]:
            best = (score, c)
    return best[1] if best else None


def propose_mapping(tables: list[RawTable], readme: str | None = None) -> Mapping:
    """Propose table roles and column mapping for a business from tables and optional readme."""
    parsed_readme = parse_readme(readme) if readme else {}
    conventions = parsed_readme.get("__conventions__", {})

    # Step 1: Score tables to find sales_table (line-item ledger)
    scored_tables = []
    for t in tables:
        tbl_name_k = _to_words(t.name)
        desc_map = _find_table_readme(t.name, t.sources, parsed_readme)

        has_item = False
        has_qty = False
        has_price = False
        has_amount = False
        has_date = False
        has_order_id = False
        has_order_total = False

        for c in t.columns:
            c_desc = desc_map.get(c) or conventions.get(c)
            r_info = role_from_description(c_desc) if c_desc else None
            if not r_info:
                r_info = role_from_column_name(c)
            if r_info:
                role, _ = r_info
                if role in ("item_name", "item_code"):
                    has_item = True
                elif role in ("qty", "qty_base"):
                    has_qty = True
                elif role == "unit_price":
                    has_price = True
                elif role == "line_amount":
                    has_amount = True
                elif role == "order_date":
                    has_date = True
                elif role == "order_id":
                    has_order_id = True
                elif role == "order_total":
                    has_order_total = True

        score = 0
        if has_amount:
            score += 40
        if has_item:
            score += 20
        if has_qty:
            score += 20
        if has_price:
            score += 15
        if has_date:
            score += 15
        if has_order_id:
            score += 10
        if has_order_total and not has_amount:
            score += 15

        # Table name heuristics
        if any(k in tbl_name_k for k in ["chi tiet", "donhang chi tiet", "ban hang", "so ban hang", "so sua xe"]):
            score += 25
        if any(k in tbl_name_k for k in ["nhap", "ton", "quy doi", "danh muc", "so quy", "khach hang", "chi phi", "giao hang", "bao cao ca", "lo hang", "lich su gia", "bang gia", "so no", "thu may cu"]):
            score -= 50

        # Row count signals
        if len(t.df) > 1000:
            score += 10
        if len(t.df) > 10000:
            score += 10

        scored_tables.append((score, has_item, has_amount, has_order_total, t))

    scored_tables.sort(key=lambda x: (x[0], len(x[4].df)), reverse=True)
    best_table = scored_tables[0][4]

    # Check if there is a separate orders table (header table)
    orders_table_candidate = None
    for sc, h_item, h_amt, h_tot, cand_t in scored_tables:
        if cand_t.name == best_table.name:
            continue
        c_name_k = _to_words(cand_t.name)
        is_order_header = (
            any(k in c_name_k for k in ["hoa don", "don hang"]) and
            not re.search(r"\b(chi tiet|nhap|phong ban|theo lo|lo hang|lo|phieu thu|thanh toan|ghi tat|quy doi)\b", c_name_k)
        )
        if is_order_header:
            orders_table_candidate = cand_t
            break

    # Step 2: Assign roles for sales_table
    sales_t = best_table
    desc_map = _find_table_readme(sales_t.name, sales_t.sources, parsed_readme)
    sales_assignments: dict[str, RoleAssignment] = {}
    sales_columns: dict[str, str | None] = {}

    ROLES_LIST = [
        "order_id", "order_date", "order_time", "status", "item_name", "item_code",
        "unit", "qty", "qty_base", "unit_price", "line_amount", "order_total",
        "order_discount", "shipping_fee", "vat", "customer_name", "customer_code",
        "staff", "channel", "payment_method", "note"
    ]

    assigned_cols = set()

    # Pass 1: README descriptions (highest priority)
    for c in sales_t.columns:
        c_desc = desc_map.get(c) or conventions.get(c)
        if c_desc:
            r_info = role_from_description(c_desc)
            if r_info and r_info[0] in ROLES_LIST:
                role, conf = r_info
                if role not in sales_columns or conf > sales_assignments[role].confidence:
                    sales_columns[role] = c
                    sales_assignments[role] = RoleAssignment(role, c, conf, f"readme: '{c_desc}'")
                    assigned_cols.add(c)

    # Pass 2: Column name matching
    for c in sales_t.columns:
        if c in assigned_cols:
            continue
        r_info = role_from_column_name(c)
        if r_info:
            role, conf = r_info
            if role not in sales_columns:
                sales_columns[role] = c
                sales_assignments[role] = RoleAssignment(role, c, conf, f"heuristic: col_name '{c}'")
                assigned_cols.add(c)

    # Special handling: if order_date is missing, check date-like column
    if "order_date" not in sales_columns:
        for c in sales_t.columns:
            if c not in assigned_cols:
                if any(k in _to_words(c) for k in ["ngay", "date", "thoi gian"]):
                    sales_columns["order_date"] = c
                    sales_assignments["order_date"] = RoleAssignment("order_date", c, 0.8, f"heuristic: date keyword in '{c}'")
                    assigned_cols.add(c)
                    break

    # Special handling: if status not found, check note column
    if "status" not in sales_columns and "note" in sales_columns:
        note_col = sales_columns["note"]
        if note_col is not None and note_col in sales_t.df.columns:
            vals = sales_t.df[note_col].dropna().astype(str).head(100)
            if any(re.search(r"huy|cancel|tra|hoan|giao|xong", norm_key(v)) for v in vals):
                sales_columns["status"] = note_col
                sales_assignments["status"] = RoleAssignment("status", note_col, 0.75, f"heuristic: status embedded in note '{note_col}'")

    # Special handling for single-level repair/order table (e.g. dev_012):
    if "line_amount" not in sales_columns and "order_total" in sales_columns:
        tot_col = sales_columns["order_total"]
        sales_columns["line_amount"] = tot_col
        sales_assignments["line_amount"] = RoleAssignment("line_amount", tot_col, 0.8, f"fallback: single-level table using order_total '{tot_col}' as line_amount")

    # Step 3: Orders table (if separate)
    orders_table_name = None
    orders_columns: dict[str, str | None] = {}
    orders_assignments: dict[str, RoleAssignment] = {}
    order_join_key = None

    if orders_table_candidate is not None:
        orders_table_name = orders_table_candidate.name
        ord_desc_map = _find_table_readme(orders_table_name, orders_table_candidate.sources, parsed_readme)
        ord_assigned_cols = set()

        for c in orders_table_candidate.columns:
            c_desc = ord_desc_map.get(c) or conventions.get(c)
            r_info = role_from_description(c_desc) if c_desc else None
            if not r_info:
                r_info = role_from_column_name(c)
            if r_info:
                role, conf = r_info
                if role not in orders_columns:
                    orders_columns[role] = c
                    src_type = "readme" if c_desc else "heuristic"
                    orders_assignments[role] = RoleAssignment(role, c, conf, f"{src_type}: '{c_desc or c}'")
                    ord_assigned_cols.add(c)

        # Fallback date in orders table
        if "order_date" not in orders_columns:
            for c in orders_table_candidate.columns:
                if c not in ord_assigned_cols and any(k in _to_words(c) for k in ["ngay", "date", "thoi gian"]):
                    orders_columns["order_date"] = c
                    orders_assignments["order_date"] = RoleAssignment("order_date", c, 0.8, f"heuristic: date keyword in '{c}'")
                    break

        # Find join key
        sales_oid = sales_columns.get("order_id")
        ord_oid = orders_columns.get("order_id")
        if sales_oid:
            order_join_key = sales_oid
        elif ord_oid:
            order_join_key = ord_oid

    # Step 3b: order_time by content when no column was named like a time (e.g. "Thời gian tạo"
    # holding a datetime next to a date-only order_date column)
    if not sales_columns.get("order_time") and not orders_columns.get("order_time"):
        for tbl, cols in ((sales_t, sales_columns), (orders_table_candidate, orders_columns)):
            if tbl is None or not cols.get("order_date"):
                continue
            used = {c for c in cols.values() if c}
            t_col = find_time_column(tbl.df, cols["order_date"], exclude=used)
            if t_col:
                cols["order_time"] = t_col
                target = sales_assignments if cols is sales_columns else orders_assignments
                target["order_time"] = RoleAssignment(
                    "order_time", t_col, 0.8, f"content: datetime on the order date in '{t_col}'")
                break

    # Step 4: Arithmetic consistency check on sales_table
    q_col = sales_columns.get("qty") or sales_columns.get("qty_base")
    p_col = sales_columns.get("unit_price")
    a_col = sales_columns.get("line_amount")
    arith_score = check_arithmetic_consistency(sales_t.df, q_col, p_col, a_col)
    if arith_score >= 0.7:
        if "line_amount" in sales_assignments:
            sales_assignments["line_amount"].confidence = min(1.0, sales_assignments["line_amount"].confidence + 0.1)
            sales_assignments["line_amount"].evidence += f" | arithmetic qty*price~=amount ({arith_score:.1%})"

    # Fill None for unassigned roles in sales_columns
    for r in ROLES_LIST:
        if r not in sales_columns:
            sales_columns[r] = None
            sales_assignments[r] = RoleAssignment(r, None, 0.0, "unassigned")

    # Step 5: Auxiliary tables
    aux_tables: dict[str, AuxiliaryTable] = {}
    for t in tables:
        if t.name == sales_t.name:
            continue
        if orders_table_name and t.name == orders_table_name:
            aux_tables[t.name] = AuxiliaryTable(t.name, "orders", order_join_key, 0.95, "order_header_table")
            continue

        t_k = _to_words(t.name)
        role = "other"
        join_key = None
        conf = 0.8

        if any(k in t_k for k in ["quy doi", "don vi"]):
            role = "unit_conversion"
            join_key = sales_columns.get("item_code") or sales_columns.get("item_name")
        elif any(k in t_k for k in ["khach hang", "khach"]):
            role = "customers"
            join_key = sales_columns.get("customer_code") or sales_columns.get("customer_name")
        elif any(k in t_k for k in ["nhap", "phieu nhap"]):
            role = "purchases"
            join_key = None
        elif any(k in t_k for k in ["ton", "the kho"]):
            role = "inventory"
            join_key = sales_columns.get("item_code") or sales_columns.get("item_name")
        elif any(k in t_k for k in ["lich su gia", "bang gia"]):
            role = "price_history"
            join_key = sales_columns.get("item_code") or sales_columns.get("item_name")
        elif any(k in t_k for k in ["chi phi"]):
            role = "expenses"
            join_key = None
        elif any(k in t_k for k in ["thanh toan", "phieu thu", "so quy", "so no", "han no", "cong no", "thu may cu"]):
            role = "payments"
            join_key = sales_columns.get("order_id")
        elif any(k in t_k for k in ["giao hang", "van chuyen"]):
            role = "delivery"
            join_key = sales_columns.get("order_id")
        elif any(k in t_k for k in ["danh muc", "san pham", "hang hoa", "thuoc"]) or re.search(r"\bhang\b", t_k):
            role = "catalog"
            join_key = sales_columns.get("item_code") or sales_columns.get("item_name")

        aux_tables[t.name] = AuxiliaryTable(t.name, role, join_key, conf, f"name_heuristic: '{t.name}'")

    return Mapping(
        sales_table=sales_t.name,
        sales_columns=sales_columns,
        assignments=sales_assignments,
        orders_table=orders_table_name,
        orders_columns=orders_columns,
        orders_assignments=orders_assignments,
        order_join_key=order_join_key,
        auxiliary_tables=aux_tables,
    )


def llm_fallback(table_name: str, columns: list[str], readme: str | None = None) -> Mapping | None:
    """Hook for future LLM-based fallback when heuristic mapping has low confidence.

    Not called in Task T2; returns None.
    """
    return None
