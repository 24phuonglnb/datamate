"""Self-consistency vote around the LLM agent: ask the agent k times with sampling and answer only when enough of the
samples agree, else abstain.  `src/agent.py` is not modified: this class has the same `solve(question, hints=None)`
as `Agent`, so `pipeline.call_agent` and `predict.py` use it unchanged.

    DATAMATE_LLM_VOTE_K            number of samples per question (default 1 = off: the agent is called once, as before)
    DATAMATE_LLM_VOTE_THRESHOLD    share of the k samples that must give the same answer (default 0.6)
    DATAMATE_LLM_VOTE_TEMPERATURE  sampling temperature of the k calls (default 0.7)
    DATAMATE_LLM_VOTE_BUDGET_S     optional wall-clock budget per question in seconds (default 0 = none)
    DATAMATE_LLM_VOTE_FULL         1 = always ask all k samples (no early stop), so the per-sample log can be re-voted
                                   offline with any threshold (`eval/vote_sweep.py`)

Every sample (answer, SQL, output, error, time) is kept in `log["vote"]["samples"]` of the run log.

SQL: every sample's SQL is run by `Agent.solve` through `BusinessDB.execute_readonly` (only SELECT / WITH, 12 s time
limit, at most 500 rows); a sample whose SQL fails or times out is an abstain sample.  Nothing else touches the data here.

Agreement: two answers are the same when the PA scorer (`eval.pa_score.score_one`, rulebook section 9: numbers exact,
percent to 2 decimals, dates, strings without accents/case, lists in order, ...) calls one correct against the other.  When
`eval` is not importable (the images copy only `src/`) a strict fallback is used: same type and the same JSON value.
An abstain / failed sample is a vote for "no answer": agreement = size of the largest group of equal answers / k.

Sampling: set on the model the agent holds.  vLLM (`LocalVLLM.params`) and any model with `set_sampling(temperature, seed)`
are supported.  `HFTransformers` generates greedily with the settings hard-coded in `generate`, so k samples would be
identical; the vote then stays off with a warning instead of pretending to vote.
"""
from __future__ import annotations

import copy
import json
import logging
import math
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

ENV_K = "DATAMATE_LLM_VOTE_K"
ENV_THRESHOLD = "DATAMATE_LLM_VOTE_THRESHOLD"
ENV_TEMPERATURE = "DATAMATE_LLM_VOTE_TEMPERATURE"
ENV_BUDGET = "DATAMATE_LLM_VOTE_BUDGET_S"
ENV_FULL = "DATAMATE_LLM_VOTE_FULL"
DEFAULT_THRESHOLD = 0.6
DEFAULT_TEMPERATURE = 0.7

try:   # the scorer lives in eval/ (not copied into the Docker images)
    from eval.pa_score import score_one as _score_one
except Exception:   # pragma: no cover - depends on the packaging
    _score_one = None


def _strict_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return a.get("type") == b.get("type") and json.dumps(a.get("answer"), sort_keys=True, default=str) == json.dumps(
        b.get("answer"), sort_keys=True, default=str)


def same_answer(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Are two answer dicts the same answer for the PA scorer?  (abstain never equals anything, even itself)"""
    if a.get("type") in (None, "abstain") or b.get("type") in (None, "abstain"):
        return False
    if _score_one is None:
        return _strict_equal(a, b)
    gold = {"type": b.get("type"), "answer": b.get("answer")}
    try:
        return _score_one(a, gold)[0] == 1
    except Exception:
        return _strict_equal(a, b)


def needed_votes(k: int, threshold: float) -> int:
    """Smallest number of equal answers that reaches the threshold (never less than 1)."""
    return max(1, math.ceil(threshold * k - 1e-9))


def set_sampling(model: Any, temperature: float, seed: int | None) -> Any | None:
    """Switch `model` to sampling; -> a restore token (pass to `restore_sampling`) or None when it cannot sample."""
    if model is None:
        return None
    if hasattr(model, "set_sampling"):
        old = model.set_sampling(temperature, seed)
        return ("method", old)
    params = getattr(model, "params", None)     # vllm.SamplingParams held by LocalVLLM
    if params is not None and hasattr(params, "temperature"):
        new = copy.copy(params)
        new.temperature = temperature
        if seed is not None and hasattr(new, "seed"):
            new.seed = seed
        model.params = new
        return ("params", params)
    return None


def restore_sampling(model: Any, token: Any) -> None:
    if token is None or model is None:
        return
    kind, old = token
    if kind == "params":
        model.params = old
    elif hasattr(model, "restore_sampling"):
        model.restore_sampling(old)


def _short(v: Any, limit: int = 400) -> Any:
    """Output of a sample's SQL, shortened so that the per-sample log stays small."""
    text = json.dumps(v, ensure_ascii=False, default=str)
    return v if len(text) <= limit else text[:limit] + "..."


def can_sample(model: Any) -> bool:
    return model is not None and (hasattr(model, "set_sampling") or hasattr(getattr(model, "params", None), "temperature"))


class VoteAgent:
    """`solve(question, hints=None)` like `Agent`, answering by self-consistency over `k` sampled agent calls."""

    def __init__(self, agent: Any, k: int, threshold: float = DEFAULT_THRESHOLD, temperature: float = DEFAULT_TEMPERATURE,
                 base_seed: int = 20261115, budget_s: float = 0.0, full: bool = False):
        if k < 1:
            raise ValueError("k must be >= 1")
        if not 0.0 < threshold <= 1.0:
            raise ValueError("threshold must be in (0, 1]")
        self.agent, self.k, self.threshold = agent, k, threshold
        self.temperature, self.base_seed, self.budget_s, self.full = temperature, base_seed, budget_s, full

    @property
    def model(self) -> Any:
        return getattr(self.agent, "model", None)

    def close(self) -> None:
        close = getattr(self.agent, "close", None)
        if callable(close):
            close()

    def _call(self, question: dict[str, Any], hints: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            import inspect
            takes_hints = "hints" in inspect.signature(self.agent.solve).parameters
        except (TypeError, ValueError):
            takes_hints = False
        return self.agent.solve(question, hints=hints) if (hints is not None and takes_hints) else self.agent.solve(question)

    def solve(self, question: dict[str, Any], hints: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        qid = str(question.get("id", ""))
        began = time.monotonic()
        abstain = {"id": qid, "type": "abstain"}
        if self.k <= 1:
            return self._call(question, hints)
        groups: list[list[dict[str, Any]]] = []      # groups of equal answers
        evidence: list[dict[str, Any]] = []          # the run log of the first sample of each group
        samples: list[dict[str, Any]] = []           # every sample, for offline re-voting
        n_abstain = n_asked = 0
        need = needed_votes(self.k, self.threshold)
        for i in range(self.k):
            if self.budget_s and time.monotonic() - began > self.budget_s and n_asked:
                break
            token = set_sampling(self.model, self.temperature, self.base_seed + i)
            try:
                ans, log = self._call(question, hints)
            except Exception as exc:     # one failed sample is one abstain vote, never an error for the question
                logger.warning("q=%s sample=%d failed: %s", qid, i, type(exc).__name__)
                ans, log = abstain, {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            finally:
                restore_sampling(self.model, token)
            n_asked += 1
            samples.append({"i": i, "answer": ans if isinstance(ans, dict) else None,
                            "code": log.get("code") if isinstance(log, dict) else None,
                            "output": _short(log.get("output")) if isinstance(log, dict) else None,
                            "error": log.get("error") if isinstance(log, dict) else None,
                            "elapsed_ms": log.get("elapsed_ms") if isinstance(log, dict) else None})
            if not isinstance(ans, dict) or ans.get("type") in (None, "abstain"):
                n_abstain += 1
            else:
                for g in groups:
                    if same_answer(ans, g[0]):
                        g.append(ans)
                        break
                else:
                    groups.append([ans])
                    evidence.append(log if isinstance(log, dict) else {})
            top = max((len(g) for g in groups), default=0)
            if self.full:
                continue
            if self.threshold > 0.5 and top >= need:          # decided: no other group can reach the threshold
                break
            if top + (self.k - n_asked) < need:               # cannot reach the threshold any more
                break
        top_group = max(groups, key=len, default=[])
        agreement = len(top_group) / self.k
        tied = sum(1 for g in groups if len(g) == len(top_group)) > 1     # two different answers with the same support: no answer
        decided = bool(top_group) and len(top_group) >= need and not tied
        answer = {**top_group[0], "id": qid} if decided else abstain
        out_log = {"id": qid, "answer": answer, "elapsed_ms": int((time.monotonic() - began) * 1000), "thinking": None,
                   "code": None, "output": None,
                   "vote": {"k": self.k, "asked": n_asked, "threshold": self.threshold, "agreement": round(agreement, 4),
                            "groups": sorted((len(g) for g in groups), reverse=True), "abstain_samples": n_abstain,
                            "decided": decided, "samples": samples}}
        if decided:                                            # keep the SQL and output of the winning group for the run log
            win = evidence[groups.index(top_group)]
            out_log["code"], out_log["output"] = win.get("code"), win.get("output")
        return answer, out_log


def maybe_vote(agent: Any, environ: dict[str, str] | None = None) -> Any:
    """Wrap `agent` in a `VoteAgent` when DATAMATE_LLM_VOTE_K >= 2 (and the model can sample); else return it unchanged."""
    env = os.environ if environ is None else environ
    try:
        k = int(env.get(ENV_K, "1") or "1")
    except ValueError:
        logger.warning("%s is not an integer: vote off", ENV_K)
        return agent
    if k < 2:
        return agent
    try:
        threshold = float(env.get(ENV_THRESHOLD, DEFAULT_THRESHOLD) or DEFAULT_THRESHOLD)
        temperature = float(env.get(ENV_TEMPERATURE, DEFAULT_TEMPERATURE) or DEFAULT_TEMPERATURE)
        budget = float(env.get(ENV_BUDGET, "0") or "0")
        if not 0.0 < threshold <= 1.0 or temperature <= 0:
            raise ValueError("threshold must be in (0, 1], temperature > 0")
    except ValueError as exc:
        logger.warning("bad vote setting (%s): vote off", exc)
        return agent
    if not can_sample(getattr(agent, "model", None)):
        logger.warning("the model cannot sample (greedy backend): vote off")
        return agent
    return VoteAgent(agent, k, threshold, temperature, budget_s=budget, full=env.get(ENV_FULL, "0") == "1")
