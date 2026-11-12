#!/usr/bin/env bash
# Legacy ingestion (task 1) vs rulebook views (task 2), Qwen3-8B, all hold-out-shop questions.
#   sbatch --array=1-2%2 eval/slurm/legacy_vs_views.sbatch      # 1 GPU each, 2 GPUs total
#SBATCH --job-name=dm-lvv
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=24:00:00
#SBATCH --output=logs/%x_%A_%a.out
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$PWD}"
export HF_HOME="${HF_HOME:-/mnt/disk1/23nhi.ttt/hf}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONHASHSEED=42 OMP_NUM_THREADS=4
export DATAMATE_CACHE_DIR="${DATAMATE_CACHE_DIR:-$HOME/datamate_work/cache_legacyviews_${SLURM_ARRAY_TASK_ID}}"
PY="${PY:-$HOME/datamate_work/venv/bin/python}"
case "${SLURM_ARRAY_TASK_ID}" in
  1) export DATAMATE_LEGACY_INGESTION=1; SUF=-legacy ;;
  2) export DATAMATE_LEGACY_INGESTION=0; SUF=-views ;;
  *) echo bad index; exit 2 ;;
esac
MP=$(ls -d "$HF_HOME"/hub/models--Qwen--Qwen3-8B/snapshots/* | head -1)
echo "host=$(hostname) gpu=$CUDA_VISIBLE_DEVICES mode=$SUF"; nvidia-smi --query-gpu=memory.used --format=csv
exec "$PY" -m eval.run_baseline --model-path "$MP" --model-name "Qwen3-8B$SUF" --device cuda:0 \
  --subset holdout --resume ${EXTRA:-}
