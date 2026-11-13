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
            assert d.route in ("template", "unanswerable", "llm", "abstain") and d.reason
            if d.route in ("template", "unanswerable"):
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
    assert inv.flags(dict(ok, unparsed_dates_pct=3.0), thr) == []  # per-question spans, not a shop flag
    # amount_ratio is a warning only: never a low_confidence reason
    assert inv.flags(dict(ok, amount_ratio=0.2), thr) == [] and inv.flags(dict(ok, amount_ratio=1.2), thr) == []
    assert inv.warnings(dict(ok, amount_ratio=0.2), thr) and inv.warnings(ok, thr) == []
    assert inv.flags(dict(ok, nonpositive_months=1), thr)[0].startswith("nonpositive_months")
    assert inv.flags(dict(ok, status_unknown_pct=0.5), thr)[0].startswith("status_unknown_pct")
    assert inv.flags(dict(ok, unit_unconverted_pct=0.1), thr)[0].startswith("unit_unconverted_pct")
    assert inv.flags(dict(ok, dup_pct=3.5), thr)[0].startswith("dup_pct")
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


def test_unparsed_spans_from_sheet_year_and_cell_month():
    import pandas as pd
    from src.router import invariants as inv
    # "3/6" parses with the sheet year (rulebook section 8), so it is NOT unparsed; only the unreadable cells are
    df = pd.DataFrame({"d": ["3/6", "5/6", "2025-07-01", None, "x?", "45/13", "7-7-7-7"],
                       "__year": [2025, 2025, 2025, 2025, 2026, 2026, 2025], "__month": [6, 6, 7, 7, 3, 11, 8]})
    sp = inv.unparsed_spans(df, "d", ("2025-01-01", "2026-12-31"))
    assert inv.blocked_by_spans(sp, "2026-03-01", "2026-03-31")            # "x?" in the sheet of March 2026
    assert inv.blocked_by_spans(sp, "2026-11-05", "2026-11-05")            # "45/13": sheet month November 2026
    assert inv.blocked_by_spans(sp, "2025-08-10", "2025-08-10")            # "7-7-7-7": sheet month August 2025
    assert inv.blocked_by_spans(sp, "2025-06-10", "2025-06-12") is None    # "3/6" parsed with the sheet year
    assert inv.blocked_by_spans(sp, "2025-07-01", "2025-07-31") is None


def test_unparsed_spans_without_year_use_data_range():
    import pandas as pd
    from src.router import invariants as inv
    df = pd.DataFrame({"d": ["??"]})
    assert inv.unparsed_spans(df, "d", ("2025-01-01", "2025-12-31")) == [["2025-01-01", "2025-12-31"]]
    assert inv.unparsed_spans(df, "d", None) == []


def test_period_meeting_unparsed_dates_abstains_others_answer():
    d = Router().route({"id": "t1", "as_of_date": AS_OF}, normalize("doanh thu tháng 3/2026 là bao nhiêu", AS_OF),
                       _db(), [["2026-03-10", "2026-03-20"]])
    assert d.route == "abstain" and d.reason.startswith("period_overlaps_unparsed_dates")
    d = Router().route({"id": "t1", "as_of_date": AS_OF}, normalize("doanh thu tháng 2/2026 là bao nhiêu", AS_OF),
                       _db(), [["2026-03-10", "2026-03-20"]])
    assert d.route == "template"
    # comparison window counts too
    d = Router().route({"id": "t1", "as_of_date": AS_OF},
                       normalize("doanh thu tháng 3/2026 tăng hay giảm bao nhiêu % so với tháng 2/2026", AS_OF),
                       _db(), [["2026-02-01", "2026-02-05"]])
    assert d.route == "abstain"


def test_pipeline_passes_spans_from_provider():
    from src.nlu.normalize import RuleNormalizer
    from src.router.pipeline import solve

    class P:
        def connection(self, shop):
            return _db()

        def flags(self, shop):
            return []

        def spans(self, shop):
            return [["2026-03-01", "2026-03-31"]]

    class A:
        calls = 0

        def solve(self, q):
            A.calls += 1
            return {"id": q["id"], "type": "abstain"}, {}

    q = {"id": "t1", "business_id": "x", "as_of_date": AS_OF, "question": "doanh thu tháng 3/2026 là bao nhiêu"}
    ans, log = solve(q, A(), Router(), RuleNormalizer(None), P())
    assert ans["type"] == "abstain" and A.calls == 0 and "period_overlaps_unparsed_dates" in log["router"]["reason"]


RB = """# Rulebook
## 1. Đơn hàng và doanh thu
| Luật | Mặc định |
|---|---|
| Đơn tính vào doanh thu | đơn không huỷ và không trả hàng |
| Đơn thuộc kỳ nào | theo **ngày đặt** |
| Số đơn | chỉ tính đơn không huỷ, không trả |
## 3. Xếp hạng
| Luật | Mặc định |
|---|---|
| Mặt hàng | món, hàng |
"""


def _guard(running, reviewed=None):
    from src.router import rule_guard as rg
    return rg.RuleGuard(rg.build_reference(RB), running, reviewed)


def test_rule_guard_identical_rulebook_disables_nothing():
    g = _guard(RB)
    assert g.changed == g.removed == g.new == [] and g.disabled == {}


def test_rule_guard_changed_row_disables_dependent_intents_only():
    g = _guard(RB.replace("theo **ngày đặt**", "theo **ngày giao**"))
    assert g.changed == ["1|don thuoc ky nao"]
    assert "revenue" in g.disabled and "order_count" in g.disabled
    r = Router(g).route({"id": "t1", "as_of_date": AS_OF}, normalize("doanh thu tháng 3/2026", AS_OF), _db())
    assert r.route == "llm" and r.reason.startswith("rulebook_changed:revenue")
    g2 = _guard(RB.replace("theo **ngày đặt**", "theo **ngày giao**"), reviewed={"1|don thuoc ky nao"})
    assert g2.disabled == {}  # a human marked the change as compatible


def test_rule_guard_new_row_cue_sends_matching_question_to_llm():
    new = RB + "## 3b. x\n" + "| Ngày đắt khách nhất | ngày có nhiều đơn nhất |\n"
    new = RB.replace("## 3. Xếp hạng", "## 3. Xếp hạng\n| Ngày đắt khách nhất | ngày có nhiều đơn nhất |")
    g = _guard(new)
    assert g.new == ["3|ngay dat khach nhat"] and g.disabled == {}
    d = Router(g).route({"id": "t1", "as_of_date": AS_OF}, normalize("tháng 3/2026 ngày nào đắt khách nhất", AS_OF), _db())
    assert d.route == "llm" and d.reason.startswith("new_rule_cue")
    d = Router(g).route({"id": "t1", "as_of_date": AS_OF}, normalize("tháng 3/2026 ngày nào bán được nhiều tiền nhất", AS_OF), _db())
    assert d.route == "template"


def test_rule_guard_removed_row():
    g = _guard(RB.replace("| Số đơn | chỉ tính đơn không huỷ, không trả |\n", ""))
    assert g.removed == ["1|so don"] and "order_count" in g.disabled and "revenue" not in g.disabled


def test_rule_guard_reference_matches_row_count():
    import json
    from src.router import rule_guard as rg
    assert len(json.loads(rg.REFERENCE_PATH.read_text(encoding="utf-8"))["rows"]) == 70


def test_sanity_checks_pass_for_plausible_answers_and_catch_implausible_ones():
    from src.router import sanity
    c = _db()
    s, e = "2026-03-01", "2026-03-31"
    assert sanity.check("revenue", 350000, c, s, e) is None
    assert sanity.check("revenue", -1, c, s, e) == "number_not_finite_nonnegative"
    assert sanity.check("cancel_rate", 25.0, c, s, e) is None and sanity.check("cancel_rate", 120.0, c, s, e)
    assert sanity.check("cancel_count", 1, c, s, e) is None and sanity.check("cancel_count", 9, c, s, e)
    assert sanity.check("rev_change_pct", -100, c, s, e) is None
    assert sanity.check("rev_change_pct", -150, c, s, e) and sanity.check("rev_change_pct", 5000, c, s, e)
    assert sanity.check("aov", 116667, c, s, e) is None            # orders 100000, 50000, 200000
    assert sanity.check("aov", 300000, c, s, e) == "aov_outside_order_range"
    assert sanity.check("aov", 10, c, s, e) == "aov_outside_order_range"
    assert sanity.check("best_day", "2026-03-09", c, s, e) is None
    assert sanity.check("best_day", "2026-04-01", c, s, e) == "date_outside_period"
    assert sanity.check("best_day", "09/03/2026", c, s, e) == "date_format"
    assert sanity.check("topk_items", ["Mì Hảo Hảo"], c, s, e) is None
    assert sanity.check("best_item", "Hàng lạ", c, s, e) == "item_name_not_in_catalog"


def test_router_abstains_on_implausible_template_answer(monkeypatch):
    from src.router import router as R
    monkeypatch.setattr(R, "run_template", lambda *a, **k: 250000000)   # not an order value -> aov outside range
    d = route("giá trị trung bình mỗi đơn tháng 3/2026")
    assert d.route == "abstain" and d.reason == "sanity:aov_outside_order_range"


def test_extended_intents_item_revenue_category_price_and_subjective():
    c = _db()
    c.executescript("""
    CREATE TABLE v_lines(order_date, item_code, item_name, unit_price_base, status);
    INSERT INTO v_lines VALUES('2026-03-09','A1','Nước suối Aqua 500ml',5000,'hoan_thanh'),
                              ('2026-03-09','A1','Nước suối Aqua 500ml',5000,'huy');
    """)
    c.execute("ALTER TABLE v_valid_lines ADD COLUMN line_amount")
    c.execute("ALTER TABLE v_valid_lines ADD COLUMN category")
    c.execute("UPDATE v_valid_lines SET line_amount = qty_base * 1000, category = 'Mì gói' WHERE item_code = 'B1'")
    c.execute("UPDATE v_valid_lines SET line_amount = 15000, category = 'Nước' WHERE item_code = 'A1'")
    c.execute("ALTER TABLE v_items ADD COLUMN category")
    c.execute("UPDATE v_items SET category = 'Nước' WHERE item_code IN ('A1', 'A2')")
    c.execute("UPDATE v_items SET category = 'Mì gói' WHERE item_code = 'B1'")
    d = route("doanh thu của mì hảo hảo tháng 3/2026 là bao nhiêu", c)
    assert d.route == "template" and d.intent == "item_revenue" and d.answer["answer"] == 14000
    d = route("tháng 3/2026 nhóm nước bán được bao nhiêu tiền", c)
    assert d.intent == "category_rev" and d.answer["answer"] == 15000
    d = route("giá bán một chai nước suối aqua 500ml vào ngày 09/03/2026 là bao nhiêu", c)
    assert d.intent == "sell_price_on_day" and d.answer["answer"] == 5000
    d = route("giá bán một gói mì hảo hảo vào ngày 09/03/2026 là bao nhiêu", c)  # no line that day -> not answered
    assert d.route == "llm"
    d = route("ai là nhân viên lành nghề nhất")
    assert d.route == "unanswerable" and d.answer["type"] == "unanswerable" and isinstance(d.answer["reason"], str)


def test_orders_threshold_phrase_goes_to_order_count():
    d = route("tháng 3/2026 có mấy đơn có doanh thu từ 100.000 đồng trở lên")
    assert d.route == "template" and d.intent == "order_count" and d.params["threshold"] == 100000 and d.answer["answer"] == 2
    d = route("tháng 3/2026 có mấy đơn có doanh thu trên 100.000 đồng")
    assert d.route == "llm"


def test_short_slash_year_is_resolved_by_the_router_path():
    d = route("doanh thu tháng 3/26 là bao nhiêu")
    assert d.route == "template" and d.params["start"] == "2026-03-01"


def test_new_row_cue_needs_the_words_close_and_in_order():
    from src.router import rule_guard as rg
    assert rg._in_order_close(["ngay", "dat", "khach"], "thang 3 ngay nao dat khach nhat".split())
    assert not rg._in_order_close(["dong", "may", "hang"], "tong tien bao nhieu dong thang 3 co may ngay ban tren 3 hang".split())
    assert not rg._in_order_close(["bao", "hanh"], "bao nhieu don co hanh khach".split())


PUBLIC = Path(os.environ.get("ZAIC_PUBLIC", ROOT / "data" / "public_test" / "public_test"))


@pytest.mark.skipif(not (PUBLIC / "data" / "dev_014").is_dir(), reason="public data not available")
def test_summary_rows_are_not_counted_as_unparsed_dates(tmp_path):
    """dev_014 has hand-written "Tong cong" / note rows in its date column; the ledger drops them, so they are
    neither unparsed dates nor a reason to block periods."""
    from src.ingestion import BusinessDB
    from src.router import invariants as inv
    db = BusinessDB(PUBLIC / "data" / "dev_014", PUBLIC / "calendar.csv",
                    cache_dir=os.environ.get("DATAMATE_CACHE_DIR") or tmp_path)
    try:
        m = inv.compute(PUBLIC / "data" / "dev_014", db.connection)
    finally:
        db.close()
    assert m["unparsed_dates_pct"] == 0 and m["unparsed_spans"] == []


def test_reviewed_file_format_has_reasons_and_pending_stays_off(tmp_path):
    import json as _json
    from src.router import rule_guard as rg
    data = _json.loads(rg.REVIEWED_PATH.read_text(encoding="utf-8"))
    assert all(x.get("reason") for x in data["approved"])
    approved = rg._load_reviewed(rg.REVIEWED_PATH)
    assert "2|den het ngay x, tinh den hom nay" in approved and "1|don thuoc ky nao" not in approved
    f = tmp_path / "r.json"
    f.write_text('["1|don thuoc ky nao"]', encoding="utf-8")
    assert rg._load_reviewed(f) == {"1|don thuoc ky nao"}   # plain list still accepted


def test_router_only_run_needs_no_model(tmp_path):
    """predict.run with model=None: router answers, everything else abstains, no model object is touched."""
    import json as _json
    from scripts.create_demo_data import create_demo
    from src.predict import run
    root = tmp_path / "data_root"
    create_demo(root)
    out = tmp_path / "result"
    n = run(root, out, None)
    answers = [_json.loads(x) for x in (out / "submission.jsonl").read_text(encoding="utf-8").splitlines()]
    logs = [_json.loads(x) for x in (out / "logs" / "questions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert n == len(answers) == len(logs) and n > 0
    assert all(a["type"] in ("abstain", "unanswerable", "number", "percent", "date", "string", "list") for a in answers)
    assert all("router" in l for l in logs)


def test_questions_are_processed_grouped_by_shop(tmp_path):
    import json as _json
    from src.predict import _lines_grouped_by_shop
    rows = [{"id": "a1", "business_id": "s2"}, {"id": "b1", "business_id": "s1"}, {"id": "a2", "business_id": "s2"},
            {"id": "b2", "business_id": "s1"}]
    f = tmp_path / "q.jsonl"
    f.write_text("\n".join(_json.dumps(r) for r in rows) + "\nnot json\n", encoding="utf-8")
    out = _lines_grouped_by_shop(f)
    ids = [(_json.loads(l)["id"] if l.startswith("{") else "bad") for l in out]
    assert ids == ["b1", "b2", "a1", "a2", "bad"]
