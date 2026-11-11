"""Offline tests for src.cleaning. Every literal below was seen in an official shop file."""
import datetime as dt
import unittest

import pandas as pd

from src.cleaning import (drop_export_duplicates, fill_order_level, find_header, norm_key,
                          parse_date, parse_datetime, parse_number, parse_qty, period_hint,
                          split_summary_rows, _family)


class NumberTests(unittest.TestCase):
    def test_spellings(self):
        cases = {"560,000": 560000, "25.000đ": 25000, "25k": 25000, "1tr440": 1440000,
                 "16,56tr": 16560000, "4,544tr": 4544000, "129 000": 129000,
                 "45,000.0000": 45000, "14036k": 14036000, "-10.000đ": -10000,
                 "1,01tr": 1010000, "294.770.300đ": 294770300, "6,719.0000": 6719,
                 "2tr5": 2500000, "0,9": 0.9, "18.6": 18.6, "1": 1}
        for raw, want in cases.items():
            self.assertEqual(parse_number(raw), want, raw)

    def test_not_numbers(self):
        for raw in ("1 hộp", "ORD000001", "", None, "Khách lẻ", True):
            self.assertIsNone(parse_number(raw), raw)

    def test_qty(self):
        self.assertEqual(parse_qty("2 thùng"), (2.0, "thùng"))
        self.assertEqual(parse_qty("1 bao 25kg"), (1.0, "bao 25kg"))
        self.assertEqual(parse_qty(3), (3.0, None))


class DateTests(unittest.TestCase):
    def test_spellings(self):
        d = dt.date
        self.assertEqual(parse_date("1 thg 6 2025"), d(2025, 6, 1))
        self.assertEqual(parse_date(45689), d(2025, 2, 1))
        self.assertEqual(parse_date("45717"), d(2025, 3, 1))
        self.assertEqual(parse_date("01/02/2025"), d(2025, 2, 1))
        self.assertEqual(parse_date("2025-02-01 06:03:42"), d(2025, 2, 1))
        self.assertEqual(parse_datetime("2025-02-01 06:03:42").hour, 6)

    def test_yearless_needs_sheet_year(self):
        self.assertIsNone(parse_date("1/1"))
        self.assertEqual(parse_date("1/1", 2025), dt.date(2025, 1, 1))

    def test_period_hint(self):
        self.assertEqual(period_hint("Tháng 01-2025"), (2025, 1))
        self.assertEqual(period_hint("T7-2025"), (2025, 7))
        self.assertEqual(period_hint("04.2025"), (2025, 4))
        self.assertEqual(period_hint("Sheet1", "SoBanHang_2026"), (2026, None))
        self.assertEqual(period_hint("Sheet1", "SoBanHang_1"), (None, None))


class LayoutTests(unittest.TestCase):
    def test_header_after_title(self):
        rows = [["SỔ CHI TIẾT BÁN HÀNG"], ["Kỳ báo cáo: toàn bộ", "Kênh bán: Tất cả"], [],
                ["Ngày", "Mã đơn hàng", "Tên hàng hóa", "Số lượng", "Thành tiền"],
                ["01/04/2025", "ORD000001", "Cà phê đen (M)", "1 ly", "25,000.0000"]]
        self.assertEqual(find_header(rows), 3)

    def test_two_level_header(self):
        rows = [["Hàng", None, None, "Tiền", None, None, "Đơn"],
                ["Hàng", "so_luong", "Unit", "Trị giá", "Status", "Giá lẻ", "Giờ", "Mã hóa đơn"],
                ["Cà phê đen (M)", 1, "ly", "25.000đ", "đã lấy", "25k", "06:00", "ORD000001"]]
        self.assertEqual(find_header(rows), 1)

    def test_text_only_table_keeps_first_row_as_header(self):
        rows = [["Ghi tắt", "Tên hàng", "Loại"], ["Cáp C", "Cáp Type-C 1m", "phụ kiện"],
                ["Cáp C-L", "Cáp Type-C sang Lightning 1m", "phụ kiện"]]
        self.assertEqual(find_header(rows), 0)

    def test_file_family(self):
        self.assertEqual(_family("DonHang_ChiTiet_2026"), "DonHang_ChiTiet")
        self.assertEqual(_family("BanHang_T1_2025"), "BanHang")
        self.assertEqual(_family("SoBanHang_1"), "SoBanHang")
        self.assertEqual(_family("ban_hang"), "ban_hang")


class OrderRepairTests(unittest.TestCase):
    def test_fill_down_keeps_real_blanks(self):
        df = pd.DataFrame({
            "ma": ["O1", None, None, "O2", None, "O3"],
            "khach": ["An", None, None, None, None, "Bình"],     # O2 is a real walk-in
            "trang_thai": ["xong", None, None, "hủy", None, "xong"],
            "hang": ["a", "b", "c", "d", "e", "f"],
            "tien": [1, 2, 3, 4, None, 6]}, dtype=object)
        out = fill_order_level(df, "ma")
        self.assertEqual(out["ma"].tolist(), ["O1", "O1", "O1", "O2", "O2", "O3"])
        self.assertEqual(out["khach"].tolist()[:3], ["An", "An", "An"])
        self.assertTrue(pd.isna(out["khach"][3]) and pd.isna(out["khach"][4]))
        self.assertEqual(out["trang_thai"].tolist(), ["xong"] * 3 + ["hủy"] * 2 + ["xong"])
        self.assertTrue(pd.isna(out["tien"][4]))  # line-level column untouched

    def test_duplicates_only_inside_one_order(self):
        df = pd.DataFrame({"ma": ["O1", "O1", "O2", None, None], "hang": ["a", "a", "a", "z", "z"],
                           "tien": [5, 5, 5, 9, 9]}, dtype=object)
        out = drop_export_duplicates(df, "ma")
        self.assertEqual(len(out), 4)  # O1 dup removed; key-less rows are separate sales

    def test_summary_rows(self):
        df = pd.DataFrame({"gio": ["06:13", "Tổng tháng", "Ghi chú: số liệu ghi tay"],
                           "ma": ["O1", None, None], "kh": ["An", None, None],
                           "tien": ["55.000đ", "901.896.400đ", None], "hang": ["x", None, None]}, dtype=object)
        data, removed = split_summary_rows(df)
        self.assertEqual(len(data), 1)
        self.assertEqual(len(removed), 2)

    def test_norm_key(self):
        self.assertEqual(norm_key("  Đã Hủy-đơn "), "da huy don")


if __name__ == "__main__":
    unittest.main()
