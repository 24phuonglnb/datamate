#!/usr/bin/env bash
# Tải dữ liệu ZAC 2026 từ HF dataset private về ./data (hoặc đường dẫn truyền vào)
set -euo pipefail
DEST="${1:-data}"
huggingface-cli whoami >/dev/null 2>&1 || { echo "Chưa đăng nhập HF: chạy 'huggingface-cli login'"; exit 1; }
huggingface-cli download nyla111/zaic-data --repo-type dataset --local-dir "$DEST"
for z in "$DEST"/*.zip; do [ -e "$z" ] && unzip -n -q "$z" -d "$DEST"; done
test -f "$DEST/train/train/answers.jsonl" || { echo "Thiếu train/train/answers.jsonl"; exit 1; }
echo "Xong."
