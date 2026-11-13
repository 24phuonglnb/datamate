"""Official scoring logic for the Zalo AI Challenge DataMate competition.

Implements the scoring rules from rulebook.md §9:
  - Correct answer  → +1
  - Wrong answer    → -1
  - Abstain         →  0
  - PA = (correct - incorrect) / total

Comparison rules per type (from rulebook §9):
  number  : exact (floating-point tolerance ≤ 0.5; "tiền đúng từng đồng")
  percent : exact to 2 decimal places (tolerance ≤ 0.005)
  boolean : exact
  string  : case/whitespace/punctuation-insensitive; also accepts aliases
  date    : exact string match ("YYYY-MM-DD" or "YYYY-MM")
  list    : order-sensitive; each element matched by string rules + per-element alias
  table   : row-order independent; first column matched with per-row alias;
            numeric columns exact; string columns by string rules

Ground-truth answers must stay inside this module during inference; they are
only accessed via score_submission() after all predictions are collected.
"""
from __future__ import annotations

import math
import re
from typing import Any

from .official_dataset import OfficialAnswer


# ── String normalisation ──────────────────────────────────────────────────

_WS_RE = re.compile(r"[\s ]+")
_PUNCT_RE = re.compile(r"[,.\-_/\\()'\"]")


def _norm(s: Any) -> str:
    """Normalize for case/whitespace comparison (not punctuation)."""
    return _WS_RE.sub(" ", str(s)).strip().lower()


def _str_eq(pred: Any, gt: Any) -> bool:
    return _norm(pred) == _norm(gt)


def _str_matches(pred: Any, gt: Any, aliases: list[Any]) -> bool:
    """Return True if pred equals gt or any alias (after normalization)."""
    pn = _norm(pred)
    if pn == _norm(gt):
        return True
    for a in aliases:
        if pn == _norm(a):
            return True
    return False


# ── Per-type comparison ───────────────────────────────────────────────────

def _cmp_number(pred: Any, gt: Any) -> bool:
    try:
        pf = float(pred)
        gf = float(gt)
    except (TypeError, ValueError):
        return False
    if math.isnan(pf) or math.isnan(gf):
        return False
    # "tiền đúng từng đồng" → integer currency: tolerance < 0.5 covers float repr
    return abs(pf - gf) < 0.5


def _cmp_percent(pred: Any, gt: Any) -> bool:
    try:
        pf = float(pred)
        gf = float(gt)
    except (TypeError, ValueError):
        return False
    if math.isnan(pf) or math.isnan(gf):
        return False
    # "phần trăm đúng 2 chữ số thập phân"
    return abs(pf - gf) < 0.005


def _cmp_boolean(pred: Any, gt: Any) -> bool:
    if isinstance(pred, str):
        pred = pred.strip().lower()
        if pred == "true":
            pred = True
        elif pred == "false":
            pred = False
        elif pred in ("1",):
            pred = True
        elif pred in ("0",):
            pred = False
    if isinstance(gt, str):
        gt = gt.strip().lower()
        gt = gt == "true"
    return bool(pred) == bool(gt)


def _cmp_date(pred: Any, gt: Any) -> bool:
    return str(pred).strip() == str(gt).strip()


def _cmp_list(pred: Any, gt: Any, alias: list[Any]) -> bool:
    """Order-sensitive list comparison with per-element aliases."""
    if not isinstance(pred, list) or not isinstance(gt, list):
        return False
    if len(pred) != len(gt):
        return False
    # alias is a list of lists: alias[i] contains alternatives for gt[i]
    for i, (p, g) in enumerate(zip(pred, gt)):
        elem_aliases: list[Any] = []
        if alias and i < len(alias):
            raw = alias[i]
            elem_aliases = raw if isinstance(raw, list) else [raw]
        # For numeric elements compare numerically; otherwise as strings
        try:
            pf, gf = float(p), float(g)
            if not (math.isnan(pf) or math.isnan(gf) or abs(pf - gf) >= 0.5):
                continue
            # Numeric mismatch — fall through to string check
        except (TypeError, ValueError):
            pass
        if not _str_matches(p, g, elem_aliases):
            return False
    return True


def _cmp_table(pred: Any, gt: Any, alias: list[Any]) -> bool:
    """Row-order-independent table comparison.

    alias is a list of per-row alternatives for the first (name/ID) column.
    Rows are matched by the first column value (canonical or alias).
    """
    if not isinstance(pred, dict) or not isinstance(gt, dict):
        return False

    pred_rows = pred.get("rows", [])
    gt_rows = gt.get("rows", [])
    pred_cols = [str(c).lower() for c in (pred.get("columns") or [])]
    gt_cols = [str(c).lower() for c in (gt.get("columns") or [])]

    if len(pred_rows) != len(gt_rows):
        return False

    # Build a lookup from (normalised first-column value or alias) → row index
    # for the ground truth so we can match rows in any order.
    gt_by_key: dict[str, int] = {}
    for idx, gt_row in enumerate(gt_rows):
        if not gt_row:
            continue
        key = _norm(gt_row[0])
        gt_by_key[key] = idx
        row_aliases: list[Any] = []
        if alias and idx < len(alias):
            raw = alias[idx]
            row_aliases = raw if isinstance(raw, list) else [raw]
        for a in row_aliases:
            gt_by_key[_norm(a)] = idx

    matched: set[int] = set()

    for pred_row in pred_rows:
        if not pred_row:
            return False
        pk = _norm(pred_row[0])
        gt_idx = gt_by_key.get(pk)
        if gt_idx is None or gt_idx in matched:
            return False
        matched.add(gt_idx)

        gt_row = gt_rows[gt_idx]

        # Compare non-first columns: numeric exact, string by normalisation.
        # Use gt column count as reference; pred may have more columns.
        for col_i in range(1, len(gt_row)):
            if col_i >= len(pred_row):
                return False
            pv = pred_row[col_i]
            gv = gt_row[col_i]
            # Numeric?
            try:
                pf, gf = float(pv), float(gv)
                if math.isnan(pf) or math.isnan(gf):
                    return False
                if abs(pf - gf) < 0.5:
                    continue
                return False
            except (TypeError, ValueError):
                pass
            # String
            if not _str_eq(pv, gv):
                return False

    return len(matched) == len(gt_rows)


# ── Main comparison entry point ───────────────────────────────────────────

def answers_match(pred_ans: Any, pred_type: str, gt: OfficialAnswer) -> bool:
    """Return True if the prediction matches the official ground truth."""
    gt_type = gt.type
    alias = gt.alias or []

    if gt_type == "unanswerable":
        return pred_type == "unanswerable"

    if pred_type in ("abstain", "unanswerable"):
        return False

    if pred_type != gt_type:
        return False

    if gt.answer is None:
        return False
    if pred_ans is None:
        return False

    try:
        if gt_type == "number":
            return _cmp_number(pred_ans, gt.answer)
        if gt_type == "percent":
            return _cmp_percent(pred_ans, gt.answer)
        if gt_type == "boolean":
            return _cmp_boolean(pred_ans, gt.answer)
        if gt_type == "date":
            return _cmp_date(pred_ans, gt.answer)
        if gt_type == "string":
            flat_alias = alias if isinstance(alias, list) else [alias]
            return _str_matches(pred_ans, gt.answer, flat_alias)
        if gt_type == "list":
            return _cmp_list(pred_ans, gt.answer, alias)
        if gt_type == "table":
            return _cmp_table(pred_ans, gt.answer, alias)
    except Exception:
        return False
    return False


# ── PA and aggregate metrics ──────────────────────────────────────────────

def compute_pa_score(
    predictions: list[dict[str, Any]],
    ground_truths: dict[str, OfficialAnswer],
) -> dict[str, Any]:
    """Compute official PA and auxiliary metrics.

    Parameters
    ----------
    predictions:
        List of dicts with at minimum ``{"id": ..., "type": ..., "answer": ...}``.
    ground_truths:
        Mapping from question id → OfficialAnswer.  Questions absent from this
        dict are ignored.

    Returns
    -------
    dict with keys:
        pa, accuracy, correct, incorrect, abstain, total,
        by_type, by_business (if business_id available in pred dict),
        missing
    """
    pred_map: dict[str, dict] = {}
    for p in predictions:
        pid = str(p.get("id", ""))
        if pid:
            pred_map[pid] = p

    total = correct = incorrect = abstain = 0
    by_type: dict[str, dict[str, int]] = {}
    by_business: dict[str, dict[str, int]] = {}
    missing: list[str] = []

    for qid, gt in ground_truths.items():
        pred = pred_map.get(qid)
        if pred is None:
            # Treat missing predictions as abstain (score = 0)
            pred = {"id": qid, "type": "abstain"}
            missing.append(qid)

        pred_type = str(pred.get("type", "abstain")).lower()
        pred_ans = pred.get("answer")
        biz = str(pred.get("business_id", ""))
        gt_t = gt.type

        total += 1

        if pred_type == "abstain":
            outcome = "abstain"
            abstain += 1
        elif answers_match(pred_ans, pred_type, gt):
            outcome = "correct"
            correct += 1
        else:
            outcome = "incorrect"
            incorrect += 1

        # By-type breakdown
        if gt_t not in by_type:
            by_type[gt_t] = {"total": 0, "correct": 0, "incorrect": 0, "abstain": 0}
        by_type[gt_t]["total"] += 1
        by_type[gt_t][outcome] += 1

        # Per-business breakdown (available when caller enriches predictions)
        if biz:
            if biz not in by_business:
                by_business[biz] = {"total": 0, "correct": 0, "incorrect": 0, "abstain": 0}
            by_business[biz]["total"] += 1
            by_business[biz][outcome] += 1

    pa = (correct - incorrect) / total if total else 0.0
    accuracy = correct / total if total else 0.0

    # Add per-type accuracy and PA
    for t, counts in by_type.items():
        n = counts["total"]
        counts["accuracy"] = round(counts["correct"] / n, 4) if n else 0.0
        counts["pa"] = round((counts["correct"] - counts["incorrect"]) / n, 4) if n else 0.0

    for b, counts in by_business.items():
        n = counts["total"]
        counts["accuracy"] = round(counts["correct"] / n, 4) if n else 0.0
        counts["pa"] = round((counts["correct"] - counts["incorrect"]) / n, 4) if n else 0.0

    return {
        "pa": round(pa, 4),
        "accuracy": round(accuracy, 4),
        "correct": correct,
        "incorrect": incorrect,
        "abstain": abstain,
        "total": total,
        "missing_predictions": len(missing),
        "by_type": by_type,
        "by_business": by_business,
    }
