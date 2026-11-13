"""Router-only submission: template / unanswerable answers from the router, abstain for everything else (no LLM, no GPU).

    DATAMATE_CACHE_DIR=<dir> python scripts/make_router_submission.py --data-dir <public_test dir> --out <file.jsonl>

Output lines follow rulebook section 9: {"id","type","answer"} / {"id","type":"unanswerable","reason"} /
{"id","type":"abstain"} (0 points).  Prints a per-shop summary and validates the file.  Do not commit the output.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.nlu.normalize import RuleNormalizer  # noqa: E402
from src.router import Router  # noqa: E402
from src.router.db import ConnectionProvider  # noqa: E402

DATE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")


def valid_line(a: dict) -> str | None:
    """None if the line is well-formed per section 9, else the problem."""
    t = a.get("type")
    if t == "abstain":
        return None if set(a) == {"id", "type"} else "abstain with extra fields"
    if t == "unanswerable":
        return None if isinstance(a.get("reason"), str) else "unanswerable without string reason"
    v = a.get("answer")
    if t in ("number", "percent"):
        return None if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else "bad number"
    if t == "date":
        return None if isinstance(v, str) and DATE.match(v) else "bad date"
    if t == "string":
        return None if isinstance(v, str) and v.strip() else "bad string"
    if t == "list":
        return None if isinstance(v, list) and v else "bad list"
    return f"unsupported type {t!r}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--guard", action="store_true", help="shop-level low_confidence flags + per-question unparsed-date spans")
    ap.add_argument("--only-shops", nargs="*", help="restrict to these shops (analysis only)")
    ap.add_argument("--meta-out", help="jsonl with id, business_id, intent, route, reason per question (not for submission)")
    a = ap.parse_args()
    data = Path(a.data_dir)
    qs = [json.loads(l) for l in open(data / "questions.jsonl", encoding="utf-8") if l.strip()]
    if a.only_shops:
        qs = [q for q in qs if q["business_id"] in a.only_shops]
    from src.router.rule_guard import RuleGuard
    guard = RuleGuard.load(data / "rulebook.md") if a.guard and (data / "rulebook.md").is_file() else None
    router, norm, prov = Router(guard), RuleNormalizer(data / "calendar.csv", tet_bare=(guard.defines("2", "tet") if guard else True)), ConnectionProvider(data)
    t0 = time.monotonic()
    meta, out, per_shop, shop_err, reasons = [], [], collections.defaultdict(collections.Counter), {}, collections.Counter()
    for q in sorted(qs, key=lambda x: x["business_id"]):  # grouped by shop only for speed; file order is irrelevant
        biz, qid = q["business_id"], q["id"]
        try:
            bad = prov.flags(biz) if a.guard else []
            if bad:
                from src.router.router import RouteDecision
                d = RouteDecision("abstain", "shop_low_confidence: " + "; ".join(bad))
            else:
                d = router.route(q, norm(q["question"], q["as_of_date"]), prov.connection(biz),
                                 prov.spans(biz) if a.guard else None)
        except Exception as exc:
            shop_err.setdefault(biz, f"{type(exc).__name__}: {str(exc)[:160]}")
            d = None
        if d is not None and d.route in ("template", "unanswerable"):
            line = d.answer
        else:
            line = {"id": qid, "type": "abstain"}
        reasons[(d.reason.split(":")[0] if d else "shop_error")] += d is None or d.route not in ("template", "unanswerable")
        per_shop[biz]["total"] += 1
        per_shop[biz][line["type"] if line["type"] in ("abstain", "unanswerable") else "answered"] += 1
        out.append(line)
        meta.append({"id": qid, "business_id": biz, "intent": d.intent if d else None,
                     "route": d.route if d else "llm", "reason": d.reason if d else "shop_error"})
    prov.close()
    ids = [x["id"] for x in out]
    problems = [(x["id"], valid_line(x)) for x in out if valid_line(x)]
    assert len(ids) == len(set(ids)) == len(qs) and set(ids) == {q["id"] for q in qs}, "ids differ from questions.jsonl"
    assert not problems, problems[:5]
    qorder = {q["id"]: i for i, q in enumerate(qs)}
    out.sort(key=lambda x: qorder[x["id"]])  # same order as questions.jsonl
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        for x in out:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    if a.meta_out:
        Path(a.meta_out).write_text("\n".join(json.dumps(m, ensure_ascii=False) for m in meta) + "\n", encoding="utf-8")
    print(f"{datetime.date.today()} wrote {len(out)} lines to {a.out} in {time.monotonic() - t0:.0f}s; ids unique, all lines valid")
    print("shop      total answered unanswerable abstain")
    for b in sorted(per_shop):
        c = per_shop[b]
        print(f"{b:9s} {c['total']:5d} {c['answered']:8d} {c['unanswerable']:12d} {c['abstain']:7d}" + (f"   SHOP ERROR {shop_err[b]}" if b in shop_err else ""))
    tot = collections.Counter()
    for c in per_shop.values():
        tot.update(c)
    print("TOTAL", dict(tot))
    print("abstain reasons:", dict(reasons.most_common()))


if __name__ == "__main__":
    main()
