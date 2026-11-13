# Evaluation harness (real train data)

Runs the unchanged `src.agent.Agent` on the official train questions and scores with
`eval/pa_score.py` (rulebook section 9: +1 correct, -1 wrong, 0 abstain).

## Setup
```bash
python -m venv venv && . venv/bin/activate
pip install -r requirements.txt          # Qwen3 needs transformers >= 4.51
bash scripts/download_data.sh            # see README "Dữ liệu chính thức"; data/ is git-ignored
```
Data layout expected: `data/train/train/{questions.jsonl,answers.jsonl,calendar.csv,...}`.
Another location: `--train-dir /path/to/train/train`.

## Files
| file | purpose |
|---|---|
| `folds.json` | 6 hold-out shops / 24 dev shops (fixed; do not edit after use) |
| `sample.py`, `sample_ids.json` | fixed 600-question stratified sample (seed 20261111) |
| `run_baseline.py` | run + score + report |
| `compare_runs.py` | compare two runs |
| `pa_score.py` | PA scorer (`python -m eval.pa_score --pred ... --gold ...`) |
| `slurm/run_baseline.sbatch` | Slurm wrapper (1 GPU per task) |

## Running
```bash
python -m eval.run_baseline \
  --model-path /path/to/Qwen3-8B-snapshot --model-name Qwen3-8B \
  [--backend transformers|vllm] [--tensor-parallel-size N] \
  [--subset sample|holdout|full] [--device cuda:0] [--limit K] [--resume]
```
* **Model / weights**: `--model-path` is a local directory (offline; set `HF_HUB_OFFLINE=1`).
  `--model-name` only labels the report.
* **Backends**: `transformers` (default, one GPU, bf16; `--device cuda:0` pins the GPU);
  `vllm` uses `--tensor-parallel-size` (e.g. 2 for Qwen3-14B). Total GPUs per person <= 2.
* **Question set** (`--subset`): `sample` = fixed 600 (default); `holdout` = all 709 questions of the
  6 hold-out shops; `full` = all 3000 (`--full` is an alias).
* **Order**: questions are sorted by shop so the 2-entry DB cache is not thrashed. Decoding is greedy.
* `--router` (branch `feat/intent-router` only) puts the intent router in front of the agent, like `predict.py`; rows get a `route`
  field and the report name a `_router` suffix. Example for the 14B run on the hold-out shops, with and without the router:
  ```bash
  python -m eval.run_baseline --model-path /path/to/Qwen3-14B --model-name Qwen3-14B --backend vllm \
      --tensor-parallel-size 2 --subset holdout            # agent only
  python -m eval.run_baseline ... --subset holdout --router # router + agent
  python -m eval.compare_runs eval/reports/<date>_Qwen3-14B_holdout.per_question.jsonl \
      eval/reports/<date>_Qwen3-14B_holdout_router.per_question.jsonl --show 10
  ```
* `--resume` continues from the `.per_question.jsonl` of the same tag (safe after a crash/preemption).
* **Ingestion flag** (when the data-layer branch `feat/p3-data-cleaning` is checked out): views are on by
  default; `DATAMATE_LEGACY_INGESTION=1` selects the old ingestion. Set a different `--date`
  (it names the report) or a model-name suffix so the two runs do not overwrite each other, e.g.
  `DATAMATE_LEGACY_INGESTION=1 python -m eval.run_baseline ... --model-name Qwen3-8B-legacy`.
* Slurm: `EXTRA="--subset holdout" SUFFIX=-holdout sbatch --array=1-1%2 eval/slurm/run_baseline.sbatch`
  (check `gpu-who` first; the job exits, and so frees the GPU, when done).

## Output (`eval/reports/`)
`<date>_<model>[_<subset>].md/.json` aggregate report (PA, accuracy, abstain rate, PA by type / shop /
intent / fold, time per question, top error groups). `.per_question.jsonl` and `_errors.md` hold raw
questions and gold answers and are git-ignored.

## Comparing two runs
```bash
python -m eval.compare_runs eval/reports/A.per_question.jsonl eval/reports/B.per_question.jsonl --show 10
```
prints PA of both, `|dPA|`, the number of questions whose submitted answer differs, and how many each
run wins. Run both on the same subset (the tool only compares common ids).

## Tests
`pytest tests/test_pa_score.py` (needs `data/` for the gold-self-score check; skipped otherwise).
