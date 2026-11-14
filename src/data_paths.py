"""Locate the official train / public_test folders on a developer machine.

Official layout (scripts/download_data.sh, docs/TEAM_HANDOFF.md):
    data/train/train/{questions.jsonl, answers.jsonl, rulebook.md, calendar.csv, data/biz_*}
    data/public_test/public_test/{questions.jsonl, rulebook.md, calendar.csv, data/dev_*}
Older checkouts unzipped one level higher (`data/train/{...}`); both are accepted.
Environment overrides: `ZAIC_TRAIN_DIR`, `ZAIC_PUBLIC_DIR`.
Only used by tests and analysis scripts; the submission reads `/data` via predict.py.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _resolve(env_var: str, name: str) -> Path:
    env = os.environ.get(env_var, "").strip()
    if env:
        return Path(env)
    nested = ROOT / "data" / name / name
    if (nested / "data").is_dir():
        return nested
    return ROOT / "data" / name


def train_dir() -> Path:
    """Folder holding `questions.jsonl` and `data/biz_*` for the train split."""
    return _resolve("ZAIC_TRAIN_DIR", "train")


def public_test_dir() -> Path:
    """Folder holding `questions.jsonl` and `data/dev_*` for the public test split."""
    return _resolve("ZAIC_PUBLIC_DIR", "public_test")
