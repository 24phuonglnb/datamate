"""
Synthetic Vietnamese business benchmark for DataMate.

Generates 5 fictional businesses (CSV/XLSX/SQLite), 105 Vietnamese questions,
and deterministic ground-truth answers computed by running oracle SQL against
the generated data.

Usage:
    python benchmark/create_benchmark.py           # writes to benchmark/data/
    python benchmark/create_benchmark.py --out /path/to/dir
    python benchmark/create_benchmark.py --verify  # print answer stats only
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

try:
    from openpyxl import Workbook
except ImportError:
    Workbook = None

PARENT = Path(__file__).parent.parent
sys.path.insert(0, str(PARENT))


# ─── Low-level file writers ────────────────────────────────────────────────

def _csv(path: Path, headers: list[str], rows: list[tuple]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


def _xlsx(path: Path, sheet: str, headers: list[str], rows: list[tuple]) -> None:
    if Workbook is None:
        raise RuntimeError("openpyxl is required for .xlsx output")
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(headers)
    for row in rows:
        ws.append(list(row))
    wb.save(path)


def _sqlite(path: Path, table: str, headers: list[str], rows: list[tuple]) -> None:
    con = sqlite3.connect(str(path))
    try:
        col_defs = ", ".join(f'"{h}" TEXT' for h in headers)
        con.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({col_defs})')
        ph = ", ".join(["?"] * len(headers))
        con.executemany(
            f'INSERT INTO "{table}" VALUES ({ph})',
            [[str(v) if v is not None else None for v in r] for r in rows],
        )
        con.commit()
    finally:
        con.close()


# ─── Business 1: Quán Cà Phê Hương Việt ──────────────────────────────────

CAFE_SALES_H = ["ngay", "san_pham", "so_luong", "don_gia", "doanh_thu", "nhan_vien", "hinh_thuc"]
CAFE_SALES = [
    # Tháng 1
    ("2026-01-05", "Cà phê đen",   10, 25000,  250000, "An",    "Tiền mặt"),
    ("2026-01-05", "Cà phê sữa",    8, 35000,  280000, "Bình",  "Thẻ"),
    ("2026-01-07", "Trà sữa",       5, 45000,  225000, "An",    "Thẻ"),
    ("2026-01-07", "Sinh tố",       6, 50000,  300000, "Cường", "Thẻ"),
    ("2026-01-10", "Cà phê đen",   15, 25000,  375000, "Bình",  "Tiền mặt"),
    ("2026-01-10", "Bánh mì",      12, 20000,  240000, "An",    "Tiền mặt"),
    ("2026-01-15", "Cà phê sữa",   10, 35000,  350000, "Cường", "Thẻ"),
    ("2026-01-15", "Trà sữa",       8, 45000,  360000, "An",    "Tiền mặt"),
    ("2026-01-20", "Cà phê đen",   18, 25000,  450000, "Bình",  "Tiền mặt"),
    ("2026-01-20", "Sinh tố",      10, 50000,  500000, "An",    "Thẻ"),
    ("2026-01-25", "Bánh mì",      15, 20000,  300000, "Cường", "Tiền mặt"),
    ("2026-01-25", "Cà phê sữa",   12, 35000,  420000, "Bình",  "Thẻ"),
    # Tháng 2
    ("2026-02-01", "Cà phê đen",   12, 25000,  300000, "An",    "Tiền mặt"),
    ("2026-02-01", "Cà phê sữa",   10, 35000,  350000, "Cường", "Thẻ"),
    ("2026-02-05", "Trà sữa",       7, 45000,  315000, "Bình",  "Tiền mặt"),
    ("2026-02-05", "Sinh tố",       8, 50000,  400000, "An",    "Thẻ"),
    ("2026-02-14", "Cà phê sữa",   20, 35000,  700000, "An",    "Tiền mặt"),
    ("2026-02-14", "Bánh mì",      25, 20000,  500000, "Bình",  "Tiền mặt"),
    ("2026-02-14", "Trà sữa",      15, 45000,  675000, "An",    "Thẻ"),
    ("2026-02-20", "Cà phê đen",   10, 25000,  250000, "Cường", "Tiền mặt"),
    ("2026-02-20", "Sinh tố",       6, 50000,  300000, "Bình",  "Thẻ"),
    # Tháng 3
    ("2026-03-01", "Cà phê đen",   14, 25000,  350000, "Bình",  "Tiền mặt"),
    ("2026-03-01", "Cà phê sữa",    9, 35000,  315000, "An",    "Thẻ"),
    ("2026-03-08", "Trà sữa",      15, 45000,  675000, "An",    "Thẻ"),
    ("2026-03-08", "Sinh tố",      12, 50000,  600000, "Bình",  "Tiền mặt"),
    ("2026-03-08", "Bánh mì",      10, 20000,  200000, "Cường", "Tiền mặt"),
    ("2026-03-15", "Cà phê đen",   20, 25000,  500000, "An",    "Thẻ"),
    ("2026-03-15", "Cà phê sữa",   11, 35000,  385000, "Cường", "Tiền mặt"),
    ("2026-03-20", "Bánh mì",      18, 20000,  360000, "Bình",  "Tiền mặt"),
    ("2026-03-20", "Trà sữa",       9, 45000,  405000, "An",    "Tiền mặt"),
    # Tháng 4
    ("2026-04-01", "Cà phê sữa",   11, 35000,  385000, "An",    "Thẻ"),
    ("2026-04-05", "Trà sữa",       9, 45000,  405000, "Bình",  "Tiền mặt"),
    ("2026-04-10", "Cà phê đen",   16, 25000,  400000, "Cường", "Tiền mặt"),
    ("2026-04-15", "Sinh tố",       8, 50000,  400000, "An",    "Thẻ"),
]

CAFE_INVENTORY_H = ["san_pham", "ton_kho", "don_vi", "gia_nhap"]
CAFE_INVENTORY = [
    ("Cà phê đen",  150, "ly",  10000),
    ("Cà phê sữa",  120, "ly",  15000),
    ("Trà sữa",      80, "ly",  20000),
    ("Sinh tố",      50, "ly",  25000),
    ("Bánh mì",      30, "cái",  8000),
]


# ─── Business 2: Nhà Thuốc Bình Minh ─────────────────────────────────────

PHARMA_PRODUCTS_H = ["ma_thuoc", "ten_thuoc", "loai", "don_gia", "so_luong_ton"]
PHARMA_PRODUCTS = [
    ("T001", "Paracetamol 500mg",   "Giảm đau",   15000,  200),
    ("T002", "Ibuprofen 400mg",     "Giảm đau",   22000,  150),
    ("T003", "Amoxicillin 500mg",   "Kháng sinh", 85000,   80),
    ("T004", "Azithromycin 250mg",  "Kháng sinh", 120000,  40),
    ("T005", "Vitamin C 1000mg",    "Vitamin",    25000,  300),
    ("T006", "Vitamin D3 1000IU",   "Vitamin",    35000,  180),
    ("T007", "Vitamin B complex",   "Vitamin",    45000,  120),
    ("T008", "Omeprazole 20mg",     "Tiêu hoá",  40000,   90),
    ("T009", "Domperidone 10mg",    "Tiêu hoá",  18000,  110),
    ("T010", "Loratadine 10mg",     "Dị ứng",    20000,  200),
    ("T011", "Cetirizine 10mg",     "Dị ứng",    18000,  160),
    ("T012", "Metformin 500mg",     "Tiểu đường",55000,   60),
    ("T013", "Amlodipine 5mg",      "Tim mạch",  65000,   50),
    ("T014", "Atorvastatin 20mg",   "Tim mạch",  90000,   45),
    ("T015", "Zinc 10mg",           "Vitamin",    12000,  250),
]

PHARMA_TX_H = ["ma_gd", "ngay", "ma_thuoc", "ten_thuoc", "so_luong", "tong_tien", "ten_khach"]
PHARMA_TX = [
    # Tháng 1
    ("GD001", "2026-01-03", "T001", "Paracetamol 500mg",  5,  75000, "Nguyễn Thị A"),
    ("GD002", "2026-01-03", "T005", "Vitamin C 1000mg",   3,  75000, "Trần Văn B"),
    ("GD003", "2026-01-05", "T002", "Ibuprofen 400mg",    2,  44000, "Lê Thị C"),
    ("GD004", "2026-01-05", "T008", "Omeprazole 20mg",    1,  40000, "Nguyễn Thị A"),
    ("GD005", "2026-01-08", "T003", "Amoxicillin 500mg",  2, 170000, "Phạm Văn D"),
    ("GD006", "2026-01-08", "T006", "Vitamin D3 1000IU",  2,  70000, "Trần Văn B"),
    ("GD007", "2026-01-12", "T001", "Paracetamol 500mg", 10, 150000, "Hoàng Thị E"),
    ("GD008", "2026-01-12", "T010", "Loratadine 10mg",    3,  60000, "Lê Thị C"),
    ("GD009", "2026-01-15", "T004", "Azithromycin 250mg", 1, 120000, "Phạm Văn D"),
    ("GD010", "2026-01-15", "T007", "Vitamin B complex",  2,  90000, "Nguyễn Thị A"),
    ("GD011", "2026-01-20", "T005", "Vitamin C 1000mg",   5, 125000, "Trần Văn B"),
    ("GD012", "2026-01-20", "T012", "Metformin 500mg",    2, 110000, "Vũ Văn F"),
    ("GD013", "2026-01-25", "T013", "Amlodipine 5mg",     1,  65000, "Vũ Văn F"),
    ("GD014", "2026-01-25", "T002", "Ibuprofen 400mg",    3,  66000, "Hoàng Thị E"),
    ("GD015", "2026-01-28", "T009", "Domperidone 10mg",   2,  36000, "Lê Thị C"),
    # Tháng 2
    ("GD016", "2026-02-02", "T001", "Paracetamol 500mg",  8, 120000, "Nguyễn Thị A"),
    ("GD017", "2026-02-02", "T005", "Vitamin C 1000mg",   4, 100000, "Trần Thị G"),
    ("GD018", "2026-02-05", "T003", "Amoxicillin 500mg",  3, 255000, "Phạm Văn D"),
    ("GD019", "2026-02-10", "T006", "Vitamin D3 1000IU",  3, 105000, "Trần Văn B"),
    ("GD020", "2026-02-10", "T014", "Atorvastatin 20mg",  1,  90000, "Vũ Văn F"),
    ("GD021", "2026-02-14", "T011", "Cetirizine 10mg",    2,  36000, "Lê Thị C"),
    ("GD022", "2026-02-20", "T007", "Vitamin B complex",  3, 135000, "Trần Thị G"),
    ("GD023", "2026-02-20", "T002", "Ibuprofen 400mg",    2,  44000, "Hoàng Thị E"),
    ("GD024", "2026-02-25", "T012", "Metformin 500mg",    2, 110000, "Vũ Văn F"),
    ("GD025", "2026-02-28", "T001", "Paracetamol 500mg",  6,  90000, "Nguyễn Thị A"),
    # Tháng 3
    ("GD026", "2026-03-05", "T015", "Zinc 10mg",          5,  60000, "Trần Văn B"),
    ("GD027", "2026-03-10", "T005", "Vitamin C 1000mg",   6, 150000, "Nguyễn Thị A"),
    ("GD028", "2026-03-15", "T004", "Azithromycin 250mg", 2, 240000, "Phạm Văn D"),
    ("GD029", "2026-03-20", "T008", "Omeprazole 20mg",    2,  80000, "Lê Thị C"),
    ("GD030", "2026-03-25", "T013", "Amlodipine 5mg",     1,  65000, "Vũ Văn F"),
]


# ─── Business 3: Nhà Hàng Phú Quý ────────────────────────────────────────

RESTAURANT_ORDERS_H = ["ma_don", "ngay", "ten_mon", "so_luong", "tong_tien", "trang_thai", "ten_khach"]
RESTAURANT_ORDERS = [
    # Tháng 1
    ("HD001", "2026-01-03", "Phở bò",          2, 160000, "hoàn thành", "Minh"),
    ("HD002", "2026-01-03", "Cơm tấm",         3, 150000, "hoàn thành", "Lan"),
    ("HD003", "2026-01-05", "Bún bò Huế",      2, 130000, "hoàn thành", "Nam"),
    ("HD004", "2026-01-05", "Hải sản xào",     1, 180000, "hoàn thành", "Minh"),
    ("HD005", "2026-01-07", "Phở bò",          4, 320000, "hoàn thành", "Hoa"),
    ("HD006", "2026-01-07", "Lẩu hải sản",     1, 350000, "hoàn thành", "Lan"),
    ("HD007", "2026-01-10", "Cơm tấm",         5, 250000, "hoàn thành", "Nam"),
    ("HD008", "2026-01-10", "Bún bò Huế",      3, 195000, "hoàn thành", "Minh"),
    ("HD009", "2026-01-12", "Hải sản xào",     2, 360000, "hoàn thành", "Hoa"),
    ("HD010", "2026-01-12", "Phở bò",          3, 240000, "huỷ",        "Lan"),
    ("HD011", "2026-01-15", "Lẩu hải sản",     2, 700000, "hoàn thành", "Nam"),
    ("HD012", "2026-01-15", "Cơm tấm",         4, 200000, "hoàn thành", "Minh"),
    ("HD013", "2026-01-18", "Bún bò Huế",      2, 130000, "hoàn thành", "Hoa"),
    ("HD014", "2026-01-18", "Phở bò",          5, 400000, "hoàn thành", "Nam"),
    ("HD015", "2026-01-20", "Hải sản xào",     3, 540000, "hoàn thành", "Lan"),
    ("HD016", "2026-01-20", "Cơm tấm",         6, 300000, "huỷ",        "Minh"),
    ("HD017", "2026-01-25", "Lẩu hải sản",     1, 350000, "hoàn thành", "Hoa"),
    ("HD018", "2026-01-25", "Phở bò",          3, 240000, "hoàn thành", "Nam"),
    # Tháng 2
    ("HD019", "2026-02-01", "Phở bò",          4, 320000, "hoàn thành", "Minh"),
    ("HD020", "2026-02-01", "Cơm tấm",         6, 300000, "hoàn thành", "Lan"),
    ("HD021", "2026-02-05", "Hải sản xào",     2, 360000, "hoàn thành", "Nam"),
    ("HD022", "2026-02-14", "Lẩu hải sản",     3, 1050000, "hoàn thành", "Hoa"),
    ("HD023", "2026-02-14", "Phở bò",          5, 400000, "hoàn thành", "Lan"),
    ("HD024", "2026-02-20", "Bún bò Huế",      4, 260000, "hoàn thành", "Minh"),
    # Tháng 3
    ("HD025", "2026-03-05", "Cơm tấm",         8, 400000, "hoàn thành", "Nam"),
    ("HD026", "2026-03-08", "Lẩu hải sản",     2, 700000, "hoàn thành", "Hoa"),
    ("HD027", "2026-03-15", "Phở bò",          6, 480000, "hoàn thành", "Lan"),
    ("HD028", "2026-03-20", "Hải sản xào",     4, 720000, "hoàn thành", "Minh"),
]

RESTAURANT_MENU_H = ["ten_mon", "loai", "gia", "co_ban"]
RESTAURANT_MENU = [
    ("Phở bò",       "Món chính",  80000, 1),
    ("Cơm tấm",      "Món chính",  50000, 1),
    ("Bún bò Huế",   "Món chính",  65000, 1),
    ("Hải sản xào",  "Hải sản",   180000, 1),
    ("Lẩu hải sản",  "Hải sản",   350000, 1),
    ("Gỏi cuốn",     "Khai vị",    35000, 1),
    ("Chả giò",      "Khai vị",    40000, 1),
    ("Chè ba màu",   "Tráng miệng",25000, 1),
    ("Kem dừa",      "Tráng miệng",30000, 1),
    ("Nước ép cam",  "Đồ uống",    30000, 1),
]

RESTAURANT_BOOKINGS_H = ["ma_dat", "ngay", "ten_khach", "so_nguoi", "trang_thai"]
RESTAURANT_BOOKINGS = [
    ("DB001", "2026-01-05", "Minh",   4, "xác nhận"),
    ("DB002", "2026-01-07", "Lan",    6, "xác nhận"),
    ("DB003", "2026-01-10", "Nam",    2, "xác nhận"),
    ("DB004", "2026-01-12", "Hoa",    8, "xác nhận"),
    ("DB005", "2026-01-15", "Minh",  10, "xác nhận"),
    ("DB006", "2026-01-18", "Lan",    4, "huỷ"),
    ("DB007", "2026-01-20", "Nam",    6, "xác nhận"),
    ("DB008", "2026-01-25", "Hoa",    3, "xác nhận"),
    ("DB009", "2026-02-14", "Minh",  12, "xác nhận"),
    ("DB010", "2026-02-14", "Lan",    8, "xác nhận"),
    ("DB011", "2026-03-08", "Hoa",    6, "xác nhận"),
    ("DB012", "2026-03-15", "Nam",    4, "huỷ"),
]


# ─── Business 4: Cửa Hàng Điện Tử Thăng Long ─────────────────────────────

ELEC_CATALOG_H = ["ma_sp", "ten_sp", "loai", "gia_nhap", "gia_ban", "bao_hanh_thang"]
ELEC_CATALOG = [
    ("SP001", "iPhone 16",          "Điện thoại",  18000000, 24000000, 12),
    ("SP002", "Samsung Galaxy S25", "Điện thoại",  15000000, 20000000, 12),
    ("SP003", "Xiaomi 14",          "Điện thoại",   8000000, 11000000, 12),
    ("SP004", "MacBook Pro M4",     "Laptop",      35000000, 46000000, 24),
    ("SP005", "Dell XPS 15",        "Laptop",      25000000, 33000000, 24),
    ("SP006", "Lenovo ThinkPad",    "Laptop",      18000000, 24000000, 24),
    ("SP007", "iPad Pro 13",        "Máy tính bảng",18000000,24000000, 12),
    ("SP008", "Samsung Tab S9",     "Máy tính bảng",10000000,14000000, 12),
    ("SP009", "AirPods Pro",        "Phụ kiện",    4000000,  5500000,  6),
    ("SP010", "Chuột Logitech MX",  "Phụ kiện",     800000,  1200000, 12),
    ("SP011", "Bàn phím cơ",        "Phụ kiện",    1200000,  1800000, 12),
    ("SP012", "Màn hình 4K 27in",   "Màn hình",    5000000,  7000000, 24),
    ("SP013", "Màn hình FHD 24in",  "Màn hình",    2500000,  3500000, 24),
]

ELEC_SALES_H = ["ma_hd", "ngay", "ma_sp", "ten_sp", "so_luong", "gia_ban", "tong_tien"]
ELEC_SALES = [
    # Tháng 1
    ("HĐ001", "2026-01-03", "SP001", "iPhone 16",          2, 24000000,  48000000),
    ("HĐ002", "2026-01-03", "SP009", "AirPods Pro",        3,  5500000,  16500000),
    ("HĐ003", "2026-01-05", "SP004", "MacBook Pro M4",     1, 46000000,  46000000),
    ("HĐ004", "2026-01-05", "SP010", "Chuột Logitech MX",  2,  1200000,   2400000),
    ("HĐ005", "2026-01-08", "SP002", "Samsung Galaxy S25", 3, 20000000,  60000000),
    ("HĐ006", "2026-01-08", "SP007", "iPad Pro 13",        1, 24000000,  24000000),
    ("HĐ007", "2026-01-10", "SP003", "Xiaomi 14",          4, 11000000,  44000000),
    ("HĐ008", "2026-01-10", "SP011", "Bàn phím cơ",        3,  1800000,   5400000),
    ("HĐ009", "2026-01-12", "SP005", "Dell XPS 15",        2, 33000000,  66000000),
    ("HĐ010", "2026-01-12", "SP012", "Màn hình 4K 27in",   2,  7000000,  14000000),
    ("HĐ011", "2026-01-15", "SP001", "iPhone 16",          3, 24000000,  72000000),
    ("HĐ012", "2026-01-15", "SP008", "Samsung Tab S9",     2, 14000000,  28000000),
    ("HĐ013", "2026-01-20", "SP006", "Lenovo ThinkPad",    1, 24000000,  24000000),
    ("HĐ014", "2026-01-20", "SP013", "Màn hình FHD 24in",  3,  3500000,  10500000),
    ("HĐ015", "2026-01-25", "SP002", "Samsung Galaxy S25", 2, 20000000,  40000000),
    ("HĐ016", "2026-01-25", "SP009", "AirPods Pro",        2,  5500000,  11000000),
    # Tháng 2
    ("HĐ017", "2026-02-03", "SP001", "iPhone 16",          1, 24000000,  24000000),
    ("HĐ018", "2026-02-05", "SP004", "MacBook Pro M4",     2, 46000000,  92000000),
    ("HĐ019", "2026-02-10", "SP003", "Xiaomi 14",          3, 11000000,  33000000),
    ("HĐ020", "2026-02-14", "SP007", "iPad Pro 13",        2, 24000000,  48000000),
    ("HĐ021", "2026-02-20", "SP005", "Dell XPS 15",        1, 33000000,  33000000),
    ("HĐ022", "2026-02-25", "SP010", "Chuột Logitech MX",  5,  1200000,   6000000),
    # Tháng 3
    ("HĐ023", "2026-03-05", "SP002", "Samsung Galaxy S25", 2, 20000000,  40000000),
    ("HĐ024", "2026-03-10", "SP012", "Màn hình 4K 27in",   3,  7000000,  21000000),
    ("HĐ025", "2026-03-15", "SP001", "iPhone 16",          2, 24000000,  48000000),
    ("HĐ026", "2026-03-20", "SP006", "Lenovo ThinkPad",    2, 24000000,  48000000),
]


# ─── Business 5: Thời Trang Thu Hà ───────────────────────────────────────

FASHION_PRODUCTS_H = ["ma_hang", "ten_hang", "loai", "mau", "size", "gia_ban", "gia_nhap"]
FASHION_PRODUCTS = [
    ("AO001", "Áo thun basic",      "Áo",     "Trắng",  "M",  180000,  80000),
    ("AO002", "Áo thun basic",      "Áo",     "Đen",    "M",  180000,  80000),
    ("AO003", "Áo sơ mi kẻ",        "Áo",     "Xanh",   "L",  350000, 150000),
    ("AO004", "Áo hoodie",          "Áo",     "Xám",    "XL", 450000, 200000),
    ("AO005", "Áo polo",            "Áo",     "Trắng",  "M",  280000, 120000),
    ("QU001", "Quần jeans slim",    "Quần",   "Xanh",   "M",  450000, 180000),
    ("QU002", "Quần jean ống rộng", "Quần",   "Đen",    "L",  480000, 190000),
    ("QU003", "Quần short kaki",    "Quần",   "Be",     "M",  280000, 110000),
    ("QU004", "Quần tây văn phòng", "Quần",   "Đen",    "L",  520000, 220000),
    ("VA001", "Váy hoa nhí",        "Váy",    "Hồng",   "S",  380000, 160000),
    ("VA002", "Váy suông dài",      "Váy",    "Trắng",  "M",  420000, 170000),
    ("PH001", "Phụ kiện thắt lưng","Phụ kiện","Nâu",   "XL", 180000,  70000),
    ("PH002", "Túi xách nhỏ",       "Phụ kiện","Đen",  "OS", 320000, 130000),
]

FASHION_ORDERS_H = ["ma_don", "ngay", "ma_hang", "ten_hang", "so_luong", "tong_tien", "trang_thai", "tinh_thanh"]
FASHION_ORDERS = [
    # Tháng 1
    ("DH001", "2026-01-03", "AO001", "Áo thun basic",     3,  540000, "hoàn thành", "Hà Nội"),
    ("DH002", "2026-01-03", "QU001", "Quần jeans slim",   2,  900000, "hoàn thành", "TP HCM"),
    ("DH003", "2026-01-05", "VA001", "Váy hoa nhí",       2,  760000, "hoàn thành", "Đà Nẵng"),
    ("DH004", "2026-01-05", "AO003", "Áo sơ mi kẻ",      3, 1050000, "hoàn thành", "Hà Nội"),
    ("DH005", "2026-01-07", "AO004", "Áo hoodie",         4, 1800000, "hoàn thành", "TP HCM"),
    ("DH006", "2026-01-07", "QU002", "Quần jean ống rộng",2,  960000, "hoàn thành", "Hà Nội"),
    ("DH007", "2026-01-10", "AO002", "Áo thun basic",     5,  900000, "hoàn thành", "Cần Thơ"),
    ("DH008", "2026-01-10", "QU003", "Quần short kaki",   3,  840000, "hoàn thành", "Đà Nẵng"),
    ("DH009", "2026-01-12", "VA002", "Váy suông dài",     2,  840000, "hoàn thành", "TP HCM"),
    ("DH010", "2026-01-12", "PH002", "Túi xách nhỏ",      2,  640000, "hoàn thành", "Hà Nội"),
    ("DH011", "2026-01-15", "AO005", "Áo polo",           4, 1120000, "hoàn thành", "Cần Thơ"),
    ("DH012", "2026-01-15", "QU004", "Quần tây văn phòng",3, 1560000, "hoàn thành", "Hà Nội"),
    ("DH013", "2026-01-18", "AO001", "Áo thun basic",     6, 1080000, "hoàn thành", "TP HCM"),
    ("DH014", "2026-01-18", "VA001", "Váy hoa nhí",       3, 1140000, "hoàn thành", "Đà Nẵng"),
    ("DH015", "2026-01-20", "AO003", "Áo sơ mi kẻ",      2,  700000, "hoàn thành", "Hà Nội"),
    ("DH016", "2026-01-20", "QU001", "Quần jeans slim",   3, 1350000, "hoàn thành", "TP HCM"),
    ("DH017", "2026-01-22", "PH001", "Phụ kiện thắt lưng",4, 720000, "hoàn",       "Cần Thơ"),
    ("DH018", "2026-01-25", "AO004", "Áo hoodie",         3, 1350000, "hoàn thành", "Hà Nội"),
    ("DH019", "2026-01-25", "VA002", "Váy suông dài",     2,  840000, "hoàn thành", "TP HCM"),
    ("DH020", "2026-01-28", "QU003", "Quần short kaki",   4, 1120000, "hoàn thành", "Đà Nẵng"),
    # Tháng 2
    ("DH021", "2026-02-01", "AO001", "Áo thun basic",     8, 1440000, "hoàn thành", "TP HCM"),
    ("DH022", "2026-02-01", "QU002", "Quần jean ống rộng",4, 1920000, "hoàn thành", "Hà Nội"),
    ("DH023", "2026-02-07", "VA001", "Váy hoa nhí",       5, 1900000, "hoàn thành", "Đà Nẵng"),
    ("DH024", "2026-02-07", "AO002", "Áo thun basic",     6, 1080000, "hoàn thành", "Cần Thơ"),
    ("DH025", "2026-02-14", "VA002", "Váy suông dài",     4, 1680000, "hoàn thành", "TP HCM"),
    ("DH026", "2026-02-14", "AO005", "Áo polo",           3,  840000, "hoàn thành", "Hà Nội"),
    ("DH027", "2026-02-20", "QU004", "Quần tây văn phòng",2, 1040000, "hoàn thành", "Hà Nội"),
    ("DH028", "2026-02-25", "AO003", "Áo sơ mi kẻ",      4, 1400000, "hoàn thành", "TP HCM"),
    # Tháng 3
    ("DH029", "2026-03-05", "AO001", "Áo thun basic",     5,  900000, "hoàn thành", "Hà Nội"),
    ("DH030", "2026-03-10", "QU001", "Quần jeans slim",   4, 1800000, "hoàn thành", "TP HCM"),
    ("DH031", "2026-03-15", "VA001", "Váy hoa nhí",       6, 2280000, "hoàn thành", "Đà Nẵng"),
    ("DH032", "2026-03-20", "AO004", "Áo hoodie",         3, 1350000, "hoàn thành", "Hà Nội"),
]


# ─── Shared calendar ─────────────────────────────────────────────────────

CALENDAR_H = ["solar_date", "lunar_date", "ten_am_lich", "ngay_le"]
CALENDAR_ROWS = [
    ("2026-01-01", "2025-11-13", "Mùng 13 tháng 11", "Tết Dương lịch"),
    ("2026-01-28", "2025-12-10", "Mùng 10 tháng 12", ""),
    ("2026-01-29", "2025-12-11", "Mùng 11 tháng 12", "Táo quân"),
    ("2026-02-17", "2026-01-01", "Mùng 1 tháng 1",   "Tết Nguyên Đán"),
    ("2026-02-18", "2026-01-02", "Mùng 2 tháng 1",   "Tết Nguyên Đán"),
    ("2026-02-19", "2026-01-03", "Mùng 3 tháng 1",   "Tết Nguyên Đán"),
    ("2026-04-30", "2026-03-13", "Mùng 13 tháng 3",  "Giải phóng miền Nam"),
    ("2026-05-01", "2026-03-14", "Mùng 14 tháng 3",  "Quốc tế Lao động"),
]


# ─── Rulebook ─────────────────────────────────────────────────────────────

RULEBOOK = """\
# Quy tắc nghiệp vụ chung

## Doanh thu
Doanh thu là tổng giá trị tong_tien hoặc doanh_thu trong kỳ, chỉ tính đơn hoàn thành.
Đơn hủy (trang_thai = 'huỷ') không tính vào doanh thu.

## Lợi nhuận
Lợi nhuận gộp = (gia_ban - gia_nhap) * so_luong.
Nếu không có trường gia_nhap, không thể tính lợi nhuận.

## Thời gian
"Tháng 1" = 2026-01-01 đến 2026-01-31.
"Quý 1" = 2026-01-01 đến 2026-03-31.
"Tới ngày X" hoặc "đến ngày X" nghĩa là ngay <= 'YYYY-MM-DD'.
Ngày mặc định của "ngày 3/3" là 2026-03-03; "tháng 2" là năm 2026.

## Hàng bán chạy
Hàng bán chạy nhất theo số lượng: dùng SUM(so_luong), không phải SUM(doanh_thu).

## Phần trăm
Trả về số thực (ví dụ: 35.5 cho 35.5%), không nhân thêm 100.
"""


# ─── Question definitions with oracle SQL ────────────────────────────────

def _questions(biz: str, as_of: str) -> list[dict]:
    return []


QUESTIONS: list[dict] = [
    # ════ biz_cafe ═══════════════════════════════════════════════════════════
    {"id": "cafe_01", "business_id": "biz_cafe",
     "question": "Tổng doanh thu tháng 1 năm 2026 của quán là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(doanh_thu AS INTEGER)) FROM \"sales\" WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01'"},

    {"id": "cafe_02", "business_id": "biz_cafe",
     "question": "Sản phẩm nào bán chạy nhất (theo số lượng) trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT san_pham FROM \"sales\" WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01' GROUP BY san_pham ORDER BY SUM(CAST(so_luong AS INTEGER)) DESC LIMIT 1"},

    {"id": "cafe_03", "business_id": "biz_cafe",
     "question": "Nhân viên nào bán được nhiều doanh thu nhất trong tháng 2?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT nhan_vien FROM \"sales\" WHERE ngay >= '2026-02-01' AND ngay < '2026-03-01' GROUP BY nhan_vien ORDER BY SUM(CAST(doanh_thu AS INTEGER)) DESC LIMIT 1"},

    {"id": "cafe_04", "business_id": "biz_cafe",
     "question": "Quán có bao nhiêu ngày bán hàng khác nhau trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT COUNT(DISTINCT ngay) FROM \"sales\" WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01'"},

    {"id": "cafe_05", "business_id": "biz_cafe",
     "question": "Hình thức thanh toán nào khách dùng nhiều nhất (theo số lần giao dịch)?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT hinh_thuc FROM \"sales\" GROUP BY hinh_thuc ORDER BY COUNT(*) DESC LIMIT 1"},

    {"id": "cafe_06", "business_id": "biz_cafe",
     "question": "Tổng doanh thu ngày 14 tháng 2 là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(doanh_thu AS INTEGER)) FROM \"sales\" WHERE ngay = '2026-02-14'"},

    {"id": "cafe_07", "business_id": "biz_cafe",
     "question": "Trà sữa bán ra tổng cộng bao nhiêu ly trong quý 1 (tháng 1 đến tháng 3)?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(so_luong AS INTEGER)) FROM \"sales\" WHERE san_pham = 'Trà sữa' AND ngay >= '2026-01-01' AND ngay < '2026-04-01'"},

    {"id": "cafe_08", "business_id": "biz_cafe",
     "question": "Cà phê sữa chiếm bao nhiêu phần trăm (%) doanh thu trong tháng 2?",
     "as_of_date": "2026-05-01", "type": "percent",
     "oracle_sql": "SELECT ROUND(100.0 * SUM(CASE WHEN san_pham = 'Cà phê sữa' THEN CAST(doanh_thu AS REAL) ELSE 0 END) / SUM(CAST(doanh_thu AS REAL)), 2) FROM \"sales\" WHERE ngay >= '2026-02-01' AND ngay < '2026-03-01'"},

    {"id": "cafe_09", "business_id": "biz_cafe",
     "question": "Sản phẩm nào có số lượng tồn kho thấp nhất trong kho?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT san_pham FROM \"inventory__stock\" ORDER BY CAST(ton_kho AS INTEGER) ASC LIMIT 1"},

    {"id": "cafe_10", "business_id": "biz_cafe",
     "question": "Liệt kê tên tất cả các sản phẩm hiện có trong kho của quán.",
     "as_of_date": "2026-05-01", "type": "list",
     "oracle_sql": "SELECT san_pham FROM \"inventory__stock\" ORDER BY san_pham"},

    {"id": "cafe_11", "business_id": "biz_cafe",
     "question": "Doanh thu tháng 1 có lớn hơn doanh thu tháng 2 không?",
     "as_of_date": "2026-05-01", "type": "boolean",
     "oracle_sql": "SELECT SUM(CASE WHEN ngay < '2026-02-01' THEN CAST(doanh_thu AS INTEGER) ELSE 0 END) > SUM(CASE WHEN ngay >= '2026-02-01' AND ngay < '2026-03-01' THEN CAST(doanh_thu AS INTEGER) ELSE 0 END) FROM \"sales\" WHERE ngay < '2026-03-01'"},

    {"id": "cafe_12", "business_id": "biz_cafe",
     "question": "Tổng doanh thu trong một ngày cao nhất của tháng 3 là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT MAX(daily) FROM (SELECT SUM(CAST(doanh_thu AS INTEGER)) AS daily FROM \"sales\" WHERE ngay >= '2026-03-01' AND ngay < '2026-04-01' GROUP BY ngay)"},

    {"id": "cafe_13", "business_id": "biz_cafe",
     "question": "Tổng số lượng bánh mì bán ra trong tháng 3?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(so_luong AS INTEGER)) FROM \"sales\" WHERE san_pham = 'Bánh mì' AND ngay >= '2026-03-01' AND ngay < '2026-04-01'"},

    {"id": "cafe_14", "business_id": "biz_cafe",
     "question": "Doanh thu trung bình mỗi ngày bán hàng trong tháng 3 là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT ROUND(AVG(daily), 2) FROM (SELECT SUM(CAST(doanh_thu AS INTEGER)) AS daily FROM \"sales\" WHERE ngay >= '2026-03-01' AND ngay < '2026-04-01' GROUP BY ngay)"},

    {"id": "cafe_15", "business_id": "biz_cafe",
     "question": "Nhân viên Cường bán được tổng bao nhiêu tiền trong tháng 2?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(doanh_thu AS INTEGER)) FROM \"sales\" WHERE nhan_vien = 'Cường' AND ngay >= '2026-02-01' AND ngay < '2026-03-01'"},

    {"id": "cafe_16", "business_id": "biz_cafe",
     "question": "Quán có bao nhiêu loại sản phẩm khác nhau đã bán từ trước đến nay?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT COUNT(DISTINCT san_pham) FROM \"sales\""},

    {"id": "cafe_17", "business_id": "biz_cafe",
     "question": "Tổng số lượng sinh tố bán trong tháng 1 và tháng 2 cộng lại là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(so_luong AS INTEGER)) FROM \"sales\" WHERE san_pham = 'Sinh tố' AND ngay >= '2026-01-01' AND ngay < '2026-03-01'"},

    {"id": "cafe_18", "business_id": "biz_cafe",
     "question": "Doanh thu tháng 2 theo từng sản phẩm là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "table",
     "oracle_sql": "SELECT san_pham, SUM(CAST(doanh_thu AS INTEGER)) AS tong_doanh_thu FROM \"sales\" WHERE ngay >= '2026-02-01' AND ngay < '2026-03-01' GROUP BY san_pham ORDER BY tong_doanh_thu DESC"},

    {"id": "cafe_19", "business_id": "biz_cafe",
     "question": "Ngày nào có tổng doanh thu cao nhất trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT ngay FROM \"sales\" WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01' GROUP BY ngay ORDER BY SUM(CAST(doanh_thu AS INTEGER)) DESC LIMIT 1"},

    {"id": "cafe_20", "business_id": "biz_cafe",
     "question": "Khách hàng thân thiết của quán là ai?",
     "as_of_date": "2026-05-01", "type": "unanswerable",
     "oracle_sql": None},

    {"id": "cafe_21", "business_id": "biz_cafe",
     "question": "Chi phí nguyên liệu tháng 1 là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "unanswerable",
     "oracle_sql": None},

    # ════ biz_pharmacy ═══════════════════════════════════════════════════════
    {"id": "pharma_01", "business_id": "biz_pharmacy",
     "question": "Tổng doanh thu trong tháng 1 của nhà thuốc là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(tong_tien AS INTEGER)) FROM \"transactions__giao_dich\" WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01'"},

    {"id": "pharma_02", "business_id": "biz_pharmacy",
     "question": "Thuốc nào được bán nhiều nhất (theo số lượng) trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT ten_thuoc FROM \"transactions__giao_dich\" WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01' GROUP BY ten_thuoc ORDER BY SUM(CAST(so_luong AS INTEGER)) DESC LIMIT 1"},

    {"id": "pharma_03", "business_id": "biz_pharmacy",
     "question": "Nhà thuốc có bao nhiêu khách hàng khác nhau đã mua hàng?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT COUNT(DISTINCT ten_khach) FROM \"transactions__giao_dich\""},

    {"id": "pharma_04", "business_id": "biz_pharmacy",
     "question": "Giá trung bình của các loại thuốc giảm đau là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT ROUND(AVG(CAST(don_gia AS REAL)), 2) FROM \"products\" WHERE loai = 'Giảm đau'"},

    {"id": "pharma_05", "business_id": "biz_pharmacy",
     "question": "Loại thuốc nào có nhiều sản phẩm (mã thuốc) nhất trong danh mục?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT loai FROM \"products\" GROUP BY loai ORDER BY COUNT(*) DESC LIMIT 1"},

    {"id": "pharma_06", "business_id": "biz_pharmacy",
     "question": "Tổng số lượng tồn kho hiện tại của tất cả thuốc là bao nhiêu hộp/vỉ?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(so_luong_ton AS INTEGER)) FROM \"products\""},

    {"id": "pharma_07", "business_id": "biz_pharmacy",
     "question": "Doanh thu tháng 2 có nhiều hơn tháng 1 không?",
     "as_of_date": "2026-05-01", "type": "boolean",
     "oracle_sql": "SELECT SUM(CASE WHEN ngay >= '2026-02-01' AND ngay < '2026-03-01' THEN CAST(tong_tien AS INTEGER) ELSE 0 END) > SUM(CASE WHEN ngay >= '2026-01-01' AND ngay < '2026-02-01' THEN CAST(tong_tien AS INTEGER) ELSE 0 END) FROM \"transactions__giao_dich\""},

    {"id": "pharma_08", "business_id": "biz_pharmacy",
     "question": "Thuốc nào có đơn giá cao nhất trong danh mục?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT ten_thuoc FROM \"products\" ORDER BY CAST(don_gia AS INTEGER) DESC LIMIT 1"},

    {"id": "pharma_09", "business_id": "biz_pharmacy",
     "question": "Khách hàng nào mua thuốc nhiều lần nhất (số lần giao dịch)?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT ten_khach FROM \"transactions__giao_dich\" GROUP BY ten_khach ORDER BY COUNT(*) DESC LIMIT 1"},

    {"id": "pharma_10", "business_id": "biz_pharmacy",
     "question": "Nhóm thuốc vitamin chiếm bao nhiêu phần trăm doanh thu tháng 1?",
     "as_of_date": "2026-05-01", "type": "percent",
     "oracle_sql": "SELECT ROUND(100.0 * SUM(CASE WHEN ten_thuoc LIKE 'Vitamin%' OR ten_thuoc LIKE 'Zinc%' THEN CAST(tong_tien AS REAL) ELSE 0 END) / SUM(CAST(tong_tien AS REAL)), 2) FROM \"transactions__giao_dich\" WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01'"},

    {"id": "pharma_11", "business_id": "biz_pharmacy",
     "question": "Liệt kê tất cả các loại thuốc (nhóm loại) có trong danh mục.",
     "as_of_date": "2026-05-01", "type": "list",
     "oracle_sql": "SELECT DISTINCT loai FROM \"products\" ORDER BY loai"},

    {"id": "pharma_12", "business_id": "biz_pharmacy",
     "question": "Doanh thu trung bình mỗi giao dịch trong tháng 1 là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT ROUND(AVG(CAST(tong_tien AS REAL)), 2) FROM \"transactions__giao_dich\" WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01'"},

    {"id": "pharma_13", "business_id": "biz_pharmacy",
     "question": "Thuốc Paracetamol bán được tổng bao nhiêu hộp trong tháng 1 và 2?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(so_luong AS INTEGER)) FROM \"transactions__giao_dich\" WHERE ten_thuoc = 'Paracetamol 500mg' AND ngay >= '2026-01-01' AND ngay < '2026-03-01'"},

    {"id": "pharma_14", "business_id": "biz_pharmacy",
     "question": "Tổng doanh thu từ nhóm thuốc kháng sinh từ đầu năm đến hết tháng 3?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(tong_tien AS INTEGER)) FROM \"transactions__giao_dich\" WHERE (ten_thuoc LIKE 'Amoxicillin%' OR ten_thuoc LIKE 'Azithromycin%') AND ngay >= '2026-01-01' AND ngay < '2026-04-01'"},

    {"id": "pharma_15", "business_id": "biz_pharmacy",
     "question": "Doanh thu theo từng loại thuốc trong tháng 1 là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "table",
     "oracle_sql": "SELECT p.loai, SUM(CAST(t.tong_tien AS INTEGER)) AS tong_doanh_thu FROM \"transactions__giao_dich\" t JOIN \"products\" p ON t.ma_thuoc = p.ma_thuoc WHERE t.ngay >= '2026-01-01' AND t.ngay < '2026-02-01' GROUP BY p.loai ORDER BY tong_doanh_thu DESC"},

    {"id": "pharma_16", "business_id": "biz_pharmacy",
     "question": "Có bao nhiêu giao dịch trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT COUNT(*) FROM \"transactions__giao_dich\" WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01'"},

    {"id": "pharma_17", "business_id": "biz_pharmacy",
     "question": "Hạn sử dụng của thuốc Paracetamol là khi nào?",
     "as_of_date": "2026-05-01", "type": "unanswerable",
     "oracle_sql": None},

    {"id": "pharma_18", "business_id": "biz_pharmacy",
     "question": "Nhà cung cấp thuốc của nhà thuốc là ai?",
     "as_of_date": "2026-05-01", "type": "unanswerable",
     "oracle_sql": None},

    {"id": "pharma_19", "business_id": "biz_pharmacy",
     "question": "Ngày nào trong tháng 1 có doanh thu cao nhất?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT ngay FROM \"transactions__giao_dich\" WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01' GROUP BY ngay ORDER BY SUM(CAST(tong_tien AS INTEGER)) DESC LIMIT 1"},

    {"id": "pharma_20", "business_id": "biz_pharmacy",
     "question": "Khách hàng Nguyễn Thị A đã chi tổng bao nhiêu tiền mua thuốc?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(tong_tien AS INTEGER)) FROM \"transactions__giao_dich\" WHERE ten_khach = 'Nguyễn Thị A'"},

    {"id": "pharma_21", "business_id": "biz_pharmacy",
     "question": "Tổng doanh thu từ đầu năm 2026 tới hết tháng 3 là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(tong_tien AS INTEGER)) FROM \"transactions__giao_dich\" WHERE ngay >= '2026-01-01' AND ngay < '2026-04-01'"},

    # ════ biz_restaurant ═════════════════════════════════════════════════════
    {"id": "rest_01", "business_id": "biz_restaurant",
     "question": "Tổng doanh thu (đơn hoàn thành) của nhà hàng trong tháng 1 là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(tong_tien AS INTEGER)) FROM \"orders\" WHERE trang_thai = 'hoàn thành' AND ngay >= '2026-01-01' AND ngay < '2026-02-01'"},

    {"id": "rest_02", "business_id": "biz_restaurant",
     "question": "Món ăn nào được gọi nhiều nhất (theo số lượng) trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT ten_mon FROM \"orders\" WHERE trang_thai = 'hoàn thành' AND ngay >= '2026-01-01' AND ngay < '2026-02-01' GROUP BY ten_mon ORDER BY SUM(CAST(so_luong AS INTEGER)) DESC LIMIT 1"},

    {"id": "rest_03", "business_id": "biz_restaurant",
     "question": "Có bao nhiêu lượt đặt bàn trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT COUNT(*) FROM \"reservations__bookings\" WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01'"},

    {"id": "rest_04", "business_id": "biz_restaurant",
     "question": "Món ăn nào có giá cao nhất trong thực đơn?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT ten_mon FROM \"menu__menu\" ORDER BY CAST(gia AS INTEGER) DESC LIMIT 1"},

    {"id": "rest_05", "business_id": "biz_restaurant",
     "question": "Nhà hàng có bao nhiêu loại món ăn khác nhau trong thực đơn?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT COUNT(DISTINCT loai) FROM \"menu__menu\""},

    {"id": "rest_06", "business_id": "biz_restaurant",
     "question": "Tổng số khách ăn tại bàn (có đặt chỗ, trạng thái xác nhận) trong tháng 1 là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(so_nguoi AS INTEGER)) FROM \"reservations__bookings\" WHERE trang_thai = 'xác nhận' AND ngay >= '2026-01-01' AND ngay < '2026-02-01'"},

    {"id": "rest_07", "business_id": "biz_restaurant",
     "question": "Khách nào đặt bàn với số người nhiều nhất trong một lần?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT ten_khach FROM \"reservations__bookings\" ORDER BY CAST(so_nguoi AS INTEGER) DESC LIMIT 1"},

    {"id": "rest_08", "business_id": "biz_restaurant",
     "question": "Tỷ lệ đơn hoàn thành (trên tổng đơn) trong tháng 1 là bao nhiêu phần trăm?",
     "as_of_date": "2026-05-01", "type": "percent",
     "oracle_sql": "SELECT ROUND(100.0 * SUM(CASE WHEN trang_thai = 'hoàn thành' THEN 1 ELSE 0 END) / COUNT(*), 2) FROM \"orders\" WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01'"},

    {"id": "rest_09", "business_id": "biz_restaurant",
     "question": "Doanh thu từ nhóm món hải sản trong tháng 1 là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(o.tong_tien AS INTEGER)) FROM \"orders\" o JOIN \"menu__menu\" m ON o.ten_mon = m.ten_mon WHERE m.loai = 'Hải sản' AND o.trang_thai = 'hoàn thành' AND o.ngay >= '2026-01-01' AND o.ngay < '2026-02-01'"},

    {"id": "rest_10", "business_id": "biz_restaurant",
     "question": "Doanh thu trung bình mỗi đơn hàng hoàn thành là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT ROUND(AVG(CAST(tong_tien AS REAL)), 2) FROM \"orders\" WHERE trang_thai = 'hoàn thành'"},

    {"id": "rest_11", "business_id": "biz_restaurant",
     "question": "Liệt kê các loại món ăn (phân nhóm) trong thực đơn.",
     "as_of_date": "2026-05-01", "type": "list",
     "oracle_sql": "SELECT DISTINCT loai FROM \"menu__menu\" ORDER BY loai"},

    {"id": "rest_12", "business_id": "biz_restaurant",
     "question": "Số lượt đặt bàn bị huỷ trong toàn bộ dữ liệu là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT COUNT(*) FROM \"reservations__bookings\" WHERE trang_thai = 'huỷ'"},

    {"id": "rest_13", "business_id": "biz_restaurant",
     "question": "Doanh thu theo từng loại món ăn trong tháng 1 (chỉ đơn hoàn thành)?",
     "as_of_date": "2026-05-01", "type": "table",
     "oracle_sql": "SELECT m.loai, SUM(CAST(o.tong_tien AS INTEGER)) AS tong_doanh_thu FROM \"orders\" o JOIN \"menu__menu\" m ON o.ten_mon = m.ten_mon WHERE o.trang_thai = 'hoàn thành' AND o.ngay >= '2026-01-01' AND o.ngay < '2026-02-01' GROUP BY m.loai ORDER BY tong_doanh_thu DESC"},

    {"id": "rest_14", "business_id": "biz_restaurant",
     "question": "Ngày nào trong tháng 1 có doanh thu cao nhất?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT ngay FROM \"orders\" WHERE trang_thai = 'hoàn thành' AND ngay >= '2026-01-01' AND ngay < '2026-02-01' GROUP BY ngay ORDER BY SUM(CAST(tong_tien AS INTEGER)) DESC LIMIT 1"},

    {"id": "rest_15", "business_id": "biz_restaurant",
     "question": "Tổng doanh thu tháng 2 của nhà hàng (chỉ đơn hoàn thành)?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(tong_tien AS INTEGER)) FROM \"orders\" WHERE trang_thai = 'hoàn thành' AND ngay >= '2026-02-01' AND ngay < '2026-03-01'"},

    {"id": "rest_16", "business_id": "biz_restaurant",
     "question": "Chi phí vật tư và nhân sự của nhà hàng trong tháng 1 là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "unanswerable",
     "oracle_sql": None},

    {"id": "rest_17", "business_id": "biz_restaurant",
     "question": "Nhà hàng có bao nhiêu nhân viên phục vụ?",
     "as_of_date": "2026-05-01", "type": "unanswerable",
     "oracle_sql": None},

    {"id": "rest_18", "business_id": "biz_restaurant",
     "question": "Phở bò bán được tổng bao nhiêu tô trong tháng 1 (đơn hoàn thành)?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(so_luong AS INTEGER)) FROM \"orders\" WHERE ten_mon = 'Phở bò' AND trang_thai = 'hoàn thành' AND ngay >= '2026-01-01' AND ngay < '2026-02-01'"},

    {"id": "rest_19", "business_id": "biz_restaurant",
     "question": "Nhà hàng có bao nhiêu món trong thực đơn?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT COUNT(*) FROM \"menu__menu\""},

    {"id": "rest_20", "business_id": "biz_restaurant",
     "question": "Khách nào đặt bàn nhiều lần nhất (số lần đặt)?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT ten_khach FROM \"reservations__bookings\" GROUP BY ten_khach ORDER BY COUNT(*) DESC LIMIT 1"},

    {"id": "rest_21", "business_id": "biz_restaurant",
     "question": "Doanh thu ngày 15/1 (đơn hoàn thành) là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(tong_tien AS INTEGER)) FROM \"orders\" WHERE trang_thai = 'hoàn thành' AND ngay = '2026-01-15'"},

    # ════ biz_electronics ════════════════════════════════════════════════════
    {"id": "elec_01", "business_id": "biz_electronics",
     "question": "Tổng doanh thu trong tháng 1 của cửa hàng là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(tong_tien AS INTEGER)) FROM \"sales__deals\" WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01'"},

    {"id": "elec_02", "business_id": "biz_electronics",
     "question": "Sản phẩm nào bán được nhiều doanh thu nhất trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT ten_sp FROM \"sales__deals\" WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01' GROUP BY ten_sp ORDER BY SUM(CAST(tong_tien AS INTEGER)) DESC LIMIT 1"},

    {"id": "elec_03", "business_id": "biz_electronics",
     "question": "Lợi nhuận gộp trong tháng 1 là bao nhiêu (tính theo gia_ban - gia_nhap nhân số lượng)?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM((CAST(s.gia_ban AS INTEGER) - CAST(c.gia_nhap AS INTEGER)) * CAST(s.so_luong AS INTEGER)) FROM \"sales__deals\" s JOIN \"catalog__items\" c ON s.ma_sp = c.ma_sp WHERE s.ngay >= '2026-01-01' AND s.ngay < '2026-02-01'"},

    {"id": "elec_04", "business_id": "biz_electronics",
     "question": "Danh mục sản phẩm nào bán được nhiều chiếc nhất trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT c.loai FROM \"sales__deals\" s JOIN \"catalog__items\" c ON s.ma_sp = c.ma_sp WHERE s.ngay >= '2026-01-01' AND s.ngay < '2026-02-01' GROUP BY c.loai ORDER BY SUM(CAST(s.so_luong AS INTEGER)) DESC LIMIT 1"},

    {"id": "elec_05", "business_id": "biz_electronics",
     "question": "Sản phẩm nào có giá bán cao nhất trong danh mục?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT ten_sp FROM \"catalog__items\" ORDER BY CAST(gia_ban AS INTEGER) DESC LIMIT 1"},

    {"id": "elec_06", "business_id": "biz_electronics",
     "question": "Cửa hàng có bao nhiêu mã sản phẩm trong danh mục?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT COUNT(*) FROM \"catalog__items\""},

    {"id": "elec_07", "business_id": "biz_electronics",
     "question": "Doanh thu tháng 2 có lớn hơn tháng 1 không?",
     "as_of_date": "2026-05-01", "type": "boolean",
     "oracle_sql": "SELECT SUM(CASE WHEN ngay >= '2026-02-01' AND ngay < '2026-03-01' THEN CAST(tong_tien AS INTEGER) ELSE 0 END) > SUM(CASE WHEN ngay >= '2026-01-01' AND ngay < '2026-02-01' THEN CAST(tong_tien AS INTEGER) ELSE 0 END) FROM \"sales__deals\""},

    {"id": "elec_08", "business_id": "biz_electronics",
     "question": "Hóa đơn có giá trị lớn nhất là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT MAX(CAST(tong_tien AS INTEGER)) FROM \"sales__deals\""},

    {"id": "elec_09", "business_id": "biz_electronics",
     "question": "Sản phẩm nào có thời gian bảo hành dài nhất?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT ten_sp FROM \"catalog__items\" ORDER BY CAST(bao_hanh_thang AS INTEGER) DESC LIMIT 1"},

    {"id": "elec_10", "business_id": "biz_electronics",
     "question": "Liệt kê tất cả các danh mục sản phẩm trong cửa hàng.",
     "as_of_date": "2026-05-01", "type": "list",
     "oracle_sql": "SELECT DISTINCT loai FROM \"catalog__items\" ORDER BY loai"},

    {"id": "elec_11", "business_id": "biz_electronics",
     "question": "Có bao nhiêu hóa đơn bán hàng trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT COUNT(*) FROM \"sales__deals\" WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01'"},

    {"id": "elec_12", "business_id": "biz_electronics",
     "question": "Điện thoại (loại 'Điện thoại') bán được bao nhiêu chiếc trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(s.so_luong AS INTEGER)) FROM \"sales__deals\" s JOIN \"catalog__items\" c ON s.ma_sp = c.ma_sp WHERE c.loai = 'Điện thoại' AND s.ngay >= '2026-01-01' AND s.ngay < '2026-02-01'"},

    {"id": "elec_13", "business_id": "biz_electronics",
     "question": "Lợi nhuận gộp theo từng danh mục trong tháng 1 là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "table",
     "oracle_sql": "SELECT c.loai, SUM((CAST(s.gia_ban AS INTEGER) - CAST(c.gia_nhap AS INTEGER)) * CAST(s.so_luong AS INTEGER)) AS loi_nhuan FROM \"sales__deals\" s JOIN \"catalog__items\" c ON s.ma_sp = c.ma_sp WHERE s.ngay >= '2026-01-01' AND s.ngay < '2026-02-01' GROUP BY c.loai ORDER BY loi_nhuan DESC"},

    {"id": "elec_14", "business_id": "biz_electronics",
     "question": "Giá trung bình của sản phẩm thuộc danh mục laptop là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT ROUND(AVG(CAST(gia_ban AS REAL)), 0) FROM \"catalog__items\" WHERE loai = 'Laptop'"},

    {"id": "elec_15", "business_id": "biz_electronics",
     "question": "Tổng doanh thu từ phụ kiện trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(s.tong_tien AS INTEGER)) FROM \"sales__deals\" s JOIN \"catalog__items\" c ON s.ma_sp = c.ma_sp WHERE c.loai = 'Phụ kiện' AND s.ngay >= '2026-01-01' AND s.ngay < '2026-02-01'"},

    {"id": "elec_16", "business_id": "biz_electronics",
     "question": "Thuế VAT phải nộp trong tháng 1 là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "unanswerable",
     "oracle_sql": None},

    {"id": "elec_17", "business_id": "biz_electronics",
     "question": "Nhà cung cấp của iPhone 16 là ai?",
     "as_of_date": "2026-05-01", "type": "unanswerable",
     "oracle_sql": None},

    {"id": "elec_18", "business_id": "biz_electronics",
     "question": "Ngày nào có doanh thu cao nhất trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT ngay FROM \"sales__deals\" WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01' GROUP BY ngay ORDER BY SUM(CAST(tong_tien AS INTEGER)) DESC LIMIT 1"},

    {"id": "elec_19", "business_id": "biz_electronics",
     "question": "Tỷ lệ lợi nhuận gộp (lợi nhuận / doanh thu * 100) của cửa hàng trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "percent",
     "oracle_sql": "SELECT ROUND(100.0 * SUM((CAST(s.gia_ban AS INTEGER) - CAST(c.gia_nhap AS INTEGER)) * CAST(s.so_luong AS INTEGER)) / SUM(CAST(s.tong_tien AS REAL)), 2) FROM \"sales__deals\" s JOIN \"catalog__items\" c ON s.ma_sp = c.ma_sp WHERE s.ngay >= '2026-01-01' AND s.ngay < '2026-02-01'"},

    {"id": "elec_20", "business_id": "biz_electronics",
     "question": "Tổng doanh thu từ đầu năm đến hết tháng 3 của cửa hàng là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(tong_tien AS INTEGER)) FROM \"sales__deals\" WHERE ngay >= '2026-01-01' AND ngay < '2026-04-01'"},

    {"id": "elec_21", "business_id": "biz_electronics",
     "question": "MacBook Pro M4 bán được bao nhiêu chiếc từ đầu năm?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(so_luong AS INTEGER)) FROM \"sales__deals\" WHERE ten_sp = 'MacBook Pro M4'"},

    # ════ biz_fashion ════════════════════════════════════════════════════════
    {"id": "fash_01", "business_id": "biz_fashion",
     "question": "Tổng doanh thu tháng 1 của cửa hàng thời trang là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(tong_tien AS INTEGER)) FROM \"orders__sales\" WHERE trang_thai = 'hoàn thành' AND ngay >= '2026-01-01' AND ngay < '2026-02-01'"},

    {"id": "fash_02", "business_id": "biz_fashion",
     "question": "Mặt hàng nào bán chạy nhất (theo số lượng) trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT ten_hang FROM \"orders__sales\" WHERE trang_thai = 'hoàn thành' AND ngay >= '2026-01-01' AND ngay < '2026-02-01' GROUP BY ten_hang ORDER BY SUM(CAST(so_luong AS INTEGER)) DESC LIMIT 1"},

    {"id": "fash_03", "business_id": "biz_fashion",
     "question": "Tỉnh/thành phố nào đặt mua nhiều nhất (theo số lượng) trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT tinh_thanh FROM \"orders__sales\" WHERE trang_thai = 'hoàn thành' AND ngay >= '2026-01-01' AND ngay < '2026-02-01' GROUP BY tinh_thanh ORDER BY SUM(CAST(so_luong AS INTEGER)) DESC LIMIT 1"},

    {"id": "fash_04", "business_id": "biz_fashion",
     "question": "Loại hàng nào (áo, quần, váy, phụ kiện) chiếm doanh thu cao nhất trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT p.loai FROM \"orders__sales\" o JOIN \"products\" p ON o.ma_hang = p.ma_hang WHERE o.trang_thai = 'hoàn thành' AND o.ngay >= '2026-01-01' AND o.ngay < '2026-02-01' GROUP BY p.loai ORDER BY SUM(CAST(o.tong_tien AS INTEGER)) DESC LIMIT 1"},

    {"id": "fash_05", "business_id": "biz_fashion",
     "question": "Lợi nhuận gộp (doanh thu - giá nhập nhân số lượng) tháng 1 là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM((CAST(o.tong_tien AS INTEGER) - CAST(p.gia_nhap AS INTEGER) * CAST(o.so_luong AS INTEGER))) FROM \"orders__sales\" o JOIN \"products\" p ON o.ma_hang = p.ma_hang WHERE o.trang_thai = 'hoàn thành' AND o.ngay >= '2026-01-01' AND o.ngay < '2026-02-01'"},

    {"id": "fash_06", "business_id": "biz_fashion",
     "question": "Doanh thu tháng 2 theo từng tỉnh/thành phố là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "table",
     "oracle_sql": "SELECT tinh_thanh, SUM(CAST(tong_tien AS INTEGER)) AS tong_doanh_thu FROM \"orders__sales\" WHERE trang_thai = 'hoàn thành' AND ngay >= '2026-02-01' AND ngay < '2026-03-01' GROUP BY tinh_thanh ORDER BY tong_doanh_thu DESC"},

    {"id": "fash_07", "business_id": "biz_fashion",
     "question": "Tỷ lệ đơn hàng hoàn thành trong tháng 1 là bao nhiêu phần trăm?",
     "as_of_date": "2026-05-01", "type": "percent",
     "oracle_sql": "SELECT ROUND(100.0 * SUM(CASE WHEN trang_thai = 'hoàn thành' THEN 1 ELSE 0 END) / COUNT(*), 2) FROM \"orders__sales\" WHERE ngay >= '2026-01-01' AND ngay < '2026-02-01'"},

    {"id": "fash_08", "business_id": "biz_fashion",
     "question": "Liệt kê tất cả các tỉnh/thành phố đã đặt hàng.",
     "as_of_date": "2026-05-01", "type": "list",
     "oracle_sql": "SELECT DISTINCT tinh_thanh FROM \"orders__sales\" ORDER BY tinh_thanh"},

    {"id": "fash_09", "business_id": "biz_fashion",
     "question": "Doanh thu trung bình mỗi đơn hàng hoàn thành trong tháng 1 là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT ROUND(AVG(CAST(tong_tien AS REAL)), 2) FROM \"orders__sales\" WHERE trang_thai = 'hoàn thành' AND ngay >= '2026-01-01' AND ngay < '2026-02-01'"},

    {"id": "fash_10", "business_id": "biz_fashion",
     "question": "Mã hàng nào được đặt mua ở nhiều tỉnh thành nhất?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT ma_hang FROM \"orders__sales\" GROUP BY ma_hang ORDER BY COUNT(DISTINCT tinh_thanh) DESC LIMIT 1"},

    {"id": "fash_11", "business_id": "biz_fashion",
     "question": "Tổng doanh thu từ nhóm hàng Áo trong tháng 1 (đơn hoàn thành)?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(o.tong_tien AS INTEGER)) FROM \"orders__sales\" o JOIN \"products\" p ON o.ma_hang = p.ma_hang WHERE p.loai = 'Áo' AND o.trang_thai = 'hoàn thành' AND o.ngay >= '2026-01-01' AND o.ngay < '2026-02-01'"},

    {"id": "fash_12", "business_id": "biz_fashion",
     "question": "Có bao nhiêu mã hàng khác nhau bán được trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT COUNT(DISTINCT ma_hang) FROM \"orders__sales\" WHERE trang_thai = 'hoàn thành' AND ngay >= '2026-01-01' AND ngay < '2026-02-01'"},

    {"id": "fash_13", "business_id": "biz_fashion",
     "question": "Đơn hàng có giá trị lớn nhất là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT MAX(CAST(tong_tien AS INTEGER)) FROM \"orders__sales\""},

    {"id": "fash_14", "business_id": "biz_fashion",
     "question": "Doanh thu tháng 2 có lớn hơn tháng 1 không (chỉ đơn hoàn thành)?",
     "as_of_date": "2026-05-01", "type": "boolean",
     "oracle_sql": "SELECT SUM(CASE WHEN ngay >= '2026-02-01' AND ngay < '2026-03-01' THEN CAST(tong_tien AS INTEGER) ELSE 0 END) > SUM(CASE WHEN ngay >= '2026-01-01' AND ngay < '2026-02-01' THEN CAST(tong_tien AS INTEGER) ELSE 0 END) FROM \"orders__sales\" WHERE trang_thai = 'hoàn thành'"},

    {"id": "fash_15", "business_id": "biz_fashion",
     "question": "Tỉnh nào chiếm nhiều phần trăm doanh thu nhất trong tháng 1?",
     "as_of_date": "2026-05-01", "type": "string",
     "oracle_sql": "SELECT tinh_thanh FROM \"orders__sales\" WHERE trang_thai = 'hoàn thành' AND ngay >= '2026-01-01' AND ngay < '2026-02-01' GROUP BY tinh_thanh ORDER BY SUM(CAST(tong_tien AS INTEGER)) DESC LIMIT 1"},

    {"id": "fash_16", "business_id": "biz_fashion",
     "question": "Có bao nhiêu loại hàng khác nhau trong danh mục sản phẩm?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT COUNT(DISTINCT loai) FROM \"products\""},

    {"id": "fash_17", "business_id": "biz_fashion",
     "question": "Khách hàng thân thiết của cửa hàng thời trang này là ai?",
     "as_of_date": "2026-05-01", "type": "unanswerable",
     "oracle_sql": None},

    {"id": "fash_18", "business_id": "biz_fashion",
     "question": "Cửa hàng bán hàng online hay offline nhiều hơn?",
     "as_of_date": "2026-05-01", "type": "unanswerable",
     "oracle_sql": None},

    {"id": "fash_19", "business_id": "biz_fashion",
     "question": "Tổng số lượng đơn hàng hoàn thành trong toàn bộ dữ liệu là bao nhiêu?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT COUNT(*) FROM \"orders__sales\" WHERE trang_thai = 'hoàn thành'"},

    {"id": "fash_20", "business_id": "biz_fashion",
     "question": "Doanh thu tháng 3 theo từng loại hàng (Áo/Quần/Váy/Phụ kiện)?",
     "as_of_date": "2026-05-01", "type": "table",
     "oracle_sql": "SELECT p.loai, SUM(CAST(o.tong_tien AS INTEGER)) AS tong_doanh_thu FROM \"orders__sales\" o JOIN \"products\" p ON o.ma_hang = p.ma_hang WHERE o.trang_thai = 'hoàn thành' AND o.ngay >= '2026-03-01' AND o.ngay < '2026-04-01' GROUP BY p.loai ORDER BY tong_doanh_thu DESC"},

    {"id": "fash_21", "business_id": "biz_fashion",
     "question": "Tổng doanh thu từ đầu năm đến hết tháng 3 (đơn hoàn thành)?",
     "as_of_date": "2026-05-01", "type": "number",
     "oracle_sql": "SELECT SUM(CAST(tong_tien AS INTEGER)) FROM \"orders__sales\" WHERE trang_thai = 'hoàn thành' AND ngay >= '2026-01-01' AND ngay < '2026-04-01'"},
]


# ─── Business builders ────────────────────────────────────────────────────

def build_biz_cafe(biz_dir: Path) -> None:
    biz_dir.mkdir(parents=True, exist_ok=True)
    (biz_dir / "README.md").write_text(
        "# Quán Cà Phê Hương Việt\n\n"
        "Quán cà phê kinh doanh các loại đồ uống và bánh mì.\n"
        "- sales.csv: lịch sử bán hàng theo ngày\n"
        "- inventory.xlsx: tồn kho hiện tại\n",
        encoding="utf-8",
    )
    _csv(biz_dir / "sales.csv", CAFE_SALES_H, CAFE_SALES)
    _xlsx(biz_dir / "inventory.xlsx", "Stock", CAFE_INVENTORY_H, CAFE_INVENTORY)


def build_biz_pharmacy(biz_dir: Path) -> None:
    biz_dir.mkdir(parents=True, exist_ok=True)
    (biz_dir / "README.md").write_text(
        "# Nhà Thuốc Bình Minh\n\n"
        "Nhà thuốc bán lẻ dược phẩm.\n"
        "- products.csv: danh mục thuốc và tồn kho\n"
        "- transactions.sqlite/giao_dich: lịch sử bán hàng\n",
        encoding="utf-8",
    )
    _csv(biz_dir / "products.csv", PHARMA_PRODUCTS_H, PHARMA_PRODUCTS)
    _sqlite(biz_dir / "transactions.sqlite", "giao_dich", PHARMA_TX_H, PHARMA_TX)


def build_biz_restaurant(biz_dir: Path) -> None:
    biz_dir.mkdir(parents=True, exist_ok=True)
    (biz_dir / "README.md").write_text(
        "# Nhà Hàng Phú Quý\n\n"
        "Nhà hàng phục vụ ẩm thực Việt Nam.\n"
        "- orders.csv: danh sách đơn hàng (trạng thái: hoàn thành, huỷ)\n"
        "- menu.xlsx: thực đơn và giá\n"
        "- reservations.sqlite/bookings: đặt bàn trước\n",
        encoding="utf-8",
    )
    _csv(biz_dir / "orders.csv", RESTAURANT_ORDERS_H, RESTAURANT_ORDERS)
    _xlsx(biz_dir / "menu.xlsx", "Menu", RESTAURANT_MENU_H, RESTAURANT_MENU)
    _sqlite(biz_dir / "reservations.sqlite", "bookings", RESTAURANT_BOOKINGS_H, RESTAURANT_BOOKINGS)


def build_biz_electronics(biz_dir: Path) -> None:
    biz_dir.mkdir(parents=True, exist_ok=True)
    (biz_dir / "README.md").write_text(
        "# Cửa Hàng Điện Tử Thăng Long\n\n"
        "Cửa hàng bán điện thoại, laptop, máy tính bảng và phụ kiện.\n"
        "- catalog.xlsx: danh mục sản phẩm với giá nhập và giá bán\n"
        "- sales.sqlite/deals: hóa đơn bán hàng\n",
        encoding="utf-8",
    )
    _xlsx(biz_dir / "catalog.xlsx", "Items", ELEC_CATALOG_H, ELEC_CATALOG)
    _sqlite(biz_dir / "sales.sqlite", "deals", ELEC_SALES_H, ELEC_SALES)


def build_biz_fashion(biz_dir: Path) -> None:
    biz_dir.mkdir(parents=True, exist_ok=True)
    (biz_dir / "README.md").write_text(
        "# Thời Trang Thu Hà\n\n"
        "Cửa hàng thời trang bán áo, quần, váy và phụ kiện.\n"
        "- products.csv: danh mục hàng hoá với giá nhập và giá bán\n"
        "- orders.xlsx: đơn hàng theo tỉnh/thành phố\n",
        encoding="utf-8",
    )
    _csv(biz_dir / "products.csv", FASHION_PRODUCTS_H, FASHION_PRODUCTS)
    _xlsx(biz_dir / "orders.xlsx", "Sales", FASHION_ORDERS_H, FASHION_ORDERS)


# ─── Ground truth computation ─────────────────────────────────────────────

def _run_oracle(db, sql: str) -> Any:
    cols, rows = db.execute_readonly(sql)
    return cols, rows


def compute_ground_truth(benchmark_root: Path, questions: list[dict]) -> list[dict]:
    from src.ingestion import BusinessDB
    from src.agent import typed_result

    calendar_path = benchmark_root / "calendar.csv"
    results: list[dict] = []

    for q in questions:
        biz_id = q["business_id"]
        qtype = q["type"]
        sql = q.get("oracle_sql")

        if qtype == "unanswerable" or sql is None:
            results.append({"id": q["id"], "type": "unanswerable", "answer": "unanswerable"})
            continue

        biz_dir = benchmark_root / "data" / biz_id
        db = BusinessDB(biz_dir, calendar_path if calendar_path.is_file() else None)
        try:
            cols, rows = db.execute_readonly(sql)
            answer = typed_result(qtype, cols, rows)
            results.append({"id": q["id"], "type": qtype, "answer": answer})
        except Exception as exc:
            results.append({"id": q["id"], "type": qtype, "answer": None,
                            "error": f"{type(exc).__name__}: {exc}"})
        finally:
            db.close()

    return results


# ─── Main ─────────────────────────────────────────────────────────────────

def build_benchmark(out_root: Path) -> None:
    data_dir = out_root / "data"

    build_biz_cafe(data_dir / "biz_cafe")
    build_biz_pharmacy(data_dir / "biz_pharmacy")
    build_biz_restaurant(data_dir / "biz_restaurant")
    build_biz_electronics(data_dir / "biz_electronics")
    build_biz_fashion(data_dir / "biz_fashion")

    (out_root / "rulebook.md").write_text(RULEBOOK, encoding="utf-8")

    _csv(out_root / "calendar.csv", list(CALENDAR_H), CALENDAR_ROWS)

    with (out_root / "questions.jsonl").open("w", encoding="utf-8") as f:
        for q in QUESTIONS:
            row = {k: v for k, v in q.items() if k != "oracle_sql" and k != "type"}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    ground_truth = compute_ground_truth(out_root, QUESTIONS)
    errors = [g for g in ground_truth if g.get("error")]
    if errors:
        print(f"WARNING: {len(errors)} oracle SQL error(s):", file=sys.stderr)
        for e in errors:
            print(f"  {e['id']}: {e['error']}", file=sys.stderr)

    with (out_root / "ground_truth.jsonl").open("w", encoding="utf-8") as f:
        for gt in ground_truth:
            f.write(json.dumps(gt, ensure_ascii=False, default=str) + "\n")

    answerable = sum(1 for g in ground_truth if g["type"] != "unanswerable")
    unanswerable = sum(1 for g in ground_truth if g["type"] == "unanswerable")
    print(f"Benchmark written to {out_root}")
    print(f"  Questions: {len(QUESTIONS)} total — {answerable} answerable, {unanswerable} unanswerable")
    print(f"  Businesses: biz_cafe, biz_pharmacy, biz_restaurant, biz_electronics, biz_fashion")
    if not errors:
        print("  All oracle SQL verified OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate DataMate synthetic benchmark")
    parser.add_argument("--out", default=str(Path(__file__).parent),
                        help="Output root directory (default: benchmark/)")
    parser.add_argument("--verify", action="store_true",
                        help="Build and print answer stats, then exit")
    args = parser.parse_args()
    out = Path(args.out)
    build_benchmark(out)
    if args.verify:
        with (out / "ground_truth.jsonl").open(encoding="utf-8") as f:
            gt = [json.loads(l) for l in f if l.strip()]
        for item in gt:
            status = "ERROR" if item.get("error") else "OK"
            ans = str(item.get("answer", ""))[:60]
            print(f"[{status}] {item['id']:15s} ({item['type']:12s})  {ans}")


if __name__ == "__main__":
    main()
