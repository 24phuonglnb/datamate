"""Unit tests for shop profiling, period coverage, and capability flags."""
from pathlib import Path
import unittest
import pandas as pd

from src.data_paths import public_test_dir, train_dir
from src.cleaning import RawTable
from src.mapping import propose_mapping
from src.profile import (
    build_profile,
    detect_has_flags,
    extract_readme_data_end,
    period_coverage,
)


class ReadmeExtractionTests(unittest.TestCase):
    """Verify extraction of data_end date from README markdown strings."""

    def test_extract_biz_101_style(self):
        readme = (
            "# Dữ liệu biz_101\n\n"
            "## Quy ước\n"
            "- Dữ liệu có đến hết 24/08/2026.\n"
        )
        self.assertEqual(extract_readme_data_end(readme), "2026-08-24")

    def test_extract_biz_112_style(self):
        readme = (
            "# Dữ liệu biz_112\n\n"
            "- Dữ liệu có đến hết 31/07/2026.\n"
        )
        self.assertEqual(extract_readme_data_end(readme), "2026-07-31")

    def test_extract_date_range_style(self):
        readme = (
            "Dữ liệu trích xuất từ 01/01/2025 đến 30/06/2025.\n"
            "Không phát sinh trả hàng trong kỳ."
        )
        self.assertEqual(extract_readme_data_end(readme), "2025-06-30")

    def test_extract_single_date_fallback(self):
        readme = "Báo cáo kinh doanh tính đến 15/08/2025."
        self.assertEqual(extract_readme_data_end(readme), "2025-08-15")

    def test_no_date_returns_none(self):
        readme = "Tài liệu mô tả dữ liệu không có mốc thời gian."
        self.assertIsNone(extract_readme_data_end(readme))


class PeriodCoverageTests(unittest.TestCase):
    """Verify period_coverage evaluation per Rulebook §7."""

    def setUp(self):
        # Realistic profile for biz_103: transaction table runs from 2025-04-01 to 2026-07-09
        self.profile = {
            "business_id": "biz_103",
            "data_end_readme": "2026-07-09",
            "tables": {
                "sales": {
                    "date_min": "2025-04-01",
                    "date_max": "2026-07-09",
                    "rows": 45534,
                }
            },
            "has": {
                "sales": True,
                "inventory": False,
            },
        }

    def test_full_coverage_within_range(self):
        # Month 5/2025 is fully within April 2025 - July 2026
        self.assertEqual(
            period_coverage(self.profile, "sales", "2025-05-01", "2025-05-31"),
            "full",
        )
        # Exactly matching endpoints
        self.assertEqual(
            period_coverage(self.profile, "sales", "2025-04-01", "2026-07-09"),
            "full",
        )

    def test_none_coverage_strictly_outside(self):
        # Months 1-3/2025 are strictly before April 2025
        self.assertEqual(
            period_coverage(self.profile, "sales", "2025-01-01", "2025-01-31"),
            "none",
        )
        self.assertEqual(
            period_coverage(self.profile, "sales", "2025-02-01", "2025-02-28"),
            "none",
        )
        self.assertEqual(
            period_coverage(self.profile, "sales", "2025-03-01", "2025-03-31"),
            "none",
        )
        # Month 8/2026 is strictly after July 2026
        self.assertEqual(
            period_coverage(self.profile, "sales", "2026-08-01", "2026-08-31"),
            "none",
        )

    def test_partial_coverage_overlapping_boundary(self):
        # 2025-03-01 to 2025-05-31 overlaps partially with [2025-04-01, 2026-07-09]
        self.assertEqual(
            period_coverage(self.profile, "sales", "2025-03-01", "2025-05-31"),
            "partial",
        )
        # 2026-07-01 to 2026-08-31
        self.assertEqual(
            period_coverage(self.profile, "sales", "2026-07-01", "2026-08-31"),
            "partial",
        )

    def test_missing_role_yields_none(self):
        # biz_103 has no inventory table
        self.assertEqual(
            period_coverage(self.profile, "inventory", "2025-05-01", "2025-05-31"),
            "none",
        )

    def test_fallback_to_readme_when_no_table_dates(self):
        profile = {
            "business_id": "biz_test",
            "data_end_readme": "2026-06-30",
            "tables": {},
            "has": {},
        }
        # Period starts after data_end_readme
        self.assertEqual(
            period_coverage(profile, "sales", "2026-07-01", "2026-07-31"),
            "none",
        )


class HasFlagsDetectionTests(unittest.TestCase):
    """Verify semantic capability flags detection against realistic configurations."""

    def test_detect_flags_with_readme_empty_columns(self):
        # Customer table has gender column, but README notes it is empty
        readme = "**Giới tính**: cột trống, không có dữ liệu\n"
        df_cust = pd.DataFrame({
            "Mã khách": ["KH01"],
            "Tên khách": ["Nguyễn Văn A"],
            "Giới tính": ["Nam"],
            "Địa chỉ": ["Hà Nội"],
        })
        t_cust = RawTable("khach_hang", df_cust, list(df_cust.columns), {})
        df_sales = pd.DataFrame({
            "Mã đơn": ["HD01"],
            "Ngày bán": ["2025-05-01"],
            "Mã hàng": ["SP01"],
            "Số lượng": [1],
            "Đơn giá": [10000],
        })
        t_sales = RawTable("ban_hang", df_sales, list(df_sales.columns), {})
        tables = [t_sales, t_cust]
        mapping = propose_mapping(tables, readme)
        flags = detect_has_flags(mapping, tables, readme)

        self.assertTrue(flags["customer_name"])
        self.assertTrue(flags["customer_address"])
        self.assertFalse(flags["customer_gender"], "Gender should be False because README marks it empty")

    def test_payment_method_empty_in_readme(self):
        # Sales table has payment method column, but README notes it is empty
        readme = "**Phương thức thanh toán**: cột trống, không có dữ liệu\n"
        df_sales = pd.DataFrame({
            "Mã đơn": ["HD01"],
            "Ngày bán": ["2025-05-01"],
            "Mã hàng": ["SP01"],
            "Số lượng": [1],
            "Đơn giá": [10000],
            "Phương thức thanh toán": ["Tiền mặt"],
        })
        t_sales = RawTable("ban_hang", df_sales, list(df_sales.columns), {})
        tables = [t_sales]
        mapping = propose_mapping(tables, readme)
        flags = detect_has_flags(mapping, tables, readme)

        self.assertTrue(flags["sales"])
        self.assertFalse(flags["payment_method"], "Payment method should be False per README notes")

    def test_missing_inventory_and_purchases(self):
        # biz_103 scenario: only sales table exists
        df_sales = pd.DataFrame({
            "Mã đơn": ["HD01"],
            "Ngày": ["2025-05-01"],
            "Mã hàng": ["SP01"],
            "Số lượng": [1],
            "Đơn giá": [10000],
        })
        t_sales = RawTable("ban_hang", df_sales, list(df_sales.columns), {})
        tables = [t_sales]
        mapping = propose_mapping(tables, "")
        flags = detect_has_flags(mapping, tables, "")

        self.assertTrue(flags["sales"])
        self.assertFalse(flags["inventory"])
        self.assertFalse(flags["purchases"])
        self.assertFalse(flags["debt"])

    def test_missing_sales_in_dev_012(self):
        # dev_012 scenario: only products catalog table
        df_prod = pd.DataFrame({
            "Mã hàng": ["SP01", "SP02"],
            "Tên hàng": ["Thuốc A", "Thuốc B"],
            "Giá bán": [50000, 75000],
        })
        t_prod = RawTable("san_pham", df_prod, list(df_prod.columns), {})
        tables = [t_prod]
        mapping = propose_mapping(tables, "")
        flags = detect_has_flags(mapping, tables, "")

        self.assertFalse(flags["sales"])
        self.assertTrue(flags["catalog"])


class RealShopProfileTests(unittest.TestCase):
    """End-to-end tests on actual shop directories from the repository."""

    def test_biz_101_profile(self):
        biz_dir = (train_dir() / "data" / "biz_101")
        if not biz_dir.exists():
            self.skipTest("biz_101 data directory not found")

        profile = build_profile(biz_dir)
        self.assertEqual(profile["business_id"], "biz_101")
        self.assertEqual(profile["data_end_readme"], "2026-08-24")
        self.assertIn("sales", profile["tables"])
        self.assertEqual(profile["tables"]["sales"]["date_max"], "2026-08-24")
        self.assertTrue(profile["has"]["sales"])
        self.assertTrue(profile["has"]["customer_name"])

    def test_biz_103_profile_capabilities(self):
        biz_dir = (train_dir() / "data" / "biz_103")
        if not biz_dir.exists():
            self.skipTest("biz_103 data directory not found")

        profile = build_profile(biz_dir)
        self.assertEqual(profile["business_id"], "biz_103")
        self.assertEqual(profile["tables"]["sales"]["date_min"], "2025-04-01")
        self.assertEqual(profile["tables"]["sales"]["date_max"], "2026-07-09")
        self.assertFalse(profile["has"]["inventory"])
        self.assertFalse(profile["has"]["purchases"])
        self.assertFalse(profile["has"]["debt"])

    def test_biz_112_profile_capabilities(self):
        biz_dir = (train_dir() / "data" / "biz_112")
        if not biz_dir.exists():
            self.skipTest("biz_112 data directory not found")

        profile = build_profile(biz_dir)
        self.assertEqual(profile["business_id"], "biz_112")
        self.assertFalse(profile["has"]["customer_name"])
        self.assertFalse(profile["has"]["customer_code"])
        self.assertFalse(profile["has"]["customer_address"])
        self.assertFalse(profile["has"]["customer_gender"])

    def test_dev_012_profile(self):
        biz_dir = (public_test_dir() / "data" / "dev_012")
        if not biz_dir.exists():
            self.skipTest("dev_012 data directory not found")

        profile = build_profile(biz_dir)
        self.assertEqual(profile["business_id"], "dev_012")
        self.assertFalse(profile["has"]["sales"])


if __name__ == "__main__":
    unittest.main()
