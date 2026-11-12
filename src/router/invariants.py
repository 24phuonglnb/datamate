"""Data-layer invariants per shop, computed at inference time (no gold needed).

A shop whose views look worse than ANY train shop on one of the metrics is flagged `low_confidence`; the router then
abstains for the whole shop (reason logged).  Thresholds: src/router/invariant_thresholds.json, derived once from the
30 train shops by scripts/data_invariants.py (worst value seen in train), never tuned on public data.

Metrics (all computed from the shop's own files through the data layer; nothing from questions or answers):
  amount_ratio        SUM(v_lines.line_amount) / SUM(raw line-amount column of the sales table)  (two-sided)
  unparsed_dates_pct  rows whose date could not be parsed / raw sales rows
  status_unknown_pct  non-empty raw status/note cells that match no known status wording / non-empty cells
  unit_unconverted_pct lines whose unit differs from the base unit but kept factor 1.0 / ledger lines
  nonpositive_months  months inside the data range whose valid revenue is <= 0 (months with no order count)
  dup_pct             export-duplicate rows removed / raw sales rows
  no_ledger           1 when the sales views could not be built
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from ..cleaning import is_blank, load_business, norm_key, parse_number
from ..ledger import _RE_GIAO, _RE_HUY, _RE_TRA, _RE_XONG, build_ledger
from ..mapping import propose_mapping
from ..views import item_match_key

THRESHOLDS_PATH = Path(__file__).with_name("invariant_thresholds.json")
HIGH_IS_BAD = ("unparsed_dates_pct", "status_unknown_pct", "unit_unconverted_pct", "nonpositive_months", "dup_pct")


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


def compute(shop_dir: Path | str, conn: Any) -> dict[str, Any]:
    """Metrics of one shop. `conn` = the shop's SQLite connection with the rulebook views (BusinessDB.connection)."""
    d = Path(shop_dir)
    out: dict[str, Any] = {k: None for k in ("amount_ratio",) + HIGH_IS_BAD}
    out["no_ledger"] = 0
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
        out["unparsed_dates_pct"] = 100.0 * issues.get("unparsed_dates", 0) / n_raw
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


def flags(metrics: dict[str, Any], thr: dict[str, Any]) -> list[str]:
    """Reasons for low_confidence; a metric that could not be computed is not a reason by itself."""
    reasons = []
    if metrics.get("no_ledger"):
        return ["no_ledger"]
    for k in HIGH_IS_BAD:
        v = metrics.get(k)
        if v is not None and k in thr and v > thr[k]["worst"] + 1e-9:
            reasons.append(f"{k}={v:.4g}>train_worst={thr[k]['worst']:.4g}")
    r = metrics.get("amount_ratio")
    if r is not None and "amount_ratio" in thr:
        lo, hi = thr["amount_ratio"]["min"], thr["amount_ratio"]["max"]
        if r < lo - 1e-9 or r > hi + 1e-9:
            reasons.append(f"amount_ratio={r:.4g} outside train [{lo:.4g},{hi:.4g}]")
    return reasons
