"""Audit loading and cell-level parsing across all 44 shops (30 train + 14 public_test).

Usage:
    python scripts/analysis/load_audit.py [--out reports/load_audit.md] [biz_101 biz_102 ...]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from src.cleaning import (
    load_business,
    infer_kinds,
    parse_date,
    parse_datetime,
    parse_number,
    parse_qty,
    split_summary_rows,
    is_blank,
    META_COLS,
)


def audit_table(table, shop_id: str) -> dict[str, Any]:
    df = table.df
    cols = table.columns
    n_rows = len(df)
    n_cols = len(cols)

    # 1. col_* columns
    col_wildcard = [c for c in cols if c.startswith("col_")]

    # 2. empty columns
    empty_cols = []
    for c in cols:
        vals = df[c]
        if vals.isna().all() or all(is_blank(v) for v in vals):
            empty_cols.append(c)

    # 3. summary rows
    _, summary_removed = split_summary_rows(df)
    n_summary_rows = len(summary_removed)

    # 4. inferred kinds and parse check
    kinds = infer_kinds(df)
    parse_issues = []

    # get year hints if available
    years = df["__year"] if "__year" in df.columns else [None] * n_rows

    for c in cols:
        k_info = kinds.get(c)
        if not k_info:
            continue
        kind = k_info.kind
        if kind not in ("date", "datetime", "number", "qty"):
            continue

        non_blank_count = 0
        unparsed_count = 0
        unparsed_examples = []

        col_vals = df[c].tolist()
        for idx, (v, y) in enumerate(zip(col_vals, years)):
            if is_blank(v):
                continue
            non_blank_count += 1
            yr = int(y) if (y is not None and not pd.isna(y)) else None
            parsed = None
            if kind == "date":
                parsed = parse_date(v, year=yr)
            elif kind == "datetime":
                parsed = parse_datetime(v, year=yr)
            elif kind == "number":
                parsed = parse_number(v)
            elif kind == "qty":
                parsed = parse_qty(v)[0]

            if parsed is None:
                unparsed_count += 1
                s_repr = repr(v)
                if s_repr not in unparsed_examples and len(unparsed_examples) < 5:
                    unparsed_examples.append(s_repr)

        fail_rate = (unparsed_count / non_blank_count) if non_blank_count > 0 else 0.0
        if unparsed_count > 0:
            parse_issues.append({
                "column": c,
                "kind": kind,
                "non_blank": non_blank_count,
                "unparsed": unparsed_count,
                "fail_rate": fail_rate,
                "examples": unparsed_examples,
            })

    return {
        "shop": shop_id,
        "name": table.name,
        "rows": n_rows,
        "cols": n_cols,
        "sources": table.sources,
        "preamble": table.preamble,
        "col_wildcard": col_wildcard,
        "empty_cols": empty_cols,
        "summary_rows": n_summary_rows,
        "parse_issues": parse_issues,
    }


def run_audit(target_shops: list[str] | None = None, out_file: Path | None = None) -> list[dict[str, Any]]:
    from src.data_paths import public_test_dir, train_dir

    splits = [("train", train_dir() / "data"),
              ("public_test", public_test_dir() / "data")]

    shop_dirs: list[tuple[str, str, Path]] = []
    for split_name, base_dir in splits:
        if not base_dir.exists():
            continue
        for sdir in sorted(base_dir.iterdir()):
            if sdir.is_dir() and not sdir.name.startswith("."):
                if target_shops is None or sdir.name in target_shops:
                    shop_dirs.append((split_name, sdir.name, sdir))

    all_results = []
    total_t0 = time.time()

    print(f"Auditing {len(shop_dirs)} shops...")
    for split_name, shop_id, sdir in shop_dirs:
        t0 = time.time()
        try:
            tables = load_business(sdir)
            t_load = time.time() - t0
        except Exception as e:
            print(f"[{shop_id}] ERROR loading: {e}")
            all_results.append({
                "shop": shop_id,
                "split": split_name,
                "error": str(e),
                "load_time": time.time() - t0,
                "tables": [],
            })
            continue

        shop_entry = {
            "shop": shop_id,
            "split": split_name,
            "error": None,
            "load_time": t_load,
            "tables": [],
        }

        for t in tables:
            t_aud = audit_table(t, shop_id)
            shop_entry["tables"].append(t_aud)

        all_results.append(shop_entry)

        # Print brief console summary
        tbl_summary = ", ".join(f"{t['name']} ({t['rows']}r)" for t in shop_entry["tables"])
        col_w = sum(len(t["col_wildcard"]) for t in shop_entry["tables"])
        n_issues = sum(len(t["parse_issues"]) for t in shop_entry["tables"])
        sum_rows = sum(t["summary_rows"] for t in shop_entry["tables"])
        warn = []
        if col_w:
            warn.append(f"col_*={col_w}")
        if n_issues:
            warn.append(f"parse_issues={n_issues}")
        if sum_rows:
            warn.append(f"summary_rows={sum_rows}")
        warn_str = f" -- [{', '.join(warn)}]" if warn else ""
        print(f"[{split_name[:4]}] {shop_id:8s} | {t_load:5.2f}s | {tbl_summary}{warn_str}")

    total_time = time.time() - total_t0
    print(f"\nAudit completed in {total_time:.2f}s")

    if out_file:
        generate_markdown_report(all_results, out_file, total_time)
        print(f"Report written to {out_file}")

    return all_results


def generate_markdown_report(results: list[dict[str, Any]], out_path: Path, total_time: float) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total_shops = len(results)
    total_tables = sum(len(r["tables"]) for r in results)
    total_rows = sum(sum(t["rows"] for t in r["tables"]) for r in results)
    shops_with_col_wildcards = [r["shop"] for r in results if any(t["col_wildcard"] for t in r["tables"])]
    shops_with_parse_issues = [r["shop"] for r in results if any(t["parse_issues"] for t in r["tables"])]
    shops_with_summary = [r["shop"] for r in results if any(t["summary_rows"] > 0 for t in r["tables"])]

    lines = [
        "# Load and Parse Audit Report (44 Shops)",
        "",
        f"- **Total shops audited**: {total_shops}",
        f"- **Total tables loaded**: {total_tables}",
        f"- **Total rows**: {total_rows:,}",
        f"- **Total load time**: {total_time:.2f}s",
        f"- **Shops with `col_*` wildcard columns**: {len(shops_with_col_wildcards)} ({', '.join(shops_with_col_wildcards) or 'None'})",
        f"- **Shops with unparsed cells in typed columns**: {len(shops_with_parse_issues)} ({', '.join(shops_with_parse_issues) or 'None'})",
        f"- **Shops with summary rows detected**: {len(shops_with_summary)} ({', '.join(shops_with_summary) or 'None'})",
        "",
        "---",
        "",
        "## 1. Shop & Table Summary",
        "",
        "| Split | Shop | Load Time | Table | Rows | Cols | Sources | Summary Rows | Header/Wildcard Cols |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for r in results:
        split = r["split"]
        shop = r["shop"]
        lt = f"{r['load_time']:.2f}s"
        if r["error"]:
            lines.append(f"| {split} | {shop} | {lt} | **ERROR** | - | - | {r['error']} | - | - |")
            continue
        for t in r["tables"]:
            sources_str = f"{len(t['sources'])} files" if len(t["sources"]) > 2 else "<br>".join(t["sources"])
            wildcards = ", ".join(t["col_wildcard"]) if t["col_wildcard"] else "-"
            lines.append(
                f"| {split} | {shop} | {lt} | `{t['name']}` | {t['rows']:,} | {t['cols']} | {sources_str} | {t['summary_rows']} | {wildcards} |"
            )

    lines.extend([
        "",
        "---",
        "",
        "## 2. Header & Wildcard Columns (`col_*`) & Empty Columns",
        "",
        "| Shop | Table | Column Name | Issue Type | Preamble Detected |",
        "|---|---|---|---|---|",
    ])

    has_h_issues = False
    for r in results:
        for t in r["tables"]:
            preamble_str = "; ".join(t["preamble"])[:80] if t["preamble"] else "None"
            for c in t["col_wildcard"]:
                has_h_issues = True
                lines.append(f"| {r['shop']} | `{t['name']}` | `{c}` | Header missing (`col_*`) | {preamble_str} |")
            for c in t["empty_cols"]:
                has_h_issues = True
                lines.append(f"| {r['shop']} | `{t['name']}` | `{c}` | Completely empty column | {preamble_str} |")
    if not has_h_issues:
        lines.append("| - | - | None | No wildcard or empty columns found | - |")

    lines.extend([
        "",
        "---",
        "",
        "## 3. Unparsed Cells in Typed Columns (Date, DateTime, Number, Qty)",
        "",
        "| Shop | Table | Column | Kind | Non-blank | Unparsed | Fail % | Sample Unparsed Values |",
        "|---|---|---|---|---|---|---|---|",
    ])

    has_p_issues = False
    for r in results:
        for t in r["tables"]:
            for pi in t["parse_issues"]:
                has_p_issues = True
                ex_str = "<br>".join(pi["examples"][:5]).replace("|", "\\|")
                lines.append(
                    f"| {r['shop']} | `{t['name']}` | `{pi['column']}` | `{pi['kind']}` | {pi['non_blank']:,} | {pi['unparsed']:,} | {pi['fail_rate']:.2%} | {ex_str} |"
                )
    if not has_p_issues:
        lines.append("| - | - | None | - | - | - | 0% | None |")

    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "reports" / "load_audit.md")
    parser.add_argument("shops", nargs="*", default=None)
    args = parser.parse_args()

    target = args.shops if args.shops else None
    run_audit(target, args.out)
