"""Unit and integration tests for `src/views.py` (Task T4: SQLite + Rulebook Views + Schema Text)."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from src.cleaning import load_business, strip_accents
from src.data_paths import public_test_dir, train_dir
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
TRAIN_DIR = train_dir()
PUBLIC_TEST_DIR = public_test_dir()


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

    # 6. Verify v_items excludes 'Phí phục vụ', includes aliases, and keeps pharmacy columns NULL on non-pharmacy shops
    items_rows = conn.execute(
        "SELECT item_code, item_name, name_aliases, category, base_unit, active_ingredient, is_prescription FROM v_items ORDER BY item_code"
    ).fetchall()
    assert len(items_rows) == 2
    assert items_rows[0][0] == "SP01"
    assert items_rows[0][1] == "Sữa tươi 180ml"
    assert "Sua tuoi 180ml" in items_rows[0][2]
    assert "Sữa tươi hộp" in items_rows[0][2]
    assert items_rows[0][5] is None and items_rows[0][6] is None
    assert items_rows[1][0] == "SP02"
    assert "Mì HH" in items_rows[1][2]
    assert items_rows[1][5] is None and items_rows[1][6] is None

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


def test_pharmacy_nameless_drug_table_and_normalization(tmp_path: Path) -> None:
    """Supplementary drug tables without a name column populate active_ingredient & is_prescription on v_items."""
    biz_dir = tmp_path / "biz_pharmacy_syn"
    biz_dir.mkdir()

    _write_csv(
        biz_dir / "danh_muc.csv",
        [
            ["Mã hàng", "Tên hàng", "ĐVT", "Giá bán"],
            ["SP01", "Panadol Extra", "vỉ", "18000"],
            ["SP02", "Amoxicillin 500mg", "vỉ", "15000"],
            ["SP03", "Hapacol 250", "gói", "3000"],
            ["SP04", "Khẩu trang y tế", "hộp", "35000"],
        ],
    )
    # Drug attribute table WITHOUT a name column, with CamelCase headers, an unrelated ID column,
    # mixed case/whitespace codes, varied raw Rx flags, and a duplicate row with blank attributes.
    _write_csv(
        biz_dir / "thong_tin_thuoc.csv",
        [
            ["IDCuaHang", "MaHangHoa", "ThanhPhanChinh", "BanTheoDon"],
            ["CH01", "sp 01", "Paracetamol  +   Cafein", "Không"],
            ["CH01", "SP02", "Amoxicillin", "x"],
            ["CH01", "SP02", "", ""],
            ["CH01", "SP03", "Paracetamol", "FALSE"],
        ],
    )
    _write_csv(
        biz_dir / "ban_hang.csv",
        [
            ["Mã HĐ", "Ngày bán", "Trạng thái", "Mã SP", "Tên hàng", "ĐVT", "SL", "Đơn giá", "Thanh tiền"],
            ["HD01", "2026-06-01", "Hoàn thành", "SP01", "Panadol Extra", "vỉ", "2", "18000", "36000"],
            ["HD01", "2026-06-01", "Hoàn thành", "SP02", "Amoxicillin 500mg", "vỉ", "1", "15000", "15000"],
            ["HD02", "2026-06-02", "Hoàn thành", "SP03", "Hapacol 250", "gói", "5", "3000", "15000"],
            ["HD02", "2026-06-02", "Hoàn thành", "SP04", "Khẩu trang y tế", "hộp", "1", "35000", "35000"],
        ],
    )

    conn = build_database(biz_dir)
    rows = conn.execute(
        "SELECT item_code, active_ingredient, is_prescription FROM v_items ORDER BY item_code"
    ).fetchall()
    assert rows == [
        ("SP01", "Paracetamol + Cafein", "0"),
        ("SP02", "Amoxicillin", "1"),
        ("SP03", "Paracetamol", "0"),
        ("SP04", None, "0"),
    ]

    # Rulebook §6: 'Paracetamol' revenue excludes combination 'Paracetamol + Cafein'
    para_rev = conn.execute(
        """
        SELECT CAST(ROUND(COALESCE(SUM(l.line_amount), 0)) AS INTEGER)
        FROM v_valid_lines l
        JOIN v_items i ON COALESCE(l.item_code, l.item_name) = COALESCE(i.item_code, i.item_name)
        WHERE l.is_service_fee = 0 AND i.active_ingredient = 'Paracetamol'
        """
    ).fetchone()[0]
    assert para_rev == 15000

    # Rulebook §6: Rx revenue percentage = 15000 / 101000 * 100 = 14.85
    rx_pct = conn.execute(
        """
        SELECT ROUND(
            SUM(CASE WHEN i.is_prescription = '1' THEN l.line_amount ELSE 0 END) * 100.0
            / NULLIF(SUM(l.line_amount), 0),
            2
        )
        FROM v_valid_lines l
        LEFT JOIN v_items i
            ON l.is_service_fee = 0
           AND COALESCE(l.item_code, l.item_name) = COALESCE(i.item_code, i.item_name)
        """
    ).fetchone()[0]
    assert rx_pct == 14.85
    conn.close()


def test_conversion_price_column_not_confused_with_prescription(tmp_path: Path) -> None:
    """Ensure 'Giá bán theo đơn vị quy đổi' is not matched as an is_prescription column."""
    biz_dir = tmp_path / "biz_non_pharmacy_conv"
    biz_dir.mkdir()
    _write_csv(
        biz_dir / "san_pham.csv",
        [
            ["Mã SP", "Tên SP", "ĐVT"],
            ["SP01", "Nước suối", "chai"],
        ],
    )
    _write_csv(
        biz_dir / "don_vi_quy_doi.csv",
        [
            ["Mã SP", "Đơn vị", "Bằng", "Giá bán theo đơn vị quy đổi"],
            ["SP01", "thùng", "24", "120000"],
        ],
    )
    _write_csv(
        biz_dir / "ban_hang.csv",
        [
            ["Mã HĐ", "Ngày bán", "Mã SP", "Tên SP", "ĐVT", "SL", "Đơn giá", "Thanh tiền"],
            ["HD01", "2026-06-01", "SP01", "Nước suối", "chai", "2", "5000", "10000"],
        ],
    )
    conn = build_database(biz_dir)
    assert conn.execute("SELECT COUNT(*), COUNT(active_ingredient), COUNT(is_prescription) FROM v_items").fetchone() == (1, 0, 0)
    conn.close()


def test_purchase_views_synthetic_header_detail_opening_cancelled_and_units(tmp_path: Path) -> None:
    """Cover §5 purchase views: header+detail, supplier lookup, cancelled exclusion, opening stock inclusion, 2 units, and item aliases."""
    biz_dir = tmp_path / "biz_purchase_full"
    biz_dir.mkdir()
    (biz_dir / "README.md").write_text(
        "# Quy đổi\n- Bò húc: 1 thùng = 24 lon\nGhi tắt: BH = Bò húc\n",
        encoding="utf-8",
    )
    _write_csv(
        biz_dir / "san_pham.csv",
        [
            ["Mã hàng", "Tên hàng", "ĐVT", "Ghi tắt"],
            ["SP01", "Bò húc", "lon", "BH"],
            ["SP02", "Trà xanh 0 độ", "chai", ""],
        ],
    )
    _write_csv(
        biz_dir / "ban_hang.csv",
        [
            ["Mã HĐ", "Ngày bán", "Trạng thái", "Mã hàng", "Tên hàng", "ĐVT", "SL", "Đơn giá", "Thành tiền"],
            ["HD01", "2026-05-05", "Hoàn thành", "SP01", "BH", "lon", "14", "10000", "140000"],
            ["HD02", "2026-05-06", "Hủy", "SP01", "Bò húc", "lon", "100", "10000", "1000000"],
        ],
    )
    _write_csv(
        biz_dir / "nha_cung_cap.csv",
        [
            ["MaNhaCungCap", "TenGoi"],
            ["NCC01", "Công ty Minh Phát"],
            ["NCC02", "Đại lý Hòa Bình"],
        ],
    )
    _write_csv(
        biz_dir / "phieu_nhap.csv",
        [
            ["MaPhieuNhap", "NgayNhapKho", "MaNhaCungCap", "TrangThai", "DienGiai"],
            ["PN01", "2026-05-01", "NCC01", "Đã nhập", "Nhập đầu kỳ"],
            ["PN02", "2026-05-03", "NCC02", "Đã nhập", ""],
            ["PN03", "2026-05-04", "NCC01", "Đã hủy", "Nhập nhầm"],
        ],
    )
    _write_csv(
        biz_dir / "chi_tiet_nhap.csv",
        [
            ["MaPhieuNhap", "MaHangHoa", "TenHang", "DonViTinh", "SL", "DonGiaNhap"],
            ["PN01", "SP01", "Bò húc", "thùng", "1", "192000"],
            ["PN02", "SP01", "BH", "thùng", "2", "216000"],
            ["PN02", "SP01", "Bò húc", "lon", "12", "8500"],
            ["PN03", "SP02", "Trà xanh 0 độ", "chai", "10", "6000"],
        ],
    )

    conn = build_database(biz_dir)

    # All lines vs valid lines (cancelled PN03 excluded, opening stock PN01 included)
    assert conn.execute("SELECT COUNT(*) FROM v_purchase_lines").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM v_valid_purchase_lines").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM v_purchases").fetchone()[0] == 3
    assert conn.execute("SELECT is_opening_stock, supplier, supplier_code FROM v_valid_purchase_lines WHERE receipt_id = 'PN01'").fetchone() == (
        1, "Công ty Minh Phát", "NCC01"
    )
    assert conn.execute("SELECT is_cancelled FROM v_purchases WHERE receipt_id = 'PN03'").fetchone()[0] == 1

    # Total valid purchase spend in 2026-05: 192000 + 2*216000 + 12*8500 = 726000
    assert conn.execute("SELECT SUM(line_amount) FROM v_valid_purchase_lines WHERE receipt_month = '2026-05'").fetchone()[0] == 726000.0

    # Weighted average unit cost per purchase unit (NOT simple arithmetic average (192000+216000)/2 = 204000)
    avg_thung = conn.execute(
        "SELECT SUM(line_amount) * 1.0 / SUM(qty) FROM v_valid_purchase_lines WHERE item_name = 'Bò húc' AND unit = 'thùng'"
    ).fetchone()[0]
    assert avg_thung == 208000.0
    avg_lon = conn.execute(
        "SELECT SUM(line_amount) * 1.0 / SUM(qty) FROM v_valid_purchase_lines WHERE item_name = 'Bò húc' AND unit = 'lon'"
    ).fetchone()[0]
    assert avg_lon == 8500.0

    # Top valid supplier by spend: NCC02 (534000) beats NCC01 (192000 because PN03 is cancelled)
    top_sup = conn.execute(
        "SELECT supplier, SUM(line_amount) AS amt FROM v_valid_purchase_lines GROUP BY supplier ORDER BY amt DESC LIMIT 1"
    ).fetchone()
    assert top_sup == ("Đại lý Hòa Bình", 534000.0)

    # Canonical item matching + conversion + purchase minus sales in base unit (`lon`)
    # Purchases: 1*24 + 2*24 + 12 = 84 lon; Sales valid: 14 lon -> Net = 70 lon
    p_base = conn.execute("SELECT SUM(qty_base) FROM v_valid_purchase_lines WHERE item_name = 'Bò húc'").fetchone()[0]
    s_base = conn.execute("SELECT SUM(qty_base) FROM v_valid_lines WHERE item_name = 'Bò húc'").fetchone()[0]
    assert p_base == 84.0
    assert s_base == 14.0
    assert p_base - s_base == 70.0

    st = schema_text(conn)
    assert "v_valid_purchase_lines" in st
    assert "v_purchase_lines" in st
    assert "v_purchases" in st
    conn.close()


def test_no_purchase_views_when_absent_and_null_cost_when_unrecorded(tmp_path: Path) -> None:
    """Verify shops without purchases have no v_purchase* views, and shops without purchase prices keep cost/amount NULL."""
    # 1. Shop without purchase tables -> no v_purchase* views
    sales_only = tmp_path / "biz_sales_only"
    sales_only.mkdir()
    _write_csv(
        sales_only / "ban_hang.csv",
        [
            ["Mã HĐ", "Ngày", "Tên hàng", "ĐVT", "SL", "Thành tiền"],
            ["HD01", "2026-05-01", "Nước suối", "chai", "2", "10000"],
        ],
    )
    conn1 = build_database(sales_only)
    views1 = {r[0] for r in conn1.execute("SELECT name FROM sqlite_master WHERE type IN ('view', 'table')").fetchall()}
    assert "v_purchase_lines" not in views1
    assert "v_valid_purchase_lines" not in views1
    assert "v_purchases" not in views1
    conn1.close()

    # 2. Shop with header+detail purchases that record qty only (no cost, no amount, no unit)
    qty_only = tmp_path / "biz_purchase_qty_only"
    qty_only.mkdir()
    _write_csv(
        qty_only / "danh_muc.csv",
        [
            ["Mã SKU", "Tên sản phẩm", "Đơn vị"],
            ["SKU01", "Sữa tươi", "hộp"],
        ],
    )
    _write_csv(
        qty_only / "ban_hang.csv",
        [
            ["Mã HĐ", "Ngày", "Mã SKU", "SL", "Thành tiền"],
            ["HD01", "2026-05-02", "SKU01", "3", "30000"],
        ],
    )
    _write_csv(
        qty_only / "DonNhapHang.csv",
        [
            ["Mã đơn nhập", "Ngày nhập", "Mã nhà cung cấp"],
            ["DN01", "2026-05-01", "NCC01"],
        ],
    )
    _write_csv(
        qty_only / "DonNhapHang_ChiTiet.csv",
        [
            ["Mã đơn nhập", "Mã SKU", "Số lượng nhập"],
            ["DN01", "SKU01", "20"],
        ],
    )
    conn2 = build_database(qty_only)
    row = conn2.execute(
        "SELECT item_name, qty, qty_base, base_unit, unit, unit_cost, line_amount FROM v_valid_purchase_lines"
    ).fetchone()
    assert row == ("Sữa tươi", 20.0, 20.0, "hộp", None, None, None)
    assert conn2.execute("SELECT total_amount FROM v_purchases WHERE receipt_id = 'DN01'").fetchone()[0] is None
    assert "does NOT record purchase prices/amounts" in schema_text(conn2)
    conn2.close()


def test_camelcase_unit_conversion_table_and_purchase_qty_base(tmp_path: Path) -> None:
    """CamelCase conversion tables such as DanhSachDonViTinh (without explicit base column) must convert purchase qty_base."""
    biz_dir = tmp_path / "biz_camelcase_conv"
    biz_dir.mkdir()
    _write_csv(
        biz_dir / "DanhSachSanPham.csv",
        [
            ["Mã hàng", "Tên hàng", "ĐVT"],
            ["SP0049", "Bánh croissant", "cái"],
        ],
    )
    _write_csv(
        biz_dir / "DanhSachDonViTinh.csv",
        [
            ["Mã hàng", "ĐVT", "Quy đổi", "Giá bán"],
            ["SP0049", "hộp", "6", "222000"],
        ],
    )
    _write_csv(
        biz_dir / "DanhSachHoaDon.csv",
        [
            ["Mã hóa đơn", "Thời gian", "Trạng thái"],
            ["ORD01", "2025-10-05", "xong"],
        ],
    )
    _write_csv(
        biz_dir / "DanhSachHoaDonChiTiet.csv",
        [
            ["Mã hóa đơn", "Mã hàng", "Tên hàng", "Đơn vị tính", "Số lượng", "Đơn giá", "Thành tiền"],
            ["ORD01", "SP0049", "Bánh croissant", "cái", "163", "37000", "6031000"],
        ],
    )
    _write_csv(
        biz_dir / "DanhSachNhapHang.csv",
        [
            ["Mã nhập hàng", "Thời gian", "Mã NCC", "Trạng thái"],
            ["PN01", "2025-10-02", "NCC01", "Đã nhập hàng"],
        ],
    )
    _write_csv(
        biz_dir / "DanhSachChiTietNhapHang.csv",
        [
            ["Mã nhập hàng", "Mã hàng", "ĐVT", "Số lượng", "Đơn giá"],
            ["PN01", "SP0049", "hộp", "28", "90000"],
        ],
    )
    conn = build_database(biz_dir)
    factor, qty_base, bu = conn.execute(
        "SELECT factor, qty_base, base_unit FROM v_valid_purchase_lines WHERE item_code = 'SP0049'"
    ).fetchone()
    assert factor == 6.0
    assert qty_base == 168.0
    assert bu == "cái"
    sold_base = conn.execute(
        "SELECT SUM(qty_base) FROM v_valid_lines WHERE item_code = 'SP0049'"
    ).fetchone()[0]
    assert qty_base - sold_base == 5.0
    conn.close()


def test_pharmacy_etc_flag_and_unrecognized_rx_value_stays_null(tmp_path: Path) -> None:
    """`ETC` means prescription; a filled Rx cell we cannot read stays NULL instead of defaulting to '0'."""
    biz_dir = tmp_path / "biz_pharmacy_etc"
    biz_dir.mkdir()
    _write_csv(
        biz_dir / "danh_muc.csv",
        [
            ["Mã hàng", "Tên hàng", "ĐVT", "Giá bán"],
            ["SP01", "Augmentin 625", "vỉ", "90000"],
            ["SP02", "Vitamin C 500", "vỉ", "10000"],
            ["SP03", "Thuốc lạ", "vỉ", "20000"],
            ["SP04", "Bông y tế", "gói", "5000"],
        ],
    )
    _write_csv(
        biz_dir / "danh_sach_thuoc.csv",
        [
            ["Mã hàng", "Hoạt chất", "Phân loại kê đơn"],
            ["SP01", "Amoxicillin + Acid clavulanic", "ETC"],
            ["SP02", "Acid ascorbic", "OTC"],
            ["SP03", "Chất X", "???"],
        ],
    )
    _write_csv(
        biz_dir / "ban_hang.csv",
        [
            ["Mã HĐ", "Ngày bán", "Trạng thái", "Mã SP", "Tên hàng", "ĐVT", "SL", "Đơn giá", "Thanh tiền"],
            ["HD01", "2026-06-01", "Hoàn thành", "SP01", "Augmentin 625", "vỉ", "1", "90000", "90000"],
            ["HD01", "2026-06-01", "Hoàn thành", "SP02", "Vitamin C 500", "vỉ", "1", "10000", "10000"],
            ["HD02", "2026-06-02", "Hoàn thành", "SP03", "Thuốc lạ", "vỉ", "1", "20000", "20000"],
            ["HD02", "2026-06-02", "Hoàn thành", "SP04", "Bông y tế", "gói", "1", "5000", "5000"],
        ],
    )
    conn = build_database(biz_dir)
    rows = conn.execute("SELECT item_code, is_prescription FROM v_items ORDER BY item_code").fetchall()
    conn.close()
    assert rows == [("SP01", "1"), ("SP02", "0"), ("SP03", None), ("SP04", "0")]


@pytest.mark.parametrize(
    "note, expected",
    [
        ("Anh Huy giao hàng", False),
        ("NCC Huy Hoàng", False),
        ("anh huy giao", False),
        ("Đã huỷ", True),
        ("Hủy do sai giá", True),
        ("phieu huy", True),
        ("da huy phieu", True),
        ("không hủy", False),
        ("Cancelled", True),
        ("nhập đầu kỳ", False),
    ],
)
def test_purchase_note_cancel_detection_ignores_person_named_huy(note: str, expected: bool) -> None:
    from src.views import _note_says_cancelled

    assert _note_says_cancelled(note) is expected


def test_purchase_note_with_person_named_huy_is_not_cancelled(tmp_path: Path) -> None:
    """A receipt whose note mentions a person named Huy still counts towards purchase spend (§5)."""
    biz_dir = tmp_path / "biz_purchase_huy"
    biz_dir.mkdir()
    _write_csv(
        biz_dir / "ban_hang.csv",
        [
            ["Mã HĐ", "Ngày bán", "Trạng thái", "Tên hàng", "ĐVT", "SL", "Đơn giá", "Thanh tiền"],
            ["HD01", "2026-06-01", "Hoàn thành", "Cà phê sữa", "ly", "2", "25000", "50000"],
        ],
    )
    _write_csv(
        biz_dir / "so_nhap_hang.csv",
        [
            ["Số phiếu", "Ngày nhập", "Nhà cung cấp", "Tên mặt hàng", "ĐVT", "SL nhập", "Giá nhập", "Thành tiền", "Ghi chú"],
            ["PN01", "2026-06-01", "NCC A", "Cà phê sữa", "ly", "10", "10000", "100000", "Anh Huy giao"],
            ["PN02", "2026-06-02", "NCC A", "Cà phê sữa", "ly", "5", "10000", "50000", "Đã huỷ"],
        ],
    )
    conn = build_database(biz_dir)
    rows = conn.execute("SELECT receipt_id, is_cancelled FROM v_purchases ORDER BY receipt_id").fetchall()
    spend = conn.execute("SELECT SUM(line_amount) FROM v_valid_purchase_lines").fetchone()[0]
    conn.close()
    assert rows == [("PN01", 0), ("PN02", 1)]
    assert spend == 100000


_CALENDAR_CANDIDATES = [
    TRAIN_DIR / "calendar.csv",
]
_CALENDAR_CSV = next((p for p in _CALENDAR_CANDIDATES if p.is_file()), None)


@pytest.mark.skipif(_CALENDAR_CSV is None, reason="calendar.csv not present")
def test_schema_text_keeps_calendar_when_budget_cuts_raw_tables(tmp_path: Path) -> None:
    """The prompt budget cuts the tail; the calendar must sit before the cleaned/raw tables so it survives."""
    biz_dir = tmp_path / "biz_budget"
    biz_dir.mkdir()
    _write_csv(
        biz_dir / "ban_hang.csv",
        [
            ["Mã HĐ", "Ngày bán", "Trạng thái", "Tên hàng", "ĐVT", "SL", "Đơn giá", "Thanh tiền"],
            ["HD01", "2026-06-01", "Hoàn thành", "Cà phê sữa", "ly", "2", "25000", "50000"],
        ],
    )
    for k in range(6):  # bulky auxiliary tables that will not fit in a small budget
        _write_csv(
            biz_dir / f"phu_luc_{k}.csv",
            [[f"Cột dài số {i} của phụ lục {k}" for i in range(8)]] + [[f"giá trị {k}-{r}-{i}" for i in range(8)] for r in range(3)],
        )
    conn = build_database(biz_dir, calendar_path=_CALENDAR_CSV)
    full = schema_text(conn, max_chars=10**7)
    cal_pos = full.index("=== CALENDAR TABLE ===")
    tables_pos = full.index("=== 2. CLEANED AUXILIARY & SOURCE TABLES ===")
    assert cal_pos < tables_pos
    cut = schema_text(conn, max_chars=tables_pos + 300)
    conn.close()
    assert len(cut) < len(full)
    assert "=== CALENDAR TABLE ===" in cut


def _views(conn: sqlite3.Connection) -> set[str]:
    return {n for (n,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'view'")}


def test_stock_from_lots_counts_returns_and_ignores_cancelled_orders(tmp_path: Path) -> None:
    """Remaining per lot = qty in − qty on non-cancelled orders + returned qty; v_stock sums the lots."""
    biz_dir = tmp_path / "biz_lots"
    biz_dir.mkdir()
    _write_csv(
        biz_dir / "danh_muc.csv",
        [
            ["Mã hàng", "Tên hàng", "ĐVT", "Giá bán"],
            ["SP01", "Amoxicillin 500mg hộp 10 vỉ x 10 viên", "viên", "1500"],
            ["SP02", "Vitamin C 500", "viên", "500"],
        ],
    )
    _write_csv(
        biz_dir / "quy_doi_don_vi.csv",
        [["Mã hàng", "Tên hàng", "ĐVT", "Quy đổi", "ĐVT cơ bản"],
         ["SP01", "Amoxicillin 500mg hộp 10 vỉ x 10 viên", "vỉ", "10", "viên"]],
    )
    _write_csv(
        biz_dir / "ban_hang.csv",
        [
            ["Mã HĐ", "Ngày bán", "Trạng thái", "Mã SP", "Tên hàng", "ĐVT", "SL", "Đơn giá", "Thanh tiền"],
            ["HD01", "2026-06-01", "Hoàn thành", "SP01", "Amoxicillin 500mg hộp 10 vỉ x 10 viên", "viên", "30", "1500", "45000"],
            ["HD02", "2026-06-02", "Đã huỷ", "SP01", "Amoxicillin 500mg hộp 10 vỉ x 10 viên", "viên", "20", "1500", "30000"],
            ["HD03", "2026-06-03", "Trả hàng", "SP02", "Vitamin C 500", "viên", "10", "500", "5000"],
        ],
    )
    _write_csv(
        biz_dir / "lo_hang.csv",
        [
            ["Mã nhập hàng", "Mã hàng", "Lô", "Hạn sử dụng", "Số lượng (ĐVT cơ bản)"],
            ["PN01", "SP01", "L-A", "2026-07-15", "100"],
            ["PN02", "SP01", "L-B", "2027-01-01", "50"],
            ["PN02", "SP02", "L-C", "2026-06-20", "40"],
        ],
    )
    _write_csv(
        biz_dir / "hoa_don_chi_tiet_lo.csv",
        [
            ["Mã hóa đơn", "Lô", "Số lượng (ĐVT cơ bản)", "Số lượng trả (ĐVT cơ bản)"],
            ["HD01", "L-A", "30", "0"],
            ["HD02", "L-B", "20", "0"],
            ["HD03", "L-C", "10", "4"],
        ],
    )
    conn = build_database(biz_dir)
    assert {"v_stock", "v_lots", "v_item_units"} <= _views(conn)
    lots = dict(conn.execute("SELECT lot, qty_remaining FROM v_lots").fetchall())
    stock = dict(conn.execute("SELECT item_code, stock_qty_base FROM v_stock").fetchall())
    hop = conn.execute(
        "SELECT factor FROM v_item_units WHERE item_code = 'SP01' AND unit = 'vỉ'"
    ).fetchone()
    nearest = conn.execute(
        "SELECT MIN(expiry_date) FROM v_lots WHERE item_code = 'SP01' AND qty_remaining > 0 AND expiry_date >= '2026-06-03'"
    ).fetchone()[0]
    conn.close()
    assert lots == {"L-A": 70.0, "L-B": 50.0, "L-C": 34.0}  # cancelled HD02 does not consume L-B; 4 returned to L-C
    assert stock == {"SP01": 120.0, "SP02": 34.0}
    assert hop == (10.0,)
    assert nearest == "2026-07-15"


def test_stock_report_in_large_unit_is_converted_and_absent_report_means_no_view(tmp_path: Path) -> None:
    biz_dir = tmp_path / "biz_report"
    biz_dir.mkdir()
    _write_csv(
        biz_dir / "ban_hang.csv",
        [
            ["Mã HĐ", "Ngày bán", "Trạng thái", "Tên hàng", "ĐVT", "SL", "Đơn giá", "Thanh tiền"],
            ["HD01", "2026-06-01", "Hoàn thành", "Bia Tiger lon", "lon", "6", "20000", "120000"],
            ["HD02", "2026-06-02", "Hoàn thành", "Bia Tiger lon", "thùng", "1", "400000", "400000"],
        ],
    )
    _write_csv(
        biz_dir / "quy_doi.csv",
        [["Tên hàng", "ĐVT", "Quy đổi", "ĐVT cơ bản"], ["Bia Tiger lon", "thùng", "24", "lon"]],
    )
    conn = build_database(biz_dir)
    assert "v_stock" not in _views(conn)  # no stock report, no lots -> stock questions stay unanswerable
    conn.close()

    _write_csv(biz_dir / "ton_kho.csv", [["Hàng hóa", "Đơn vị tính", "Tồn cuối"], ["Bia Tiger lon", "thùng", "2"]])
    conn = build_database(biz_dir)
    row = conn.execute("SELECT stock_qty_base, stock_date, source FROM v_stock WHERE item_name = 'Bia Tiger lon'").fetchone()
    text = schema_text(conn)
    conn.close()
    assert row == (48.0, "2026-06-02", "report")
    assert "v_stock" in text


def test_stock_and_purchase_failures_do_not_break_the_shop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A crash in the optional purchase/stock builders drops only those views; sales views still work."""
    import src.stock
    import src.views

    def boom(*_a: object, **_k: object) -> None:
        raise ValueError("unseen layout")

    monkeypatch.setattr(src.stock, "create_stock_views", boom)
    monkeypatch.setattr(src.views, "_build_purchase_lines_df", boom)
    biz_dir = tmp_path / "biz_guard"
    biz_dir.mkdir()
    _write_csv(
        biz_dir / "ban_hang.csv",
        [
            ["Mã HĐ", "Ngày bán", "Trạng thái", "Tên hàng", "ĐVT", "SL", "Đơn giá", "Thanh tiền"],
            ["HD01", "2026-06-01", "Hoàn thành", "Cà phê sữa", "ly", "2", "25000", "50000"],
        ],
    )
    conn = build_database(biz_dir)
    views = _views(conn)
    revenue = conn.execute("SELECT SUM(revenue) FROM v_valid_orders").fetchone()[0]
    text = schema_text(conn)
    conn.close()
    assert "v_valid_orders" in views and not ({"v_stock", "v_purchases"} & views)
    assert revenue == 50000
    assert "v_valid_orders" in text


def test_stock_card_gives_balance_by_date_and_feeds_v_stock(tmp_path: Path) -> None:
    """A stock card with CamelCase headers (`SLQuyDoi`, `TonCuoi`) yields v_stock_card and the end-of-data v_stock."""
    biz_dir = tmp_path / "biz_card"
    biz_dir.mkdir()
    _write_csv(
        biz_dir / "san_pham.csv",
        [["MaHangHoa", "TenGoi", "DonViCoSo", "GiaBanLe"], ["SP01", "Nước suối 500ml", "chai", "5000"]],
    )
    _write_csv(
        biz_dir / "ban_hang.csv",
        [
            ["Mã HĐ", "Ngày bán", "Trạng thái", "Mã SP", "Tên hàng", "ĐVT", "SL", "Đơn giá", "Thanh tiền"],
            ["HD01", "2026-06-02", "Hoàn thành", "SP01", "Nước suối 500ml", "chai", "4", "5000", "20000"],
            ["HD02", "2026-06-05", "Hoàn thành", "SP01", "Nước suối 500ml", "chai", "3", "5000", "15000"],
        ],
    )
    _write_csv(
        biz_dir / "the_kho.csv",
        [
            ["MaGiaoDichKho", "MaHangHoa", "NgayGioPhatSinh", "LoaiGiaoDich", "SLQuyDoi", "TonCuoi"],
            ["MV1", "SP01", "2026-06-01 06:00:00", "in_purchase", "24", "24"],
            ["MV2", "SP01", "2026-06-02 09:00:00", "out_sale", "-4", "20"],
            ["MV3", "SP01", "2026-06-05 10:00:00", "out_sale", "-3", "17"],
            # two movements at the same moved_at: file order decides, so the balance is 15, not 16
            ["MV5", "SP01", "2026-06-07 08:00:00", "out_sale", "-1", "16"],
            ["MV4", "SP01", "2026-06-07 08:00:00", "out_sale", "-1", "15"],
            ["MV6", "SP01", "2026-06-06 12:00:00", "in_return", "0", "17"],
        ],
    )
    conn = build_database(biz_dir)
    last_by = (
        "SELECT stock_after FROM v_stock_card WHERE item_code = 'SP01' AND moved_date <= ? "
        "ORDER BY moved_at DESC, rowid DESC LIMIT 1"
    )
    at_jun3 = conn.execute(last_by, ("2026-06-03",)).fetchone()
    at_jun7 = conn.execute(last_by, ("2026-06-07",)).fetchone()
    order = [r[0] for r in conn.execute("SELECT moved_at FROM v_stock_card ORDER BY rowid")]
    end = conn.execute("SELECT stock_qty_base, source FROM v_stock WHERE item_code = 'SP01'").fetchone()
    conn.close()
    assert at_jun3 == (20.0,)
    assert at_jun7 == (15.0,)
    assert order == sorted(order)  # rowid follows moved_at (the out-of-order MV6 row is moved)
    assert end == (15.0, "card")
