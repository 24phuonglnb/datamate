"""Unit tests for src.mapping. Every literal and snippet below was taken from official shop files."""
import unittest
import pandas as pd

from src.cleaning import RawTable
from src.mapping import (
    AuxiliaryTable,
    Mapping,
    RoleAssignment,
    check_arithmetic_consistency,
    parse_readme,
    propose_mapping,
    role_from_column_name,
    role_from_description,
)


class TestParseReadme(unittest.TestCase):
    def test_flat_file_readme(self):
        # Literal snippet from data/train/data/biz_101/README.md
        text = """# Dữ liệu biz_101

Một file phẳng, mỗi dòng một bản ghi (một dòng hàng trong đơn).

## File
- `ban_hang.csv` (csv)

## Cột trong `ban_hang.csv`
- **Giá bán**: đơn giá
- **Kết quả**: trạng thái đơn
- **Nội dung**: tên hàng
- **Ngày tháng**: ngày bán
- **Đơn vị (tính)**: đơn vị tính
- **so_luong**: số lượng
- **Thanh tien**: thành tiền sau giảm
- **Quy ra ĐV lẻ**: số lượng đã đổi ra đơn vị cơ bản
- **Mã hóa đơn**: mã đơn
- **Đối tác**: tên khách (Khách lẻ nếu không lưu)
"""
        got = parse_readme(text)
        self.assertIn("ban_hang.csv", got)
        self.assertIn("ban_hang", got)
        cols = got["ban_hang"]
        self.assertEqual(cols["Giá bán"], "đơn giá")
        self.assertEqual(cols["Thanh tien"], "thành tiền sau giảm")
        self.assertEqual(cols["Mã hóa đơn"], "mã đơn")
        self.assertEqual(cols["Kết quả"], "trạng thái đơn")
        self.assertEqual(cols["Ngày tháng"], "ngày bán")

    def test_multi_sheet_readme(self):
        # Literal snippet from data/train/data/biz_116/README.md
        text = """# Dữ liệu biz_116

## File
- `Bao_cao_ban_hang.xlsx` (xlsx)

## Cột trong `Bao_cao_ban_hang.xlsx`, sheet `So_chi_tiet_ban_hang`
- **Ngày**: ngày bán
- **Mã đơn hàng**: mã đơn
- **Tên hàng hóa**: tên hàng
- **Số lượng**: số lượng
- **Đơn vị tính**: đơn vị tính
- **Đơn giá**: đơn giá
- **Thành tiền**: thành tiền sau giảm
- **Trạng thái**: trạng thái đơn

## Cột trong `Bao_cao_ban_hang.xlsx`, sheet `Danh sách hàng hóa`
- **Mã hàng hóa**: mã hàng
- **Tên hàng hóa**: tên hàng
- **Đơn vị tính**: đơn vị tính
"""
        got = parse_readme(text)
        self.assertIn("So_chi_tiet_ban_hang", got)
        self.assertEqual(got["So_chi_tiet_ban_hang"]["Thành tiền"], "thành tiền sau giảm")
        self.assertIn("Danh sách hàng hóa", got)
        self.assertEqual(got["Danh sách hàng hóa"]["Mã hàng hóa"], "mã hàng")

    def test_sqlite_conventions_readme(self):
        # Literal snippet from data/train/data/biz_123/README.md
        text = """# Dữ liệu biz_123

## File
- `pos.sqlite` (sqlite)

## Quy ước
- Dữ liệu có đến hết 28/06/2026.
- **Dòng hàng**: `chi_tiet_don.TriGia` là thành tiền của dòng (đã trừ giảm giá dòng); `chi_tiet_don.SLQuyDoi` là số lượng đã đổi ra đơn vị cơ bản.
- **Công nợ**: mỗi lần khách trả tiền cho một đơn là một dòng, `thanh_toan.SoTienThu` là số tiền trả lần đó; `don_hang.TongThanhToan` là số khách phải trả cho cả đơn.
- **Giá vốn**: `chi_tiet_don.GiaVonLucBan` là giá vốn một đơn vị bán.
"""
        got = parse_readme(text)
        self.assertIn("chi_tiet_don", got)
        self.assertEqual(got["chi_tiet_don"]["TriGia"], "thành tiền của dòng (đã trừ giảm giá dòng)")
        self.assertEqual(got["chi_tiet_don"]["SLQuyDoi"], "số lượng đã đổi ra đơn vị cơ bản")
        self.assertIn("don_hang", got)
        self.assertEqual(got["don_hang"]["TongThanhToan"], "số khách phải trả cho cả đơn")


class TestVocabularyAndHeuristics(unittest.TestCase):
    def test_description_to_role(self):
        cases = {
            "mã đơn": "order_id",
            "mã hóa đơn": "order_id",
            "thành tiền sau giảm": "line_amount",
            "thành tiền của dòng": "line_amount",
            "trạng thái đơn": "status",
            "số lượng đã đổi ra đơn vị cơ bản": "qty_base",
            "tổng thanh toán": "order_total",
            "khách phải trả cho cả đơn": "order_total",
            "tổng bill": "order_total",
            "ngày bán": "order_date",
            "ngày đặt hàng": "order_date",
            "đơn giá": "unit_price",
            "giá bán lẻ": "unit_price",
            "số lượng": "qty",
            "tên hàng": "item_name",
            "đơn vị tính": "unit",
            "tên khách": "customer_name",
            "mã khách": "customer_code",
            "ghi chú của đơn": "note",
            "tiền nhập của cả dòng": None,
        }
        for desc, want_role in cases.items():
            got = role_from_description(desc)
            if want_role is None:
                self.assertTrue(got is None or got[0] is None, f"Expected None for {desc}, got {got}")
            else:
                self.assertIsNotNone(got, f"Expected {want_role} for {desc}, got None")
                self.assertEqual(got[0], want_role, f"Description: {desc}")

    def test_column_name_to_role(self):
        cases = {
            "Mã hóa đơn": "order_id",
            "MaHoaDon": "order_id",
            "MaGD": "order_id",
            "Mã giao dịch": "order_id",
            "Order ID": "order_id",
            "Ngày đặt hàng": "order_date",
            "NgayBan": "order_date",
            "NgayLap": "order_date",
            "Thành tiền": "line_amount",
            "TriGia": "line_amount",
            "Amount": "line_amount",
            "Số lượng": "qty",
            "SL": "qty",
            "SLQuyDoi": "qty_base",
            "Đơn giá": "unit_price",
            "GiaDonVi": "unit_price",
            "Đơn vị tính": "unit",
            "DonViTinh": "unit",
            "Trạng thái": "status",
            "TinhTrang": "status",
            "TongThanhToan": "order_total",
            "Tổng sau giảm giá": "order_total",
        }
        for col, want_role in cases.items():
            got = role_from_column_name(col)
            self.assertIsNotNone(got, f"Expected {want_role} for {col}, got None")
            self.assertEqual(got[0], want_role, f"Column: {col}")


class TestArithmeticConsistency(unittest.TestCase):
    def test_exact_and_discounted(self):
        df = pd.DataFrame({
            "qty": [1, 2, 5, 10],
            "price": [10000, 25000, 5000, 100000],
            "amount": [10000, 50000, 24000, 950000],  # row 3 & 4 have discounts
        })
        score = check_arithmetic_consistency(df, "qty", "price", "amount")
        self.assertEqual(score, 1.0)

    def test_inconsistent(self):
        df = pd.DataFrame({
            "qty": [1, 2, 3],
            "price": [10000, 20000, 30000],
            "amount": [999999, 888888, 777777],
        })
        score = check_arithmetic_consistency(df, "qty", "price", "amount")
        self.assertEqual(score, 0.0)


class TestProposeMapping(unittest.TestCase):
    def test_flat_table_mapping(self):
        df = pd.DataFrame({
            "Mã hóa đơn": ["HD01", "HD02"],
            "Ngày bán": ["01/01/2025", "02/01/2025"],
            "Tên hàng": ["Bánh", "Kẹo"],
            "Số lượng": [2, 3],
            "Đơn giá": [10000, 5000],
            "Thành tiền": [20000, 15000],
            "Trạng thái": ["Hoàn thành", "Hoàn thành"],
        })
        t = RawTable(name="ban_hang", df=df, sources=["ban_hang.csv"])
        m = propose_mapping([t])
        self.assertEqual(m.sales_table, "ban_hang")
        self.assertEqual(m.get_column("order_id"), "Mã hóa đơn")
        self.assertEqual(m.get_column("order_date"), "Ngày bán")
        self.assertEqual(m.get_column("line_amount"), "Thành tiền")
        self.assertEqual(m.get_column("status"), "Trạng thái")
        self.assertEqual(m.get_column("unit_price"), "Đơn giá")
        self.assertEqual(m.get_column("qty"), "Số lượng")
        self.assertEqual(m.get_column("item_name"), "Tên hàng")
        self.assertIsNone(m.orders_table)

    def test_two_tier_tables_mapping(self):
        df_lines = pd.DataFrame({
            "MaHoaDon": ["HD01", "HD01"],
            "MaHangHoa": ["SP01", "SP02"],
            "DonViTinh": ["hộp", "gói"],
            "SL": [1, 2],
            "GiaDonVi": [20000, 15000],
            "TriGia": [20000, 30000],
        })
        df_orders = pd.DataFrame({
            "MaHoaDon": ["HD01"],
            "NgayLap": ["2025-01-01"],
            "TinhTrang": ["xong"],
            "TongThanhToan": [50000],
        })
        t_lines = RawTable(name="chi_tiet_don", df=df_lines, sources=["pos.sqlite:chi_tiet_don"])
        t_orders = RawTable(name="don_hang", df=df_orders, sources=["pos.sqlite:don_hang"])
        m = propose_mapping([t_lines, t_orders])

        self.assertEqual(m.sales_table, "chi_tiet_don")
        self.assertEqual(m.orders_table, "don_hang")
        self.assertEqual(m.get_column("order_id"), "MaHoaDon")
        self.assertEqual(m.get_column("line_amount"), "TriGia")
        self.assertEqual(m.get_column("order_date"), "NgayLap")
        self.assertEqual(m.get_column("status"), "TinhTrang")
        self.assertEqual(m.get_column("order_total"), "TongThanhToan")
        self.assertIn("don_hang", m.auxiliary_tables)
        self.assertEqual(m.auxiliary_tables["don_hang"].role, "orders")

    def test_json_serialization(self):
        df = pd.DataFrame({
            "Mã hóa đơn": ["HD01"],
            "Ngày bán": ["01/01/2025"],
            "Thành tiền": [20000],
        })
        t = RawTable(name="ban_hang", df=df, sources=["ban_hang.csv"])
        m = propose_mapping([t])
        d = m.to_dict()
        m2 = Mapping.from_dict(d)
        self.assertEqual(m.sales_table, m2.sales_table)
        self.assertEqual(m.get_column("order_id"), m2.get_column("order_id"))
        self.assertEqual(m.get_column("line_amount"), m2.get_column("line_amount"))

    def test_auxiliary_tables_classification(self):
        t_sales = RawTable("ban_hang", pd.DataFrame({"Mã đơn": ["D1"], "Ngày": ["2025-01-01"], "Tiền": [1000]}))
        t_cat = RawTable("DanhSachSanPham", pd.DataFrame({"Mã hàng": ["SP1"], "Tên hàng": ["Bánh"]}))
        t_cust = RawTable("DanhSachKhachHang", pd.DataFrame({"Mã KH": ["KH1"], "Tên KH": ["Nam"]}))
        t_pur = RawTable("DanhSachNhapHang", pd.DataFrame({"Mã nhập": ["N1"], "Tiền": [5000]}))
        t_inv = RawTable("BaoCaoTonKho", pd.DataFrame({"Mã hàng": ["SP1"], "Tồn": [10]}))
        t_unit = RawTable("DanhSachDonViTinh", pd.DataFrame({"Mã hàng": ["SP1"], "Hệ số": [12]}))
        t_pay = RawTable("SoQuy", pd.DataFrame({"Mã đơn": ["D1"], "Số tiền": [1000]}))

        m = propose_mapping([t_sales, t_cat, t_cust, t_pur, t_inv, t_unit, t_pay])
        self.assertEqual(m.auxiliary_tables["DanhSachSanPham"].role, "catalog")
        self.assertEqual(m.auxiliary_tables["DanhSachKhachHang"].role, "customers")
        self.assertEqual(m.auxiliary_tables["DanhSachNhapHang"].role, "purchases")
        self.assertEqual(m.auxiliary_tables["BaoCaoTonKho"].role, "inventory")
        self.assertEqual(m.auxiliary_tables["DanhSachDonViTinh"].role, "unit_conversion")
        self.assertEqual(m.auxiliary_tables["SoQuy"].role, "payments")


if __name__ == "__main__":
    unittest.main()
