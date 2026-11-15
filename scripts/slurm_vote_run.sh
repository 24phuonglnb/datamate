#!/usr/bin/env bash
# Router + LLM self-consistency vote on one data directory, 1 RTX 3090 on vishc-server-1.
#
#   DATA_DIR=<dir with questions.jsonl, rulebook.md, calendar.csv, data/> RESULT_DIR=<out dir> \
#   MODEL_PATH=~/models/Qwen3-14B-AWQ PY=~/venvs/vllm/bin/python K=5 TEMP=0.7 \
#   sbatch scripts/slurm_vote_run.sh
#
# Every sample of every question that reaches the LLM is kept in $RESULT_DIR/logs/questions.jsonl (DATAMATE_LLM_VOTE_FULL=1:
# all K samples are asked, no early stop), so thresholds can be swept offline with `python -m eval.vote_sweep`.
# submission.jsonl is complete from the first second (abstain until answered) and by_shop/<shop>.jsonl is written per shop.
#SBATCH --job-name=dm-vote
#SBATCH --partition=gpu
#SBATCH --gres=gpu:rtx3090:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=24:00:00
#SBATCH --output=%x_%j.out
set -euo pipefail

: "${DATA_DIR:?set DATA_DIR}"
: "${RESULT_DIR:?set RESULT_DIR}"
MODEL_PATH="${MODEL_PATH:-$HOME/models/Qwen3-14B-AWQ}"
PY="${PY:-$HOME/venvs/vllm/bin/python}"
K="${K:-5}"
TEMP="${TEMP:-0.7}"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export DATAMATE_CACHE_DIR="${DATAMATE_CACHE_DIR:-$HOME/datamate_work/cache_vote}"
mkdir -p "${RESULT_DIR}" "${DATAMATE_CACHE_DIR}"

export DATAMATE_LLM_VOTE_K="${K}"
export DATAMATE_LLM_VOTE_TEMPERATURE="${TEMP}"
export DATAMATE_LLM_VOTE_FULL=1
export DATAMATE_LLM_VOTE_THRESHOLD="${THRESHOLD:-0.6}"
export DATAMATE_MAX_MODEL_LEN="${DATAMATE_MAX_MODEL_LEN:-16384}" DATAMATE_MAX_NEW_TOKENS="${DATAMATE_MAX_NEW_TOKENS:-1024}" DATAMATE_GPU_UTIL="${DATAMATE_GPU_UTIL:-0.88}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONHASHSEED=42 PYTHONUNBUFFERED=1
unset DATAMATE_ROUTER_ONLY

# Slurm here does not constrain devices (every GPU is visible) and hands out GPU 0 even when somebody else's process sits on it:
# use exactly ONE GPU, the first one that is really free (< 300 MB in use), never one that another user is working on.
if [ "${PICK_FREE_GPU:-1}" = "1" ]; then
    FREE_GPU="$(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits | awk -F', ' '$2 < 300 {print $1; exit}')"
    if [ -z "${FREE_GPU}" ]; then echo "no free GPU right now: exit without running"; exit 3; fi
    export CUDA_VISIBLE_DEVICES="${FREE_GPU}"
fi
echo "node: $(hostname)  gpu: ${CUDA_VISIBLE_DEVICES:-unset}  K=${K}  temperature=${TEMP}  model=${MODEL_PATH}"
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader || true
cd "${PROJECT_ROOT}"
"${PY}" -m src.predict --data-dir "${DATA_DIR}" --result-dir "${RESULT_DIR}" \
    --model-path "${MODEL_PATH}" --tensor-parallel-size 1
echo "done: $(wc -l < "${RESULT_DIR}/submission.jsonl") lines"
