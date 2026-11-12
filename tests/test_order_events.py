"""Calendar table, content-detected order time, and payment / delivery / due-date tables."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.mapping import find_time_column
from src.views import build_database, calendar_frame, schema_text


def _write_csv(path: Path, rows: list[list[object]]) -> None:
    path.write_text("\n".join(",".join("" if c is None else str(c) for c in r) for r in rows), encoding="utf-8")


CALENDAR_ROWS = [
    ["date", "weekday", "lunar_day", "lunar_month", "lunar_year", "lunar_leap", "holiday"],
    ["2026-02-10", 2, 23, 12, 2025, "false", ""],
    ["2026-02-17", 2, 1, 1, 2026, "false", "Tết"],
    ["2026-02-22", 7, 6, 1, 2026, "false", ""],
]


def test_calendar_frame_adds_solar_columns(tmp_path: Path) -> None:
    _write_csv(tmp_path / "calendar.csv", CALENDAR_ROWS)
    cal = calendar_frame(tmp_path / "calendar.csv")
    row = cal.set_index("date").loc["2026-02-22"]
    assert (row["year"], row["month"], row["day"], row["quarter"]) == (2026, 2, 22, 1)
    assert row["day_of_week"] == 7 and row["weekday"] == 7 and row["is_weekend"] == 1
    assert row["day_name_vi"] == "Chủ nhật"
    assert row["lunar_month"] == 1 and row["lunar_day"] == 6 and row["lunar_leap"] == 0
    assert cal.set_index("date").loc["2026-02-17", "holiday_vi"] == "Tết"
    assert pd.isna(row["holiday"])


def test_find_time_column_requires_same_day_and_clock_time() -> None:
    df = pd.DataFrame({
        "Thời gian": ["01/02/2025"] * 12,
        "Thời gian tạo": [f"2025-02-01 0{i % 9 + 1}:15:00" for i in range(12)],
        "Thời gian thu": [f"2025-02-03 10:0{i % 9}:00" for i in range(12)],
    })
    assert find_time_column(df, "Thời gian") == "Thời gian tạo"
    assert find_time_column(df, "Thời gian", exclude={"Thời gian tạo"}) is None


def _shop(tmp_path: Path) -> Path:
    biz = tmp_path / "data" / "biz_x"
    biz.mkdir(parents=True)
    _write_csv(tmp_path / "calendar.csv", CALENDAR_ROWS)
    sales = [["Mã đơn hàng", "Ngày", "Thời gian tạo", "Tên hàng", "SL", "Đơn giá", "Thành tiền", "Trạng thái"]]
    for i in range(1, 13):
        sales.append([f"DH{i:03d}", "10/02/2026", f"2026-02-10 08:{i:02d}:00", "Xi măng", 2, 100000, 200000, "Hoàn thành"])
    _write_csv(biz / "SoBanHang.csv", sales)
    _write_csv(biz / "SoQuy.csv", [["Mã phiếu", "Thời gian", "Mã đơn hàng", "Giá trị"]]
               + [[f"PT{i}", f"2026-02-1{i % 3 + 1} 09:00:00", f"DH{i:03d}", 200000] for i in range(1, 13)])
    _write_csv(biz / "Bảng kê phiếu giao hàng.csv", [["Ngày giao hàng", "Mã đơn hàng", "Lần giao", "Tên hàng", "SL giao"]]
               + [["11/02/2026", f"DH{i:03d}", 1, "Xi măng", 1] for i in range(1, 13)]
               + [["11/02/2026", "DH001", 1, "Cát", 1], ["13/02/2026", "DH001", 2, "Xi măng", 1]])
    _write_csv(biz / "Chi tiết công nợ theo hạn.csv", [["Mã đơn hàng", "Số ngày được nợ", "Hạn thanh toán"]]
               + [[f"DH{i:03d}", 30, "12/03/2026"] for i in range(1, 7)])
    return biz


def test_order_events_payments_deliveries_due(tmp_path: Path) -> None:
    conn = build_database(_shop(tmp_path))
    o = conn.execute(
        "SELECT order_time, first_paid_at, paid_amount, n_payments, first_delivery_date, last_delivery_date, "
        "n_delivery_rounds, due_date FROM v_orders WHERE order_id = 'DH001'"
    ).fetchone()
    assert o == ("08:01:00", "2026-02-12 09:00:00", 200000.0, 1, "2026-02-11", "2026-02-13", 2, "2026-03-12")
    assert conn.execute("SELECT due_date FROM v_orders WHERE order_id = 'DH012'").fetchone() == (None,)
    # one row per delivery round, not per shipped item
    assert conn.execute("SELECT COUNT(*) FROM v_deliveries WHERE delivery_month = '2026-02'").fetchone() == (13,)
    assert conn.execute("SELECT COUNT(*) FROM v_payments WHERE paid_month = '2026-02'").fetchone() == (12,)
    # JOIN with the calendar on the order date
    assert conn.execute(
        "SELECT COUNT(*) FROM v_valid_orders o JOIN calendar c ON c.date = o.order_date "
        "WHERE c.lunar_month = 12 AND c.lunar_day >= 23"
    ).fetchone() == (12,)
    text = schema_text(conn)
    assert "VIEW `v_payments`" in text and "VIEW `v_deliveries`" in text and "due_date" in text


def test_order_events_empty_when_shop_has_none(tmp_path: Path) -> None:
    biz = _shop(tmp_path)
    for f in ("SoQuy.csv", "Bảng kê phiếu giao hàng.csv", "Chi tiết công nợ theo hạn.csv"):
        (biz / f).unlink()
    conn = build_database(biz)
    assert conn.execute("SELECT COUNT(*) FROM v_orders WHERE first_paid_at IS NOT NULL OR due_date IS NOT NULL").fetchone() == (0,)
    assert conn.execute("SELECT COUNT(*) FROM v_payments").fetchone() == (0,)
    text = schema_text(conn)
    assert "VIEW `v_payments`" not in text and "first_paid_at" not in text
