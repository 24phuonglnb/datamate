"""
DataMate synthetic benchmark evaluation runner.

Runs the Agent against benchmark/questions.jsonl and compares predictions
against benchmark/ground_truth.jsonl.  Reports accuracy, answer rate,
abstain rate, SQL success rate, and latency.  Saves per-question detail.

Usage — offline smoke test (no GPU, 5 questions):
    python3 eval/evaluate.py --backend mock --limit 5

Usage — full 105-question synthetic benchmark with Transformers backend:
    python3 eval/evaluate.py --backend transformers \\
        --model-path /path/to/Qwen3-14B

Usage — full benchmark with vLLM backend:
    python3 eval/evaluate.py --backend vllm \\
        --model-path /path/to/Qwen3-14B --tp 2

Usage — rebuild benchmark data first, then evaluate:
    python3 eval/evaluate.py --backend mock --build-benchmark

Outputs (written to --out directory, default eval_results/):
    summary.json          — aggregate metrics + device info
    per_question.jsonl    — per-question detail (gt, pred, correct, sql, latency)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

PARENT = Path(__file__).parent.parent
sys.path.insert(0, str(PARENT))

from src.agent import Agent


# ─── Answer comparison ────────────────────────────────────────────────────

def _float(v: Any) -> float:
    if isinstance(v, bool):
        raise TypeError
    return float(v)


def _answers_match(pred_ans: Any, gt_ans: Any, qtype: str) -> bool:
    if qtype in ("unanswerable", "abstain"):
        return True
    if pred_ans is None or gt_ans is None:
        return False
    try:
        if qtype == "number":
            pf, gf = _float(pred_ans), _float(gt_ans)
            if math.isnan(pf) or math.isnan(gf):
                return False
            tol = max(0.5, abs(gf) * 0.001)
            return abs(pf - gf) <= tol
        if qtype == "percent":
            pf, gf = _float(pred_ans), _float(gt_ans)
            return abs(pf - gf) <= 0.11
        if qtype == "boolean":
            return bool(pred_ans) == bool(gt_ans)
        if qtype == "string":
            return str(pred_ans).strip().lower() == str(gt_ans).strip().lower()
        if qtype == "date":
            return str(pred_ans).strip() == str(gt_ans).strip()
        if qtype == "list":
            ps = {str(x).strip().lower() for x in pred_ans}
            gs = {str(x).strip().lower() for x in gt_ans}
            return ps == gs
        if qtype == "table":
            if len(pred_ans) != len(gt_ans):
                return False
            for pr, gr in zip(pred_ans, gt_ans):
                pk = {k.lower(): str(v).strip().lower() for k, v in pr.items()}
                gk = {k.lower(): str(v).strip().lower() for k, v in gr.items()}
                if pk != gk:
                    return False
            return True
    except (TypeError, ValueError, AttributeError):
        return False
    return False


def _sql_succeeded(code: Any, output: Any) -> bool:
    """Return True when at least one SQL attempt returned rows (not an error string)."""
    if code is None:
        return False
    if isinstance(code, list):
        # Multiple attempts: output is a parallel list of (rows | error_string).
        return any(isinstance(item, list) for item in (output or []))
    # Single attempt: output is list-of-tuples on success, string on error.
    return isinstance(output, list)


# ─── Mock model for offline testing ──────────────────────────────────────

class MockModel:
    """Returns abstain for every question — validates the pipeline without a GPU."""

    def generate(self, system: str, user: str) -> tuple[str, None]:
        return '{"type":"abstain"}', None


# ─── Evaluation runner ────────────────────────────────────────────────────

def evaluate(
    benchmark_root: Path,
    model: Any,
    out_dir: Path,
    max_attempts: int = 2,
    limit: int | None = None,
    backend_name: str = "unknown",
) -> dict[str, Any]:
    """Run *model* on the benchmark and return an aggregate metrics dict.

    Parameters
    ----------
    benchmark_root:
        Directory containing ``questions.jsonl`` and ``ground_truth.jsonl``.
    model:
        Any object with a ``generate(system, user) -> (str, str|None)`` method.
    out_dir:
        Where ``summary.json`` and ``per_question.jsonl`` are written.
    max_attempts:
        How many SQL retries the Agent is allowed per question.
    limit:
        If set, only the first *N* questions are evaluated (useful for smoke tests).
    backend_name:
        Human-readable label stored in ``summary.json["backend"]``.
    """
    questions_path = benchmark_root / "questions.jsonl"
    gt_path = benchmark_root / "ground_truth.jsonl"

    if not questions_path.is_file():
        raise FileNotFoundError(f"questions.jsonl not found: {questions_path}")
    if not gt_path.is_file():
        raise FileNotFoundError(f"ground_truth.jsonl not found: {gt_path}")

    questions: list[dict] = []
    with questions_path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line))

    if limit is not None:
        questions = questions[:limit]

    ground_truth: dict[str, dict] = {}
    with gt_path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                gt = json.loads(line)
                ground_truth[gt["id"]] = gt

    out_dir.mkdir(parents=True, exist_ok=True)
    agent = Agent(model, benchmark_root, max_attempts=max_attempts)

    per_question: list[dict] = []
    total = 0
    correct = 0
    answered = 0
    abstained = 0
    sql_success = 0
    sql_attempted = 0
    total_latency_ms = 0.0

    try:
        for q in questions:
            qid = q["id"]
            gt = ground_truth.get(qid, {})
            gt_type = gt.get("type", "unanswerable")
            gt_ans = gt.get("answer")

            answer, log = agent.solve(q)

            pred_type = answer.get("type", "abstain")
            pred_ans = answer.get("answer")
            elapsed = log.get("elapsed_ms", 0)
            total_latency_ms += elapsed
            total += 1

            if pred_type == "abstain":
                abstained += 1
            elif pred_type != "unanswerable":
                answered += 1

            code = log.get("code")
            output = log.get("output")
            if code is not None:
                sql_attempted += 1
                if _sql_succeeded(code, output):
                    sql_success += 1

            if gt_type == "unanswerable":
                is_correct = pred_type == "unanswerable"
            elif pred_type == "abstain":
                is_correct = False
            elif pred_type != gt_type:
                is_correct = False
            else:
                is_correct = _answers_match(pred_ans, gt_ans, gt_type)

            if is_correct:
                correct += 1

            per_question.append({
                "id": qid,
                "gt_type": gt_type,
                "gt_answer": gt_ans,
                "pred_type": pred_type,
                "pred_answer": pred_ans,
                "correct": is_correct,
                "elapsed_ms": elapsed,
                "sql": log.get("code"),
                "error": log.get("error"),
            })
    finally:
        agent.close()

    with (out_dir / "per_question.jsonl").open("w", encoding="utf-8") as f:
        for row in per_question:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    sql_sr = (sql_success / sql_attempted) if sql_attempted else None
    summary: dict[str, Any] = {
        "backend": backend_name,
        "total_questions": total,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "correct": correct,
        "answer_rate": round(answered / total, 4) if total else 0.0,
        "abstain_rate": round(abstained / total, 4) if total else 0.0,
        "unanswerable_rate": round((total - answered - abstained) / total, 4) if total else 0.0,
        "sql_attempted": sql_attempted,
        "sql_success_rate": round(sql_sr, 4) if sql_sr is not None else None,
        "mean_latency_ms": round(total_latency_ms / total, 1) if total else 0.0,
        "note": "Synthetic benchmark only — does not equal official competition score.",
    }

    # Include device placement info if the backend exposes it.
    if hasattr(model, "device_info"):
        try:
            summary["device_info"] = model.device_info
        except Exception:
            pass

    with (out_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return summary


# ─── CLI display ──────────────────────────────────────────────────────────

def _print_summary(summary: dict[str, Any]) -> None:
    n = summary["total_questions"]
    print("\n── Evaluation Summary ──────────────────────────────────")
    print(f"  Backend           : {summary['backend']}")
    print(f"  Total questions   : {n}")
    print(f"  Accuracy          : {summary['accuracy']:.1%}  ({summary['correct']}/{n})")
    print(f"  Answer rate       : {summary['answer_rate']:.1%}")
    print(f"  Abstain rate      : {summary['abstain_rate']:.1%}")
    if summary.get("sql_success_rate") is not None:
        print(f"  SQL success rate  : {summary['sql_success_rate']:.1%}"
              f"  ({summary['sql_attempted']} queries attempted)")
    print(f"  Mean latency      : {summary['mean_latency_ms']} ms/question")
    if "device_info" in summary:
        di = summary["device_info"]
        print(f"  Devices           : {di.get('devices', '?')}")
        if di.get("cpu_offloading"):
            print(f"  CPU-offloaded     : {di.get('cpu_offloaded_layers', '?')} layer(s)")
    print(f"  Note: {summary['note']}")
    print("────────────────────────────────────────────────────────")


# ─── Entry point ─────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate DataMate agent on the synthetic benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--benchmark",
        default=str(Path(__file__).parent.parent / "benchmark"),
        help="Path to benchmark root (default: benchmark/)",
    )
    parser.add_argument(
        "--out", default="eval_results",
        help="Output directory (default: eval_results/)",
    )
    parser.add_argument(
        "--backend", choices=["mock", "transformers", "vllm"], default="mock",
        help="Inference backend: mock (offline), transformers (HF), vllm",
    )
    parser.add_argument(
        "--model-path", default=None,
        help="Path to local model weights (required for transformers/vllm backends)",
    )
    parser.add_argument(
        "--tp", type=int, default=2,
        help="Tensor-parallel size for the vLLM backend (default: 2)",
    )
    parser.add_argument(
        "--torch-dtype", default="bfloat16",
        choices=["bfloat16", "float16", "float32", "auto"],
        help="Weight dtype for Transformers backend (default: bfloat16)",
    )
    parser.add_argument(
        "--max-new-tokens", type=int, default=1024,
        help="Maximum tokens to generate per query (default: 1024)",
    )
    parser.add_argument(
        "--max-attempts", type=int, default=2,
        help="Max SQL retry attempts per question (default: 2)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        metavar="N",
        help="Only evaluate the first N questions (e.g. --limit 5 for a smoke test)",
    )
    parser.add_argument(
        "--build-benchmark", action="store_true",
        help="(Re)generate benchmark data before evaluating",
    )
    # Backwards-compatible alias.
    parser.add_argument(
        "--mock", action="store_true",
        help="[deprecated] Alias for --backend mock",
    )
    args = parser.parse_args()

    # --mock overrides --backend for backwards compatibility.
    if args.mock:
        args.backend = "mock"

    benchmark_root = Path(args.benchmark)
    if args.build_benchmark or not (benchmark_root / "questions.jsonl").is_file():
        print("Building benchmark data...", file=sys.stderr)
        from benchmark.create_benchmark import build_benchmark
        build_benchmark(benchmark_root)

    model: Any
    if args.backend == "mock":
        model = MockModel()
        print("Using MockModel (abstain baseline — no GPU needed)", file=sys.stderr)

    elif args.backend == "transformers":
        if not args.model_path:
            parser.error("--backend transformers requires --model-path")
        from src.llm import HFTransformers
        print(f"Loading HFTransformers from {args.model_path} ...", file=sys.stderr)
        model = HFTransformers(
            args.model_path,
            torch_dtype=args.torch_dtype,
            max_new_tokens=args.max_new_tokens,
        )
        di = model.device_info
        print(f"Model loaded. Devices: {di.get('devices', '?')}", file=sys.stderr)
        if di.get("cpu_offloading"):
            print(
                f"  WARNING: {di.get('cpu_offloaded_layers', '?')} layer(s) offloaded to CPU "
                "(expect slower inference)",
                file=sys.stderr,
            )

    elif args.backend == "vllm":
        if not args.model_path:
            parser.error("--backend vllm requires --model-path")
        from src.llm import get_model
        print(f"Loading vLLM from {args.model_path} (tp={args.tp}) ...", file=sys.stderr)
        model = get_model(args.model_path, backend="vllm", tensor_parallel_size=args.tp)

    else:
        # Should be unreachable given choices=.
        parser.error(f"Unknown backend: {args.backend}")

    out_dir = Path(args.out)
    if args.limit:
        print(f"Limiting evaluation to first {args.limit} questions.", file=sys.stderr)

    t0 = time.monotonic()
    summary = evaluate(
        benchmark_root,
        model,
        out_dir,
        max_attempts=args.max_attempts,
        limit=args.limit,
        backend_name=args.backend,
    )
    elapsed = time.monotonic() - t0

    _print_summary(summary)
    print(f"\nResults saved to {out_dir}/")
    print(f"Total wall time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
