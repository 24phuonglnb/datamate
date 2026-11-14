"""Write src/router/rule_reference.json (row hashes of the TRAIN rulebook; no rule text) and show a rulebook diff.

    python scripts/build_rule_reference.py build --rulebook data/train/train/rulebook.md
    python scripts/build_rule_reference.py diff  --rulebook data/public_test/public_test/rulebook.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.router import rule_guard as rg  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["build", "diff"])
    ap.add_argument("--rulebook", required=True)
    a = ap.parse_args()
    text = Path(a.rulebook).read_text(encoding="utf-8")
    if a.mode == "build":
        ref = rg.build_reference(text)
        rg.REFERENCE_PATH.write_text(json.dumps({"_note": "sha256 of normalised TRAIN rulebook rows; no rule text",
                                                  "rows": ref}, indent=1), encoding="utf-8")
        print(f"{len(ref)} rows -> {rg.REFERENCE_PATH}")
    else:
        g = rg.RuleGuard.load(a.rulebook)
        print(json.dumps(g.report(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
