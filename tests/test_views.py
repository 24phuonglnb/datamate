"""Unit and integration tests for `src/views.py` (Task T4: SQLite + Rulebook Views + Schema Text)."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from src.cleaning import load_business, strip_accents
from src.mapping import propose_mapping
from src.views import (
    build_database,
    can_build_ledger,
    enable_readonly,
    item_match_key,
    safe_identifier,
    schema_text,
)

ROOT = Path(__file__).resolve().parents[1]
TRAIN_DIR = ROOT / "data" / "train"
PUBLIC_TEST_DIR = ROOT / "data" / "public_test"


def _write_csv(path: Path, rows: list[list[object]]) -> None:
    lines = []
    for r in rows:
        cells = []
        for c in r:
            s = "" if c is None else str(c)
            if any(ch in s for ch in (",", '"', "\n")):
                s = '"' + s.replace('"', '""') + '"'
            cells.append(s)
        lines.append(",".join(cells))
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------- Synthetic Shop Tests


def test_synthetic_shop_views_and_rulebook_rules(tmp_path: Path) -> None:
    """Build SQLite DB on a synthetic shop and verify all 5 views, rulebook rules, and schema_text."""
    biz_dir = tmp_path / "biz_syn"
    biz_dir.mkdir()

    # Create calendar.csv in parent directory
    _write_csv(
        tmp_path / "calendar.csv",
        [
            ["date", "year", "month", "day", "quarter", "iso_year", "iso_week", "day_of_week", "day_name_vi", "is_weekend", "lunar_year", "lunar_month", "lunar_day", "lunar_leap", "holiday_vi"],
            ["2025-05-01", 2025, 5, 1, 2, 2025, 18, 4, "Thứ Năm", 0, 2025, 4, 4, 0, "Ngày Quốc tế Lao động"],
            ["2025-05-02", 2025, 5, 2, 2, 2025, 18, 5, "Thứ Sáu", 0, 2025, 4, 5, 0, ""],
        ],
    )

    # Create README.md with unit conversion and column meanings
    (biz_dir / "README.md").write_text(
        "# Cửa hàng Tạp Hoá Synthetic\n"
        "Dữ liệu có đến hết 31/05/2025.\n\n"
        "Quy đổi đơn vị:\n"
        "- Sữa tươi 180ml: 1 thùng = 48 hộp\n\n"
        "Các cột trong `ban_hang.csv`:\n"
        "- `Mã HĐ`: Mã đơn hàng\n"
        "- `Ngày bán`: Ngày đặt đơn\n"
        "- `Thanh tien`: Thành tiền sau chiết khấu\n",
        encoding="utf-8",
    )

    # Create catalog table with aliases
    _write_csv(
        biz_dir / "danh_muc.csv",
        [
            ["Mã hàng", "Tên hàng", "Tên gọi khác", "Nhóm hàng", "ĐVT cơ bản", "Giá bán", "Giá vốn"],
            ["SP01", "Sữa tươi 180ml", "Sữa tươi hộp, Sua tuoi", "Sữa", "hộp", "8000", "6000"],
            ["SP02", "Mì Hảo Hảo tôm chua cay", "Mì HH", "Mì gói", "gói", "4500", "3500"],
        ],
    )

    # Create sales table covering:
    # - HD01: completed order with 2 lines (1 thùng Sữa tươi = 48 hộp + 10 gói Mì HH via alias) + Phí phục vụ
    # - HD02: shipping order ('Đang giao') -> included in v_valid_orders (§1)
    # - HD03: order with 1 normal line + 1 returned line ('Hoàn trả') -> ENTIRE order is 'tra_hang' (§1, §8)
    # - HD04: cancelled order ('Khách hủy') -> excluded from v_valid_orders, included in v_orders & v_lines (§5)
    # - Subtotal row ('Tổng tháng 05') -> dropped by split_summary_rows
    _write_csv(
        biz_dir / "ban_hang.csv",
        [
            ["Mã HĐ", "Ngày bán", "Trạng thái", "Mã SP", "Tên hàng", "ĐVT", "SL", "Đơn giá", "Thanh tien", "Khách hàng"],
            ["HD01", "2025-05-01", "Hoàn thành", "SP01", "Sua tuoi 180ml", "thùng", "1", "384000", "384000", "Nguyễn Văn A"],
            ["", "", "", "SP02", "Mì HH", "gói", "10", "4500", "45000", ""],
            ["", "", "", "", "Phí phục vụ", "lần", "1", "10000", "10000", ""],
            ["HD02", "2025-05-01", "Đang giao", "SP01", "Sữa tươi 180ml", "hộp", "5", "8000", "40000", "Khách lẻ"],
            ["HD03", "2025-05-02", "Hoàn thành", "SP01", "Sữa tươi 180ml", "hộp", "2", "8000", "16000", "Trần Thị B"],
            ["HD03", "2025-05-02", "Khách trả hàng", "SP02", "Mì Hảo Hảo tôm chua cay", "gói", "1", "4500", "4500", "Trần Thị B"],
            ["HD04", "2025-05-02", "Khách hủy", "SP02", "Mì Hảo Hảo tôm chua cay", "gói", "4", "4500", "18000", "KL"],
            ["Tổng tháng 05", "", "", "", "", "", "", "", "517500", ""],
        ],
    )

    conn = build_database(biz_dir)

    # 1. Check all 5 views exist
    views = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall()
    }
    assert {"v_lines", "v_valid_lines", "v_orders", "v_valid_orders", "v_items"} <= views

    # 2. Check cleaned tables, raw_ tables, and calendar exist
    tables = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {"lines", "items", "ban_hang", "raw_ban_hang", "danh_muc", "raw_danh_muc", "calendar"} <= tables

    # 3. Verify v_valid_orders contains only HD01 and HD02 (no 'huy' or 'tra_hang')
    valid_orders = conn.execute(
        "SELECT order_id, status, revenue, customer_name, customer_key FROM v_valid_orders ORDER BY order_id"
    ).fetchall()
    assert len(valid_orders) == 2
    assert valid_orders[0] == ("HD01", "hoan_thanh", 439000.0, "Nguyễn Văn A", "nguyen van a")
    # Walk-in 'Khách lẻ' on HD02 has NULL customer_name and NULL customer_key (§3)
    assert valid_orders[1] == ("HD02", "dang_giao", 40000.0, None, None)

    # 4. Verify v_orders has all 4 orders with HD03 resolved to 'tra_hang' and HD04 'huy'
    all_orders = dict(conn.execute("SELECT order_id, status FROM v_orders").fetchall())
    assert all_orders == {
        "HD01": "hoan_thanh",
        "HD02": "dang_giao",
        "HD03": "tra_hang",
        "HD04": "huy",
    }

    # 5. Verify qty_base and service fee handling in v_valid_lines
    top_items = conn.execute(
        """
        SELECT item_code, item_name, SUM(qty_base) AS total_qb
        FROM v_valid_lines
        WHERE is_service_fee = 0
        GROUP BY item_code, item_name
        ORDER BY total_qb DESC, COALESCE(item_code, item_name) ASC
        """
    ).fetchall()
    # SP01: 1 thùng (48 hộp) in HD01 + 5 hộp in HD02 = 53 hộp
    # SP02: 10 gói in HD01 (resolved from alias 'Mì HH')
    assert top_items == [
        ("SP01", "Sữa tươi 180ml", 53.0),
        ("SP02", "Mì Hảo Hảo tôm chua cay", 10.0),
    ]

    # 6. Verify v_items excludes 'Phí phục vụ' and includes aliases
    items_rows = conn.execute(
        "SELECT item_code, item_name, name_aliases, category, base_unit FROM v_items ORDER BY item_code"
    ).fetchall()
    assert len(items_rows) == 2
    assert items_rows[0][0] == "SP01"
    assert items_rows[0][1] == "Sữa tươi 180ml"
    assert "Sua tuoi 180ml" in items_rows[0][2]
    assert "Sữa tươi hộp" in items_rows[0][2]
    assert items_rows[1][0] == "SP02"
    assert "Mì HH" in items_rows[1][2]

    # 7. Verify schema_text order and contents
    stext = schema_text(conn, max_chars=13000)
    assert len(stext) <= 13000
    assert "v_valid_orders" in stext
    assert "v_items" in stext
    assert "danh_muc" in stext
    assert stext.index("v_valid_orders") < stext.index("TABLE `danh_muc`")

    # 8. Verify read-only mode works after views are created
    enable_readonly(conn)
    assert conn.execute("SELECT COUNT(*) FROM v_valid_orders").fetchone()[0] == 2
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DROP TABLE lines")

    conn.close()


def test_line_only_ledger_without_order_id(tmp_path: Path) -> None:
    """Rulebook §8: tables without an order_id column treat each row as 1 order in v_orders."""
    biz_dir = tmp_path / "biz_line_only"
    biz_dir.mkdir()
    _write_csv(
        biz_dir / "so_ban_hang.csv",
        [
            ["Ngày bán", "Tên mặt hàng", "Số lượng", "Đơn giá", "Tổng tiền", "Trạng thái xử lý"],
            ["2025-03-01", "Cà phê đen", "2", "20000", "40000", "Hoàn thành"],
            ["2025-03-01", "Trà đào", "1", "30000", "30000", "Hoàn thành"],
            ["2025-03-02", "Cà phê sữa", "1", "25000", "25000", "Huỷ"],
        ],
    )
    conn = build_database(biz_dir)
    n_orders = conn.execute("SELECT COUNT(*) FROM v_orders").fetchone()[0]
    n_valid = conn.execute("SELECT COUNT(*), SUM(revenue) FROM v_valid_orders").fetchone()
    assert n_orders == 3
    assert n_valid == (2, 70000.0)
    conn.close()


def test_non_ledger_shop_synthetic_and_dev_012(tmp_path: Path) -> None:
    """Verify non-ledger repair shops (synthetic and real dev_012) do not create sales views and do not crash."""
    biz_dir = tmp_path / "dev_repair"
    biz_dir.mkdir()
    _write_csv(
        biz_dir / "so_sua_xe.csv",
        [
            ["Ngày nhận", "Biển số", "Thợ chính", "Tiền công", "Tiền phụ tùng", "Tổng thu"],
            ["2025-01-05", "59A1-12345", "Anh Tư", "50000", "120000", "170000"],
            ["2025-01-06", "59B2-67890", "Anh Năm", "80000", "0", "80000"],
        ],
    )
    tables = load_business(biz_dir)
    mapping = propose_mapping(tables)
    assert can_build_ledger(tables, mapping) is False

    conn = build_database(biz_dir)
    views = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall()]
    assert views == []
    tbls = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"so_sua_xe", "raw_so_sua_xe"} <= tbls
    stext = schema_text(conn)
    assert "NON-LEDGER BUSINESS (NO SALES VIEWS)" in stext
    assert "so_sua_xe" in stext
    conn.close()

    # Also test real dev_012 if present
    dev_012_dir = PUBLIC_TEST_DIR / "data" / "dev_012"
    if dev_012_dir.is_dir():
        conn12 = build_database(dev_012_dir)
        views12 = [r[0] for r in conn12.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall()]
        assert views12 == []
        tbls12 = {r[0] for r in conn12.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert {"so_sua_xe", "raw_so_sua_xe", "danh_sach_tho", "raw_danh_sach_tho", "calendar"} <= tbls12
        stext12 = schema_text(conn12)
        assert "NON-LEDGER BUSINESS (NO SALES VIEWS)" in stext12
        assert conn12.execute("SELECT COUNT(*) FROM so_sua_xe").fetchone()[0] > 1000
        conn12.close()


# ---------------------------------------------------------------------- Real Train Benchmark Tests


@pytest.mark.skipif(not (TRAIN_DIR / "data" / "biz_102").is_dir(), reason="train data not available")
def test_five_canonical_sql_examples_from_views_doc() -> None:
    """Verify the 5 SQL query templates in `docs/VIEWS.md` produce exact official answers on `biz_102`."""
    answers = {
        json.loads(line)["id"]: json.loads(line)["answer"]
        for line in (TRAIN_DIR / "answers.jsonl").open(encoding="utf-8")
    }
    conn = build_database(TRAIN_DIR / "data" / "biz_102", readonly=True)

    # 1. Monthly revenue (q_79dbf0f33660: 01/2025 -> 435803500)
    rev_01 = conn.execute(
        "SELECT CAST(ROUND(SUM(revenue)) AS INTEGER) FROM v_valid_orders WHERE order_month = '2025-01'"
    ).fetchone()[0]
    assert rev_01 == answers["q_79dbf0f33660"] == 435803500

    # 2. Cancelled order count (q_1bd200cd8993: 02/2025 -> 61)
    cancelled_02 = conn.execute(
        """
        SELECT COUNT(*)
        FROM v_orders
        WHERE order_month = '2025-02'
          AND status = 'huy'
        """
    ).fetchone()[0]
    assert cancelled_02 == answers["q_1bd200cd8993"] == 61

    # 3. Cancellation rate (q_3379b46319a8: 02/2025 -> 2.58)
    cancel_rate_02 = conn.execute(
        """
        SELECT ROUND(
            SUM(CASE WHEN status = 'huy' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) + 1e-9,
            2
        )
        FROM v_orders
        WHERE order_month = '2025-02'
        """
    ).fetchone()[0]
    assert cancel_rate_02 == answers["q_3379b46319a8"] == 2.58

    # 4. Top 3 best-selling items by converted base quantity (q_dfe2b9e2e7b3: 02/2026)
    top3_feb = [
        r[0]
        for r in conn.execute(
            """
            SELECT
                item_name,
                SUM(qty_base) AS total_qty_base
            FROM v_valid_lines
            WHERE order_month = '2026-02'
              AND is_service_fee = 0
            GROUP BY item_code, item_name
            ORDER BY total_qty_base DESC, COALESCE(item_code, item_name) ASC
            LIMIT 3
            """
        ).fetchall()
    ]
    assert top3_feb == answers["q_dfe2b9e2e7b3"]

    # 5. Average order value rounded half-up (q_dcc0b785c232: 02/2025 -> 158315)
    aov_02 = conn.execute(
        """
        SELECT CAST(SUM(revenue) * 1.0 / COUNT(*) + 0.5 AS INTEGER)
        FROM v_valid_orders
        WHERE order_month = '2025-02'
        """
    ).fetchone()[0]
    assert aov_02 == answers["q_dcc0b785c232"] == 158315

    conn.close()


@pytest.mark.skipif(not (TRAIN_DIR / "data" / "biz_101").is_dir(), reason="train data not available")
def test_monthly_revenue_benchmark_via_v_valid_orders() -> None:
    """Verify `SUM(revenue)` from `v_valid_orders` matches official answers across all 8 benchmark shops (36/36) + biz_110."""
    benchmark_shops = [
        "biz_101",
        "biz_102",
        "biz_103",
        "biz_105",
        "biz_107",
        "biz_112",
        "biz_114",
        "biz_117",
        "biz_110",
    ]
    questions = [json.loads(line) for line in (TRAIN_DIR / "questions.jsonl").open(encoding="utf-8")]
    answers = {
        json.loads(line)["id"]: json.loads(line)
        for line in (TRAIN_DIR / "answers.jsonl").open(encoding="utf-8")
    }

    total_checked = 0
    for shop in benchmark_shops:
        biz_dir = TRAIN_DIR / "data" / shop
        conn = build_database(biz_dir)

        # Ensure no 'huy' or 'tra_hang' in v_valid_orders
        bad_cnt = conn.execute(
            "SELECT COUNT(*) FROM v_valid_orders WHERE status IN ('huy', 'tra_hang')"
        ).fetchone()[0]
        assert bad_cnt == 0, f"{shop} has cancelled/returned orders in v_valid_orders"

        for q in questions:
            if q["business_id"] != shop or answers[q["id"]]["type"] != "number":
                continue
            s = strip_accents(q["question"]).lower()
            m = re.search(r"thang (\d{1,2})(?:/| nam )(\d{4})", s)
            if not m or not re.search(r"doanh thu|dthu", s):
                continue
            if re.search(
                r"nhom|khach|\bdon\b|\bca\b|nhan vien|tra bang|so voi|%|phan tram|ngay|hoat chat|ke don|size|trung binh|binh quan|moi|quy|mat hang|mon |ban chay|top|doanh thu cua (?!cua hang)|dthu cua (?!cua hang)",
                s,
            ):
                continue

            mo, yr = int(m.group(1)), int(m.group(2))
            ym = f"{yr:04d}-{mo:02d}"
            as_of = q["as_of_date"]

            got = conn.execute(
                """
                SELECT CAST(ROUND(COALESCE(SUM(revenue), 0)) AS INTEGER)
                FROM v_valid_orders
                WHERE order_month = ? AND order_date <= ?
                """,
                (ym, as_of),
            ).fetchone()[0]
            expected = answers[q["id"]]["answer"]
            assert got == expected, f"Mismatch on {shop} {q['id']} ({ym}): got {got}, expected {expected}"
            total_checked += 1

        conn.close()

    assert total_checked >= 38  # 36 from the 8 benchmark shops + 2 from biz_110


def test_safe_identifier_and_item_match_key() -> None:
    assert safe_identifier("Mã hóa đơn") == "ma_hoa_don"
    assert safe_identifier("Tổng tiền (VNĐ)") == "tong_tien_vnd"
    assert safe_identifier("123_abc") == "col_123_abc"
    assert safe_identifier("select") == "select_col"
    assert item_match_key("Paracetamol 500 mg") == item_match_key("Paracetamol 500mg")
