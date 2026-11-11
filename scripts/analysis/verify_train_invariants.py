"""Verify invariants across all 30 train shops.

Runs propose_mapping + build_ledger + verify_invariants for each shop,
reports pass/fail/NA for all 5 invariants, and logs any failures with explanation.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from src.cleaning import load_business
from src.ledger import build_ledger, verify_invariants
from src.mapping import propose_mapping

DATA = ROOT / "data" / "train" / "data"

INVARIANTS = [
    "single_date_and_status_per_order",
    "arithmetic_line_amount",
    "constant_unit_factor",
    "cancellation_rate",
    "date_range_matches_readme",
]


def main():
    biz_dirs = sorted([p for p in DATA.iterdir() if p.is_dir() and p.name.startswith("biz_")])
    print(f"Evaluating invariants on {len(biz_dirs)} train shops...")

    results = []
    inv_pass_counts = {inv: 0 for inv in INVARIANTS}
    inv_total_counts = {inv: 0 for inv in INVARIANTS}
    shop_pass_all = 0

    print(f"{'Shop':<10} | {'Rows':<8} | {'Date/Stat':<9} | {'Arith':<7} | {'Unit':<7} | {'Cancel':<7} | {'DateRg':<7} | {'Pass/Tot':<8}")
    print("-" * 80)

    for b_dir in biz_dirs:
        b_name = b_dir.name
        readme_file = b_dir / "README.md"
        readme = readme_file.read_text() if readme_file.exists() else ""

        try:
            tables = load_business(b_dir)
            mapping = propose_mapping(tables, readme)
            ledger_df, issues = build_ledger(tables, mapping, readme)
            invs = verify_invariants(ledger_df, readme)
        except Exception as e:
            print(f"{b_name:<10} | ERROR: {e}")
            continue

        row_res = {"shop": b_name, "rows": len(ledger_df)}
        n_pass = 0
        n_eval = 0

        status_display = []
        for inv in INVARIANTS:
            st = invs.get(inv, {}).get("status", "N/A")
            row_res[inv] = invs.get(inv, {})
            if st == "PASS":
                inv_pass_counts[inv] += 1
                inv_total_counts[inv] += 1
                n_pass += 1
                n_eval += 1
                status_display.append("PASS")
            elif st == "FAIL":
                inv_total_counts[inv] += 1
                n_eval += 1
                status_display.append("FAIL")
            else:
                status_display.append("N/A")

        if n_pass == n_eval and n_eval > 0:
            shop_pass_all += 1

        print(
            f"{b_name:<10} | {len(ledger_df):<8} | "
            f"{status_display[0]:<9} | {status_display[1]:<7} | {status_display[2]:<7} | "
            f"{status_display[3]:<7} | {status_display[4]:<7} | {n_pass}/{n_eval}"
        )
        sys.stdout.flush()
        results.append(row_res)

    print("=" * 80)
    print(f"OVERALL SUMMARY ({len(results)} shops evaluated):")
    print(f"Shops passing 100% evaluated invariants: {shop_pass_all}/{len(results)} ({shop_pass_all / len(results):.1%})")
    print("-" * 80)
    for inv in INVARIANTS:
        p = inv_pass_counts[inv]
        t = inv_total_counts[inv]
        pct = (p / t * 100) if t > 0 else 0
        print(f"  {inv:<35}: {p}/{t} ({pct:.1f}%)")

    # Save detailed JSON report
    report_path = ROOT / "reports" / "train_invariants_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nDetailed report saved to {report_path}")


if __name__ == "__main__":
    main()
