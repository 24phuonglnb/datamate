"""Run the current baseline Agent on the fixed sample and score it with PA.

    python -m eval.run_baseline --model-path <dir or repo id> --model-name Qwen3-8B
    python -m eval.run_baseline ... --full            # all 3000 train questions

Outputs (eval/reports/):
    <date>_<model>[_<subset>].md / .json       aggregate report (committed)
    <date>_<model>[_<subset>].per_question.jsonl   raw per-question rows   (git-ignored)
    <date>_<model>[_<subset>]_errors.md        top error groups + examples (git-ignored)

Per-question rows are written as they finish, so a killed run resumes with --resume.
The baseline (src/) is NOT modified; this script only drives it.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

from eval import pa_score  # noqa: E402
from src.agent import Agent  # noqa: E402


# --------------------------------------------------------------------------
# intent (simple regex on accent-stripped lowercase text)
# --------------------------------------------------------------------------
def _fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


INTENT_RULES: list[tuple[str, str]] = [
    ("ton_kho", r"ton kho|con (may|bao nhieu)|het hang|con ton|trong kho"),
    ("cong_no", r"\bno\b|cong no|khach no|con no|mua chiu|thu hoi"),
    ("gia_tang_gia", r"tang gia|doi gia|len gia|\bgia ban\b|\bgia nhap\b"),
    ("nhap_hang", r"nhap hang|phieu nhap|nha cung cap|tien nhap"),
    ("huy_tra", r"\bhuy\b|tra hang"),
    ("loi_nhuan", r"\blai\b|loi nhuan|lai gop|lai rong"),
    ("so_sanh_ky", r"so voi|tang hay giam|thay doi|hon hay kem|tang lien tuc|cung ky"),
    ("xep_hang", r"nhieu nhat|cao nhat|chay nhat|lon nhat|\btop\b|liet ke|\b\d{1,2} (mat hang|khach|san pham)"),
    ("so_don", r"so don|bao nhieu don|\bbill\b|may don"),
    ("doanh_thu", r"doanh thu|dthu|ban duoc|ban ra|tien ban|tong"),
]
_INTENT_RE = [(n, re.compile(p)) for n, p in INTENT_RULES]


def intent_of(question: str) -> str:
    t = _fold(question)
    for name, rx in _INTENT_RE:
        if rx.search(t):
            return name
    return "khac"


# --------------------------------------------------------------------------
# error grouping
# --------------------------------------------------------------------------
def error_group(row: dict[str, Any]) -> str:
    gold_t, pred = row["gold_type"], row["answer"]
    pt = pred.get("type") if isinstance(pred, dict) else None
    st = row["status"]
    if st == "correct":
        return "correct"
    if st in ("abstain", "missing", "unreadable"):
        why = row.get("abstain_cause", "other")
        return f"abstain:{why} (gold={gold_t})"
    if gold_t == "unanswerable":
        return f"answered_but_gold_unanswerable (pred={pt})"
    if pt == "unanswerable":
        return f"false_unanswerable (gold={gold_t})"
    if pt != gold_t:
        return f"wrong_type: pred={pt} gold={gold_t}"
    return f"wrong_value: {gold_t}"


def abstain_cause(log: dict[str, Any]) -> str:
    if log.get("error"):
        return "agent_exception"
    out = log.get("output")
    if isinstance(out, list) and out and all(isinstance(o, str) for o in out):
        return "sql_error_all_attempts"
    if isinstance(out, str):
        return "sql_error"
    if log.get("code") is None:
        return "no_sql(parse/abstain)"
    return "other"


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def _read_jsonl(p: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _agg(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {"n": 0}
    tot = sum(r["score"] for r in rows)
    return {
        "n": n,
        "pa": round(tot / n, 4),
        "accuracy": round(sum(r["status"] == "correct" for r in rows) / n, 4),
        "abstain_rate": round(sum(r["status"] in ("abstain", "missing", "unreadable") for r in rows) / n, 4),
        "wrong_rate": round(sum(r["status"] == "wrong" for r in rows) / n, 4),
    }


def _by(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    g: dict[str, list] = collections.defaultdict(list)
    for r in rows:
        g[r[key]].append(r)
    return {k: _agg(v) for k, v in sorted(g.items())}


def build_model(path: str, backend: str, device: str | None, tp: int = 1):
    if backend == "mock":
        from src.llm import MockLLM
        return MockLLM()
    if backend == "vllm":
        from src.llm import get_model
        return get_model(path, "vllm", tensor_parallel_size=tp)
    from src.llm import HFTransformers
    kw = {}
    if device:
        kw["device_map"] = {"": device}
    return HFTransformers(path, **kw)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-path", required=True)
    ap.add_argument("--model-name", required=True)
    ap.add_argument("--backend", default="transformers", choices=["transformers", "vllm", "mock"])
    ap.add_argument("--tensor-parallel-size", type=int, default=1, help="vllm backend only")
    ap.add_argument("--train-dir", default=str(HERE.parent / "data" / "train" / "train"))
    ap.add_argument("--sample", default=str(HERE / "sample_ids.json"))
    ap.add_argument("--folds", default=str(HERE / "folds.json"))
    ap.add_argument("--out", default=str(HERE / "reports"))
    ap.add_argument("--subset", default="sample", choices=["sample", "holdout", "full"],
                    help="sample = fixed 600; holdout = every question of the 6 hold-out shops; full = all 3000")
    ap.add_argument("--full", action="store_true", help="alias of --subset full")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--router", action="store_true",
                    help="put the intent router in front of the agent (docs/ROUTER.md); report name gets a _router suffix")
    ap.add_argument("--device", default=None, help="e.g. cuda:0 (default: device_map auto)")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    a = ap.parse_args()

    train = Path(a.train_dir)
    questions = _read_jsonl(train / "questions.jsonl")
    gold = {g["id"]: g for g in _read_jsonl(train / "answers.jsonl")}
    folds = json.loads(Path(a.folds).read_text(encoding="utf-8"))
    hold = set(folds["holdout"])
    if a.full:
        a.subset = "full"
    if a.subset == "holdout":
        questions = [q for q in questions if q["business_id"] in hold]
    elif a.subset == "sample":
        keep = set(json.loads(Path(a.sample).read_text(encoding="utf-8"))["ids"])
        questions = [q for q in questions if q["id"] in keep]
    # Group by shop (stable) so the Agent's 2-entry DB cache is not thrashed by the
    # shuffled question file; each shop's workbook ingest costs ~15 s.
    questions = sorted(questions, key=lambda q: q["business_id"])
    if a.limit:
        questions = questions[: a.limit]

    tag = f"{a.date}_{a.model_name}" + ("" if a.subset == "sample" else f"_{a.subset}") + ("_router" if a.router else "") + ("_mock" if a.backend == "mock" else "")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    pq_path = out / f"{tag}.per_question.jsonl"

    done: dict[str, dict[str, Any]] = {}
    if a.resume and pq_path.is_file():
        for r in _read_jsonl(pq_path):
            done[r["id"]] = r
    elif pq_path.is_file():
        pq_path.unlink()

    t0 = time.monotonic()
    model = build_model(a.model_path, a.backend, a.device, a.tensor_parallel_size)
    load_s = time.monotonic() - t0
    print(f"model loaded in {load_s:.1f}s; {len(questions)} questions, {len(done)} already done", flush=True)

    agent = Agent(model, train)
    router = normalizer = provider = None
    if a.router:
        from src.nlu.normalize import RuleNormalizer
        from src.router import Router
        from src.router.db import ConnectionProvider
        from src.router.pipeline import solve as solve_routed
        router, normalizer, provider = Router(), RuleNormalizer(train / "calendar.csv"), ConnectionProvider(train)
    t_run = time.monotonic()
    try:
        with pq_path.open("a", encoding="utf-8", buffering=1) as f:
            for i, q in enumerate(questions, 1):
                if q["id"] in done:
                    continue
                if a.router:
                    answer, log = solve_routed(q, agent, router, normalizer, provider)
                else:
                    answer, log = agent.solve(q)
                g = gold[q["id"]]
                score, status = pa_score.score_one(answer, g)
                row = {
                    "id": q["id"], "business_id": q["business_id"], "question": q["question"],
                    "as_of_date": q.get("as_of_date"), "intent": intent_of(q["question"]),
                    "fold": "holdout" if q["business_id"] in hold else "dev",
                    "gold_type": g["type"], "gold": g["answer"], "answer": answer,
                    "score": score, "status": status,
                    "sql": log.get("code"), "output": log.get("output"),
                    "elapsed_s": round(log.get("elapsed_ms", 0) / 1000, 3), "error": log.get("error"),
                }
                if "router" in log:
                    from src.router.gate import gate_key
                    from types import SimpleNamespace
                    row["route"] = log["router"]["route"]
                    row["router_intent"] = log["router"].get("intent")
                    row["router_reason"] = log["router"].get("reason")
                    row["gate_key"] = gate_key(SimpleNamespace(reason=row["router_reason"], intent=row["router_intent"]))
                if status in ("abstain", "missing", "unreadable"):
                    row["abstain_cause"] = abstain_cause(log)
                row["group"] = error_group(row)
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                done[q["id"]] = row
                if i % 20 == 0:
                    pa_now = sum(r["score"] for r in done.values()) / len(done)
                    print(f"{i}/{len(questions)} PA so far {pa_now:.3f}", flush=True)
    finally:
        agent.close()
        if provider is not None:
            provider.close()
    run_s = time.monotonic() - t_run

    rows = [done[q["id"]] for q in questions if q["id"] in done]
    elapsed = [r["elapsed_s"] for r in rows]
    # rows resumed from an earlier process keep their own timings; wall time covers this process only
    report = {
        "date": a.date, "model": a.model_name, "model_path": a.model_path, "backend": a.backend,
        "set": {"full": "full_3000", "sample": "sample_600", "holdout": "holdout_all"}[a.subset],
        "percent_mode": pa_score.PERCENT_MODE,
        "overall": _agg(rows),
        "by_fold": _by(rows, "fold"),
        "by_type": _by(rows, "gold_type"),
        "by_intent": _by(rows, "intent"),
        "by_shop": _by(rows, "business_id"),
        "timing": {
            "model_load_s": round(load_s, 1),
            "sec_per_question_mean": round(sum(elapsed) / max(1, len(elapsed)), 2),
            "sec_per_question_median": round(sorted(elapsed)[len(elapsed) // 2], 2) if elapsed else None,
            "sec_per_question_p95": round(sorted(elapsed)[int(0.95 * (len(elapsed) - 1))], 2) if elapsed else None,
            "wall_s_this_process": round(run_s, 1),
        },
        "answered_rate": round(sum(r["status"] in ("correct", "wrong") for r in rows) / max(1, len(rows)), 4),
        "answered_precision": round(
            sum(r["status"] == "correct" for r in rows) / max(1, sum(r["status"] in ("correct", "wrong") for r in rows)), 4),
    }
    (out / f"{tag}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- markdown (aggregates only; no question text) ----
    def table(d: dict[str, Any], title: str) -> list[str]:
        L = [f"### {title}", "", "| key | n | PA | acc | abstain | wrong |", "|---|---|---|---|---|---|"]
        for k, v in d.items():
            L.append(f"| {k} | {v['n']} | {v['pa']:.3f} | {v['accuracy']:.3f} | {v['abstain_rate']:.3f} | {v['wrong_rate']:.3f} |")
        return L + [""]

    o = report["overall"]
    md = [f"# Baseline report — {a.model_name} — {report['set']} — {a.date}", "",
          f"- PA: **{o['pa']:.4f}**, accuracy {o['accuracy']:.4f}, abstain {o['abstain_rate']:.4f}, wrong {o['wrong_rate']:.4f} (n={o['n']})",
          f"- Answered precision (correct / answered): {report['answered_precision']:.4f}; answered rate {report['answered_rate']:.4f}",
          f"- Timing: load {report['timing']['model_load_s']} s, {report['timing']['sec_per_question_mean']} s/question mean (includes ~15 s workbook ingest on the first question of each shop), median {report['timing']['sec_per_question_median']} s, p95 {report['timing']['sec_per_question_p95']} s",
          f"- Percent comparison mode in pa_score: `{pa_score.PERCENT_MODE}`", ""]
    md += table(report["by_fold"], "By fold") + table(report["by_type"], "By gold type")
    md += table(report["by_intent"], "By intent (regex)") + table(report["by_shop"], "By shop")
    (out / f"{tag}.md").write_text("\n".join(md), encoding="utf-8")

    # ---- error groups with examples (private text; git-ignored) ----
    lost: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for r in rows:
        if r["score"] < 1:
            lost[r["group"]].append(r)
    ranked = sorted(lost.items(), key=lambda kv: -sum(1 - x["score"] for x in kv[1]))[:10]
    E = [f"# Top error groups — {tag}", "", "Ranked by points lost (1 per abstain, 2 per wrong).", ""]
    for gname, items in ranked:
        pts = sum(1 - x["score"] for x in items)
        E += [f"## {gname} — {len(items)} questions, {pts} points lost", ""]
        for x in items[:2]:
            E += [f"- shop {x['business_id']} | intent {x['intent']} | as_of {x['as_of_date']}",
                  f"  - Q: {x['question']}",
                  f"  - SQL: `{json.dumps(x['sql'], ensure_ascii=False)[:500]}`",
                  f"  - output: `{json.dumps(x['output'], ensure_ascii=False, default=str)[:300]}`",
                  f"  - pred: `{json.dumps(x['answer'], ensure_ascii=False, default=str)[:300]}`",
                  f"  - gold: `{json.dumps(x['gold'], ensure_ascii=False, default=str)[:300]}`"]
        E.append("")
    (out / f"{tag}_errors.md").write_text("\n".join(E), encoding="utf-8")
    print(json.dumps(report["overall"]), json.dumps(report["timing"]), flush=True)


if __name__ == "__main__":
    main()
