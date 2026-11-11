"""Tests for the synthetic benchmark: data generation and ground truth validity."""
import json
import tempfile
import unittest
from pathlib import Path

from benchmark.create_benchmark import build_benchmark, QUESTIONS
from src.ingestion import BusinessDB


class BenchmarkBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        build_benchmark(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_all_expected_files_exist(self):
        self.assertTrue((self.root / "questions.jsonl").is_file())
        self.assertTrue((self.root / "ground_truth.jsonl").is_file())
        self.assertTrue((self.root / "rulebook.md").is_file())
        self.assertTrue((self.root / "calendar.csv").is_file())
        for biz in ("biz_cafe", "biz_pharmacy", "biz_restaurant", "biz_electronics", "biz_fashion"):
            self.assertTrue((self.root / "data" / biz).is_dir(), f"Missing business dir: {biz}")

    def test_question_count(self):
        with (self.root / "questions.jsonl").open(encoding="utf-8") as f:
            qs = [json.loads(l) for l in f if l.strip()]
        self.assertGreaterEqual(len(qs), 100, "Benchmark must have at least 100 questions")

    def test_question_fields(self):
        with (self.root / "questions.jsonl").open(encoding="utf-8") as f:
            qs = [json.loads(l) for l in f if l.strip()]
        for q in qs:
            self.assertIn("id", q)
            self.assertIn("business_id", q)
            self.assertIn("question", q)
            self.assertIn("as_of_date", q)
            self.assertNotIn("oracle_sql", q, "oracle_sql must be stripped from published questions")
            self.assertNotIn("type", q, "ground-truth type must not be in questions.jsonl")

    def test_ground_truth_count_matches_questions(self):
        with (self.root / "questions.jsonl").open(encoding="utf-8") as f:
            q_ids = {json.loads(l)["id"] for l in f if l.strip()}
        with (self.root / "ground_truth.jsonl").open(encoding="utf-8") as f:
            gt_ids = {json.loads(l)["id"] for l in f if l.strip()}
        self.assertEqual(q_ids, gt_ids)

    def test_no_oracle_errors(self):
        with (self.root / "ground_truth.jsonl").open(encoding="utf-8") as f:
            gt = [json.loads(l) for l in f if l.strip()]
        errors = [(g["id"], g["error"]) for g in gt if g.get("error")]
        self.assertEqual(errors, [], f"Oracle SQL errors: {errors}")

    def test_answerable_questions_have_non_null_answers(self):
        with (self.root / "ground_truth.jsonl").open(encoding="utf-8") as f:
            gt = [json.loads(l) for l in f if l.strip()]
        for g in gt:
            if g["type"] != "unanswerable":
                self.assertIsNotNone(g.get("answer"),
                                     f"{g['id']}: answerable question has null answer")

    def test_question_type_diversity(self):
        # Check that multiple types are covered
        type_map = {q["id"]: q["type"] for q in QUESTIONS}
        types_present = set(type_map.values())
        required_types = {"number", "string", "boolean", "percent", "list", "table", "unanswerable"}
        missing = required_types - types_present
        self.assertEqual(missing, set(), f"Missing question types: {missing}")

    def test_business_coverage(self):
        biz_ids = {q["business_id"] for q in QUESTIONS}
        expected = {"biz_cafe", "biz_pharmacy", "biz_restaurant", "biz_electronics", "biz_fashion"}
        self.assertEqual(biz_ids, expected)

    def test_min_questions_per_business(self):
        from collections import Counter
        counts = Counter(q["business_id"] for q in QUESTIONS)
        for biz, count in counts.items():
            self.assertGreaterEqual(count, 15, f"{biz} has only {count} questions (need ≥15)")


class BenchmarkDBTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        build_benchmark(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _db(self, biz: str) -> BusinessDB:
        return BusinessDB(
            self.root / "data" / biz,
            self.root / "calendar.csv",
        )

    def test_biz_cafe_tables(self):
        db = self._db("biz_cafe")
        try:
            names = [t.name for t in db.tables]
            self.assertIn("sales", names)
            self.assertIn("inventory__stock", names)
            self.assertIn("calendar", names)
            _, rows = db.execute_readonly('SELECT COUNT(*) FROM "sales"')
            self.assertGreater(rows[0][0], 0)
        finally:
            db.close()

    def test_biz_pharmacy_tables(self):
        db = self._db("biz_pharmacy")
        try:
            names = [t.name for t in db.tables]
            self.assertIn("products", names)
            self.assertIn("transactions__giao_dich", names)
        finally:
            db.close()

    def test_biz_restaurant_tables(self):
        db = self._db("biz_restaurant")
        try:
            names = [t.name for t in db.tables]
            self.assertIn("orders", names)
            self.assertIn("menu__menu", names)
            self.assertIn("reservations__bookings", names)
        finally:
            db.close()

    def test_biz_electronics_tables(self):
        db = self._db("biz_electronics")
        try:
            names = [t.name for t in db.tables]
            self.assertIn("catalog__items", names)
            self.assertIn("sales__deals", names)
        finally:
            db.close()

    def test_biz_fashion_tables(self):
        db = self._db("biz_fashion")
        try:
            names = [t.name for t in db.tables]
            self.assertIn("products", names)
            self.assertIn("orders__sales", names)
        finally:
            db.close()

    def test_cafe_total_revenue_jan(self):
        db = self._db("biz_cafe")
        try:
            _, rows = db.execute_readonly(
                "SELECT SUM(CAST(doanh_thu AS INTEGER)) FROM \"sales\" "
                "WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01'"
            )
            self.assertEqual(rows[0][0], 4050000)
        finally:
            db.close()

    def test_pharmacy_join_works(self):
        db = self._db("biz_pharmacy")
        try:
            _, rows = db.execute_readonly(
                'SELECT COUNT(*) FROM "transactions__giao_dich" t '
                'JOIN "products" p ON t.ma_thuoc = p.ma_thuoc'
            )
            self.assertGreater(rows[0][0], 0)
        finally:
            db.close()

    def test_electronics_profit_calculation(self):
        db = self._db("biz_electronics")
        try:
            _, rows = db.execute_readonly(
                'SELECT SUM((CAST(s.gia_ban AS INTEGER) - CAST(c.gia_nhap AS INTEGER)) * CAST(s.so_luong AS INTEGER)) '
                'FROM "sales__deals" s JOIN "catalog__items" c ON s.ma_sp = c.ma_sp '
                "WHERE s.ngay >= '2026-01-01' AND s.ngay < '2026-02-01'"
            )
            self.assertGreater(rows[0][0], 0, "Should have positive profit")
        finally:
            db.close()

    def test_schema_text_includes_type_hints(self):
        db = self._db("biz_cafe")
        try:
            schema = db.schema_text()
            self.assertIn("NUMERIC", schema, "Schema should annotate numeric columns")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
