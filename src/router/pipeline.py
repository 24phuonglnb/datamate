"""Pipeline glue: router first, LLM agent only for what the router does not answer. agent.py is not modified.

`provider` = ConnectionProvider (src/router/db.py): shop views via the ingestion layer, not via the agent."""
from __future__ import annotations

import time
from typing import Any, Callable

from .router import RouteDecision, Router


class AbstainAgent:
    """Stand-in for the LLM agent in router-only runs (no model, no GPU): every question the router leaves abstains."""

    def solve(self, question: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        qid = str(question.get("id", ""))
        answer = {"id": qid, "type": "abstain"}
        return answer, {"id": qid, "answer": answer, "elapsed_ms": 0, "thinking": None, "code": None, "output": None}

    def close(self) -> None:
        pass


def solve(question: dict[str, Any], agent: Any, router: Router | None, normalizer: Callable[..., Any] | None,
          provider: Any = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """-> (answer, log). log["router"] = {route, reason, intent, params} for every question."""
    qid = str(question.get("id", ""))
    began = time.monotonic()
    decision = RouteDecision("llm", "router_disabled")
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
    elif decision.route == "abstain":
        answer = {"id": qid, "type": "abstain"}
        log = {"id": qid, "answer": answer, "elapsed_ms": int((time.monotonic() - began) * 1000),
               "thinking": None, "code": None, "output": None}
    else:
        answer, log = agent.solve(question)
    log["router"] = decision.log()
    if provider is not None and hasattr(provider, "warnings"):
        try:
            w = provider.warnings(str(question.get("business_id", "")))
        except Exception:
            w = []
        if w:
            log["router"]["shop_warnings"] = w
    return answer, log
