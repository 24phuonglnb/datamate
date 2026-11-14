"""Unit tests for Task T5 (`scripts/analysis/rule_regression.py`).

Uses real literals from `data/train/train/questions.jsonl`, `data/train/train/answers.jsonl`,
and `data/train/train/data/biz_102`, `biz_111`, `biz_117`, `biz_123`.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_paths import train_dir  # noqa: E402

_BIZ_102 = train_dir() / "data" / "biz_102"
_BIZ_117 = train_dir() / "data" / "biz_117"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "analysis"))

from scripts.analysis.rule_regression import (
    answers_match,
    diagnose_failure,
    execute_template,
    match_item_in_catalog,
    month_bounds,
    parse_explicit_period,
    should_skip_question,
)
from src.cleaning import load_business
from src.mapping import propose_mapping
from src.views import build_database


def test_parse_explicit_period_and_month_bounds():
    # Source: data/train/questions.jsonl (q_79dbf0f33660, biz_102)
    q1 = "xem giup tong dthu thang 1 nam 2025 la bao nhieu"
    p1 = parse_explicit_period(q1, "2026-08-15")
    assert p1 == ("2025-01-01", "2025-01-31", (2025, 1))

    # Source: period capped by as_of_date per Rulebook §2
    assert month_bounds(2026, 8, "2026-08-15") == ("2026-08-01", "2026-08-15")

    # Source: data/train/questions.jsonl (q_2277003c32e8, biz_103 — date range should not match single date)
    q_range = "giai đoạn từ 25/06/2026 đến heets 01/07/2026 có tổng cộng mấy mặt hàng ees, bán ko dc món nào hả"
    assert parse_explicit_period(q_range, "2026-07-10") is None


def test_should_skip_question_filters():
    # Plain monthly revenue -> not skipped
    # Source: data/train/questions.jsonl (q_79dbf0f33660, biz_102)
    p = ("2025-01-01", "2025-01-31", (2025, 1))
    assert (
        should_skip_question(
            "revenue",
            "xem giup tong dthu thang 1 nam 2025 la bao nhieu",
            "number",
            has_sales_views=True,
            min_date="2025-01-01",
            period_info=p,
        )
        is None
    )

    # Item-specific revenue with telex typo "bans" -> skipped from shop-wide revenue template
    # Source: data/train/questions.jsonl (q_0e8470f64962, biz_102)
    assert (
        should_skip_question(
            "revenue",
            "tháng 4/2026 bans Bột ngọt Ajinomoto 400g được bao nhiêu tieenf",
            "number",
            has_sales_views=True,
            min_date="2025-01-01",
            period_info=("2026-04-01", "2026-04-30", (2026, 4)),
        )
        == "item_specific_revenue"
    )

    # Item-specific revenue with "dthu cuar <item>" -> skipped from shop-wide revenue template
    # Source: data/train/questions.jsonl (q_06496e250b4a, biz_104)
    assert (
        should_skip_question(
            "revenue",
            "dthu cuar Sữa tươi trân châu đường đen (L) trong thangs 6 năm 2025 là bao nhiêu",
            "number",
            has_sales_views=True,
            min_date="2025-01-01",
            period_info=("2025-06-01", "2025-06-30", (2025, 6)),
        )
        == "extra_filter_or_subintent"
    )

    # Period before shop min_date -> skipped
    # Source: data/train/questions.jsonl (biz_103 starts 2025-04-01, asks month 2/2025)
    assert (
        should_skip_question(
            "revenue",
            "dthu thang 2/2025 bnhiu",
            "unanswerable",
            has_sales_views=True,
            min_date="2025-04-01",
            period_info=("2025-02-01", "2025-02-28", (2025, 2)),
        )
        == "before_shop_min_date"
    )


@pytest.mark.skipif(not _BIZ_102.exists(), reason="private data not present (data/train/train/data/biz_102)")
def test_execute_templates_on_biz_102():
    # Source: data/train/train/data/biz_102 and official answers in data/train/train/answers.jsonl
    biz_dir = _BIZ_102
    conn = build_database(biz_dir)
    try:
        cat_items = conn.execute(
            "SELECT item_code, item_name, name_aliases, base_unit FROM v_items"
        ).fetchall()

        # 1. Monthly revenue: q_79dbf0f33660 (tháng 1/2025 -> 435803500)
        q_rev = "xem giup tong dthu thang 1 nam 2025 la bao nhieu"
        p_rev = parse_explicit_period(q_rev, "2026-08-01")
        assert p_rev is not None
        val_rev, skip_rev = execute_template(conn, "revenue", q_rev, "2026-08-01", p_rev, cat_items)
        assert skip_rev is None
        assert val_rev == 435803500

        # 2. Cancelled order count: q_1bd200cd8993 (tháng 2/2025 -> 61)
        q_canc = "xem giúp trong tháng 2/2025, cửa hàng có mấy đơn ở trạng thái huỷ"
        p_canc = parse_explicit_period(q_canc, "2026-08-01")
        assert p_canc is not None
        val_canc, _ = execute_template(conn, "cancel_count", q_canc, "2026-08-01", p_canc, cat_items)
        assert val_canc == 61

        # 3. Cancellation rate: q_3379b46319a8 (tháng 2/2025 -> 2.58)
        q_rate = "Trong tháng 2/2025, tỉ lệ đơn huỷ là bao nhiêu phần trăm?"
        p_rate = parse_explicit_period(q_rate, "2026-08-01")
        assert p_rate is not None
        val_rate, _ = execute_template(conn, "cancel_rate", q_rate, "2026-08-01", p_rate, cat_items)
        assert answers_match(val_rate, 2.58)

        # 4. AOV half-up: q_dcc0b785c232 (tháng 2/2025 -> 158315)
        q_aov = "Tháng 2/2025 dthu bình quân mỗi đơn là bao nhiêu?"
        p_aov = parse_explicit_period(q_aov, "2026-08-01")
        assert p_aov is not None
        val_aov, _ = execute_template(conn, "aov", q_aov, "2026-08-01", p_aov, cat_items)
        assert val_aov == 158315

        # 5. Best day: tháng 12/2025 -> "2025-12-29"
        q_bday = "Cho hỏi trong tháng 12/2025, xét theo doanh thu, ngày nào bán đắt nhất?"
        p_bday = parse_explicit_period(q_bday, "2026-08-01")
        assert p_bday is not None
        val_bday, _ = execute_template(conn, "best_day", q_bday, "2026-08-01", p_bday, cat_items)
        assert val_bday == "2025-12-29"

        # 6. Top-k items: q_dfe2b9e2e7b3 (tháng 2/2026 -> ['Snack Oishi tôm cay 40g', 'Mì Hảo Hảo tôm chua cay', 'Trứng gà so'])
        q_topk = "thangs 2/2026 top 3 hàng chạy nhất laf gì ta"
        p_topk = parse_explicit_period(q_topk, "2026-08-01")
        assert p_topk is not None
        val_topk, _ = execute_template(conn, "topk_items", q_topk, "2026-08-01", p_topk, cat_items)
        assert val_topk == ["Snack Oishi tôm cay 40g", "Mì Hảo Hảo tôm chua cay", "Trứng gà so"]

        # 7. Item quantity: tháng 6/2025 Nếp cái hoa vàng -> 59 kg
        q_iqty = "thang 6/2025 ban ra bnhiu kg nep cai hoa vang"
        p_iqty = parse_explicit_period(q_iqty, "2026-08-01")
        assert p_iqty is not None
        val_iqty, _ = execute_template(conn, "item_qty", q_iqty, "2026-08-01", p_iqty, cat_items)
        assert val_iqty == 59

        # 8. Revenue change pct MoM and YoY:
        # MoM: tháng 5/2026 so với tháng trước -> -1.79
        q_mom = "Doanh thu tháng 5/2026 tăng hay giảm bao nhiêu phần trăm so với tháng trước?"
        p_mom = parse_explicit_period(q_mom, "2026-08-01")
        assert p_mom is not None
        val_mom, _ = execute_template(conn, "rev_change_pct", q_mom, "2026-08-01", p_mom, cat_items)
        assert answers_match(val_mom, -1.79)

        # YoY: tháng 4 năm 2026 so với cùng tháng năm trước -> 2.25
        q_yoy = "so vs cung thang nam truoc, dthu thang 4 nam 2026 thay doi may %"
        p_yoy = parse_explicit_period(q_yoy, "2026-08-01")
        assert p_yoy is not None
        val_yoy, _ = execute_template(conn, "rev_change_pct", q_yoy, "2026-08-01", p_yoy, cat_items)
        assert answers_match(val_yoy, 2.25)
    finally:
        conn.close()


@pytest.mark.skipif(not _BIZ_117.exists(), reason="private data not present (data/train/train/data/biz_117)")
def test_diagnose_failure_variants():
    # biz_117 (q_788ab61d79d1) used to fail because its unit-conversion table was not recognised
    # Source: data/train/train/data/biz_117/DanhMuc.xlsx (`Hàng`, `ĐV lớn`, `ĐV nhỏ`, `Hệ số QĐ`)
    biz_dir = _BIZ_117
    readme = (biz_dir / "README.md").read_text(encoding="utf-8")
    tables = load_business(biz_dir)
    mapping = propose_mapping(tables, readme)
    conn = build_database(biz_dir)
    try:
        q = "Liệt kê 5 mặt hàng bán chạy nhất tháng 9/2025."
        p = parse_explicit_period(q, "2026-05-20")
        assert p is not None
        expected = [
            "Xi măng Hà Tiên PCB40 bao 50kg",
            "Xi măng INSEE Power-S bao 50kg",
            "Thép cuộn phi 6 Hòa Phát",
            "Băng keo điện Nano 20 yard",
            "Thép Pomina D10 cây 11.7m",
        ]
        calc, _ = execute_template(conn, "topk_items", q, "2026-05-20", p, [])
        # The conversion table in DanhMuc.xlsx is now read by load_unit_conversions, so the
        # template answer is already right and there is nothing left to diagnose.
        assert calc == expected
        diags = diagnose_failure(
            conn, tables, mapping, readme, "topk_items", q, "2026-05-20", p, calc, expected
        )
        assert isinstance(diags, list)
    finally:
        conn.close()
