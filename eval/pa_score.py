"""PA (point-average) scorer implementing rulebook section 9.

Independent re-implementation, written from rulebook.md section 9 only
(NOT from eval/evaluate.py).  It is a stand-in until the official score.py
is available; when it is, run both on the same output and compare.

Scoring per question:
    +1  correct (right type, right format, right value)
    -1  wrong   (answered with wrong type / format / value; answering
                 a gold-unanswerable question; unanswerable on an answerable one)
     0  abstain / missing line / unreadable line

PA = sum(score) / number of gold questions (missing lines count as 0).

Usage:
    python -m eval.pa_score --pred submission.jsonl --gold answers.jsonl [--ids ids.json]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any

VALID_TYPES = {"number", "percent", "string", "date", "boolean", "list", "table", "unanswerable"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")

# Percent comparison mode.  Section 9: "làm tròn 2 chữ số thập phân" specifies
# agents must submit the value already rounded to 2 decimals; scorer rounds the
# submitted value to 2dp before comparing.  "round2" is the rulebook-correct mode.
PERCENT_MODE = "round2"


# --------------------------------------------------------------------------
# value comparison helpers
# --------------------------------------------------------------------------
def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _num_eq(pred: Any, gold: Any) -> bool:
    if not (_is_num(pred) and _is_num(gold)):
        return False
    return math.isclose(pred, gold, rel_tol=1e-9, abs_tol=1e-9)


def norm_str(s: str) -> str:
    """Case-, whitespace- and punctuation-insensitive; Vietnamese diacritics kept."""
    s = unicodedata.normalize("NFC", s).casefold()
    return "".join(c for c in s if unicodedata.category(c)[0] in "LNM")


def _str_eq(pred: Any, gold: Any, alias: list[Any] | None) -> bool:
    if not isinstance(pred, str):
        return False
    p = norm_str(pred)
    accepted = {norm_str(str(gold))}
    for a in alias or []:
        accepted.add(norm_str(str(a)))
    return p in accepted


def _cell_eq(pred: Any, gold: Any, alias: list[Any] | None = None) -> bool:
    if isinstance(gold, bool):
        return isinstance(pred, bool) and pred == gold
    if _is_num(gold):
        return _num_eq(pred, gold)
    if isinstance(gold, str):
        return _str_eq(pred, gold, alias)
    return pred == gold


# --------------------------------------------------------------------------
# per-type comparison (type already known to match)
# --------------------------------------------------------------------------
def _match_number(pred: Any, gold: Any) -> bool:
    return _num_eq(pred, gold)


def _match_percent(pred: Any, gold: Any) -> bool:
    if not _is_num(pred):
        return False
    if PERCENT_MODE == "round2":
        pred = round(pred, 2)
    return _num_eq(pred, gold)


def _match_date(pred: Any, gold: Any) -> bool:
    if not isinstance(pred, str):
        return False
    pred = pred.strip()
    return bool(_DATE_RE.match(pred)) and pred == gold


def _match_boolean(pred: Any, gold: Any) -> bool:
    return isinstance(pred, bool) and pred == gold


def _match_string(pred: Any, gold: Any, alias: list[Any]) -> bool:
    return _str_eq(pred, gold, alias)


def _match_list(pred: Any, gold: list[Any], alias: list[Any]) -> bool:
    if not isinstance(pred, list) or len(pred) != len(gold):
        return False
    for i, (p, g) in enumerate(zip(pred, gold)):
        al = alias[i] if i < len(alias) and isinstance(alias[i], list) else None
        if not _cell_eq(p, g, al):
            return False
    return True


def _match_table(pred: Any, gold: dict[str, Any], alias: list[Any]) -> bool:
    if not isinstance(pred, dict):
        return False
    pcols, prows = pred.get("columns"), pred.get("rows")
    gcols, grows = gold["columns"], gold["rows"]
    if not (isinstance(pcols, list) and isinstance(prows, list)):
        return False
    if len(pcols) != len(gcols):
        return False
    if not all(isinstance(r, list) and len(r) == len(pcols) for r in prows):
        return False
    if len(prows) != len(grows):
        return False
    # columns are matched by name; if names do not match, by position
    gn = [norm_str(str(c)) for c in gcols]
    pn = [norm_str(str(c)) for c in pcols]
    if sorted(gn) == sorted(pn) and len(set(gn)) == len(gn):
        order = [pn.index(n) for n in gn]  # order[j] = pred column index for gold column j
    else:
        order = list(range(len(gcols)))
    prows = [[r[k] for k in order] for r in prows]
    # row order is irrelevant: match each gold row to an unused pred row
    used = [False] * len(prows)
    for gi, grow in enumerate(grows):
        al = alias[gi] if gi < len(alias) and isinstance(alias[gi], list) else None
        hit = -1
        for pi, prow in enumerate(prows):
            if used[pi]:
                continue
            if all(_cell_eq(prow[c], grow[c], al if c == 0 else None) for c in range(len(grow))):
                hit = pi
                break
        if hit < 0:
            return False
        used[hit] = True
    return True


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------
def score_one(pred: Any, gold: dict[str, Any]) -> tuple[int, str]:
    """Return (score, status).  status in correct|wrong|abstain|missing|unreadable."""
    if pred is None:
        return 0, "missing"
    if not isinstance(pred, dict):
        return 0, "unreadable"
    ptype = pred.get("type")
    if ptype == "abstain" or ptype is None and "answer" not in pred:
        return 0, "abstain"
    if not isinstance(ptype, str):
        return 0, "unreadable"
    if ptype == "unanswerable" and "reason" in pred and not isinstance(pred["reason"], str):
        return 0, "unreadable"  # section 7: non-string reason => treated as blank
    gtype = gold["type"]
    if ptype != gtype or ptype not in VALID_TYPES:
        return -1, "wrong"
    if gtype == "unanswerable":
        return 1, "correct"
    if "answer" not in pred:
        return -1, "wrong"
    ans, g, alias = pred["answer"], gold["answer"], gold.get("alias") or []
    if gtype == "number":
        ok = _match_number(ans, g)
    elif gtype == "percent":
        ok = _match_percent(ans, g)
    elif gtype == "date":
        ok = _match_date(ans, g)
    elif gtype == "boolean":
        ok = _match_boolean(ans, g)
    elif gtype == "string":
        ok = _match_string(ans, g, alias)
    elif gtype == "list":
        ok = _match_list(ans, g, alias)
    elif gtype == "table":
        ok = _match_table(ans, g, alias)
    else:
        ok = False
    return (1, "correct") if ok else (-1, "wrong")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    rows.append({"__unreadable__": True})
    return rows


def score_all(
    preds: list[dict[str, Any]],
    golds: list[dict[str, Any]],
    ids: set[str] | None = None,
) -> dict[str, Any]:
    """Score predictions against gold; returns aggregate + per-question detail."""
    pmap: dict[str, Any] = {}
    for p in preds:
        if isinstance(p, dict) and "id" in p:
            pmap[str(p["id"])] = p
    detail: dict[str, dict[str, Any]] = {}
    for g in golds:
        gid = str(g["id"])
        if ids is not None and gid not in ids:
            continue
        s, st = score_one(pmap.get(gid), g)
        detail[gid] = {"score": s, "status": st, "gold_type": g["type"]}
    n = len(detail)
    total = sum(d["score"] for d in detail.values())
    cnt = {k: sum(1 for d in detail.values() if d["status"] == k)
           for k in ("correct", "wrong", "abstain", "missing", "unreadable")}
    return {
        "n": n,
        "pa": total / n if n else 0.0,
        "total": total,
        "accuracy": cnt["correct"] / n if n else 0.0,
        "abstain_rate": (cnt["abstain"] + cnt["missing"] + cnt["unreadable"]) / n if n else 0.0,
        "counts": cnt,
        "percent_mode": PERCENT_MODE,
        "detail": detail,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--ids", help="JSON list of question ids to score (default: all gold)")
    args = ap.parse_args()
    ids = set(json.loads(Path(args.ids).read_text())) if args.ids else None
    res = score_all(read_jsonl(Path(args.pred)), read_jsonl(Path(args.gold)), ids)
    res.pop("detail")
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
