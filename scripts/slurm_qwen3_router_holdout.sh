#!/usr/bin/env bash
# Qwen3-14B + router evaluation on CECS (2 × RTX A5000, a5000 partition, student QoS)
#
# MUST be run from the feat/intent-router branch on CECS:
#   git checkout feat/intent-router   # or whichever branch has src/router/
#
# Usage:
#   # Smoke test (15 questions from holdout shops, mock backend — no GPU needed):
#   SMOKE=1 sbatch scripts/slurm_qwen3_router_holdout.sh
#
#   # Full holdout evaluation (709 questions, router + Qwen3-14B):
#   sbatch scripts/slurm_qwen3_router_holdout.sh
#
#   # Router-only baseline on holdout (no model, CPU only):
#   ROUTER_ONLY=1 sbatch scripts/slurm_qwen3_router_holdout.sh
#
# Required env before submission:
#   export MODEL_PATH=$HOME/models/Qwen3-14B   # already on CECS
#   export VENV=$HOME/datamate_work/venv        # virtualenv with torch+transformers
#
# Outputs land in eval/reports/ (aggregates committed) and
#   eval/reports/<tag>.per_question.jsonl (git-ignored).

#SBATCH --job-name=dm-qwen3-router
#SBATCH --partition=a5000
#SBATCH --qos=student
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=56G
#SBATCH --gres=gpu:a5000:2
#SBATCH --time=08:00:00
#SBATCH --output=logs/dm_qwen3_router_%j.out
#SBATCH --error=logs/dm_qwen3_router_%j.err

set -euo pipefail

# ── Configurable via env vars ──────────────────────────────────────────────
MODEL_PATH="${MODEL_PATH:?Set MODEL_PATH=$HOME/models/Qwen3-14B}"
VENV="${VENV:-$HOME/datamate_work/venv}"
SMOKE="${SMOKE:-}"              # non-empty = 15-question smoke test (mock backend)
ROUTER_ONLY="${ROUTER_ONLY:-}"  # non-empty = no model, router answers only
BACKEND="${BACKEND:-transformers}"
SUBSET="${SUBSET:-holdout}"     # holdout (709 q) | sample (600 q) | full (3000 q)
RESUME="${RESUME:-}"            # non-empty = resume an earlier killed run
DATE="$(date +%Y-%m-%d)"

# ── Project root ───────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TRAIN_DIR="${TRAIN_DIR:-${PROJECT_ROOT}/train}"

cd "${PROJECT_ROOT}"
mkdir -p logs

# ── Activate virtualenv ────────────────────────────────────────────────────
if [[ -f "${VENV}/bin/activate" ]]; then
    source "${VENV}/bin/activate"
    echo "Activated venv: ${VENV}"
else
    echo "WARNING: venv not found at ${VENV}; using system Python"
fi

PY="${VENV}/bin/python3"
[[ -x "${PY}" ]] || PY="$(command -v python3)"

# ── Offline mode ───────────────────────────────────────────────────────────
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PYTHONHASHSEED=42
export OMP_NUM_THREADS=4
export PYTHONPATH="${PROJECT_ROOT}"

# ── GPU diagnostics ────────────────────────────────────────────────────────
echo "========================================================"
echo "Job: ${SLURM_JOB_ID:-local}  Host: $(hostname)"
echo "GPUs: ${CUDA_VISIBLE_DEVICES:-not set}"
if command -v nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader
fi
echo "========================================================"

# ── Verify branch has router code ─────────────────────────────────────────
if [[ ! -d "${PROJECT_ROOT}/src/router" ]]; then
    echo "ERROR: src/router/ not found."
    echo "  This script requires the feat/intent-router branch."
    echo "  On CECS: git fetch origin && git checkout feat/intent-router"
    exit 1
fi

# ── Build CLI args for eval/run_baseline.py ───────────────────────────────
# eval/run_baseline.py uses eval/folds.json for the holdout split,
# writes per-question JSONL and aggregate markdown/JSON reports.

CMD="${PY} -m eval.run_baseline"
CMD+=" --train-dir ${TRAIN_DIR}"
CMD+=" --folds ${PROJECT_ROOT}/eval/folds.json"
CMD+=" --out ${PROJECT_ROOT}/eval/reports"
CMD+=" --subset ${SUBSET}"
CMD+=" --date ${DATE}"

if [[ -n "${SMOKE}" ]]; then
    # Smoke: mock backend, 15 questions, no GPU
    CMD+=" --backend mock"
    CMD+=" --model-path ${MODEL_PATH}"
    CMD+=" --model-name smoke_mock"
    CMD+=" --limit 15"
    CMD+=" --router"
    echo "SMOKE TEST: mock backend, --limit 15, router enabled"
elif [[ -n "${ROUTER_ONLY}" ]]; then
    # Router-only: no model loaded, every non-routed question abstains.
    # eval/run_baseline.py doesn't have a --router-only flag; use mock backend
    # combined with the router to simulate it (router answers, mock abstains for the rest).
    CMD+=" --backend mock"
    CMD+=" --model-path ${MODEL_PATH}"
    CMD+=" --model-name Qwen3-14B_router_only"
    CMD+=" --router"
    echo "ROUTER-ONLY: mock backend + router (no GPU inference)"
else
    # Full router + Qwen3-14B run
    CMD+=" --backend ${BACKEND}"
    CMD+=" --model-path ${MODEL_PATH}"
    CMD+=" --model-name Qwen3-14B"
    CMD+=" --router"
    # device_map=auto distributes across both A5000s (confirmed working)
    # No --device flag → HFTransformers uses device_map='auto' by default
    [[ -n "${RESUME}" ]] && CMD+=" --resume"
    echo "ROUTER + LLM: HFTransformers backend, device_map=auto, 2 × A5000"
fi

echo "Command: ${CMD}"
echo "========================================================"

${CMD}

echo "========================================================"
echo "Done. Reports written to ${PROJECT_ROOT}/eval/reports/"
echo "========================================================"
