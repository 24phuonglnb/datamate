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
    "tháng 3/2026 lãi gộp là bao nhiêu",                          # gross profit (no cost data yet)
    "tháng 3/2026 nhân viên nào bán nhiều nhất",                  # staff
])
def test_non_target_goes_to_llm(text):
    assert intent(text)[0] is None


@pytest.mark.parametrize("text", [
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
    ("tháng 3/2026 tồn kho còn bao nhiêu", "stock_needs_day"),     # stock is asked at the end of a day, not a month
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


def _canon_rulebook(edit=None, extra_rows=""):
    """A rulebook made of the canonical paraphrase of every row the templates use (rule_specs.canon)."""
    import json as _json
    from src.router import rule_guard as rg
    from src.router import rule_specs as rs
    ref = _json.loads(rg.REFERENCE_PATH.read_text(encoding="utf-8"))["rows"]
    by_sec: dict[str, list[str]] = {}
    for (sec, prefix), spec in rs.SPECS.items():
        text = spec["canon"]
        if edit:
            text = edit(prefix, text)
        # use the full row name of the train rulebook so that the canonical rows are not "new rows"
        full = min((k.split("|", 1)[1] for k in ref if k.startswith(f"{sec}|") and k.split("|", 1)[1].startswith(prefix)),
                   key=len, default=prefix)
        if text is not None:
            by_sec.setdefault(sec, []).append(f"| {full} | {text} |")
    out = ["# Rulebook"]
    for sec, rows in sorted(by_sec.items(), key=lambda kv: int(kv[0])):
        out += [f"## {sec}. Muc {sec}", "| Luat | Mac dinh |", "|---|---|"] + rows
    return "\n".join(out) + "\n" + extra_rows


def _guard(running):
    import json as _json
    from src.router import rule_guard as rg
    ref = _json.loads(rg.REFERENCE_PATH.read_text(encoding="utf-8"))["rows"]
    return rg.RuleGuard(ref, running)


ALL_INTENTS = {"revenue", "order_count", "cancel_count", "cancel_rate", "aov", "best_day", "topk_items", "best_item",
               "item_qty", "item_revenue", "category_rev", "sell_price_on_day", "rev_change_pct", "best_month",
               "monthly_series", "streak_bool", "cust_group_rev", "payment_method_rev", "channel_rev", "unit_total_qty",
               "ingredient_revenue", "rx_nonrx_revenue", "rx_share",
               "shift", "category_share", "size_qty", "unsold_count", "cust_freq_count", "cust_freq_share", "staff_revenue",
               "days_over_threshold"}


def test_rule_guard_canonical_rulebook_disables_nothing():
    assert _guard(_canon_rulebook()).disabled == {}


def test_rule_guard_train_rulebook_disables_nothing():
    f = ROOT / "data" / "train" / "train" / "rulebook.md"
    if not f.is_file():
        pytest.skip("train rulebook not available")
    g = _guard(f.read_text(encoding="utf-8"))
    assert g.disabled == {} and g.new == [] and g.changed == [] and g.removed == []


def test_rule_guard_public_rulebook_only_switches_off_what_has_a_reason():
    f = PUBLIC / "rulebook.md"
    if not f.is_file():
        pytest.skip("public rulebook not available")
    g = _guard(f.read_text(encoding="utf-8"))
    for intent, why in g.disabled.items():
        assert why and all(("missing" in w or "contradicting" in w or "main idea absent" in w) for w in why), (intent, why)
    # a row whose text was only extended (the public edit of "don thuoc ky nao") must not switch anything off
    assert not any("don thuoc ky nao" in w for ws in g.disabled.values() for w in ws)


def test_rule_guard_reversed_rule_switches_off_the_intents_that_use_it():
    g = _guard(_canon_rulebook(lambda p, t: "don huy van tinh vao doanh thu, khong tra hang" if p == "don tinh vao doanh thu" else t))
    assert set(g.disabled) == ALL_INTENTS - {"cancel_count", "cancel_rate", "sell_price_on_day"}
    assert any("contradicting" in w for w in g.disabled["revenue"] if "don tinh vao doanh thu" in w)
    r = Router(g).route({"id": "t1", "as_of_date": AS_OF}, normalize("doanh thu tháng 3/2026", AS_OF), _db())
    assert r.route == "llm" and r.reason.startswith("rulebook_guard:revenue")


def test_rule_guard_negation_is_respected():
    only = lambda p, t, new: new if p == "doanh thu mot don" else t  # noqa: E731
    bad = _guard(_canon_rulebook(lambda p, t: only(p, t, "tong thanh tien cac dong hang, tru giam gia tren ca don")))
    assert "aov" in bad.disabled and "best_day" in bad.disabled
    ok = _guard(_canon_rulebook(lambda p, t: only(p, t, "tong thanh tien cac dong hang (da tru giam gia tren tung dong), khong tru giam gia tren ca don")))
    assert ok.disabled == {}


def test_rule_guard_removed_row_or_section_switches_off():
    g = _guard(_canon_rulebook(lambda p, t: None if p == "so don" else t))
    assert set(g.disabled) == {"order_count", "aov"} and "missing" in g.disabled["order_count"][0]
    g = _guard(_canon_rulebook(lambda p, t: None if p in ("ti le don huy trong ky", "gia ban x ngay d") else t))
    assert set(g.disabled) == {"cancel_rate", "sell_price_on_day"}


def test_rule_guard_extra_sentences_and_new_rows_do_not_switch_off_but_new_rows_make_cues():
    g = _guard(_canon_rulebook(lambda p, t: t + ". them mot cau vi du moi, khong doi y nghia (vi du: don chua giao)",
                               "## 3. Muc 3\n| Ngày đắt khách nhất | ngày có nhiều đơn nhất |\n"))
    assert g.disabled == {} and g.new == ["3|ngay dat khach nhat"]
    d = Router(g).route({"id": "t1", "as_of_date": AS_OF}, normalize("tháng 3/2026 ngày nào đắt khách nhất", AS_OF), _db())
    assert d.route == "llm" and d.reason.startswith("new_rule_cue")
    d = Router(g).route({"id": "t1", "as_of_date": AS_OF}, normalize("tháng 3/2026 ngày nào bán được nhiều tiền nhất", AS_OF), _db())
    assert d.route == "template"


def test_rule_guard_variants_of_the_main_idea_are_accepted():
    g = _guard(_canon_rulebook(lambda p, t: "ngoai tru don huy va don tra hang, bo toan bo don co tra hang" if p == "don tinh vao doanh thu" else t))
    assert g.disabled == {}


def test_reviewed_notes_do_not_change_the_decision():
    from src.router import rule_guard as rg
    reversed_rb = _canon_rulebook(lambda p, t: "huy van tinh, khong tra hang, ca don" if p == "don tinh vao doanh thu" else t)
    import json as _json
    ref = _json.loads(rg.REFERENCE_PATH.read_text(encoding="utf-8"))["rows"]
    g = rg.RuleGuard(ref, reversed_rb, reviewed={"1|don tinh vao doanh thu"})
    assert "revenue" in g.disabled   # an approval note cannot re-enable a contradicted rule


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


def test_reviewed_file_format_has_reasons(tmp_path):
    import json as _json
    from src.router import rule_guard as rg
    data = _json.loads(rg.REVIEWED_PATH.read_text(encoding="utf-8"))
    assert all(x.get("reason") for x in data["approved"])
    approved = rg._load_reviewed(rg.REVIEWED_PATH)
    assert {"2|den het ngay x, tinh den hom nay", "1|don thuoc ky nao"} <= approved
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


class _P:
    def connection(self, shop):
        return _db()

    def flags(self, shop):
        return []

    def spans(self, shop):
        return []


def _q(text, qid="t1"):
    return {"id": qid, "business_id": "x", "as_of_date": AS_OF, "question": text}


def test_hints_reach_an_agent_that_accepts_them():
    from src.nlu.normalize import RuleNormalizer
    from src.router.pipeline import solve

    class NewAgent:
        got = None

        def solve(self, question, hints=None):
            NewAgent.got = hints
            return {"id": question["id"], "type": "abstain"}, {}

    solve(_q("tháng 3/2026 tồn kho mì hảo hảo còn bao nhiêu"), NewAgent(), Router(), RuleNormalizer(None), _P())
    h = NewAgent.got
    assert h["fallthrough_reason"].startswith("stock_needs_day") and h["normalized_text"]   # stock asked for a month: not routed
    assert h["period"] == [{"start": "2026-03-01", "end": "2026-03-31", "granularity": "month", "source": "thang 3/2026"}]
    assert h["where_sql"][0]["sql"] == "order_date BETWEEN '2026-03-01' AND '2026-03-31'"
    assert h["entities"]["item"]["item_name"] == "Mì Hảo Hảo"
    assert h["comparison_period"] is None and h["flags"] == []


def test_hints_part_of_day_and_comparison_where_sql():
    from src.nlu.normalize import RuleNormalizer
    from src.router.pipeline import solve

    class A:
        got = None

        def solve(self, question, **kw):   # **kwargs also counts as accepting hints
            A.got = kw.get("hints")
            return {"id": question["id"], "type": "abstain"}, {}

    solve(_q("tháng 3/2026 ca chiều bán được bao nhiêu tiền so với tháng 2/2026"), A(), Router(), RuleNormalizer(None), _P())
    sqls = [w["sql"] for w in A.got["where_sql"]]
    assert any("BETWEEN '14:00' AND '21:59'" in q for q in sqls) and len(sqls) == 2


def test_old_agent_without_hints_still_runs():
    from src.nlu.normalize import RuleNormalizer
    from src.router.pipeline import solve

    class OldAgent:
        calls = 0

        def solve(self, question):
            OldAgent.calls += 1
            return {"id": question["id"], "type": "abstain"}, {}

    ans, log = solve(_q("tháng 3/2026 tồn kho còn bao nhiêu"), OldAgent(), Router(), RuleNormalizer(None), _P())
    assert OldAgent.calls == 1 and log["router"]["route"] == "llm"


def test_type_error_inside_the_agent_is_not_retried():
    from src.nlu.normalize import RuleNormalizer
    from src.router.pipeline import solve

    class Broken:
        calls = 0

        def solve(self, question, hints=None):
            Broken.calls += 1
            raise TypeError("bug inside the model call")

    with pytest.raises(TypeError):
        solve(_q("tháng 3/2026 tồn kho còn bao nhiêu"), Broken(), Router(), RuleNormalizer(None), _P())
    assert Broken.calls == 1


def test_llm_gate_enables_only_listed_kinds_and_default_is_open():
    from src.nlu.normalize import RuleNormalizer
    from src.router import gate as G
    from src.router.pipeline import solve

    class A:
        calls = 0

        def solve(self, question, hints=None):
            A.calls += 1
            return {"id": question["id"], "type": "number", "answer": 1}, {}

    text = "tháng 3/2026 tồn kho còn bao nhiêu"        # tagger label stock_qty
    ans, log = solve(_q(text), A(), Router(), RuleNormalizer(None), _P())                      # no gate: LLM answers
    assert ans["type"] == "number" and log["router"]["reason"].startswith("stock_needs_day")
    off = {"enabled": ["debt_total"]}
    ans, log = solve(_q(text), A(), Router(), RuleNormalizer(None), _P(), off)
    assert ans["type"] == "abstain" and log["router"]["route"] == "abstain" and log["router"]["reason"] == "llm_gate:stock_qty"
    on = {"enabled": ["stock_qty"]}
    ans, log = solve(_q(text), A(), Router(), RuleNormalizer(None), _P(), on)
    assert ans["type"] == "number"
    assert A.calls == 2
    assert G.gate_key(type("D", (), {"reason": "extra_filter_or_subintent", "intent": "revenue"})()) == "revenue"
    assert G.gate_key(type("D", (), {"reason": "period_missing", "intent": None})()) == "period_missing"


def test_llm_gate_builder_thresholds_and_unknown_kinds(tmp_path):
    import json as _json
    from eval import llm_gate
    rows = []
    rows += [{"route": "llm", "gate_key": "stock_qty", "status": "correct", "fold": "holdout"}] * 8
    rows += [{"route": "llm", "gate_key": "stock_qty", "status": "wrong", "fold": "holdout"}] * 2          # 0.8, 10 answered
    rows += [{"route": "llm", "gate_key": "debt_total", "status": "correct", "fold": "holdout"}] * 4
    rows += [{"route": "llm", "gate_key": "debt_total", "status": "wrong", "fold": "holdout"}] * 8          # 0.33
    rows += [{"route": "llm", "gate_key": "tet", "status": "correct", "fold": "holdout"}] * 3               # too few
    rows += [{"route": "llm", "gate_key": "shift", "status": "abstain", "fold": "holdout"}] * 20            # never answers
    rows += [{"route": "template", "gate_key": "stock_qty", "status": "correct", "fold": "holdout"}] * 50   # not llm route
    g = llm_gate.build_gate(rows, 0.6, 10)
    assert g["enabled"] == ["stock_qty"]
    assert g["disabled"] == {"debt_total": "low_accuracy", "shift": "insufficient_answers", "tet": "insufficient_answers"}
    assert g["stats"]["stock_qty"]["accuracy"] == 0.8 and g["stats"]["stock_qty"]["n"] == 10
    assert g["llm_route"]["questions"] == 10 + 12 + 3 + 20
    assert g["llm_route"]["pa_with_gate"] > g["llm_route"]["pa_llm_answers_all"]
    # rows without gate_key fall back to the router fields
    assert llm_gate.key_of({"router_reason": "not_target:stock_qty", "router_intent": None}) == "stock_qty"
    # file round trip through the CLI path and the pipeline's loader
    f = tmp_path / "pq.jsonl"
    f.write_text("\n".join(_json.dumps(r) for r in rows), encoding="utf-8")
    out = tmp_path / "gate.json"
    import sys as _sys
    from unittest import mock
    with mock.patch.object(_sys, "argv", ["llm_gate", "--per-question", str(f), "--out", str(out)]):
        llm_gate.main()
    from src.router.gate import llm_allowed, load_gate
    gate = load_gate(out)
    assert llm_allowed(gate, "stock_qty") and not llm_allowed(gate, "debt_total") and not llm_allowed(gate, "never_seen")
    assert llm_allowed(None, "anything")


def _db_ext():
    """Synthetic shop with channel / payment / customer group columns and unit-priced lines."""
    c = sqlite3.connect(":memory:")
    _OPEN.append(c)
    c.executescript("""
    CREATE TABLE v_orders(order_id, order_date, order_time, status, revenue, channel, payment_method, customer_group);
    CREATE VIEW v_valid_orders AS SELECT * FROM v_orders WHERE status NOT IN ('huy','tra_hang');
    CREATE TABLE v_valid_lines(order_date, item_code, item_name, qty_base, base_unit, is_service_fee, line_amount, category);
    CREATE TABLE v_items(item_code, item_name, name_aliases, base_unit, category);
    INSERT INTO v_items VALUES('C1','Cà phê sữa','Cà phê sữa','ly','Cà phê'),('C2','Trà đào','Trà đào','ly','Trà');
    """)
    rows = [(1, "2026-01-05", "09:00", "hoan_thanh", 100, "store", "Tiền mặt", "sỉ"),
            (2, "2026-01-06", "10:00", "hoan_thanh", 200, "zalo_oa", "Chuyển khoản", "thân thiết"),
            (3, "2026-01-07", "10:00", "huy", 999, "store", "Tiền mặt", "sỉ"),
            (4, "2026-02-05", "11:00", "hoan_thanh", 400, "store", "Thu hộ (COD)", None),
            (5, "2026-02-09", "11:00", "hoan_thanh", 50, "phone", "Tiền mặt", "sỉ"),
            (6, "2026-03-02", "11:00", "hoan_thanh", 300, "store", "Ghi nợ", "thân thiết")]
    c.executemany("INSERT INTO v_orders VALUES(?,?,?,?,?,?,?,?)", rows)
    c.executemany("INSERT INTO v_valid_lines VALUES(?,?,?,?,?,?,?,?)", [
        ("2026-01-05", "C1", "Cà phê sữa", 3, "ly", 0, 90, "Cà phê"), ("2026-01-06", "C2", "Trà đào", 2, "ly", 0, 100, "Trà"),
        ("2026-01-06", None, "Phí phục vụ", 1, "ly", 1, 10, None)])
    return c


def test_monthly_intents_best_month_series_and_streak():
    c = _db_ext()
    d = route("từ tháng 1/2026 tới tháng 3/2026, tháng nào doanh thu cao nhất", c)
    assert d.route == "template" and d.intent == "best_month" and d.answer == {"id": "t1", "type": "date", "answer": "2026-02"}
    d = route("doanh thu 3 tháng liền nhau kết thúc ở tháng 3/2026 là bao nhiêu mỗi tháng, từ tháng cũ đến tháng mới", c)
    assert d.intent == "monthly_series" and d.answer["type"] == "list" and d.answer["answer"] == [300, 450, 300]
    d = route("từ tháng 1/2026 qua tháng 2/2026 rồi tháng 3/2026, doanh thu có tăng liên tục không", c)
    assert d.intent == "streak_bool" and d.answer == {"id": "t1", "type": "boolean", "answer": False}
    d = route("từ tháng 1/2026 qua tháng 2/2026, doanh thu có tăng liên tục không", c)
    assert d.answer["answer"] is True
    d = route("tháng 1/2026 tháng 2/2026 và tháng 3/2026 tháng nào doanh thu cao nhất", c)   # months named in the order given
    assert d.route == "template"


def test_monthly_tie_goes_to_the_llm_and_month_before_data_too():
    c = _db_ext()
    c.execute("INSERT INTO v_orders VALUES(7,'2026-03-03','12:00','hoan_thanh',150,'store','Tiền mặt',NULL)")  # March = 450 = Feb
    d = route("từ tháng 1/2026 tới tháng 3/2026, tháng nào doanh thu cao nhất", c)
    assert d.route == "llm" and d.reason == "best_month_tie_or_empty"
    d = route("từ tháng 11/2025 tới tháng 1/2026, tháng nào doanh thu cao nhất", c)
    assert d.route == "llm" and d.reason == "month_before_data_start"


def test_group_payment_channel_and_unit_totals():
    c = _db_ext()
    d = route("doanh thu các đơn của khách nhóm sỉ tháng 1/2026", c)
    assert d.intent == "cust_group_rev" and d.answer["answer"] == 100            # the cancelled sỉ order is not valid
    d = route("doanh thu các đơn trả bằng chuyển khoản tháng 1/2026 là bao nhiêu", c)
    assert d.intent == "payment_method_rev" and d.answer["answer"] == 200
    d = route("doanh thu các đơn trả bằng COD tháng 2/2026 là bao nhiêu", c)
    assert d.answer["answer"] == 400                                             # "Thu hộ (COD)" is its own method
    d = route("doanh thu các đơn bán tại quầy tháng 2/2026 là bao nhiêu", c)
    assert d.intent == "channel_rev" and d.answer["answer"] == 400
    d = route("doanh thu các đơn bán qua zalo oa và bán tại quầy tháng 1/2026", c)   # two channels: one number each, in question order
    assert d.route == "template" and d.answer["type"] == "list" and len(d.answer["answer"]) == 2
    d = route("tháng 1/2026 tổng cộng bán được bao nhiêu ly", c)
    assert d.intent == "unit_total_qty" and d.answer["answer"] == 5                 # service fee line excluded
    d = route("tháng 1/2026 bán được tổng cộng bao nhiêu ly cà phê sữa", c)         # a named item: not the all-items total
    assert d.route == "llm"
    d = route("tháng 1/2026 tổng cộng bán được bao nhiêu chai", c)
    assert d.route == "llm" and d.reason == "unit_not_a_base_unit"


# ---- pharmacy drug attributes, purchases, stock and lots (synthetic shop; views as in docs/VIEWS.md 3.5, 3.8, 3.9) ------
def _pharma_db(*, purchases=True, stock=True, lots=True, amounts=True, card=False):
    c = _db()
    c.executescript("""
    DROP TABLE v_items; DROP TABLE v_valid_lines;
    CREATE TABLE v_items(item_code, item_name, name_aliases, base_unit, category, active_ingredient, is_prescription);
    CREATE TABLE v_valid_lines(order_date, item_code, item_name, qty_base, is_service_fee, line_amount);
    """)
    c.executemany("INSERT INTO v_items VALUES(?,?,?,?,?,?,?)", [
        ("T1", "Panadol hộp 10 vỉ x 10 viên", "Panadol hộp 10 vỉ x 10 viên", "viên", "Thuốc", "Paracetamol", "0"),
        ("T2", "Efferalgan hộp 10 viên", "Efferalgan hộp 10 viên", "viên", "Thuốc", "Paracetamol + Cafein", "0"),
        ("T3", "Augmentin 625 hộp 14 viên", "Augmentin 625 hộp 14 viên", "viên", "Thuốc", "Amoxicillin", "1")])
    c.executemany("INSERT INTO v_valid_lines VALUES(?,?,?,?,?,?)", [
        ("2026-03-02", "T1", "Panadol hộp 10 vỉ x 10 viên", 10, 0, 50000), ("2026-03-03", "T2", "Efferalgan hộp 10 viên", 5, 0, 30000),
        ("2026-03-04", "T3", "Augmentin 625 hộp 14 viên", 2, 0, 20000)])
    if purchases:
        c.execute("CREATE TABLE v_valid_purchase_lines(receipt_id, receipt_date, receipt_month, supplier, item_code, item_name, qty, unit, line_amount)")
        a = (lambda x: x) if amounts else (lambda x: None)
        c.executemany("INSERT INTO v_valid_purchase_lines VALUES(?,?,?,?,?,?,?,?,?)", [
            ("P1", "2026-03-02", "2026-03", "Cty A", "T1", "Panadol hộp 10 vỉ x 10 viên", 2, "hộp", a(200000)),
            ("P2", "2026-03-10", "2026-03", "Cty B", "T1", "Panadol hộp 10 vỉ x 10 viên", 3, "hộp", a(330000)),
            ("P3", "2026-03-12", "2026-03", "Cty A", "T3", "Augmentin 625 hộp 14 viên", 1, "hộp", a(100000))])
    if stock:
        c.execute("CREATE TABLE v_stock(item_code, item_name, base_unit, stock_date, stock_qty_base, cost_price, stock_value, source)")
        c.executemany("INSERT INTO v_stock VALUES(?,?,?,?,?,?,?,?)", [
            ("T1", "Panadol hộp 10 vỉ x 10 viên", "viên", AS_OF, 253, 100, 25300, "report"),
            ("T2", "Efferalgan hộp 10 viên", "viên", AS_OF, 0, 200, 0, "report"),
            ("T3", "Augmentin 625 hộp 14 viên", "viên", AS_OF, 30, 500, 15000, "report")])
        c.execute("CREATE TABLE v_item_units(item_code, item_name, unit, unit_key, factor, base_unit)")
        c.executemany("INSERT INTO v_item_units VALUES(?,?,?,?,?,?)", [
            ("T1", "Panadol hộp 10 vỉ x 10 viên", "hộp", "hop", 100, "viên"), ("T1", "Panadol hộp 10 vỉ x 10 viên", "vỉ", "vi", 10, "viên")])
    if lots:
        c.execute("CREATE TABLE v_lots(lot, item_code, item_name, expiry_date, qty_remaining)")
        c.executemany("INSERT INTO v_lots VALUES(?,?,?,?,?)", [
            ("L1", "T1", "Panadol hộp 10 vỉ x 10 viên", "2026-10-01", 50), ("L2", "T1", "Panadol hộp 10 vỉ x 10 viên", "2026-12-01", 20),
            ("L3", "T3", "Augmentin 625 hộp 14 viên", "2026-09-20", 30), ("L4", "T3", "Augmentin 625 hộp 14 viên", "2026-09-30", 0),
            ("L5", "T3", "Augmentin 625 hộp 14 viên", "2026-09-01", 5)])
    if card:
        c.execute("CREATE TABLE v_stock_card(item_code, item_name, moved_at, moved_date, qty_change, stock_after)")
        c.executemany("INSERT INTO v_stock_card VALUES(?,?,?,?,?,?)", [
            ("T1", "Panadol hộp 10 vỉ x 10 viên", "2026-08-01 09:00:00", "2026-08-01", 300, 300),
            ("T1", "Panadol hộp 10 vỉ x 10 viên", "2026-08-05 09:00:00", "2026-08-05", -47, 253)])
    return c


@pytest.mark.parametrize("text,answer,atype", [
    ("tháng 3/2026 nhà thuốc thu được bao nhiêu tiền từ các thuốc có hoạt chất Paracetamol?", 50000, "number"),   # not the A + B combination
    ("tháng 3/2026 các thuốc có hoạt chất Paracetamol + Cafein bán được bao nhiêu tiền", 30000, "number"),
    ("doanh thu thuốc kê đơn tháng 3/2026 là bao nhiêu", 20000, "number"),
    ("doanh thu hàng không kê đơn tháng 3/2026 là bao nhiêu", 80000, "number"),
    ("trừ thuốc kê đơn ra, tháng 3/2026 các mặt hàng còn lại bán được bao nhiêu tiền", 80000, "number"),
    ("tháng 3/2026 thuốc kê đơn chiếm bao nhiêu phần trăm doanh thu", 20.0, "percent"),
])
def test_pharmacy_sales_templates(text, answer, atype):
    d = route(text, _pharma_db())
    assert d.route == "template", d.reason
    assert (d.answer["answer"], d.answer["type"]) == (answer, atype)


def test_ingredient_not_in_catalog_goes_to_llm():
    d = route("tháng 3/2026 thuốc có hoạt chất Ibuprofen bán được bao nhiêu tiền", _pharma_db())
    assert d.route == "llm" and d.reason == "ingredient_not_found"
    c = _pharma_db()
    c.execute("DELETE FROM v_items WHERE active_ingredient = 'Paracetamol + Cafein'")   # only 'Paracetamol' is left: "A + B" is not 'A'
    d = route("tháng 3/2026 thuốc có hoạt chất Paracetamol + Cafein bán được bao nhiêu tiền", c)
    assert d.route == "llm"


@pytest.mark.parametrize("text,answer,atype", [
    ("tổng tiền nhập hàng tháng 3/2026 là bao nhiêu", 630000, "number"),
    ("tháng 3/2026 tổng giá trị các phiếu nhập hàng là bao nhiêu", 630000, "number"),
    ("tháng 3/2026 tiền nhập hàng từ nhà cung cấp nào cao nhất", "Cty B", "string"),
    ("trong tháng 3/2026, Panadol hộp 10 vỉ x 10 viên nhập vào giá bình quân một hộp là bao nhiêu", 106000, "number"),
])
def test_purchase_templates(text, answer, atype):
    d = route(text, _pharma_db())
    assert d.route == "template", d.reason
    assert (d.answer["answer"], d.answer["type"]) == (answer, atype)


def test_purchase_avg_price_unit_must_be_an_import_unit():
    d = route("trong tháng 3/2026, Panadol hộp 10 vỉ x 10 viên nhập vào giá bình quân một viên là bao nhiêu", _pharma_db())
    assert d.route == "llm" and d.reason == "unit_not_an_import_unit"


@pytest.mark.parametrize("text,answer,atype", [
    ("cuối ngày hôm nay Panadol hộp 10 vỉ x 10 viên trong kho còn bao nhiêu viên", 253, "number"),
    ("cuối ngày hôm nay trong kho còn bao nhiêu hộp Panadol hộp 10 vỉ x 10 viên chẵn và bao nhiêu viên lẻ", [2, 53], "list"),
    ("tính theo giá vốn, tiền hàng nằm trong kho vào cuối ngày 07/09/2026 là bao nhiêu", 40300, "number"),
    ("có mấy lô hàng còn tồn sẽ hết hạn từ nay đến hết ngày 31/10/2026", 2, "number"),      # L3 and L1; L4 is empty, L5 expired, L2 later
    ("những sản phẩm nào đang còn hàng có hạn dùng từ 07/09/2026 đến hết 31/12/2026", ["Augmentin 625 hộp 14 viên", "Panadol hộp 10 vỉ x 10 viên"], "list"),
    ("lô Panadol hộp 10 vỉ x 10 viên còn ở kho gần hết hạn nhất có hạn dùng ngày nào", "2026-10-01", "date"),
])
def test_stock_and_lot_templates(text, answer, atype):
    d = route(text, _pharma_db())
    assert d.route == "template", d.reason
    assert (d.answer["answer"], d.answer["type"]) == (answer, atype)


def test_stock_at_an_earlier_day_uses_the_stock_card_only_when_it_exists():
    q = "hết ngày 03/08/2026 trong kho còn bao nhiêu viên Panadol hộp 10 vỉ x 10 viên"
    d = route(q, _pharma_db(card=True))
    assert d.route == "template" and d.answer["answer"] == 300
    d = route(q, _pharma_db(card=False))
    assert d.route == "llm" and d.reason == "stock_past_no_card"


@pytest.mark.parametrize("kw,text,code", [
    (dict(purchases=False), "tổng tiền nhập hàng tháng 3/2026 là bao nhiêu", "no_purchase_book"),
    (dict(purchases=False), "tháng 3/2026 tiền nhập hàng từ nhà cung cấp nào cao nhất", "no_purchase_book"),
    (dict(purchases=False), "trong tháng 3/2026, Panadol hộp 10 vỉ x 10 viên nhập vào giá bình quân một hộp là bao nhiêu", "no_purchase_book"),
    (dict(amounts=False), "tổng tiền nhập hàng tháng 3/2026 là bao nhiêu", "no_purchase_amount"),      # quantities only
    (dict(stock=False), "cuối ngày hôm nay Panadol hộp 10 vỉ x 10 viên trong kho còn bao nhiêu viên", "no_stock_data"),
    (dict(stock=False), "cuối ngày hôm nay trong kho còn bao nhiêu hộp Panadol hộp 10 vỉ x 10 viên chẵn và bao nhiêu viên lẻ", "no_stock_data"),
    (dict(stock=False), "tính theo giá vốn, tiền hàng nằm trong kho vào cuối ngày 07/09/2026 là bao nhiêu", "no_stock_data"),
    (dict(lots=False), "có mấy lô hàng còn tồn sẽ hết hạn từ nay đến hết ngày 31/10/2026", "no_lot_data"),
    (dict(lots=False), "lô Panadol hộp 10 vỉ x 10 viên còn ở kho gần hết hạn nhất có hạn dùng ngày nào", "no_lot_data"),
])
def test_shop_without_the_view_is_unanswerable_not_an_sql_error(kw, text, code):
    d = route(text, _pharma_db(**kw))
    assert d.route == "unanswerable" and d.reason == code
    assert d.answer["type"] == "unanswerable" and d.answer["id"] == "t1" and isinstance(d.answer["reason"], str)
    assert "answer" not in d.answer


def test_inventory_rule_rows_missing_switch_the_intent_off():
    from src.router.rule_guard import RuleGuard
    ref = json.loads((ROOT / "src" / "router" / "rule_reference.json").read_text(encoding="utf-8"))["rows"]
    text = "## 5. Kho\n| Tiền nhập hàng trong kỳ | x |\n"   # every other row missing: the dependent intents are disabled
    g = RuleGuard(ref, text)
    assert "stock_large_unit" in g.disabled and "purchase_avg_price" in g.disabled and "ingredient_revenue" in g.disabled


# ---- router-expansion: shifts, price effect, category share, size, unsold items, customers, staff -----------------------
def _exp_db(order_time=True):
    c = sqlite3.connect(":memory:")
    _OPEN.append(c)
    c.executescript("""
    CREATE TABLE v_orders(order_id, order_date, order_time, status, revenue, customer_key, staff);
    CREATE VIEW v_valid_orders AS SELECT * FROM v_orders WHERE status NOT IN ('huy','tra_hang');
    CREATE TABLE v_valid_lines(order_date, item_code, item_name, qty_base, is_service_fee, line_amount, category);
    CREATE TABLE v_items(item_code, item_name, name_aliases, base_unit, category);
    CREATE TABLE v_item_units(item_code, item_name, unit, unit_key, factor, base_unit);
    """)
    t = (lambda x: x) if order_time else (lambda x: None)
    c.executemany("INSERT INTO v_orders VALUES(?,?,?,?,?,?,?)", [
        (1, "2026-03-02", t("09:00:00"), "hoan_thanh", 1000, "K1", "NV001"), (2, "2026-03-02", t("15:30:00"), "hoan_thanh", 3000, "K1", "NV002"),
        (3, "2026-03-03", t("10:00:00"), "hoan_thanh", 500, "K2", "NV001"), (4, "2026-03-03", t("20:00:00"), "huy", 9990, "K2", "NV001"),
        (5, "2026-03-04", t("07:00:00"), "hoan_thanh", 1500, None, "NV001"), (6, "2026-03-05", t("14:00:00"), "hoan_thanh", 2000, "K1", "NV002")])
    c.executemany("INSERT INTO v_items VALUES(?,?,?,?,?)", [
        ("A1", "Cà phê sữa (M)", "Cà phê sữa (M)", "ly", "Cà phê"), ("A2", "Cà phê sữa (L)", "Cà phê sữa (L)", "ly", "Cà phê"),
        ("B1", "Nước suối Aqua", "Nước suối Aqua", "chai", "Nước"), ("C1", "Bánh mì", "Bánh mì", "cái", "Bánh")])
    c.executemany("INSERT INTO v_item_units VALUES(?,?,?,?,?,?)", [("B1", "Nước suối Aqua", "thùng", "thung", 24, "chai")])
    c.executemany("INSERT INTO v_valid_lines VALUES(?,?,?,?,?,?,?)", [
        ("2026-02-20", "C1", "Bánh mì", 4, 0, 40, "Bánh"),                                       # sold before March only
        ("2026-03-02", "A1", "Cà phê sữa (M)", 3, 0, 150, "Cà phê"), ("2026-03-02", "A2", "Cà phê sữa (L)", 2, 0, 250, "Cà phê"),
        ("2026-03-03", "B1", "Nước suối Aqua", 48, 0, 50, "Nước"), ("2026-03-04", "B1", "Nước suối Aqua", 24, 0, 150, "Nước"),
        ("2026-03-06", "B1", "Nước suối Aqua", 12, 0, 60, "Nước"), ("2026-03-02", None, "Phí phục vụ", 1, 1, 10, None)])
    return c


@pytest.mark.parametrize("text,answer,atype", [
    ("doanh thu ca sáng tháng 3/2026 là bao nhiêu", 3000, "number"),                                  # orders 1, 3, 5: 09:00, 10:00, 07:00 (4 is cancelled)
    ("tháng 3/2026 ca chiều có bao nhiêu đơn", 2, "number"),                                          # 15:30 and 14:00
    ("tháng 3/2026 doanh thu ca chiều so với ca sáng chênh bao nhiêu %", 66.67, "percent"),           # (5000 - 3000) / 3000
])
def test_shift_templates(text, answer, atype):
    d = route(text, _exp_db())
    assert d.route == "template", d.reason
    assert (d.answer["answer"], d.answer["type"]) == (answer, atype)


def test_shift_without_order_time_is_not_answered():
    d = route("doanh thu ca sáng tháng 3/2026 là bao nhiêu", _exp_db(order_time=False))
    assert d.route == "llm" and d.reason == "order_time_missing"


def test_price_effect_uses_the_resolved_ranges():
    q = "từ ngày 03/03/2026, Nước suối Aqua tăng giá lên 6.000đ. So 2 ngày kể từ ngày 03/03/2026 với 2 ngày ngay trước đó, số chai bán ra thay đổi bao nhiêu %"
    d = route(q, _exp_db())            # 03-03..03-04: 72 bottles; 03-01..03-02: none -> not decidable
    assert d.route == "llm" and d.reason == "empty_previous_range"
    q2 = "từ ngày 05/03/2026, Nước suối Aqua tăng giá lên 6.000đ. So 2 ngày kể từ ngày 05/03/2026 với 2 ngày ngay trước đó, số chai bán ra thay đổi bao nhiêu %"
    d = route(q2, _exp_db())           # 03-05..03-06: 12; 03-03..03-04: 72 -> -83.33
    assert d.route == "template" and d.answer == {"id": "t1", "type": "percent", "answer": -83.33}
    q3 = q2.replace("ngày kể từ ngày 05/03/2026", "ngày kể từ ngày đó")
    d = route(q3, _exp_db())
    assert d.route == "template" and d.answer["answer"] == -83.33


def test_category_size_unsold_threshold_customers_staff_and_unit_conversion():
    c = _exp_db()
    d = route("tháng 3/2026 nhóm cà phê chiếm bao nhiêu phần trăm doanh thu", c)       # 400 / 8000 = 5%
    assert d.route == "template" and d.answer["answer"] == 5.0 and d.answer["type"] == "percent"
    d = route("tháng 3/2026 bán được bao nhiêu ly size M", c)
    assert d.route == "template" and d.answer["answer"] == 3
    d = route("tháng 3/2026 có bao nhiêu mặt hàng bị ế", c)                               # Bánh mì sold in February, not in March
    assert d.route == "template" and d.answer["answer"] == 1
    d = route("tháng 3/2026 có mấy ngày doanh thu đạt 2.000 đồng trở lên", c)              # 03-02: 4000, 03-03: 500, 03-04: 1500, 03-05: 2000
    assert d.route == "template" and d.answer["answer"] == 2
    d = route("tháng 3/2026 có mấy khách mua từ 2 đơn trở lên", c)                         # K1: 3 orders; K2: 1
    assert d.route == "template" and d.answer["answer"] == 1
    d = route("tháng 3/2026 khách mua từ 2 đơn trở lên chiếm bao nhiêu phần trăm số khách đã mua", c)
    assert d.route == "template" and d.answer["answer"] == 50.0
    d = route("tháng 3/2026 nhân viên mã NV002 bán được bao nhiêu tiền", c)
    assert d.route == "template" and d.answer["answer"] == 5000
    d = route("tháng 3/2026 bán được bao nhiêu thùng nước suối aqua", c)                  # 84 bottles = 3.5 crates
    assert d.route == "template" and d.answer["answer"] == 3.5
    d = route("tháng 3/2026 khách mua hơn 2 đơn", c)                                       # not "at least": never answered
    assert d.route == "llm"
