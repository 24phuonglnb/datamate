"""DataMate competition entrypoint. Reads /data and streams /result answers."""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

from .agent import Agent
from .llm import LocalVLLM
from .nlu.normalize import RuleNormalizer
from .router import Router
from .router.pipeline import solve as solve_routed


def run(data_dir: Path, result_dir: Path, model, max_attempts: int = 2) -> int:
    questions_file = data_dir / "questions.jsonl"
    if not questions_file.is_file():
        raise FileNotFoundError(f"No questions.jsonl: {questions_file}")
    result_dir.mkdir(parents=True, exist_ok=True)
    logdir = result_dir / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    answers_path = result_dir / "submission.jsonl"
    log_path = logdir / "questions.jsonl"
    agent = Agent(model, data_dir, max_attempts=max_attempts)
    # Router first (templates over the views), LLM agent for the rest; DATAMATE_ROUTER=0 disables it.
    use_router = os.environ.get("DATAMATE_ROUTER", "1").lower() not in ("0", "false", "no")
    router = Router() if use_router else None
    normalizer = RuleNormalizer(data_dir / "calendar.csv") if use_router else None
    count = 0
    try:
        # Open in write mode for a clean, deterministic run. Flush each answer.
        with questions_file.open("r", encoding="utf-8") as input_file, \
             answers_path.open("w", encoding="utf-8", buffering=1) as answers, \
             log_path.open("w", encoding="utf-8", buffering=1) as logs:
            for line in input_file:
                if not line.strip():
                    continue
                try:
                    question = json.loads(line)
                    answer, log = solve_routed(question, agent, router, normalizer)
                except Exception as exc:
                    qid = ""
                    try:
                        qid = str(json.loads(line).get("id", ""))
                    except Exception:
                        pass
                    answer = {"id": qid, "type": "abstain"}
                    log = {"id": qid, "answer": answer, "elapsed_ms": 0, "thinking": None, "error": repr(exc)}
                answers.write(json.dumps(answer, ensure_ascii=False, default=str) + "\n")
                answers.flush()
                logs.write(json.dumps(log, ensure_ascii=False, default=str) + "\n")
                logs.flush()
                count += 1
                if count % 20 == 0:
                    print(f"Processed {count} questions", file=sys.stderr, flush=True)
    finally:
        agent.close()
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "/data"))
    parser.add_argument("--result-dir", default=os.environ.get("RESULT_DIR", "/result"))
    parser.add_argument("--model-path", default=os.environ.get("MODEL_PATH", "/code/models/Qwen3-8B"))
    parser.add_argument("--tensor-parallel-size", type=int, default=int(os.environ.get("TP_SIZE", "2")))
    parser.add_argument("--max-attempts", type=int, default=int(os.environ.get("MAX_ATTEMPTS", "2")))
    args = parser.parse_args()
    random.seed(42)
    model = LocalVLLM(args.model_path, args.tensor_parallel_size)
    print(f"Loaded local model at {args.model_path}; inference is offline", file=sys.stderr)
    n = run(Path(args.data_dir), Path(args.result_dir), model, args.max_attempts)
    print(f"Wrote {n} predictions to {args.result_dir}/submission.jsonl", file=sys.stderr)


if __name__ == "__main__":
    main()
