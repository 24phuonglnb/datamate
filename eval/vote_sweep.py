"""Re-vote a logged self-consistency run offline with several thresholds (no model, no GPU).

    python -m eval.vote_sweep --log <result>/logs/questions.jsonl --gold <train>/answers.jsonl \\
        [--thresholds 0.4 0.5 0.6 0.8] [--out report.md]

Input: the run log of `src.predict` with DATAMATE_LLM_VOTE_K >= 2 and DATAMATE_LLM_VOTE_FULL=1 (every question that fell to the
LLM carries all k samples in log["vote"]["samples"]; router-answered questions carry log["router"]).  For each threshold t a
question is answered when the largest group of equal answers (`src.router.vote.same_answer`, the PA scorer's equality) has at
least ceil(t * k) samples and no other group is as large; else abstain.  Scores: +1 / -1 / 0 (rulebook section 9).

Reported per threshold: answered / correct / wrong on the LLM-route questions, PA of the LLM branch (sum of scores / LLM-route
questions), total PA (router + voted LLM answers, over all logged questions) against router-only, and the accuracy of the
answered LLM-route questions by fall-through intent (the router's intent, else the tagger label of the reason).
"""
from __future__ import annotations

import argparse
import collections
import json
import math
from pathlib import Path
from typing import Any

try:
    from eval import pa_score
    from src.router.vote import needed_votes, same_answer
except ImportError:   # run as a script
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from eval import pa_score
    from src.router.vote import needed_votes, same_answer


def read(p: str | Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def kind_of(log: dict[str, Any]) -> str:
    r = log.get("router") or {}
    if r.get("intent"):
        return str(r["intent"])
    reason = str(r.get("reason") or "unknown")
    return reason.split(":", 1)[1] if reason.startswith("not_target:") else reason.split(":")[0]


def revote(vote: dict[str, Any], qid: str, threshold: float) -> dict[str, Any]:
    """The answer of a logged vote at `threshold` (abstain when the support is too small or tied)."""
    k = int(vote["k"])
    groups: list[list[dict[str, Any]]] = []
    for s in vote.get("samples", []):
        a = s.get("answer")
        if not isinstance(a, dict) or a.get("type") in (None, "abstain"):
            continue
        for g in groups:
            if same_answer(a, g[0]):
                g.append(a)
                break
        else:
            groups.append([a])
    top = max(groups, key=len, default=[])
    tied = sum(1 for g in groups if len(g) == len(top)) > 1
    if top and len(top) >= needed_votes(k, threshold) and not tied:
        return {**top[0], "id": qid}
    return {"id": qid, "type": "abstain"}


def sweep(logs: list[dict[str, Any]], gold: dict[str, dict[str, Any]], thresholds: list[float]) -> dict[str, Any]:
    n_all = sum(1 for l in logs if l["id"] in gold)
    router_sum = 0
    llm_logs = []
    for l in logs:
        g = gold.get(l["id"])
        if g is None:
            continue
        r = l.get("router") or {}
        if r.get("route") == "llm" and isinstance(l.get("vote"), dict):
            llm_logs.append(l)
        else:
            router_sum += pa_score.score_one(l.get("answer"), g)[0]
    out: dict[str, Any] = {"n": n_all, "n_llm": len(llm_logs), "router_sum": router_sum,
                           "router_only_pa": router_sum / n_all if n_all else 0.0, "rows": {}}
    for t in thresholds:
        c = collections.Counter()
        by = collections.defaultdict(collections.Counter)
        ssum = 0
        for l in llm_logs:
            ans = revote(l["vote"], l["id"], t)
            sc, st = pa_score.score_one(ans, gold[l["id"]])
            ssum += sc
            c[st] += 1
            by[kind_of(l)][st] += 1
        answered = c["correct"] + c["wrong"]
        out["rows"][t] = {"answered": answered, "correct": c["correct"], "wrong": c["wrong"], "llm_pa_sum": ssum,
                          "pa_llm_branch": ssum / len(llm_logs) if llm_logs else 0.0,
                          "pa_total": (router_sum + ssum) / n_all if n_all else 0.0,
                          "accuracy": c["correct"] / answered if answered else None,
                          "by_kind": {k: dict(v) for k, v in by.items()}}
    return out


def to_markdown(res: dict[str, Any]) -> str:
    L = [f"# Vote sweep: {res['n']} questions, {res['n_llm']} reached the LLM", "",
         f"router-only PA (LLM never answers): {res['router_only_pa']:.4f}", "",
         "| threshold | answered | correct | wrong | accuracy | PA LLM branch | PA total | vs router-only |", "|---|---|---|---|---|---|---|---|"]
    for t, r in res["rows"].items():
        acc = "-" if r["accuracy"] is None else f"{r['accuracy']:.3f}"
        L.append(f"| {t} | {r['answered']} | {r['correct']} | {r['wrong']} | {acc} | {r['pa_llm_branch']:.4f} | {r['pa_total']:.4f} | "
                 f"{r['pa_total'] - res['router_only_pa']:+.4f} |")
    for t, r in res["rows"].items():
        L += ["", f"## threshold {t}: accuracy of answered LLM-route questions by fall-through intent", "", "| intent | answered | correct | wrong | accuracy |", "|---|---|---|---|---|"]
        for k, v in sorted(r["by_kind"].items(), key=lambda kv: -(kv[1].get("correct", 0) + kv[1].get("wrong", 0))):
            a = v.get("correct", 0) + v.get("wrong", 0)
            if a:
                L.append(f"| {k} | {a} | {v.get('correct', 0)} | {v.get('wrong', 0)} | {v.get('correct', 0) / a:.3f} |")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--thresholds", type=float, nargs="+", default=[0.4, 0.5, 0.6, 0.8])
    ap.add_argument("--out")
    a = ap.parse_args()
    gold = {g["id"]: g for g in read(a.gold)}
    res = sweep(read(a.log), gold, a.thresholds)
    md = to_markdown(res)
    print(md)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
