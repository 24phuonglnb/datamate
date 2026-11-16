"""Write /code/training_code/data_manifest.json at image build time.

    python docker/router/make_manifest.py /code                          # router-only image
    python docker/router/make_manifest.py /code --models models.json     # GPU image (docker/gpu/models.json)

Hashes the derived lookup files and generator scripts that are actually in the image, so the
manifest can never drift from the image contents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

# SHA-256 of the organiser-provided training split the lookup files were derived from.
# The split itself is not bundled in this image.
TRAIN_SPLIT = {
    "location_in_repo": "data/train/train/ (organiser-provided train split; not committed to git)",
    "files": {
        "questions.jsonl": {"sha256": "b258ebd978a6d51b3b0b431b26926f958e56522beeb7da2984fea8333e21cec1", "lines": 3000},
        "rulebook.md": {"sha256": "740267bccba29df70f745bc39968bbec5b3e62dada2c858c45314f3ec723d113"},
        "calendar.csv": {"sha256": "c2579905e8b4eb152a4833b05f1f72de3e3d2c517b5d610d7664aeeb2d6a75b3"},
    },
    "shops": 30,
    "splits": {"dev": 24, "holdout": 6, "definition": "training_code/data_generation/folds.json"},
}

DERIVED = [
    ("src/nlu/resources/vocab.json", "build_nlu_resources.py", "question text of dev shops"),
    ("src/nlu/resources/teencode.json", "build_nlu_resources.py", "question text of dev shops (curated seed list filtered by count>=3)"),
    ("src/router/rule_reference.json", "build_rule_reference.py build", "row hashes of train rulebook.md"),
    ("src/router/invariant_thresholds.json", "data_invariants.py derive", "per-metric worst value over the 30 train shops"),
]


def _entry(root: Path, rel: str) -> dict:
    p = root / rel
    data = p.read_bytes()
    return {"path": f"/code/{rel}", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main(root: Path, models: list[dict]) -> None:
    gen_dir = root / "training_code" / "data_generation"
    manifest = {
        "status": "no_model_training_performed",
        "inference_models": models,
        "training_split": TRAIN_SPLIT,
        "derived_files": [
            {**_entry(root, rel), "generator": gen, "derived_from": src} for rel, gen, src in DERIVED
        ],
        "generator_scripts": [_entry(root, str(p.relative_to(root))) for p in sorted(gen_dir.iterdir()) if p.is_file()],
        "public_or_private_test_data_used": False,
    }
    out = root / "training_code" / "data_manifest.json"
    out.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default="/code")
    ap.add_argument("--models", help="JSON list of inference models (omit: no model)")
    a = ap.parse_args()
    main(Path(a.root), json.loads(Path(a.models).read_text(encoding="utf-8")) if a.models else [])
