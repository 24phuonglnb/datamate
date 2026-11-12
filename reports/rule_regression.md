# Báo cáo Regression Tầng Dữ Liệu (Task T5 — Không dùng LLM)

**Tổng kết: 923/942 (97.98% đúng trên câu đã chọn)** | Doanh thu tháng (`revenue`): **197/197 (100.00%)** | Thời gian chạy 30 shop: `664.4s`

## 1. Thống kê theo Intent

| Intent | Tổng câu khớp tag + kỳ tường minh | Đã chọn (Selected) | Đúng (Correct) | Sai (Wrong) | Bỏ qua (Skipped) | % Đúng trên câu đã chọn |
|---|---:|---:|---:|---:|---:|---:|
| `revenue` | 260 | 197 | 197 | 0 | 63 | **100.00%** |
| `order_count` | 11 | 11 | 11 | 0 | 0 | **100.00%** |
| `cancel_count` | 101 | 100 | 100 | 0 | 1 | **100.00%** |
| `cancel_rate` | 121 | 120 | 120 | 0 | 1 | **100.00%** |
| `aov` | 124 | 124 | 124 | 0 | 0 | **100.00%** |
| `best_day` | 123 | 121 | 121 | 0 | 2 | **100.00%** |
| `topk_items` | 106 | 48 | 38 | 10 | 58 | **79.17%** |
| `best_item` | 11 | 10 | 9 | 1 | 1 | **90.00%** |
| `item_qty` | 103 | 96 | 88 | 8 | 7 | **91.67%** |
| `rev_change_pct` | 125 | 115 | 115 | 0 | 10 | **100.00%** |
| **TỔNG** | **1085** | **942** | **923** | **19** | **143** | **97.98%** |

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
| `biz_111` | Yes | 52 | 47 | 40 | 7 | 5 | 85.1% | 5/5 |
| `biz_112` | Yes | 28 | 20 | 20 | 0 | 8 | 100.0% | 8/8 |
| `biz_113` | Yes | 18 | 15 | 15 | 0 | 3 | 100.0% | 4/4 |
| `biz_114` | Yes | 20 | 18 | 18 | 0 | 2 | 100.0% | 8/8 |
| `biz_115` | Yes | 68 | 62 | 62 | 0 | 6 | 100.0% | 9/9 |
| `biz_116` | Yes | 64 | 59 | 59 | 0 | 5 | 100.0% | 10/10 |
| `biz_117` | Yes | 30 | 26 | 23 | 3 | 4 | 88.5% | 3/3 |
| `biz_118` | Yes | 29 | 20 | 20 | 0 | 9 | 100.0% | 4/4 |
| `biz_119` | Yes | 50 | 43 | 43 | 0 | 7 | 100.0% | 6/6 |
| `biz_120` | Yes | 35 | 34 | 34 | 0 | 1 | 100.0% | 5/5 |
| `biz_121` | Yes | 33 | 24 | 24 | 0 | 9 | 100.0% | 6/6 |
| `biz_122` | Yes | 32 | 25 | 25 | 0 | 7 | 100.0% | 10/10 |
| `biz_123` | Yes | 21 | 20 | 16 | 4 | 1 | 80.0% | 6/6 |
| `biz_124` | Yes | 22 | 19 | 19 | 0 | 3 | 100.0% | 5/5 |
| `biz_125` | Yes | 20 | 20 | 20 | 0 | 0 | 100.0% | 6/6 |
| `biz_126` | Yes | 22 | 22 | 22 | 0 | 0 | 100.0% | 9/9 |
| `biz_127` | Yes | 60 | 54 | 54 | 0 | 6 | 100.0% | 10/10 |
| `biz_128` | Yes | 41 | 37 | 37 | 0 | 4 | 100.0% | 5/5 |
| `biz_129` | Yes | 56 | 53 | 48 | 5 | 3 | 90.6% | 8/8 |
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

Kết quả chẩn đoán tự động gom toàn bộ **19/19 câu sai** về **2 nguyên nhân gốc ở tầng dữ liệu** (cả 2 đều có biến thể kiểm chứng tự động khớp 100% đáp án chuẩn):

1. **Nối bảng danh mục `san_pham` khi bảng bán hàng chỉ ghi `item_code` (`biz_111`, `biz_123`, `biz_129` — 16 câu ở `topk_items`, `best_item`, `item_qty`):**
   - **Nguyên nhân:**
     - Ở `biz_123` (`pos.sqlite`) và `biz_129` (`san_pham.csv`), bảng `san_pham` có cột mã vạch (`ma_vach_ean` / `Mã vạch EAN`) và cột `Mẫu ghi chú` đứng trước cột mã hàng (`MaHangHoa` / `Mã HH`). Hàm tìm cột mã trong `src/ledger.py` (dòng 419) và `src/views.py` (dòng 343) khớp từ khoá `"ma"` trên cột đầu tiên nên lấy nhầm cột barcode (`893...`) thay vì `SP00xx`, khiến phép join `chi_tiet_don.item_code = san_pham.item_code` không khớp và `item_name` trên `v_lines` bị rỗng (`''`).
     - Riêng ở `biz_111` (`san_pham.csv`), cột tên hàng đặt tên là `Sản phẩm` (đứng sau `Mô tả sản phẩm` và `Mã barcode`), chưa có trong danh sách từ khoá `["ten", "name"]` ở `src/ledger.py` và `src/views.py`, nên `san_pham` bị bỏ qua khi dựng `v_items` và join tên hàng.
   - **Bằng chứng chẩn đoán:** Biến thể `enhanced_catalog_join` (loại trừ cột `barcode`/`ma vach`/`ean`/`ghi chu`/`mo ta` khi tìm `code_c` và thêm từ khoá `"san pham"` cho `name_c`) trả về đúng **16/16** câu của `biz_111`, `biz_123`, `biz_129`.
2. **Đọc hệ số quy đổi đơn vị trong bảng tên `DanhMuc.xlsx` (`biz_117` — 3 câu `topk_items`):**
   - **Nguyên nhân:** Ở `biz_117`, bảng quy đổi đơn vị nằm trong file `DanhMuc.xlsx` (`norm_key(t.name) == "danhmuc"`) với 4 cột `['Hàng', 'ĐV lớn', 'ĐV nhỏ', 'Hệ số QĐ']` (ví dụ `Xi măng Hà Tiên PCB40 bao 50kg`: `1 tấn = 20 bao`, `Gạch ống 8x8x18 Tuynel`: `1 thiên = 1000 viên`). Trong `src/ledger.py:load_unit_conversions` (dòng 209), điều kiện nhận diện bảng quy đổi chỉ kiểm tra tên bảng chứa `["quy doi", "don vi"]` (bỏ sót `"danhmuc"`/`"quydoi"`), và tên cột mặt hàng/đơn vị chưa có `"hang"`, `"dv lon"`, `"dv nho"`.
   - **Bằng chứng chẩn đoán:** Biến thể `enhanced_unit_conv` đọc `DanhMuc.xlsx` cho ra đúng **3/3** câu `topk_items` của `biz_117`.

## 5. Danh sách chi tiết các câu sai & Chẩn đoán tự động

| # | Shop | Intent | Question ID | Câu hỏi | Giá trị tính | Đáp án chuẩn | Chẩn đoán tự động (Biến thể khớp) |
|---:|---|---|---|---|---|---|---|
| 1 | `biz_111` | `topk_items` | `q_261ae1fe4be0` | tháng 3/2025 top 5 hàng bán chạy nhất là j | `["", "", "", "", ""]` | `["Cà phê sữa (M)", "Trà đào cam sả (M)", "Trà sữa trân châu (M)", "Cà phê đen (M)", "Bạc xỉu (M)"]` | variant MATCH: `enhanced_catalog_join` (nối `san_pham` qua cột `SKU`/`Mã HH`/`MaHangHoa` và `Sản phẩm` thay vì cột barcode lấy đúng `item_name`) |
| 2 | `biz_111` | `topk_items` | `q_3c6ec225a628` | cho toi 3 mat hang ban chay nhat trong thang 5/2026 | `["", "", ""]` | `["Cà phê sữa (M)", "Trà đào cam sả (M)", "Cà phê đen (M)"]` | variant MATCH: `enhanced_catalog_join` (nối `san_pham` qua cột `SKU`/`Mã HH`/`MaHangHoa` và `Sản phẩm` thay vì cột barcode lấy đúng `item_name`) |
| 3 | `biz_111` | `item_qty` | `q_4a3cf2a9214e` | trong tháng 7 năm 2025 cửa hàng bán được mấy ly Nước ép dưa hấu (L) | `null` | `61` | variant MATCH: `enhanced_catalog_join` (nối đúng mã `SP0040` -> `Nước ép dưa hấu (L)` từ `san_pham` ra đúng `61`) |
| 4 | `biz_111` | `item_qty` | `q_521fed0ffe38` | Cho mình hỏi số ly Sinh tố xoài (M) bán được trong tháng 1/2026 là bao nhiêu? | `null` | `131` | variant MATCH: `enhanced_catalog_join` (nối đúng mã `SP0035` -> `Sinh tố xoài (M)` từ `san_pham` ra đúng `131`) |
| 5 | `biz_111` | `topk_items` | `q_9707962ad285` | 3 mat hang ban chay nhat thang 4/2025 la nhung mat hang nao | `["", "", ""]` | `["Cà phê sữa (M)", "Cà phê đen (M)", "Trà sữa trân châu (M)"]` | variant MATCH: `enhanced_catalog_join` (nối `san_pham` qua cột `SKU`/`Mã HH`/`MaHangHoa` và `Sản phẩm` thay vì cột barcode lấy đúng `item_name`) |
| 6 | `biz_111` | `item_qty` | `q_a4c169ab2814` | Xem giúp số ly Sữa tươi trân châu đường đen (L) bán được trong tháng 7/2025 là bao nhiêu? | `null` | `63` | variant MATCH: `enhanced_catalog_join` (nối đúng mã `SP0032` -> `Sữa tươi trân châu đường đen (L)` từ `san_pham` ra đúng `63`) |
| 7 | `biz_111` | `item_qty` | `q_ae0df4a36ad5` | Cho mình hỏi số ly Sinh tố xoài (M) bán được trong tháng 8/2025 là bao nhiêu? | `null` | `110` | variant MATCH: `enhanced_catalog_join` (nối đúng mã `SP0035` -> `Sinh tố xoài (M)` từ `san_pham` ra đúng `110`) |
| 8 | `biz_117` | `topk_items` | `q_788ab61d79d1` | Liệt kê 5 mặt hàng bán chạy nhất tháng 9/2025. | `["Thép cuộn phi 6 Hòa Phát", "Thép Pomina D10 cây 11.7m", "Xi măng Hà Tiên PCB40 bao 50kg", "Bột trét Jotun nội thất 40kg", "Nước khoáng Lavie 19L"]` | `["Xi măng Hà Tiên PCB40 bao 50kg", "Xi măng INSEE Power-S bao 50kg", "Thép cuộn phi 6 Hòa Phát", "Băng keo điện Nano 20 yard", "Thép Pomina D10 cây 11.7m"]` | variant MATCH: `enhanced_unit_conv` (đọc hệ số quy đổi từ bảng `DanhMuc`/`QuyDoi` có cột `Hàng`/`ĐV lớn` ra đúng thứ tự top-k) |
| 9 | `biz_117` | `topk_items` | `q_b71b56dffceb` | top 3 sp bán nhiều nhất tháng 4 năm 2026 là những j | `["Gạch ống 8x8x18 Tuynel", "Xi măng INSEE Power-S bao 50kg", "Keo dán gạch Weber.tai fix xám 25kg"]` | `["Xi măng Hà Tiên PCB40 bao 50kg", "Băng keo điện Nano 20 yard", "Xi măng INSEE Power-S bao 50kg"]` | variant MATCH: `enhanced_unit_conv` (đọc hệ số quy đổi từ bảng `DanhMuc`/`QuyDoi` có cột `Hàng`/`ĐV lớn` ra đúng thứ tự top-k) |
| 10 | `biz_117` | `topk_items` | `q_d42bb63de182` | liệt kê 3 mặt hàng hot nhất tháng 11/2025 | `["Thép cuộn phi 6 Hòa Phát", "Xi măng INSEE Power-S bao 50kg", "Xi măng Hà Tiên PCB40 bao 50kg"]` | `["Xi măng Hà Tiên PCB40 bao 50kg", "Xi măng INSEE Power-S bao 50kg", "Lưới B40 mạ kẽm khổ 1.5m"]` | variant MATCH: `enhanced_unit_conv` (đọc hệ số quy đổi từ bảng `DanhMuc`/`QuyDoi` có cột `Hàng`/`ĐV lớn` ra đúng thứ tự top-k) |
| 11 | `biz_123` | `item_qty` | `q_0bfcbccec99e` | Tháng 1/2025 cửa hàng bán được tổng cộng bao nhiêu viên Gofen 400 hộp 5 vỉ x 10 viên nang? | `0` | `588` | variant MATCH: `enhanced_catalog_join` (nối đúng mã `SP0030` -> `Gofen 400 hộp 5 vỉ x 10 viên nang` từ `san_pham` ra đúng `588`) |
| 12 | `biz_123` | `best_item` | `q_11d14818cbfc` | mat hang hot nhat thang 7 nam 2025 la mat hang nao | `""` | `"Panadol Extra hộp 15 vỉ x 12 viên"` | variant MATCH: `enhanced_catalog_join` (nối `san_pham` qua cột `SKU`/`Mã HH`/`MaHangHoa` và `Sản phẩm` thay vì cột barcode lấy đúng `item_name`) |
| 13 | `biz_123` | `topk_items` | `q_4ff224b3425b` | cho toi 5 mat hang ban chay nhat trong thang 5/2025 | `["", "", "", "", ""]` | `["Panadol Extra hộp 15 vỉ x 12 viên", "Hapacol 250 hộp 24 gói", "Cefuroxim 500mg Vidipha hộp 10 vỉ x 10 viên", "Amoxicillin 500mg Domesco hộp 10 vỉ x 10 viên", "Salonpas cao dán hộp 24 gói x 10 miếng"]` | variant MATCH: `enhanced_catalog_join` (nối `san_pham` qua cột `SKU`/`Mã HH`/`MaHangHoa` và `Sản phẩm` thay vì cột barcode lấy đúng `item_name`) |
| 14 | `biz_123` | `topk_items` | `q_fa48e43bff04` | 5 mặt hàng bán chạy nhất tháng 6/2025 là những mặt hàng nào | `["", "", "", "", ""]` | `["Panadol Extra hộp 15 vỉ x 12 viên", "Enervon hộp 10 vỉ x 10 viên", "Panadol 500mg hộp 10 vỉ x 12 viên", "Tiffy Dey hộp 25 vỉ x 4 viên", "Amoxicillin 500mg Domesco hộp 10 vỉ x 10 viên"]` | variant MATCH: `enhanced_catalog_join` (nối `san_pham` qua cột `SKU`/`Mã HH`/`MaHangHoa` và `Sản phẩm` thay vì cột barcode lấy đúng `item_name`) |
| 15 | `biz_129` | `item_qty` | `q_4103fb4b4b98` | Cho hỏi tháng 1/2025 bán ra bao nhiêu đĩa Ba chỉ chiên cháy cạnh? | `0` | `137` | variant MATCH: `enhanced_catalog_join` (nối đúng mã `SP0048` -> `Ba chỉ chiên cháy cạnh` từ `san_pham` ra đúng `137`) |
| 16 | `biz_129` | `topk_items` | `q_41a920e55256` | Xem giúp tháng 1/2026 top 3 hàng bán chạy nhất là gì? | `["", "", ""]` | `["Bia Tiger lon", "Lẩu Thái tôm cá (nhỏ)", "Bia Tiger Bạc lon"]` | variant MATCH: `enhanced_catalog_join` (nối `san_pham` qua cột `SKU`/`Mã HH`/`MaHangHoa` và `Sản phẩm` thay vì cột barcode lấy đúng `item_name`) |
| 17 | `biz_129` | `topk_items` | `q_84800ceb36a8` | Giúp mình liệt kê 5 mặt hàng bán chạy nhất tháng 7/2025. | `["", "", "", "", ""]` | `["Bia Tiger lon", "Bia Sài Gòn Special lon", "Bia Tiger Bạc lon", "Coca-Cola lon", "Nước suối"]` | variant MATCH: `enhanced_catalog_join` (nối `san_pham` qua cột `SKU`/`Mã HH`/`MaHangHoa` và `Sản phẩm` thay vì cột barcode lấy đúng `item_name`) |
| 18 | `biz_129` | `item_qty` | `q_ce98842bb9b6` | coi giùm tháng 1/2025 bán ra bn đĩa Đậu que xào tỏi | `0` | `129` | variant MATCH: `enhanced_catalog_join` (nối đúng mã `SP0044` -> `Đậu que xào tỏi` từ `san_pham` ra đúng `129`) |
| 19 | `biz_129` | `item_qty` | `q_f0123548f973` | coi gium trong thang 5 nam 2025 cua hang ban duoc may dia goi ngo sen tom thit do | `0` | `299` | variant MATCH: `enhanced_catalog_join` (nối đúng mã `SP0019` -> `Gỏi ngó sen tôm thịt` từ `san_pham` ra đúng `299`) |
