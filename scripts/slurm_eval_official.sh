#!/bin/bash
# Slurm job template for official DataMate evaluation on CECS
#
# Usage (from project root):
#   sbatch scripts/slurm_eval_official.sh
#
# Override defaults with environment variables:
#   SPLIT=train LIMIT=15 sbatch scripts/slurm_eval_official.sh
#   SPLIT=public_test PREDICT_ONLY=1 sbatch scripts/slurm_eval_official.sh
#
# Required environment before submission:
#   export MODEL_PATH=/path/to/Qwen3-14B
#   export TRAIN_DIR=/path/to/train            # or set DATASET_ROOT
#   export PUBLIC_TEST_DIR=/path/to/public_test

#SBATCH --job-name=datamate-eval
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --gres=gpu:2
#SBATCH --time=24:00:00
#SBATCH --output=logs/datamate_eval_%j.out
#SBATCH --error=logs/datamate_eval_%j.err

set -euo pipefail

# ── Configurable via env vars ─────────────────────────────────────────────
SPLIT="${SPLIT:-train}"
BACKEND="${BACKEND:-transformers}"
LIMIT="${LIMIT:-}"
BUSINESSES="${BUSINESSES:-}"
PREDICT_ONLY="${PREDICT_ONLY:-}"
MODEL_PATH="${MODEL_PATH:?MODEL_PATH must be set}"
TP="${TP:-2}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-2}"
TORCH_DTYPE="${TORCH_DTYPE:-bfloat16}"
MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-1024}"

# Resolve dataset root: use DATASET_ROOT env if set, else infer from project
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ "${SPLIT}" == "train" ]]; then
    DATASET_ROOT="${TRAIN_DIR:-${PROJECT_ROOT}/data/train/train}"
else
    DATASET_ROOT="${PUBLIC_TEST_DIR:-${PROJECT_ROOT}/public_test}"
fi

# Output dir
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="${PROJECT_ROOT}/eval_results/official_${SPLIT}_${TIMESTAMP}"

# ── Environment setup ─────────────────────────────────────────────────────
# Adjust to match your CECS module system
# module load cuda/12.1 python/3.10

cd "${PROJECT_ROOT}"

# Install / verify dependencies
if [[ -d .venv ]]; then
    source .venv/bin/activate
fi

# ── Build CLI args ────────────────────────────────────────────────────────
CMD="python3 eval/eval_official.py"
CMD+=" --dataset ${SPLIT}"
CMD+=" --dataset-root ${DATASET_ROOT}"
CMD+=" --backend ${BACKEND}"
CMD+=" --model-path ${MODEL_PATH}"
CMD+=" --tp ${TP}"
CMD+=" --torch-dtype ${TORCH_DTYPE}"
CMD+=" --max-new-tokens ${MAX_NEW_TOKENS}"
CMD+=" --max-attempts ${MAX_ATTEMPTS}"
CMD+=" --out ${OUT_DIR}"

[[ -n "${LIMIT}" ]] && CMD+=" --limit ${LIMIT}"
[[ -n "${BUSINESSES}" ]] && CMD+=" --businesses ${BUSINESSES}"
[[ -n "${PREDICT_ONLY}" ]] && CMD+=" --predict-only"

echo "========================================================"
echo "DataMate official evaluation"
echo "  Split        : ${SPLIT}"
echo "  Dataset root : ${DATASET_ROOT}"
echo "  Backend      : ${BACKEND}  (tp=${TP})"
echo "  Model        : ${MODEL_PATH}"
echo "  Output       : ${OUT_DIR}"
echo "  Cmd          : ${CMD}"
echo "========================================================"

mkdir -p "${PROJECT_ROOT}/logs"
${CMD}

echo "Done. Results in ${OUT_DIR}"
