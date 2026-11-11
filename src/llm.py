"""LLM backends for DataMate.  Three options, same interface:

  HFTransformers  — Hugging Face Transformers + Accelerate (target backend)
  LocalVLLM       — vLLM server-style inference (competition Docker backend)
  MockLLM         — deterministic test double; never downloads anything

All backends expose exactly:
    generate(system: str, user: str) -> tuple[str, str | None]
      Returns (raw_text, thinking_text_or_None).

HFTransformers additionally exposes:
    device_info -> dict   (placement across GPUs / CPU offload summary)
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


# ─── Mock (offline test double) ───────────────────────────────────────────

class MockLLM:
    """Deterministic offline test double.  NOT part of the competition pipeline.

    Replays pre-canned responses in order; falls back to abstain when exhausted.
    """

    def __init__(self, responses: list[str] | None = None):
        self._responses = iter(responses or [])
        self._default = '{"type":"abstain"}'

    def generate(self, system: str, user: str) -> tuple[str, None]:
        try:
            return next(self._responses), None
        except StopIteration:
            return self._default, None


# ─── HFTransformers (primary inference backend) ───────────────────────────

class HFTransformers:
    """Hugging Face Transformers + Accelerate inference backend.

    Loads the model once into ``device_map='auto'`` and keeps it resident for
    all queries.  Passes ``attention_mask`` to generate and uses deterministic
    (greedy) decoding.

    Target environment: Python 3.10, Torch 2.5.1+cu121,
        Transformers ≥4.52, Accelerate ≥1.7, 2 × RTX A5000 24 GB.

    Qwen3-14B example::

        model = HFTransformers(
            "/models/Qwen3-14B",
            torch_dtype="bfloat16",
            max_new_tokens=1024,
        )

    With explicit device map (e.g. CPU-offload on constrained hardware)::

        model = HFTransformers(
            "/models/Qwen3-14B",
            device_map={"": "cuda:0"},   # single-GPU, no offload
        )
    """

    def __init__(
        self,
        model_path: str,
        device_map: str | dict = "auto",
        max_new_tokens: int = 1024,
        torch_dtype: str = "bfloat16",
        trust_remote_code: bool = False,
        attn_implementation: str | None = None,
    ):
        if not Path(model_path).is_dir():
            raise FileNotFoundError(
                f"Model weights not found: {model_path}. "
                "Download or copy the checkpoint before running."
            )

        # Lazy imports — only fail at construction time if the packages are absent.
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

        self.max_new_tokens = max_new_tokens
        self._device_map = device_map
        self._torch = torch

        _dtype_map: dict[str, Any] = {
            "bfloat16": torch.bfloat16,
            "float16": torch.float16,
            "float32": torch.float32,
            "auto": "auto",
        }
        resolved_dtype = _dtype_map.get(torch_dtype, "auto")

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path, trust_remote_code=trust_remote_code
        )

        load_kwargs: dict[str, Any] = {
            "device_map": device_map,
            "torch_dtype": resolved_dtype,
            "trust_remote_code": trust_remote_code,
        }
        if attn_implementation:
            load_kwargs["attn_implementation"] = attn_implementation

        self.model = AutoModelForCausalLM.from_pretrained(model_path, **load_kwargs)
        self.model.eval()

    # ── device placement reporting ────────────────────────────────────────

    @property
    def device_info(self) -> dict:
        """Return a summary of which device(s) the model layers are on.

        ``cpu_offloading: True`` appears when Accelerate has placed some layers
        on CPU RAM.  Users should check this when memory is tight.
        """
        info: dict[str, Any] = {"device_map": str(self._device_map)}
        hf_map = getattr(self.model, "hf_device_map", None)
        if hf_map:
            devices = sorted({str(v) for v in hf_map.values()})
            cpu_layers = [k for k, v in hf_map.items() if str(v) == "cpu"]
            info["devices"] = devices
            info["total_layers_mapped"] = len(hf_map)
            if cpu_layers:
                info["cpu_offloading"] = True
                info["cpu_offloaded_layers"] = len(cpu_layers)
        else:
            # Fallback for single-device models without an hf_device_map attribute.
            try:
                dev = str(next(iter(self.model.parameters())).device)
                info["devices"] = [dev]
            except StopIteration:
                pass
        return info

    # ── inference ────────────────────────────────────────────────────────

    def generate(self, system: str, user: str) -> tuple[str, str | None]:
        torch = self._torch
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

        # apply_chat_template with enable_thinking=False, return_dict=True, return_tensors='pt'.
        # Fall back to omitting enable_thinking for tokenizers that don't support it.
        try:
            inputs = self.tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                enable_thinking=False,
                return_dict=True,
                return_tensors="pt",
            )
        except TypeError:
            inputs = self.tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt",
            )

        # With device_map='auto' the model may span multiple GPUs; move inputs
        # to whichever device holds the first layer (embedding / input projection).
        try:
            first_device = next(iter(self.model.parameters())).device
        except StopIteration:
            first_device = torch.device("cpu")

        input_ids: Any = inputs["input_ids"].to(first_device)
        attention_mask: Any = inputs["attention_mask"].to(first_device)
        prompt_len: int = input_ids.shape[-1]

        with torch.no_grad():
            output_ids = self.model.generate(
                input_ids,
                attention_mask=attention_mask,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                temperature=1.0,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        # Decode only the new tokens (not the echoed prompt).
        new_tokens = output_ids[0][prompt_len:]
        text: str = self.tokenizer.decode(new_tokens, skip_special_tokens=True)

        thinking = re.findall(r"<think>(.*?)</think>", text, flags=re.S)
        return text, "\n".join(thinking) if thinking else None


# ─── vLLM (competition Docker backend) ───────────────────────────────────

class LocalVLLM:
    """Offline vLLM inference backend.

    Requires vllm package, CUDA-capable GPU, and weights in ``model_path``.

    Qwen3-14B::
        model = LocalVLLM("/models/Qwen3-14B", tensor_parallel_size=2,
                          max_model_len=16384, max_new_tokens=1024)
    Qwen3-8B (default)::
        model = LocalVLLM("/models/Qwen3-8B", tensor_parallel_size=2)
    """

    def __init__(
        self,
        model_path: str,
        tensor_parallel_size: int = 2,
        max_model_len: int = 8192,
        max_new_tokens: int = 640,
        temperature: float = 0.0,
        gpu_memory_utilization: float = 0.85,
    ):
        if not Path(model_path).is_dir():
            raise FileNotFoundError(
                f"Inference model missing: {model_path}. Copy weights before running."
            )
        from vllm import LLM, SamplingParams

        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        self.params = SamplingParams(
            temperature=temperature, top_p=1.0, max_tokens=max_new_tokens
        )
        self.llm = LLM(
            model=model_path,
            tensor_parallel_size=tensor_parallel_size,
            max_model_len=max_model_len,
            trust_remote_code=False,
            gpu_memory_utilization=gpu_memory_utilization,
        )
        self.tokenizer = self.llm.get_tokenizer()

    def generate(self, system: str, user: str) -> tuple[str, str | None]:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            prompt = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
        except TypeError:
            prompt = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        text = self.llm.generate([prompt], self.params, use_tqdm=False)[0].outputs[0].text
        thinking = re.findall(r"<think>(.*?)</think>", text, flags=re.S)
        return text, "\n".join(thinking) if thinking else None


# ─── Helpers ──────────────────────────────────────────────────────────────

def qwen3_14b(model_path: str, tensor_parallel_size: int = 2) -> LocalVLLM:
    """Return a LocalVLLM configured for Qwen3-14B (vLLM backend).

    For the HF-Transformers backend use HFTransformers directly.
    """
    return LocalVLLM(
        model_path=model_path,
        tensor_parallel_size=tensor_parallel_size,
        max_model_len=16384,
        max_new_tokens=1024,
        temperature=0.0,
        gpu_memory_utilization=0.88,
    )


def get_model(
    model_path: str,
    backend: str = "transformers",
    tensor_parallel_size: int = 2,
    **kwargs: Any,
) -> HFTransformers | LocalVLLM:
    """Factory: return the right backend for *model_path* and *backend*.

    backend='transformers'  → HFTransformers (device_map='auto')
    backend='vllm'          → LocalVLLM (auto-detects 14B config)
    """
    if backend == "transformers":
        return HFTransformers(model_path, **kwargs)
    if backend == "vllm":
        name = Path(model_path).name.lower()
        if "14b" in name:
            return qwen3_14b(model_path, tensor_parallel_size)
        return LocalVLLM(model_path, tensor_parallel_size, **kwargs)
    raise ValueError(f"Unknown backend {backend!r}. Choose 'transformers' or 'vllm'.")
