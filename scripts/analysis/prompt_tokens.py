"""Count real prompt tokens for the questions the router hands to the LLM (CPU only, tokenizer only).

Runs the submission pipeline with a stand-in model that applies the Qwen3 chat template,
counts tokens and abstains, so the prompts are exactly what LocalVLLM would receive
(router hints included). Use it to check MAX_MODEL_LEN before a GPU run.

    python scripts/analysis/prompt_tokens.py --data-dir data/public_test/public_test \
        --tokenizer /path/to/Qwen3-14B [--max-model-len 20480 --max-new-tokens 640]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.predict import run  # noqa: E402


class CountingModel:
    def __init__(self, tokenizer_path: str):
        from transformers import AutoTokenizer

        self.tok = AutoTokenizer.from_pretrained(tokenizer_path)
        self.counts: list[int] = []

    def generate(self, system: str, user: str):
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            prompt = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                                  enable_thinking=False)
        except TypeError:
            prompt = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        self.counts.append(len(self.tok.encode(prompt, add_special_tokens=False)))
        return json.dumps({"type": "abstain"}), None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--tokenizer", required=True, help="model folder with tokenizer files")
    ap.add_argument("--max-model-len", type=int, default=20480)
    ap.add_argument("--max-new-tokens", type=int, default=640)
    args = ap.parse_args()
    model = CountingModel(args.tokenizer)
    with tempfile.TemporaryDirectory() as out:
        run(Path(args.data_dir), Path(out), model, max_attempts=1)
    c = sorted(model.counts)
    if not c:
        print("no question reached the LLM")
        return
    limit = args.max_model_len - args.max_new_tokens
    over = sum(n > limit for n in c)
    p95 = c[min(len(c) - 1, int(0.95 * len(c)))]
    print(f"LLM prompts: {len(c)}  min {c[0]}  median {int(statistics.median(c))}  p95 {p95}  max {c[-1]} tokens")
    print(f"over {limit} (= {args.max_model_len} - {args.max_new_tokens} answer tokens): {over}")


if __name__ == "__main__":
    main()
