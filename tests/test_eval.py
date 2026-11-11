"""Tests for the evaluation runner, answer-comparison logic, and LLM backends."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from benchmark.create_benchmark import build_benchmark, QUESTIONS
from eval.evaluate import MockModel, evaluate, _answers_match, _sql_succeeded
from src.agent import normalize_date_hints, json_object


class AnswerMatchTests(unittest.TestCase):
    def test_number_exact(self):
        self.assertTrue(_answers_match(1000000, 1000000, "number"))

    def test_number_tolerance(self):
        self.assertTrue(_answers_match(1000001, 1000000, "number"))
        self.assertFalse(_answers_match(1002000, 1000000, "number"))

    def test_number_zero(self):
        self.assertTrue(_answers_match(0, 0, "number"))
        self.assertFalse(_answers_match(1, 0, "number"))

    def test_percent(self):
        self.assertTrue(_answers_match(35.5, 35.5, "percent"))
        self.assertTrue(_answers_match(35.55, 35.5, "percent"))
        self.assertFalse(_answers_match(35.7, 35.5, "percent"))

    def test_string_case_insensitive(self):
        self.assertTrue(_answers_match("Cà phê đen", "cà phê đen", "string"))
        self.assertTrue(_answers_match("  Cà phê  ", "Cà phê", "string"))
        self.assertFalse(_answers_match("Trà sữa", "Cà phê đen", "string"))

    def test_boolean(self):
        self.assertTrue(_answers_match(True, True, "boolean"))
        self.assertFalse(_answers_match(True, False, "boolean"))
        self.assertTrue(_answers_match(False, False, "boolean"))

    def test_list_order_insensitive(self):
        self.assertTrue(_answers_match(["B", "A"], ["A", "B"], "list"))
        self.assertFalse(_answers_match(["A", "C"], ["A", "B"], "list"))

    def test_list_case_insensitive(self):
        self.assertTrue(_answers_match(["áo"], ["Áo"], "list"))

    def test_table_match(self):
        pred = [{"loai": "Điện thoại", "total": "120000000"}]
        gt = [{"loai": "Điện thoại", "total": "120000000"}]
        self.assertTrue(_answers_match(pred, gt, "table"))

    def test_table_mismatch_row_count(self):
        pred = [{"x": "1"}, {"x": "2"}]
        gt = [{"x": "1"}]
        self.assertFalse(_answers_match(pred, gt, "table"))

    def test_unanswerable_always_match(self):
        self.assertTrue(_answers_match(None, None, "unanswerable"))
        self.assertTrue(_answers_match("anything", None, "unanswerable"))

    def test_none_pred_no_match(self):
        self.assertFalse(_answers_match(None, 1000, "number"))


class DateNormalizationTests(unittest.TestCase):
    def test_dd_mm_no_year(self):
        result = normalize_date_hints("ngày 3/3", "2026-05-01")
        self.assertIn("2026-03-03", result)

    def test_dd_mm_yyyy(self):
        result = normalize_date_hints("ngày 15/01/2026", "2026-05-01")
        self.assertIn("2026-01-15", result)

    def test_month_only(self):
        result = normalize_date_hints("tháng 2", "2026-05-01")
        self.assertIn("tháng 2", result)

    def test_no_match(self):
        text = "Doanh thu tháng Hai là bao nhiêu?"
        result = normalize_date_hints(text, "2026-05-01")
        self.assertEqual(result, text)


class JsonObjectParsingTests(unittest.TestCase):
    def test_plain_json(self):
        obj = json_object('{"type":"number","sql":"SELECT 1"}')
        self.assertEqual(obj["type"], "number")

    def test_with_thinking_tags(self):
        obj = json_object('<think>some thought</think>{"type":"abstain"}')
        self.assertEqual(obj["type"], "abstain")

    def test_with_code_fence(self):
        obj = json_object('```json\n{"type":"string","sql":"SELECT x"}\n```')
        self.assertEqual(obj["type"], "string")

    def test_embedded_in_text(self):
        obj = json_object('Here is my answer: {"type":"number","sql":"SELECT 1"}')
        self.assertEqual(obj["type"], "number")

    def test_raises_on_no_json(self):
        with self.assertRaises(ValueError):
            json_object("Just plain text")


class EvaluatorPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.benchmark_root = Path(cls._tmp.name) / "benchmark"
        build_benchmark(cls.benchmark_root)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_mock_model_abstain_baseline(self):
        """MockModel returns abstain for everything; confirms pipeline runs end-to-end."""
        out_dir = Path(self._tmp.name) / "eval_out_mock"
        model = MockModel()
        summary = evaluate(self.benchmark_root, model, out_dir)

        self.assertEqual(summary["total_questions"], len(QUESTIONS))
        self.assertAlmostEqual(summary["abstain_rate"], 1.0, places=1)
        self.assertIn("accuracy", summary)
        self.assertTrue((out_dir / "summary.json").is_file())
        self.assertTrue((out_dir / "per_question.jsonl").is_file())

    def test_mock_model_unanswerable_correct(self):
        """MockModel abstains on everything; unanswerable questions should NOT count as correct."""
        out_dir = Path(self._tmp.name) / "eval_out_unans"
        model = MockModel()
        summary = evaluate(self.benchmark_root, model, out_dir)
        # abstain != unanswerable, so unanswerable questions are not scored correct
        self.assertEqual(summary["accuracy"], 0.0)

    def test_oracle_model_perfect_score(self):
        """A model that returns the exact oracle SQL should score 100% on answerable questions."""
        from benchmark.create_benchmark import QUESTIONS as ALL_Q

        # Build a response list: for each question, return the oracle answer or unanswerable
        with (self.benchmark_root / "ground_truth.jsonl").open(encoding="utf-8") as f:
            gt_map = {json.loads(l)["id"]: json.loads(l) for l in f if l.strip()}

        responses = []
        for q in ALL_Q:
            gt = gt_map[q["id"]]
            oracle_sql = q.get("oracle_sql")
            qtype = q["type"]
            if qtype == "unanswerable" or oracle_sql is None:
                responses.append('{"type":"unanswerable","reason":"missing data"}')
            else:
                responses.append(json.dumps({"type": qtype, "sql": oracle_sql}, ensure_ascii=False))

        from src.llm import MockLLM
        model = MockLLM(responses)
        out_dir = Path(self._tmp.name) / "eval_out_oracle"
        summary = evaluate(self.benchmark_root, model, out_dir)

        self.assertGreater(summary["accuracy"], 0.90,
                           f"Oracle model accuracy should be >90%, got {summary['accuracy']:.1%}")

    def test_per_question_jsonl_has_all_fields(self):
        out_dir = Path(self._tmp.name) / "eval_out_fields"
        evaluate(self.benchmark_root, MockModel(), out_dir)
        with (out_dir / "per_question.jsonl").open(encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
        for row in rows:
            self.assertIn("id", row)
            self.assertIn("gt_type", row)
            self.assertIn("pred_type", row)
            self.assertIn("correct", row)
            self.assertIn("elapsed_ms", row)

    def test_summary_note_mentions_synthetic(self):
        out_dir = Path(self._tmp.name) / "eval_out_note"
        summary = evaluate(self.benchmark_root, MockModel(), out_dir)
        self.assertIn("synthetic", summary["note"].lower())


class ReliabilityTests(unittest.TestCase):
    """Tests for reliability improvements in Agent and ingestion."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name) / "data"
        build_benchmark(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_agent_handles_bad_json_and_retries(self):
        from src.agent import Agent
        from src.llm import MockLLM
        # First response: bad JSON; second: valid abstain
        model = MockLLM(["not json at all", '{"type":"abstain"}'])
        agent = Agent(model, self.root)
        try:
            q = {
                "id": "reliability_01",
                "business_id": "biz_cafe",
                "question": "Test?",
                "as_of_date": "2026-05-01",
            }
            answer, log = agent.solve(q)
            self.assertIn(answer["type"], ("abstain", "unanswerable"))
        finally:
            agent.close()

    def test_agent_invalid_business_id_raises(self):
        from src.agent import Agent
        from src.llm import MockLLM
        model = MockLLM(['{"type":"abstain"}'])
        agent = Agent(model, self.root)
        try:
            q = {
                "id": "safety_01",
                "business_id": "../../etc/passwd",
                "question": "Test?",
                "as_of_date": "2026-05-01",
            }
            answer, log = agent.solve(q)
            # Should abstain safely, not crash
            self.assertEqual(answer["type"], "abstain")
        finally:
            agent.close()

    def test_schema_text_has_cast_hint(self):
        from src.ingestion import BusinessDB
        db = BusinessDB(
            self.root / "data" / "biz_cafe",
            self.root / "calendar.csv",
        )
        try:
            schema = db.schema_text()
            self.assertIn("CAST", schema)
        finally:
            db.close()


# ─── SQL success helper ───────────────────────────────────────────────────

class SqlSucceededTests(unittest.TestCase):
    def test_single_success(self):
        # Single attempt, output is a list-of-tuples (rows) → success
        self.assertTrue(_sql_succeeded("SELECT 1", [(1,)]))

    def test_single_failure(self):
        # Single attempt, output is an error string → failure
        self.assertFalse(_sql_succeeded("SELECT bad", "no such column"))

    def test_no_code(self):
        self.assertFalse(_sql_succeeded(None, None))

    def test_multi_attempt_one_success(self):
        # Multiple attempts: second attempt succeeded
        self.assertTrue(_sql_succeeded(
            ["SELECT bad", "SELECT 1"],
            ["no such column", [(1,)]],
        ))

    def test_multi_attempt_all_fail(self):
        self.assertFalse(_sql_succeeded(
            ["SELECT bad", "SELECT worse"],
            ["error1", "error2"],
        ))


# ─── --limit and --backend features ──────────────────────────────────────

class EvaluateLimitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.benchmark_root = Path(cls._tmp.name) / "benchmark"
        build_benchmark(cls.benchmark_root)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_limit_reduces_question_count(self):
        out = Path(self._tmp.name) / "eval_limit5"
        summary = evaluate(self.benchmark_root, MockModel(), out, limit=5)
        self.assertEqual(summary["total_questions"], 5)

    def test_limit_zero_returns_empty(self):
        out = Path(self._tmp.name) / "eval_limit0"
        summary = evaluate(self.benchmark_root, MockModel(), out, limit=0)
        self.assertEqual(summary["total_questions"], 0)
        self.assertEqual(summary["accuracy"], 0.0)

    def test_limit_larger_than_dataset_clamps(self):
        out = Path(self._tmp.name) / "eval_limit9999"
        summary = evaluate(self.benchmark_root, MockModel(), out, limit=9999)
        self.assertEqual(summary["total_questions"], len(QUESTIONS))

    def test_backend_name_in_summary(self):
        out = Path(self._tmp.name) / "eval_backend_name"
        summary = evaluate(self.benchmark_root, MockModel(), out,
                           limit=3, backend_name="mock")
        self.assertEqual(summary["backend"], "mock")

    def test_per_question_count_matches_limit(self):
        out = Path(self._tmp.name) / "eval_pq_limit"
        evaluate(self.benchmark_root, MockModel(), out, limit=7)
        with (out / "per_question.jsonl").open(encoding="utf-8") as f:
            rows = [l for l in f if l.strip()]
        self.assertEqual(len(rows), 7)

    def test_summary_has_unanswerable_rate(self):
        out = Path(self._tmp.name) / "eval_unans_rate"
        summary = evaluate(self.benchmark_root, MockModel(), out, limit=5)
        self.assertIn("unanswerable_rate", summary)

    def test_device_info_included_when_model_has_property(self):
        class FakeModelWithDeviceInfo:
            device_info = {"devices": ["cuda:0"], "device_map": "auto"}

            def generate(self, s, u):
                return '{"type":"abstain"}', None

        out = Path(self._tmp.name) / "eval_device_info"
        summary = evaluate(self.benchmark_root, FakeModelWithDeviceInfo(), out, limit=2)
        self.assertIn("device_info", summary)
        self.assertEqual(summary["device_info"]["devices"], ["cuda:0"])

    def test_device_info_absent_when_model_lacks_property(self):
        out = Path(self._tmp.name) / "eval_no_device_info"
        summary = evaluate(self.benchmark_root, MockModel(), out, limit=2)
        self.assertNotIn("device_info", summary)


# ─── HFTransformers backend (mocked; no weights downloaded) ──────────────

class TransformersBackendTests(unittest.TestCase):
    """Unit tests for HFTransformers using mocked torch/transformers.

    ``transformers`` is not installed on this dev machine (it IS on the GPU
    server).  We inject a stub module via ``sys.modules`` so that the lazy
    ``from transformers import ...`` inside HFTransformers.__init__ resolves
    to our mocks without requiring the real package.
    ``torch`` IS installed here, so we use real tensors for realistic slicing.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.fake_path = self._tmp.name   # real directory → passes Path.is_dir()

    def tearDown(self):
        self._tmp.cleanup()

    # ── mock factories ────────────────────────────────────────────────────

    def _build_mocks(self, decode_responses: list[str] | None = None):
        """Return (mock_tok, mock_model) with side-effects wired up."""
        import torch
        response_iter = iter(decode_responses or ['{"type":"abstain"}'])

        mock_tok = MagicMock()
        mock_tok.eos_token_id = 2

        def _apply_chat_template(*a, **kw):
            return {
                "input_ids": torch.tensor([[10, 20, 30]]),
                "attention_mask": torch.tensor([[1, 1, 1]]),
            }

        def _decode(tokens, **kw):
            try:
                return next(response_iter)
            except StopIteration:
                return '{"type":"abstain"}'

        mock_tok.apply_chat_template.side_effect = _apply_chat_template
        mock_tok.decode.side_effect = _decode

        mock_model = MagicMock()
        mock_param = MagicMock()
        mock_param.device = "cpu"
        mock_model.parameters.return_value = [mock_param]
        # First 3 tokens are the echoed prompt; 4 and 5 are the new tokens.
        mock_model.generate.return_value = torch.tensor([[10, 20, 30, 40, 50]])
        mock_model.hf_device_map = {
            "model.layers.0": "cuda:0",
            "model.layers.1": "cuda:1",
        }

        return mock_tok, mock_model

    def _stub_tf(self, mock_tok, mock_model):
        """Return a types.ModuleType stub for 'transformers' + sys.modules entry."""
        import types
        stub = types.ModuleType("transformers")
        stub.AutoTokenizer = MagicMock()
        stub.AutoTokenizer.from_pretrained.return_value = mock_tok
        stub.AutoModelForCausalLM = MagicMock()
        stub.AutoModelForCausalLM.from_pretrained.return_value = mock_model
        return stub

    def _make_backend(self, decode_responses: list[str] | None = None):
        """Instantiate HFTransformers with mocked transformers/torch."""
        import sys
        from src.llm import HFTransformers
        mock_tok, mock_model = self._build_mocks(decode_responses)
        stub = self._stub_tf(mock_tok, mock_model)
        with patch.dict(sys.modules, {"transformers": stub}):
            backend = HFTransformers(self.fake_path)
        return backend, mock_tok, mock_model, stub

    # ── construction ─────────────────────────────────────────────────────

    def test_raises_file_not_found_without_weights(self):
        # Path check happens before the lazy import, so no stub needed.
        from src.llm import HFTransformers
        with self.assertRaises(FileNotFoundError):
            HFTransformers("/absolute/nonexistent/path/xyzzy_12345")

    def test_instantiation_calls_from_pretrained(self):
        import sys
        from src.llm import HFTransformers
        mock_tok, mock_model = self._build_mocks()
        stub = self._stub_tf(mock_tok, mock_model)
        with patch.dict(sys.modules, {"transformers": stub}):
            HFTransformers(self.fake_path)
        stub.AutoTokenizer.from_pretrained.assert_called_once()
        stub.AutoModelForCausalLM.from_pretrained.assert_called_once()

    def test_model_set_to_eval_mode(self):
        import sys
        from src.llm import HFTransformers
        mock_tok, mock_model = self._build_mocks()
        stub = self._stub_tf(mock_tok, mock_model)
        with patch.dict(sys.modules, {"transformers": stub}):
            HFTransformers(self.fake_path)
        mock_model.eval.assert_called()

    def test_offline_env_vars_set(self):
        import os, sys
        from src.llm import HFTransformers
        mock_tok, mock_model = self._build_mocks()
        stub = self._stub_tf(mock_tok, mock_model)
        with patch.dict(sys.modules, {"transformers": stub}):
            HFTransformers(self.fake_path)
        self.assertEqual(os.environ.get("HF_HUB_OFFLINE"), "1")
        self.assertEqual(os.environ.get("TRANSFORMERS_OFFLINE"), "1")

    # ── generate() interface ─────────────────────────────────────────────

    def test_generate_returns_tuple_str_none(self):
        backend, _, _, _ = self._make_backend(['{"type":"abstain"}'])
        text, thinking = backend.generate("sys", "user")
        self.assertIsInstance(text, str)
        self.assertIsNone(thinking)

    def test_apply_chat_template_called_with_return_dict(self):
        backend, mock_tok, _, _ = self._make_backend()
        backend.generate("sys", "user")
        kw = mock_tok.apply_chat_template.call_args[1]
        self.assertTrue(kw.get("return_dict"))
        self.assertEqual(kw.get("return_tensors"), "pt")
        self.assertTrue(kw.get("add_generation_prompt"))

    def test_attention_mask_passed_to_model_generate(self):
        backend, _, mock_model, _ = self._make_backend()
        backend.generate("sys", "user")
        kw = mock_model.generate.call_args[1]
        self.assertIn("attention_mask", kw)

    def test_do_sample_false_for_determinism(self):
        backend, _, mock_model, _ = self._make_backend()
        backend.generate("sys", "user")
        kw = mock_model.generate.call_args[1]
        self.assertIs(kw.get("do_sample"), False)

    def test_only_new_tokens_decoded(self):
        """Decoder must NOT receive the echoed prompt tokens (first 3 here)."""
        import torch
        backend, mock_tok, mock_model, _ = self._make_backend()
        mock_model.generate.return_value = torch.tensor([[10, 20, 30, 40, 50]])
        backend.generate("sys", "user")
        decoded_tokens = mock_tok.decode.call_args[0][0]
        # apply_chat_template returned prompt of length 3; new tokens = [40, 50]
        self.assertEqual(len(decoded_tokens), 2)

    def test_thinking_tags_returned_as_second_element(self):
        response = '<think>my reasoning</think>{"type":"number","sql":"SELECT 1"}'
        backend, _, _, _ = self._make_backend([response])
        text, thinking = backend.generate("sys", "user")
        self.assertEqual(thinking, "my reasoning")
        self.assertIn("<think>", text)

    def test_no_thinking_tag_returns_none(self):
        backend, _, _, _ = self._make_backend(['{"type":"abstain"}'])
        _, thinking = backend.generate("sys", "user")
        self.assertIsNone(thinking)

    def test_generate_called_with_max_new_tokens(self):
        backend, _, mock_model, _ = self._make_backend()
        backend.generate("sys", "user")
        kw = mock_model.generate.call_args[1]
        self.assertIn("max_new_tokens", kw)
        self.assertEqual(kw["max_new_tokens"], backend.max_new_tokens)

    # ── device_info ──────────────────────────────────────────────────────

    def test_device_info_reports_devices(self):
        backend, _, _, _ = self._make_backend()
        info = backend.device_info
        self.assertIn("devices", info)
        self.assertIn("device_map", info)

    def test_device_info_detects_cpu_offload(self):
        import sys
        from src.llm import HFTransformers
        mock_tok, mock_model = self._build_mocks()
        mock_model.hf_device_map = {
            "model.layers.0": "cuda:0",
            "model.layers.1": "cpu",
            "model.layers.2": "cpu",
        }
        stub = self._stub_tf(mock_tok, mock_model)
        with patch.dict(sys.modules, {"transformers": stub}):
            backend = HFTransformers(self.fake_path)
        info = backend.device_info
        self.assertTrue(info.get("cpu_offloading"))
        self.assertEqual(info.get("cpu_offloaded_layers"), 2)

    def test_device_info_no_cpu_offload_when_all_gpu(self):
        backend, _, _, _ = self._make_backend()  # hf_device_map → only cuda:0 and cuda:1
        info = backend.device_info
        self.assertNotIn("cpu_offloading", info)

    def test_device_info_fallback_when_no_hf_device_map(self):
        """When hf_device_map is None/absent, device_info uses parameters() fallback."""
        import sys
        from src.llm import HFTransformers
        mock_tok, mock_model = self._build_mocks()
        mock_model.hf_device_map = None          # falsy → triggers fallback branch
        stub = self._stub_tf(mock_tok, mock_model)
        with patch.dict(sys.modules, {"transformers": stub}):
            backend = HFTransformers(self.fake_path)
        info = backend.device_info
        self.assertIn("devices", info)

    # ── get_model factory ─────────────────────────────────────────────────

    def test_get_model_transformers_returns_hf_instance(self):
        import sys
        from src.llm import get_model, HFTransformers
        mock_tok, mock_model = self._build_mocks()
        stub = self._stub_tf(mock_tok, mock_model)
        with patch.dict(sys.modules, {"transformers": stub}):
            backend = get_model(self.fake_path, backend="transformers")
        self.assertIsInstance(backend, HFTransformers)

    def test_get_model_unknown_backend_raises(self):
        from src.llm import get_model
        with self.assertRaises(ValueError):
            get_model(self.fake_path, backend="unknown_backend_xyz")

    # ── agent integration with HFTransformers ────────────────────────────

    def test_agent_uses_hf_backend_end_to_end(self):
        """Agent.solve() works with an HFTransformers-backed mock (no real model)."""
        import sys
        from src.agent import Agent
        from src.llm import HFTransformers

        tmp = tempfile.TemporaryDirectory()
        broot = Path(tmp.name) / "data"
        build_benchmark(broot)

        try:
            mock_tok, mock_model = self._build_mocks([
                '{"type":"number","sql":"SELECT SUM(CAST(doanh_thu AS INTEGER)) FROM \\"sales\\""}',
                '{"type":"abstain"}',
            ])
            stub = self._stub_tf(mock_tok, mock_model)
            with patch.dict(sys.modules, {"transformers": stub}):
                hf_backend = HFTransformers(self.fake_path)

            agent = Agent(hf_backend, broot)
            try:
                q = {
                    "id": "hf_e2e_01",
                    "business_id": "biz_cafe",
                    "question": "Tổng doanh thu?",
                    "as_of_date": "2026-05-01",
                }
                answer, log = agent.solve(q)
                self.assertIn(answer["type"], {"number", "abstain", "unanswerable"})
                self.assertIn("elapsed_ms", log)
                self.assertIsNotNone(log["answer"])
            finally:
                agent.close()
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
