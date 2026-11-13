"""Regression tests for the official dataset adapter and scoring.

Tests verify:
  - Official dataset parsing (questions.jsonl, answers.jsonl schema)
  - PA scoring: correct → +1, incorrect → -1, abstain → 0
  - Unanswerable / abstain handling
  - Alias matching for strings, lists, and tables
  - Type-exact matching rules (number, percent, boolean, date)
  - Split separation: ground truth never leaks into agent input
  - Official evaluator end-to-end (mock model)
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from eval.official_dataset import OfficialDataset, OfficialQuestion, OfficialAnswer
from eval.official_score import (
    answers_match,
    compute_pa_score,
    _cmp_number,
    _cmp_percent,
    _cmp_list,
    _cmp_table,
    _str_matches,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

def _make_dataset(
    tmp_dir: Path,
    questions: list[dict],
    answers: list[dict] | None,
    *,
    split: str = "train",
) -> OfficialDataset:
    """Create a minimal on-disk dataset for testing."""
    root = tmp_dir / split
    root.mkdir(parents=True)
    (root / "data").mkdir()

    # Collect unique business IDs and create placeholder dirs
    biz_ids = {q["business_id"] for q in questions}
    for biz_id in biz_ids:
        biz_dir = root / "data" / biz_id
        biz_dir.mkdir(parents=True, exist_ok=True)
        (biz_dir / "README.md").write_text(f"# {biz_id}\nTest business.\n")

    with (root / "questions.jsonl").open("w", encoding="utf-8") as f:
        for q in questions:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    if answers is not None:
        with (root / "answers.jsonl").open("w", encoding="utf-8") as f:
            for a in answers:
                f.write(json.dumps(a, ensure_ascii=False) + "\n")

    (root / "calendar.csv").write_text("date,weekday\n2026-01-01,4\n")
    (root / "rulebook.md").write_text("# Rulebook\nTest rules.\n")

    return OfficialDataset(root, split=split)


SAMPLE_QUESTIONS = [
    {"id": "q_001", "business_id": "biz_a", "question": "Total revenue?", "as_of_date": "2026-05-01"},
    {"id": "q_002", "business_id": "biz_a", "question": "Best seller?", "as_of_date": "2026-05-01"},
    {"id": "q_003", "business_id": "biz_b", "question": "Revenue Jan?", "as_of_date": "2026-05-01"},
    {"id": "q_004", "business_id": "biz_b", "question": "Unanswerable one", "as_of_date": "2026-05-01"},
]

SAMPLE_ANSWERS = [
    {"id": "q_001", "type": "number",  "answer": 1000000, "alias": []},
    {"id": "q_002", "type": "string",  "answer": "Cà phê sữa", "alias": ["SP001"]},
    {"id": "q_003", "type": "percent", "answer": 12.50,   "alias": []},
    {"id": "q_004", "type": "unanswerable", "answer": None, "alias": []},
]


# ── Dataset parsing ───────────────────────────────────────────────────────

class TestOfficialDatasetParsing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.ds = _make_dataset(
            Path(cls._tmp.name),
            SAMPLE_QUESTIONS,
            SAMPLE_ANSWERS,
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_question_count(self):
        self.assertEqual(len(self.ds.questions), 4)

    def test_answer_count(self):
        self.assertEqual(len(self.ds.answers), 4)

    def test_question_fields(self):
        q = self.ds.questions[0]
        self.assertIsInstance(q, OfficialQuestion)
        self.assertEqual(q.id, "q_001")
        self.assertEqual(q.business_id, "biz_a")
        self.assertIsNotNone(q.question)
        self.assertIsNotNone(q.as_of_date)

    def test_answer_fields(self):
        a = self.ds.answers["q_001"]
        self.assertIsInstance(a, OfficialAnswer)
        self.assertEqual(a.type, "number")
        self.assertEqual(a.answer, 1000000)

    def test_has_answers_true_for_train(self):
        self.assertTrue(self.ds.has_answers)

    def test_business_ids(self):
        self.assertSetEqual(set(self.ds.business_ids()), {"biz_a", "biz_b"})

    def test_filter_by_business(self):
        qs = self.ds.filter_questions(business_ids=["biz_a"])
        self.assertEqual(len(qs), 2)
        self.assertTrue(all(q.business_id == "biz_a" for q in qs))

    def test_filter_by_limit(self):
        qs = self.ds.filter_questions(limit=2)
        self.assertEqual(len(qs), 2)

    def test_iter_pairs_no_answer_for_public_test(self):
        with tempfile.TemporaryDirectory() as td:
            ds = _make_dataset(
                Path(td),
                SAMPLE_QUESTIONS,
                None,  # no answers
                split="public_test",
            )
            self.assertFalse(ds.has_answers)
            for q, gt in ds.iter_pairs():
                self.assertIsNone(gt, "public_test must yield None answers")

    def test_validate_returns_no_warnings_for_valid_dataset(self):
        warnings = self.ds.validate()
        self.assertEqual(warnings, [], f"Unexpected warnings: {warnings}")

    def test_validate_warns_on_missing_business_dir(self):
        with tempfile.TemporaryDirectory() as td:
            qs = [
                {"id": "q_x", "business_id": "biz_missing",
                 "question": "?", "as_of_date": "2026-01-01"}
            ]
            ds = _make_dataset(Path(td), qs, [{"id": "q_x", "type": "number", "answer": 0, "alias": []}])
            # Remove the auto-created dir
            import shutil
            shutil.rmtree(ds.root / "data" / "biz_missing")
            warnings = ds.validate()
            self.assertTrue(any("Missing data directory" in w for w in warnings))

    def test_missing_field_raises_value_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "bad_dataset"
            root.mkdir()
            (root / "data").mkdir()
            # Missing 'as_of_date'
            (root / "questions.jsonl").write_text(
                '{"id":"q1","business_id":"b1","question":"?"}\n'
            )
            with self.assertRaises(ValueError):
                OfficialDataset(root).questions  # trigger lazy load

    def test_to_dict_has_no_ground_truth(self):
        """OfficialQuestion.to_dict() must NOT include type or answer."""
        q = self.ds.questions[0]
        d = q.to_dict()
        self.assertNotIn("type", d)
        self.assertNotIn("answer", d)
        self.assertNotIn("alias", d)


# ── Type comparison ───────────────────────────────────────────────────────

class TestNumberComparison(unittest.TestCase):
    def test_exact_integer(self):
        self.assertTrue(_cmp_number(1000000, 1000000))

    def test_float_repr_tolerance(self):
        # 1000000.0 vs 1000000 — only float rounding tolerated (< 0.5)
        self.assertTrue(_cmp_number(1000000.0, 1000000))

    def test_off_by_one_is_wrong(self):
        # "tiền đúng từng đồng" — 1 VND difference is a wrong answer
        self.assertFalse(_cmp_number(1000001, 1000000))

    def test_large_difference_wrong(self):
        self.assertFalse(_cmp_number(1002000, 1000000))

    def test_zero(self):
        self.assertTrue(_cmp_number(0, 0))
        self.assertFalse(_cmp_number(1, 0))

    def test_negative_number(self):
        self.assertTrue(_cmp_number(-500, -500))
        self.assertFalse(_cmp_number(-500, 500))


class TestPercentComparison(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(_cmp_percent(12.50, 12.50))

    def test_within_2dp_tolerance(self):
        # 12.4999 rounds to 12.50, so within 0.005
        self.assertTrue(_cmp_percent(12.4999, 12.50))

    def test_beyond_2dp_tolerance(self):
        self.assertFalse(_cmp_percent(12.51, 12.50))

    def test_zero_percent(self):
        self.assertTrue(_cmp_percent(0.0, 0.0))

    def test_strict_no_half_percent_tolerance(self):
        # The old synthetic benchmark used 0.11 tolerance — official uses 0.005
        self.assertFalse(_cmp_percent(12.60, 12.50))


class TestStringMatching(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(_str_matches("Cà phê sữa", "Cà phê sữa", []))

    def test_case_insensitive(self):
        self.assertTrue(_str_matches("cà phê sữa", "Cà phê sữa", []))
        self.assertTrue(_str_matches("CÀ PHÊ SỮA", "Cà phê sữa", []))

    def test_whitespace_insensitive(self):
        self.assertTrue(_str_matches("Cà phê  sữa", "Cà phê sữa", []))
        self.assertTrue(_str_matches(" Cà phê sữa ", "Cà phê sữa", []))

    def test_alias_match(self):
        self.assertTrue(_str_matches("SP001", "Cà phê sữa", ["SP001"]))

    def test_alias_case_insensitive(self):
        self.assertTrue(_str_matches("sp001", "Cà phê sữa", ["SP001"]))

    def test_no_match_different_string(self):
        self.assertFalse(_str_matches("Trà sữa", "Cà phê sữa", ["SP001"]))


class TestListComparison(unittest.TestCase):
    def test_exact_string_list(self):
        self.assertTrue(_cmp_list(["A", "B", "C"], ["A", "B", "C"], []))

    def test_order_matters(self):
        # Lists are order-sensitive per rulebook §9
        self.assertFalse(_cmp_list(["B", "A"], ["A", "B"], []))

    def test_case_insensitive_elements(self):
        self.assertTrue(_cmp_list(["a", "b"], ["A", "B"], []))

    def test_alias_per_element(self):
        self.assertTrue(
            _cmp_list(["SP001", "SP002"], ["Cà phê sữa", "Trà đào"], [["SP001"], ["SP002"]])
        )

    def test_length_mismatch(self):
        self.assertFalse(_cmp_list(["A"], ["A", "B"], []))
        self.assertFalse(_cmp_list(["A", "B", "C"], ["A", "B"], []))

    def test_numeric_list_elements(self):
        self.assertTrue(_cmp_list([100.0, 200.0], [100, 200], []))

    def test_numeric_exact_requirement(self):
        # Numbers in a list are exact (< 0.5 tolerance)
        self.assertFalse(_cmp_list([101, 200], [100, 200], []))


class TestTableComparison(unittest.TestCase):
    def _gt(self, rows, columns=None):
        return {"columns": columns or ["name", "value"], "rows": rows}

    def test_exact_match_single_row(self):
        pred = {"columns": ["name", "value"], "rows": [["Alice", 100]]}
        gt = self._gt([["Alice", 100]])
        self.assertTrue(_cmp_table(pred, gt, []))

    def test_row_order_independent(self):
        pred = {"columns": ["name", "value"], "rows": [["Bob", 200], ["Alice", 100]]}
        gt = self._gt([["Alice", 100], ["Bob", 200]])
        self.assertTrue(_cmp_table(pred, gt, []))

    def test_first_column_alias(self):
        pred = {"columns": ["khach", "so_no"], "rows": [["KH001", 50000]]}
        gt = self._gt([["Nguyễn Văn A", 50000]], columns=["khach", "so_no"])
        alias = [["KH001"]]
        self.assertTrue(_cmp_table(pred, gt, alias))

    def test_wrong_value_fails(self):
        pred = {"columns": ["name", "value"], "rows": [["Alice", 999]]}
        gt = self._gt([["Alice", 100]])
        self.assertFalse(_cmp_table(pred, gt, []))

    def test_wrong_row_count_fails(self):
        pred = {"columns": ["name", "value"], "rows": [["Alice", 100], ["Bob", 200]]}
        gt = self._gt([["Alice", 100]])
        self.assertFalse(_cmp_table(pred, gt, []))


# ── PA scoring ────────────────────────────────────────────────────────────

class TestPaScoring(unittest.TestCase):

    def _gt(self, qid, qtype, answer, alias=None):
        return OfficialAnswer(id=qid, type=qtype, answer=answer, alias=alias or [])

    def _pred(self, qid, ptype, answer=None, biz=None):
        p = {"id": qid, "type": ptype}
        if answer is not None:
            p["answer"] = answer
        if biz:
            p["business_id"] = biz
        return p

    def test_all_correct_pa_1(self):
        gts = {
            "q1": self._gt("q1", "number", 100),
            "q2": self._gt("q2", "number", 200),
        }
        preds = [
            self._pred("q1", "number", 100),
            self._pred("q2", "number", 200),
        ]
        result = compute_pa_score(preds, gts)
        self.assertEqual(result["pa"], 1.0)
        self.assertEqual(result["correct"], 2)
        self.assertEqual(result["incorrect"], 0)

    def test_all_wrong_pa_minus_1(self):
        gts = {"q1": self._gt("q1", "number", 100)}
        preds = [self._pred("q1", "number", 999)]
        result = compute_pa_score(preds, gts)
        self.assertEqual(result["pa"], -1.0)
        self.assertEqual(result["incorrect"], 1)

    def test_abstain_pa_0(self):
        gts = {"q1": self._gt("q1", "number", 100)}
        preds = [self._pred("q1", "abstain")]
        result = compute_pa_score(preds, gts)
        self.assertEqual(result["pa"], 0.0)
        self.assertEqual(result["abstain"], 1)
        self.assertEqual(result["correct"], 0)
        self.assertEqual(result["incorrect"], 0)

    def test_pa_formula(self):
        # 3 correct, 1 wrong, 1 abstain → PA = (3 - 1) / 5 = 0.4
        gts = {f"q{i}": self._gt(f"q{i}", "number", 100) for i in range(5)}
        preds = [
            self._pred("q0", "number", 100),
            self._pred("q1", "number", 100),
            self._pred("q2", "number", 100),
            self._pred("q3", "number", 999),  # wrong
            self._pred("q4", "abstain"),       # abstain
        ]
        result = compute_pa_score(preds, gts)
        self.assertAlmostEqual(result["pa"], 0.4, places=4)

    def test_unanswerable_correct_when_predicted(self):
        gts = {"q1": self._gt("q1", "unanswerable", None)}
        preds = [self._pred("q1", "unanswerable")]
        result = compute_pa_score(preds, gts)
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["pa"], 1.0)

    def test_unanswerable_wrong_when_answered(self):
        gts = {"q1": self._gt("q1", "unanswerable", None)}
        preds = [self._pred("q1", "number", 999)]
        result = compute_pa_score(preds, gts)
        self.assertEqual(result["incorrect"], 1)
        self.assertEqual(result["pa"], -1.0)

    def test_unanswerable_abstain_scores_zero(self):
        gts = {"q1": self._gt("q1", "unanswerable", None)}
        preds = [self._pred("q1", "abstain")]
        result = compute_pa_score(preds, gts)
        self.assertEqual(result["abstain"], 1)
        self.assertEqual(result["pa"], 0.0)

    def test_missing_prediction_treated_as_abstain(self):
        gts = {"q1": self._gt("q1", "number", 100)}
        preds = []  # no prediction for q1
        result = compute_pa_score(preds, gts)
        self.assertEqual(result["abstain"], 1)
        self.assertEqual(result["missing_predictions"], 1)
        self.assertEqual(result["pa"], 0.0)

    def test_by_type_breakdown(self):
        gts = {
            "q1": self._gt("q1", "number", 100),
            "q2": self._gt("q2", "string", "Alpha"),
        }
        preds = [
            self._pred("q1", "number", 100),
            self._pred("q2", "string", "Beta"),  # wrong
        ]
        result = compute_pa_score(preds, gts)
        self.assertIn("number", result["by_type"])
        self.assertIn("string", result["by_type"])
        self.assertEqual(result["by_type"]["number"]["correct"], 1)
        self.assertEqual(result["by_type"]["string"]["incorrect"], 1)

    def test_by_business_breakdown(self):
        gts = {
            "q1": self._gt("q1", "number", 100),
            "q2": self._gt("q2", "number", 200),
        }
        preds = [
            self._pred("q1", "number", 100, biz="biz_a"),
            self._pred("q2", "number", 999, biz="biz_b"),
        ]
        result = compute_pa_score(preds, gts)
        self.assertIn("biz_a", result["by_business"])
        self.assertEqual(result["by_business"]["biz_a"]["correct"], 1)
        self.assertEqual(result["by_business"]["biz_b"]["incorrect"], 1)

    def test_total_zero_no_crash(self):
        result = compute_pa_score([], {})
        self.assertEqual(result["pa"], 0.0)
        self.assertEqual(result["total"], 0)

    def test_partial_coverage_all_wrong_gives_negative_pa(self):
        # 3 answered (all wrong) + 7 abstain out of 10 total.
        # PA = (0 − 3) / 10 = −0.3, NOT 0.
        # This pins down that partial coverage does NOT guarantee non-negative PA.
        gts = {f"q{i}": self._gt(f"q{i}", "number", 100) for i in range(10)}
        preds = [
            self._pred("q0", "number", 999),
            self._pred("q1", "number", 999),
            self._pred("q2", "number", 999),
            # q3–q9 have no prediction → treated as abstain
        ]
        result = compute_pa_score(preds, gts)
        self.assertEqual(result["correct"], 0)
        self.assertEqual(result["incorrect"], 3)
        self.assertEqual(result["abstain"], 7)
        self.assertAlmostEqual(result["pa"], -0.3, places=4)

    def test_coverage_maximum_pa_equals_coverage_rate(self):
        # 3 answered (all correct) + 7 abstain out of 10 total.
        # PA = (3 − 0) / 10 = 0.3 — this is the MAXIMUM for 30% coverage.
        gts = {f"q{i}": self._gt(f"q{i}", "number", 100) for i in range(10)}
        preds = [
            self._pred("q0", "number", 100),
            self._pred("q1", "number", 100),
            self._pred("q2", "number", 100),
            # q3–q9 abstain
        ]
        result = compute_pa_score(preds, gts)
        self.assertEqual(result["correct"], 3)
        self.assertEqual(result["incorrect"], 0)
        self.assertEqual(result["abstain"], 7)
        self.assertAlmostEqual(result["pa"], 0.3, places=4)

    def test_accuracy_metric_is_correct_over_total_not_over_answered(self):
        # 1 correct answer out of 10 total (9 abstain).
        # accuracy = 1/10 = 0.1, NOT 1/1 = 1.0.
        # accuracy in compute_pa_score always uses total as denominator.
        gts = {f"q{i}": self._gt(f"q{i}", "number", 100) for i in range(10)}
        preds = [self._pred("q0", "number", 100)]
        result = compute_pa_score(preds, gts)
        self.assertEqual(result["correct"], 1)
        self.assertAlmostEqual(result["accuracy"], 0.1, places=4)
        # PA and accuracy share the same denominator (total)
        self.assertAlmostEqual(result["pa"], result["accuracy"], places=4)


# ── answers_match integration ─────────────────────────────────────────────

class TestAnswersMatch(unittest.TestCase):

    def _gt(self, qtype, answer, alias=None):
        return OfficialAnswer(id="x", type=qtype, answer=answer, alias=alias or [])

    def test_number_exact(self):
        self.assertTrue(answers_match(5000000, "number", self._gt("number", 5000000)))

    def test_number_off_by_one_fails(self):
        self.assertFalse(answers_match(5000001, "number", self._gt("number", 5000000)))

    def test_percent_2dp(self):
        self.assertTrue(answers_match(12.50, "percent", self._gt("percent", 12.50)))
        self.assertFalse(answers_match(12.51, "percent", self._gt("percent", 12.50)))

    def test_string_with_alias(self):
        self.assertTrue(
            answers_match("SP001", "string", self._gt("string", "Cà phê sữa", ["SP001"]))
        )

    def test_abstain_on_answerable_is_wrong(self):
        self.assertFalse(answers_match(None, "abstain", self._gt("number", 100)))

    def test_unanswerable_correct(self):
        self.assertTrue(answers_match(None, "unanswerable", self._gt("unanswerable", None)))

    def test_wrong_type_fails(self):
        self.assertFalse(answers_match(100, "number", self._gt("percent", 100)))

    def test_boolean_true(self):
        self.assertTrue(answers_match(True, "boolean", self._gt("boolean", True)))

    def test_boolean_false(self):
        self.assertTrue(answers_match(False, "boolean", self._gt("boolean", False)))

    def test_date_exact(self):
        self.assertTrue(answers_match("2026-05-01", "date", self._gt("date", "2026-05-01")))
        self.assertFalse(answers_match("2026-05-02", "date", self._gt("date", "2026-05-01")))

    def test_list_ordered(self):
        self.assertTrue(
            answers_match(["A", "B"], "list", self._gt("list", ["A", "B"]))
        )
        self.assertFalse(
            answers_match(["B", "A"], "list", self._gt("list", ["A", "B"]))
        )

    def test_list_alias(self):
        self.assertTrue(
            answers_match(
                ["SP001", "SP002"],
                "list",
                self._gt("list", ["Cà phê sữa", "Trà đào"], [["SP001"], ["SP002"]]),
            )
        )


# ── Split separation ──────────────────────────────────────────────────────

class TestSplitSeparation(unittest.TestCase):
    """Ground truth must never be accessible via OfficialQuestion.to_dict()."""

    def test_question_to_dict_has_no_ground_truth_keys(self):
        q = OfficialQuestion(
            id="q1",
            business_id="biz_x",
            question="Revenue?",
            as_of_date="2026-01-01",
        )
        d = q.to_dict()
        for forbidden in ("type", "answer", "alias", "oracle_sql", "gt"):
            self.assertNotIn(forbidden, d, f"Key {forbidden!r} must not appear in question dict")

    def test_public_test_dataset_yields_no_answers(self):
        with tempfile.TemporaryDirectory() as td:
            # Create a "public_test" dataset with NO answers.jsonl
            qs = [
                {"id": "q1", "business_id": "biz_x",
                 "question": "?", "as_of_date": "2026-01-01"},
            ]
            ds = _make_dataset(Path(td), qs, None, split="public_test")
            self.assertEqual(ds.answers, {})
            for _, gt in ds.iter_pairs():
                self.assertIsNone(gt)

    def test_train_answers_not_in_question_iteration(self):
        with tempfile.TemporaryDirectory() as td:
            qs = [
                {"id": "q1", "business_id": "biz_x",
                 "question": "Revenue?", "as_of_date": "2026-01-01"},
            ]
            answers = [{"id": "q1", "type": "number", "answer": 42, "alias": []}]
            ds = _make_dataset(Path(td), qs, answers)
            for q, _gt in ds.iter_pairs():
                # The question object (which goes to the agent) has no answer
                d = q.to_dict()
                self.assertNotIn("answer", d)
                self.assertNotIn("type", d)


# ── End-to-end with mock model ────────────────────────────────────────────

class TestOfficialEvalE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        # We need a real business dir with actual data files for the agent
        from benchmark.create_benchmark import build_benchmark
        bm = cls.root / "bm"
        build_benchmark(bm)
        # Reuse the benchmark's biz_cafe as a fake official dataset
        import shutil
        official_root = cls.root / "mock_official"
        official_root.mkdir()
        shutil.copytree(bm / "data", official_root / "data")
        shutil.copy(bm / "calendar.csv", official_root / "calendar.csv")
        shutil.copy(bm / "rulebook.md", official_root / "rulebook.md")
        # Create questions from the benchmark
        with (bm / "questions.jsonl").open(encoding="utf-8") as f:
            qs = [json.loads(l) for l in f if l.strip()][:5]
        with (official_root / "questions.jsonl").open("w", encoding="utf-8") as f:
            for q in qs:
                f.write(json.dumps(q, ensure_ascii=False) + "\n")
        # Create answers.jsonl from ground_truth.jsonl
        with (bm / "ground_truth.jsonl").open(encoding="utf-8") as f:
            gt = {json.loads(l)["id"]: json.loads(l) for l in f if l.strip()}
        with (official_root / "answers.jsonl").open("w", encoding="utf-8") as f:
            for q in qs:
                g = gt[q["id"]]
                entry = {
                    "id": g["id"],
                    "type": g["type"],
                    "answer": g.get("answer"),
                    "alias": [],
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        cls.official_root = official_root

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_e2e_mock_model_runs_without_error(self):
        from eval.eval_official import MockModel, run_official
        ds = OfficialDataset(self.official_root, split="mock_train")
        model = MockModel()
        out = self.root / "e2e_out"
        summary = run_official(ds, model, out, max_attempts=1, backend_name="mock")
        self.assertEqual(summary["total_questions"], 5)
        self.assertTrue((out / "submission.jsonl").is_file())
        self.assertTrue((out / "diagnostics.jsonl").is_file())
        self.assertTrue((out / "summary.json").is_file())

    def test_submission_jsonl_has_valid_format(self):
        from eval.eval_official import MockModel, run_official
        ds = OfficialDataset(self.official_root, split="mock_train")
        model = MockModel()
        out = self.root / "e2e_submission"
        run_official(ds, model, out, max_attempts=1, backend_name="mock")
        with (out / "submission.jsonl").open(encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(rows), 5)
        for row in rows:
            self.assertIn("id", row)
            self.assertIn("type", row)
            # Ground truth must NOT appear in submission
            self.assertNotIn("gt_answer", row)

    def test_mock_model_abstain_pa_zero(self):
        from eval.eval_official import MockModel, run_official
        ds = OfficialDataset(self.official_root, split="mock_train")
        model = MockModel()
        out = self.root / "e2e_pa"
        summary = run_official(ds, model, out, max_attempts=1, backend_name="mock")
        # Mock model always abstains → PA = 0 (some questions are unanswerable)
        self.assertIn("pa", summary)
        # Correct == 0 (abstain ≠ correct), incorrect == 0
        self.assertEqual(summary["incorrect"], 0)
        self.assertEqual(summary["correct"], 0)

    def test_predict_only_skips_scoring(self):
        from eval.eval_official import MockModel, run_official
        ds = OfficialDataset(self.official_root, split="mock_train")
        model = MockModel()
        out = self.root / "e2e_predict_only"
        summary = run_official(ds, model, out, max_attempts=1,
                               backend_name="mock", predict_only=True)
        self.assertNotIn("pa", summary)
        self.assertNotIn("correct", summary)


if __name__ == "__main__":
    unittest.main()
