"""Hints handed to the LLM agent for a question the router did not answer (see docs/ROUTER.md, "Interface for the agent").

All values are plain JSON-able data; nothing here needs a model.  Any failure while building a field only drops that field.
"""
from __future__ import annotations

from typing import Any

from . import intents as I


def _period_dict(p: Any) -> dict[str, Any]:
    return {"start": p.start.isoformat() if p.start else None, "end": p.end.isoformat(), "granularity": p.granularity,
            "source": p.source}


def build_hints(question: dict[str, Any], nq: Any, decision: Any, conn: Any = None) -> dict[str, Any]:
    res = nq.period
    pod = None
    if res.part_of_day:
        shifts = [k for k in ("sang", "chieu") if k in res.part_of_day]
        pod = res.part_of_day[shifts[0]] if len(shifts) == 1 else None  # both shifts: the agent filters each itself
    hints: dict[str, Any] = {
        "normalized_text": nq.text,
        "period": [_period_dict(p) for p in res.periods],
        "comparison_period": _period_dict(res.comparison) if res.comparison else None,
        "part_of_day": {k: v for k, v in res.part_of_day.items() if k in ("sang", "chieu", "baseline")} if res.part_of_day else None,
        "where_sql": [{"period": p.source, "sql": p.where_sql("order_date", "order_time", pod)} for p in res.periods],
        "ambiguous_period": [a.get("text") for a in res.ambiguous],
        "flags": list(nq.flags),
        "entities": {"numbers": nq.entities.get("numbers", []), "dates": nq.entities.get("dates", [])},
        "fallthrough_reason": decision.reason,
        "fallthrough_intent": decision.intent,
    }
    if res.comparison:
        hints["where_sql"].append({"period": "comparison", "sql": res.comparison.where_sql("order_date", "order_time", pod)})
    if conn is not None:
        try:
            s = I.prepare(nq.text)
            s_item = I.strip_dates(s)   # item_match_key glues a digit to the next word ("25/12/2025, xuc xich" -> "2025xuc xich")
            cat = conn.execute("SELECT item_code, item_name, name_aliases, base_unit FROM v_items").fetchall()
            m, _ = I.match_item(cat, s_item)
            if m:
                hints["entities"]["item"] = {"item_code": m[0], "item_name": m[1], "base_unit": m[2]}
            cats = [r[0] for r in conn.execute("SELECT DISTINCT category FROM v_items WHERE category IS NOT NULL")]
            c, _ = I.match_category(cats, s_item)
            if c:
                hints["entities"]["category"] = c
        except Exception:
            pass
        _add_order_filters(hints, I.prepare(nq.text), conn)
    return hints


def _q(v: str) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def _add_order_filters(hints: dict[str, Any], s: str, conn: Any) -> None:
    """Payment method, channel and customer group named in the question, matched with the v3 template matchers.

    Added twice: structured in `entities` (payment_method / channel / customer_group: [{"name", "values"}]) and as
    `where_sql` entries (`period` = "<kind> filter"), because agent.format_hints_for_prompt prints every where_sql entry
    but only the entities it knows (item, category).  Columns are those of v_valid_orders."""
    try:
        specs = [("payment_method", "payment_method", I._PAY, I._PAY_CUES), ("channel", "channel", I._CHAN, I._CHAN_CUES)]
        for key, col, table, cues in specs:
            raw = [r[0] for r in conn.execute(f"SELECT DISTINCT {col} FROM v_valid_orders WHERE {col} IS NOT NULL")]
            for label, vals in I.match_named_all(table, cues, raw, s):
                hints["entities"].setdefault(key, []).append({"name": label, "values": vals})
                hints["where_sql"].append({"period": f"{key} filter ({label})", "sql": f"{col} IN ({', '.join(_q(v) for v in vals)})"})
        groups = [r[0] for r in conn.execute("SELECT DISTINCT customer_group FROM v_valid_orders WHERE customer_group IS NOT NULL")]
        for g in I.match_group_all(groups, s):
            hints["entities"].setdefault("customer_group", []).append({"name": g, "values": [g]})
            hints["where_sql"].append({"period": f"customer_group filter ({g})", "sql": f"customer_group = {_q(g)}"})
    except Exception:
        pass
