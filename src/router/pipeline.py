"""Pipeline glue: router first, LLM agent only for what the router does not answer. agent.py is not modified.

`provider` = ConnectionProvider (src/router/db.py): shop views via the ingestion layer, not via the agent."""
from __future__ import annotations

import inspect
import time
from typing import Any, Callable

from . import gate as G
from .hints import build_hints
from .router import RouteDecision, Router


class AbstainAgent:
    """Stand-in for the LLM agent in router-only runs (no model, no GPU): every question the router leaves abstains."""

    def solve(self, question: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        qid = str(question.get("id", ""))
        answer = {"id": qid, "type": "abstain"}
        return answer, {"id": qid, "answer": answer, "elapsed_ms": 0, "thinking": None, "code": None, "output": None}

    def close(self) -> None:
        pass


def _accepts_hints(agent: Any) -> bool:
    try:
        params = inspect.signature(agent.solve).parameters
    except (TypeError, ValueError):
        return False
    return "hints" in params or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


def call_agent(agent: Any, question: dict[str, Any], hints: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """agent.solve(question, hints=hints) when the agent takes `hints`, else agent.solve(question) as before.

    The signature is inspected instead of catching TypeError so that a TypeError raised inside a (slow) model call is
    never mistaken for 'no hints parameter' and the call is never repeated."""
    if hints is not None and _accepts_hints(agent):
        return agent.solve(question, hints=hints)
    return agent.solve(question)


def solve(question: dict[str, Any], agent: Any, router: Router | None, normalizer: Callable[..., Any] | None,
          provider: Any = None, gate: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """-> (answer, log). log["router"] = {route, reason, intent, params} for every question.

    Questions that fall to the LLM go to `call_agent` with hints (normalized text, periods, where_sql, matched entities,
    fallthrough reason).  With a `gate` (llm_gate.json) a question whose kind is not enabled abstains instead."""
    qid = str(question.get("id", ""))
    began = time.monotonic()
    decision = RouteDecision("llm", "router_disabled")
    nq = conn = None
    if router is not None and normalizer is not None and provider is not None:
        try:
            nq = normalizer(str(question.get("question", "")), str(question.get("as_of_date", "")))
            conn = provider.connection(str(question["business_id"]))
            bad = provider.flags(str(question["business_id"])) if hasattr(provider, "flags") else []
            not_applicable = bool(bad) and all(b == "no_ledger" or b.startswith("invariants_error") for b in bad)
            if not_applicable:  # no views / check impossible: the router has nothing to say, the agent works as before
                decision = RouteDecision("llm", "shop_router_not_applicable: " + "; ".join(bad))
            elif bad:  # views exist but the data layer looks worse than any train shop: the whole shop abstains
                decision = RouteDecision("abstain", "shop_low_confidence: " + "; ".join(bad))
            else:
                spans = provider.spans(str(question["business_id"])) if hasattr(provider, "spans") else None
                decision = router.route(question, nq, conn, spans)
        except Exception as exc:  # never let the router break a question: fall back to the agent
            decision = RouteDecision("llm", f"router_error:{type(exc).__name__}")
    if decision.route in ("template", "unanswerable"):
        answer = decision.answer
        log = {"id": qid, "answer": answer, "elapsed_ms": int((time.monotonic() - began) * 1000),
               "thinking": None, "code": None, "output": None}
        if decision.route == "template":  # guideline §3.3: predefined code -> source file/function, inputs, output
            log["code"] = f"src/router/templates.py::run_template(intent={decision.intent!r})"
            log["inputs"] = decision.params
            log["output"] = (answer or {}).get("answer")
    elif decision.route == "abstain":
        answer = {"id": qid, "type": "abstain"}
        log = {"id": qid, "answer": answer, "elapsed_ms": int((time.monotonic() - began) * 1000),
               "thinking": None, "code": None, "output": None}
    else:
        key = G.gate_key(decision)
        if not G.llm_allowed(gate, key):
            answer = {"id": qid, "type": "abstain"}
            log = {"id": qid, "answer": answer, "elapsed_ms": 0, "thinking": None, "code": None, "output": None}
            decision = RouteDecision("abstain", f"llm_gate:{key}", decision.intent, params=decision.params)
        else:
            hints = None
            if nq is not None:
                try:
                    hints = build_hints(question, nq, decision, conn)
                except Exception:
                    hints = None
            answer, log = call_agent(agent, question, hints)
    log["router"] = decision.log()
    if provider is not None and hasattr(provider, "warnings"):
        try:
            w = provider.warnings(str(question.get("business_id", "")))
        except Exception:
            w = []
        if w:
            log["router"]["shop_warnings"] = w
    return answer, log
