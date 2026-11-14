"""Official scoring logic for the Zalo AI Challenge DataMate competition.

Implements the scoring rules from rulebook.md §9:
  - Correct answer  → +1
  - Wrong answer    → -1
  - Abstain         →  0
  - PA = (correct - incorrect) / total

Comparison rules per type (from rulebook §9):
  number  : JSON number only (rulebook §9: string "4820000" is explicitly wrong).
            Tolerance: math.isclose(rel_tol=1e-9, abs_tol=1e-9) — covers genuine
            IEEE 754 float-repr error (~2e-12) but rejects values differing by 0.3+.
  percent : JSON number only.  Agents must round to 2 dp before submitting
            (rulebook §9: "làm tròn 2 chữ số thập phân").  Scorer rounds the
            prediction to 2 dp then applies 1e-9 float tolerance.
  boolean : JSON true/false only.  Rulebook §9 explicitly marks "1" and "có" wrong.
  string  : case/whitespace/punctuation-insensitive (rulebook §9: "không phân biệt
            hoa thường, khoảng trắng, dấu câu"); Vietnamese diacritics kept
            ("ngoài các cách viết đó, dấu tiếng Việt phải đúng").
  date    : exact string match ("YYYY-MM-DD" or "YYYY-MM")
  list    : order-sensitive; numeric elements need JSON number type (not string);
            string elements matched by string rules + per-element alias.
  table   : row-order independent (rulebook: "Thứ tự các dòng không ảnh hưởng");
            columns matched by name first, then by position (rulebook: "Cột so
            theo tên; tên không khớp thì so theo vị trí"); first column matched
            with per-row alias; numeric cells need JSON number type.

Ground-truth answers must stay inside this module during inference; they are
only accessed via score_submission() after all predictions are collected.
"""
from __future__ import annotations

import math
import unicodedata
from typing import Any

from .official_dataset import OfficialAnswer


# ── String normalisation ──────────────────────────────────────────────────

def _norm(s: Any) -> str:
    """Case-, whitespace- and punctuation-insensitive; Vietnamese diacritics kept.

    Rulebook §9: "không phân biệt hoa thường, khoảng trắng, dấu câu".
    NFC-normalise then casefold; keep only Unicode Letter/Number/Mark code points
    so punctuation and separators are stripped while diacritical marks are kept.
    """
    s = unicodedata.normalize("NFC", str(s)).casefold()
    return "".join(c for c in s if unicodedata.category(c)[0] in "LNM")


def _str_eq(pred: Any, gt: Any) -> bool:
    return _norm(pred) == _norm(gt)


def _str_matches(pred: Any, gt: Any, aliases: list[Any]) -> bool:
    """Return True if pred equals gt or any alias (after normalisation)."""
    pn = _norm(pred)
    if pn == _norm(gt):
        return True
    for a in aliases:
        if pn == _norm(a):
            return True
    return False


# ── Type guard ────────────────────────────────────────────────────────────

def _is_num(v: Any) -> bool:
    """True if v is a JSON numeric value (int or float, not bool, not NaN/Inf)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


# ── Per-type comparison ───────────────────────────────────────────────────

def _cmp_number(pred: Any, gt: Any) -> bool:
    # Rulebook §9: JSON number only. String "4820000" is explicitly wrong.
    if not _is_num(pred):
        return False
    if not _is_num(gt):
        return False
    # "tiền đúng từng đồng" — exact match; 1e-9 rel+abs tolerance covers float repr.
    return math.isclose(float(pred), float(gt), rel_tol=1e-9, abs_tol=1e-9)


def _cmp_percent(pred: Any, gt: Any) -> bool:
    # Rulebook §9: JSON number only ("12,4%" and 0.124 are explicitly wrong).
    if not _is_num(pred):
        return False
    if not _is_num(gt):
        return False
    # Agents must round to 2 dp (rulebook §9: "làm tròn 2 chữ số thập phân").
    # Round pred first, then 1e-9 tolerance covers float repr of the rounded value.
    return math.isclose(round(float(pred), 2), float(gt), rel_tol=1e-9, abs_tol=1e-9)


def _cmp_boolean(pred: Any, gt: Any) -> bool:
    # Rulebook §9: boolean answer is JSON true/false only.
    # Explicitly wrong: "có", 1 — do NOT coerce strings or integers.
    if not isinstance(pred, bool):
        return False
    if not isinstance(gt, bool):
        return False
    return pred == gt


def _cmp_date(pred: Any, gt: Any) -> bool:
    return str(pred).strip() == str(gt).strip()


def _cmp_list(pred: Any, gt: Any, alias: list[Any]) -> bool:
    """Order-sensitive list comparison with per-element aliases."""
    if not isinstance(pred, list) or not isinstance(gt, list):
        return False
    if len(pred) != len(gt):
        return False
    for i, (p, g) in enumerate(zip(pred, gt)):
        elem_aliases: list[Any] = []
        if alias and i < len(alias):
            raw = alias[i]
            elem_aliases = raw if isinstance(raw, list) else [raw]
        if _is_num(g):
            # Gold element is a JSON number — pred must also be a JSON number.
            if not _is_num(p):
                return False
            if not math.isclose(float(p), float(g), rel_tol=1e-9, abs_tol=1e-9):
                return False
        else:
            if not _str_matches(p, g, elem_aliases):
                return False
    return True


def _cmp_table(pred: Any, gt: Any, alias: list[Any]) -> bool:
    """Row-order-independent table comparison.

    Columns are matched by name first, then by position (rulebook §9: "Cột so
    theo tên; tên không khớp thì so theo vị trí").  Row order is irrelevant
    (rulebook §9: "Thứ tự các dòng không ảnh hưởng kết quả chấm").

    alias is a list of per-row alternatives for the first (name/ID) column.
    """
    if not isinstance(pred, dict) or not isinstance(gt, dict):
        return False

    pred_rows: list = pred.get("rows") or []
    gt_rows: list = gt.get("rows") or []
    pred_col_names = [_norm(c) for c in (pred.get("columns") or [])]
    gt_col_names = [_norm(c) for c in (gt.get("columns") or [])]

    if len(pred_rows) != len(gt_rows):
        return False

    n_gt_cols = len(gt_col_names)

    # Build column index remapping: col_order[j] = index in pred_row for gt col j.
    # Rulebook: match by name; fall back to position when names don't align.
    if (
        pred_col_names
        and gt_col_names
        and len(set(gt_col_names)) == len(gt_col_names)  # gt names unique
        and all(n in pred_col_names for n in gt_col_names)  # all gt names present in pred
    ):
        try:
            col_order = [pred_col_names.index(n) for n in gt_col_names]
        except ValueError:
            col_order = list(range(n_gt_cols))
    else:
        col_order = list(range(n_gt_cols))

    def _reorder(row: list) -> list:
        return [row[i] if i < len(row) else None for i in col_order]

    # Row-order-independent matching via first-column value or alias.
    # Use a set of matched gold indices to handle tables where two rows share the
    # same first-column text (duplicates are legitimate in some business datasets).
    matched_gt: set[int] = set()

    for pred_row in pred_rows:
        if not isinstance(pred_row, list) or not pred_row:
            return False

        reordered = _reorder(pred_row)
        pk = _norm(reordered[0])

        hit = -1
        for gi, gt_row in enumerate(gt_rows):
            if gi in matched_gt or not gt_row:
                continue
            # First-column match: canonical value or any alias for this row.
            row_aliases: list[Any] = []
            if alias and gi < len(alias):
                raw = alias[gi]
                row_aliases = raw if isinstance(raw, list) else [raw]
            first_col_ok = pk == _norm(gt_row[0]) or any(
                pk == _norm(a) for a in row_aliases
            )
            if not first_col_ok:
                continue
            # First column matched — check remaining columns.
            if _cmp_data_row(reordered, gt_row, n_gt_cols):
                hit = gi
                break

        if hit < 0:
            return False
        matched_gt.add(hit)

    return len(matched_gt) == len(gt_rows)


def _cmp_data_row(pred_row: list, gt_row: list, n_cols: int) -> bool:
    """Compare non-first columns of a matched table row pair."""
    for col_i in range(1, min(n_cols, len(gt_row))):
        if col_i >= len(pred_row) or pred_row[col_i] is None:
            return False
        pv = pred_row[col_i]
        gv = gt_row[col_i]
        if _is_num(gv):
            if not _is_num(pv):
                return False
            if math.isnan(float(pv)) or math.isnan(float(gv)):
                return False
            if not math.isclose(float(pv), float(gv), rel_tol=1e-9, abs_tol=1e-9):
                return False
        else:
            if not _str_eq(pv, gv):
                return False
    return True


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

        if gt_t not in by_type:
            by_type[gt_t] = {"total": 0, "correct": 0, "incorrect": 0, "abstain": 0}
        by_type[gt_t]["total"] += 1
        by_type[gt_t][outcome] += 1

        if biz:
            if biz not in by_business:
                by_business[biz] = {"total": 0, "correct": 0, "incorrect": 0, "abstain": 0}
            by_business[biz]["total"] += 1
            by_business[biz][outcome] += 1

    pa = (correct - incorrect) / total if total else 0.0
    accuracy = correct / total if total else 0.0

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
