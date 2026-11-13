"""Protection against a rulebook that differs from the one the templates were written for.

The router's templates encode rulebook rows (valid orders, who counts as a customer, ...).  At inference the running
`rulebook.md` is compared row by row with a reference (`rule_reference.json`: sha256 of the normalised text of every
row of the TRAIN rulebook, no rule text stored).  An intent is disabled when a row it depends on changed or vanished;
rows that did not exist in the reference are reported and, when a question contains all content words of such a row's
name, the question goes to the LLM (a new rule may redefine what the question asks).

`reviewed_rule_changes.json` lists, under "approved", the "<section>|<row>" keys a human has checked as compatible with
the templates (each with a "reason"); those are not treated as changes.  "pending" rows stay switched off.  Nothing is
added there automatically.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from ..timeutil import fold

REFERENCE_PATH = Path(__file__).with_name("rule_reference.json")
REVIEWED_PATH = Path(__file__).with_name("reviewed_rule_changes.json")

_TIME = [("2", n) for n in (
    "ngay x, hom nay, hom qua", "den het ngay x", "tu x den y", "n ngay gan nhat", "tuan", "thang m/y", "thang nay",
    "tu dau nam", "thang m, quy q khong ghi nam")]
_STATUS = [("8", "trang thai don"), ("8", "hai dong cua cung mot don"), ("8", "o de trong o cac dong sau"),
           ("8", "ten goi, nhan")]
_ORDER = [("1", "don tinh vao doanh thu"), ("1", "don thuoc ky nao")] + _STATUS + _TIME
DEPENDENCIES: dict[str, list[tuple[str, str]]] = {
    "revenue": _ORDER + [("1", "ban duoc bao nhieu tien"), ("1", "doanh thu mot don")],
    "order_count": _ORDER + [("1", "so don")],
    "cancel_count": [("1", "don bi huy"), ("1", "don thuoc ky nao")] + _STATUS + _TIME,
    "cancel_rate": [("1", "ti le don huy trong ky"), ("1", "don bi huy"), ("1", "don thuoc ky nao")] + _STATUS + _TIME,
    "aov": _ORDER + [("1", "doanh thu mot don"), ("1", "so don"), ("3", "gia tri trung binh mot don")],
    "best_day": _ORDER + [("1", "doanh thu mot don")],
    "topk_items": _ORDER + [("3", "mat hang"), ("3", "ban chay"), ("10", "don vi co ban")],
    "best_item": _ORDER + [("3", "mat hang"), ("3", "ban chay"), ("10", "don vi co ban")],
    "item_qty": _ORDER + [("3", "mat hang"), ("3", "ban duoc bao nhieu"), ("10", "don vi co ban")],
    "item_revenue": _ORDER + [("1", "ban duoc bao nhieu tien"), ("3", "mat hang")],
    "category_rev": _ORDER + [("1", "ban duoc bao nhieu tien"), ("3", "nhom hang")],
    "sell_price_on_day": [("5", "gia ban x ngay d"), ("10", "don vi co ban")] + _STATUS + [("2", "ngay x, hom nay, hom qua")],
    "rev_change_pct": _ORDER + [("1", "ban duoc bao nhieu tien"), ("1", "doanh thu mot don"),
                                ("1", "phan tram thay doi")],
}
_STOP = {"la", "cua", "va", "cac", "mot", "nhieu", "nhat", "x", "y", "n", "m"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", fold(text.replace("**", "").replace("`", ""))).strip()


def parse_rulebook(text: str) -> dict[str, str]:
    """{"<section>|<folded row name>": normalised row text} for every table row under a numbered section."""
    rows: dict[str, str] = {}
    sec = ""
    for line in text.splitlines():
        m = re.match(r"^##\s+(\d+)\.", line)
        if m:
            sec = m.group(1)
            continue
        if not sec or not line.startswith("|") or re.match(r"^\|\s*-", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or _norm(cells[0]) in ("luat", "cach noi", "type", "tu", "cach ghi"):
            continue
        rows[f"{sec}|{_norm(cells[0])}"] = _norm(" | ".join(cells[1:]))
    return rows


def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def build_reference(rulebook_text: str) -> dict[str, str]:
    return {k: _h(v) for k, v in parse_rulebook(rulebook_text).items()}


def _find(keys, sec: str, prefix: str):
    return [k for k in keys if k.startswith(f"{sec}|") and k.split("|", 1)[1].startswith(prefix)]


def _in_order_close(toks: list[str], words: list[str], max_gap: int = 2) -> bool:
    """All tokens appear in this order, each at most `max_gap` words after the previous one (so "ngay nao dat khach"
    matches the row "Ngày đắt khách nhất" but unrelated words spread over the question do not)."""
    for i, w in enumerate(words):
        if w != toks[0]:
            continue
        pos, ok = i, True
        for t in toks[1:]:
            nxt = next((j for j in range(pos + 1, min(len(words), pos + 2 + max_gap)) if words[j] == t), None)
            if nxt is None:
                ok = False
                break
            pos = nxt
        if ok:
            return True
    return False


def _load_reviewed(path: Path) -> set[str]:
    """Approved keys. Accepts {"approved": [{"key", "reason", ...}], "pending": [...]} or a plain list of keys."""
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("approved", []) if isinstance(data, dict) else data
    return {(x["key"] if isinstance(x, dict) else x) for x in items}


class RuleGuard:
    def __init__(self, reference: dict[str, str], running_text: str, reviewed: set[str] | None = None):
        self.reviewed = reviewed or set()
        run = parse_rulebook(running_text)
        run_h = {k: _h(v) for k, v in run.items()}
        self._running_keys = set(run)
        self.changed = sorted(k for k in run_h if k in reference and run_h[k] != reference[k] and k not in self.reviewed)
        self.removed = sorted(k for k in reference if k not in run_h and k not in self.reviewed)
        self.new = sorted(k for k in run_h if k not in reference and k not in self.reviewed)
        bad = set(self.changed) | set(self.removed)
        self.disabled: dict[str, list[str]] = {}
        for intent, deps in DEPENDENCIES.items():
            hit = sorted({k for sec, pre in deps for k in _find(set(reference) | set(run_h), sec, pre) if k in bad})
            if hit:
                self.disabled[intent] = hit
        self._cues = []
        for k in self.new:
            toks = [t for t in re.findall(r"[a-z0-9]+", k.split("|", 1)[1]) if t not in _STOP and len(t) > 1]
            if len(toks) >= 2:
                self._cues.append((k, toks))

    @classmethod
    def load(cls, running_rulebook: Path | str) -> "RuleGuard":
        ref = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))["rows"]
        rp = Path(os.environ.get("DATAMATE_REVIEWED_RULES") or REVIEWED_PATH)  # env: analysis only
        rev = _load_reviewed(rp)
        return cls(ref, Path(running_rulebook).read_text(encoding="utf-8"), rev)

    def defines(self, sec: str, prefix: str) -> bool:
        """Does the running rulebook still have a row (section, name starting with prefix)?"""
        return any(k.startswith(f"{sec}|{prefix}") for k in self._running_keys)

    def check(self, intent: str, folded_question: str) -> str | None:
        """Reason to leave the question to the LLM, else None."""
        if intent in self.disabled:
            return f"rulebook_changed:{intent}<-{';'.join(self.disabled[intent])}"
        words = re.findall(r"[a-z0-9]+", folded_question)
        for key, toks in self._cues:
            if _in_order_close(toks, words):
                return f"new_rule_cue:{key}"
        return None

    def report(self) -> dict[str, Any]:
        return {"changed": self.changed, "removed": self.removed, "new": self.new, "disabled_intents": self.disabled}
