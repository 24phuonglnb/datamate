"""Build src/nlu/resources/*.json from the question texts of DEV shops only.

    python scripts/build_nlu_resources.py --train-dir data/train/train --folds eval/folds.json

Only question *text* of dev shops is used (never answers, never hold-out shops, never public test).
Outputs:
  vocab.json    {"words": {diacritic word: count>=3}, "noaccent_suspect": [folded forms that are
                 almost always written WITH diacritics in clean sentences]}
  teencode.json {token: expansion} -- curated seed list, kept only if the token occurs >=3 times
                 in dev questions (counts recorded under "_counts")
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import unicodedata
from pathlib import Path

SEED_TEENCODE = {
    "dthu": "doanh thu", "bn": "bao nhiêu", "bnhiu": "bao nhiêu", "bnhieu": "bao nhiêu",
    "nhiu": "nhiêu", "nhìu": "nhiều", "dc": "được", "đc": "được", "trc": "trước", "vs": "với",
    "z": "vậy", "hnay": "hôm nay", "hqua": "hôm qua", "ko": "không", "k": "không", "hok": "không",
    "hông": "không", "sp": "sản phẩm", "nv": "nhân viên", "kh": "khách hàng", "sl": "số lượng",
    "tg": "thời gian", "r": "rồi", "ck": "chuyển khoản", "tm": "tiền mặt", "dt": "doanh thu", "tt": "thanh toán", "ntn": "như thế nào", "j": "gì",
}


def fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def words(s: str) -> list[str]:
    return re.findall(r"\b[^\W\d_]+\b", unicodedata.normalize("NFC", s.lower()))


def has_dia(s: str) -> bool:
    return any(c == "đ" or unicodedata.category(c) == "Mn" for c in unicodedata.normalize("NFD", s.lower()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-dir", default="data/train/train")
    ap.add_argument("--folds", default="eval/folds.json")
    ap.add_argument("--out", default="src/nlu/resources")
    a = ap.parse_args()
    dev = set(json.loads(Path(a.folds).read_text(encoding="utf-8"))["dev"])
    qs = [json.loads(x) for x in (Path(a.train_dir) / "questions.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    texts = [q["question"] for q in qs if q["business_id"] in dev]
    allc = collections.Counter(w for t in texts for w in words(t))
    marked = {w: n for w, n in allc.items() if fold(w) != w and n >= 3}
    marked_by_fold = collections.Counter()
    for w, n in marked.items():
        marked_by_fold[fold(w)] += n
    clean_unmarked = collections.Counter(w for t in texts if has_dia(t) for w in words(t) if fold(w) == w)
    suspect = sorted(f for f, n in marked_by_fold.items() if n >= 3 and len(f) >= 2 and clean_unmarked[f] <= 0.1 * n)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "vocab.json").write_text(json.dumps({"n_questions": len(texts), "words": marked, "noaccent_suspect": suspect},
                                               ensure_ascii=False, sort_keys=True), encoding="utf-8")
    counts = {k: allc.get(k, 0) for k in SEED_TEENCODE}
    kept = {k: v for k, v in SEED_TEENCODE.items() if counts[k] >= 3}
    (out / "teencode.json").write_text(json.dumps({"map": kept, "_counts": counts, "_dropped_lt3": sorted(set(SEED_TEENCODE) - set(kept))},
                                                  ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"questions={len(texts)} words={len(marked)} suspect={len(suspect)} teencode kept={len(kept)} dropped={sorted(set(SEED_TEENCODE)-set(kept))}")


if __name__ == "__main__":
    main()
