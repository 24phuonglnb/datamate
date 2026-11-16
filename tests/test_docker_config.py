"""Competition image config: one MODEL_PATH, a context that fits the prompts, no crash on long prompts."""
import re
import sys
from pathlib import Path

import pytest

from scripts.create_demo_data import create_demo
from src.agent import Agent
from src import llm, predict

ROOT = Path(__file__).resolve().parents[1]


class _Tok:
    """Stand-in tokenizer: one token per character."""

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True, **_):
        return "".join(m["content"] for m in messages)

    def encode(self, text, add_special_tokens=False):
        return list(text)


def _vllm(max_model_len, max_new_tokens):
    m = object.__new__(llm.LocalVLLM)  # skip __init__: no vllm / GPU needed
    m.tokenizer, m.max_model_len, m.max_new_tokens = _Tok(), max_model_len, max_new_tokens
    m.llm = None  # calling the engine would fail the test
    return m


def test_prompt_over_the_context_raises_before_the_engine():
    with pytest.raises(llm.PromptTooLongError, match="max_model_len 100"):
        _vllm(100, 40).generate("s" * 30, "u" * 31)


def test_agent_abstains_on_a_too_long_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAMATE_NO_CACHE", "1")
    create_demo(tmp_path)
    agent = Agent(_vllm(100, 40), tmp_path)
    q = {"id": "q_long", "business_id": "shop_demo", "question": "doanh thu tháng 3", "as_of_date": "2026-03-31"}
    answer, log = agent.solve(q)
    agent.close()
    assert answer == {"id": "q_long", "type": "abstain"}
    assert "PromptTooLongError" in log["error"]


def test_default_context_is_above_8192():
    import inspect
    assert inspect.signature(llm.LocalVLLM).parameters["max_model_len"].default >= 16384


def test_model_path_is_set_once_in_the_dockerfile():
    env = re.search(r"MODEL_PATH=(\S+)", (ROOT / "Dockerfile").read_text()).group(1)
    assert env == "/code/models/Qwen3-14B"
    for f in ("predict.sh", "src/predict.py", "src/llm.py", "models/README.md"):
        assert "Qwen3-8B" not in (ROOT / f).read_text(), f
    assert "--model-path" not in (ROOT / "predict.sh").read_text()
    allow = (ROOT / "Dockerfile.dockerignore").read_text()
    assert "!models/Qwen3-14B/" in allow and "!models/\n" not in allow


def test_each_dockerfile_has_its_own_ignore_file():
    assert not (ROOT / ".dockerignore").exists()  # a root file would apply to the GPU build too
    router_ignore = (ROOT / "Dockerfile.router.dockerignore").read_text()
    assert re.search(r"^models/$", router_ignore, re.M)
    gpu_ignore = (ROOT / "Dockerfile.dockerignore").read_text().splitlines()
    for needed in ("!src/", "!predict.sh", "!README.md", "!training_code/", "!requirements.txt"):
        assert needed in gpu_ignore


def test_predict_without_model_path_errors_clearly(monkeypatch, tmp_path):
    monkeypatch.delenv("MODEL_PATH", raising=False)
    monkeypatch.delenv("DATAMATE_ROUTER_ONLY", raising=False)
    monkeypatch.setattr(sys, "argv", ["predict", "--data-dir", str(tmp_path), "--result-dir", str(tmp_path)])
    with pytest.raises(SystemExit):
        predict.main()
