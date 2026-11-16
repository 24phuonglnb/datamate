#!/usr/bin/env bash
set -euo pipefail
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PYTHONPATH=/code
export PYTHONHASHSEED=42
export NCCL_P2P_DISABLE=1
export OMP_NUM_THREADS=4
mkdir -p "${RESULT_DIR:-/result}/logs"
cd /code
# MODEL_PATH, TP_SIZE and MAX_MODEL_LEN come from the Dockerfile ENV; src/predict.py reads them.
exec python -m src.predict --data-dir "${DATA_DIR:-/data}" --result-dir "${RESULT_DIR:-/result}"
