import gc
import json
import sqlite3
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

from src.agent import Agent
from src.ingestion import BusinessDB
from src.predict import run
from scripts.create_demo_data import create_demo


class FakeModel:
    """Offline TEST DOUBLE: not part of the competition's inference pipeline."""
    def __init__(self, responses):
        self.responses = iter(responses)
    def generate(self, system, user):
        return next(self.responses), None


class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'data'
        create_demo(self.root)
    def tearDown(self):
        self.tmp.cleanup()

    def test_three_input_formats_and_calendar(self):
        db = BusinessDB(self.root / 'data' / 'shop_demo', self.root / 'calendar.csv')
        try:
            names = [x.name for x in db.tables]
            self.assertIn('sales', names)
            self.assertIn('inventory__ton_kho', names)
            self.assertIn('payments__pay', names)
            self.assertIn('calendar', names)
            c, rows = db.execute_readonly('SELECT SUM(CAST("doanh_thu" AS INTEGER)) FROM "sales"')
            self.assertEqual(rows[0][0], 1750000)
            with self.assertRaises(ValueError):
                db.execute_readonly('DELETE FROM "sales"')
            with self.assertRaises((sqlite3.DatabaseError, sqlite3.Warning)):
                db.execute_readonly('SELECT * FROM "sales"; DROP TABLE "sales"')
        finally:
            db.close()

    def test_model_execution_and_unanswerable(self):
        model = FakeModel([
            '{"type":"number","sql":"SELECT SUM(CAST(doanh_thu AS INTEGER)) FROM sales WHERE ngay <= \'2026-03-03\'"}',
            '{"type":"string","sql":"SELECT san_pham FROM sales WHERE ngay <= \'2026-03-03\' GROUP BY san_pham ORDER BY SUM(CAST(so_luong AS INTEGER)) DESC LIMIT 1"}',
            '{"type":"unanswerable","reason":"Không có đánh giá hài lòng"}',
        ])
        result_dir = Path(self.tmp.name) / 'result'
        count = run(self.root, result_dir, model)
        self.assertEqual(count, 3)
        answers = [json.loads(x) for x in (result_dir / 'submission.jsonl').read_text().splitlines()]
        logs = [json.loads(x) for x in (result_dir / 'logs' / 'questions.jsonl').read_text().splitlines()]
        self.assertEqual(answers[0]['answer'], 1150000)
        self.assertEqual(answers[1]['answer'], 'Xi măng A')
        self.assertEqual(answers[2]['type'], 'unanswerable')
        self.assertTrue(all({'id','answer','elapsed_ms','thinking'} <= set(x) for x in logs))
        self.assertIn('SELECT SUM', logs[0]['code'])
        self.assertIsNone(logs[0]['thinking'])

    def test_retry_then_abstain_not_unanswerable(self):
        model = FakeModel(['{"type":"number","sql":"SELECT fake_column FROM sales"}',
                           '{"type":"number","sql":"SELECT another_missing FROM sales"}'])
        agent = Agent(model, self.root)
        try:
            question = {'id':'q_test', 'business_id':'shop_demo', 'question':'Một số liệu?', 'as_of_date':'2026-03-04'}
            answer, log = agent.solve(question)
            self.assertEqual(answer['type'], 'abstain')
            self.assertEqual(len(log['code']), 2)
        finally:
            agent.close()


class RegressionTests(unittest.TestCase):
    """Regression tests for bugs fixed after first release."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'data'
        create_demo(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_demo_no_connection_leak(self):
        """create_demo must not leave open SQLite connections (ResourceWarning regression)."""
        root2 = Path(self.tmp.name) / 'rw2'
        caught = []
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always', ResourceWarning)
            create_demo(root2)
            gc.collect()
        db_warnings = [w for w in caught
                       if issubclass(w.category, ResourceWarning)
                       and 'database' in str(w.message).lower()]
        self.assertEqual(db_warnings, [],
                         f"create_demo left {len(db_warnings)} open SQLite connection(s)")

    def test_enable_load_extension_attribute_error_is_handled(self):
        """BusinessDB must initialize when enable_load_extension raises AttributeError.

        Python 3.12 builds without SQLITE_ENABLE_LOAD_EXTENSION: the method exists
        (hasattr returns True) but calling it raises AttributeError.  The try/except
        guard must absorb the error and leave the connection fully operational.
        """
        shop_dir = self.root / 'data' / 'shop_demo'
        _real_connect = sqlite3.connect

        class _ConnWrapper:
            """Wraps a real connection but makes enable_load_extension raise AttributeError."""
            def __init__(self, conn):
                self._c = conn
            def enable_load_extension(self, flag):
                raise AttributeError("not compiled with SQLITE_ENABLE_LOAD_EXTENSION")
            def __getattr__(self, name):
                return getattr(self._c, name)

        def patched_connect(database, **kwargs):
            return _ConnWrapper(_real_connect(database, **kwargs))

        with patch('src.ingestion.sqlite3.connect', patched_connect):
            db = BusinessDB(shop_dir)
        try:
            c, rows = db.execute_readonly('SELECT COUNT(*) FROM "sales"')
            self.assertEqual(rows[0][0], 4)
        finally:
            db.close()


class ScalarShapeRegressionTests(unittest.TestCase):
    """Regression tests for scalar shape checks, duplicate SQL detection, and date validation."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'data'
        create_demo(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    # ── typed_result shape checks ─────────────────────────────────────────

    def test_typed_result_raises_for_multi_row_string(self):
        from src.agent import typed_result
        with self.assertRaises(ValueError) as ctx:
            typed_result("string", ["name"], [("Xi măng A",), ("Xi măng B",)])
        self.assertIn("1 row", str(ctx.exception))

    def test_typed_result_raises_for_multi_col_string(self):
        from src.agent import typed_result
        with self.assertRaises(ValueError) as ctx:
            typed_result("string", ["name", "total"], [("Xi măng A", 100)])
        self.assertIn("1 column", str(ctx.exception))

    def test_typed_result_ok_for_single_row_col(self):
        from src.agent import typed_result
        result = typed_result("string", ["name"], [("Xi măng A",)])
        self.assertEqual(result, "Xi măng A")

    # ── date validation fix ────────────────────────────────────────────────

    def test_normalize_invalid_date_not_annotated(self):
        """Feb 29 in a non-leap year must NOT be annotated (2026 is not a leap year)."""
        from src.agent import normalize_date_hints
        result = normalize_date_hints("ngày 29/2", "2026-05-01")
        self.assertNotIn("2026-02-29", result)

    def test_normalize_valid_date_annotated(self):
        from src.agent import normalize_date_hints
        result = normalize_date_hints("ngày 28/2", "2026-05-01")
        self.assertIn("2026-02-28", result)

    def test_normalize_leap_year_feb29_annotated(self):
        from src.agent import normalize_date_hints
        result = normalize_date_hints("ngày 29/2/2024", "2026-05-01")
        self.assertIn("2024-02-29", result)

    # ── duplicate SQL detection ────────────────────────────────────────────

    def test_duplicate_sql_causes_abstain(self):
        """If both attempts return the same failing SQL, the agent must abstain."""
        # Ranking query without LIMIT 1 → multiple rows → shape error
        bad_sql = (
            'SELECT "san_pham" FROM "sales" GROUP BY "san_pham" '
            'ORDER BY SUM(CAST("so_luong" AS INTEGER)) DESC'
        )
        resp = json.dumps({"type": "string", "sql": bad_sql})
        model = FakeModel([resp, resp])
        agent = Agent(model, self.root)
        try:
            question = {
                'id': 'dup_01',
                'business_id': 'shop_demo',
                'question': 'Sản phẩm nào bán chạy nhất?',
                'as_of_date': '2026-03-04',
            }
            answer, log = agent.solve(question)
            self.assertEqual(answer['type'], 'abstain')
        finally:
            agent.close()

    # ── shape-specific retry message ───────────────────────────────────────

    def test_retry_message_mentions_limit_1_on_shape_error(self):
        """Retry prompt must include 'LIMIT 1' hint when SQL returns wrong shape."""
        bad_sql = (
            'SELECT "san_pham" FROM "sales" GROUP BY "san_pham" '
            'ORDER BY SUM(CAST("so_luong" AS INTEGER)) DESC'
        )
        captured = []

        class CapturingModel:
            def generate(self, system, user):
                captured.append(user)
                if len(captured) == 1:
                    return json.dumps({"type": "string", "sql": bad_sql}), None
                return '{"type":"abstain"}', None

        agent = Agent(CapturingModel(), self.root)
        try:
            question = {
                'id': 'shape_msg_01',
                'business_id': 'shop_demo',
                'question': 'Sản phẩm nào bán chạy nhất?',
                'as_of_date': '2026-03-04',
            }
            agent.solve(question)
        finally:
            agent.close()

        self.assertGreater(len(captured), 1, "Expected at least 2 generate calls")
        self.assertIn("LIMIT 1", captured[1])


if __name__ == '__main__':
    unittest.main()
