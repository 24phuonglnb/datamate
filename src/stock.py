"""Stock views (rulebook §5, §6 pharmacy lots): `v_stock`, `v_lots`, `v_item_units`.

Sources, detected by keywords + content (never by shop or table name):

1. Stock report ("Báo cáo tồn kho", "Tồn kho"): one row per item with the closing quantity
   at the end of the data. On every train shop that has one it equals the movement-based stock.
2. Lot master ("Lô hàng": lot, item, expiry, qty in base unit) + lot sales ("Hoá đơn chi tiết lô":
   order, lot, qty, returned qty). Remaining per lot = qty in − qty on non-cancelled orders + returned
   qty. Verified 100% against the stock report on every train pharmacy that has both.

`v_stock` holds the state at the end of the data (`stock_date` = last order / receipt date), which is
"hôm nay" for every question in train/public. Shops with neither source get no stock views, so stock
questions stay unanswerable there.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any

import pandas as pd

from src.cleaning import META_COLS, RawTable, is_blank, nfc, norm_key, parse_date, parse_number, split_summary_rows

_LOT_COL_RE = re.compile(r"^(ma |so )?lo( hang| sx| san xuat)?$|\b(batch|lot)\b")
_EXPIRY_COL_RE = re.compile(r"\b(han su dung|han dung|hsd|het han|expiry|exp date)\b")
_RETURN_COL_RE = re.compile(r"\b(tra|tra lai|hoan tra|return(ed)?)\b")
_QTY_COL_RE = re.compile(r"\b(so luong|sl|qty|quantity|quy ra le)\b")
_STOCK_QTY_RE = re.compile(r"\b(ton cuoi( ky)?|ton thuc( te)?|ton kho|so luong ton|ton hien tai|ton)\b")
_STOCK_QTY_EXCLUDE = ("lon nhat", "toi thieu", "toi da", "dinh muc", "gia tri", "tien", "dau ky")
_SKIP_TABLE_WORDS = ("khach hang", "nha cung cap", "nhan vien", "chi phi", "thu chi", "quy doi", "cong no")


def _ck(col: Any) -> str:
    """Normalized column/table key with CamelCase split (`SoLuongTra` -> `so luong tra`)."""
    t = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", nfc(str(col)))  # SLQuyDoi -> SL QuyDoi
    return norm_key(re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", t))


def _id(v: Any) -> str:
    return "" if is_blank(v) else re.sub(r"\s+", "", nfc(v)).upper()


def _cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in META_COLS]


def _overlap(df: pd.DataFrame, col: str, wanted: set[str]) -> float:
    vals = {_id(v) for v in df[col].dropna().head(500)}
    vals.discard("")
    return len(vals & wanted) / len(vals) if vals else 0.0


def _best_col(df: pd.DataFrame, cols: list[str], wanted: set[str], min_overlap: float = 0.5) -> str | None:
    best, best_s = None, min_overlap
    for c in cols:
        s = _overlap(df, c, wanted)
        if s >= best_s:
            best, best_s = c, s
    return best


class _ItemIndex:
    """Map raw item codes / names / aliases to the canonical `v_items` row."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        from src.views import item_match_key

        self._mk = item_match_key
        self.by_code: dict[str, tuple[str | None, str, str | None]] = {}
        self.by_name: dict[str, tuple[str | None, str, str | None]] = {}
        for code, name, base, aliases in conn.execute(
            "SELECT item_code, item_name, base_unit, name_aliases FROM v_items"
        ):
            entry = (code, name, base)
            if code:
                self.by_code[_id(code)] = entry
            for nm in [name] + [p for p in (aliases or "").split(" | ") if p]:
                k = item_match_key(nm)
                if k and k not in self.by_name:
                    self.by_name[k] = entry
        self.codes = set(self.by_code)
        self.names = set(self.by_name)

    def lookup(self, code: Any = None, name: Any = None) -> tuple[str | None, str, str | None] | None:
        if not is_blank(code) and _id(code) in self.by_code:
            return self.by_code[_id(code)]
        if not is_blank(name):
            return self.by_name.get(self._mk(nfc(name)))
        return None

    def name_col(self, df: pd.DataFrame, cols: list[str]) -> str | None:
        best, best_s = None, 0.6
        for c in cols:
            vals = [v for v in df[c].dropna().head(300) if not is_blank(v)]
            if not vals:
                continue
            s = sum(self._mk(nfc(v)) in self.names for v in vals) / len(vals)
            if s >= best_s:
                best, best_s = c, s
        return best


def _unit_factor(units: dict[tuple[str, str], float], item_name: str, unit: Any, base_unit: str | None) -> float | None:
    if is_blank(unit):
        return 1.0
    uk = norm_key(unit)
    if base_unit and uk == norm_key(base_unit):
        return 1.0
    return units.get((item_name, uk))


# ---------------------------------------------------------------------------------------- units


def _display_unit(unit_key: str, item_name: str | None, base: str | None) -> str:
    """Conversion tables are keyed without accents ('vi'); recover the written form ('vỉ') from the item name."""
    if base and norm_key(base) == unit_key:
        return base
    for tok in re.split(r"[\s,;/()x]+", nfc(item_name or "")):
        if tok and norm_key(tok) == unit_key:
            return tok.lower()
    return unit_key


def build_item_units(conn: sqlite3.Connection, tables: list[RawTable], readme: str) -> pd.DataFrame:
    """One row per (item, unit) with `factor` to the base unit, from sales/purchase lines and conversion tables."""
    from src.ledger import load_unit_conversions

    rows: dict[tuple[str, str], dict[str, Any]] = {}

    def add(code: Any, name: str, unit: Any, factor: Any, base: Any) -> None:
        if is_blank(unit) or factor is None or pd.isna(factor) or float(factor) <= 0:
            return
        key = (name, norm_key(unit))
        if key not in rows:
            rows[key] = {"item_code": code, "item_name": name, "unit": nfc(str(unit)).strip(), "unit_key": key[1],
                         "factor": float(factor), "base_unit": base}

    for code, name, unit, factor, base in conn.execute(
        "SELECT item_code, item_name, unit, MAX(factor), MAX(base_unit) FROM v_lines GROUP BY item_name, unit"
    ):
        add(code, name, unit, factor, base)
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'v_purchase_lines'").fetchone():
        for code, name, unit, factor, base in conn.execute(
            "SELECT item_code, item_name, unit, MAX(factor), MAX(base_unit) FROM v_purchase_lines GROUP BY item_name, unit"
        ):
            add(code, name, unit, factor, base)

    conversions = load_unit_conversions(tables, readme)
    for code, name, base in conn.execute("SELECT item_code, item_name, base_unit FROM v_items"):
        for key_cand in (name, code):
            if not key_cand:
                continue
            kc = norm_key(key_cand)
            for (ik, uk), (factor, _b) in conversions.items():
                if ik == kc:
                    add(code, name, _display_unit(uk, name, base), factor, base)
        if base:
            add(code, name, base, 1.0, base)
    if not rows:
        return pd.DataFrame(columns=["item_code", "item_name", "unit", "unit_key", "factor", "base_unit"])
    return pd.DataFrame(list(rows.values())).sort_values(["item_name", "factor"]).reset_index(drop=True)


# ---------------------------------------------------------------------------------------- report


def _stock_report(tables: list[RawTable], idx: _ItemIndex, units: dict[tuple[str, str], float],
                  skip: set[str]) -> tuple[dict[str, float], str | None]:
    """Closing stock per canonical item name from a stock report table, in base units."""
    for t in tables:
        if t.name in skip:
            continue
        tk = _ck(t.name)
        if "ton" not in tk.split() or any(w in tk for w in _SKIP_TABLE_WORDS):
            continue
        df, _ = split_summary_rows(t.df)
        cols = _cols(df)
        if df.empty or any(_LOT_COL_RE.search(_ck(c)) for c in cols):
            continue
        qty_c = next((c for c in cols if _STOCK_QTY_RE.search(_ck(c))
                      and not any(x in _ck(c) for x in _STOCK_QTY_EXCLUDE)), None)
        if not qty_c:
            continue
        rest = [c for c in cols if c != qty_c]
        code_c = _best_col(df, rest, idx.codes)
        name_c = None if code_c else idx.name_col(df, rest)
        if not (code_c or name_c):
            continue
        unit_c = next((c for c in rest if c not in (code_c, name_c)
                       and re.search(r"\b(dvt|don vi( tinh)?|unit)\b", _ck(c))), None)
        out: dict[str, float] = {}
        n_rows = n_ok = 0
        for _, r in df.iterrows():
            q = parse_number(r[qty_c])
            if q is None:
                continue
            n_rows += 1
            hit = idx.lookup(code=r[code_c] if code_c else None, name=r[name_c] if name_c else None)
            if hit is None:
                continue
            _code, name, base = hit
            f = _unit_factor(units, name, r[unit_c] if unit_c else None, base)
            if f is None:
                continue
            out[name] = out.get(name, 0.0) + float(q) * f
            n_ok += 1
        if n_rows and n_ok / n_rows >= 0.8:
            return out, t.name
    return {}, None


# ---------------------------------------------------------------------------------------- stock card


_CARD_AFTER_RE = re.compile(r"\b(ton cuoi|ton sau|so du|balance|ton)\b")
_DATETIME_HDR_RE = re.compile(r"\b(ngay|thoi gian|gio|date|time|phat sinh)\b")


def _stock_card(tables: list[RawTable], idx: _ItemIndex, skip: set[str]) -> pd.DataFrame | None:
    """Stock card ("Thẻ kho"): one row per stock movement with the running balance after it."""
    from src.cleaning import parse_datetime

    for t in tables:
        if t.name in skip or any(w in _ck(t.name) for w in _SKIP_TABLE_WORDS):
            continue
        df, _ = split_summary_rows(t.df)
        cols = _cols(df)
        if df.empty or len(df) < 2:
            continue
        after_c = next((c for c in cols if _CARD_AFTER_RE.search(_ck(c))
                        and not any(x in _ck(c) for x in _STOCK_QTY_EXCLUDE)), None)
        if not after_c:
            continue
        rest = [c for c in cols if c != after_c]
        code_c = _best_col(df, rest, idx.codes)
        if not code_c:
            continue
        dt_c = next((c for c in rest if c != code_c and _DATETIME_HDR_RE.search(_ck(c))
                     and df[c].dropna().head(20).map(lambda v: parse_datetime(v) is not None).mean() >= 0.8), None)
        if not dt_c:
            continue
        chg_c = next((c for c in rest if c not in (code_c, dt_c) and _QTY_COL_RE.search(_ck(c))), None)
        out = pd.DataFrame({
            "raw_code": df[code_c],
            "moved_at": df[dt_c].map(lambda v: (d.isoformat(sep=" ") if (d := parse_datetime(v)) else None)),
            "qty_change": df[chg_c].map(parse_number) if chg_c else None,
            "stock_after": df[after_c].map(parse_number),
            "_ord": range(len(df)),
        }).dropna(subset=["moved_at", "stock_after"])
        if len(out) < 2:
            continue
        hits = out["raw_code"].map(lambda v: idx.lookup(code=v))
        out["item_code"] = hits.map(lambda h: h[0] if h else None)
        out["item_name"] = hits.map(lambda h: h[1] if h else None)
        out = out.dropna(subset=["item_name"])
        if out.empty:
            continue
        out["moved_date"] = out["moved_at"].str.slice(0, 10)
        out = out.sort_values(["moved_at", "_ord"]).drop(columns=["_ord", "raw_code"])
        out.attrs["table"] = t.name
        return out[["item_code", "item_name", "moved_at", "moved_date", "qty_change", "stock_after"]]
    return None


# ---------------------------------------------------------------------------------------- lots


_BASE_QTY_HINT = re.compile(r"\b(co ban|quy ra le|quy doi|le)\b")


def _lot_frames(tables: list[RawTable], idx: _ItemIndex, order_ids: set[str],
                units: dict[tuple[str, str], float]) -> tuple[pd.DataFrame | None, pd.DataFrame | None, list[str]]:
    """Find the lot master (lot, item, expiry, qty in) and lot sales (order, lot, qty, returned) tables.

    Several tables may carry lot + expiry (a lot list and a purchase detail): prefer the one whose
    quantity is stated in the base unit; otherwise convert by its unit column.
    """
    masters: list[tuple[int, str, pd.DataFrame]] = []
    sales = None
    sales_table: str | None = None
    for t in tables:
        if any(w in _ck(t.name) for w in _SKIP_TABLE_WORDS):
            continue
        df, _ = split_summary_rows(t.df)
        cols = _cols(df)
        if df.empty:
            continue
        lot_c = next((c for c in cols if _LOT_COL_RE.search(_ck(c))), None)
        if not lot_c:
            continue
        rest = [c for c in cols if c != lot_c]
        exp_c = next((c for c in rest if _EXPIRY_COL_RE.search(_ck(c))), None)
        ret_c = next((c for c in rest if _RETURN_COL_RE.search(_ck(c)) and _QTY_COL_RE.search(_ck(c))), None)
        qty_c = next((c for c in rest if c != ret_c and _QTY_COL_RE.search(_ck(c))
                      and not _RETURN_COL_RE.search(_ck(c))), None)
        if not qty_c:
            continue
        if exp_c:
            code_c = _best_col(df, [c for c in rest if c not in (exp_c, qty_c)], idx.codes)
            if not code_c:
                continue
            rid_c = next((c for c in rest if c not in (exp_c, qty_c, code_c)
                          and re.search(r"\b(ma|so) (nhap|phieu|don nhap)|phieu nhap|nhap hang", _ck(c))), None)
            unit_c = next((c for c in rest if c not in (exp_c, qty_c, code_c, rid_c)
                           and re.search(r"\b(dvt|don vi( tinh)?|unit)\b", _ck(c))), None)
            base_marked = bool(_BASE_QTY_HINT.search(_ck(qty_c)))

            def to_base(r: pd.Series) -> float | None:
                q = parse_number(r[qty_c])
                if q is None or base_marked or not unit_c:
                    return q
                hit = idx.lookup(code=r[code_c])
                f = _unit_factor(units, hit[1], r[unit_c], hit[2]) if hit else None
                return None if f is None else q * f

            m = pd.DataFrame({
                "lot": df[lot_c].map(_id),
                "raw_code": df[code_c],
                "expiry_date": df[exp_c].map(lambda v: (d.isoformat() if (d := parse_date(v)) else None)),
                "qty_in": df.apply(to_base, axis=1),
                "receipt_id": df[rid_c].map(lambda v: None if is_blank(v) else nfc(v).strip()) if rid_c else None,
            })
            m = m[(m["lot"] != "") & m["qty_in"].notna()]
            if not m.empty:
                score = (2 if base_marked else 0) + (1 if "lo" in _ck(t.name).split() else 0)
                masters.append((score, t.name, m))
        elif sales is None:
            ord_c = _best_col(df, [c for c in rest if c not in (qty_c, ret_c)], order_ids)
            if not ord_c:
                continue
            s = pd.DataFrame({
                "lot": df[lot_c].map(_id),
                "order_key": df[ord_c].map(_id),
                "qty": df[qty_c].map(parse_number).fillna(0.0),
                "qty_returned": df[ret_c].map(parse_number).fillna(0.0) if ret_c else 0.0,
            })
            s = s[s["lot"] != ""]
            if not s.empty:
                sales, sales_table = s, t.name
    master = None
    used: list[str] = []
    if masters:
        masters.sort(key=lambda x: -x[0])
        _score, m_name, master = masters[0]
        used.append(m_name)
    if sales_table:
        used.append(sales_table)
    return master, sales, used


def _build_lots(conn: sqlite3.Connection, master: pd.DataFrame, sales: pd.DataFrame | None, idx: _ItemIndex) -> pd.DataFrame:
    status = {_id(o): s for o, s in conn.execute("SELECT order_id, status FROM v_orders")}
    sold: dict[str, float] = {}
    returned: dict[str, float] = {}
    if sales is not None:
        for lot, ok, q, r in sales[["lot", "order_key", "qty", "qty_returned"]].itertuples(index=False):
            if status.get(ok) == "huy":
                continue
            sold[lot] = sold.get(lot, 0.0) + float(q)
            returned[lot] = returned.get(lot, 0.0) + float(r)

    has_p = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'v_purchases'").fetchone())
    rdate: dict[str, str] = {}
    cost: dict[tuple[str, str], float] = {}
    if has_p:
        rdate = {_id(r): d for r, d in conn.execute("SELECT receipt_id, receipt_date FROM v_purchases")}
        for r, nm, c in conn.execute(
            "SELECT receipt_id, item_name, SUM(line_amount) / NULLIF(SUM(qty_base), 0) "
            "FROM v_valid_purchase_lines GROUP BY receipt_id, item_name"
        ):
            if c is not None:
                cost[(_id(r), nm)] = float(c)

    rows = []
    agg = master.groupby("lot", as_index=False).agg(
        raw_code=("raw_code", "first"), expiry_date=("expiry_date", "first"),
        qty_in=("qty_in", "sum"), receipt_id=("receipt_id", "first"),
    )
    for lot, raw_code, exp, q_in, rid in agg.itertuples(index=False):
        hit = idx.lookup(code=raw_code)
        code, name, base = hit if hit else (None if is_blank(raw_code) else nfc(raw_code).strip(), None, None)
        s, r = sold.get(lot, 0.0), returned.get(lot, 0.0)
        rk = _id(rid) if rid else ""
        rows.append({
            "lot": lot, "item_code": code, "item_name": name, "base_unit": base,
            "receipt_id": rid, "receipt_date": rdate.get(rk), "expiry_date": exp,
            "qty_in": float(q_in), "qty_sold": s, "qty_returned": r, "qty_remaining": float(q_in) - s + r,
            "unit_cost_base": cost.get((rk, name)) if name else None,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------- views


def create_stock_views(conn: sqlite3.Connection, tables: list[RawTable], readme: str, skip_tables: set[str]) -> dict[str, Any]:
    """Create `v_item_units`, and `v_lots` / `v_stock` when the shop has stock data. Returns metadata."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'v_items'").fetchone():
        return {"has_stock": False, "reason": "no_ledger"}
    meta: dict[str, Any] = {"has_stock": False}

    units_df = build_item_units(conn, tables, readme)
    units_df.to_sql("item_units", conn, index=False, if_exists="replace")
    conn.executescript("DROP VIEW IF EXISTS v_item_units; CREATE VIEW v_item_units AS SELECT * FROM item_units;")
    units = {(r.item_name, norm_key(r.unit)): float(r.factor) for r in units_df.itertuples()}

    idx = _ItemIndex(conn)
    order_ids = {_id(o) for (o,) in conn.execute("SELECT order_id FROM v_orders")}
    master, sales, lot_tables = _lot_frames(tables, idx, order_ids, units)
    # Without a lot-sales table `qty_remaining` would equal `qty_in` (wrong), so no lots view then.
    lots_df = _build_lots(conn, master, sales, idx) if (master is not None and sales is not None) else pd.DataFrame()
    if not lots_df.empty:
        lots_df.to_sql("lots", conn, index=False, if_exists="replace")
        conn.executescript("DROP VIEW IF EXISTS v_lots; CREATE VIEW v_lots AS SELECT * FROM lots;")
        meta.update(has_lots=True, lot_tables=lot_tables, lots_have_sales=sales is not None)

    card = _stock_card(tables, idx, skip_tables | set(lot_tables))
    if card is not None:
        card.to_sql("stock_card", conn, index=False, if_exists="replace")
        conn.executescript("DROP VIEW IF EXISTS v_stock_card; CREATE VIEW v_stock_card AS SELECT rowid, * FROM stock_card;")
        meta.update(has_card=True, card_table=card.attrs.get("table"))

    report, report_table = _stock_report(tables, idx, units, skip_tables | set(lot_tables))
    if report:
        stock, source = report, "report"
        meta["report_table"] = report_table
    elif card is not None:
        stock = card.groupby("item_name")["stock_after"].last().to_dict()
        source = "card"
    elif not lots_df.empty and sales is not None:
        stock = lots_df.dropna(subset=["item_name"]).groupby("item_name")["qty_remaining"].sum().to_dict()
        source = "lots"
    else:
        return meta

    stock_date = conn.execute(
        "SELECT MAX(d) FROM (SELECT MAX(order_date) AS d FROM v_lines"
        + (" UNION ALL SELECT MAX(receipt_date) FROM v_purchase_lines" if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'v_purchase_lines'").fetchone() else "")
        + ")"
    ).fetchone()[0]
    rows = []
    for code, name, base, cost in conn.execute(
        "SELECT item_code, item_name, base_unit, cost_price FROM v_items WHERE is_service_fee = 0 OR is_service_fee IS NULL"
        if "is_service_fee" in [c[1] for c in conn.execute("PRAGMA table_info(v_items)")]
        else "SELECT item_code, item_name, base_unit, cost_price FROM v_items"
    ):
        if name not in stock:
            continue
        q = float(stock[name])
        rows.append({
            "item_code": code, "item_name": name, "base_unit": base, "stock_date": stock_date,
            "stock_qty_base": q, "cost_price": cost,
            "stock_value": q * float(cost) if (cost is not None and q > 0) else (0.0 if q <= 0 else None),
            "source": source,
        })
    if not rows:
        return meta
    pd.DataFrame(rows).to_sql("stock", conn, index=False, if_exists="replace")
    conn.executescript("DROP VIEW IF EXISTS v_stock; CREATE VIEW v_stock AS SELECT * FROM stock;")
    meta.update(has_stock=True, stock_source=source, stock_date=stock_date, n_items=len(rows))
    return meta


def stock_schema_lines(conn: sqlite3.Connection, meta: dict[str, Any]) -> list[str]:
    """Prompt section describing the stock views (kept short: the schema prompt has a char budget)."""
    out: list[str] = []
    n_units = conn.execute("SELECT COUNT(*) FROM item_units").fetchone()[0] if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name = 'item_units'").fetchone() else 0
    if meta.get("has_stock"):
        out += [
            "=== 1c. STOCK VIEWS (TỒN KHO; state at END of data = 'hôm nay' / 'cuối ngày hôm nay') ===",
            f"- VIEW `v_stock` (one row per item, stock_date={meta.get('stock_date')}): item_code, item_name, base_unit, "
            "stock_date, stock_qty_base (REAL, base unit), cost_price (catalog cost per base unit, may be NULL), "
            "stock_value (stock_qty_base*cost_price, only items still in stock; NULL if no cost), source. "
            "Stock value = SUM(stock_value) WHERE stock_qty_base > 0. Out of stock = stock_qty_base <= 0.",
        ]
    if meta.get("has_card"):
        out.append(
            "- VIEW `v_stock_card` (stock card, one row per movement): rowid (movement order), item_code, item_name, moved_at, "
            "moved_date, qty_change, stock_after (running balance in base unit). Stock at end of day X = stock_after of the "
            "LAST movement with moved_date <= X for that item (items with no movement yet have no stock): "
            "ORDER BY moved_at DESC, rowid DESC LIMIT 1 (rowid breaks ties between movements at the same moved_at)."
        )
    if meta.get("has_lots"):
        out.append(
            "- VIEW `v_lots` (one row per lot, pharmacy §6): lot, item_code, item_name, base_unit, receipt_id, receipt_date, "
            "expiry_date ('YYYY-MM-DD'), qty_in, qty_sold, qty_returned, qty_remaining (base unit, end of data), "
            "unit_cost_base (purchase price of that lot per base unit). Expiring in N days from D: "
            "qty_remaining > 0 AND expiry_date BETWEEN D AND date(D,'+N day'); nearest lot: qty_remaining > 0 AND expiry_date >= D ORDER BY expiry_date."
        )
    if n_units:
        out.append(
            "- VIEW `v_item_units`: item_code, item_name, unit, unit_key (unaccented, for matching), factor (base units per 1 unit), base_unit. "
            "Stock in a large unit = [CAST(stock_qty_base / factor AS INT), stock_qty_base % factor] (remainder in BASE unit, §5)."
        )
    return out
