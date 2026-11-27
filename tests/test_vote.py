"""Self-consistency vote and shop-wise submission: mock agent and mock model, no GPU, no data."""
from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from src.router import vote as V
from src.shard_writer import ShardedSubmission


def num(v, qid="q"):
    return {"id": qid, "type": "number", "answer": v}


ABSTAIN = {"id": "q", "type": "abstain"}


class FakeModel:
    """Like LocalVLLM: holds `params` (an object with temperature and seed) that the agent's calls read."""

    def __init__(self):
        self.params = SimpleNamespace(temperature=0.0, seed=None)


class ScriptedAgent:
    """Returns the scripted answers one by one and records the sampling settings seen at each call."""

    def __init__(self, answers, model=None, sleep=0.0):
        self.answers, self.model, self.sleep, self.calls, self.seen, self.hints_seen = list(answers), model, sleep, 0, [], []

    def solve(self, question, hints=None):
        self.hints_seen.append(hints)
        if self.model is not None:
            self.seen.append((self.model.params.temperature, self.model.params.seed))
        if self.sleep:
            time.sleep(self.sleep)
        a = self.answers[self.calls]
        self.calls += 1
        if isinstance(a, Exception):
            raise a
        return {**a, "id": question["id"]}, {"id": question["id"], "answer": a, "code": f"SELECT {self.calls}", "output": [[1]]}

    def close(self):
        pass


Q = {"id": "q1", "business_id": "s1", "question": "?"}


def vote(answers, k=5, threshold=0.6, **kw):
    agent = ScriptedAgent(answers, FakeModel(), **kw)
    return V.VoteAgent(agent, k, threshold), agent


def test_agreement_decides_and_stops_early():
    va, agent = vote([num(100), num(100), num(100), num(101), ABSTAIN])
    ans, log = va.solve(Q)
    assert ans == {"id": "q1", "type": "number", "answer": 100}
    assert agent.calls == 3                                   # 3 of 5 reach 0.6: the last two samples are not asked
    assert log["vote"]["decided"] and log["vote"]["agreement"] == 0.6 and log["code"] == "SELECT 1"


def test_disagreement_abstains_and_stops_when_the_threshold_cannot_be_reached():
    va, agent = vote([num(1), num(2), num(3), num(4), num(5)])
    ans, log = va.solve(Q)
    assert ans == {"id": "q1", "type": "abstain"} and not log["vote"]["decided"]
    assert agent.calls == 4                                   # after 4 samples the best group (1) + 1 left < 3 needed


def test_abstain_samples_count_against_agreement():
    va, _ = vote([num(7), ABSTAIN, num(7), ABSTAIN, ABSTAIN], threshold=0.6)
    ans, log = va.solve(Q)
    assert ans["type"] == "abstain" and log["vote"]["abstain_samples"] >= 2


def test_equal_answers_are_judged_by_the_pa_scorer():
    assert V.same_answer(num(100), num(100.0))
    assert not V.same_answer(num(100), num(101))
    assert not V.same_answer(num(100), {"type": "percent", "answer": 100})               # other type
    assert not V.same_answer({"type": "list", "answer": [1, 2]}, {"type": "list", "answer": [2, 1]})   # order matters
    assert V.same_answer({"type": "unanswerable", "reason": "a"}, {"type": "unanswerable", "reason": "b"})
    assert not V.same_answer(ABSTAIN, ABSTAIN)
    assert V.same_answer({"type": "string", "answer": "Cà phê sữa"}, {"type": "string", "answer": "Cà phê sữa "})      # spacing only
    assert not V.same_answer({"type": "string", "answer": "Cà phê sữa"}, {"type": "string", "answer": "ca phe sua"})  # accents count (section 9)


def test_a_failing_sample_is_an_abstain_vote_not_an_error():
    va, _ = vote([RuntimeError("boom"), num(5), num(5), num(5), num(5)], k=5, threshold=0.6)
    ans, log = va.solve(Q)
    assert ans["answer"] == 5 and log["vote"]["abstain_samples"] == 1


def test_sampling_is_set_for_each_call_and_restored():
    model = FakeModel()
    original = model.params
    agent = ScriptedAgent([num(1)] * 5, model)
    V.VoteAgent(agent, 5, 0.6, temperature=0.7, base_seed=100).solve(Q)
    assert [t for t, _ in agent.seen] == [0.7, 0.7, 0.7]       # decided after 3
    assert [s for _, s in agent.seen] == [100, 101, 102]       # a different seed per sample
    assert model.params is original and original.temperature == 0.0 and original.seed is None


def test_model_with_set_sampling_method():
    class M:
        state = (0.0, None)

        def set_sampling(self, temperature, seed):
            old, self.state = self.state, (temperature, seed)
            return old

        def restore_sampling(self, old):
            self.state = old
    m = M()
    seen = []

    class A:
        model = m

        def solve(self, q, hints=None):
            seen.append(m.state)
            return num(3, q["id"]), {"id": q["id"]}
    V.VoteAgent(A(), 3, 0.6, temperature=0.5, base_seed=7).solve(Q)
    assert seen[0] == (0.5, 7) and m.state == (0.0, None)


def test_k_1_is_a_plain_call_and_hints_are_passed_on():
    agent = ScriptedAgent([num(9)], FakeModel())
    ans, _ = V.VoteAgent(agent, 1).solve(Q, hints={"x": 1})
    assert ans["answer"] == 9 and agent.calls == 1 and agent.hints_seen == [{"x": 1}]
    assert agent.seen == [(0.0, None)]                          # no sampling at k = 1

    class OldAgent:          # solve without a hints parameter
        model = None

        def solve(self, q):
            return num(1, q["id"]), {}
    assert V.VoteAgent(OldAgent(), 1).solve(Q, hints={"a": 1})[0]["answer"] == 1


def test_time_budget_stops_sampling():
    agent = ScriptedAgent([num(1)] * 5, FakeModel(), sleep=0.03)
    ans, log = V.VoteAgent(agent, 5, 0.6, budget_s=0.01).solve(Q)
    assert agent.calls == 1 and ans["type"] == "abstain" and log["vote"]["asked"] == 1


@pytest.mark.parametrize("env,expect_vote", [
    ({}, False), ({"DATAMATE_LLM_VOTE_K": "1"}, False), ({"DATAMATE_LLM_VOTE_K": "3"}, True),
    ({"DATAMATE_LLM_VOTE_K": "abc"}, False), ({"DATAMATE_LLM_VOTE_K": "3", "DATAMATE_LLM_VOTE_THRESHOLD": "1.5"}, False),
    ({"DATAMATE_LLM_VOTE_K": "3", "DATAMATE_LLM_VOTE_THRESHOLD": "0.5", "DATAMATE_LLM_VOTE_TEMPERATURE": "0"}, False),
])
def test_maybe_vote_reads_the_flags(env, expect_vote):
    agent = ScriptedAgent([], FakeModel())
    out = V.maybe_vote(agent, env)
    assert isinstance(out, V.VoteAgent) == expect_vote
    if expect_vote:
        assert out.k == 3 and out.threshold == float(env.get("DATAMATE_LLM_VOTE_THRESHOLD", 0.6))


def test_maybe_vote_leaves_greedy_backends_and_router_only_alone():
    greedy = ScriptedAgent([], SimpleNamespace(generate=lambda s, u: ("", None)))   # HFTransformers-like: no params, no set_sampling
    assert V.maybe_vote(greedy, {"DATAMATE_LLM_VOTE_K": "3"}) is greedy
    from src.router.pipeline import AbstainAgent
    ab = AbstainAgent()
    assert V.maybe_vote(ab, {"DATAMATE_LLM_VOTE_K": "3"}) is ab


# ---- shop-wise submission ---------------------------------------------------------------------------------------
def _qs():
    return [("a1", "A"), ("b1", "B"), ("a2", "A"), ("b2", "B")]


def _read(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def test_submission_is_complete_from_the_start_and_after_every_shop(tmp_path):
    sub = ShardedSubmission(tmp_path, _qs(), checkpoint_every=100)
    assert [r["id"] for r in _read(tmp_path / "submission.jsonl")] == ["a1", "b1", "a2", "b2"]
    assert all(r["type"] == "abstain" for r in _read(tmp_path / "submission.jsonl"))
    sub.add({"id": "a1", "type": "string", "answer": "Cà phê sữa"})
    sub.add({"id": "a2", "type": "number", "answer": 5})
    sub.finish_shop("A")
    rows = _read(tmp_path / "submission.jsonl")
    assert [r["type"] for r in rows] == ["string", "abstain", "number", "abstain"]            # order of questions.jsonl
    assert [r["id"] for r in _read(tmp_path / "by_shop" / "A.jsonl")] == ["a1", "a2"]
    assert "Cà phê sữa" in (tmp_path / "submission.jsonl").read_text(encoding="utf-8")          # UTF-8, not escaped
    assert not list(tmp_path.glob("*.tmp")) and not list((tmp_path / "by_shop").glob("*.tmp"))
    sub.add({"id": "zzz", "type": "number", "answer": 1})                                       # unknown id: ignored
    sub.add({"id": "b1", "type": "number", "answer": 2})
    sub.add({"id": "b2", "type": "number", "answer": 3})
    sub.finish_shop("B")
    assert [r.get("answer") for r in _read(tmp_path / "submission.jsonl")] == ["Cà phê sữa", 2, 5, 3] and sub.done() == 4


def test_checkpoint_keeps_answers_without_waiting_for_the_shop_to_finish(tmp_path):
    sub = ShardedSubmission(tmp_path, _qs(), checkpoint_every=1)
    sub.add({"id": "b2", "type": "number", "answer": 9})                                        # the run could be killed here
    assert [r["type"] for r in _read(tmp_path / "submission.jsonl")] == ["abstain", "abstain", "abstain", "number"]


def test_predict_run_writes_shop_by_shop_when_asked(tmp_path, monkeypatch):
    from src import predict
    data, out = tmp_path / "data", tmp_path / "out"
    data.mkdir()
    qs = [{"id": f"q{i}", "business_id": "s1" if i % 2 else "s2", "question": "?", "as_of_date": "2026-01-01"} for i in range(4)]
    (data / "questions.jsonl").write_text("\n".join(json.dumps(q) for q in qs) + "\n", encoding="utf-8")
    monkeypatch.setenv("DATAMATE_ROUTER", "0")
    monkeypatch.setenv("DATAMATE_SHARDED_SUBMISSION", "1")
    assert predict.run(data, out, None) == 4
    rows = _read(out / "submission.jsonl")
    assert [r["id"] for r in rows] == ["q0", "q1", "q2", "q3"] and all(r["type"] == "abstain" for r in rows)
    assert sorted(p.name for p in (out / "by_shop").glob("*.jsonl")) == ["s1.jsonl", "s2.jsonl"]


def test_full_mode_asks_every_sample_and_logs_each_one():
    agent = ScriptedAgent([num(1), num(1), num(1), num(2), RuntimeError("boom")], FakeModel())
    ans, log = V.VoteAgent(agent, 5, 0.6, full=True).solve(Q)
    assert agent.calls == 5 and ans["answer"] == 1                     # decided after 3 but all 5 are asked
    samples = log["vote"]["samples"]
    assert [s["i"] for s in samples] == [0, 1, 2, 3, 4]
    assert samples[0]["code"] == "SELECT 1" and samples[0]["answer"]["answer"] == 1
    assert samples[3]["answer"]["answer"] == 2 and samples[4]["error"].startswith("RuntimeError") and samples[4]["answer"]["type"] == "abstain"
    json.dumps(log)                                                     # the log is plain JSON


def test_flag_full_is_read_from_the_environment():
    agent = ScriptedAgent([], FakeModel())
    assert V.maybe_vote(agent, {"DATAMATE_LLM_VOTE_K": "5", "DATAMATE_LLM_VOTE_FULL": "1"}).full is True
    assert V.maybe_vote(agent, {"DATAMATE_LLM_VOTE_K": "5"}).full is False


def test_tie_between_two_answers_is_an_abstain():
    va = V.VoteAgent(ScriptedAgent([num(1), num(2), num(1), num(2)], FakeModel()), 4, 0.5, full=True)
    ans, log = va.solve(Q)
    assert ans["type"] == "abstain" and log["vote"]["groups"] == [2, 2]


def test_offline_sweep_revotes_the_logged_samples():
    from eval.vote_sweep import revote, sweep
    samples = [{"i": i, "answer": a} for i, a in enumerate([num(1), num(1), num(2), {"type": "abstain"}, num(1)])]
    vote_log = {"k": 5, "samples": samples}
    assert revote(vote_log, "q1", 0.6)["answer"] == 1                                  # 3 of 5
    assert revote(vote_log, "q1", 0.8)["type"] == "abstain"                              # 3 < 4
    logs = [{"id": "q1", "answer": {"id": "q1", "type": "abstain"}, "router": {"route": "llm", "intent": "shift", "reason": "x"}, "vote": vote_log},
            {"id": "q2", "answer": num(5, "q2"), "router": {"route": "template", "intent": "revenue", "reason": "ok"}}]
    gold = {"q1": {"id": "q1", "type": "number", "answer": 1}, "q2": {"id": "q2", "type": "number", "answer": 5}}
    res = sweep(logs, gold, [0.6, 0.8])
    assert res["router_only_pa"] == 0.5 and res["rows"][0.6]["pa_total"] == 1.0 and res["rows"][0.8]["pa_total"] == 0.5
    assert res["rows"][0.6]["by_kind"]["shift"]["correct"] == 1
