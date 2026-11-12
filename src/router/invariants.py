"""Data-layer invariants per shop, computed at inference time (no gold needed).

A shop whose views look worse than ANY train shop on one of the HIGH_IS_BAD metrics is flagged `low_confidence`
(amount_ratio is a logged warning only); the router then
abstains for the whole shop (reason logged).  Thresholds: src/router/invariant_thresholds.json, derived once from the
30 train shops by scripts/data_invariants.py (worst value seen in train), never tuned on public data.

Metrics (all computed from the shop's own files through the data layer; nothing from questions or answers):
  amount_ratio        SUM(v_lines.line_amount) / SUM(raw line-amount column of the sales table)  (two-sided)
  unparsed_dates_pct  non-blank date cells that fail to parse even with the sheet's year / non-blank date cells
                      (per-question spans, not a shop flag; blank cells filled down by the ledger are not failures)
  status_unknown_pct  non-empty raw status/note cells that match no known status wording / non-empty cells
  unit_unconverted_pct lines whose unit differs from the base unit but kept factor 1.0 / ledger lines
  nonpositive_months  months inside the data range whose valid revenue is <= 0 (months with no order count)
  dup_pct             export-duplicate rows removed / raw sales rows
  no_ledger           1 when the sales views could not be built
"""
from __future__ import annotations

import calendar
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from ..cleaning import is_blank, load_business, norm_key, parse_datetime, parse_number, split_summary_rows
from ..ledger import _RE_GIAO, _RE_HUY, _RE_TRA, _RE_XONG, build_ledger
from ..mapping import propose_mapping
from ..views import item_match_key

THRESHOLDS_PATH = Path(__file__).with_name("invariant_thresholds.json")
HIGH_IS_BAD = ("unparsed_dates_pct", "status_unknown_pct", "unit_unconverted_pct", "nonpositive_months", "dup_pct")
# shop-level flags; unparsed dates are handled per question through `unparsed_spans` (see blocked_by_spans)
SHOP_FLAGS = ("status_unknown_pct", "unit_unconverted_pct", "nonpositive_months", "dup_pct")
_PAIR = re.compile(r"^\s*(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*$")


def _status_unknown_pct(tables, mapping) -> float | None:
    n = unknown = 0
    seen = set()
    for t_name, cols in ((mapping.sales_table, mapping.sales_columns), (mapping.orders_table, mapping.orders_columns)):
        col = (cols or {}).get("status")
        if not t_name or not col or (t_name, col) in seen:
            continue
        seen.add((t_name, col))
        t = next((x for x in tables if x.name == t_name), None)
        if t is None or col not in t.df.columns:
            continue
        for v in t.df[col].tolist():
            if is_blank(v):
                continue
            n += 1
            s = norm_key(v)
            if not any(rx.search(s) for rx in (_RE_HUY, _RE_TRA, _RE_GIAO, _RE_XONG)):
                unknown += 1
    return None if n == 0 else 100.0 * unknown / n


def _month_span(y: int, m: int) -> tuple[str, str]:
    return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def unparsed_spans(sales_df, date_col, data_range: tuple[str, str] | None) -> list[list[str]]:
    """Time spans the unparsed date cells can belong to (merged, ISO dates).

    A non-blank date cell the ledger could not parse is placed by the year of its sheet (`__year`): "d/m" gives the
    candidate month(s) of that year; a cell with no recognisable pattern falls back to the sheet's month, then to the
    sheet's year, then to the whole date range of the shop."""
    if not date_col or date_col not in sales_df.columns:
        return []
    cols = sales_df.columns
    years = sales_df["__year"].tolist() if "__year" in cols else [None] * len(sales_df)
    months = sales_df["__month"].tolist() if "__month" in cols else [None] * len(sales_df)
    spans: set[tuple[str, str]] = set()

    def num(v):
        try:
            return None if v is None or v != v else int(v)
        except (TypeError, ValueError):
            return None

    for v, y, sm in zip(sales_df[date_col].tolist(), years, months):
        if is_blank(v):
            continue
        y, sm = num(y), num(sm)
        if parse_datetime(v, year=y) is not None:
            continue
        m = _PAIR.match(str(v))
        if m and y:
            a, b = int(m.group(1)), int(m.group(2))
            cand = {x for x in (b, a) if 1 <= x <= 12} if a <= 12 else ({b} if 1 <= b <= 12 else set())
            if cand:
                spans.update(_month_span(y, c) for c in cand)
                continue
        if y and sm and 1 <= sm <= 12:
            spans.add(_month_span(y, sm))
        elif y:
            spans.add((f"{y:04d}-01-01", f"{y:04d}-12-31"))
        elif data_range:
            spans.add(data_range)
    merged: list[list[str]] = []
    for lo, hi in sorted(spans):
        if merged and lo <= (dt.date.fromisoformat(merged[-1][1]) + dt.timedelta(days=1)).isoformat():
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return merged


def blocked_by_spans(spans: list[list[str]], start: str, end: str) -> list[str] | None:
    """The first span intersecting [start, end] (inclusive ISO dates), else None."""
    for lo, hi in spans or []:
        if lo <= end and start <= hi:
            return [lo, hi]
    return None


def compute(shop_dir: Path | str, conn: Any) -> dict[str, Any]:
    """Metrics of one shop. `conn` = the shop's SQLite connection with the rulebook views (BusinessDB.connection)."""
    d = Path(shop_dir)
    out: dict[str, Any] = {k: None for k in ("amount_ratio",) + HIGH_IS_BAD}
    out["no_ledger"] = 0
    out["unparsed_spans"] = []
    has_views = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='v_lines'").fetchone())
    if not has_views:
        out["no_ledger"] = 1
        return out
    tables = load_business(d)
    readme = (d / "README.md").read_text(encoding="utf-8", errors="replace") if (d / "README.md").is_file() else ""
    mapping = propose_mapping(tables, readme)
    ledger, issues = build_ledger(tables, mapping, readme)
    sales = next((t for t in tables if t.name == mapping.sales_table), None)
    n_raw = len(sales.df) if sales is not None else 0
    if n_raw:
        # Cells that really fail to parse: non-blank date cells that parse_datetime cannot read even with the sheet's
        # year (rulebook section 8).  Blank cells are NOT failures: many books write the date on the first line of an
        # order only and the ledger fills it down (the ledger's own `unparsed_dates` counter counts those blanks).
        date_col = mapping.sales_columns.get("order_date")
        spans: list[list[str]] = []
        failed = nonblank = 0
        # hand-written summary rows ("Tổng cộng", notes) are not sales lines: the ledger drops them first (split_summary_rows)
        body, _ = split_summary_rows(sales.df.copy())
        if date_col and date_col in body.columns:
            years = body["__year"].tolist() if "__year" in body.columns else [None] * len(body)
            for v, y in zip(body[date_col].tolist(), years):
                if is_blank(v):
                    continue
                nonblank += 1
                try:
                    yy = int(y) if y is not None and y == y else None
                except (TypeError, ValueError):
                    yy = None
                failed += parse_datetime(v, year=yy) is None
        out["unparsed_dates_pct"] = 100.0 * failed / nonblank if nonblank else 0.0
        rng = conn.execute("SELECT MIN(order_date), MAX(order_date) FROM v_lines").fetchone()
        data_range = (rng[0], rng[1]) if rng and rng[0] else None
        if failed:
            spans = unparsed_spans(sales.df, date_col, data_range)
        # lines that still have no order date after the ledger filled orders down cannot be placed in time at all
        if len(ledger) and bool(ledger["order_date"].isna().any()):
            spans = spans + [list(data_range) if data_range else ["0001-01-01", "9999-12-31"]]
        out["unparsed_spans"] = spans
        out["dup_pct"] = 100.0 * issues.get("duplicate_rows_dropped", 0) / n_raw
        col = mapping.sales_columns.get("line_amount")
        if col and col in sales.df.columns:
            raw = sum(x for x in (parse_number(v) for v in sales.df[col].tolist()) if x is not None)
            view = conn.execute("SELECT COALESCE(SUM(line_amount), 0) FROM v_lines").fetchone()[0] or 0.0
            out["amount_ratio"] = (view / raw) if raw else None
    out["status_unknown_pct"] = _status_unknown_pct(tables, mapping)
    if len(ledger):
        u = ledger["unit"].map(item_match_key)
        b = ledger["base_unit"].map(item_match_key)
        bad = (u != "") & (b != "") & (u != b) & (ledger["factor"].fillna(1.0) == 1.0)
        out["unit_unconverted_pct"] = 100.0 * float(bad.mean())
    rows = conn.execute("SELECT SUBSTR(order_date,1,7) m, SUM(revenue) FROM v_valid_orders "
                        "WHERE order_date IS NOT NULL GROUP BY m").fetchall()
    rev = {m: (v or 0.0) for m, v in rows if m}
    if rev:
        lo, hi = min(rev), max(rev)
        y, m = int(lo[:4]), int(lo[5:7])
        ym_hi = (int(hi[:4]), int(hi[5:7]))
        nonpos = 0
        while (y, m) <= ym_hi:
            if rev.get(f"{y:04d}-{m:02d}", 0.0) <= 0:
                nonpos += 1
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        out["nonpositive_months"] = nonpos
    return out


def load_thresholds(path: Path | str | None = None) -> dict[str, Any]:
    return json.loads(Path(path or THRESHOLDS_PATH).read_text(encoding="utf-8"))


def warnings(metrics: dict[str, Any], thr: dict[str, Any]) -> list[str]:
    """Logged only, never a reason to abstain.

    amount_ratio = view total / raw column total.  It depends on how a file writes the invoice total (repeated on every
    line gives about 1/3) and on how many export duplicates are removed, so it does not reflect parse errors."""
    r = metrics.get("amount_ratio")
    if r is not None and "amount_ratio" in thr:
        lo, hi = thr["amount_ratio"]["min"], thr["amount_ratio"]["max"]
        if r < lo - 1e-9 or r > hi + 1e-9:
            return [f"amount_ratio={r:.4g} outside train [{lo:.4g},{hi:.4g}] (warning only)"]
    return []


def flags(metrics: dict[str, Any], thr: dict[str, Any]) -> list[str]:
    """Reasons for low_confidence (the whole shop abstains): unknown statuses, unconverted units or a
    month with revenue <= 0 beyond the train worst case (0), duplicate share above the train worst case.
    Unparsed dates do NOT flag the shop: questions whose period meets `unparsed_spans` abstain individually.
    A metric that could not be computed is not a reason by itself."""
    reasons = []
    if metrics.get("no_ledger"):
        return ["no_ledger"]
    for k in SHOP_FLAGS:
        v = metrics.get(k)
        if v is not None and k in thr and v > thr[k]["worst"] + 1e-9:
            reasons.append(f"{k}={v:.4g}>train_worst={thr[k]['worst']:.4g}")
    return reasons
