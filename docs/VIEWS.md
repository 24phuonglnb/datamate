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
4. **Calendar Table (`calendar`)** — nạp từ `calendar.csv` (dương lịch, âm lịch, thứ trong tuần, cuối tuần, ngày lễ).

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
GROUP BY order_id;
```

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
| `active_ingredient` | `TEXT` | Hoạt chất (đối với nhà thuốc, nếu có). |
| `is_prescription` | `TEXT` | Thuốc kê đơn (đối với nhà thuốc, nếu có). |

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
