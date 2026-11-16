# DataMate — router-only submission (Zalo AI Challenge 2026)

This image is the team's final solution: a deterministic, CPU-only question router.
**No language model, no GPU, no network.** Built from `Dockerfile.router`.

## Run

```
docker run --rm --network none --entrypoint bash \
  -v /path/to/public_test:/data:ro -v /path/to/output:/result \
  zaic2026_datamate_<team>:final /code/predict.sh
```

`predict.sh` takes no arguments. `DATAMATE_ROUTER_ONLY=1` is set in the image ENV, so
`src/predict.py` loads no model. Settings are fixed (`PYTHONHASHSEED=42`, `random.seed(42)`,
no sampling anywhere), so two runs on the same input give identical files.

Input: `/data/questions.jsonl`, `/data/rulebook.md`, `/data/calendar.csv`, `/data/data/<business_id>/`.
Output: `/result/submission.jsonl` (one line per question, written and flushed as soon as it is
answered) and `/result/logs/questions.jsonl` (one log record per question: `id`, `answer`,
`elapsed_ms`, `thinking` = `null` because no model reasoning is generated, plus the template
that ran and its inputs/output).

## Approach

1. **Data layer** (`src/ingestion.py`, `src/views.py`, `src/ledger.py`, `src/stock.py`, `src/cleaning.py`): each shop's
   CSV / XLSX / SQLite files are loaded into an in-memory SQLite database; views apply the
   rulebook definitions (valid orders, statuses, unit conversion, customer group, category).
2. **Question normalisation** (`src/nlu/`): Vietnamese text without diacritics / teencode is
   normalised using `src/nlu/resources/{vocab,teencode}.json`.
3. **Period resolution** (`src/timeutil.py`): relative dates, solar/lunar periods and Tết are
   resolved from `as_of_date` and `/data/calendar.csv`.
4. **Router** (`src/router/`): the question is matched to an intent and parameters. A
   predefined SQL template (`src/router/templates.py`) runs over the views only when intent,
   period and parameters are all certain. A rule guard (`src/router/rule_guard.py`) switches
   off any intent whose rulebook rows differ from the training rulebook; data invariants
   (`src/router/invariants.py`) block answers on data that looks broken.
5. Everything the router does not answer with certainty is written as `abstain`
   (or `unanswerable` when the period lies entirely before the shop's data, rulebook §7).

No logic is keyed on question or business IDs and no answers are hard-coded.

## Models

None. The image contains no model weights and loads none. Total inference parameters: 0.

## Data and training

No model was trained or fine-tuned. Three small lookup files were derived from the
organiser-provided **training split** only (never public/private test data or answers):

| File in image | Generator (in `/code/training_code/data_generation/`) | Derived from |
|---|---|---|
| `src/nlu/resources/vocab.json`, `teencode.json` | `build_nlu_resources.py` | question **text** of the 24 dev shops in `folds.json` |
| `src/router/rule_reference.json` | `build_rule_reference.py` | row hashes of the train `rulebook.md` (no rule text) |
| `src/router/invariant_thresholds.json` | `data_invariants.py derive` | per-metric worst value over the 30 train shops |

Paths, sizes, SHA-256 checksums and the training-split checksums are in
`/code/training_code/data_manifest.json` (written at image build time).
See `/code/training_code/README.md` for the exact commands.

## Folder layout

```
/code/predict.sh                  entry point
/code/README.md                   this file
/code/requirements.txt            pinned runtime deps (pandas, openpyxl)
/code/src/                        inference code
/code/training_code/              data-generation scripts, README, data_manifest.json
```
