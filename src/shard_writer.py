"""Submission written shop by shop, complete and valid at every moment.

A slow run (the LLM voting k times per question) can be killed by a time limit.  `submission.jsonl` is therefore never a
half-written stream: from the first second it holds one line for EVERY question (abstain until answered), in the order of
questions.jsonl, and it is rewritten atomically (temporary file + rename) when a shop is finished and every
`checkpoint_every` answers.  The answers of each finished shop are also kept in `by_shop/<shop>.jsonl`.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class ShardedSubmission:
    def __init__(self, result_dir: Path | str, questions: list[tuple[str, str]], checkpoint_every: int = 25):
        """questions: [(question id, shop id)] in the order of questions.jsonl."""
        self.dir = Path(result_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "by_shop").mkdir(exist_ok=True)
        self.path = self.dir / "submission.jsonl"
        self.order = [q for q, _ in questions]
        self.shop_of = dict(questions)
        self.answers: dict[str, dict[str, Any]] = {}
        self.checkpoint_every = max(1, checkpoint_every)
        self._since = 0
        self._write_all()

    @classmethod
    def from_questions_file(cls, questions_file: Path | str, result_dir: Path | str, checkpoint_every: int = 25) -> "ShardedSubmission":
        qs = []
        for line in Path(questions_file).read_text(encoding="utf-8").splitlines():
            if line.strip():
                q = json.loads(line)
                qs.append((str(q["id"]), str(q.get("business_id", ""))))
        return cls(result_dir, qs, checkpoint_every)

    def _atomic_write(self, path: Path, lines: list[str]) -> None:
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("".join(l + "\n" for l in lines))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def _line(self, qid: str) -> str:
        return json.dumps(self.answers.get(qid) or {"id": qid, "type": "abstain"}, ensure_ascii=False, default=str)

    def _write_all(self) -> None:
        self._atomic_write(self.path, [self._line(q) for q in self.order])
        self._since = 0

    def add(self, answer: dict[str, Any]) -> None:
        """Record the answer of one question (a line without a known id is ignored: the placeholder abstain stays)."""
        qid = str(answer.get("id", ""))
        if qid not in self.shop_of:
            return
        self.answers[qid] = answer
        self._since += 1
        if self._since >= self.checkpoint_every:
            self._write_all()

    def finish_shop(self, shop: str) -> None:
        ids = [q for q in self.order if self.shop_of[q] == shop]
        self._atomic_write(self.dir / "by_shop" / f"{shop}.jsonl", [self._line(q) for q in ids])
        self._write_all()

    def done(self) -> int:
        return len(self.answers)
