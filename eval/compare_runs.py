"""Compare two harness runs on the same question set.

    python -m eval.compare_runs A.per_question.jsonl B.per_question.jsonl [--show 10]

Prints PA of each run, |dPA|, and the number of questions whose submitted answer differs
(answer type or value), split into: both correct, both wrong, only-A-correct, only-B-correct.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read(p: str) -> dict[str, dict]:
    return {r["id"]: r for r in map(json.loads, Path(p).read_text(encoding="utf-8").splitlines()) if r.get("id")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--show", type=int, default=0, help="print this many differing questions")
    x = ap.parse_args()
    A, B = _read(x.a), _read(x.b)
    ids = sorted(set(A) & set(B))
    if not ids:
        raise SystemExit("no common question ids")
    pa = lambda R: sum(R[i]["score"] for i in ids) / len(ids)  # noqa: E731
    diff = [i for i in ids if json.dumps(A[i]["answer"], sort_keys=True, ensure_ascii=False)
            != json.dumps(B[i]["answer"], sort_keys=True, ensure_ascii=False)]
    only_a = [i for i in ids if A[i]["score"] > B[i]["score"]]
    only_b = [i for i in ids if B[i]["score"] > A[i]["score"]]
    print(f"common questions : {len(ids)} (A={len(A)}, B={len(B)})")
    print(f"PA A = {pa(A):+.4f}   PA B = {pa(B):+.4f}   |dPA| = {abs(pa(A) - pa(B)):.4f}")
    print(f"answers differing: {len(diff)}   A scores higher on {len(only_a)}, B on {len(only_b)}")
    for i in diff[: x.show]:
        print(f"- {i}: gold={A[i].get('gold')!r}\n    A={A[i]['answer']!r} ({A[i]['score']})\n    B={B[i]['answer']!r} ({B[i]['score']})")


if __name__ == "__main__":
    main()
