# DataMate - Offline Vietnamese Business QA Agent

**Track:** Zalo AI Challenge 2026 — DataMate
**Status:** V2 baseline complete. Synthetic benchmark: 74/105 (70.48%). Unit tests: 92 passed.

> Official train/public/private datasets and model weights are NOT included in this repository.
> Benchmark results are on a **synthetic dataset only** — they are not official competition scores.

---

## Architecture

```
question.jsonl
  └─► data ingestion (CSV / XLSX / SQLite → in-memory SQLite)
       └─► schema profiling (column types, sample rows, row counts)
            └─► Qwen3-14B LLM prompt (system + schema + question)
                 └─► SQL generation + JSON parsing
                      └─► read-only SQL execution (guarded, time-limited)
                           └─► typed result → submission.jsonl
```

Each question goes through up to 2 attempts. On SQL failure the error message is fed back to the model for one retry. On parse failure or repeated identical SQL the agent abstains.

---

## Repository structure

```
datamate/
├── src/
│   ├── agent.py          # Prompting, SQL execution, typed answer serialisation
│   ├── ingestion.py      # CSV/XLSX/SQLite → in-memory SQLite (BusinessDB)
│   ├── llm.py            # HFTransformers, LocalVLLM, MockLLM backends
│   └── predict.py        # Competition entrypoint (reads /data, writes /result)
├── benchmark/
│   ├── create_benchmark.py  # Generates synthetic data + oracle ground truth
│   ├── questions.jsonl      # 105 synthetic Vietnamese questions
│   ├── ground_truth.jsonl   # Oracle answers (derived from SQL, never hardcoded)
│   ├── rulebook.md          # Business rules used in prompt
│   ├── calendar.csv         # Solar/lunar calendar for date questions
│   └── data/                # 5 synthetic business datasets (CSV/XLSX/SQLite)
├── eval/
│   └── evaluate.py       # Evaluation runner: accuracy, SQL rate, latency
├── eval_results/
│   └── qwen3_full/       # Reference V2 results (74/105, Qwen3-14B)
│       ├── summary.json
│       └── per_question.jsonl
├── tests/
│   ├── test_smoke.py     # Agent + ingestion + LLM integration smoke tests
│   ├── test_benchmark.py # Benchmark generation and ground-truth verification
│   └── test_eval.py      # Evaluator correctness tests
├── example_data/         # Minimal demo dataset (no GPU needed)
├── example_result/       # Output of demo_run (not committed)
├── scripts/
│   ├── demo_run.py       # End-to-end demo with MockLLM
│   └── create_demo_data.py
├── training_code/
│   ├── README.md         # Training evidence declaration (no fine-tuning performed)
│   └── data_manifest.json
├── models/
│   └── README.md         # Placeholder; model weights go here, not in git
├── docs/
│   ├── EXPERIMENTS.md    # V1 / V2 / full 105-question results with failure analysis
│   └── NEXT_STEPS.md     # Prioritised engineering roadmap
├── Dockerfile            # Competition container (vllm/vllm-openai:v0.10.1.1)
├── predict.sh            # Container entrypoint
└── requirements.txt      # openpyxl==3.1.5 (vLLM/PyTorch supplied by base image)
```

---

## Installation

**Python 3.10+ required.** For CPU-only tests (no GPU, no model weights):

```bash
pip install openpyxl==3.1.5
```

For real inference (GPU required):

```bash
# HFTransformers backend (tested on 2 × RTX A5000):
pip install torch transformers accelerate openpyxl

# vLLM backend (competition Docker):
# Use base image vllm/vllm-openai:v0.10.1.1; openpyxl is the only additional dep.
```

---

## Dữ liệu chính thức

Dữ liệu ZAC 2026 nằm ở dataset **private** trên Hugging Face: `nyla111/zaic-data`. Nhắn Nhi để được cấp quyền.
Không commit dữ liệu, token hay weights (đã chặn trong `.gitignore`).

### Tải về
```bash
pip install -U "huggingface_hub[cli]"
huggingface-cli login            # token HF cá nhân, quyền read
bash scripts/download_data.sh    # mặc định tải về ./data
```

### Cấu trúc
Cấu trúc thật trên HF có **hai cấp lồng nhau** (`train/train/`, `public_test/public_test/`):
```
data/
├── train/train/
│   ├── questions.jsonl, answers.jsonl
│   ├── rulebook.md, calendar.csv
│   └── data/            # biz_101 … biz_130
└── public_test/public_test/
    ├── questions.jsonl, rulebook.md, calendar.csv
    └── data/            # dev_001 … dev_014, không có đáp án
```

- Chỉ dùng train để phát triển và đánh giá. public_test chỉ để chạy và nộp leaderboard, không dùng để tune hay sinh dữ liệu.
- Shop hold-out cố định trong `eval/folds.json`. Không tune trên các shop này.
- Trên server dùng chung, đặt `HF_HOME` vào thư mục đủ quota.
- Docker lúc nộp đọc dữ liệu từ `/data` (offline). Script này chỉ dùng cho môi trường dev.

### Trỏ code tới dữ liệu
`src/predict.py` đọc `<DATA_DIR>/questions.jsonl`, `<DATA_DIR>/rulebook.md`, `<DATA_DIR>/calendar.csv` và `<DATA_DIR>/data/<business_id>/`,
nên `DATA_DIR` phải trỏ vào thư mục lồng bên trong (không di chuyển dữ liệu):
```bash
export DATA_DIR=$PWD/data/train/train          # hoặc data/public_test/public_test
python -m src.predict --data-dir "$DATA_DIR" --result-dir /path/to/result --model-path /path/to/Qwen3-8B
```

---

## Running unit tests

All 92 tests run offline — no GPU or model weights needed:

```bash
python3 -m pytest tests/ -v
# or
python3 -m unittest discover -s tests -v
```

The tests inject a deterministic `MockLLM` test double. They validate data ingestion, SQL execution, answer typing, and evaluation logic, but do NOT test LLM reasoning quality.

---

## Synthetic benchmark

### Build and verify

```bash
# Generate data files and ground truth (idempotent)
python3 benchmark/create_benchmark.py

# Verify ground-truth answer statistics
python3 benchmark/create_benchmark.py --verify
```

### Run evaluation

```bash
# Offline pipeline smoke-test (MockModel abstains on everything — 0% expected)
python3 eval/evaluate.py --backend mock

# Full benchmark with HFTransformers backend (GPU required)
python3 eval/evaluate.py \
    --backend transformers \
    --model-path /path/to/Qwen3-14B \
    --out eval_results/my_run

# Full benchmark with vLLM backend (GPU required)
python3 eval/evaluate.py \
    --backend vllm \
    --model-path /path/to/Qwen3-14B \
    --tp 2 \
    --out eval_results/my_run

# Evaluate first 5 questions only (quick sanity check)
python3 eval/evaluate.py --backend transformers --model-path /path/to/Qwen3-14B --limit 5
```

Results are written to `--out/summary.json` and `--out/per_question.jsonl`.

**Reference V2 results** (Qwen3-14B, HFTransformers, 2 × RTX A5000):

| Metric | Value |
|--------|-------|
| Accuracy | 70.48% (74/105) |
| SQL success rate | 97.83% |
| Mean latency | 5,386 ms/question |

See `docs/EXPERIMENTS.md` for full breakdown by answer type and failure analysis.

---

## Configuring the local model path

The model path can be set three ways (highest priority first):

1. **CLI flag:** `--model-path /absolute/path/to/Qwen3-14B`
2. **Environment variable:** `MODEL_PATH=/absolute/path/to/Qwen3-14B`
3. **Default:** `/code/models/Qwen3-8B` (competition container default)

Place model weights under `models/` locally (this directory is excluded from git via `.gitignore`).

### HFTransformers backend (development / CECS)

```python
from src.llm import HFTransformers
model = HFTransformers(
    "/path/to/Qwen3-14B",
    device_map="auto",        # auto-distributes across available GPUs
    torch_dtype="bfloat16",
    max_new_tokens=1024,
)
```

### vLLM backend (competition Docker)

```python
from src.llm import get_model
model = get_model("/path/to/Qwen3-14B", backend="vllm", tensor_parallel_size=2)
```

Both backends expose the same `generate(system, user) -> (str, str|None)` interface and can be used interchangeably with the `Agent`.

---

## Running the competition Docker container

```bash
docker build --platform linux/amd64 -t zaic2026_datamate_team:final .
docker run --rm --gpus '"device=0,1"' --network none --shm-size=16g \
  -v /absolute/path/to/official_train:/data:ro \
  -v /absolute/path/to/output:/result \
  zaic2026_datamate_team:final
```

Environment variables: `MODEL_PATH` (default `/code/models/Qwen3-8B`), `TP_SIZE` (default `2`), `DATA_DIR`, `RESULT_DIR`.

---

## One-command demo (no GPU needed)

```bash
PYTHONPATH=. python3 -m scripts.demo_run
```

Generates `example_data/` and `example_result/` using `MockLLM`. Demonstrates the full data ingestion → SQL → JSONL pipeline without loading model weights.

---

## Known limitations

- **Table answer type: 0/6 (0%)** — All six table questions fail due to two compounding issues: column alias mismatches between model SQL and oracle SQL, and JOIN abstentions on cross-table aggregations. See `docs/NEXT_STEPS.md` §1.2 and §2.1.
- **String/date type conflation (5 failures)** — The model correctly retrieves date-formatted strings but labels them `type: "date"` rather than `type: "string"`. The values are correct; only the type label is wrong.
- **JOIN abstentions (10 failures)** — Multi-table queries requiring a JOIN cause the model to abstain after two failed attempts. The retry hint partially mitigates single-table scalar errors but does not fully address cross-table reasoning.
- **In-memory SQLite** — All CSV/XLSX/SQLite files are loaded into a single in-memory SQLite database per question. Memory usage scales with business dataset size; large official datasets may require DuckDB or streaming.
- **Synthetic vs. official gap** — The synthetic benchmark was designed to exercise pipeline correctness, not to replicate the official competition distribution. 70.48% synthetic accuracy is not a prediction of official score.
- **Docker not tested end-to-end** — The HFTransformers path was tested on CECS; the vLLM Docker path (`predict.sh`) requires a separate GPU integration test on hardware matching the reference environment (2 × RTX 5090, CUDA 12.8+).

---

## Provenance / compliance

- No fine-tuning or data generation beyond synthetic smoke-test samples has been performed.
- Official Docker guide: https://dl-challenge.zalo.ai/2026/datamate_dkewxftdzo/zac2026_DataMate_docker_guideline_final.pdf
- Inference model (team must fill before final submission): name / version / revision / source / release date / license / parameter count. All models combined ≤ 15B parameters.
- Public or private test questions must not be used as training labels. No hardcoded answers or business/question-ID rules.
