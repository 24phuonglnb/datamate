"""Rule-layer normalization + timeutil tests.

Cases are real DEV-shop train questions, referenced by id (the question text is read from the
private data at test time and is NOT stored in the repo).  Expected values were derived by hand
from rulebook section 2 / section 5, not copied from program output.  Tests skip when the
official data is not present.
"""
import json
import os
import re
import unittest
from datetime import date
from pathlib import Path

from src.nlu.normalize import normalize
from src.timeutil import LunarCalendar, resolve

ROOT = Path(__file__).parent.parent
TRAIN = Path(os.environ.get("ZAIC_TRAIN_DIR", ROOT / "data" / "train" / "train"))
FOLDS = Path(os.environ.get("ZAIC_FOLDS", ROOT / "eval" / "folds.json"))
HAVE = (TRAIN / "questions.jsonl").is_file() and FOLDS.is_file()

D = date.fromisoformat


def P(a, b):
    return (D(a) if a else None, D(b))


# id -> (periods, comparison or None)
# Kỳ mong đợi tự suy từ rulebook §2, không lấy từ answers.jsonl; chỉ dùng trong test, không dùng lúc inference.
PERIOD_CASES = {
    # cumulative: "đến hết ngày X", "cuối ngày hôm nay"
    "q_0194d8d10f17": ([P(None, "2026-08-19")], None),
    "q_0946f3145fb4": ([P(None, "2026-06-12")], None),
    "q_8ff6713cd1b9": ([P(None, "2026-03-23")], None),
    "q_23cea7790c35": ([P(None, "2025-04-05")], None),
    # tháng này (to date) vs cùng kỳ tháng trước (same number of days)
    "q_864c9d9c036a": ([P("2026-05-01", "2026-05-09")], P("2026-04-01", "2026-04-09")),
    "q_aa9b48472c8b": ([P("2025-05-01", "2025-05-14")], P("2025-04-01", "2025-04-14")),
    "q_4726d037f8a8": ([P("2026-03-01", "2026-03-20")], P("2026-02-01", "2026-02-20")),
    "q_d9dffcc652db": ([P("2026-04-01", "2026-04-22")], P("2026-03-01", "2026-03-22")),
    "q_b3b16e699a67": ([P("2026-06-01", "2026-06-10")], P("2026-05-01", "2026-05-10")),
    "q_301e64ea77a9": ([P("2025-08-01", "2025-08-31")], P("2025-07-01", "2025-07-31")),
    # từ đầu năm
    "q_f6bb21e6ebb7": ([P("2026-01-01", "2026-05-04")], None),
    "q_4470cd3d68b2": ([P("2025-01-01", "2025-05-08")], None),
    "q_18f8cdf43ae0": ([P("2026-01-01", "2026-05-28")], None),
    "q_2ca8fd946a09": ([P("2026-01-01", "2026-05-29")], None),  # filled below (as_of read from data)
    # từ X đến Y
    "q_e81372dda9dc": ([P("2026-01-01", "2026-04-27")], None),
    "q_f241b877efe2": ([P("2026-03-16", "2026-03-22")], None),
    "q_c00dc4e2a578": ([P("2025-07-21", "2025-07-27")], None),
    "q_ab998f9ea093": ([P("2026-05-25", "2026-09-22")], None),
    "q_7dae0d81eb69": ([P(None, "2026-05-25"), P("2026-05-25", "2026-09-22")], None),
    # ngày
    "q_25501a11062a": ([P("2025-11-05", "2025-11-05")], None),
    "q_81d75bf535d0": ([P("2026-05-25", "2026-05-25")], None),
    "q_26ec390f37d7": ([P("2025-08-25", "2025-08-25")], None),
    "q_d5e6651d3fb6": ([P("2025-07-02", "2025-07-02")], None),
    # N ngày kể từ ngày D vs N ngày ngay trước D (section 5)
    "q_b946d3a969a0": ([P("2026-02-06", "2026-03-07")], P("2026-01-07", "2026-02-05")),
    "q_dd6531374a2b": ([P("2026-04-18", "2026-04-24")], P("2026-04-11", "2026-04-17")),
    "q_ae5a19034686": ([P("2026-06-22", "2026-07-05")], P("2026-06-08", "2026-06-21")),
    "q_328566752555": ([P("2026-02-01", "2026-02-14")], P("2026-01-18", "2026-01-31")),
    # tháng M/Y
    "q_acf5e6eebd7d": ([P("2025-05-01", "2025-05-31")], None),
    "q_99543ed94f0b": ([P("2025-05-01", "2025-05-31")], None),
    "q_f0adbb2db8ff": ([P("2025-07-01", "2025-07-31")], None),
    "q_5941a809c334": ([P("2025-11-01", "2025-11-30")], None),
    "q_f673036bdd05": ([P("2026-02-01", "2026-02-28")], P("2026-01-01", "2026-01-31")),
    "q_36d4c28e5079": ([P("2026-01-01", "2026-01-31")], P("2025-12-01", "2025-12-31")),
    "q_5c7a3aed2f4f": ([P("2025-08-01", "2025-08-31")], P("2025-07-01", "2025-07-31")),
    # ca sáng / chiều: same period, no previous-period comparison
    "q_b445c50f6b5e": ([P("2025-08-01", "2025-08-31")], None),
    "q_66ade8db83b2": ([P("2025-11-01", "2025-11-30")], None),
    "q_1c4d072b63b0": ([P("2026-02-02", "2026-02-08")], None),
    # chuỗi tháng: "tháng sau / tháng trước" is relative to the series, not to today
    "q_5b66ecfa2ba0": ([P("2026-02-01", "2026-04-30")], None),
    "q_823d917dff8b": ([P("2025-04-01", "2025-06-30")], None),
    "q_6d6f14c7978d": ([P("2025-07-01", "2025-09-30")], None),
    # tháng này
    "q_44edb3d764e9": ([P("2026-07-01", "2026-07-17")], None),
    "q_e5e5eb7b1d8e": ([P("2026-05-01", "2026-05-20")], None),
    "q_863a95ddf319": ([P("2026-06-01", "2026-06-12")], None),
    # quý
    "q_2a9c7770d574": ([P("2025-04-01", "2025-06-30")], None),
    "q_6257a245a516": ([P("2025-07-01", "2025-09-30")], None),
    "q_9b23c0d87092": ([P("2025-10-01", "2025-12-31")], None),
    "q_10e47ea13db9": ([P("2026-01-01", "2026-03-31")], None),
    # N ngày gần nhất (ends today, inclusive)
    "q_e15496dc385c": ([P("2026-02-19", "2026-03-04")], None),
    "q_c972201b657c": ([P("2025-06-02", "2025-06-08")], None),
    "q_9246992fa01b": ([P("2026-01-30", "2026-02-05")], None),
    # Tết
    "q_0fbd522a4f2f": ([P("2026-02-10", "2026-02-26")], P("2026-01-24", "2026-02-09")),
    "q_eef55227353d": ([P("2026-02-10", "2026-02-26")], P("2025-01-22", "2025-02-07")),
    # tuần rồi / tuần này (Monday start)
    "q_0b6552ce1b0d": ([P("2025-03-17", "2025-03-23")], None),
    "q_e4fe38fbebb9": ([P("2025-06-30", "2025-07-06")], None),
    "q_2225d390b8bb": ([P("2025-07-28", "2025-08-03")], None),
    "q_e5f51c796fd2": ([P("2026-09-07", "2026-09-13")], None),
    "q_49d3650e803b": ([P("2026-05-25", "2026-05-29")], None),
    "q_d81abc9c0964": ([P("2025-04-07", "2025-04-10")], None),
    "q_b00ae87945f5": ([P("2026-03-23", "2026-03-27")], None),
    # no time expression at all
    "q_1af6e691fc94": ([], None),
}

# id -> expected rule-layer text (teencode + telex repaired; diacritic-less words untouched)
TEXT_CASES = {
    "q_001883280e83": "tháng này tổng giá trị các phiếu nhập hàng là bao nhiêu",
    "q_008f69128180": "trong thang 10/2025, ti le don huy la bao nhiêu %",
    "q_00c4e64fe706": "Tháng 5/2025 cửa hàng bán được tổng cộng bao nhiêu tiền?",
    "q_0139627bccae": "check gium hôm nay cua hang co bao nhiêu don",
    "q_01a47607f90c": "tổng doanh thu trong ngày hôm nay là bao nhiêu vậy",
    "q_02ed16421456": "tháng 8/2025 quán bán được bao nhiêu ly size m",
    "q_044a0d4c3ff0": "tiền bán má heo nướng nước mắm tháng 9/2025 là nhiêu",
    "q_0465a6852f62": "giá trị trung bình một đơn tháng 4/2026 là bao nhiêu",
    "q_058bd677f168": "ê trung bình mỗi đơn tuần trước mang về bao nhiêu doanh thu",
    "q_065aa2aac90c": "thang 2/2026 ngay nao cua hang ban được nhiêu tien nhat",
    "q_06de33fa21cc": "sản phẩm bán được nhiều nhất tuần rồi là gì",
    "q_076dfb541ac4": "tháng 2/2025 doanh thu hàng không kê đơn là bao nhiêu",
    "q_0bb2685c3a94": "cho tôi 5 khách mua nhiều tiền nhất tháng 6/2026",
    "q_0f6233b739e9": "thang 11/2025 cac thuoc co hoat chat natri clorid ban được bao nhiêu tien vậy",
    "q_1324e9ac2b41": "tháng 4/2025 ngày nào cửa hàng bán được nhiều tiền nhất",
    "q_1af02cd5fe06": "Cho tôi biết số đơn hôm qua",
    "q_1dbea6881dab": "tháng 6/2026 cửa hàng bán được tổng cộng bao nhiêu tiền",
    "q_21e3d299c23d": "doanh thu thang 3/2025 tang hay giam bao nhieu % so với tháng truoc",
    "q_261ae1fe4be0": "tháng 3/2025 top 5 hàng bán chạy nhất là gì",
    "q_29503ba420d0": "tháng 5/2026 doanh thu hàng không kê đơn là bao nhiêu ta",
    "q_2ca8fd946a09": "doanh thu từ đầu năm tới hết hôm nay là bao nhiêu nhỉ",
    "q_5a1e29a88b63": "hôm qua doanh thu được bao nhiêu",
    "q_5c01ed371d11": "cho hoi thang 11/2025 nha thuoc ban hang không ke don được bao nhieu tien",
    "q_607f89f0a1de": "7 ngày gần nhất, cửa hàng có mấy mặt hàng ế hẳn, không ai mua cái nào?",
    "q_a57e54686875": "30 ngày gần nhất cửa hàng bán được bao nhiêu tiền",
}


def _load():
    folds = json.loads(FOLDS.read_text(encoding="utf-8"))
    qs = {}
    for line in (TRAIN / "questions.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            q = json.loads(line)
            qs[q["id"]] = q
    return set(folds["dev"]), qs


@unittest.skipUnless(HAVE, "official train data / folds not available")
class RealQuestionCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dev, cls.qs = _load()
        cls.cal = LunarCalendar(TRAIN / "calendar.csv")

    def test_only_dev_shops_are_used(self):
        for qid in list(PERIOD_CASES) + list(TEXT_CASES):
            self.assertIn(self.qs[qid]["business_id"], self.dev, qid)

    def test_case_count(self):
        self.assertGreaterEqual(len(PERIOD_CASES) + len(TEXT_CASES), 50)

    def test_periods(self):
        for qid, (periods, comp) in PERIOD_CASES.items():
            q = self.qs[qid]
            nq = normalize(q["question"], q["as_of_date"], self.cal)
            got = [(p.start, p.end) for p in nq.period.periods]
            if qid == "q_2ca8fd946a09":  # as_of is data-dependent: expected is Jan 1 .. as_of
                a = D(q["as_of_date"])
                periods = [(date(a.year, 1, 1), a)]
            with self.subTest(qid=qid):
                self.assertEqual(got, periods)
                c = nq.period.comparison
                self.assertEqual((c.start, c.end) if c else None, comp)

    def test_shift_cases(self):
        q = self.qs["q_b445c50f6b5e"]
        pod = normalize(q["question"], q["as_of_date"]).period.part_of_day
        self.assertEqual(pod["baseline"], "sang")  # "so với ca sáng": baseline is the morning shift
        q = self.qs["q_66ade8db83b2"]
        pod = normalize(q["question"], q["as_of_date"]).period.part_of_day
        self.assertEqual(set(pod) - {"rule"}, {"sang"})
        self.assertEqual(pod["sang"], ("06:00", "13:59"))

    def test_text_repairs(self):
        for qid, expected in TEXT_CASES.items():
            with self.subTest(qid=qid):
                self.assertEqual(normalize(self.qs[qid]["question"]).text, expected)

    def test_needs_llm_flags(self):
        self.assertFalse(normalize(self.qs["q_00c4e64fe706"]["question"]).needs_llm)  # clean after repair
        for qid in ("q_008f69128180", "q_065aa2aac90c", "q_21e3d299c23d"):  # still diacritic-less
            self.assertTrue(normalize(self.qs[qid]["question"]).needs_llm, qid)

    def test_numbers_preserved_on_all_dev_questions(self):
        """Normalization must never add, drop or alter a digit sequence."""
        bad = []
        for q in self.qs.values():
            if q["business_id"] not in self.dev:
                continue
            nq = normalize(q["question"], q["as_of_date"], self.cal)
            if re.findall(r"\d+", q["question"]) != re.findall(r"\d+", nq.text):
                bad.append(q["id"])
        self.assertEqual(bad, [])

    def test_gold_dates_fall_inside_resolved_period(self):
        gold = {}
        for line in (TRAIN / "answers.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                a = json.loads(line)
                gold[a["id"]] = a
        checked = ok = 0
        for q in self.qs.values():
            a = gold[q["id"]]
            if q["business_id"] not in self.dev or a["type"] != "date":
                continue
            ps = normalize(q["question"], q["as_of_date"], self.cal).period.periods
            if not ps:
                continue
            checked += 1
            ans = a["answer"]
            hit = any(p.start is not None and (p.start.strftime("%Y-%m") <= ans <= p.end.strftime("%Y-%m") if len(ans) == 7
                                              else p.start <= D(ans) <= p.end) for p in ps)
            ok += hit
        self.assertGreater(checked, 100)
        self.assertGreaterEqual(ok / checked, 0.97)


class SyntheticRules(unittest.TestCase):
    """Rule rows with no real example in the dev questions (kept synthetic, no data needed)."""

    def test_this_month_vs_short_previous_month(self):
        r = resolve("doanh thu thang nay so voi cung ky thang truoc", "2026-03-30")
        self.assertEqual((r.periods[0].start, r.periods[0].end), (D("2026-03-01"), D("2026-03-30")))
        self.assertEqual((r.comparison.start, r.comparison.end), (D("2026-02-01"), D("2026-02-28")))  # no day 30 in Feb

    def test_month_without_year(self):
        r = resolve("doanh thu thang 11", "2026-09-07")  # after today -> last year
        self.assertEqual((r.periods[0].start, r.periods[0].end), (D("2025-11-01"), D("2025-11-30")))
        r = resolve("doanh thu thang 5", "2026-09-07")  # not after today -> this year
        self.assertEqual((r.periods[0].start, r.periods[0].end), (D("2026-05-01"), D("2026-05-31")))

    def test_quarter_without_year(self):
        r = resolve("doanh thu quy 4", "2026-09-07")
        self.assertEqual((r.periods[0].start, r.periods[0].end), (D("2025-10-01"), D("2025-12-31")))
        r = resolve("doanh thu quy 2", "2026-09-07")
        self.assertEqual((r.periods[0].start, r.periods[0].end), (D("2026-04-01"), D("2026-06-30")))

    def test_public_formats(self):
        r = resolve("Th2/2026", "2026-09-07")
        self.assertEqual((r.periods[0].start, r.periods[0].end), (D("2026-02-01"), D("2026-02-28")))
        r = resolve("Q1/2026", "2026-09-07")
        self.assertEqual((r.periods[0].start, r.periods[0].end), (D("2026-01-01"), D("2026-03-31")))

    def test_short_slash_convention_by_keyword(self):
        def one(q, asof="2026-09-07"):
            r = resolve(q, asof)
            return ([(str(p.start), str(p.end)) for p in r.periods], bool(r.ambiguous))
        # keyword "ngay": day a, month b (year by the rule for a month without year)
        self.assertEqual(one("doanh thu ngay 25/6"), ([("2026-06-25", "2026-06-25")], False))
        self.assertEqual(one("doanh thu ngay 25/10"), ([("2025-10-25", "2025-10-25")], False))  # after today -> last year
        self.assertEqual(one("doanh thu ngay 6/25")[1], True)                                   # month 25 impossible
        # keyword "thang": month a, year 20b (20..39 only)
        self.assertEqual(one("doanh thu thang 6/25"), ([("2025-06-01", "2025-06-30")], False))
        self.assertEqual(one("doanh thu th6/26"), ([("2026-06-01", "2026-06-30")], False))
        self.assertEqual(one("doanh thu thang 6/15")[1], True)
        self.assertEqual(one("doanh thu thang 6/45")[1], True)
        # no keyword
        self.assertEqual(one("doanh thu 6/25"), ([("2025-06-01", "2025-06-30")], False))
        self.assertEqual(one("doanh thu 3/6"), ([("2026-06-03", "2026-06-03")], False))      # b <= 12: day a month b
        self.assertEqual(one("doanh thu 6/15")[1], True)                                       # 13..19: ambiguous
        self.assertEqual(one("doanh thu 6/45")[1], True)                                       # >= 40: ambiguous

    def test_day_month_still_day_month(self):
        r = resolve("ngay 1/1", "2026-04-27")
        self.assertEqual((r.periods[0].start, r.periods[0].end), (D("2026-01-01"), D("2026-01-01")))

    def test_bare_tet_is_ambiguous(self):
        r = resolve("doanh thu dip tet", "2026-09-07")
        self.assertEqual(r.periods, [])
        self.assertTrue(r.ambiguous)


if __name__ == "__main__":
    unittest.main()


def test_same_month_last_year_and_teencode_comparison():
    from src.timeutil import resolve
    r = resolve("so vs cung thang nam truoc, dthu thang 5 nam 2026 doi bn %", "2026-07-10")
    assert (str(r.comparison.start), str(r.comparison.end)) == ("2025-05-01", "2025-05-31")
    r = resolve("so voi cung ky nam trc, dthu thang 9/2026 tang hay giam", "2026-10-03")
    assert str(r.comparison.start) == "2025-09-01"
    r = resolve("thang 7/2026 hon hay kem th truoc bn %", "2026-08-20")
    assert (str(r.comparison.start), str(r.comparison.end)) == ("2026-06-01", "2026-06-30")


def test_period_where_sql():
    from src.timeutil import resolve
    p = resolve("doanh thu thang 3/2026", "2026-09-07").periods[0]
    assert p.where_sql() == "order_date BETWEEN '2026-03-01' AND '2026-03-31'"
    assert "order_time" in p.where_sql(part_of_day=("06:00", "13:59"))


def test_calendar_without_lunar_columns_is_tolerated(tmp_path):
    from src.timeutil import LunarCalendar
    f = tmp_path / "calendar.csv"
    f.write_text("date,weekday\n2026-01-01,Thu\n", encoding="utf-8")
    assert LunarCalendar(f).tet(2026) is None


class TetWithoutYear(unittest.TestCase):
    CAL = None

    @classmethod
    def setUpClass(cls):
        import tempfile
        from src.timeutil import LunarCalendar
        cls.tmp = tempfile.TemporaryDirectory()
        f = Path(cls.tmp.name) / "calendar.csv"
        # synthetic calendar: Tet 2025 = 2025-01-22..2025-02-08, Tet 2026 = 2026-02-10..2026-02-27
        f.write_text("date,lunar_year,lunar_month,lunar_day,lunar_leap\n"
                     "2025-01-22,2024,12,23,false\n2025-02-08,2025,1,10,false\n"
                     "2026-02-10,2025,12,23,false\n2026-02-27,2026,1,10,false\n", encoding="utf-8")
        cls.CAL = LunarCalendar(f)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def tet(self, asof, **kw):
        r = resolve("doanh thu dip tet", asof, calendar=self.CAL, **kw)
        return ([(str(p.start), str(p.end)) for p in r.periods], bool(r.ambiguous))

    def test_latest_tet_that_has_started(self):
        self.assertEqual(self.tet("2025-12-01"), ([("2025-01-22", "2025-02-08")], False))   # 2026 not started yet
        self.assertEqual(self.tet("2026-02-10"), ([("2026-02-10", "2026-02-27")], False))   # starts today
        self.assertEqual(self.tet("2026-05-01"), ([("2026-02-10", "2026-02-27")], False))
        self.assertEqual(self.tet("2025-01-10")[1], True)                                    # none started in the calendar

    def test_ambiguous_when_rulebook_does_not_define_tet_or_no_calendar(self):
        self.assertEqual(self.tet("2026-05-01", tet_bare=False)[1], True)
        self.assertEqual(resolve("doanh thu dip tet", "2026-05-01").ambiguous[0]["text"], "dip tet")


def test_n_days_from_the_price_day_named_once_in_the_question():
    """"7 ngay ke tu ngay do / ngay tang gia" = the 7 days from the one full date of the question, vs the 7 days before."""
    import datetime as dt
    from src.timeutil import resolve
    for q in ("pho vifon doi gia vao ngay 29/06/2025. 7 ngay ke tu ngay do ban duoc nhieu hay it hon 7 ngay truoc do bao nhieu %",
              "pho vifon doi gia vao ngay 29/06/2025. 7 ngay ke tu ngay tang gia so voi 7 ngay truoc"):
        r = resolve(q, "2026-09-10")
        assert any((p.start, p.end) == (dt.date(2025, 6, 29), dt.date(2025, 7, 5)) for p in r.periods)
        assert (r.comparison.start, r.comparison.end) == (dt.date(2025, 6, 22), dt.date(2025, 6, 28))
    r = resolve("7 ngay ke tu ngay do so voi 7 ngay truoc", "2026-09-10")      # no date named: nothing is guessed
    assert not r.periods and r.comparison is None
    r = resolve("ngay 01/06/2025 va ngay 29/06/2025, 7 ngay ke tu ngay do", "2026-09-10")   # two dates: ambiguous, not guessed
    assert not any(p.end == dt.date(2025, 7, 5) for p in r.periods)
