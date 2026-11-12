"""Intent recognition and parameter extraction on the normalized question (rules only, no model).

Recognition = the winner of the first-match rules of `_tagger_rules` (which rejects every non-target family),
confirmed by the target-family detectors below (several competing target intents -> not routed), and the
"extra filter / sub-intent" rejections taken from `scripts/analysis/rule_regression.py::should_skip_question`
(feat/p3-data-cleaning, author: Nghiep; regexes copied, NEEDS REVIEW BY THE AUTHOR).
"""
from __future__ import annotations

import re
from typing import Any

from ..timeutil import fold
from . import _tagger_rules as T
from ..views import item_match_key

TARGET_INTENTS = (
    "revenue", "order_count", "cancel_count", "cancel_rate", "aov",
    "best_day", "topk_items", "best_item", "item_qty", "rev_change_pct",
)
_RULE_RX = dict(T.RULES)
GENERIC = {"revenue"}  # may co-occur with a more specific intent ("doanh thu ... tang bao nhieu %")
# The tagger rules are ordered specific -> general, so a general rule always also matches a specific question
# ("ti le huy %" also matches cancel_count and the % rule).  Only these co-matches are tolerated.
COMPAT = {"cancel_rate": {"cancel_count", "rev_change_pct"}, "cancel_count": {"order_count"},
          "topk_items": {"best_item"}, "best_item": {"topk_items"}, "rev_change_pct": set()}


def prepare(text: str) -> str:
    """Accent-stripped, lower-cased text with the tagger's light repairs (applied to already normalized text)."""
    return T.deacc(fold(text))


def recognise(s: str) -> tuple[str | None, str]:
    """-> (intent or None, reason)."""
    first = T.tag(s)
    if first not in TARGET_INTENTS:
        return None, f"not_target:{first}"
    rivals = [n for n in TARGET_INTENTS if n != first and n not in GENERIC and n not in COMPAT.get(first, ()) and re.search(_RULE_RX[n], s)]
    if rivals:
        return None, "multi_intent:" + "+".join([first] + rivals)
    if first == "topk_items" and topk_k(s) is None:
        first = "best_item"  # the tagger reads the digits of "2026 mat hang" as k; the question has no k
    return first, "ok"


_SKIP: dict[str, str] = {
    "revenue": (r"nhom|khach|\bdon\b|bill|\bca\b|nhan vien|tra bang|so voi|%|phan tram|ngay|hoat chat|ke don|"
                r"size|trung binh|binh quan|moi|quy|mat hang|mon |ban chay|top|xu huong|luon cao hon|con no|cong no|"
                r"(?:doanh thu|dthu) (?:cua|cuar) (?!cua hang)"),
    "order_count": r"khach|nhom|nhan vien|kenh|\bca\b|mat hang|san pham|mon ",
    "cancel_count": r"giao tre|ly do|nguyen nhan|khach|nhom|nhan vien|kenh|\bca\b",
    "cancel_rate": r"khach|nhom|nhan vien|kenh|\bca\b",
    "aov": r"khach|nhom|nhan vien|kenh|\bca\b",
    "best_day": r"khach|nhom|nhan vien|kenh|\bca\b",
    "topk_items": (r"thu ve|bao nhieu tien|bn tien|bnhiu tien|"
                   r"ban (duoc|dc|ra) (tong cong |total )?(bao nhieu|bnhiu|bn|nhieu|may)|"
                   r"\be\b|khong ban|nhom|khach|kenh"),
    "item_qty": r"hon hay kem|%|phan tram|khach|nhom|kenh|\bca\b",
    "rev_change_pct": (r"khach|mua tu \d+ don|gia bao nhieu|ban ra|ban (?:duoc|dc) (?:may|bao nhieu|bnhiu|bn)|"
                       r"nhom|kenh|\bca\b"),
}
_SKIP["best_item"] = _SKIP["topk_items"]
# revenue also: item-specific revenue ("ban <mat hang> ... bao nhieu tien")
_ITEM_REV = re.compile(r"\b(ban|bans)\b")
_ITEM_REV_OK = re.compile(r"cua\s*\w*\s+hang\s*\w*\s+(?:ban|bans)\s+\S+\s+(tong cong|total|toongr cong|bao nhieu|bnhiu|bn)")


def extra_filter(intent: str, s: str) -> str | None:
    if re.search(_SKIP[intent], s):
        return "extra_filter_or_subintent"
    if intent == "revenue" and _ITEM_REV.search(s) and not _ITEM_REV_OK.search(s):
        return "item_specific_revenue"
    return None


def topk_k(s: str) -> int | None:
    """k of "top k" / "k mat hang" after removing explicit month/date phrases (rule_regression._extract_topk_k)."""
    s2 = re.sub(r"thang\s+\d{1,2}(?:/|\s+nam\s+)\d{4}|\d{1,2}/\d{1,2}/\d{4}", " ", s)
    m = re.search(r"(?:top ?|liet ke |cho minh |cho toi |xem giup |coi gium |cho hoi |giup minh liet ke )?(\d+)\s+"
                  r"(?:mat\s*\w*\s+hang\w*|san pham|hang\w*|mon|sp|best)", s2)
    return int(m.group(1)) if m else None


_UNIT_RX = re.compile(T.HOWMANY + " " + T.U + r"\b")


def asked_unit(s: str) -> str | None:
    m = _UNIT_RX.search(s)
    return m.group(2) if m else None


def match_item(catalog: list[tuple[Any, ...]], s: str) -> tuple[tuple[str | None, str, str | None] | None, str]:
    """Longest alias contained in the question (accent/spacing-insensitive key).

    catalog rows: (item_code, item_name, name_aliases, base_unit).  Ambiguous (two different items with the
    same longest alias length) or very short aliases are rejected."""
    qk = item_match_key(s)
    best_len, found = 0, {}
    for code, name, aliases, bunit in catalog:
        for al in (aliases or name or "").split(" | "):
            ak = item_match_key(al)
            if len(ak) < 3:
                continue
            if re.search(r"(?<![0-9a-z])" + re.escape(ak) + r"(?![0-9a-z])", qk):
                if len(ak) > best_len:
                    best_len, found = len(ak), {}
                if len(ak) == best_len:
                    found[(code, name)] = bunit
    if not found:
        return None, "item_not_found"
    if len(found) > 1:
        return None, "item_ambiguous"
    (code, name), bunit = next(iter(found.items()))
    return (code, name, bunit), "ok"


_THRESH = re.compile(r"(?:≥|>=|tu|dat)\s*([\d\.]+)\s*dong")
_MONEY_CUE = re.compile(r"[\d\.]{4,}\s*(?:dong|d\b|vnd)|≥|>=")
_STRICT = re.compile(r"duoi|tren|hon\b|it hon|toi da|nho hon|lon hon|khong qua|<|>(?!=)")


def order_threshold(s: str) -> tuple[float | None, str]:
    """Revenue threshold of "so don co doanh thu >= X dong" (rule_regression.execute_template, same regex).

    -> (value, "ok") ; (None, "no_threshold") when the question has none ; (None, reason) when it has one we cannot
    apply exactly (strict comparison, unparsed amount) -> the router sends it to the LLM."""
    if not _MONEY_CUE.search(s):
        return None, "no_threshold"
    if _STRICT.search(s):
        return None, "threshold_strict_or_other"
    m = _THRESH.search(s)
    if not m:
        return None, "threshold_unparsed"
    try:
        return float(m.group(1).replace(".", "")), "ok"
    except ValueError:
        return None, "threshold_unparsed"
