"""Rule layer of question normalization (no model).

    nq = normalize("check gium hoom qua dthu cuwar hàng la bn", "2026-09-07", calendar)
    nq.text   -> "check giùm hôm qua doanh thu của hàng là bao nhiêu"   (telex + teencode fixed)
    nq.flags  -> e.g. ["partial_no_diacritics"]  -> nq.needs_llm tells the pipeline to call the LLM layer

Steps: Unicode NFC -> telex typo repair -> teencode dictionary -> flags -> period resolution.
Resources (src/nlu/resources/*.json) are built from DEV-shop question text by
scripts/build_nlu_resources.py.  No business_id / question_id logic.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..timeutil import LunarCalendar, ResolveResult, resolve

_RES = Path(__file__).parent / "resources"
_WORD = re.compile(r"\b[^\W\d_]+\b")
_VOWELS = "aăâeêioôơuưy"
_TONES = {"s": "́", "f": "̀", "r": "̉", "x": "̃", "j": "̣"}
_UNITS = {"ml", "mg", "kg", "mm", "cm", "pvc", "cod", "oa", "xl", "xxl", "gb", "tb", "g", "l", "m", "s", "x", "ly",
          "vnd", "tmđt", "tmdt", "sku"}
_TELEX_MARK = re.compile(r"aa|ee|oo|dd|uw|ow|aw")
_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_DATE = re.compile(r"\d{1,2}\s*[/-]\s*\d{1,2}(?:\s*[/-]\s*\d{2,4})?")


def fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower().replace("đ", "d").replace("Đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def has_diacritics(s: str) -> bool:
    return any(c == "đ" or unicodedata.category(c) == "Mn" for c in unicodedata.normalize("NFD", s.lower()))


@lru_cache(maxsize=1)
def _resources() -> dict[str, Any]:
    vocab = json.loads((_RES / "vocab.json").read_text(encoding="utf-8"))
    tc = json.loads((_RES / "teencode.json").read_text(encoding="utf-8"))["map"]
    words = vocab["words"]
    fold_words = {fold(w) for w in words}
    return {"words": words, "fold_words": fold_words, "suspect": set(vocab["noaccent_suspect"]), "teencode": tc}


# ---------------------------------------------------------------- telex
def telex_decode(token: str) -> str | None:
    """Decode a telex-typed Vietnamese word ('dduwowcj' -> 'được'); None if it is not valid telex."""
    w = token.lower()
    tone = None
    if len(w) >= 3 and w[-1] in _TONES:  # tone key is typed at the end of the word, after the final consonant
        tone, w = w[-1], w[:-1]
    w = w.replace("uwow", "ươ").replace("uow", "ươ").replace("dd", "đ")
    for a, b in (("aa", "â"), ("ee", "ê"), ("oo", "ô"), ("aw", "ă"), ("ow", "ơ"), ("uw", "ư")):
        w = w.replace(a, b)
    if any(c in w for c in "wfjz"):  # leftover telex keys: not a valid Vietnamese syllable
        return None
    if tone:
        w = _place_tone(w, _TONES[tone])
        if w is None:
            return None
    return unicodedata.normalize("NFC", w)


def _place_tone(w: str, mark: str) -> str | None:
    i = 0
    if w.startswith(("qu", "gi")) and len(w) > 2 and w[2] in _VOWELS:
        i = 2  # u of "qu" / i of "gi" belong to the onset
    while i < len(w) and w[i] not in _VOWELS:  # skip the initial consonants
        i += 1
    j = i
    while j < len(w) and w[j] in _VOWELS:
        j += 1
    nucleus = list(range(i, j))
    if not nucleus:
        return None
    modified = [k for k in nucleus if w[k] in "ăâêôơư"]
    if modified:
        k = modified[-1]
    elif len(nucleus) == 1:
        k = nucleus[0]
    elif len(nucleus) == 2:
        closed = j < len(w)
        pair = w[nucleus[0]] + w[nucleus[1]]
        k = nucleus[1] if (closed or pair in ("oa", "oe", "uy")) else nucleus[0]
    else:
        k = nucleus[1]
    return unicodedata.normalize("NFC", w[:k + 1] + mark + w[k + 1:])


# ---------------------------------------------------------------- data class
@dataclass
class NormalizedQuestion:
    text: str
    original: str
    period: ResolveResult
    entities: dict[str, list[str]]
    flags: list[str] = field(default_factory=list)
    changes: list[tuple[str, str]] = field(default_factory=list)

    @property
    def needs_llm(self) -> bool:
        """Rule layer left diacritic-less or teencode-looking text: LLM layer may rewrite it."""
        return bool({"no_diacritics", "partial_no_diacritics", "residual_teencode"} & set(self.flags))


def extract_entities(text: str) -> dict[str, list[str]]:
    dates = [m.group(0) for m in _DATE.finditer(text)]
    rest = _DATE.sub(" ", text)
    return {"numbers": [m.group(0) for m in _NUM.finditer(rest)], "dates": dates,
            "quoted": re.findall(r"[\"“'‘]([^\"”'’]+)[\"”'’]", text)}


# ---------------------------------------------------------------- main
def _keep_case(src: str, out: str) -> str:
    return out[:1].upper() + out[1:] if src[:1].isupper() else out


def fix_tokens(text: str) -> tuple[str, list[tuple[str, str]]]:
    res = _resources()
    changes: list[tuple[str, str]] = []

    def repl(m: re.Match) -> str:
        tok = m.group(0)
        low = tok.lower()
        if low in res["teencode"]:
            out = _keep_case(tok, res["teencode"][low])
        elif low in res["words"] or low in res["fold_words"] or len(low) < 2:
            return tok
        else:
            dec = telex_decode(low)
            if dec is None or dec == low or len(low) < 3:
                return tok
            cnt = res["words"].get(dec, 0)
            # explicit modifier pairs (ee, uw, dd, ...) are strong evidence; bare tone keys need a common word
            if cnt < (2 if _TELEX_MARK.search(low) else 20):
                return tok
            out = _keep_case(tok, dec)
        changes.append((tok, out))
        return out

    return _WORD.sub(repl, text), changes


def compute_flags(text: str, original: str) -> list[str]:
    res = _resources()
    toks = _WORD.findall(text)
    flags: list[str] = []
    alpha = [t.lower() for t in toks]
    plain = [t for t in alpha if t in res["suspect"] and t not in res["words"]]
    if not has_diacritics(text) and len(plain) >= 2:
        flags.append("no_diacritics")
    elif len(plain) >= 2 and len(plain) / max(1, len(alpha)) >= 0.3:
        flags.append("partial_no_diacritics")
    orig_caps = {t.lower() for t in _WORD.findall(original) if t[:1].isupper()}
    for t in alpha:
        if t in orig_caps or t in _UNITS or t in res["words"] or t in res["fold_words"] or len(t) < 2:
            continue
        if (not re.search("[aeiouy]", fold(t)) and len(t) >= 2) or _TELEX_MARK.search(t):
            flags.append("residual_teencode")
            break
    return flags


def normalize(question: str, as_of: str | date | None = None, calendar: LunarCalendar | None = None,
              short_slash: str | None = None, tet_bare: bool = True) -> NormalizedQuestion:
    original = question
    text = unicodedata.normalize("NFC", question)
    text = re.sub(r"\s+", " ", text).strip()
    text, changes = fix_tokens(text)
    flags = compute_flags(text, original)
    period = resolve(text, as_of, calendar, short_slash, tet_bare) if as_of else ResolveResult()
    return NormalizedQuestion(text=text, original=original, period=period, entities=extract_entities(original),
                              flags=flags, changes=changes)


class RuleNormalizer:
    """Callable wrapper used by Agent: binds the lunar calendar once."""

    def __init__(self, calendar_path: str | Path | None = None, short_slash: str | None = None, tet_bare: bool = True):
        self.tet_bare = tet_bare
        self.calendar = LunarCalendar(calendar_path) if calendar_path and Path(calendar_path).is_file() else None
        self.short_slash = short_slash

    def __call__(self, question: str, as_of: str | date | None) -> NormalizedQuestion:
        return normalize(question, as_of, self.calendar, self.short_slash, self.tet_bare)
