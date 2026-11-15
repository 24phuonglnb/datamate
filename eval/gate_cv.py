"""Cross-validate the LLM abstain gate by shop.

    python -m eval.gate_cv --per-question eval/reports/<run>_holdout_router.per_question.jsonl \\
        [--min-acc 0.5 0.6 0.7] [--min-n 3 5 10] [--split A,B,C] [--out eval/reports/<date>_gate_cv.md]

Input: the per-question rows of `eval.run_baseline --router` (fields id, business_id, route, status, score, gate_key,
router_reason, router_intent), one run that has the LLM answer every question the router leaves.  A gate (the kinds of
question the LLM may answer, `eval.llm_gate.build_gate`) is chosen on some shops and measured on others, so the number
is never the one the gate was fitted on:

  * split      shops are cut into two halves; fit on one half, measure on the other, then swap (2 runs);
               default halves: the sorted shop list's first half / second half, or --split A,B,C for the first half
  * loo        leave one shop out: fit on all other shops, measure on the left-out one (one run per shop)
  * (reference) "all"  = the LLM answers every question it is given (no gate); "router-only" = the LLM never answers

Per configuration and (min_acc, min_n): the PA of the LLM branch (sum of scores of the LLM-route questions the gate lets
through, divided by the number of LLM-route questions of the measured shops) and the total PA (router answers + gated LLM
answers, divided by all questions of the measured shops).  Pooled over the measured shops of every run in the configuration.
Score = +1 correct, -1 wrong, 0 abstain (rulebook section 9); no model, no GPU.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

try:
    from eval.llm_gate import build_gate, key_of
except ImportError:   # run as a script
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from eval.llm_gate import build_gate, key_of


def _score(r: dict) -> int:
    s = r.get("score")
    if isinstance(s, (int, float)):
        return int(s)
    return {"correct": 1, "wrong": -1}.get(r.get("status"), 0)


def measure(rows: list[dict], enabled: set[str] | None) -> dict:
    """PA of `rows` when the LLM may answer the kinds in `enabled` (None = every kind, empty set = none)."""
    n = len(rows)
    router = sum(_score(r) for r in rows if r.get("route") != "llm")
    llm_rows = [r for r in rows if r.get("route") == "llm"]
    let_through = [r for r in llm_rows if enabled is None or key_of(r) in enabled]
    llm = sum(_score(r) for r in let_through)
    return {"n": n, "n_llm": len(llm_rows), "llm_answered": sum(1 for r in let_through if r.get("status") in ("correct", "wrong")),
            "llm_pa_sum": llm, "router_pa_sum": router,
            "pa_llm_branch": llm / len(llm_rows) if llm_rows else 0.0, "pa_total": (router + llm) / n if n else 0.0}


def _pool(parts: list[dict]) -> dict:
    n, n_llm = sum(p["n"] for p in parts), sum(p["n_llm"] for p in parts)
    llm, router = sum(p["llm_pa_sum"] for p in parts), sum(p["router_pa_sum"] for p in parts)
    return {"n": n, "n_llm": n_llm, "llm_answered": sum(p["llm_answered"] for p in parts), "llm_pa_sum": llm,
            "router_pa_sum": router, "pa_llm_branch": llm / n_llm if n_llm else 0.0, "pa_total": (router + llm) / n if n else 0.0}


def run_fold(rows: list[dict], fit_shops: set[str], test_shops: set[str], min_acc: float, min_n: int) -> dict:
    gate = build_gate([r for r in rows if r["business_id"] in fit_shops], min_acc, min_n)
    test = [r for r in rows if r["business_id"] in test_shops]
    out = measure(test, set(gate["enabled"]))
    out["enabled"] = gate["enabled"]
    return out


def splits(shops: list[str], first_half: list[str] | None) -> list[tuple[set[str], set[str]]]:
    a = set(first_half) if first_half else set(shops[: len(shops) // 2])
    b = set(shops) - a
    return [(a, b), (b, a)]


def cross_validate(rows: list[dict], min_accs: list[float], min_ns: list[int], first_half: list[str] | None = None) -> dict:
    shops = sorted({r["business_id"] for r in rows})
    res: dict = {"shops": shops, "reference": {}, "configs": {}}
    res["reference"]["all"] = measure(rows, None)
    res["reference"]["router-only"] = measure(rows, set())
    for acc, mn in itertools.product(min_accs, min_ns):
        key = f"min_acc={acc},min_n={mn}"
        sp = [run_fold(rows, fit, test, acc, mn) for fit, test in splits(shops, first_half)]
        loo = [run_fold(rows, set(shops) - {s}, {s}, acc, mn) for s in shops]
        res["configs"][key] = {"split": {"folds": sp, "pooled": _pool(sp)}, "loo": {"folds": loo, "pooled": _pool(loo)}}
    return res


def to_markdown(res: dict) -> str:
    ref = res["reference"]
    L = [f"# Gate cross-validation by shop ({len(res['shops'])} shops: {', '.join(res['shops'])})", "",
         "| configuration | gate fitted on | PA of the LLM branch | total PA | LLM answered |", "|---|---|---|---|---|",
         f"| all (no gate, LLM answers everything) | none | {ref['all']['pa_llm_branch']:.4f} | {ref['all']['pa_total']:.4f} | {ref['all']['llm_answered']} |",
         f"| router-only (LLM never answers) | none | 0.0000 | {ref['router-only']['pa_total']:.4f} | 0 |"]
    for key, c in res["configs"].items():
        for name, label in (("split", "other half (both directions)"), ("loo", "the other shops (leave one out)")):
            p = c[name]["pooled"]
            L.append(f"| {key} {name} | {label} | {p['pa_llm_branch']:.4f} | {p['pa_total']:.4f} | {p['llm_answered']} |")
    L += ["", "PA of the LLM branch = (correct - wrong) of the LLM-route questions let through / number of LLM-route questions; "
          "total PA = (router + gated LLM scores) / all questions of the measured shops.", ""]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-question", nargs="+", required=True)
    ap.add_argument("--fold", default="holdout", choices=["holdout", "dev", "both"])
    ap.add_argument("--min-acc", type=float, nargs="+", default=[0.5, 0.6, 0.7])
    ap.add_argument("--min-n", type=int, nargs="+", default=[3, 5, 10])
    ap.add_argument("--split", help="comma-separated shops of the first half (default: first half of the sorted shops)")
    ap.add_argument("--out", help="write the markdown table here (and <out>.json)")
    a = ap.parse_args()
    rows = [json.loads(l) for p in a.per_question for l in open(p, encoding="utf-8") if l.strip()]
    if a.fold != "both":
        rows = [r for r in rows if r.get("fold") == a.fold]
    res = cross_validate(rows, a.min_acc, a.min_n, a.split.split(",") if a.split else None)
    md = to_markdown(res)
    print(md)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
        Path(a.out + ".json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
