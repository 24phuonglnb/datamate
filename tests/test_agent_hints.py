"""CPU-only agent regressions with synthetic data; no model weights or gold lookup."""
import copy
import csv
import inspect
import json
from unittest.mock import Mock

import pytest

from eval.pa_score import score_one
from scripts.create_demo_data import create_demo
from src.agent import Agent, SYSTEM, format_hints_for_prompt, normalize_date_hints, typed_result
from src.nlu.normalize import normalize


class CapturingModel:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.prompts = []

    def generate(self, system, user):
        self.prompts.append((system, user))
        return json.dumps(next(self.responses), ensure_ascii=False), None


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAMATE_NO_CACHE", "1")
    monkeypatch.delenv("DATAMATE_LEGACY_INGESTION", raising=False)
    create_demo(tmp_path)
    return tmp_path


@pytest.fixture
def question():
    return {"id": "synthetic_agent", "business_id": "shop_demo",
            "question": "dthu xi mang a thang 3 la bn", "as_of_date": "2026-03-31"}


@pytest.fixture
def hints():
    return {
        "normalized_text": "Doanh thu mặt hàng Xi măng A trong tháng 03/2026 là bao nhiêu?",
        "period": [{"start": "2026-03-01", "end": "2026-03-31", "granularity": "month", "source": "tháng 3"}],
        "comparison_period": None, "part_of_day": None,
        "where_sql": [{"period": "tháng 3", "sql": "order_date BETWEEN '2026-03-01' AND '2026-03-31'"}],
        "ambiguous_period": [], "flags": ["no_diacritics"],
        "entities": {"numbers": [], "dates": [],
                     "item": {"item_code": "SP01", "item_name": "Xi măng A", "base_unit": "bao"},
                     "category": "Vật liệu xây dựng"},
        "fallthrough_reason": "extra_filter_or_subintent", "fallthrough_intent": "item_revenue",
    }


def test_typed_result_table_matches_pa_scorer_format():
    expected = {"columns": ["item_name", "qty"], "rows": [["Bia Tiger", 10], ["Nước ngọt", 5]]}
    result = typed_result("table", ["item_name", "qty"], [("Bia Tiger", 10), ("Nước ngọt", 5)])
    assert result == expected
    assert score_one({"type": "table", "answer": result}, {"type": "table", "answer": expected}) == (1, "correct")


def test_table_preserves_null_order_and_empty_result():
    assert typed_result("table", ["z", "a"], [(None, 0), ("", 1.5)]) == {
        "columns": ["z", "a"], "rows": [[None, 0], ["", 1.5]]}
    assert typed_result("table", ["item_name"], []) == {"columns": ["item_name"], "rows": []}


@pytest.mark.parametrize("columns,rows", [([], []), (["x", "y"], [(1,)]),
                                         (["x"], [(1, 2)]), (["x"], [(float("inf"),)]),
                                         (["x"], [(float("nan"),)])])
def test_table_rejects_invalid_shape_and_nonfinite_values(columns, rows):
    with pytest.raises(ValueError):
        typed_result("table", columns, rows)


def test_agent_accepts_optional_hints_signature():
    assert inspect.signature(Agent.solve).parameters["hints"].default is None


def test_agent_solve_injects_router_hints_into_prompt(root, question, hints):
    model = CapturingModel({"type": "number", "sql":
        "SELECT SUM(CAST(doanh_thu AS INTEGER)) FROM sales "
        "WHERE san_pham = 'Xi măng A' AND ngay BETWEEN '2026-03-01' AND '2026-03-31'"})
    normalizer = Mock(side_effect=AssertionError("Router already normalized the question"))
    agent = Agent(model, root, normalizer=normalizer)
    original = copy.deepcopy(hints)
    try:
        answer, log = agent.solve(question, hints=hints)
        assert answer == {"id": question["id"], "type": "number", "answer": 1000000}
        prompt = model.prompts[0][1]
        for value in ("ROUTER HINTS", hints["where_sql"][0]["sql"], "Xi măng A", "SP01",
                      "bao", "Vật liệu xây dựng", "no_diacritics", "extra_filter_or_subintent"):
            assert value in prompt
        assert prompt.endswith("QUESTION: " + hints["normalized_text"])
        assert "ORIGINAL QUESTION: " + question["question"] in prompt
        assert log["hints"] == original == hints
        json.dumps(log, ensure_ascii=False, allow_nan=False)
        normalizer.assert_not_called()
    finally:
        agent.close()


def test_comparison_shifts_ambiguity_and_open_start(hints):
    hints["period"][0]["start"] = None
    hints["comparison_period"] = {"start": "2026-02-01", "end": "2026-02-28", "source": "tháng trước"}
    hints["part_of_day"] = {"sang": ["06:00", "13:59"], "chieu": ["14:00", "23:59"], "baseline": "sang"}
    hints["ambiguous_period"] = ["6/25"]
    hints["where_sql"].append({"period": "comparison", "sql": "order_month = '2026-02'"})
    rendered = format_hints_for_prompt(hints)
    for value in ("BEGINNING_OF_DATA", "Comparison period", "2026-02-28", "06:00", "23:59",
                  '"baseline": "sang"', "6/25", "order_month = '2026-02'"):
        assert value in rendered


@pytest.mark.parametrize("bad", [None, {}, [], "invalid", 7,
    {"period": 7, "where_sql": True, "entities": [], "part_of_day": "sang", "ambiguous_period": 2},
    {"period": [None, "bad", {}], "where_sql": [None, "bad", {"sql": 7}], "entities": {"item": []}}])
def test_optional_malformed_hints_do_not_crash(bad):
    assert format_hints_for_prompt(bad) == ""


@pytest.mark.parametrize("bad", [None, {}, [], "invalid"])
def test_no_usable_hints_preserve_normalizer_path(root, question, bad):
    question["question"] = "doanh thu tháng 3/2026 là bao nhiêu"
    nq = normalize(question["question"], question["as_of_date"])
    normalizer = Mock(return_value=nq)
    model = CapturingModel({"type": "abstain"})
    agent = Agent(model, root, normalizer=normalizer)
    try:
        answer, log = agent.solve(question, hints=bad)
        normalizer.assert_called_once_with(question["question"], question["as_of_date"])
        assert answer["type"] == "abstain"
        assert log["normalized"]["text"] == nq.text
        assert "RESOLVED TIME PERIODS" in model.prompts[0][1]
        assert "ROUTER HINTS" not in model.prompts[0][1]
    finally:
        agent.close()


@pytest.mark.parametrize("normalized_text", [None, "", "  ", 123, ["bad"]])
def test_partial_hints_keep_raw_question_and_skip_second_normalization(root, question, normalized_text):
    question["question"] = "Doanh thu ngày 3/3?"
    model = CapturingModel({"type": "abstain"})
    normalizer = Mock(side_effect=AssertionError("Must not rerun router normalization"))
    agent = Agent(model, root, normalizer=normalizer)
    try:
        _, log = agent.solve(question, hints={"normalized_text": normalized_text, "fallthrough_reason": "extra_filter"})
        assert "QUESTION: Doanh thu ngày 3/3 (2026-03-03)?" in model.prompts[0][1]
        assert "error" not in log
        normalizer.assert_not_called()
    finally:
        agent.close()


def test_legacy_call_without_normalizer(root, question):
    question["question"] = "Doanh thu ngày 3/3?"
    model = CapturingModel({"type": "number", "sql": "SELECT SUM(CAST(doanh_thu AS INTEGER)) FROM sales"})
    agent = Agent(model, root)
    try:
        answer, log = agent.solve(question)
        assert answer["answer"] == 1750000
        assert "2026-03-03" in model.prompts[0][1]
        assert "hints" not in log and "normalized" not in log
    finally:
        agent.close()


@pytest.mark.parametrize("length", [25000, 60000])
def test_entire_rulebook_reaches_model(root, question, length):
    marker = "RULE_TAIL_MARKER_SECTION_11"
    rulebook = "Quy tắc\n" + "x" * length + marker
    (root / "rulebook.md").write_text(rulebook, encoding="utf-8")
    model = CapturingModel({"type": "abstain"})
    agent = Agent(model, root)
    try:
        assert agent.rulebook == rulebook
        agent.solve(question)
        assert marker in model.prompts[0][1]
    finally:
        agent.close()


def test_system_prompt_is_view_first():
    for value in ("v_valid_orders", "v_valid_lines", "is_service_fee = 0", "v_orders", "v_lines",
                  "v_items", "v_valid_purchase_lines", "v_stock", "v_lots", "v_stock_card",
                  "v_item_units", "v_payments", "v_deliveries", "calendar", "NON-LEDGER", "NULLIF"):
        assert value in SYSTEM
    assert "All CSV columns are stored as SQLite TEXT" not in SYSTEM


def test_table_end_to_end_and_retry_keeps_hints(root, question, hints):
    model = CapturingModel(
        {"type": "table", "sql": "SELECT missing_column FROM sales"},
        {"type": "table", "sql": "SELECT san_pham AS item_name, SUM(CAST(so_luong AS REAL)) AS qty "
                                  "FROM sales GROUP BY san_pham ORDER BY san_pham"})
    agent = Agent(model, root)
    try:
        answer, log = agent.solve(question, hints=hints)
        gold = {"type": "table", "answer": {"columns": ["item_name", "qty"],
                                             "rows": [["Gạch B", 15], ["Xi măng A", 10]]}}
        assert score_one(answer, gold) == (1, "correct")
        assert len(model.prompts) == 2
        assert all(hints["where_sql"][0]["sql"] in user for _, user in model.prompts)
        assert "PREVIOUS SQL ATTEMPT FAILED" in model.prompts[1][1]
        assert log["answer"] == answer
    finally:
        agent.close()


def test_hints_cannot_bypass_readonly_execution(root, question, hints):
    hints["where_sql"] = [{"sql": "DELETE FROM sales"}]
    model = CapturingModel({"type": "number", "sql": "DELETE FROM sales"})
    agent = Agent(model, root, max_attempts=1)
    try:
        answer, _ = agent.solve(question, hints=hints)
        assert answer["type"] == "abstain"
        assert agent._db("shop_demo").execute_readonly("SELECT COUNT(*) FROM sales")[1] == [(4,)]
    finally:
        agent.close()


@pytest.mark.parametrize("text,anchor,expected", [
    ("ngày 3/3", "2031-05-01", "ngày 3/3 (2031-03-03)"),
    ("ngày 3/3", "", "ngày 3/3"),
    ("ngày 3/3", "invalid", "ngày 3/3"),
    ("ngày 3/3", "2026-02-30", "ngày 3/3"),
    ("ngày 29/2/2024", "", "ngày 29/2/2024 (2024-02-29)"),
    ("ngày 29/2", "2026-03-31", "ngày 29/2"),
    ("tháng 13", "2026-03-31", "tháng 13"),
    ("tháng 3", "", "tháng 3"),
    ("tháng 03/2025", "2030-03-31", "tháng 03/2025 (tháng 03/2025)"),
    ("tháng 2 năm 2024", "", "tháng 2 năm 2024 (tháng 2/2024)"),
    ("2026-03-01", "2026-03-31", "2026-03-01"),
])
def test_date_annotations_never_invent_year_or_rewrite_iso(text, anchor, expected):
    assert normalize_date_hints(text, anchor) == expected


@pytest.fixture
def ledger_question(root, question):
    """A separate synthetic ledger shop; shop_demo intentionally has no sales views."""
    question = {**question, "business_id": "synthetic_ledger"}
    business = root / "data" / question["business_id"]
    business.mkdir()
    (business / "README.md").write_text("Sổ bán vật liệu, mỗi dòng là một đơn hàng.", encoding="utf-8")
    for name, rows in {
        "danh_muc.csv": [
            ["Mã hàng", "Tên hàng", "Nhóm hàng", "ĐVT cơ bản", "Giá bán"],
            ["SP01", "Xi măng A", "Vật liệu xây dựng", "bao", 100000]],
        "ban_hang.csv": [
            ["Mã HĐ", "Ngày bán", "Trạng thái", "Mã SP", "Tên hàng", "ĐVT", "SL", "Đơn giá", "Thanh tien"],
            ["HD01", "2026-03-01", "Hoàn thành", "SP01", "Xi măng A", "bao", 4, 100000, 400000],
            ["HD02", "2026-03-03", "Đang giao", "SP01", "Xi măng A", "bao", 6, 100000, 600000],
            ["HD03", "2026-03-05", "Khách hủy", "SP01", "Xi măng A", "bao", 2, 100000, 200000]],
    }.items():
        with (business / name).open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(rows)
    return question


def test_agent_executes_view_query(root, ledger_question):
    model = CapturingModel({"type": "number", "sql": "SELECT SUM(revenue) FROM v_valid_orders"})
    agent = Agent(model, root)
    try:
        answer, log = agent.solve(ledger_question)
        assert answer["answer"] == 1000000, log
        assert "v_valid_orders" in model.prompts[0][1]
    finally:
        agent.close()


def test_real_router_handoff(root, ledger_question):
    # main intentionally has no router package; exercised on integration branches.
    pipeline = pytest.importorskip("src.router.pipeline")
    from src.router.hints import build_hints
    from src.router.router import RouteDecision

    question = {**ledger_question, "question": "Doanh thu Xi măng A tháng 3/2026 là bao nhiêu?"}
    nq = normalize(question["question"], question["as_of_date"])
    model = CapturingModel({"type": "number", "sql":
        "SELECT SUM(line_amount) FROM v_valid_lines WHERE item_name = 'Xi măng A' AND is_service_fee = 0"})
    normalizer = Mock(side_effect=AssertionError("Already normalized"))
    agent = Agent(model, root, normalizer=normalizer)
    try:
        assert pipeline._accepts_hints(agent)
        hints = build_hints(question, nq, RouteDecision("llm", "extra_filter", "item_revenue"),
                            agent._db(question["business_id"]).connection)
        answer, log = pipeline.call_agent(agent, question, hints)
        assert answer["answer"] == 1000000
        assert log["hints"] == hints
        assert hints["entities"]["item"]["item_code"] == "SP01"
        assert "2026-03-01" in model.prompts[0][1]
        assert "Xi măng A" in model.prompts[0][1]
        normalizer.assert_not_called()
    finally:
        agent.close()
