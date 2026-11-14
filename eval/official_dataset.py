"""Loader for the official Zalo AI Challenge DataMate datasets.

Provides clean separation between:
  - questions (fed to the Agent during inference)
  - ground-truth answers (kept exclusively in the evaluation layer)

Supports both the train split (has answers.jsonl) and the public_test split
(no answers — predictions only).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


# ── Schema definitions ────────────────────────────────────────────────────

@dataclass
class OfficialQuestion:
    """One question record from questions.jsonl."""
    id: str
    business_id: str
    question: str
    as_of_date: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "business_id": self.business_id,
            "question": self.question,
            "as_of_date": self.as_of_date,
        }


@dataclass
class OfficialAnswer:
    """One answer record from answers.jsonl (ground truth — never shown to agent)."""
    id: str
    type: str
    answer: Any
    alias: list[Any] = field(default_factory=list)


# ── Dataset loader ────────────────────────────────────────────────────────

class OfficialDataset:
    """Loads and validates an official DataMate split directory.

    The expected directory layout is::

        <root>/
            questions.jsonl      # always present
            answers.jsonl        # train split only; absent for public_test
            calendar.csv         # shared lunar calendar
            rulebook.md          # scoring rules
            data/
                <business_id>/
                    README.md
                    *.csv / *.xlsx / *.sqlite

    Parameters
    ----------
    root:
        Path to the split root (e.g. ``train/`` or ``public_test/``).
    split:
        Human-readable label stored in diagnostics (``"train"`` or
        ``"public_test"``).  Inferred from *root* name when not supplied.
    """

    def __init__(self, root: str | Path, split: str | None = None) -> None:
        self.root = Path(root)
        if not self.root.is_dir():
            raise FileNotFoundError(f"Dataset root not found: {self.root}")

        self.split = split or self.root.name  # e.g. "train" or "public_test"

        # Mandatory files
        self.questions_path = self.root / "questions.jsonl"
        if not self.questions_path.is_file():
            raise FileNotFoundError(f"questions.jsonl not found: {self.questions_path}")

        self.answers_path = self.root / "answers.jsonl"
        self.has_answers = self.answers_path.is_file()

        self.calendar_path = self.root / "calendar.csv"
        self.rulebook_path = self.root / "rulebook.md"
        self.data_dir = self.root / "data"
        if not self.data_dir.is_dir():
            raise FileNotFoundError(f"data/ directory not found: {self.data_dir}")

        self._questions: list[OfficialQuestion] | None = None
        self._answers: dict[str, OfficialAnswer] | None = None

    # ── Loading ──────────────────────────────────────────────────────────

    def _load_questions(self) -> list[OfficialQuestion]:
        questions: list[OfficialQuestion] = []
        with self.questions_path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"{self.questions_path}:{lineno}: JSON decode error: {exc}"
                    ) from exc
                missing = {k for k in ("id", "business_id", "question", "as_of_date") if k not in obj}
                if missing:
                    raise ValueError(
                        f"{self.questions_path}:{lineno}: missing fields: {missing}"
                    )
                questions.append(
                    OfficialQuestion(
                        id=str(obj["id"]),
                        business_id=str(obj["business_id"]),
                        question=str(obj["question"]),
                        as_of_date=str(obj["as_of_date"]),
                    )
                )
        return questions

    def _load_answers(self) -> dict[str, OfficialAnswer]:
        if not self.has_answers:
            return {}
        answers: dict[str, OfficialAnswer] = {}
        with self.answers_path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"{self.answers_path}:{lineno}: JSON decode error: {exc}"
                    ) from exc
                if "id" not in obj or "type" not in obj:
                    raise ValueError(
                        f"{self.answers_path}:{lineno}: missing id or type"
                    )
                ans = OfficialAnswer(
                    id=str(obj["id"]),
                    type=str(obj["type"]),
                    answer=obj.get("answer"),
                    alias=obj.get("alias") or [],
                )
                answers[ans.id] = ans
        return answers

    # ── Public accessors ─────────────────────────────────────────────────

    @property
    def questions(self) -> list[OfficialQuestion]:
        if self._questions is None:
            self._questions = self._load_questions()
        return self._questions

    @property
    def answers(self) -> dict[str, OfficialAnswer]:
        """Ground-truth answers keyed by question id.  Empty for public_test."""
        if self._answers is None:
            self._answers = self._load_answers()
        return self._answers

    def business_ids(self) -> list[str]:
        return sorted({q.business_id for q in self.questions})

    def filter_questions(
        self,
        limit: int | None = None,
        business_ids: list[str] | None = None,
    ) -> list[OfficialQuestion]:
        qs = self.questions
        if business_ids:
            ids_set = set(business_ids)
            qs = [q for q in qs if q.business_id in ids_set]
        if limit is not None:
            qs = qs[:limit]
        return qs

    def iter_pairs(
        self,
        limit: int | None = None,
        business_ids: list[str] | None = None,
    ) -> Iterator[tuple[OfficialQuestion, OfficialAnswer | None]]:
        """Yield (question, answer_or_none) pairs for evaluation.

        The caller is responsible for keeping answers out of the agent's reach.
        """
        for q in self.filter_questions(limit=limit, business_ids=business_ids):
            gt = self.answers.get(q.id) if self.has_answers else None
            yield q, gt

    def validate(self) -> list[str]:
        """Return a list of warning messages (empty = all OK)."""
        warnings: list[str] = []
        q_ids = {q.id for q in self.questions}

        if self.has_answers:
            a_ids = set(self.answers.keys())
            only_q = q_ids - a_ids
            only_a = a_ids - q_ids
            if only_q:
                warnings.append(f"{len(only_q)} question IDs have no answer entry")
            if only_a:
                warnings.append(f"{len(only_a)} answer entries have no question")

        for biz_id in self.business_ids():
            biz_dir = self.data_dir / biz_id
            if not biz_dir.is_dir():
                warnings.append(f"Missing data directory: {biz_dir}")
            elif not (biz_dir / "README.md").is_file():
                warnings.append(f"Missing README.md for {biz_id}")

        if not self.calendar_path.is_file():
            warnings.append("calendar.csv not found — lunar date queries will fail")

        if not self.rulebook_path.is_file():
            warnings.append("rulebook.md not found")

        return warnings

    def __repr__(self) -> str:
        q = len(self.questions)
        a = len(self.answers)
        biz = len(self.business_ids())
        return (
            f"OfficialDataset(split={self.split!r}, questions={q}, "
            f"answers={a}, businesses={biz})"
        )
