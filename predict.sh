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
exec python -m src.predict --data-dir "${DATA_DIR:-/data}" --result-dir "${RESULT_DIR:-/result}" --model-path "${MODEL_PATH:-/code/models/Qwen3-8B}" --tensor-parallel-size "${TP_SIZE:-2}"
