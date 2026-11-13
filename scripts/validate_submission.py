"""Validate submission.jsonl against the official DataMate submission schema.

Checks (all from rulebook §9 and make_router_submission.py's valid_line):
  1. Every question ID in questions.jsonl is present in submission.jsonl.
  2. No duplicate IDs.
  3. No extra IDs not in questions.jsonl.
  4. Each line is valid JSON.
  5. Each line has 'id' and 'type'.
  6. 'type' is one of: number, percent, string, date, boolean, list, table,
     unanswerable, abstain.
  7. abstain lines have EXACTLY {"id", "type"} — no extra fields.
  8. unanswerable lines have a string 'reason' field.
  9. number/percent 'answer' is a finite float/int (not bool).
 10. list 'answer' is a list.
 11. table 'answer' is a dict with 'rows' (list of lists).
 12. boolean 'answer' is True/False.
 13. date 'answer' matches YYYY-MM-DD or YYYY-MM.

Usage:
    python3 scripts/validate_submission.py submission.jsonl questions.jsonl

Exit 0 on success, 1 on any validation failure.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

VALID_TYPES = {"number", "percent", "string", "date", "boolean", "list", "table", "unanswerable", "abstain"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")


def _check_line(a: dict) -> str | None:
    """Return None if the line is valid, else a short problem description."""
    if "id" not in a:
        return "missing 'id'"
    if "type" not in a:
        return "missing 'type'"
    t = a["type"]
    if t not in VALID_TYPES:
        return f"invalid type {t!r}"
    if t == "abstain":
        extra = set(a) - {"id", "type"}
        if extra:
            return f"abstain with extra fields: {extra}"
        return None
    if t == "unanswerable":
        if not isinstance(a.get("reason"), str):
            return "unanswerable without string 'reason'"
        return None
    # Answerable types require 'answer'
    if "answer" not in a:
        return f"type={t!r} missing 'answer'"
    v = a["answer"]
    if t in ("number", "percent"):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return f"{t} answer must be numeric, got {type(v).__name__}"
        if not math.isfinite(v):
            return f"{t} answer is not finite: {v}"
    elif t == "boolean":
        if not isinstance(v, bool):
            return f"boolean answer must be True/False, got {v!r}"
    elif t == "list":
        if not isinstance(v, list):
            return f"list answer must be a list, got {type(v).__name__}"
    elif t == "table":
        if not isinstance(v, dict) or not isinstance(v.get("rows"), list):
            return "table answer must be a dict with 'rows' list"
    elif t == "date":
        if not isinstance(v, str) or not _DATE_RE.match(v):
            return f"date answer must match YYYY-MM-DD or YYYY-MM, got {v!r}"
    return None


def validate(submission_path: Path, questions_path: Path) -> list[str]:
    """Return a list of error strings (empty = all OK)."""
    errors: list[str] = []

    # Load expected IDs
    try:
        expected_ids: list[str] = []
        with questions_path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    q = json.loads(line)
                    expected_ids.append(str(q["id"]))
                except (json.JSONDecodeError, KeyError) as exc:
                    errors.append(f"questions.jsonl:{lineno}: {exc}")
        expected_set = set(expected_ids)
    except FileNotFoundError:
        errors.append(f"questions.jsonl not found: {questions_path}")
        return errors

    # Load and validate predictions
    seen_ids: list[str] = []
    with submission_path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                a = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"submission.jsonl:{lineno}: JSON decode error: {exc}")
                continue
            qid = str(a.get("id", ""))
            if not qid:
                errors.append(f"submission.jsonl:{lineno}: empty or missing 'id'")
                continue
            seen_ids.append(qid)
            problem = _check_line(a)
            if problem:
                errors.append(f"submission.jsonl:{lineno} id={qid!r}: {problem}")

    seen_set = set(seen_ids)

    # Duplicate check
    if len(seen_ids) != len(seen_set):
        from collections import Counter
        dupes = [qid for qid, cnt in Counter(seen_ids).items() if cnt > 1]
        errors.append(f"Duplicate prediction IDs ({len(dupes)}): {dupes[:5]}")

    # Coverage check
    missing = sorted(expected_set - seen_set)
    if missing:
        errors.append(
            f"{len(missing)} question IDs have no prediction: "
            f"{missing[:5]}{'...' if len(missing) > 5 else ''}"
        )

    # Extra ID check
    extra = sorted(seen_set - expected_set)
    if extra:
        errors.append(
            f"{len(extra)} prediction IDs not in questions.jsonl: "
            f"{extra[:5]}{'...' if len(extra) > 5 else ''}"
        )

    return errors


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: python3 {sys.argv[0]} submission.jsonl questions.jsonl", file=sys.stderr)
        sys.exit(1)

    submission_path = Path(sys.argv[1])
    questions_path = Path(sys.argv[2])

    if not submission_path.is_file():
        print(f"ERROR: submission file not found: {submission_path}", file=sys.stderr)
        sys.exit(1)
    if not questions_path.is_file():
        print(f"ERROR: questions file not found: {questions_path}", file=sys.stderr)
        sys.exit(1)

    errors = validate(submission_path, questions_path)
    sub_lines = sum(1 for l in submission_path.read_text(encoding="utf-8").splitlines() if l.strip())
    q_lines = sum(1 for l in questions_path.read_text(encoding="utf-8").splitlines() if l.strip())

    print(f"Submission : {submission_path}  ({sub_lines} lines)")
    print(f"Questions  : {questions_path}  ({q_lines} questions)")

    if errors:
        print(f"\nFAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    else:
        print(f"\nOK — all {sub_lines} predictions are valid.")


if __name__ == "__main__":
    main()
