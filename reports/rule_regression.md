# Báo cáo Regression Tầng Dữ Liệu (Task T5 — Không dùng LLM)

**Tổng kết: 942/942 (100.00% đúng trên câu đã chọn)** | Doanh thu tháng (`revenue`): **197/197 (100.00%)** | Thời gian chạy 30 shop: `630.5s`

## 1. Thống kê theo Intent

| Intent | Tổng câu khớp tag + kỳ tường minh | Đã chọn (Selected) | Đúng (Correct) | Sai (Wrong) | Bỏ qua (Skipped) | % Đúng trên câu đã chọn |
|---|---:|---:|---:|---:|---:|---:|
| `revenue` | 260 | 197 | 197 | 0 | 63 | **100.00%** |
| `order_count` | 11 | 11 | 11 | 0 | 0 | **100.00%** |
| `cancel_count` | 101 | 100 | 100 | 0 | 1 | **100.00%** |
| `cancel_rate` | 121 | 120 | 120 | 0 | 1 | **100.00%** |
| `aov` | 124 | 124 | 124 | 0 | 0 | **100.00%** |
| `best_day` | 123 | 121 | 121 | 0 | 2 | **100.00%** |
| `topk_items` | 106 | 48 | 48 | 0 | 58 | **100.00%** |
| `best_item` | 11 | 10 | 10 | 0 | 1 | **100.00%** |
| `item_qty` | 103 | 96 | 96 | 0 | 7 | **100.00%** |
| `rev_change_pct` | 125 | 115 | 115 | 0 | 10 | **100.00%** |
| **TỔNG** | **1085** | **942** | **942** | **0** | **143** | **100.00%** |

## 2. Thống kê theo Shop (30 shop train)

| Shop | Có Sales Views | Tổng câu tag | Đã chọn | Đúng | Sai | Bỏ qua | % Đúng | Doanh thu tháng (`revenue`) |
|---|:---:|---:|---:|---:|---:|---:|---:|---:|
| `biz_101` | Yes | 22 | 18 | 18 | 0 | 4 | 100.0% | 9/9 |
| `biz_102` | Yes | 71 | 66 | 66 | 0 | 5 | 100.0% | 11/11 |
| `biz_103` | Yes | 31 | 19 | 19 | 0 | 12 | 100.0% | 5/5 |
| `biz_104` | Yes | 68 | 57 | 57 | 0 | 11 | 100.0% | 7/7 |
| `biz_105` | Yes | 33 | 27 | 27 | 0 | 6 | 100.0% | 5/5 |
| `biz_106` | Yes | 22 | 19 | 19 | 0 | 3 | 100.0% | 5/5 |
| `biz_107` | Yes | 23 | 19 | 19 | 0 | 4 | 100.0% | 7/7 |
| `biz_108` | Yes | 49 | 46 | 46 | 0 | 3 | 100.0% | 5/5 |
| `biz_109` | Yes | 16 | 13 | 13 | 0 | 3 | 100.0% | 4/4 |
| `biz_110` | Yes | 9 | 9 | 9 | 0 | 0 | 100.0% | 4/4 |
| `biz_111` | Yes | 52 | 47 | 47 | 0 | 5 | 100.0% | 5/5 |
| `biz_112` | Yes | 28 | 20 | 20 | 0 | 8 | 100.0% | 8/8 |
| `biz_113` | Yes | 18 | 15 | 15 | 0 | 3 | 100.0% | 4/4 |
| `biz_114` | Yes | 20 | 18 | 18 | 0 | 2 | 100.0% | 8/8 |
| `biz_115` | Yes | 68 | 62 | 62 | 0 | 6 | 100.0% | 9/9 |
| `biz_116` | Yes | 64 | 59 | 59 | 0 | 5 | 100.0% | 10/10 |
| `biz_117` | Yes | 30 | 26 | 26 | 0 | 4 | 100.0% | 3/3 |
| `biz_118` | Yes | 29 | 20 | 20 | 0 | 9 | 100.0% | 4/4 |
| `biz_119` | Yes | 50 | 43 | 43 | 0 | 7 | 100.0% | 6/6 |
| `biz_120` | Yes | 35 | 34 | 34 | 0 | 1 | 100.0% | 5/5 |
| `biz_121` | Yes | 33 | 24 | 24 | 0 | 9 | 100.0% | 6/6 |
| `biz_122` | Yes | 32 | 25 | 25 | 0 | 7 | 100.0% | 10/10 |
| `biz_123` | Yes | 21 | 20 | 20 | 0 | 1 | 100.0% | 6/6 |
| `biz_124` | Yes | 22 | 19 | 19 | 0 | 3 | 100.0% | 5/5 |
| `biz_125` | Yes | 20 | 20 | 20 | 0 | 0 | 100.0% | 6/6 |
| `biz_126` | Yes | 22 | 22 | 22 | 0 | 0 | 100.0% | 9/9 |
| `biz_127` | Yes | 60 | 54 | 54 | 0 | 6 | 100.0% | 10/10 |
| `biz_128` | Yes | 41 | 37 | 37 | 0 | 4 | 100.0% | 5/5 |
| `biz_129` | Yes | 56 | 53 | 53 | 0 | 3 | 100.0% | 8/8 |
| `biz_130` | Yes | 40 | 31 | 31 | 0 | 9 | 100.0% | 8/8 |

## 3. Lý do bỏ qua câu hỏi (Skipped Breakdown)

| Intent & Lý do bỏ qua | Số câu |
|---|---:|
| `topk_items:item_rev_or_qty_in_topk_tag` | 56 |
| `revenue:extra_filter_or_subintent` | 35 |
| `revenue:item_specific_revenue` | 24 |
| `item_qty:misclassified_or_extra_filter` | 7 |
| `rev_change_pct:misclassified_or_extra_filter` | 7 |
| `revenue:before_shop_min_date` | 4 |
| `rev_change_pct:unanswerable_ground_truth` | 3 |
| `topk_items:before_shop_min_date` | 2 |
| `best_day:before_shop_min_date` | 2 |
| `best_item:unparsed_or_range_period` | 1 |
| `cancel_count:unanswerable_ground_truth` | 1 |
| `cancel_rate:before_shop_min_date` | 1 |

## 4. Phân nhóm lỗi hệ thống & Ghi chú cho T1–T4

Kết quả chẩn đoán tự động gom toàn bộ các câu sai về **2 nguyên nhân gốc ở tầng dữ liệu** (cả 2 đều giải thích 100% các câu sai):

1. **Nối bảng danh mục `san_pham` khi bảng bán hàng chỉ ghi `item_code` (`biz_111`, `biz_123`, `biz_129` — 19 câu ở `topk_items`, `best_item`, `item_qty`):**
   - **Nguyên nhân:** Ở `biz_123` (`pos.sqlite`) và `biz_129` (`san_pham.csv`), bảng `san_pham` có cột mã vạch (`ma_vach_ean` / `Mã vạch EAN`) đứng trước cột mã hàng (`MaHangHoa` / `Mã HH`). Hàm tìm cột mã trong `src/ledger.py` (dòng 419) và `src/views.py` (dòng 343) khớp từ khoá `"ma"` trên cột đầu tiên nên lấy nhầm cột barcode (`893...`) thay vì `SP00xx`, khiến phép join `chi_tiet_don.item_code = san_pham.item_code` không khớp và `item_name` trên `v_lines` bị rỗng (`''`).
   - Riêng ở `biz_111` (`san_pham.csv`), cột tên hàng đặt tên là `Sản phẩm` (mô tả trong README: `- **Sản phẩm**: tên`), chưa có trong danh sách từ khoá `["ten", "name"]` ở `src/ledger.py` và `src/views.py`, nên `san_pham` bị bỏ qua khi dựng `v_items`.
   - **Bằng chứng chẩn đoán:** Biến thể `enhanced_catalog_join` (loại trừ cột `barcode`/`ma vach`/`ean` khi tìm `code_c` và thêm từ khoá `"san pham"` cho `name_c`) trả về đúng **19/19** câu của `biz_111`, `biz_123`, `biz_129`.
2. **Đọc hệ số quy đổi đơn vị trong bảng tên `DanhMuc.xlsx` (`biz_117` — 3 câu `topk_items`):**
   - **Nguyên nhân:** Ở `biz_117`, bảng quy đổi đơn vị nằm trong file `DanhMuc.xlsx` với 4 cột `['Hàng', 'ĐV lớn', 'ĐV nhỏ', 'Hệ số QĐ']` (ví dụ `Xi măng Hà Tiên PCB40 bao 50kg`: `1 tấn = 20 bao`, `Gạch ống 8x8x18 Tuynel`: `1 thiên = 1000 viên`). Trong `src/ledger.py:load_unit_conversions` (dòng 209), điều kiện nhận diện bảng quy đổi chỉ kiểm tra tên bảng chứa `["quy doi", "don vi"]` (bỏ sót `DanhMuc`), và tên cột mặt hàng/đơn vị chưa có `"hang"`, `"dv lon"`, `"dv nho"`.
   - **Bằng chứng chẩn đoán:** Biến thể `enhanced_unit_conv` đọc `DanhMuc.xlsx` cho ra đúng **3/3** câu `topk_items` của `biz_117`.

## 5. Danh sách chi tiết các câu sai & Chẩn đoán tự động

Không có câu sai nào.
