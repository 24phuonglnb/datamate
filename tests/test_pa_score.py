"""Tests for eval/pa_score.py (rulebook section 9)."""
import json
import os
import unittest
from pathlib import Path

from eval import pa_score as pa

ROOT = Path(__file__).parent.parent
TRAIN = Path(os.environ.get("ZAIC_TRAIN_DIR", ROOT / "data" / "train" / "train"))
GOLD = TRAIN / "answers.jsonl"


def G(typ, ans, alias=None):
    return {"id": "q", "type": typ, "answer": ans, "alias": alias or []}


def P(typ, ans=None, **kw):
    d = {"id": "q", "type": typ}
    if ans is not None:
        d["answer"] = ans
    d.update(kw)
    return d


class FormatRules(unittest.TestCase):
    def sc(self, pred, gold):
        return pa.score_one(pred, gold)[0]

    def test_number(self):
        g = G("number", 4820000)
        self.assertEqual(self.sc(P("number", 4820000), g), 1)
        self.assertEqual(self.sc(P("number", 4820000.0), g), 1)
        for bad in ["4820000", "4,82 triệu", "4.820.000", 4820001, True]:
            self.assertEqual(self.sc(P("number", bad), g), -1, bad)

    def test_percent(self):
        g = G("percent", 12.4)
        self.assertEqual(self.sc(P("percent", 12.4), g), 1)
        self.assertEqual(self.sc(P("percent", "12,4%"), g), -1)
        self.assertEqual(self.sc(P("percent", 0.124), g), -1)

    def test_type_must_match_first(self):
        self.assertEqual(self.sc(P("number", 12.4), G("percent", 12.4)), -1)

    def test_date(self):
        self.assertEqual(self.sc(P("date", "2026-08-15"), G("date", "2026-08-15")), 1)
        self.assertEqual(self.sc(P("date", "15/08/2026"), G("date", "2026-08-15")), -1)
        self.assertEqual(self.sc(P("date", "2025-09"), G("date", "2025-09")), 1)

    def test_boolean(self):
        self.assertEqual(self.sc(P("boolean", True), G("boolean", True)), 1)
        for bad in ["có", 1]:
            self.assertEqual(self.sc(P("boolean", bad), G("boolean", True)), -1)

    def test_string(self):
        g = G("string", "Sting dâu 330ml", ["SP0001"])
        self.assertEqual(self.sc(P("string", "sting DÂU  330ml"), g), 1)
        self.assertEqual(self.sc(P("string", "SP0001"), g), 1)
        self.assertEqual(self.sc(P("string", "Sting dầu 330ml"), g), -1)  # wrong diacritic
        self.assertEqual(self.sc(P("string", ["Sting dâu 330ml"]), g), -1)

    def test_list_order_and_singleton(self):
        g = G("list", ["Cà phê sữa", "Bạc xỉu"], [["SP1"], ["SP2"]])
        self.assertEqual(self.sc(P("list", ["Cà phê sữa", "Bạc xỉu"]), g), 1)
        self.assertEqual(self.sc(P("list", ["SP1", "bạc xỉu"]), g), 1)
        self.assertEqual(self.sc(P("list", ["Bạc xỉu", "Cà phê sữa"]), g), -1)
        self.assertEqual(self.sc(P("list", "Cà phê sữa, Bạc xỉu"), g), -1)
        self.assertEqual(self.sc(P("list", ["Cà phê sữa"]), G("list", ["Cà phê sữa"])), 1)
        self.assertEqual(self.sc(P("list", [3, 10]), G("list", [3, 10])), 1)

    def test_table(self):
        g = G("table", {"columns": ["khach_hang", "so_tien_no"],
                        "rows": [["Chị Lan", 3200000], ["Anh Nam", 100]]}, [["KH1"], ["KH2"]])
        ok = {"columns": ["khach_hang", "so_tien_no"], "rows": [["Anh Nam", 100], ["Chị Lan", 3200000]]}
        self.assertEqual(self.sc(P("table", ok), g), 1)  # row order irrelevant
        swapped = {"columns": ["so_tien_no", "khach_hang"], "rows": [[3200000, "Chị Lan"], [100, "Anh Nam"]]}
        self.assertEqual(self.sc(P("table", swapped), g), 1)  # columns by name
        renamed = {"columns": ["a", "b"], "rows": [["KH1", 3200000], ["KH2", 100]]}
        self.assertEqual(self.sc(P("table", renamed), g), 1)  # by position, alias accepted
        bad = {"columns": ["khach_hang", "so_tien_no"], "rows": [["Chị Lan", "3.200.000đ"], ["Anh Nam", 100]]}
        self.assertEqual(self.sc(P("table", bad), g), -1)

    def test_unanswerable(self):
        gu = G("unanswerable", None)
        self.assertEqual(self.sc(P("unanswerable", reason="thiếu dữ liệu"), gu), 1)
        self.assertEqual(self.sc(P("unanswerable"), gu), 1)  # reason optional
        self.assertEqual(self.sc(P("number", 5), gu), -1)  # answering unanswerable is wrong
        self.assertEqual(self.sc(P("unanswerable"), G("number", 5)), -1)
        self.assertEqual(self.sc(P("unanswerable", reason=5), gu), 0)  # unreadable => blank

    def test_abstain_and_missing(self):
        for g in (G("number", 5), G("unanswerable", None)):
            self.assertEqual(self.sc({"id": "q", "type": "abstain"}, g), 0)
            self.assertEqual(self.sc(None, g), 0)


@unittest.skipUnless(GOLD.is_file(), "official train data not available")
class SanityOnTrain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gold = pa.read_jsonl(GOLD)

    def test_gold_scores_one(self):
        self.assertEqual(len(self.gold), 3000)
        preds = []
        for g in self.gold:
            p = {"id": g["id"], "type": g["type"]}
            if g["type"] == "unanswerable":
                p["reason"] = "x"
            else:
                p["answer"] = g["answer"]
            preds.append(p)
        r = pa.score_all(preds, self.gold)
        self.assertEqual(r["pa"], 1.0)
        self.assertEqual(r["counts"]["wrong"], 0)

    def test_all_abstain_scores_zero(self):
        preds = [{"id": g["id"], "type": "abstain"} for g in self.gold]
        self.assertEqual(pa.score_all(preds, self.gold)["pa"], 0.0)
        self.assertEqual(pa.score_all([], self.gold)["pa"], 0.0)  # missing lines

    def test_all_unanswerable_is_negative_unless_gold(self):
        preds = [{"id": g["id"], "type": "unanswerable"} for g in self.gold]
        r = pa.score_all(preds, self.gold)
        n_un = sum(g["type"] == "unanswerable" for g in self.gold)
        self.assertEqual(r["total"], n_un - (3000 - n_un))


if __name__ == "__main__":
    unittest.main()
