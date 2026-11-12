"""Pipeline glue: router first, LLM agent only for what the router does not answer. agent.py is not modified.

`provider` = ConnectionProvider (src/router/db.py): shop views via the ingestion layer, not via the agent."""
from __future__ import annotations

import time
from typing import Any, Callable

from .router import RouteDecision, Router


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
            if bad:  # shop-level data check failed: the whole shop abstains, reason logged
                decision = RouteDecision("abstain", "shop_low_confidence: " + "; ".join(bad))
            else:
                decision = router.route(question, nq, conn)
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
    return answer, log
