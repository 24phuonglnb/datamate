"""Router tests: synthetic sentences (no competition text) + end-to-end on two dev shops (skipped without data)."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from src.nlu.normalize import normalize
from src.router import Router
from src.router import intents as I

ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-09-07"


def intent(text):
    return I.recognise(I.prepare(text))


@pytest.mark.parametrize("text,expected", [
    ("Doanh thu tháng 3/2026 là bao nhiêu?", "revenue"),
    ("tháng 3/2026 cửa hàng có bao nhiêu đơn", "order_count"),
    ("Có bao nhiêu đơn bị hủy trong tháng 5/2026", "cancel_count"),
    ("tỉ lệ hủy đơn tháng 5/2026 là mấy %", "cancel_rate"),
    ("giá trị trung bình mỗi đơn tháng 2/2026", "aov"),
    ("tháng 4/2026 ngày nào bán được nhiều tiền nhất", "best_day"),
    ("top 5 mặt hàng bán chạy tháng 4/2026", "topk_items"),
    ("tháng 4/2026 mặt hàng nào bán chạy nhất", "best_item"),
    ("tháng 4/2026 bán được bao nhiêu chai Nước suối A", "item_qty"),
])
def test_recognise_target_intents(text, expected):
    assert intent(text) == (expected, "ok")


@pytest.mark.parametrize("text", [
    "Tháng 3/2026 tổng công nợ của khách là bao nhiêu",          # debt: not a target family
    "tháng 3/2026 tồn kho còn bao nhiêu",                         # stock
    "tháng 3/2026 nhân viên nào bán nhiều nhất",                  # staff
])
def test_non_target_goes_to_llm(text):
    assert intent(text)[0] is None


@pytest.mark.parametrize("text", [
    "doanh thu tháng 3/2026 của nhóm khách thân thiết",
    "doanh thu ca sáng tháng 3/2026",
    "doanh thu tháng 3/2026 so với tháng 2/2026",
])
def test_extra_filters_rejected(text):
    s = I.prepare(text)
    first, _ = I.recognise(s)
    assert first is None or I.extra_filter(first, s) is not None


def test_topk_k_extraction():
    assert I.topk_k(I.prepare("top 7 mặt hàng bán chạy tháng 3/2026")) == 7
    assert I.topk_k(I.prepare("liệt kê 4 sản phẩm bán chạy nhất tháng 12/2025")) == 4
    assert I.topk_k(I.prepare("mặt hàng bán chạy nhất tháng 3/2026")) is None  # the month is not k


CAT = [("A1", "Nước suối Aqua 500ml", "Nước suối Aqua 500ml | nuoc suoi aqua", "chai"),
       ("A2", "Nước suối Aqua 1.5L", "Nước suối Aqua 1.5L", "chai"),
       ("B1", "Mì Hảo Hảo", "Mì Hảo Hảo | mi hao hao | hh", "gói")]


def test_item_match_and_ambiguity():
    m, why = I.match_item(CAT, I.prepare("tháng 3/2026 bán bao nhiêu gói mì hảo hảo"))
    assert why == "ok" and m[1] == "Mì Hảo Hảo" and m[2] == "gói"
    assert I.match_item(CAT, I.prepare("tháng 3/2026 bán bao nhiêu chai bia"))[1] == "item_not_found"
    assert I.match_item(CAT, I.prepare("bao nhiêu chai nước suối aqua 500ml và nước suối aqua 1.5l"))[1] in ("ok", "item_ambiguous")
    assert I.asked_unit(I.prepare("bán bao nhiêu gói mì hảo hảo")) == "goi"


_OPEN: list = []


@pytest.fixture(autouse=True)
def _close_test_connections():
    yield
    while _OPEN:  # no leaked sqlite connections (test_smoke checks ResourceWarning process-wide)
        _OPEN.pop().close()


def _db():
    c = sqlite3.connect(":memory:")
    _OPEN.append(c)
    c.executescript("""
    CREATE TABLE v_orders(order_id, order_date, order_time, status, revenue);
    CREATE VIEW v_valid_orders AS SELECT * FROM v_orders WHERE status NOT IN ('huy','tra_hang');
    CREATE TABLE v_valid_lines(order_date, item_code, item_name, qty_base, is_service_fee);
    CREATE TABLE v_items(item_code, item_name, name_aliases, base_unit);
    """)
    c.executemany("INSERT INTO v_orders VALUES(?,?,?,?,?)", [
        (1, "2026-03-02", "09:00", "hoan_thanh", 100000), (2, "2026-03-02", "10:00", "hoan_thanh", 50000),
        (3, "2026-03-05", "11:00", "huy", 70000), (4, "2026-03-09", "12:00", "hoan_thanh", 200000),
        (5, "2026-02-10", "12:00", "hoan_thanh", 100000)])
    c.executemany("INSERT INTO v_valid_lines VALUES(?,?,?,?,?)", [
        ("2026-03-02", "B1", "Mì Hảo Hảo", 10, 0), ("2026-03-09", "A1", "Nước suối Aqua 500ml", 3, 0),
        ("2026-03-09", "B1", "Mì Hảo Hảo", 4, 0)])
    c.executemany("INSERT INTO v_items VALUES(?,?,?,?)", CAT)
    return c


def route(text, conn=None):
    nq = normalize(text, AS_OF)
    return Router().route({"id": "t1", "as_of_date": AS_OF}, nq, conn or _db())


def test_template_answers_and_formats():
    d = route("doanh thu tháng 3/2026 là bao nhiêu")
    assert (d.route, d.answer["type"], d.answer["answer"]) == ("template", "number", 350000)
    d = route("tháng 3/2026 có bao nhiêu đơn bị hủy")
    assert d.answer["answer"] == 1 and d.answer["type"] == "number"
    d = route("tỉ lệ hủy đơn tháng 3/2026 là bao nhiêu %")
    assert d.answer == {"id": "t1", "type": "percent", "answer": 25.0}
    d = route("tháng 3/2026 ngày nào bán được nhiều tiền nhất")
    assert d.answer["type"] == "date" and d.answer["answer"] == "2026-03-09"
    d = route("top 2 mặt hàng bán chạy tháng 3/2026")
    assert d.answer["answer"] == ["Mì Hảo Hảo", "Nước suối Aqua 500ml"]
    d = route("tháng 3/2026 bán được bao nhiêu gói mì hảo hảo")
    assert d.answer["answer"] == 14
    d = route("doanh thu tháng 3/2026 tăng hay giảm bao nhiêu % so với tháng 2/2026")
    assert d.route == "template" and d.answer["type"] == "percent" and d.answer["answer"] == 250.0


@pytest.mark.parametrize("text,reason", [
    ("doanh thu là bao nhiêu", "period_missing"),                      # no period
    ("doanh thu tháng 3/2026 và tháng 2/2026 là bao nhiêu", "period_count"),  # two periods, no comparison cue
    ("tháng 3/2026 bán được bao nhiêu chai bia hơi", "item_not_found"),
    ("tháng 3/2026 bán được bao nhiêu chai mì hảo hảo", "unit_mismatch"),
    ("tháng 3/2026 tồn kho còn bao nhiêu", "not_target"),
])
def test_unsafe_goes_to_llm(text, reason):
    d = route(text)
    assert d.route == "llm" and d.reason.split(":")[0] == reason


def test_period_before_data_is_unanswerable():
    d = route("doanh thu tháng 1/2020 là bao nhiêu")
    assert d.route == "unanswerable" and d.reason == "before_data_start"
    assert d.answer["type"] == "unanswerable" and isinstance(d.answer["reason"], str) and d.answer["id"] == "t1"
    d = route("doanh thu tháng 2/2026 là bao nhiêu")           # data starts 2026-02-10: partly covered -> answered
    assert d.route == "template" and d.answer["answer"] == 100000
    d = route("doanh thu tháng 1/2026 là bao nhiêu")           # ends before the first data day (2026-02-10)
    assert d.route == "unanswerable"


def test_order_threshold():
    d = route("tháng 3/2026 có bao nhiêu đơn có tiền hàng đạt 100.000 đồng trở lên")
    assert d.route == "template" and d.answer["answer"] == 2 and d.params["threshold"] == 100000
    d = route("tháng 3/2026 số đơn có doanh thu ≥ 150.000 đồng là bao nhiêu")
    assert d.answer["answer"] == 1
    d = route("tháng 3/2026 có bao nhiêu đơn có doanh thu trên 100.000 đồng")  # strict comparison: not the template
    assert d.route == "llm" and d.reason in ("threshold_strict_or_other", "not_target:orders_threshold")


def test_log_has_route_and_reason():
    d = route("doanh thu tháng 3/2026")
    assert set(d.log()) == {"route", "reason", "intent", "params"}


def test_no_business_or_question_id_logic():
    src = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src" / "router").glob("*.py") if p.name != "pipeline.py")  # pipeline.py only picks the shop DB
    assert "business_id" not in src and "biz_" not in src
    assert "question_id" not in src


DATA = Path(os.environ.get("ZAIC_TRAIN", ROOT / "data" / "train" / "train"))


@pytest.mark.skipif(not (DATA / "questions.jsonl").is_file(), reason="train data not available")
def test_end_to_end_two_dev_shops(tmp_path):
    from eval import pa_score
    from src.ingestion import BusinessDB
    qs = [json.loads(l) for l in open(DATA / "questions.jsonl", encoding="utf-8")]
    gold = {json.loads(l)["id"]: json.loads(l) for l in open(DATA / "answers.jsonl", encoding="utf-8")}
    routed = ok = 0
    for biz in ("biz_101", "biz_105"):
        db = BusinessDB(DATA / "data" / biz, DATA / "calendar.csv",
                        cache_dir=os.environ.get("DATAMATE_CACHE_DIR") or tmp_path)
        for q in (x for x in qs if x["business_id"] == biz):
            d = Router().route(q, normalize(q["question"], q["as_of_date"]), db.connection)
            assert d.route in ("template", "llm", "abstain") and d.reason
            if d.route == "template":
                routed += 1
                ok += pa_score.score_one(d.answer, gold[q["id"]])[0] == 1
        db.close()
    assert routed >= 20
    assert ok / routed >= 0.95


def test_pipeline_routes_template_and_falls_back(monkeypatch):
    from src.nlu.normalize import RuleNormalizer
    from src.router.pipeline import solve

    class FakeProvider:
        def connection(self, biz):
            return _db()

    class FakeAgent:
        def __init__(self):
            self.calls = 0

        def solve(self, q):
            self.calls += 1
            return {"id": q["id"], "type": "abstain"}, {"id": q["id"], "answer": None}

    agent, norm = FakeAgent(), RuleNormalizer(None)
    q = {"id": "t1", "business_id": "x", "as_of_date": AS_OF, "question": "doanh thu tháng 3/2026 là bao nhiêu"}
    ans, log = solve(q, agent, Router(), norm, FakeProvider())
    assert ans["answer"] == 350000 and agent.calls == 0 and log["router"]["route"] == "template"
    q2 = dict(q, id="t2", question="tháng 3/2026 tồn kho còn bao nhiêu")
    ans, log = solve(q2, agent, Router(), norm, FakeProvider())
    assert agent.calls == 1 and log["router"]["route"] == "llm"
    ans, log = solve(q, agent, None, None)  # disabled -> straight to the agent
    assert agent.calls == 2 and log["router"]["reason"] == "router_disabled"
    q3 = dict(q, id="t3", question="doanh thu tháng 1/2020 là bao nhiêu")
    ans, log = solve(q3, agent, Router(), norm, FakeProvider())
    assert ans["type"] == "unanswerable" and agent.calls == 2 and log["router"]["route"] == "unanswerable"


def test_invariant_flags_use_train_worst_values():
    from src.router import invariants as inv
    thr = {"unparsed_dates_pct": {"worst": 0.0}, "dup_pct": {"worst": 2.9}, "nonpositive_months": {"worst": 0},
           "status_unknown_pct": {"worst": 0.0}, "unit_unconverted_pct": {"worst": 0.0},
           "amount_ratio": {"min": 0.33, "max": 1.0}}
    ok = {"amount_ratio": 0.5, "unparsed_dates_pct": 0.0, "dup_pct": 2.9, "nonpositive_months": 0, "no_ledger": 0}
    assert inv.flags(ok, thr) == []
    assert inv.flags(dict(ok, unparsed_dates_pct=3.0), thr)[0].startswith("unparsed_dates_pct")
    assert inv.flags(dict(ok, amount_ratio=0.2), thr) and inv.flags(dict(ok, amount_ratio=1.2), thr)
    assert inv.flags({"no_ledger": 1}, thr) == ["no_ledger"]
    assert inv.flags(dict(ok, amount_ratio=None), thr) == []  # not computable is not a reason by itself


def test_flagged_shop_abstains_in_pipeline():
    from src.nlu.normalize import RuleNormalizer
    from src.router.pipeline import solve

    class P:
        def connection(self, shop):
            return _db()

        def flags(self, shop):
            return ["unparsed_dates_pct=54>train_worst=0"]

    class A:
        calls = 0

        def solve(self, q):
            A.calls += 1
            return {"id": q["id"], "type": "abstain"}, {}

    q = {"id": "t1", "business_id": "x", "as_of_date": AS_OF, "question": "doanh thu tháng 3/2026 là bao nhiêu"}
    ans, log = solve(q, A(), Router(), RuleNormalizer(None), P())
    assert ans == {"id": "t1", "type": "abstain"} and A.calls == 0
    assert log["router"]["route"] == "abstain" and "shop_low_confidence" in log["router"]["reason"]


def test_shop_without_views_still_goes_to_the_agent():
    from src.nlu.normalize import RuleNormalizer
    from src.router.pipeline import solve

    class P:
        def connection(self, shop):
            return _db()

        def flags(self, shop):
            return ["no_ledger"]

    class A:
        calls = 0

        def solve(self, q):
            A.calls += 1
            return {"id": q["id"], "type": "abstain"}, {}

    q = {"id": "t1", "business_id": "x", "as_of_date": AS_OF, "question": "doanh thu tháng 3/2026 là bao nhiêu"}
    _, log = solve(q, A(), Router(), RuleNormalizer(None), P())
    assert A.calls == 1 and log["router"]["route"] == "llm" and "not_applicable" in log["router"]["reason"]


def test_thresholds_file_has_train_values():
    from src.router import invariants as inv
    thr = inv.load_thresholds()
    assert thr["amount_ratio"]["n"] == 30 and "worst" in thr["dup_pct"]
