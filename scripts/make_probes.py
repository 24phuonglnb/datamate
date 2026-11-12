"""Leaderboard probe files from a router submission (no GPU, no gold).

    python scripts/make_probes.py --submission v1.jsonl --meta v1_meta.jsonl --outdir <dir> --date YYYY-MM-DD [--flagged dev_012 ...]

Writes probe_G1/G2 (answers of one intent group kept as in the submission, everything else abstain; 1000 lines each)
and, with --flagged, probe_v1_minus_flagged (submission with every flagged shop abstained).  G3 = the rest, to be inferred.
Groups: G1 revenue-based (revenue, aov, best_day), G2 order counts (order_count, cancel_count, cancel_rate),
G3 comparisons / rankings / item (rev_change_pct, topk_items, best_item, item_qty).  Do not commit the outputs.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

GROUPS = {"G1": ("revenue", "aov", "best_day"),
          "G2": ("order_count", "cancel_count", "cancel_rate"),
          "G3": ("rev_change_pct", "topk_items", "best_item", "item_qty")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--flagged", nargs="*", default=[])
    a = ap.parse_args()
    sub = [json.loads(l) for l in open(a.submission, encoding="utf-8") if l.strip()]
    meta = {m["id"]: m for m in map(json.loads, open(a.meta, encoding="utf-8")) if m}
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    answered = [s for s in sub if s["type"] != "abstain"]
    assert len(sub) == len({s["id"] for s in sub}) == 1000

    def write(name, keep):
        lines = [s if keep(s) else {"id": s["id"], "type": "abstain"} for s in sub]
        (out / name).write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n", encoding="utf-8")
        return sum(1 for s in sub if keep(s) and s["type"] != "abstain")

    rows = []
    for g, intents in GROUPS.items():
        member = lambda s, intents=intents: s["type"] != "abstain" and meta[s["id"]]["intent"] in intents  # noqa: E731
        n = sum(1 for s in sub if member(s))
        per = collections.Counter(meta[s["id"]]["business_id"] for s in sub if member(s))
        by_int = collections.Counter(meta[s["id"]]["intent"] for s in sub if member(s))
        rows.append((g, intents, n, per, by_int))
        if g in ("G1", "G2"):
            write(f"probe_{g}_{a.date}.jsonl", member)
    print("| group | intents (n) | n | per shop |\n|---|---|---|---|")
    for g, intents, n, per, by_int in rows:
        print(f"| {g}{'' if g != 'G3' else ' (inferred, no file)'} | " + ", ".join(f"{i} {by_int[i]}" for i in intents) +
              f" | {n} | " + ", ".join(f"{s} {c}" for s, c in sorted(per.items())) + " |")
    print("total answered in v1:", len(answered), "=", sum(r[2] for r in rows))
    if a.flagged:
        keep = lambda s: meta[s["id"]]["business_id"] not in set(a.flagged)  # noqa: E731
        kept = write(f"probe_v1_minus_flagged_{a.date}.jsonl", keep)
        print(f"v1 minus flagged {a.flagged}: answered {kept}, dropped {len(answered) - kept}")


if __name__ == "__main__":
    main()
