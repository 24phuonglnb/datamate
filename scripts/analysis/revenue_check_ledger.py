"""Verify monthly revenue on benchmark shops using automatic pipeline: propose_mapping + build_ledger.

NO hand mapping dictionary is used.
Every shop is processed through:
    1. load_business(dir)
    2. propose_mapping(tables, readme)
    3. build_ledger(tables, mapping, readme)
    4. Monthly revenue calculation according to Rulebook §1:
       - Status not in ('huy', 'tra_hang') (completed or shipping)
       - order_date.year == y and order_date.month == m and order_date <= as_of_date
       - sum(line_amount)

Usage:
    python scripts/analysis/revenue_check_ledger.py [biz_101 biz_102 ...]
"""
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
from src.cleaning import load_business, strip_accents
from src.ledger import build_ledger, verify_invariants
from src.mapping import propose_mapping

DATA = ROOT / "data" / "train"
BENCHMARK_SHOPS = [
    "biz_101",
    "biz_102",
    "biz_103",
    "biz_105",
    "biz_107",
    "biz_112",
    "biz_114",
    "biz_117",
]


def deacc(s: str) -> str:
    return strip_accents(s).lower()


def run_benchmark(shops: list[str] | None = None):
    if not shops:
        shops = BENCHMARK_SHOPS

    questions = [json.loads(line) for line in open(DATA / "questions.jsonl")]
    answers = {json.loads(line)["id"]: json.loads(line) for line in open(DATA / "answers.jsonl")}

    total_hit = 0
    total_q = 0

    print("=" * 70)
    print("RUNNING MONTHLY REVENUE BENCHMARK WITH AUTOMATIC BUILD_LEDGER PIPELINE")
    print("=" * 70)

    for b in shops:
        biz_dir = DATA / "data" / b
        if not biz_dir.exists():
            continue

        readme_file = biz_dir / "README.md"
        readme = readme_file.read_text() if readme_file.exists() else ""

        # Step 1 & 2: Load and propose mapping automatically
        tables = load_business(biz_dir)
        mapping = propose_mapping(tables, readme)

        # Step 3: Build standard SalesLedger
        ledger_df, issues = build_ledger(tables, mapping, readme)
        invs = verify_invariants(ledger_df, readme)

        # Filter valid revenue rows according to Rulebook §1:
        # Non-cancelled, non-returned orders (including shipping)
        rev_df = ledger_df[~ledger_df["status"].isin(["huy", "tra_hang"])].copy()

        # Date column as timestamp for comparison
        rev_df["_dt"] = pd.to_datetime(rev_df["order_date"])

        hit = 0
        tot = 0
        misses = []

        for q in questions:
            if q["business_id"] != b or answers[q["id"]]["type"] != "number":
                continue

            s = deacc(q["question"])
            m = re.search(r"thang (\d{1,2})(?:/| nam )(\d{4})", s)
            if not m or not re.search(r"doanh thu|dthu", s):
                continue
            if re.search(
                r"nhom|khach|\bdon\b|\bca\b|nhan vien|tra bang|so voi|%|phan tram|ngay|hoat chat|ke don|size|trung binh|binh quan|moi|quy|mat hang|mon |ban chay|top|doanh thu cua (?!cua hang)|dthu cua (?!cua hang)",
                s,
            ):
                continue

            mo, y = int(m.group(1)), int(m.group(2))
            asof = pd.Timestamp(q["as_of_date"])
            tot += 1

            matched_lines = rev_df[
                (rev_df["_dt"].dt.year == y)
                & (rev_df["_dt"].dt.month == mo)
                & (rev_df["_dt"] <= asof)
            ]
            v = round(matched_lines["line_amount"].sum())
            expected = answers[q["id"]]["answer"]

            if v == expected:
                hit += 1
            else:
                misses.append((q["id"], q["question"][:65], v, expected))

        total_hit += hit
        total_q += tot

        print(
            f"{b}: questions {tot:2d}, hit {hit:2d}/{tot:2d} | "
            f"rows: {len(ledger_df):6d}, unparsed_dates: {issues['unparsed_dates']}, "
            f"unit_mismatches: {issues['unit_conv_mismatches']}, "
            f"invs: {sum(v.get('status') == 'PASS' for v in invs.values())}/{len(invs)} PASS",
            flush=True,
        )
        for qid, qtext, calc, ans in misses:
            print(f"    MISS [{qid}] {qtext} -> calc: {calc}, expected: {ans}")

    print("=" * 70)
    print(f"TOTAL BENCHMARK SCORE: {total_hit}/{total_q}")
    print("=" * 70)
    return total_hit, total_q


if __name__ == "__main__":
    target_shops = sys.argv[1:] if len(sys.argv) > 1 else None
    run_benchmark(target_shops)
