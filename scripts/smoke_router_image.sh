#!/usr/bin/env bash
# Run the submission image exactly like the organisers (guideline §10) and check the output.
#
#   bash scripts/smoke_router_image.sh <image> <data_dir> <out_dir>
#
# <data_dir> holds questions.jsonl, rulebook.md, calendar.csv, data/<shop>/ (mounted read-only).
# Checks: one submission line and one log line per question, validate_submission.py passes,
# every log record has id/answer/elapsed_ms/thinking, and a second run gives the same file.
set -euo pipefail
IMAGE="$1"; DATA="$(realpath "$2")"; OUT="$(realpath -m "$3")"
HERE="$(cd "$(dirname "$0")" && pwd)"

run() {  # $1 = result dir
  mkdir -p "$1"
  # shellcheck disable=SC2086  # EXTRA_DOCKER_ARGS: optional extra flags, e.g. "-e DATAMATE_ROUTER_ONLY=1"
  docker run --rm --network none --entrypoint bash ${EXTRA_DOCKER_ARGS:-} \
    -v "$DATA":/data:ro -v "$1":/result "$IMAGE" /code/predict.sh
}

run "$OUT/run1"
run "$OUT/run2"

n_q=$(grep -c . "$DATA/questions.jsonl")
n_s=$(grep -c . "$OUT/run1/submission.jsonl" || true)
n_l=$(grep -c . "$OUT/run1/logs/questions.jsonl" || true)
echo "questions=$n_q submission=$n_s logs=$n_l"
[ "$n_q" = "$n_s" ] || { echo "FAIL: submission has $n_s lines, expected $n_q"; exit 1; }
[ "$n_q" = "$n_l" ] || { echo "FAIL: logs have $n_l lines, expected $n_q"; exit 1; }

python3 "$HERE/validate_submission.py" "$OUT/run1/submission.jsonl" "$DATA/questions.jsonl"

python3 - "$OUT/run1/logs/questions.jsonl" <<'EOF'
import json, sys, collections
need = ("id", "answer", "elapsed_ms", "thinking")
routes = collections.Counter()
for i, line in enumerate(open(sys.argv[1], encoding="utf-8"), 1):
    r = json.loads(line)
    miss = [k for k in need if k not in r]
    assert not miss, f"log line {i}: missing {miss}"
    assert isinstance(r["elapsed_ms"], int) and r["elapsed_ms"] >= 0, f"log line {i}: bad elapsed_ms"
    route = (r.get("router") or {}).get("route")
    routes[route] += 1
    if route == "template":
        assert r.get("code") and "output" in r, f"log line {i}: template answer without code/output"
print("log fields OK; routes:", dict(routes))
EOF

cmp "$OUT/run1/submission.jsonl" "$OUT/run2/submission.jsonl" \
  || { echo "FAIL: two runs on the same input differ"; exit 1; }
echo "two runs identical"
echo "SMOKE OK"
