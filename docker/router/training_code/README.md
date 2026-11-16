# Training code — router-only submission

**No model training or fine-tuning was performed.** No model weights are used for inference.

The only data preparation is three small lookup files, regenerated with the commands below
from the organiser-provided training split (laid out as `data/train/train/` in the repository,
which is the same layout as `/data`). Hardware: any CPU; each command takes under a few minutes.
Nothing here is random; the outputs are deterministic.

```
# from the repository root (or /code), with pandas and openpyxl installed
python training_code/data_generation/build_nlu_resources.py \
    --train-dir data/train/train --folds training_code/data_generation/folds.json --out src/nlu/resources
python training_code/data_generation/build_rule_reference.py build --rulebook data/train/train/rulebook.md
DATAMATE_CACHE_DIR=/tmp/datamate_cache \
    python training_code/data_generation/data_invariants.py derive --data-dir data/train/train
```

In the repository these scripts live in `scripts/` and `folds.json` in `eval/`; the image keeps
a copy under `/code/training_code/data_generation/`.

- `folds.json` fixes which train shops are "dev" (24) and "hold-out" (6). Only dev-shop
  question text feeds `build_nlu_resources.py`; answers are never read.
- Public and private test data are never used.

`data_manifest.json` lists every derived file and generator script with its size and SHA-256,
plus the SHA-256 of the training-split files they were built from.
