"""Intent router: answers the deterministic question families from the rulebook views, everything else goes to the LLM agent.

    from src.router import Router
    decision = Router().route(question_dict, normalized_question, connection)
    decision.route in ("template", "llm", "abstain"); decision.reason explains it.
"""
from .router import RouteDecision, Router

__all__ = ["Router", "RouteDecision"]
