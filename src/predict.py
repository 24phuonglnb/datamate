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
from .router.db import ConnectionProvider
from .router.rule_guard import RuleGuard
from .router.gate import load_gate
from .router.pipeline import AbstainAgent, solve as solve_routed


def _lines_grouped_by_shop(path: Path) -> list[str]:
    """Question lines grouped by shop (stable: file order inside a shop, shops in sorted order).

    questions.jsonl is shuffled across shops; opening a shop (ingestion or cache hash) costs seconds, so alternating
    shops is very slow.  The order is deterministic; answers are matched by id, not by position."""
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def key(item: tuple[int, str]) -> tuple[str, int]:
        i, l = item
        try:
            return str(json.loads(l).get("business_id", "")), i
        except Exception:
            return "\uffff", i  # unreadable lines last; the loop below turns them into abstain lines

    return [l for _, l in sorted(enumerate(lines), key=key)]


def run(data_dir: Path, result_dir: Path, model, max_attempts: int = 2) -> int:
    questions_file = data_dir / "questions.jsonl"
    if not questions_file.is_file():
        raise FileNotFoundError(f"No questions.jsonl: {questions_file}")
    result_dir.mkdir(parents=True, exist_ok=True)
    logdir = result_dir / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    answers_path = result_dir / "submission.jsonl"
    log_path = logdir / "questions.jsonl"
    # model None = router-only run: no weights, no GPU; questions the router does not answer abstain
    agent = Agent(model, data_dir, max_attempts=max_attempts) if model is not None else AbstainAgent()
    # Router first (templates over the views), LLM agent for the rest; DATAMATE_ROUTER=0 disables it.
    use_router = os.environ.get("DATAMATE_ROUTER", "1").lower() not in ("0", "false", "no")
    rule_guard = None
    if use_router and (data_dir / "rulebook.md").is_file():
        rule_guard = RuleGuard.load(data_dir / "rulebook.md")  # intents whose rulebook rows changed are switched off
    router = Router(rule_guard) if use_router else None
    tet_bare = rule_guard.defines("2", "tet") if rule_guard is not None else True  # undefined Tết stays ambiguous
    normalizer = RuleNormalizer(data_dir / "calendar.csv", tet_bare=tet_bare) if use_router else None
    provider = ConnectionProvider(data_dir) if use_router else None
    gate = load_gate(os.environ.get("DATAMATE_LLM_GATE")) if use_router else None  # None: the LLM answers everything
    count = 0
    try:
        # Open in write mode for a clean, deterministic run. Flush each answer.
        with answers_path.open("w", encoding="utf-8", buffering=1) as answers, \
             log_path.open("w", encoding="utf-8", buffering=1) as logs:
            for line in _lines_grouped_by_shop(questions_file):
                try:
                    question = json.loads(line)
                    answer, log = solve_routed(question, agent, router, normalizer, provider, gate)
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
        if provider is not None:
            provider.close()
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "/data"))
    parser.add_argument("--result-dir", default=os.environ.get("RESULT_DIR", "/result"))
    # MODEL_PATH / TP_SIZE / MAX_MODEL_LEN: set once in the Dockerfile ENV; no model default here.
    parser.add_argument("--model-path", default=os.environ.get("MODEL_PATH"))
    parser.add_argument("--tensor-parallel-size", type=int, default=int(os.environ.get("TP_SIZE", "2")))
    parser.add_argument("--max-model-len", type=int,
                        default=int(os.environ["MAX_MODEL_LEN"]) if os.environ.get("MAX_MODEL_LEN") else None)
    parser.add_argument("--max-attempts", type=int, default=int(os.environ.get("MAX_ATTEMPTS", "2")))
    parser.add_argument("--router-only", action="store_true",
                        default=os.environ.get("DATAMATE_ROUTER_ONLY", "0").lower() in ("1", "true", "yes"),
                        help="do not load a model: answer with the router only, abstain on the rest")
    args = parser.parse_args()
    random.seed(42)
    if args.router_only:
        model = None
        print("Router-only run: no model is loaded", file=sys.stderr)
    else:
        if not args.model_path:
            parser.error("set MODEL_PATH (Dockerfile ENV) or --model-path, or use --router-only")
        extra = {"max_model_len": args.max_model_len} if args.max_model_len else {}
        model = LocalVLLM(args.model_path, args.tensor_parallel_size, **extra)
        print(f"Loaded local model at {args.model_path}; inference is offline", file=sys.stderr)
    n = run(Path(args.data_dir), Path(args.result_dir), model, args.max_attempts)
    print(f"Wrote {n} predictions to {args.result_dir}/submission.jsonl", file=sys.stderr)


if __name__ == "__main__":
    main()
