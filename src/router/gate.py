"""Abstain gate for the LLM route: which kinds of question the LLM may answer, decided from a measured run.

`eval/llm_gate.py` writes the config (`src/router/llm_gate.json` by default) from a harness run on the hold-out shops.
At inference, `DATAMATE_LLM_GATE=<path>` switches the gate on: a question that falls to the LLM is answered only when
its gate key is in "enabled"; every other key (including keys never seen in the measured run) abstains.  Without the
variable the LLM answers everything (so that a run can be measured).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def gate_key(decision: Any) -> str:
    """Kind of question for gating: the tagger label of a not-target question, else the router intent, else the reason."""
    reason = decision.reason or ""
    if reason.startswith("not_target:"):
        return reason.split(":", 1)[1].strip() or "unknown"
    if decision.intent:
        return decision.intent
    return reason.split(":")[0].strip() or "unknown"


def load_gate(path: Path | str | None) -> dict[str, Any] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def llm_allowed(gate: dict[str, Any] | None, key: str) -> bool:
    return True if gate is None else key in set(gate.get("enabled", []))
