# SQLite Database & Rulebook Views Contract (`src/views.py`)

Tài liệu này là **hợp đồng giao diện (interface contract)** giữa tầng dữ liệu (P3 – `src/views.py`) và tầng sinh truy vấn / trả lời câu hỏi (P1/P2 – `src/agent.py`, prompt text-to-SQL).

---

## 1. Public API

```python
from src.views import build_database, schema_text, can_build_ledger, enable_readonly

# 1. Dựng SQLite in-memory (hoặc file tạm) cho 1 hộ kinh doanh
conn = build_database(
    business_dir="data/train/biz_101",
    calendar_path=None,     # Tự động tìm calendar.csv ở thư mục cha nếu để None
    readonly=False,         # Đặt True để bật PRAGMA query_only = ON sau khi tạo xong bảng & view
    db_path=":memory:",
)

# 2. Sinh mô tả schema gọn cho LLM prompt (views trước, bảng phụ sau, <= max_chars)
prompt_schema = schema_text(conn, max_chars=13000)

# 3. Bật chế độ chỉ đọc bất kỳ lúc nào trước khi chạy SQL do model sinh
enable_readonly(conn)
```

---

## 2. Cấu trúc các bảng & View trong SQLite

Mỗi database của một tiệm gồm **4 lớp dữ liệu**:

1. **Rulebook Sales Views (`v_valid_orders`, `v_valid_lines`, `v_orders`, `v_lines`, `v_items`)** — chỉ tạo khi `can_build_ledger(tables, mapping, readme) == True`. Toàn bộ tên cột là tiếng Anh `snake_case`, đã áp dụng sẵn quy tắc làm sạch và chuẩn hoá theo `rulebook.md`.
2. **Cleaned Tables (`<safe_table_name>`)** — mọi bảng của tiệm đã cắt dòng tổng cộng ghi tay (`split_summary_rows`), đổi tên cột sang ASCII `snake_case`, ép kiểu số (`REAL`) và ngày chuẩn ISO (`YYYY-MM-DD` / `YYYY-MM-DD HH:MM:SS`).
3. **Raw Fallback Tables (`raw_<safe_table_name>`)** — giữ nguyên tên cột gốc và dữ liệu gốc (chỉ bỏ `META_COLS`), dùng cho các truy vấn đặc thù ngoài phạm vi view chuẩn.
4. **Calendar Table (`calendar`)** — nạp từ `calendar.csv` lúc dựng DB, thêm các cột dương lịch suy ra từ `date` (xem mục 3.7).
5. **Order events (`payments`, `deliveries`, `order_due` → view `v_payments`, `v_deliveries`, cột mới trong `v_orders`)** — ngày thu tiền, ngày giao, hạn thanh toán lấy từ bảng phụ của tiệm khi có (xem mục 3.6).

---

## 3. Chi tiết các View theo Rulebook

### 3.1. `v_lines` — Toàn bộ dòng bán hàng ở mọi trạng thái đơn

Dựa trên bảng `lines` (kết quả của `SalesLedger` đã chuẩn hoá tên hàng, mã hàng, đơn vị cơ bản và khách hàng).

| Cột | Kiểu | Ý nghĩa & Quy tắc Rulebook áp dụng |
|---|---|---|
| `line_id` | `INTEGER` | Số thứ tự dòng (1-based, duy nhất). |
| `order_id` | `TEXT` | Mã đơn hàng. Nếu sổ bán hàng không có cột mã đơn (`biz_107`, `biz_113`, `biz_126`), mỗi dòng được gán mã đơn tổng hợp `'ROW_' \|\| line_id` theo **§8** (*"Bảng không ghi theo đơn: mỗi dòng là một lần ghi"*). |
| `order_date` | `TEXT` | Ngày đặt đơn chuẩn ISO `'YYYY-MM-DD'` (**§1**: tính theo ngày đặt; các dòng thuộc cùng một `order_id` dùng chung ngày đặt sớm nhất của đơn; **§8**: ngày khuyết năm đã ghép năm từ tên sheet/file). |
| `order_time` | `TEXT` | Giờ đặt đơn `'HH:MM:SS'` (hoặc `NULL` nếu sổ không ghi giờ). |
| `order_month` | `TEXT` | Tháng đặt đơn `'YYYY-MM'` (`SUBSTR(order_date, 1, 7)`). |
| `status` | `TEXT` | Trạng thái cấp đơn đã chuẩn hoá về 4 giá trị: `'hoan_thanh'`, `'dang_giao'`, `'huy'`, `'tra_hang'`. Theo **§1 & §8**, nếu đơn có bất kỳ dòng hoàn/trả nào (kể cả trả một phần), toàn bộ đơn mang `status = 'tra_hang'`. |
| `item_code` | `TEXT` | Mã mặt hàng chuẩn hoá (đã đồng bộ giữa bảng danh mục và bảng bán hàng). `NULL` đối với dòng `Phí phục vụ`. |
| `item_name` | `TEXT` | Tên mặt hàng chuẩn hoá (đã giải mã tên viết tắt từ sheet `Ghi tắt` / cột `Tên gọi khác` và gộp các biến thể khoảng trắng/dấu theo **§9**). |
| `category` | `TEXT` | Nhóm hàng / danh mục mặt hàng (lấy từ bảng danh mục hoặc cột nhóm hàng trên sổ bán). |
| `is_service_fee` | `INTEGER` | `1` nếu là dòng `"Phí phục vụ"`, `0` nếu là mặt hàng thật. Theo **§3**, dòng `"Phí phục vụ"` **được cộng vào doanh thu đơn**, nhưng **không phải là mặt hàng** khi đếm hoặc xếp hạng mặt hàng (luôn lọc `is_service_fee = 0` khi truy vấn theo mặt hàng). Các dòng điều chỉnh cấp hoá đơn như `"Voucher"`, `"Phí ship"`, `"Dùng <n> điểm"` có số lượng trống đã được loại khỏi `lines` theo **§1**. |
| `unit` | `TEXT` | Đơn vị tính lúc bán trên dòng đơn (ví dụ `'thùng'`, `'lốc'`, `'hộp'`, `'cái'`). |
| `qty` | `REAL` | Số lượng bán theo đơn vị trên dòng (`unit`). |
| `factor` | `REAL` | Hệ số quy đổi về đơn vị nhỏ nhất (`qty_base = qty * factor`, **§10**). |
| `qty_base` | `REAL` | Số lượng đã quy đổi về đơn vị nhỏ nhất (`base_unit`). Dùng cột này cho mọi câu hỏi tổng số lượng bán / xếp hạng bán chạy theo số lượng (**§3, §10**). |
| `base_unit` | `TEXT` | Tên đơn vị nhỏ nhất của mặt hàng (**§10**), giữ đúng chính tả có dấu như trong file (`viên`, `hộp`, `gói`; không phải `vien`, `hop`, `goi`). Khi lọc theo đơn vị, so sánh với dạng có dấu. |
| `unit_price` | `REAL` | Đơn giá bán theo đơn vị trên dòng (`unit`). |
| `unit_price_base` | `REAL` | Đơn giá quy đổi về đơn vị nhỏ nhất (`unit_price / factor`, **§5**). |
| `line_amount` | `REAL` | Thành tiền của dòng sau chiết khấu dòng (**§1**). |
| `customer_code` | `TEXT` | Mã khách hàng (`NULL` nếu là khách lẻ). |
| `customer_name` | `TEXT` | Tên khách hàng chuẩn hoá có dấu (`NULL` nếu là khách lẻ). |
| `customer_key` | `TEXT` | Khoá định danh khách hàng để `GROUP BY` / `COUNT(DISTINCT customer_key)` (**§3**): bằng `customer_code` nếu tiệm có dùng mã khách (đơn không ghi mã khách là khách lẻ -> `NULL`), ngược lại bằng tên khách đã chuẩn hoá: bỏ dấu, viết thường, bỏ dấu câu, và nối các cụm chữ số liền nhau, nên `Triệu Linh An - 0327 988 481` và `Triệu Linh An 0327988481` là cùng một khách (tên chỉ khác cách viết là một khách; khác chữ hoặc khác số là hai khách). Mọi nhãn khách vãng lai (`Khách lẻ`, `Lẻ`, `KL`, `Khách vãng lai`, `Vãng lai`, trống) đều có `customer_key = NULL`. |
| `customer_group` | `TEXT` | Nhóm / hạng khách hàng (nếu có trong bảng khách hàng hoặc sổ bán). |
| `staff` | `TEXT` | Nhân viên bán hàng / thu ngân. |
| `channel` | `TEXT` | Kênh bán hàng. |
| `payment_method` | `TEXT` | Hình thức thanh toán. |
| `src_file`, `src_sheet`, `src_row` | `TEXT`, `TEXT`, `INTEGER` | Nguồn gốc dòng dữ liệu để truy vết. |

> **Khi nào dùng `v_lines`?**
> - Tra **đơn giá bán ngày D** (**§5**: *"tính trên mọi đơn ghi ngày D (kể cả đơn huỷ và đơn hoàn trả)"*).

---

### 3.2. `v_valid_lines` — Dòng bán hàng hợp lệ (không huỷ, không hoàn trả)

```sql
CREATE VIEW v_valid_lines AS
SELECT *
FROM v_lines
WHERE status NOT IN ('huy', 'tra_hang');
```

- Bao gồm cả đơn `'hoan_thanh'` và `'dang_giao'` (**§1**: *"tính các đơn không huỷ và không hoàn trả (kể cả đơn đang giao)"*).
- Dùng cho: **doanh thu theo mặt hàng / nhóm hàng**, **top mặt hàng bán chạy theo số lượng (`SUM(qty_base)`) hoặc doanh thu (`SUM(line_amount)`)** (nhớ kèm `WHERE is_service_fee = 0`), **số lượng bán của mặt hàng**.

---

### 3.3. `v_orders` — Mỗi đơn một dòng (mọi trạng thái)

```sql
CREATE VIEW v_orders AS
SELECT
    order_id,
    MIN(order_date) AS order_date,
    MIN(order_time) AS order_time,
    SUBSTR(MIN(order_date), 1, 7) AS order_month,
    MAX(status) AS status,
    SUM(line_amount) AS revenue,
    COUNT(*) AS n_lines,
    SUM(CASE WHEN is_service_fee = 0 THEN qty_base ELSE 0 END) AS total_qty_base,
    MAX(customer_code) AS customer_code,
    MAX(customer_name) AS customer_name,
    MAX(customer_key) AS customer_key,
    MAX(customer_group) AS customer_group,
    MAX(staff) AS staff,
    MAX(channel) AS channel,
    MAX(payment_method) AS payment_method
FROM v_lines
GROUP BY order_id
-- rồi LEFT JOIN order_events (mục 3.6), thêm 8 cột:
-- first_paid_at, last_paid_at, paid_amount, n_payments,
-- first_delivery_date, last_delivery_date, n_delivery_rounds, due_date
```

`order_time` lấy từ cột giờ của sổ bán hoặc bảng hoá đơn. Khi không cột nào có tên kiểu giờ, `propose_mapping` chọn theo nội dung (`find_time_column`): cột datetime có giờ khác 00:00:00 trên đa số dòng và rơi **cùng ngày** với `order_date` trên ≥ 95% dòng (vd. `Thời gian tạo` cạnh `Thời gian` chỉ có ngày). Giờ thu tiền, giờ giao ở ngày khác nên không bị chọn nhầm.

> **Khi nào dùng `v_orders`?**
> - Đếm **tổng số đơn phát sinh**, **số đơn huỷ** (`status = 'huy'`), **số đơn hoàn trả** (`status = 'tra_hang'`), **số đơn đang giao** (`status = 'dang_giao'`).
> - Tính **tỉ lệ huỷ đơn** (`SUM(CASE WHEN status = 'huy' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)`).

---

### 3.4. `v_valid_orders` — Đơn hàng hợp lệ (không huỷ, không hoàn trả)

```sql
CREATE VIEW v_valid_orders AS
SELECT *
FROM v_orders
WHERE status NOT IN ('huy', 'tra_hang');
```

> **Khi nào dùng `v_valid_orders`?**
> - Tính **doanh thu** ngày / tuần / tháng / quý / năm (`SUM(revenue)`).
> - Tính **số đơn hợp lệ** (`COUNT(*)`), **giá trị trung bình mỗi đơn (AOV)** (`SUM(revenue) / COUNT(*)`).
> - Tính **doanh thu theo kênh bán (`channel`), hình thức thanh toán (`payment_method`), nhân viên (`staff`), khách hàng (`customer_key`)**.

---

### 3.5. `v_items` — Danh mục mặt hàng & từ điển tên gọi (`name_aliases`)

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `item_code` | `TEXT` | Mã hàng chuẩn hoá (`NULL` nếu tiệm không đánh mã). |
| `item_name` | `TEXT` | Tên hàng chuẩn đầy đủ dấu tiếng Việt (dùng để xuất câu trả lời theo **§9**). |
| `name_aliases` | `TEXT` | Danh sách mọi cách viết xuất hiện trong các file của tiệm (tên chuẩn, tên viết tắt trong sheet `Ghi tắt`, cột `Tên gọi khác`, biến thể không dấu/dư khoảng trắng), ngăn cách bởi `' \| '`. |
| `category` | `TEXT` | Nhóm hàng / loại hàng. |
| `base_unit` | `TEXT` | Đơn vị tính nhỏ nhất (**§10**), chính tả có dấu như trong file. |
| `sell_price` | `REAL` | Giá bán niêm yết trong bảng danh mục (nếu có). |
| `cost_price` | `REAL` | Giá vốn / giá nhập chuẩn trong bảng danh mục (nếu có, dùng cho **§2**). |
| `active_ingredient` | `TEXT` | Hoạt chất (đối với nhà thuốc). Giữ nguyên chuỗi gốc trong file (chỉ chuẩn hoá NFC và gộp khoảng trắng), **không** tách thuốc phối hợp nhiều hoạt chất dạng `'A + B'` theo **§6**. `NULL` với sản phẩm không ghi hoạt chất hoặc tiệm không phải nhà thuốc. |
| `is_prescription` | `TEXT` | Trạng thái thuốc kê đơn chuẩn hoá về `'1'` (kê đơn) hoặc `'0'` (không kê đơn) đối với nhà thuốc — mọi sản phẩm thuộc nhà thuốc không ghi kê đơn trong bảng thuốc đều mang `'0'` theo **§6**. `ETC` được hiểu là kê đơn, `OTC` là không kê đơn. `NULL` nếu tiệm không có bảng thuốc / không phải nhà thuốc, hoặc ô kê đơn có giá trị lạ không đọc được (không tự gán `'0'`). |

Ví dụ truy vấn nhà thuốc trên `v_items` + `v_valid_lines` (chạy trên `biz_119`):

```sql
-- Doanh thu theo hoạt chất (giữ nguyên chuỗi hoạt chất gốc, không gộp thuốc phối hợp 'Paracetamol + Cafein' vào 'Paracetamol' theo §6)
SELECT CAST(ROUND(COALESCE(SUM(l.line_amount), 0)) AS INTEGER) AS ingredient_revenue
FROM v_valid_lines l
JOIN v_items i ON COALESCE(l.item_code, l.item_name) = COALESCE(i.item_code, i.item_name)
WHERE l.is_service_fee = 0
  AND i.active_ingredient = 'Paracetamol'
  AND l.order_month = '2026-06';

-- Tỉ lệ doanh thu thuốc kê đơn (%) theo §6
SELECT ROUND(
    SUM(CASE WHEN i.is_prescription = '1' THEN l.line_amount ELSE 0 END) * 100.0
    / NULLIF(SUM(l.line_amount), 0),
    2
) AS rx_revenue_pct
FROM v_valid_lines l
LEFT JOIN v_items i
    ON l.is_service_fee = 0
   AND COALESCE(l.item_code, l.item_name) = COALESCE(i.item_code, i.item_name)
WHERE l.order_month = '2026-06';
```

---

### 3.6. Ngày thu tiền, ngày giao, hạn thanh toán (`v_payments`, `v_deliveries`, cột mới của `v_orders`)

Chỉ có dữ liệu khi tiệm có bảng phụ. Bảng nguồn được nhận theo **nội dung**, không theo tên shop:

1. Bảng có một cột mà ≥ 80% giá trị khác nhau là `order_id` của sổ bán (bỏ qua cột toàn số nguyên ≤ 4 chữ số như STT, lần giao).
2. Cột ngày của bảng đó được xếp loại theo tên cột: `Hạn …` → hạn thanh toán; `Thời gian thu`, `Ngày TT`, `Ngày thanh toán`… → thu tiền; `Ngày giao (hàng)`, `Ngày chở`… → giao (không nhận `giao dịch`). Nếu bảng chỉ có một cột ngày chung chung (`Thời gian`) thì dựa vào tên bảng (`Sổ quỹ`, `Phiếu thu`, `Thanh toán` / `Giao hàng`, `Sổ giao`).
3. Giữ mọi dòng nguồn, mọi trạng thái đơn; **không** áp luật rulebook nào (doanh thu và kỳ vẫn theo ngày đặt).

| Đối tượng | Cột |
|---|---|
| `v_payments` (mỗi phiếu thu một dòng) | `order_id`, `paid_at` (`YYYY-MM-DD HH:MM:SS` hoặc `YYYY-MM-DD`), `paid_date`, `paid_time`, `paid_month`, `amount`, `method`, `src_table` |
| `v_deliveries` (mỗi **đợt giao** của mỗi đơn một dòng, gộp các dòng hàng cùng đợt) | `order_id`, `delivery_round` (số đợt; nếu sổ không ghi đợt thì là ngày giao), `delivery_date`, `delivery_month`, `n_rows`, `src_table` |
| `v_orders` / `v_valid_orders` (thêm) | `first_paid_at`, `last_paid_at`, `paid_amount`, `n_payments`, `first_delivery_date`, `last_delivery_date`, `n_delivery_rounds`, `due_date` — `NULL` khi đơn không có bản ghi |

Phủ trên 44 shop (12/11/2026): thu tiền ở biz_106, 109, 111, 123, 124, 127, 129, dev_003, 006, 010; giao + hạn nợ ở biz_115–118 và dev_004. Kiểm chứng: "số đợt giao trong tháng X" = `SELECT COUNT(*) FROM v_deliveries WHERE delivery_month = 'YYYY-MM'` khớp 5/5 câu train (biz_117, biz_118). Sổ nợ / trả góp ghi theo khách (dev_014) không có mã đơn nên không vào đây; truy vấn bảng đã làm sạch.

`schema_text` chỉ mô tả các cột/view này khi shop có dữ liệu, để không tốn chỗ trong prompt.

---

### 3.7. `calendar`

Dựng từ `calendar.csv` lúc chạy (file nào được đưa vào thì dùng file đó). Cột gốc giữ nguyên: `date`, `weekday` (1=T2..7=CN), `lunar_day`, `lunar_month`, `lunar_year`, `lunar_leap` (0/1), `holiday`. Cột thêm, tính từ `date`: `year`, `month`, `day`, `quarter`, `iso_year`, `iso_week`, `day_of_week` (1=T2..7=CN), `day_name_vi` (`Thứ Hai`..`Chủ nhật`), `is_weekend`, `holiday_vi` (= `holiday`).

Không dựng sẵn khoảng Tết hay mùa nào, vì định nghĩa nằm trong rulebook và có thể đổi. Lọc bằng JOIN, ví dụ đơn hợp lệ từ 23 tháng Chạp năm âm 2025 đến hết mùng 10 tháng Giêng năm âm 2026:

```sql
SELECT SUM(o.revenue)
FROM v_valid_orders o
JOIN calendar c ON c.date = o.order_date
WHERE (c.lunar_year = 2025 AND c.lunar_month = 12 AND c.lunar_day >= 23 AND c.lunar_leap = 0)
   OR (c.lunar_year = 2026 AND c.lunar_month = 1 AND c.lunar_day <= 10 AND c.lunar_leap = 0);
```

Cách an toàn hơn khi kỳ phức tạp: tính `[start, end]` dương lịch bằng Python từ `calendar` rồi lọc `order_date BETWEEN start AND end`.

---

### 3.8. Nhập hàng (`v_purchase_lines`, `v_valid_purchase_lines`, `v_purchases`)

Chỉ được tạo khi shop thực sự có dữ liệu nhập hàng rõ ràng (bảng phẳng như `SoNhapHang`/`SoTay_NhapHang`/`ChiTietNhapHang` hoặc cặp đầu phiếu + chi tiết như `DanhSachNhapHang` + `DanhSachChiTietNhapHang`, `phieu_nhap` + `chi_tiet_nhap`, `DonNhapHang` + `DonNhapHang_ChiTiet`). Shop **không có** sổ nhập hàng hoặc cấu trúc nhập không rõ ràng sẽ **không tạo** các view `v_purchase*` (không tạo view rỗng).

- **`v_purchase_lines`** (một dòng mỗi dòng hàng nhập, giữ mọi trạng thái kể cả phiếu huỷ):
  - `line_id` (INT)
  - `receipt_id` (TEXT): mã/số phiếu nhập (sinh mã `PN_ROW_<n>` nếu bảng phẳng thiếu cột mã phiếu)
  - `receipt_date` (TEXT `YYYY-MM-DD`), `receipt_month` (TEXT `YYYY-MM`)
  - `supplier` (TEXT | NULL): tên nhà cung cấp (nếu có bảng NCC sẽ ánh xạ sang tên gọi; nếu chỉ có mã NCC thì giữ mã)
  - `supplier_code` (TEXT | NULL): mã NCC nếu có
  - `status` (TEXT: `'hoan_thanh'` | `'huy'`), `is_cancelled` (INT `0`/`1`), `is_opening_stock` (INT `0`/`1`, bằng `1` khi ghi chú/phiếu có `"nhập đầu kỳ"` / `"đầu kỳ"`)
  - `item_code` (TEXT | NULL), `item_name` (TEXT canonical khớp `v_items` và `v_lines` qua alias/`Ghi tắt`)
  - `qty` (REAL), `unit` (TEXT | NULL, đơn vị nhập; `NULL` ở shop chỉ ghi số lượng gốc không ghi cột ĐVT)
  - `factor` (REAL), `qty_base` (REAL, quy đổi về `base_unit` qua bảng quy đổi nếu có)
  - `base_unit` (TEXT | NULL)
  - `unit_cost` (REAL | NULL, đơn giá theo `unit`), `unit_cost_base` (REAL | NULL, đơn giá theo `base_unit`), `line_amount` (REAL | NULL)
  - `src_table`, `src_file`, `src_sheet`, `src_row`: truy vết nguồn
- **`v_valid_purchase_lines`**: `SELECT * FROM v_purchase_lines WHERE is_cancelled = 0`.
- **`v_purchases`** (một dòng mỗi phiếu nhập): `receipt_id`, `receipt_date`, `receipt_month`, `supplier`, `supplier_code`, `status`, `is_cancelled`, `is_opening_stock`, `n_lines`, `total_amount` (`SUM(line_amount)`).

**Luật áp dụng (§2, §5, §9, §10):**
1. **Tiền nhập trong kỳ & nhập đầu kỳ**: tổng `line_amount` trên `v_valid_purchase_lines` (hoặc `total_amount` trên `v_purchases WHERE is_cancelled = 0`) lọc theo `receipt_date` / `receipt_month`. Phiếu `"nhập đầu kỳ"` (`is_opening_stock = 1`) **vẫn được tính** như mọi phiếu nhập hợp lệ khác.
2. **Nguồn tổng tiền phiếu**: `v_purchases.total_amount` tính từ `SUM(line_amount)` của các dòng chi tiết (`line_amount = qty * unit_cost` khi thiếu cột thành tiền), nhất quán 100% với cột tổng đầu phiếu ở toàn bộ shop dev/public test và đồng nhất với `v_orders.revenue`.
3. **Shop thiếu giá/tiền nhập** (ví dụ chỉ ghi số lượng nhập theo mã SKU, không có cột giá nhập và thành tiền): `unit_cost`, `unit_cost_base`, `line_amount`, `v_purchases.total_amount` giữ giá trị `NULL` (không điền `0`), để câu hỏi về tiền nhập / giá nhập trả về `unanswerable` còn câu hỏi số lượng nhập / nhập trừ bán vẫn dùng `qty` / `qty_base`.
4. **Giá nhập bình quân**: tính bình quân **theo số lượng nhập** (`SUM(line_amount) / SUM(qty)`) theo từng đơn vị nhập (`unit`), không lấy `AVG(unit_cost)`.
5. **Nhập trừ bán**: phần nhập lấy từ `v_valid_purchase_lines`, phần bán lấy từ `v_valid_lines` (§1), cả hai đã quy chuẩn `item_name` qua `v_items` và `qty_base` về cùng `base_unit`.

**3 câu SQL mẫu cho view nhập hàng:**

```sql
-- 1) Tổng tiền nhập hàng trong một tháng (tính cả nhập đầu kỳ, bỏ phiếu huỷ)
SELECT COALESCE(SUM(line_amount), 0) AS total_purchase_amount
FROM v_valid_purchase_lines
WHERE receipt_month = '2025-05';

-- 2) Giá nhập bình quân theo số lượng nhập của một mặt hàng trong tháng (theo đơn vị nhập)
SELECT
    item_name,
    unit,
    SUM(line_amount) * 1.0 / NULLIF(SUM(qty), 0) AS weighted_avg_unit_cost
FROM v_valid_purchase_lines
WHERE receipt_month = '2025-05'
  AND LOWER(item_name) = LOWER('Cà phê đen (M)')
GROUP BY item_name, unit;

-- 3) Nhà cung cấp nhập nhiều tiền nhất trong kỳ (hoặc toàn kỳ nếu bỏ WHERE)
SELECT
    supplier,
    SUM(line_amount) AS total_spend
FROM v_valid_purchase_lines
WHERE receipt_month = '2025-05'
  AND supplier IS NOT NULL
GROUP BY supplier
ORDER BY total_spend DESC, supplier ASC
LIMIT 1;
```

---

### 3.9. Tồn kho, lô, đơn vị (`v_stock`, `v_lots`, `v_item_units`)

Code: `src/stock.py`. Chỉ tạo `v_stock` / `v_lots` khi shop có dữ liệu tồn; shop không có thì **không có view** → câu hỏi tồn kho trả `unanswerable` (khớp đáp án train, ví dụ biz_103, biz_118, biz_130).

**Nguồn dữ liệu** (nhận theo từ khoá + nội dung, không theo tên shop):
1. **Báo cáo tồn** (`Tồn cuối kỳ`, `Tồn cuối`, `Tồn thực`, `Tồn kho`…): tồn **cuối dữ liệu** của từng mặt hàng; nếu báo cáo ghi theo đơn vị lớn thì quy về đơn vị cơ bản.
2. **Lô** (nhà thuốc): bảng lô (`Lô`, `Hạn sử dụng`, số lượng nhập theo đơn vị cơ bản) + bảng bán theo lô (`Mã hóa đơn`, `Lô`, `Số lượng`, `Số lượng trả`).
   Còn lại của lô = nhập − bán trên đơn **không huỷ** + số lượng **trả lại**. Công thức này khớp 100% với báo cáo tồn ở mọi shop train có cả hai nguồn.
   Chỉ tạo `v_lots` khi có cả bảng bán theo lô (thiếu thì `qty_remaining` sẽ sai).
3. **Thẻ kho** (`the_kho`: mỗi lần nhập/xuất một dòng, kèm `TonCuoi` sau giao dịch): tồn tại **mọi thời điểm**. Ở shop public có cả thẻ kho lẫn lô, hai nguồn khớp 80/80 mặt hàng.

Thứ tự ưu tiên cho `v_stock`: báo cáo tồn → thẻ kho → lô.

- **`v_stock`** (mỗi mặt hàng một dòng): `item_code`, `item_name`, `base_unit`, `stock_date` (ngày cuối dữ liệu = "hôm nay" của mọi câu train/public), `stock_qty_base` (REAL, đơn vị cơ bản), `cost_price` (giá vốn trong danh mục, có thể NULL), `stock_value` (= `stock_qty_base * cost_price`, chỉ hàng còn tồn; NULL nếu không có giá vốn), `source` (`'report'` | `'lots'`).
- **`v_lots`** (mỗi lô một dòng): `lot`, `item_code`, `item_name`, `base_unit`, `receipt_id`, `receipt_date`, `expiry_date` (`YYYY-MM-DD`), `qty_in`, `qty_sold`, `qty_returned`, `qty_remaining`, `unit_cost_base` (giá nhập của chính lô, theo đơn vị cơ bản — dùng cho "tiền vốn hàng sắp hết hạn" §6).
- **`v_stock_card`** (khi có thẻ kho): `item_code`, `item_name`, `moved_at`, `moved_date`, `qty_change`, `stock_after`. Tồn hết ngày X = `stock_after` của giao dịch **cuối cùng** có `moved_date <= X`.
- **`v_item_units`** (mọi shop có sổ bán): `item_code`, `item_name`, `unit`, `unit_key` (không dấu, để so khớp), `factor` (số đơn vị cơ bản trong 1 `unit`), `base_unit`.

**Giới hạn:** `v_stock` là tình trạng **cuối dữ liệu**. Câu hỏi "đến hết ngày X" với X sớm hơn: dùng `v_stock_card` nếu có; shop chỉ có báo cáo tồn thì không có dữ liệu trả hàng theo dòng nên không tính lại chính xác được.

```sql
-- 1) Tồn cuối ngày hôm nay của một mặt hàng (đơn vị cơ bản)
SELECT stock_qty_base FROM v_stock WHERE LOWER(item_name) = LOWER('Bia Tiger lon');

-- 2) Tồn theo đơn vị lớn §5: [số đơn vị lớn nguyên, số đơn vị cơ bản lẻ]
SELECT CAST(s.stock_qty_base / u.factor AS INTEGER) AS so_chan,
       CAST(s.stock_qty_base - CAST(s.stock_qty_base / u.factor AS INTEGER) * u.factor AS INTEGER) AS so_le
FROM v_stock s JOIN v_item_units u ON u.item_name = s.item_name
WHERE LOWER(s.item_name) = LOWER('Amoxicillin 500mg hộp 10 vỉ x 10 viên') AND u.unit_key = 'hop';

-- 2b) Tồn hết ngày X từ thẻ kho
SELECT stock_after FROM v_stock_card
WHERE item_code = 'SP0001' AND moved_date <= '2026-03-31'
ORDER BY moved_at DESC, rowid DESC LIMIT 1;

-- 3) Số mặt hàng hết hàng cuối ngày hôm nay
SELECT COUNT(*) FROM v_stock WHERE stock_qty_base <= 0;

-- 4) Giá trị hàng tồn kho (giá vốn danh mục, chỉ hàng còn tồn)
SELECT SUM(stock_value) FROM v_stock WHERE stock_qty_base > 0;

-- 5) Số lô còn tồn hết hạn từ hôm nay D đến hết ngày E; lô gần hết hạn nhất của một thuốc
SELECT COUNT(*) FROM v_lots WHERE qty_remaining > 0 AND expiry_date BETWEEN '2026-05-25' AND '2026-09-22';
SELECT MIN(expiry_date) FROM v_lots
WHERE item_name = 'Siro ăn ngon Ích Nhi Plus chai 100ml' AND qty_remaining > 0 AND expiry_date >= '2026-05-25';
```

---

## 4. Hộ kinh doanh không có SalesLedger (Non-ledger shops)

Một số tiệm đặc thù không bán mặt hàng theo đơn mà chỉ ghi sổ dịch vụ/sửa chữa (ví dụ `dev_012` – Tiệm sửa xe máy có `SoSuaXe.xlsx` và `DanhSachTho.xlsx`, không có cột tên mặt hàng, số lượng hay mã đơn).

- Hàm `can_build_ledger(tables, mapping, readme)` trả về `False`.
- `build_database` **không tạo** bảng `lines`, `items` và các view `v_lines`, `v_valid_lines`, `v_orders`, `v_valid_orders`, `v_items`.
- `build_database` tạo đầy đủ các bảng đã làm sạch (`so_sua_xe`, `danh_sach_tho`, ...) và bảng gốc (`raw_so_sua_xe`, `raw_danh_sach_tho`, ...) cùng bảng `calendar`.
- `schema_text(conn)` hiển thị thông báo rõ ở đầu:
  `=== NOTICE: NON-LEDGER BUSINESS (NO SALES VIEWS) ===` để model truy vấn trực tiếp trên các bảng đã làm sạch.

---

## 5. Năm (5) câu SQL mẫu khớp đáp án `answers.jsonl`

Dưới đây là 5 mẫu câu SQL chuẩn chạy trực tiếp trên `build_database("data/train/data/biz_102")` (và `biz_101`) khớp 100% đáp án chuẩn trong `data/train/answers.jsonl`:

### Mẫu 1: Doanh thu tháng (`q_79dbf0f33660` – `biz_102`, tháng `01/2025`, đáp án: `435803500`; `q_79b47679f41f` – `biz_101`, tháng `06/2025`, đáp án: `202856500`)

```sql
SELECT CAST(ROUND(SUM(revenue)) AS INTEGER) AS monthly_revenue
FROM v_valid_orders
WHERE order_month = '2025-01';
-- Kết quả trên biz_102 (q_79dbf0f33660): 435803500
```

### Mẫu 2: Số đơn huỷ trong kỳ (`q_1bd200cd8993` – `biz_102`, tháng `02/2025`, đáp án: `61`)

```sql
SELECT COUNT(*) AS cancelled_orders
FROM v_orders
WHERE order_month = '2025-02'
  AND status = 'huy';
-- Kết quả trên biz_102 (q_1bd200cd8993): 61
```

### Mẫu 3: Tỉ lệ huỷ đơn (`q_3379b46319a8` – `biz_102`, tháng `02/2025`, đáp án: `2.58`)

```sql
SELECT ROUND(
    SUM(CASE WHEN status = 'huy' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) + 1e-9,
    2
) AS cancellation_rate_pct
FROM v_orders
WHERE order_month = '2025-02';
-- Kết quả trên biz_102 (q_3379b46319a8): 2.58
```

### Mẫu 4: Top 3 mặt hàng bán chạy theo số lượng quy đổi (`q_dfe2b9e2e7b3` – `biz_102`, tháng `02/2026`)

Đáp án chuẩn: `['Snack Oishi tôm cay 40g', 'Mì Hảo Hảo tôm chua cay', 'Trứng gà so']` (theo **§3**: lọc `is_service_fee = 0`, xếp theo `SUM(qty_base) DESC`, nếu bằng nhau xếp theo `COALESCE(item_code, item_name) ASC`).

```sql
SELECT
    item_name,
    SUM(qty_base) AS total_qty_base
FROM v_valid_lines
WHERE order_month = '2026-02'
  AND is_service_fee = 0
GROUP BY item_code, item_name
ORDER BY total_qty_base DESC, COALESCE(item_code, item_name) ASC
LIMIT 3;
-- Kết quả trên biz_102 (q_dfe2b9e2e7b3):
-- 1. Snack Oishi tôm cay 40g
-- 2. Mì Hảo Hảo tôm chua cay
-- 3. Trứng gà so
```

### Mẫu 5: Giá trị trung bình mỗi đơn hàng làm tròn nửa lên – AOV (`q_dcc0b785c232` – `biz_102`, tháng `02/2025`, đáp án: `158315`)

Theo **§11** (làm tròn nửa lên — `CAST(x + 0.5 AS INTEGER)` cho số dương):

```sql
SELECT CAST(SUM(revenue) * 1.0 / COUNT(*) + 0.5 AS INTEGER) AS aov_half_up
FROM v_valid_orders
WHERE order_month = '2025-02';
-- Kết quả trên biz_102 (q_dcc0b785c232): 158315
```
