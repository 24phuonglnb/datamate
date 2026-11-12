#!/usr/bin/env bash
# One baseline run per array task; at most 2 tasks at a time (2-GPU rule), 1 GPU each.
#   sbatch --array=1-1%2 eval/slurm/run_baseline.sbatch                    # sample 600
#   EXTRA="--full" sbatch --array=1-1%2 eval/slurm/run_baseline.sbatch     # all 3000
#   EXTRA="--limit 6" ... for a smoke test
# Array index -> model: 1 = Qwen3-8B, 2 = Qwen3-14B (14B weights not downloaded yet).
#SBATCH --job-name=dm-baseline
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=24:00:00
#SBATCH --output=logs/%x_%A_%a.out
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$PWD}"
export HF_HOME="${HF_HOME:-/mnt/disk1/23nhi.ttt/hf}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONHASHSEED=42 OMP_NUM_THREADS=4
PY="${PY:-$HOME/datamate_work/venv/bin/python}"
case "${SLURM_ARRAY_TASK_ID:-1}" in
  1) NAME=Qwen3-8B;  REPO=models--Qwen--Qwen3-8B ;;
  2) NAME=Qwen3-14B; REPO=models--Qwen--Qwen3-14B ;;
  *) echo "bad array index"; exit 2 ;;
esac
MP=$(ls -d "$HF_HOME"/hub/$REPO/snapshots/* | head -1)
echo "host=$(hostname) gpu=$CUDA_VISIBLE_DEVICES model=$NAME path=$MP"
exec "$PY" -m eval.run_baseline --model-path "$MP" --model-name "${NAME}${SUFFIX:-}" --device cuda:0 --resume ${EXTRA:-}
