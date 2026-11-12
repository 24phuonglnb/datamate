"""Fixed stratified sample: 20 questions per shop, stratified by gold answer type.

Deterministic (seed + sorted ids).  Writes eval/sample_ids.json.
    python -m eval.sample --train-dir data/train/train
"""
from __future__ import annotations

import argparse
import collections
import json
import random
from pathlib import Path

PER_SHOP = 20
SEED = 20261111
HERE = Path(__file__).parent


def _alloc(counts: dict[str, int], total: int) -> dict[str, int]:
    """Largest-remainder proportional allocation, capped by availability;
    'unanswerable' gets at least one slot when the shop has any."""
    n = sum(counts.values())
    raw = {t: total * c / n for t, c in counts.items()}
    out = {t: min(counts[t], int(v)) for t, v in raw.items()}
    if "unanswerable" in counts and out["unanswerable"] == 0:
        out["unanswerable"] = 1
    while sum(out.values()) > total:  # trim from the largest stratum
        t = max(out, key=lambda k: out[k])
        out[t] -= 1
    order = sorted(counts, key=lambda t: (raw[t] - int(raw[t])), reverse=True)
    i = 0
    while sum(out.values()) < total:
        t = order[i % len(order)]
        if out[t] < counts[t]:
            out[t] += 1
        i += 1
    return out


def build(train_dir: Path, per_shop: int = PER_SHOP, seed: int = SEED) -> dict:
    q = {}
    for line in (train_dir / "questions.jsonl").open(encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            q[r["id"]] = r
    gold = {}
    for line in (train_dir / "answers.jsonl").open(encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            gold[r["id"]] = r["type"]
    by_shop: dict[str, dict[str, list[str]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for qid, r in q.items():
        by_shop[r["business_id"]][gold[qid]].append(qid)
    rng = random.Random(seed)
    ids: list[str] = []
    per_shop_ids: dict[str, list[str]] = {}
    for shop in sorted(by_shop):
        strata = by_shop[shop]
        alloc = _alloc({t: len(v) for t, v in strata.items()}, per_shop)
        chosen: list[str] = []
        for t in sorted(strata):
            pool = sorted(strata[t])
            chosen += rng.sample(pool, alloc[t])
        chosen.sort()
        per_shop_ids[shop] = chosen
        ids += chosen
    return {"seed": seed, "per_shop": per_shop, "n": len(ids), "ids": ids, "by_shop": per_shop_ids}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-dir", default=str(HERE.parent / "data" / "train" / "train"))
    ap.add_argument("--out", default=str(HERE / "sample_ids.json"))
    a = ap.parse_args()
    res = build(Path(a.train_dir))
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", a.out, "n =", res["n"])


if __name__ == "__main__":
    main()
