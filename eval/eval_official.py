"""Official DataMate evaluation CLI.

Runs the DataMate Agent against the official Zalo AI Challenge datasets and
optionally scores predictions against ground truth.

## Modes

### Train split — smoke test (10–20 questions)
    python3 eval/eval_official.py \\
        --dataset train \\
        --limit 15 \\
        --out eval_results/smoke/

### Train split — multiple businesses
    python3 eval/eval_official.py \\
        --dataset train \\
        --businesses biz_101 biz_102 biz_103 \\
        --out eval_results/multi_biz/

### Train split — full 3 000-question benchmark
    python3 eval/eval_official.py \\
        --dataset train \\
        --out eval_results/train_full/

### Public test — prediction only (no PA computed; answers are hidden)
    python3 eval/eval_official.py \\
        --dataset public_test \\
        --out eval_results/public_test/ \\
        --predict-only

## Model backends
  --backend mock          Offline smoke test; every question abstains.
  --backend transformers  Local HF weights via Transformers (CPU / GPU).
  --backend vllm          Local HF weights via vLLM (multi-GPU).

## CECS / Slurm usage
    sbatch scripts/slurm_eval_official.sh      # see scripts/ for a template

## Configurable paths
  --dataset-root DIR    Override auto-resolved dataset root.
  --model-path PATH     Path to local Qwen3-14B weights.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# Allow running as a top-level script from the project root.
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from eval.official_dataset import OfficialDataset
from eval.official_score import answers_match, compute_pa_score
from src.agent import Agent


# ── Mock model (offline testing) ──────────────────────────────────────────

class MockModel:
    """Returns abstain for every question (no GPU needed)."""

    def generate(self, system: str, user: str) -> tuple[str, None]:
        return '{"type":"abstain"}', None


# ── Runner ────────────────────────────────────────────────────────────────

def run_official(
    dataset: OfficialDataset,
    model: Any,
    out_dir: Path,
    *,
    limit: int | None = None,
    business_ids: list[str] | None = None,
    max_attempts: int = 2,
    backend_name: str = "unknown",
    predict_only: bool = False,
) -> dict[str, Any]:
    """Run *model* on *dataset* and return aggregate metrics.

    Parameters
    ----------
    dataset:
        Loaded OfficialDataset (train or public_test).
    model:
        Any object with a ``generate(system, user) -> (str, str|None)`` method.
    out_dir:
        Where outputs are written:
            submission.jsonl     — predictions in competition format
            diagnostics.jsonl    — per-question detail (latency, SQL, errors)
            summary.json         — aggregate metrics (omitted for public_test)
    limit:
        Evaluate only the first *N* questions from the filtered set.
    business_ids:
        If set, restrict to these business IDs only.
    max_attempts:
        SQL retry budget per question.
    backend_name:
        Label stored in summary.json.
    predict_only:
        When True, skip scoring even if answers are available (use for
        public_test where your local answers.jsonl would be invalid).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    agent = Agent(
        model,
        dataset.root,
        max_attempts=max_attempts,
    )

    questions = dataset.filter_questions(limit=limit, business_ids=business_ids)
    answers = dataset.answers  # empty dict when predict_only or no answers file

    predictions: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    total = 0
    total_latency_ms = 0.0
    sql_attempted = 0
    sql_success = 0

    submission_path = out_dir / "submission.jsonl"
    diag_path = out_dir / "diagnostics.jsonl"

    try:
        with (
            submission_path.open("w", encoding="utf-8") as sub_f,
            diag_path.open("w", encoding="utf-8") as diag_f,
        ):
            for q in questions:
                q_dict = q.to_dict()
                answer, log = agent.solve(q_dict)

                # Enrich prediction with business_id for per-business breakdown
                enriched = dict(answer)
                enriched["business_id"] = q.business_id
                predictions.append(enriched)

                # Submission file uses only the official fields
                sub_entry = {
                    "id": answer.get("id", q.id),
                    "type": answer.get("type", "abstain"),
                }
                if "answer" in answer:
                    sub_entry["answer"] = answer["answer"]
                if answer.get("type") == "unanswerable" and "reason" in answer:
                    sub_entry["reason"] = answer["reason"]
                sub_f.write(json.dumps(sub_entry, ensure_ascii=False, default=str) + "\n")

                # Diagnostics
                gt = answers.get(q.id)
                diag: dict[str, Any] = {
                    "id": q.id,
                    "business_id": q.business_id,
                    "as_of_date": q.as_of_date,
                    "question": q.question,
                    "pred_type": answer.get("type", "abstain"),
                    "pred_answer": answer.get("answer"),
                    "elapsed_ms": log.get("elapsed_ms", 0),
                    "sql": log.get("code"),
                    "error": log.get("error"),
                }
                if gt is not None and not predict_only:
                    diag["gt_type"] = gt.type
                    diag["gt_answer"] = gt.answer
                    pred_type = answer.get("type", "abstain")
                    pred_ans = answer.get("answer")
                    correct = answers_match(pred_ans, pred_type, gt)
                    if pred_type == "abstain":
                        diag["outcome"] = "abstain"
                    elif correct:
                        diag["outcome"] = "correct"
                    else:
                        diag["outcome"] = "incorrect"
                diag_f.write(json.dumps(diag, ensure_ascii=False, default=str) + "\n")

                # Accumulators
                total += 1
                total_latency_ms += log.get("elapsed_ms", 0)
                code = log.get("code")
                if code is not None:
                    sql_attempted += 1
                    output = log.get("output")
                    if isinstance(code, list):
                        if any(isinstance(o, list) for o in (output or [])):
                            sql_success += 1
                    elif isinstance(output, list):
                        sql_success += 1

                if total % 50 == 0:
                    print(f"  processed {total}/{len(questions)} questions…", file=sys.stderr)

    finally:
        agent.close()

    # ── Summary (only when ground truth is available) ────────────────────
    summary: dict[str, Any] = {
        "split": dataset.split,
        "backend": backend_name,
        "total_questions": total,
        "mean_latency_ms": round(total_latency_ms / total, 1) if total else 0.0,
        "sql_attempted": sql_attempted,
        "sql_success_rate": round(sql_success / sql_attempted, 4) if sql_attempted else None,
    }

    if not predict_only and dataset.has_answers:
        # Only score the questions we actually evaluated (respects --limit / --businesses)
        evaluated_ids = {p["id"] for p in predictions}
        subset_answers = {qid: gt for qid, gt in answers.items() if qid in evaluated_ids}
        metrics = compute_pa_score(predictions, subset_answers)
        summary.update(metrics)
        # Print a brief scorecard
        _print_summary(summary)
    else:
        print(
            f"\n── Prediction run complete ─────────────────────────────\n"
            f"  Split             : {dataset.split}\n"
            f"  Total questions   : {total}\n"
            f"  Mean latency      : {summary['mean_latency_ms']} ms/question\n"
            f"  Submission        : {submission_path}\n"
            f"  Note: no ground truth — PA not computed\n"
            f"────────────────────────────────────────────────────────"
        )

    summary_path = out_dir / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nOutputs written to {out_dir}/")
    return summary


def _print_summary(summary: dict[str, Any]) -> None:
    n = summary["total_questions"]
    print("\n── Official Evaluation Summary ─────────────────────────")
    print(f"  Split             : {summary['split']}")
    print(f"  Backend           : {summary['backend']}")
    print(f"  Total questions   : {n}")
    if "pa" in summary:
        print(f"  PA score          : {summary['pa']:.4f}  ({summary['correct']}+{summary['incorrect']}-)")
        print(f"  Accuracy          : {summary['accuracy']:.1%}  ({summary['correct']}/{n})")
        print(f"  Correct           : {summary['correct']}")
        print(f"  Incorrect         : {summary['incorrect']}")
        print(f"  Abstain           : {summary['abstain']}")
        if summary.get("missing_predictions"):
            print(f"  Missing preds     : {summary['missing_predictions']}")
    if summary.get("sql_success_rate") is not None:
        print(f"  SQL success rate  : {summary['sql_success_rate']:.1%}"
              f"  ({summary['sql_attempted']} queries)")
    print(f"  Mean latency      : {summary['mean_latency_ms']} ms/question")

    # Per-type breakdown
    if "by_type" in summary:
        print("\n  ── By answer type ──")
        for atype, counts in sorted(summary["by_type"].items()):
            nt = counts["total"]
            print(
                f"    {atype:<15} n={nt:4d}  "
                f"acc={counts['accuracy']:.1%}  pa={counts['pa']:+.4f}"
            )

    # Per-business top 5 worst performers (by PA)
    if "by_business" in summary and summary["by_business"]:
        biz_items = sorted(
            summary["by_business"].items(),
            key=lambda kv: kv[1]["pa"],
        )
        print("\n  ── Per-business (5 lowest PA) ──")
        for biz, counts in biz_items[:5]:
            print(
                f"    {biz:<12}  n={counts['total']:4d}  "
                f"pa={counts['pa']:+.4f}  acc={counts['accuracy']:.1%}"
            )

    print("────────────────────────────────────────────────────────")


# ── Entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Official DataMate evaluation CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── Dataset ──────────────────────────────────────────────────────────
    parser.add_argument(
        "--dataset",
        choices=["train", "public_test"],
        default="train",
        help="Which official split to evaluate (default: train)",
    )
    parser.add_argument(
        "--dataset-root",
        default=None,
        metavar="DIR",
        help=(
            "Override the dataset root directory.  "
            "By default resolves to <project>/<dataset>/"
        ),
    )
    parser.add_argument(
        "--businesses",
        nargs="+",
        default=None,
        metavar="BIZ_ID",
        help="Restrict evaluation to these business IDs (space-separated)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Evaluate only the first N questions after filtering",
    )
    parser.add_argument(
        "--predict-only",
        action="store_true",
        help=(
            "Generate predictions but skip PA scoring (always set for public_test; "
            "can also be used to generate train predictions without scoring)"
        ),
    )

    # ── Model ─────────────────────────────────────────────────────────────
    parser.add_argument(
        "--backend",
        choices=["mock", "transformers", "vllm"],
        default="mock",
        help="Inference backend (default: mock)",
    )
    parser.add_argument(
        "--model-path",
        default=None,
        help="Path to local model weights (required for transformers/vllm)",
    )
    parser.add_argument(
        "--tp",
        type=int,
        default=2,
        help="Tensor-parallel size for vLLM (default: 2)",
    )
    parser.add_argument(
        "--torch-dtype",
        default="bfloat16",
        choices=["bfloat16", "float16", "float32", "auto"],
        help="Weight dtype for Transformers backend (default: bfloat16)",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=1024,
        help="Max tokens to generate per query (default: 1024)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=2,
        help="SQL retry budget per question (default: 2)",
    )

    # ── Output ────────────────────────────────────────────────────────────
    parser.add_argument(
        "--out",
        default="eval_results/official",
        metavar="DIR",
        help="Output directory (default: eval_results/official/)",
    )

    args = parser.parse_args()

    # ── Resolve dataset root ─────────────────────────────────────────────
    if args.dataset_root:
        dataset_root = Path(args.dataset_root)
    else:
        dataset_root = _PROJECT_ROOT / args.dataset

    print(f"Loading dataset: {dataset_root}", file=sys.stderr)
    dataset = OfficialDataset(dataset_root, split=args.dataset)
    warnings = dataset.validate()
    for w in warnings:
        print(f"  WARNING: {w}", file=sys.stderr)
    print(f"  {dataset}", file=sys.stderr)

    # Public test never has answers → always predict-only
    predict_only = args.predict_only or (args.dataset == "public_test")

    # ── Build model ───────────────────────────────────────────────────────
    model: Any
    if args.backend == "mock":
        model = MockModel()
        print("Using MockModel (abstain baseline — no GPU needed)", file=sys.stderr)

    elif args.backend == "transformers":
        if not args.model_path:
            parser.error("--backend transformers requires --model-path")
        from src.llm import HFTransformers
        print(f"Loading HFTransformers from {args.model_path} …", file=sys.stderr)
        model = HFTransformers(
            args.model_path,
            torch_dtype=args.torch_dtype,
            max_new_tokens=args.max_new_tokens,
        )
        di = model.device_info
        print(f"  Devices: {di.get('devices', '?')}", file=sys.stderr)
        if di.get("cpu_offloading"):
            print(
                f"  WARNING: {di.get('cpu_offloaded_layers', '?')} layer(s) offloaded to CPU",
                file=sys.stderr,
            )

    elif args.backend == "vllm":
        if not args.model_path:
            parser.error("--backend vllm requires --model-path")
        from src.llm import get_model
        print(f"Loading vLLM from {args.model_path} (tp={args.tp}) …", file=sys.stderr)
        model = get_model(args.model_path, backend="vllm", tensor_parallel_size=args.tp)

    else:
        parser.error(f"Unknown backend: {args.backend}")

    out_dir = Path(args.out)
    if args.limit:
        print(f"Limiting to first {args.limit} questions.", file=sys.stderr)
    if args.businesses:
        print(f"Filtering to businesses: {args.businesses}", file=sys.stderr)

    t0 = time.monotonic()
    summary = run_official(
        dataset=dataset,
        model=model,
        out_dir=out_dir,
        limit=args.limit,
        business_ids=args.businesses,
        max_attempts=args.max_attempts,
        backend_name=args.backend,
        predict_only=predict_only,
    )
    elapsed = time.monotonic() - t0
    print(f"Total wall time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
