"""Generate column and table role mapping reports for all 44 shops.

Saves each shop's mapping JSON to `reports/mappings/<shop>.json` and verifies
benchmark consistency against manual mappings in `revenue_check.py`.

Usage:
    .venv/bin/python scripts/analysis/mapping_report.py [biz_101 biz_103 ...]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.cleaning import load_business
from src.mapping import propose_mapping

BENCHMARK_MAPPINGS = {
    "biz_101": ("ban_hang", "Mã hóa đơn", "Ngày tháng", "Kết quả", "Thanh tien"),
    "biz_103": ("DonHang_ChiTiet", "Mã đơn hàng", "Ngày đặt hàng", "Trạng thái đơn hàng", "Tổng tiền"),
    "biz_117": ("SoBanHang", "Mã phiếu", "Ngày lập", "Ghi chú TT", "Tiền"),
    "biz_107": ("SoBanHang", None, "ngay_ban", "Trạng thái xử lý", "Tổng tiền"),
    "biz_105": ("SoBanHang", "Mã hóa đơn", "Ngày giao dịch", "Status", "Trị giá"),
    "biz_112": ("So_chi_tiet_ban_hang", "Mã đơn hàng", "Ngày", "Trạng thái", "Thành tiền"),
    "biz_102": ("DonHang_ChiTiet", "Mã đơn hàng", "Ngày đặt hàng", "Trạng thái đơn hàng", "Tổng tiền"),
    "biz_114": ("ban_hang", "Mã GD", "Ngày", "trang_thai", "Tổng"),
}


def run_reports(target_shops: list[str] | None = None) -> None:
    reports_dir = ROOT / "reports" / "mappings"
    reports_dir.mkdir(parents=True, exist_ok=True)

    from src.data_paths import train_dir as _train_dir

    train_dir = _train_dir() / "data"
    from src.data_paths import public_test_dir as _public_test_dir

    public_dir = _public_test_dir() / "data"

    all_shops = []
    for p in sorted(train_dir.iterdir()):
        if p.is_dir():
            all_shops.append(("train", p))
    for p in sorted(public_dir.iterdir()):
        if p.is_dir():
            all_shops.append(("public_test", p))

    if target_shops:
        all_shops = [(split, p) for split, p in all_shops if p.name in target_shops]

    print(f"Generating mapping reports for {len(all_shops)} shops...")

    benchmark_pass = 0
    benchmark_total = 0
    train_ok = 0
    train_total = 0
    public_ok = 0
    public_total = 0

    for split, shop_path in all_shops:
        shop = shop_path.name
        tables = load_business(shop_path)
        readme_file = shop_path / "README.md"
        readme = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

        mapping = propose_mapping(tables, readme)

        # Save JSON report
        out_path = reports_dir / f"{shop}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(mapping.to_dict(), f, ensure_ascii=False, indent=2)

        # Check key roles
        date_col = mapping.get_column("order_date")
        amt_col = mapping.get_column("line_amount")
        oid_col = mapping.get_column("order_id")
        status_col = mapping.get_column("status")

        has_core = mapping.sales_table is not None and date_col is not None and amt_col is not None
        if split == "train":
            train_total += 1
            if has_core:
                train_ok += 1
        else:
            public_total += 1
            if has_core:
                public_ok += 1

        # Check benchmark if applicable
        bench_status = ""
        if shop in BENCHMARK_MAPPINGS:
            benchmark_total += 1
            want_tbl, want_oid, want_date, want_status, want_amt = BENCHMARK_MAPPINGS[shop]
            matched = (
                mapping.sales_table == want_tbl
                and oid_col == want_oid
                and date_col == want_date
                and status_col == want_status
                and amt_col == want_amt
            )
            if matched:
                benchmark_pass += 1
                bench_status = " [BENCHMARK MATCH]"
            else:
                bench_status = (
                    f" [BENCHMARK MISMATCH! want: tbl={want_tbl}, oid={want_oid}, date={want_date}, "
                    f"status={want_status}, amt={want_amt} | got: tbl={mapping.sales_table}, "
                    f"oid={oid_col}, date={date_col}, status={status_col}, amt={amt_col}]"
                )

        # Find low confidence or missing roles
        missing = [r for r, c in mapping.sales_columns.items() if c is None and r in ("order_id", "order_date", "status", "item_name", "qty", "unit_price", "line_amount")]
        low_conf = [
            f"{r}={a.column}({a.confidence:.2f})"
            for r, a in mapping.assignments.items()
            if a.column is not None and a.confidence < 0.7
        ]

        status_flag = "OK" if has_core else "MISS"
        ord_info = f" + orders:{mapping.orders_table}" if mapping.orders_table else ""
        print(
            f"[{status_flag:4s}] {shop:7s} ({split:11s}): sales={mapping.sales_table}{ord_info} | "
            f"date={str(date_col):15s} | amt={str(amt_col):15s}{bench_status}"
        )
        if missing:
            print(f"       Missing sales roles: {', '.join(missing)}")
        if low_conf:
            print(f"       Low confidence (<0.7): {', '.join(low_conf)}")

    print("\n" + "=" * 60)
    print("MAPPING SUMMARY REPORT")
    print("=" * 60)
    if train_total:
        print(f"Train Core Found (sales_tbl + date + amt) : {train_ok}/{train_total} ({train_ok/train_total:.1%})")
    if public_total:
        print(f"Public Core Found (sales_tbl + date + amt): {public_ok}/{public_total} ({public_ok/public_total:.1%})")
    if benchmark_total:
        print(f"Benchmark Match (8 manual mappings)       : {benchmark_pass}/{benchmark_total} ({benchmark_pass/benchmark_total:.1%})")
    print(f"Saved mapping JSONs to {reports_dir}/")


if __name__ == "__main__":
    run_reports(sys.argv[1:] if len(sys.argv) > 1 else None)
