"""Abstain gate for the LLM route, from a measured harness run.

    python -m eval.llm_gate --per-question eval/reports/<run>_router.per_question.jsonl [--fold holdout] \\
        [--min-acc 0.6] [--min-n 10] [--out src/router/llm_gate.json]

Input: per-question rows of `eval.run_baseline --router` (fields route, gate_key, status, score, fold).  Only rows with
route == "llm" are used.  For every kind of question (gate key = tagger label of a not-target question, else the router
intent, else the fall-through reason):  n questions, answered, correct, accuracy = correct / answered, and the PA of the
group if the LLM answers it.  A kind is ENABLED when answered >= min-n and accuracy >= min-acc; everything else abstains
(a kind with too few answers abstains too).  Output: the config read by the pipeline when DATAMATE_LLM_GATE=<path>.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def key_of(row: dict) -> str:
    if row.get("gate_key"):
        return row["gate_key"]
    from src.router.gate import gate_key
    return gate_key(SimpleNamespace(reason=row.get("router_reason") or "", intent=row.get("router_intent")))


def build_gate(rows: list[dict], min_acc: float = 0.6, min_n: int = 10) -> dict:
    by: dict[str, dict[str, int]] = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        if r.get("route") != "llm":
            continue
        c = by[key_of(r)]
        c["n"] += 1
        st = r.get("status")
        if st == "correct":
            c["correct"] += 1
        elif st == "wrong":
            c["wrong"] += 1
        else:
            c["abstain"] += 1
    stats, enabled, disabled = {}, [], {}
    for k, c in sorted(by.items(), key=lambda kv: -kv[1]["n"]):
        answered = c["correct"] + c["wrong"]
        acc = c["correct"] / answered if answered else None
        stats[k] = {"n": c["n"], "answered": answered, "correct": c["correct"], "wrong": c["wrong"],
                    "accuracy": None if acc is None else round(acc, 4),
                    "pa_if_enabled": round((c["correct"] - c["wrong"]) / c["n"], 4)}
        if answered >= min_n and acc is not None and acc >= min_acc:
            enabled.append(k)
        else:
            disabled[k] = "insufficient_answers" if answered < min_n else "low_accuracy"
    tot_n = sum(s["n"] for s in stats.values())
    pa_all = sum(s["correct"] - s["wrong"] for s in stats.values()) / tot_n if tot_n else 0.0
    pa_gate = sum(stats[k]["correct"] - stats[k]["wrong"] for k in enabled) / tot_n if tot_n else 0.0
    return {"enabled": enabled, "disabled": disabled, "unknown_kinds": "abstain",
            "thresholds": {"min_accuracy": min_acc, "min_answered": min_n},
            "llm_route": {"questions": tot_n, "pa_llm_answers_all": round(pa_all, 4), "pa_with_gate": round(pa_gate, 4)},
            "stats": stats}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-question", nargs="+", required=True)
    ap.add_argument("--fold", default="holdout", choices=["holdout", "dev", "both"])
    ap.add_argument("--min-acc", type=float, default=0.6)
    ap.add_argument("--min-n", type=int, default=10)
    ap.add_argument("--out", default=str(ROOT / "src" / "router" / "llm_gate.json"))
    a = ap.parse_args()
    rows = [json.loads(l) for p in a.per_question for l in open(p, encoding="utf-8") if l.strip()]
    if a.fold != "both":
        rows = [r for r in rows if r.get("fold") == a.fold]
    gate = build_gate(rows, a.min_acc, a.min_n)
    gate["source"] = {"files": [Path(p).name for p in a.per_question], "fold": a.fold, "rows": len(rows)}
    Path(a.out).write_text(json.dumps(gate, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(gate['enabled'])} kinds enabled, {len(gate['disabled'])} abstain -> {a.out}")
    print("kind | n | answered | accuracy | PA if enabled | decision")
    for k, s in gate["stats"].items():
        print(f"{k} | {s['n']} | {s['answered']} | {s['accuracy']} | {s['pa_if_enabled']} | "
              f"{'ENABLED' if k in gate['enabled'] else gate['disabled'][k]}")
    print(gate["llm_route"])


if __name__ == "__main__":
    main()
