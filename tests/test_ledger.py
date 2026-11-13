"""Tests for SalesLedger construction: order status normalization and unit conversion."""
import datetime as dt
import unittest
from pathlib import Path

import pandas as pd

from src.cleaning import RawTable
from src.ledger import (
    CANONICAL_COLUMNS,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_RETURNED,
    STATUS_SHIPPING,
    _resolve_multi_tier,
    build_ledger,
    load_unit_conversions,
    normalize_status,
    verify_invariants,
)
from src.mapping import Mapping


class StatusNormalizationTests(unittest.TestCase):
    """Verify normalization of all 113 unique raw status values surveyed across 44 shops."""

    RAW_CANCELLED = [
        "Huỷ",
        "Huỷ đơn",
        "Hủy",
        "Không giao được",
        "cancel",
        "hủy",
        "hủy đơn",
        "khách hủy",
        "Đã huỷ",
        "Đã hủy",
        "Đã hủy đơn",
    ]

    RAW_RETURNED = [
        "Hoàn trả",
        "Khách trả",
        "Trả hàng",
        "hàng trả về",
        "khách mang trả",
        "khách trả lại",
        "trả hàng",
        "trả lại",
        "trả lại hàng",
        "Đã hoàn hàng",
        "Đã trả hàng",
        "Đổi trả",
    ]

    RAW_SHIPPING = [
        "Chờ giao",
        "chưa giao",
        "Đang giao",
        "Đang giao dịch",
        "Đang giao hàng",
        "Đang vận chuyển",
        "Đang xử lý",
        "đang giao",
        "đang gửi",
        "đang ship",
    ]

    RAW_COMPLETED = [
        "Hoàn thành",
        "Thành công",
        "Xong",
        "xong",
        "ok",
        "Đã giao",
        "Đã hoàn thành",
        "đã lấy",
        "đã xong",
        "đã gọi khách",
        "hẹn chiều lấy",
        "thay thêm nếu cần",
        "khách chờ lấy liền",
        "kiểm tra lại tuần sau",
        "xe để lại qua đêm",
        "bảo hành",
        "bảo hành, phiếu 1/8",
        "bảo hành, phiếu 10/6",
        "bảo hành, phiếu 10/7",
        "bảo hành, phiếu 11/7",
        "bảo hành, phiếu 12/2",
        "bảo hành, phiếu 12/3",
        "bảo hành, phiếu 12/9",
        "bảo hành, phiếu 14/7",
        "bảo hành, phiếu 15/2",
        "bảo hành, phiếu 15/4",
        "bảo hành, phiếu 15/7",
        "bảo hành, phiếu 16/10",
        "bảo hành, phiếu 16/2",
        "bảo hành, phiếu 16/7",
        "bảo hành, phiếu 16/8",
        "bảo hành, phiếu 17/11",
        "bảo hành, phiếu 17/12",
        "bảo hành, phiếu 17/4",
        "bảo hành, phiếu 17/5",
        "bảo hành, phiếu 18/10",
        "bảo hành, phiếu 18/11",
        "bảo hành, phiếu 18/3",
        "bảo hành, phiếu 18/5",
        "bảo hành, phiếu 19/5",
        "bảo hành, phiếu 2/1",
        "bảo hành, phiếu 2/10",
        "bảo hành, phiếu 20/3",
        "bảo hành, phiếu 20/7",
        "bảo hành, phiếu 21/4",
        "bảo hành, phiếu 21/7",
        "bảo hành, phiếu 21/8",
        "bảo hành, phiếu 21/9",
        "bảo hành, phiếu 22/11",
        "bảo hành, phiếu 23/11",
        "bảo hành, phiếu 23/7",
        "bảo hành, phiếu 24/11",
        "bảo hành, phiếu 24/12",
        "bảo hành, phiếu 24/5",
        "bảo hành, phiếu 26/9",
        "bảo hành, phiếu 27/11",
        "bảo hành, phiếu 27/12",
        "bảo hành, phiếu 27/5",
        "bảo hành, phiếu 28/3",
        "bảo hành, phiếu 28/9",
        "bảo hành, phiếu 3/5",
        "bảo hành, phiếu 4/10",
        "bảo hành, phiếu 4/3",
        "bảo hành, phiếu 4/6",
        "bảo hành, phiếu 5/10",
        "bảo hành, phiếu 5/4",
        "bảo hành, phiếu 5/7",
        "bảo hành, phiếu 5/9",
        "bảo hành, phiếu 6/2",
        "bảo hành, phiếu 6/6",
        "bảo hành, phiếu 7/3",
        "bảo hành, phiếu 7/7",
        "bảo hành, phiếu 8/11",
        "bảo hành, phiếu 8/3",
        "bảo hành, phiếu 8/6",
        "bảo hành, phiếu 8/8",
        "bảo hành, phiếu 8/9",
        "bảo hành, phiếu 9/5",
        "bảo hành, phiếu 9/6",
        "bảo hành, phiếu 9/8",
    ]

    def test_total_113_raw_values_covered(self):
        total_count = (
            len(self.RAW_CANCELLED)
            + len(self.RAW_RETURNED)
            + len(self.RAW_SHIPPING)
            + len(self.RAW_COMPLETED)
        )
        self.assertEqual(total_count, 113)

    def test_all_113_values_mapped_correctly(self):
        for raw in self.RAW_CANCELLED:
            self.assertEqual(normalize_status(raw), STATUS_CANCELLED, f"Failed for {raw}")

        for raw in self.RAW_RETURNED:
            self.assertEqual(normalize_status(raw), STATUS_RETURNED, f"Failed for {raw}")

        for raw in self.RAW_SHIPPING:
            self.assertEqual(normalize_status(raw), STATUS_SHIPPING, f"Failed for {raw}")

        for raw in self.RAW_COMPLETED:
            self.assertEqual(normalize_status(raw), STATUS_COMPLETED, f"Failed for {raw}")

    def test_fallback_to_note(self):
        # Empty status cell, but note indicates cancellation
        self.assertEqual(normalize_status(None, note="khách hủy đơn"), STATUS_CANCELLED)
        self.assertEqual(normalize_status("", note="khách mang trả"), STATUS_RETURNED)
        self.assertEqual(normalize_status(None, note="đang vận chuyển"), STATUS_SHIPPING)
        # Note without status defaults to completed
        self.assertEqual(normalize_status(None, note="giao sau 5h chiều"), STATUS_COMPLETED)
        self.assertEqual(normalize_status(None, note=None), STATUS_COMPLETED)


class UnitConversionTests(unittest.TestCase):
    """Test unit conversions, multi-tier chaining, and README bullet parsing."""

    def test_multi_tier_chaining(self):
        # 1 hộp = 15 vỉ, 1 vỉ = 12 viên -> 1 hộp = 180 viên
        raw_rules = [
            ("Thuốc Panadol", "hộp", 15.0, "vỉ", "viên"),
            ("Thuốc Panadol", "vỉ", 12.0, "viên", "viên"),
        ]
        resolved = _resolve_multi_tier(raw_rules)
        item_k = "thuoc panadol"

        # base unit keeps the spelling seen in the file; lookup keys stay accent-free
        self.assertEqual(resolved[(item_k, "hop")], (180.0, "viên"))
        self.assertEqual(resolved[(item_k, "vi")], (12.0, "viên"))
        self.assertEqual(resolved[(item_k, "vien")], (1.0, "viên"))

    def test_multi_tier_three_levels(self):
        # 1 thùng = 4 lốc, 1 lốc = 6 lon -> 1 thùng = 24 lon
        raw_rules = [
            ("Bia Heineken", "thùng", 4.0, "lốc", "lon"),
            ("Bia Heineken", "lốc", 6.0, "lon", "lon"),
        ]
        resolved = _resolve_multi_tier(raw_rules)
        item_k = "bia heineken"

        self.assertEqual(resolved[(item_k, "thung")], (24.0, "lon"))
        self.assertEqual(resolved[(item_k, "loc")], (6.0, "lon"))
        self.assertEqual(resolved[(item_k, "lon")], (1.0, "lon"))

    def test_load_unit_conversions_biz_118(self):
        readme_path = Path("data/train/data/biz_118/README.md")
        if not readme_path.exists():
            self.skipTest("biz_118 README not found")
        readme = readme_path.read_text()
        convs = load_unit_conversions([], readme)

        # 1 tấn = 20 bao
        self.assertEqual(convs[("xi mang ha tien pcb40 bao 50kg", "tan")], (20.0, "bao"))
        # 1 xe 4m3 = 4 m3
        self.assertEqual(convs[("cat xay to", "xe 4m3")], (4.0, "m3"))
        # 1 cuon 4x50m = 200 m2
        self.assertEqual(convs[("bat xanh cam kho 4m", "cuon 4x50m")], (200.0, "m2"))
        # 1 cay = 10 cuon
        self.assertEqual(convs[("bang keo dien nano 20 yard", "cay")], (10.0, "cuộn"))
        # 1 cuon 10m = 10 m
        self.assertEqual(convs[("luoi b40 ma kem kho 1 5m", "cuon 10m")], (10.0, "m"))
        # 1 thien = 1000 vien
        self.assertEqual(convs[("gach ong 8x8x18 tuynel", "thien")], (1000.0, "viên"))


class LedgerBuildAndInvariantsTests(unittest.TestCase):
    """Test SalesLedger construction, order-level status override, and invariants."""

    def test_order_level_return_override(self):
        # Order ORD_01 has 2 lines: one completed, one returned
        # Rulebook §1, §8: any return -> entire order is returned
        df = pd.DataFrame({
            "order_id": ["ORD_01", "ORD_01", "ORD_02", "ORD_02"],
            "date": ["2026-05-01", "2026-05-01", "2026-05-02", "2026-05-02"],
            "status": ["Đã hoàn thành", "Trả hàng", "Đang giao", "Đã huỷ"],
            "item": ["Bút bi", "Vở kẻ ngang", "Thước kẻ", "Tẩy"],
            "unit": ["cây", "quyển", "cây", "cục"],
            "qty": [2, 1, 1, 1],
            "price": [5000, 10000, 3000, 2000],
            "amount": [10000, 10000, 3000, 2000],
            "__file": ["f.xlsx"] * 4,
            "__sheet": ["Sheet1"] * 4,
            "__row": [1, 2, 3, 4],
        })
        table = RawTable("sales", df, list(df.columns), ["f.xlsx"])
        mapping = Mapping(
            sales_table="sales",
            sales_columns={
                "order_id": "order_id",
                "order_date": "date",
                "status": "status",
                "item_name": "item",
                "unit": "unit",
                "qty": "qty",
                "unit_price": "price",
                "line_amount": "amount",
            },
            assignments={},
        )
        ledger, issues = build_ledger([table], mapping)

        self.assertEqual(len(ledger), 4)
        # ORD_01 must be completely tra_hang
        ord1 = ledger[ledger["order_id"] == "ORD_01"]
        self.assertEqual(set(ord1["status"]), {STATUS_RETURNED})

        # ORD_02 has dang_giao and huy -> huy has higher priority
        ord2 = ledger[ledger["order_id"] == "ORD_02"]
        self.assertEqual(set(ord2["status"]), {STATUS_CANCELLED})

    def test_yearless_dates_use_sheet_year_and_blank_cells_are_not_unparsed(self):
        # Rulebook §8: "3/6" takes the year of its sheet; blank continuation cells take the order's date
        df = pd.DataFrame({
            "order_id": ["ORD_01", None, "ORD_02", "ORD_03"],
            "date": ["3/6", None, "27/2", "khong ro"],
            "item": ["Bút bi", "Vở", "Thước", "Tẩy"],
            "qty": [1, 1, 1, 1],
            "price": [5000, 10000, 3000, 2000],
            "amount": [5000, 10000, 3000, 2000],
            "__file": ["f.xlsx"] * 4,
            "__sheet": ["T06-2025", "T06-2025", "T02-2026", "T02-2026"],
            "__row": [1, 2, 3, 4],
            "__year": [2025, 2025, 2026, 2026],
            "__month": [6, 6, 2, 2],
        })
        table = RawTable("sales", df, ["f.xlsx"])
        mapping = Mapping(
            sales_table="sales",
            sales_columns={"order_id": "order_id", "order_date": "date", "item_name": "item",
                           "qty": "qty", "unit_price": "price", "line_amount": "amount"},
            assignments={},
        )
        ledger, issues = build_ledger([table], mapping)
        dates = dict(zip(ledger["item_name"], ledger["order_date"]))
        self.assertEqual(dates["Bút bi"], dt.date(2025, 6, 3))
        self.assertEqual(dates["Vở"], dt.date(2025, 6, 3))
        self.assertEqual(dates["Thước"], dt.date(2026, 2, 27))
        self.assertEqual(issues["unparsed_date_cells"], 1)
        self.assertEqual(issues["unparsed_dates"], 1)  # only "khong ro" stays without a date

    def test_canonical_columns_present(self):
        df = pd.DataFrame({
            "order_id": ["ORD_01"],
            "date": ["2026-05-01"],
            "item": ["Bút bi"],
            "qty": [2],
            "price": [5000],
            "amount": [10000],
            "__file": ["f.xlsx"],
            "__sheet": ["Sheet1"],
            "__row": [1],
        })
        table = RawTable("sales", df, list(df.columns), ["f.xlsx"])
        mapping = Mapping(
            sales_table="sales",
            sales_columns={
                "order_id": "order_id",
                "order_date": "date",
                "item_name": "item",
                "qty": "qty",
                "unit_price": "price",
                "line_amount": "amount",
            },
            assignments={},
        )
        ledger, _ = build_ledger([table], mapping)
        for col in CANONICAL_COLUMNS:
            self.assertIn(col, ledger.columns)

    def test_verify_invariants_pass(self):
        # 100 valid orders
        rows = []
        for i in range(100):
            rows.append({
                "order_id": f"ORD_{i:03d}",
                "order_date": dt.date(2026, 6, 1),
                "order_time": None,
                "status": STATUS_COMPLETED if i > 5 else STATUS_CANCELLED,
                "item_name": "Sản phẩm A",
                "item_code": "SP_A",
                "unit": "cái",
                "qty": 2.0,
                "factor": 1.0,
                "qty_base": 2.0,
                "base_unit": "cái",
                "unit_price": 50000.0,
                "line_amount": 100000.0,
                "customer_name": "Khách A",
                "customer_code": None,
                "staff": None,
                "channel": None,
                "payment_method": None,
                "src_file": "f.xlsx",
                "src_sheet": "Sheet1",
                "src_row": i + 1,
            })
        ledger = pd.DataFrame(rows)
        invs = verify_invariants(ledger, readme="Dữ liệu có đến hết 30/06/2026")

        for name, res in invs.items():
            self.assertEqual(res["status"], "PASS", f"Invariant {name} failed: {res}")


if __name__ == "__main__":
    unittest.main()


class CatalogAndConversionDiscoveryTests(unittest.TestCase):
    """Layouts below were seen in official shop files (columns are shuffled in exports)."""

    def test_name_has_matches_names_written_without_separators(self):
        from src.cleaning import name_has, norm_key
        # public dev_005 "DanhSachSanPham.xlsx", train biz_117 "DanhMuc.xlsx"
        self.assertTrue(name_has(norm_key("DanhSachSanPham"), ["san pham"]))
        self.assertTrue(name_has(norm_key("QuanLy/DanhMuc"), ["danh muc"]))
        self.assertFalse(name_has(norm_key("SoBanHang"), ["san pham", "danh muc"]))

    def test_pick_catalog_columns_ignores_barcode_and_description(self):
        from src.ledger import pick_catalog_columns
        # train biz_111 san_pham.csv: barcode and description columns come before the real ones
        cat = pd.DataFrame({
            "Mã barcode": [None, None, None],
            "SKU": ["SP0001", "SP0002", "SP0003"],
            "Giá": ["25000", "30000", "35000"],
            "Mô tả sản phẩm": [None, None, None],
            "Mã HH Liên quan": [None, None, None],
            "Sản phẩm": ["Cà phê đen (M)", "Cà phê sữa (M)", "Bạc xỉu (M)"],
        })
        self.assertEqual(pick_catalog_columns(cat, ["SP0001", "SP0003"]), ("SKU", "Sản phẩm"))

    def test_pick_catalog_columns_prefers_code_over_ean(self):
        from src.ledger import pick_catalog_columns
        # train biz_123 pos.sqlite san_pham: EAN barcode column precedes MaHangHoa
        cat = pd.DataFrame({
            "ma_vach_ean": ["8937439774399", "8937439774400"],
            "MaHangHoa": ["SP0001", "SP0002"],
            "TenGoi": ["Panadol Extra hộp 15 vỉ x 12 viên", "Hapacol 250 hộp 24 gói"],
            "DanhMuc": ["giảm đau hạ sốt", "giảm đau hạ sốt"],
        })
        self.assertEqual(pick_catalog_columns(cat, ["SP0002"]), ("MaHangHoa", "TenGoi"))

    def _conv(self, name, df):
        return load_unit_conversions([RawTable(name, df, [name + ".xlsx"], [])])

    def test_conversion_table_named_danhmuc_large_small_units(self):
        # train biz_117 DanhMuc.xlsx
        df = pd.DataFrame({"Hàng": ["Xi măng Hà Tiên PCB40 bao 50kg"], "ĐV lớn": ["tấn"],
                           "ĐV nhỏ": ["bao"], "Hệ số QĐ": [20]})
        self.assertEqual(self._conv("DanhMuc", df)[("xi mang ha tien pcb40 bao 50kg", "tan")], (20.0, "bao"))

    def test_conversion_table_with_unit_type_and_base_unit(self):
        # public dev_004 DanhMuc.xlsx
        df = pd.DataFrame({"Hàng": ["Đá 4x6"], "Hệ số": [4], "ĐV gốc": ["m3"], "Loại ĐV": ["xe 4m3"]})
        self.assertEqual(self._conv("DanhMuc", df)[("da 4x6", "xe 4m3")], (4.0, "m3"))

    def test_conversion_written_in_catalog_cell(self):
        # public dev_013 QuanLy.xlsx[DanhMuc]: "Quy đổi" = "1 thùng = 4 bịch"
        df = pd.DataFrame({"Tên hàng": ["Tã quần Bobby size L 54 miếng", "Tã dán Bobby size M 76 miếng"],
                           "Nhóm": ["bỉm tã", "bỉm tã"], "ĐVT": ["bịch", "bịch"],
                           "Quy đổi": ["1 thùng = 4 bịch", "1 thùng = 4 bịch"]})
        self.assertEqual(self._conv("QuanLy/DanhMuc", df)[("ta quan bobby size l 54 mieng", "thung")], (4.0, "bịch"))
