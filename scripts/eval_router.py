"""CPU-only evaluation of the intent router on the train questions (no LLM, no GPU).

    DATAMATE_CACHE_DIR=<dir> python scripts/eval_router.py --train-dir data/train/train [--folds eval/folds.json] \
        [--shops biz_101 ...] [--out eval/reports/<date>_router]

Writes <out>.md / .json (aggregates + errors by question id, no question text and no gold values) and
<out>.per_question.jsonl (git-ignored: ids, route, reason, scores and local diagnostics).
Scores use eval/pa_score.py (rulebook section 9).  "PA lower bound" = template answers, every other question abstains.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval import pa_score  # noqa: E402
from src.ingestion import BusinessDB  # noqa: E402
from src.nlu.normalize import normalize  # noqa: E402
from src.router import Router  # noqa: E402
from src.router.intents import EXTRA_INTENTS, TARGET_INTENTS  # noqa: E402
from src.router.templates import ANSWER_TYPE, run_template  # noqa: E402
from src.timeutil import LunarCalendar  # noqa: E402


def read(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def attribute(conn, d, gold):
    """Why is a wrong template answer wrong?  intent / param / other (local diagnostic, uses gold)."""
    p = d.params
    for alt in TARGET_INTENTS:
        if alt == d.intent or "start" not in p:
            continue
        try:
            kw = {}
            if alt == "topk_items":
                kw["k"] = p.get("k", 3)
            if alt == "item_qty" or (alt == "rev_change_pct" and "prev" not in p):
                continue
            if alt == "rev_change_pct":
                kw["prev"] = tuple(p["prev"])
            v = run_template(conn, alt, p["start"], p["end"], **kw)
        except Exception:
            continue
        if v is not None and pa_score.score_one({"id": "x", "type": ANSWER_TYPE[alt], "answer": v}, gold)[0] == 1:
            return f"intent_error(true={alt})"
    if d.intent in ("topk_items", "best_item"):
        return "param_or_template(k/ranking)"
    if d.intent == "item_qty":
        return "param(item/unit)"
    return f"period_or_template({p.get('start', '')[:0]}granularity-check)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-dir", required=True)
    ap.add_argument("--folds", default=str(ROOT / "eval" / "folds.json"))
    ap.add_argument("--shops", nargs="*")
    ap.add_argument("--fold", choices=["dev", "holdout", "both"], default="both",
                    help="evaluate only dev shops (use while developing) or only the hold-out shops")
    ap.add_argument("--out", default=str(ROOT / "eval" / "reports" / f"{datetime.date.today()}_router"))
    a = ap.parse_args()
    train = Path(a.train_dir)
    qs = read(train / "questions.jsonl")
    gold = {g["id"]: g for g in read(train / "answers.jsonl")}
    hold = set(json.loads(Path(a.folds).read_text())["holdout"])
    cal = LunarCalendar(train / "calendar.csv")
    router = Router()
    by_shop = collections.defaultdict(list)
    for q in qs:
        fold_q = "holdout" if q["business_id"] in hold else "dev"
        if a.fold != "both" and fold_q != a.fold:
            continue
        if not a.shops or q["business_id"] in a.shops:
            by_shop[q["business_id"]].append(q)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows, t0 = [], time.monotonic()
    with open(str(out) + ".per_question.jsonl", "w", encoding="utf-8") as f:
        for biz in sorted(by_shop):
            db = BusinessDB(train / "data" / biz, train / "calendar.csv")
            for q in by_shop[biz]:
                nq = normalize(q["question"], q["as_of_date"], cal)
                d = router.route(q, nq, db.connection)
                g = gold[q["id"]]
                row = {"id": q["id"], "fold": "holdout" if biz in hold else "dev", "route": d.route, "reason": d.reason,
                       "intent": d.intent, "gold_type": g["type"], "gran": None}
                if d.route in ("template", "unanswerable"):
                    row["score"], row["status"] = pa_score.score_one(d.answer, g)
                    row["answer"], row["gold"], row["params"] = d.answer.get("answer"), g.get("answer"), d.params
                    if row["score"] != 1:
                        row["attr"] = attribute(db.connection, d, g)
                rows.append(row)
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            db.close()
            print(biz, len(by_shop[biz]), f"{time.monotonic() - t0:.0f}s", flush=True)

    def agg(rs):
        n = len(rs)
        tm = [r for r in rs if r["route"] in ("template", "unanswerable")]
        ok = sum(r["score"] == 1 for r in tm)
        return {"n": n, "template": len(tm), "template_pct": round(100 * len(tm) / max(n, 1), 2),
                "template_correct": ok, "template_acc_pct": round(100 * ok / max(len(tm), 1), 2),
                "template_pa": round(sum(r["score"] for r in tm) / max(len(tm), 1), 4),
                "pa_lower_bound": round(sum(r["score"] for r in tm) / max(n, 1), 4),
                "wrong": len(tm) - ok}

    rep = {}
    for fold in ("dev", "holdout"):
        rs = [r for r in rows if r["fold"] == fold]
        tm = [r for r in rs if r["route"] in ("template", "unanswerable")]
        rep[fold] = {**agg(rs),
                     "by_intent": {i: agg([r for r in rs if r["intent"] == i and r["route"] in ("template", "unanswerable")]) for i in (*TARGET_INTENTS, *EXTRA_INTENTS)},
                     "llm_reasons": dict(collections.Counter(r["reason"].split(":")[0] for r in rs if r["route"] not in ("template", "unanswerable")).most_common()),
                     "wrong_attribution": dict(collections.Counter(r["attr"].split("(")[0] for r in tm if r["score"] != 1 and "attr" in r)),
                     "intent_accuracy_pct": round(100 * (1 - sum(1 for r in tm if str(r.get("attr", "")).startswith("intent_error")) / max(len(tm), 1)), 2),
                     "errors": [{"id": r["id"], "intent": r["intent"], "gold_type": r["gold_type"], "attr": r["attr"], "reason_params": sorted(r["params"])}
                                for r in tm if r["score"] != 1]}
    Path(str(out) + ".json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    L = [f"# Router evaluation (CPU, no LLM) {datetime.date.today()}", "",
         "| fold | questions | template route | % | correct | accuracy % | template PA | PA lower bound | wrong | intent acc % |", "|---|---|---|---|---|---|---|---|---|---|"]
    for fold, r in rep.items():
        L.append(f"| {fold} | {r['n']} | {r['template']} | {r['template_pct']} | {r['template_correct']} | {r['template_acc_pct']} | {r['template_pa']} | {r['pa_lower_bound']} | {r['wrong']} | {r['intent_accuracy_pct']} |")
    for fold, r in rep.items():
        L += ["", f"## {fold}: by intent (template route)", "", "| intent | n | correct | acc % |", "|---|---|---|---|"]
        L += [f"| {i} | {v['template']} | {v['template_correct']} | {v['template_acc_pct']} |" for i, v in r["by_intent"].items() if v["template"]]
        L += ["", f"LLM/other reasons: {r['llm_reasons']}", f"Wrong attribution: {r['wrong_attribution']}", "", f"### {fold} errors (id, intent, gold type, attribution)", ""]
        L += [f"- {e['id']} {e['intent']} {e['gold_type']} {e['attr']}" for e in r["errors"]]
    Path(str(out) + ".md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:6]))


if __name__ == "__main__":
    main()
