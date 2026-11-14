"""Validate src/timeutil.py against gold using the data-layer rule-regression templates (no LLM, no GPU).

For every question that scripts/analysis/rule_regression.py of the data-layer branch selects (the "942"
template group: explicit month / explicit date), the date part of the SQL template is replaced by the filter
generated from the timeutil Period (`Period.where_sql`) and the computed answer is compared with gold.
Selection, SQL templates, answer comparison and the data layer are the data-layer branch's, unmodified.

    python scripts/validate_timeutil_templates.py --p3-root <checkout of feat/p3-data-cleaning> --train-dir data/train/train \
        --out outputs/timeutil_templates.md [--folds eval/folds.json] [--shops biz_101 ...]

--folds defaults to $ZAIC_FOLDS, else eval/folds.json in this repo if present (file comes from feat/real-data-eval);
without it every shop is reported as "dev".
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


BETWEEN = "order_date BETWEEN ? AND ?"


class ConnProxy:
    """Rewrites the template's `order_date BETWEEN ? AND ?` into the timeutil Period filter."""

    def __init__(self, conn, state):
        self._c, self._s = conn, state

    def execute(self, sql, params=()):
        clauses = self._s.get("clauses")
        if clauses and BETWEEN in sql:
            params = list(params)
            for cl in clauses:
                if BETWEEN not in sql:
                    break
                sql = sql.replace(BETWEEN, cl, 1)
                params = params[2:]
            self._s["rewritten"] = True
        return self._c.execute(sql, params)

    def __getattr__(self, k):
        return getattr(self._c, k)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p3-root", required=True)
    ap.add_argument("--train-dir", required=True)
    ap.add_argument("--folds", default=os.environ.get("ZAIC_FOLDS") or (str(ROOT / "eval" / "folds.json") if (ROOT / "eval" / "folds.json").is_file() else None))
    ap.add_argument("--out", required=True)
    ap.add_argument("--shops", nargs="*")
    a = ap.parse_args()

    p3 = Path(a.p3_root).resolve()
    # `src` is this branch's package (timeutil, nlu); the data-layer branch's src/ is searched first for the
    # modules both have (ingestion, views, ...), so its data layer is used unmodified.
    sys.path.insert(0, str(ROOT))
    import src
    src.__path__.insert(0, str(p3 / "src"))
    from src.nlu.normalize import normalize
    sys.path.insert(0, str(p3))
    sys.path.insert(0, str(p3 / "scripts" / "analysis"))
    rr = load_module("rule_regression_p3", p3 / "scripts" / "analysis" / "rule_regression.py")
    train = Path(a.train_dir).resolve()
    rr.DATA_DIR = train

    state: dict = {}
    records: list[dict] = []
    orig_parse, orig_exec, orig_build = rr.parse_explicit_period, rr.execute_template, rr.build_database

    def parse(question, as_of):
        info = orig_parse(question, as_of)
        state.clear()
        state["q"], state["as_of"], state["orig"] = question, as_of, info
        return info

    def build(*args, **kw):
        return ConnProxy(orig_build(*args, **kw), state)

    def execute(conn, intent, question, as_of, period_info, catalog):
        res = normalize(question, as_of).period  # rule layer then timeutil, as in the pipeline
        as_of_d = dt.date.fromisoformat(as_of)
        rec = {"question": question, "as_of": as_of, "intent": intent,
               "orig": list(period_info[:2]), "tu": None, "ambiguous": res.ambiguous}
        clauses = None
        if intent == "rev_change_pct":
            cur = res.periods[0] if res.periods else None
            prev = res.comparison or (res.periods[1] if len(res.periods) > 1 else None)
            if cur and prev:
                clauses = [cur.where_sql(), prev.where_sql()]
                rec["tu"] = [cur.start.isoformat() if cur.start else None, cur.end.isoformat()]
        elif res.periods:
            p = res.periods[0]
            clauses = [p.where_sql()]
            rec["tu"] = [p.start.isoformat() if p.start else None, min(p.end, as_of_d).isoformat()]
        state["clauses"] = clauses or ["1=0"] * (2 if intent == "rev_change_pct" else 1)
        state["rewritten"] = False
        rec["no_period"] = clauses is None
        # rr's own period tuple is kept only so that its (unchanged) helper code runs; the SQL date filter
        # comes from the Period (ConnProxy) -- except rev_change_pct comparison windows which rr derives
        # itself and which are replaced the same way.
        out = orig_exec(conn, intent, question, as_of, period_info, catalog)
        rec["rewritten"] = state["rewritten"]
        rec["calc"] = out[0]
        records.append(rec)
        state["clauses"] = None
        return out

    rr.parse_explicit_period, rr.execute_template, rr.build_database = parse, execute, build
    res = rr.run_regression(a.shops or None)

    fails = {(f.question, f.as_of_date): f for f in res["failures"]}
    folds = json.loads(Path(a.folds).read_text()) if a.folds else {"holdout": []}
    shop_of = {}
    for line in open(train / "questions.jsonl", encoding="utf-8"):
        q = json.loads(line)
        shop_of[(q["question"], q["as_of_date"])] = q["business_id"]
    hold = set(folds["holdout"])

    tot = collections.Counter()
    by_intent: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    by_fold: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    period_diff, mism = [], []
    for r in records:
        ok = (r["question"], r["as_of"]) not in fails
        fold = "holdout" if shop_of.get((r["question"], r["as_of"])) in hold else "dev"
        for c in (tot, by_intent[r["intent"]], by_fold[fold]):
            c["n"] += 1
            c["ok"] += ok
            c["no_period"] += r["no_period"]
        if r["tu"] and r["intent"] != "rev_change_pct" and r["tu"] != r["orig"]:
            period_diff.append(r)
        if not ok:
            mism.append((r, fails[(r["question"], r["as_of"])]))

    L = ["# timeutil vs gold on the data-layer template group", "",
         f"Questions selected by rule_regression.py: {tot['n']}; answered correctly with the timeutil Period filter: "
         f"**{tot['ok']}/{tot['n']} = {100 * tot['ok'] / max(tot['n'], 1):.2f}%**; timeutil returned no period: {tot['no_period']}.",
         f"SQL filter actually rewritten from the Period: {sum(r['rewritten'] for r in records)}/{len(records)}.",
         f"Periods differing from rule_regression's own (single-period intents): {len(period_diff)}.", "",
         "| group | n | correct | % | no period |", "|---|---|---|---|---|"]
    for name, d in sorted(by_intent.items()):
        L.append(f"| intent {name} | {d['n']} | {d['ok']} | {100 * d['ok'] / d['n']:.1f} | {d['no_period']} |")
    for name, d in sorted(by_fold.items()):
        L.append(f"| fold {name} | {d['n']} | {d['ok']} | {100 * d['ok'] / d['n']:.1f} | {d['no_period']} |")
    L += ["", f"## Mismatches ({len(mism)})", ""]
    for r, f in mism:
        L.append(f"- [{f.business_id}] {f.intent}: `{r['question']}` as_of={r['as_of']}  timeutil={r['tu']} "
                 f"rr={r['orig']}  calc={f.calculated!r} gold={f.expected!r}  ambiguous={bool(r['ambiguous'])}")
    L += ["", f"## Period differs from rule_regression's parse ({len(period_diff)})", ""]
    for r in period_diff:
        L.append(f"- `{r['question']}` timeutil={r['tu']} rr={r['orig']}")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:14]))


if __name__ == "__main__":
    main()
