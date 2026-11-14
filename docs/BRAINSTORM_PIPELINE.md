# DataMate (ZAC 2026) — Brainstorm và phản biện pipeline

Ngày viết: 11/11/2026. Hạn nộp Docker: 16/11/2026 23:59 GMT+7.

Quy ước nhãn trong tài liệu:

- **[KC]** = sự thật đã kiểm chứng, kèm cách kiểm chứng.
- **[GT]** = giả thuyết, chưa đo. Mọi con số PA kỳ vọng đều là [GT].

Những gì **chưa** làm được trong lượt phân tích này: chưa chạy LLM nào (máy phân tích chỉ có RTX 4060 8 GB), chưa đọc lại PDF Docker guideline (dùng các ràng buộc đã ghi trong prompt), và không kiểm tra được danh sách model phát hành sau tháng 6/2026.

---

## 1. Tóm tắt khuyến nghị

1. **Gộp 2a và 2b thành một đường duy nhất: LLM sinh Python gọi thư viện helper** (`revenue(period, **filters)`, `rank(...)`), được phép rơi xuống pandas thô khi helper không phủ. Bỏ plan JSON thuần.
2. **Không ép mọi shop vào schema chung cứng.** Chỉ chuẩn hoá phần "sổ bán hàng" (order lines) mà 44/44 shop đều có; mọi bảng còn lại giữ dạng bảng đã làm sạch ô + mô tả cột, để code-gen tự xử lý. Ngành mới ở public (sửa xe, điện thoại, mẹ & bé) không khớp schema orders/payments.
3. **Mapping cột: README trước, heuristic sau, LLM cuối cùng.** 37/44 README có từ điển cột với từ vựng gần như cố định ("mã đơn", "thành tiền sau giảm", "trạng thái đơn"…).
4. **Dùng 3000 câu train làm bộ regression exact-match cho thư viện helper**, không phải chỉ làm eval cuối. Một helper "xong" khi tái lập đúng đáp án train của intent đó trên mọi shop.
5. **Ưu tiên số 1 của tầng LLM là chuẩn hoá ngôn ngữ, không phải parser.** Public lệch hẳn train về cách viết ngày (35% câu public dùng `T8/2025`, `8/26`, `6-2025`, `Q1/2026`; train 0%) và phương ngữ/teencode. Regex viết theo train sẽ vỡ.
6. **Không yêu cầu "2 đường đồng ý mới trả lời".** Với +1/−1/0, điểm hoà vốn là xác suất đúng 50%. Trả lời khi phiếu đa số của N chương trình ≥ ngưỡng (calibrate trên shop giữ lại), abstain phần còn lại.
7. **Đưa nguyên rulebook của split vào prompt** (19–24 KB, vừa context, cache prefix). Diff rulebook chỉ dùng để **tắt helper** có luật đã đổi, không dùng để định tuyến.
8. **Giữ Qwen3-14B, không thêm model embedding** (14.8B + bất kỳ embedder nào > 0.2B là vượt 15B). Nối tên hàng/khách bằng fuzzy matching không dùng mạng nơ-ron.
9. **Không LoRA trong 5 ngày.** Thay bằng "distill vào prompt": ngân hàng ví dụ (câu hỏi → chương trình) đã kiểm chứng ra đúng đáp án train, truy hồi bằng BM25.
10. **Nộp Docker bản an toàn vào 15/11**, bản cuối 16/11 trước 18:00. Dành 25 lượt nộp public còn lại (5/ngày) làm phép đo tổng quát hoá ngành mới, có kế hoạch từng lượt.

---

## 2. Phản biện hướng hiện tại

### 2.1 Giữ

| Ý | Lý do | Bằng chứng |
|---|---|---|
| "Biên dịch câu hỏi thành phép tính" xác định | Đáp án chuẩn sinh từ code xác định; làm đúng mapping + làm sạch là khớp từng đồng | **[KC]** Với mapping tay 5 cột + `src/cleaning.py` (fill-down, khử trùng), doanh thu tháng khớp **24/24** câu trên 6 shop (biz_101, 103, 107, 112, 114, 117). Script: `scripts/analysis/revenue_check.py` |
| Làm sạch bằng code, không bằng LLM | Lỗi làm sạch là lỗi hệ thống, kéo sai hàng loạt | **[KC]** biz_103: 27.401 ô mã đơn trống cần fill-down; bỏ fill-down thì câu doanh thu tháng sai. biz_117: 473 dòng trùng trong cùng đơn; bỏ khử trùng thì sai |
| Giải thời gian bằng Python | Luật §2 có nhiều góc (tháng này so tháng trước cùng số ngày, Tết theo lịch âm) | **[KC]** 64% câu train là "tháng M/YYYY" tường minh; phần tương đối (hôm nay 7%, hôm qua 6%, tháng này 5%, tuần rồi 4%) đều có định nghĩa máy móc trong §2 |
| Eval giữ lại nguyên business | Private có shop và ngành mới | Xem §3.10 về cách chia |
| Luật riêng cho unanswerable | 70/3000 câu train (2,3%), sai là −1 | **[KC]** Đọc cả 70 câu: 3 loại rõ ràng (§3.6) |

### 2.2 Đổi

**(a) Schema chung cứng → schema lõi + bảng tự do.**

**[KC]** Đọc cấu trúc 44 shop (tái lập bằng `scripts/analysis/profile_raw.py`). Năm shop minh hoạ độ lệch:

| Shop | Cấu trúc | Hệ quả cho schema |
|---|---|---|
| biz_101 | 1 CSV phẳng, 56.501 dòng, ngày dạng `1 thg 6 2025`, khách là tên | Không có products/customers riêng; quy đổi đơn vị nằm trong README |
| biz_105 | Sổ tay Excel, 17 sheet theo tháng, header gộp 2 dòng (`Hàng / Tiền / Đơn`), giá `25.000đ`, có `BangGia`, `SoNhapHang`, `TonKho` | Cần dò header, lấy năm từ tên sheet |
| biz_106 | POS xuất 10 file, có dòng tiêu đề `DANH SÁCH HÓA ĐƠN` trên header, chi tiết tách `_1`, `_2`, có `SoQuy` (thanh toán) | Cần bỏ preamble, nối file tách |
| biz_123 | `pos.sqlite` 17 bảng: `the_kho`, `lo_hang`, `chi_tiet_don_lo`, `lich_su_gia`, `tra_hang` | Schema giàu hơn hẳn mọi schema chung hợp lý |
| dev_012 (public, sửa xe) | `SoSuaXe.xlsx`: mỗi dòng một lượt xe; cột `Xe` chứa dòng xe + biển số; cột `Làm gì` là văn bản tự do nhiều việc; `DanhSachTho` có % hoa hồng | **Không có** đơn/dòng hàng/sản phẩm. Ép vào `orders/order_lines` là mất thông tin |
| dev_014 (public, điện thoại) | Sổ bán + sheet `Ghi tắt`, sổ thu máy cũ, sổ nợ, sổ góp, sổ bảo hành; nối qua STT, IMEI, tên + SĐT | Các thực thể "kỳ góp", "lượt bảo hành" không tồn tại ở train |

Kết luận: schema 9 bảng (orders, order_lines, products, unit_conv, customers, payments, purchases, inventory, expenses) phủ tốt train nhưng ngành mới sẽ luôn có bảng nằm ngoài. P1 sẽ tốn cả tuần đuổi theo mà vẫn hụt đúng chỗ private khác biệt.

**(b) 2a (plan JSON) + 2b (pandas) song song → một đường code-gen gọi helper.**

- Plan JSON là một ngôn ngữ thứ hai phải thiết kế, viết interpreter, và dạy model. Mỗi intent mới ở public (ví dụ "có mấy bữa quán bán được từ 9.100.000 đồng trở lên", 1,6% public, ~0% train **[KC]**) đòi mở rộng DSL.
- 2a và 2b dùng chung bảng đã làm sạch, chung kết quả giải thời gian, chung cách hiểu câu hỏi của cùng một model. Lỗi của chúng **tương quan**, nên "đồng ý" là tín hiệu yếu hơn vẻ ngoài **[GT]**.
- Code Python gọi helper thì: câu dễ chỉ là một dòng (`answer = revenue(month(2025, 5))`), câu lạ dùng pandas trên cùng bảng; cùng một định dạng log (`code`/`output`) mà BTC yêu cầu.

**(c) "Đồng ý mới trả lời" → ngưỡng theo xác suất.** Xem §3.6. Yêu cầu đồng thuận 2 đường sẽ abstain toàn bộ phần DSL không phủ, tức đúng phần ngành mới.

**(d) Diff rulebook để định tuyến → rulebook nguyên văn trong prompt + diff để tắt helper.** Xem §3.5.

### 2.3 Bỏ (trong 5 ngày)

- **LoRA/distill vào weights.** Lý do ở §3.8.
- **LLM đề xuất mapping cho mọi shop.** Chỉ gọi LLM cho cột mà README và heuristic không gán được.
- **Sửa bug "tháng M không ghi năm".** **[KC]** Chỉ 4/3000 câu train thuộc dạng này (public: 39/1000 theo regex thô, nhưng phần lớn là do định dạng ngày mới chứ không phải thiếu năm). Sẽ được giải quyết chung trong bộ giải thời gian, không cần ưu tiên riêng.
- **`benchmark/` 105 câu synthetic** làm thước đo. Chỉ giữ làm smoke test.

---

## 3. Kiến trúc đề xuất

### 3.1 Sơ đồ stage

```
/data/<split>/
   │
   ├─[S0] load + clean (mỗi business 1 lần, cache)        P1   code xác định
   │        RawTable[] ──► CleanTable[] + Profile
   │        + SalesLedger (nếu nhận diện được sổ bán)
   │        + invariant report
   │
   ├─[S1] rulebook: đọc bản của split, diff với bản train  P3   code xác định
   │        ──► RuleDiff {changed, added, removed}
   │        ──► tập helper bị tắt
   │
   └─ mỗi câu hỏi ──────────────────────────────────────────────────────
        [S2] chuẩn hoá câu hỏi          LLM (no-think) + Python    P3
             ──► NormQ {text, periods[], entities[], answer_type}
        [S3] gate unanswerable          luật + LLM                 P3
        [S4] sinh N chương trình        LLM (think), batch vLLM    P3
             prompt = rulebook + profile shop + NormQ + k ví dụ
        [S5] thực thi sandbox           subprocess, timeout        P4
             ──► N × (value, type, error)
        [S6] bỏ phiếu + kiểm tra hợp lý ──► answer | abstain       P4
        [S7] format §9 + log                                       P4
```

### 3.2 Tầng dữ liệu (S0) — trả lời câu 2

**Schema lõi `SalesLedger`** (một DataFrame, mỗi dòng là một dòng hàng đã bán):

```
order_id      str | None   # None nếu sổ không ghi theo đơn (biz_107, biz_113)
order_date    date
order_time    time | None
status        {"hoan_thanh","huy","tra_hang","dang_giao"}   # rulebook §8
item_name     str          # nguyên văn trong file
item_code     str | None
unit          str
qty           float
qty_base      float        # đã quy về đơn vị cơ bản
unit_price    float
line_amount   float        # thành tiền sau giảm giá dòng
customer_name str | None
customer_code str | None
extra         dict         # mọi cột còn lại của dòng (kênh, nhân viên, PTTT, ca…)
```

Mọi bảng khác (danh mục, khách, nhập hàng, tồn, thanh toán, lô, giá, chi phí, sổ góp, sổ bảo hành…) giữ nguyên dạng `CleanTable`: cột đã ép kiểu (số, ngày), header đã dò, sheet đã nối, kèm `role` nếu đoán được và mô tả cột lấy từ README.

**Chữ ký:**

```python
def load_business(dir: Path) -> list[RawTable]                 # đã có trong src/cleaning.py
def clean_tables(raw: list[RawTable], readme: str) -> list[CleanTable]
def build_sales_ledger(tables: list[CleanTable], mapping: ColumnMapping) -> SalesLedger | None
def propose_mapping(tables, readme) -> ColumnMapping           # README → heuristic → LLM
def check_invariants(ledger, tables) -> list[InvariantResult]
def profile_text(tables, ledger, max_chars=6000) -> str        # đưa vào prompt
```

**Mapping: README trước, heuristic sau, LLM cuối.**

- **[KC]** 26/30 README train và 11/14 README public có mục `## Cột trong …` dạng `- **<tên cột>**: <mô tả>`. Từ vựng mô tả rất tập trung: "mã đơn" (51 lần trên train), "tên hàng" (47), "trạng thái đơn" (30), "ngày bán" (30), "thành tiền sau giảm" (29), "số lượng đã đổi ra đơn vị cơ bản" (24). Đếm bằng regex trên 44 README.
- **[KC]** Từ vựng này **nở ra** ở public: 105 mô tả khác nhau trên train, 151 trên public. Nên bảng tra mô tả → vai trò phải khớp mờ, và có đường lui.
- 7 shop không có từ điển cột đều là POS xuất (biz_106, 109, 123, 124; dev_003, 006, 014) với tên cột kiểu POS quen thuộc (`Mã hóa đơn`, `Thành tiền`, `MaHoaDon`, `TriGia`). Heuristic theo tên cột + kiểu dữ liệu đủ cho phần lớn; LLM chỉ xử lý phần còn lại, đầu ra JSON, cache theo business.
- Cấm mapping theo `business_id`. Mọi quyết định suy từ README và nội dung ô.

**Invariant bắt lỗi mapping** (mỗi cái trả pass/fail/không áp dụng):

| Invariant | Bắt lỗi gì |
|---|---|
| `qty × unit_price ≈ line_amount` trên ≥ 95% dòng (cho phép giảm giá dòng) | Nhầm cột tiền/giá/số lượng |
| Tổng `line_amount` theo đơn ≈ cột "tổng tiền hàng" của bảng đơn (nếu có) | Nối sai bảng đơn ↔ chi tiết, thiếu file `_2` |
| `qty_base / qty` là hằng số theo (mặt hàng, đơn vị) và khớp bảng quy đổi/README | Nhầm cột quy đổi; hệ số sai |
| Mỗi `order_id` có đúng một `status`, một `order_date` sau fill-down | Fill-down sai nhóm; mã đơn nhầm cột |
| `status` sau chuẩn hoá ∈ 4 giá trị §8; tỉ lệ huỷ nằm trong 0–15% | Nhầm cột trạng thái (**[KC]** 6 shop kiểm tra có 1,9–3,0% số dòng thuộc đơn huỷ) |
| Ngày parse được ≥ 99,5%; khoảng ngày khớp "Dữ liệu có đến hết dd/mm/yyyy" trong README | Parse nhầm ngày/tháng, sai năm theo sheet |
| Số dòng sau khử trùng ≤ trước; tỉ lệ trùng < 5% | Khử trùng quá tay |
| Mọi `item_name` trong ledger nối được vào danh mục (nếu có danh mục) | Nối tên sai, danh mục sai file |

Invariant fail không dừng pipeline: nó hạ độ tin cậy mọi câu của shop đó (§3.6) và ghi vào log.

**Việc còn mở cho P1 [KC]:** `scripts/analysis/revenue_check.py` báo biz_117 còn 40 ngày và 23 số tiền chưa parse được, biz_107 còn 526 ngày chưa parse (ngày dạng serial Excel `45717`). Đây là các dòng tổng/ghi chú hoặc định dạng chưa phủ; cần phân loại trước khi tin doanh thu các shop này ở mọi kỳ.

### 3.3 DSL hay code tự do — trả lời câu 3

Điểm cân bằng: **helper là thư viện Python, không phải ngôn ngữ**. LLM viết Python; helper chỉ đóng gói những luật rulebook dễ sai nhất.

```python
# thời gian: trả về Period(start: date, end: date), đã cắt theo as_of
month(y, m); quarter(y, q); day(d); last_n_days(n); this_week(); last_week()
this_month(); same_days_prev_month(); ytd(); tet(year); before_tet(year)
between(d1, d2)

# sổ bán: mọi hàm nhận period và bộ lọc theo cột
valid_lines(period, **filters) -> DataFrame      # đơn không huỷ, không trả (§1)
all_orders(period, **filters)  -> DataFrame      # mọi trạng thái (mẫu số tỉ lệ huỷ)
revenue(period, **filters) -> int
order_count(period, **filters) -> int
qty_base(period, **filters) -> float
group_revenue(period, by, **filters) -> Series

# trả lời
rank(series, k=None, tie_codes=None) -> list     # giảm dần, hoà thì theo mã (§9)
pct_change(cur, prev) -> float                   # 2 chữ số, âm khi giảm
share(part, whole) -> float
find_item(text) -> Item; find_customer(text) -> Customer   # fuzzy, trả mã + tên chuẩn
as_answer(value, type) -> dict                   # ép format §9
```

Nguyên tắc:

- Helper **không** quyết định intent. Nó chỉ làm đúng một luật. Thứ gì phải diễn giải thì để LLM viết.
- Bảng tự do truy cập qua `T["ten_bang"]` (DataFrame đã làm sạch). Câu về sổ góp, bảo hành, lượt xe đi đường này.
- Mỗi helper gắn `rule_refs` = dòng rulebook train mà nó hiện thực (dùng cho §3.5).
- DSL rộng đến đâu: đủ cho tier A và B của taxonomy (≈ 80% câu train). Tier C thêm dần theo số câu.

### 3.4 Chuẩn hoá câu hỏi (S2)

Đầu ra:

```json
{"text": "doanh thu tháng 8/2025 so với tháng liền trước thay đổi bao nhiêu phần trăm",
 "periods": [{"kind": "month", "y": 2025, "m": 8}],
 "entities": [{"span": "sting dau", "kind": "item", "code": "SP0042", "name": "Sting dâu 330ml", "score": 0.97}],
 "answer_type": "percent"}
```

- **Viết lại câu hỏi bằng LLM** (no-think, nhiệt độ 0) thành tiếng Việt chuẩn có dấu, giữ nguyên số và tên riêng. Sau đó Python mới trích kỳ thời gian từ câu đã chuẩn hoá. Lý do: **[KC]** public có `8/26`, `Th5/2026`, `T1/2025`, `6-2025`, `06/2026`, `Q1/2026`, "ngày mô", "bữa ni", "tháng ni", "nhứt", "mik", "kó", "hok", "đh", "o đờ", "10 củ", lỗi gõ "bná", "báng đượt", emoji. Không regex nào viết từ train phủ hết, và private sẽ lệch tiếp.
- **Kiểm tra an toàn sau khi viết lại:** mọi con số trong câu gốc phải còn trong câu mới (so tập số); nếu không, dùng câu gốc.
- **Nối thực thể không dùng embedding:** chuẩn hoá bỏ dấu + n-gram ký tự + token-set ratio trên danh mục hàng/khách của shop. Trả top-3 ứng viên vào prompt, để LLM chọn. Đáp án string luôn xuất **tên nguyên văn trong file** (§9 nhận mọi cách viết có trong file hoặc mã).
- **`answer_type`** đoán từ mẫu câu ("bao nhiêu %" → percent, "ngày nào" → date, "top k" → list, "bảng… kèm số tiền" → table, "có… không" → boolean). Sai type là sai câu, nên type do bước này quyết, không để code-gen tự chọn.

### 3.5 Tổng quát hoá cho private — trả lời câu 4

**[KC] Rulebook dự báo phân bố câu hỏi.** Diff rulebook train ↔ public (`diff` hai file): public **bỏ** 3 luật "Giá nhập bình quân", "Tồn theo đơn vị lớn", "Giá bán X ngày D". Đếm intent tương ứng: `purchase_avg_price` 63 câu train → **0** public; `stock_large_unit` 20 → **0**; `sell_price_on_day` 50 → 3. Ngược lại public **thêm** ~30 dòng luật (khách sộp nhất, giờ cao điểm, mẹ & bé, sửa xe, điện thoại) và các câu tương ứng xuất hiện (hoa hồng thợ/lượt xe 2,6%, bảo hành 1,0%, thu máy cũ 2,0%).

Hệ quả thiết kế:

1. **Rulebook nguyên văn vào prompt.** 19 KB (train) / 24 KB (public), ước ~8–10k token **[GT]**; đặt ở đầu prompt để vLLM cache prefix. Model luôn thấy luật của đúng split, không cần cơ chế chọn đoạn.
2. **Diff để tắt helper.** Lúc chạy, so từng dòng luật của split với bản train đóng trong image. Helper nào có `rule_refs` trỏ tới dòng đã **đổi hoặc biến mất** thì bị gỡ khỏi namespace và khỏi tài liệu helper trong prompt; LLM buộc viết pandas theo luật mới. Dòng **thêm** không cần xử lý riêng vì đã nằm trong prompt. Khả thi: diff theo dòng bảng Markdown là đủ, ~30 dòng code.
   - Ví dụ thật: public sửa dòng "Đơn thuộc kỳ nào" (thêm câu về đơn trả sau kỳ) và "Giao nhiều đợt" (thêm "tính đến hết hôm nay"). Cái đầu không đổi phép tính; cái sau có. Diff chỉ báo "đổi"; mặc định an toàn là tắt helper liên quan.
3. **Ngành mới đi đường bảng tự do.** Không có `SalesLedger` thì helper sổ bán không được nạp; prompt chỉ có profile bảng + README + rulebook. Đây là lý do không được để pipeline phụ thuộc vào việc dựng được ledger.
4. **Đo trước khi tin:** chia eval theo ngành (§3.10) và dùng lượt nộp public để đo riêng 4 shop ngành mới (dev_011–014).

Ý tốt hơn diff, nếu còn thời gian **[GT]**: "biên dịch rulebook lúc chạy". Trước khi trả lời câu nào, với mỗi dòng luật mới/đổi, cho LLM viết một ghi chú thực thi ngắn (cột nào, lọc gì, mẫu số nào) dựa trên profile các shop của split; cache và chèn vào prompt các câu liên quan. Chi phí: ~30–50 lần gọi một lần cho cả split.

### 3.6 Abstain và độ tin cậy — trả lời câu 5

**Số học.** PA = (đúng − sai) / N. Trả lời một câu có xác suất đúng p đóng góp kỳ vọng 2p − 1; abstain đóng góp 0. **Ngưỡng tối ưu là p > 0,5**, không phải "chắc chắn mới trả lời".

Ví dụ minh hoạ (không phải dự báo): độ chính xác khi trả lời hết = 75% → PA = 0,50. Nếu bộ lọc bắt được 60% câu sai (15 điểm) và bỏ nhầm 5 điểm câu đúng: PA = (70 − 10)/100 = 0,60.

**Tín hiệu, xếp theo giá trị/công sức:**

| Tín hiệu | Cách làm | Nhận xét |
|---|---|---|
| Lỗi thực thi, kết quả rỗng/NaN | Miễn phí | Luôn dùng; sau 1 lần sửa lỗi mà vẫn hỏng thì abstain |
| Kiểm tra hợp lý theo type | percent trong [−100, +∞) và share trong [0, 100]; date nằm trong kỳ hỏi; tên trong list có trong danh mục; số đếm là số nguyên ≥ 0; list đúng k phần tử | Miễn phí, bắt lỗi thô |
| **Phiếu đa số của N chương trình** | N = 5 chương trình sinh từ 5 biến thể prompt (bộ ví dụ khác nhau, có/không nêu helper), nhiệt độ 0; so giá trị sau format | Tín hiệu chính. Tỉ lệ đồng thuận → xác suất đúng qua bảng calibrate |
| Invariant của shop | Từ §3.2 | Hạ một bậc tin cậy cho cả shop |
| Intent lạ | Không ví dụ train nào gần (điểm BM25 thấp) | Nâng ngưỡng đồng thuận |
| Logprob | Trung bình logprob token câu trả lời | Yếu với code-gen; bỏ qua trong 5 ngày |

**Calibrate:** trên các shop giữ lại, lập bảng `(mức đồng thuận, có helper hay pandas thô, invariant pass/fail) → tỉ lệ đúng`. Trả lời khi tỉ lệ đúng của ô > 0,5 (lấy 0,55 để có biên). Ô nào ít hơn 30 mẫu thì gộp với ô lân cận.

**Unanswerable.** **[KC]** 70 câu train, đọc hết, chia 3 loại:

1. Kỳ hỏi nằm **hoàn toàn trước** ngày đầu dữ liệu (ví dụ biz_103 dữ liệu từ 04/2025, hỏi "dthu thang 2/2025"). Ước ~1/3 số câu. Bắt bằng code: so `Period` với [min ngày, max ngày] của bảng liên quan.
2. Shop **không ghi** loại thông tin đó: không có tồn kho/nhập hàng/công nợ/PTTT/nhóm khách, hoặc thuộc tính không có cột (giới tính, đường phố: 9 câu). Bắt bằng: LLM được hỏi "cần bảng/cột nào", đối chiếu profile.
3. Chủ quan hoặc kiến thức ngoài ("nhân viên có tận tâm không", "nên uống mấy viên": 7 câu). Bắt bằng LLM.

**[KC]** Unanswerable dồn theo shop: biz_103 và biz_112 mỗi shop 12 câu, 18/30 shop có 0 câu. Tức nó phụ thuộc shop thiếu bảng gì, nên gate loại 2 phải dựa trên profile shop chứ không trên câu chữ. Một câu như "tồn kho red bull 250ml cuối ngày hôm nay" trả lời được ở biz_109 nhưng unanswerable ở biz_103.

Trả `unanswerable` cũng là một câu trả lời có rủi ro −1; áp cùng ngưỡng p > 0,5 và calibrate riêng.

**Ước lượng [GT]:** so với "trả lời hết", bỏ phiếu + kiểm tra hợp lý tăng PA khoảng +0,05 đến +0,12, tuỳ độ chính xác gốc (gốc càng thấp, lợi càng nhiều). Phải đo trên shop giữ lại.

### 3.7 Model và inference — trả lời câu 6

- **Model:** giữ **Qwen3-14B** (đã tích hợp, 14,8B). Nếu P4 có nửa ngày, A/B với một model code ~14B (ví dụ Qwen2.5-Coder-14B) trên shop giữ lại; chọn theo PA. Không kiểm tra được model ra sau 06/2026: P4 nên rà nhanh xem có model ≤ 15B nào phát hành trước 26/10/2026 mạnh hơn rõ rệt về code.
- **Ngân sách tham số:** 14,8B để lại 0,2B. **Không** thêm embedder/reranker (bge-m3 ~0,57B là vượt). Mọi truy hồi dùng BM25/n-gram.
- **Thinking:** bật cho S4 (sinh code), giới hạn token suy nghĩ; tắt cho S2 (viết lại câu hỏi) và mapping. Log `thinking` nguyên văn theo yêu cầu.
- **Quantization và bố trí GPU [GT]:** 14,8B ở bf16 ≈ 30 GB, không vừa một 5090 kèm KV cache. Hai lựa chọn: (i) một engine tensor-parallel 2 GPU, bf16; (ii) hai replica lượng tử hoá (FP8 hoặc AWQ 4-bit, ~10–16 GB), mỗi GPU một cái, thông lượng gấp đôi. Chọn (ii) nếu PA trên shop giữ lại không giảm quá 0,01; ngược lại (i).
- **Batching:** gom theo business (prefix rulebook + profile dùng chung → cache), gửi đồng thời toàn bộ câu của business cho vLLM. Baseline hiện chạy tuần tự là lãng phí lớn nhất về thời gian.
- **Ngân sách thời gian [GT]:** 500 câu × 5 chương trình × ~1,5k token ra ≈ 3,75M token. Mục tiêu tổng thời gian ≤ 2 giờ, để dư 4 giờ; thời gian suy luận cũng là tiêu chí phân hạng khi hoà điểm.
- **Chống chết giữa chừng:** ghi `submission.jsonl` tăng dần sau mỗi business (BTC chỉ chấm phần đã ghi nếu quá giờ). Xử lý business nhỏ trước. Có đồng hồ tổng: sau 4,5 giờ thì hạ N xuống 1.
- **Tái lập (|ΔPA| ≤ 0,03, tức ≤ 15 câu/500):** nhiệt độ 0, seed cố định, đa dạng đến từ biến thể prompt chứ không từ sampling; sắp xếp câu hỏi và thứ tự batch cố định; code sinh ra chạy trong subprocess với `PYTHONHASHSEED=0`, mọi sort có khoá phụ. vLLM batch vẫn có nhiễu số học nhỏ: **đo** bằng cách chạy cùng image 2 lần trên shop giữ lại và đếm số câu đổi đáp án.

### 3.8 Fine-tune/distill — trả lời câu 7

**Không làm LoRA trong 5 ngày.** Lý do:

- Nút cổ chai hiện tại là tầng dữ liệu và chuẩn hoá câu hỏi, không phải năng lực sinh code của model **[GT, dựa trên việc phép tính tay khớp 24/24]**.
- 30 shop train, ít ngành. LoRA trên 3000 câu dễ khớp theo mẫu câu train, trong khi **[KC]** public đã lệch mẫu câu (35% định dạng ngày mới, 10% câu rơi vào OTHER của bộ gán nhãn so với 2% ở train).
- Tốn ≥ 2 ngày của một người + rủi ro tái lập, lượng tử hoá adapter, tích hợp vLLM.

**Làm thay thế (rẻ, cùng lợi ích chính): ngân hàng ví dụ đã kiểm chứng.**

1. Với mỗi câu train, sinh chương trình bằng chính pipeline (hoặc Claude/GPT, lưu prompt/response theo luật).
2. Chạy, **chỉ giữ** chương trình ra đúng đáp án `answers.jsonl`.
3. Lúc chạy, truy hồi k = 3–5 ví dụ gần nhất bằng BM25 trên câu đã chuẩn hoá, khác shop với nhau, làm few-shot.

Ví dụ lưu dạng (câu chuẩn hoá, chương trình), không chứa id. Đây là dùng train hợp lệ.

**Điều kiện để xét LoRA (cổng ngày 14/11):** helper tier A+B đã khớp train, PA trên shop giữ lại bão hoà, và lỗi còn lại chủ yếu là model viết sai code dù có ví dụ. Khi đó quy trình tối thiểu: ~2–3k cặp đã kiểm chứng, rank 16, 2 epoch, chỉ fine-tune cho S4. Khả năng cao là không tới cổng này.

### 3.9 Ý tưởng khó bị trùng — trả lời câu 9

1. **3000 đáp án train = 3000 unit test exact-match cho thư viện.** Đa số đội dùng train để chấm pipeline LLM đầu-cuối. Dùng nó để chứng minh từng helper đúng từng đồng trên mọi shop, độc lập với LLM, cho một vòng phát triển nhanh và xác định (không cần GPU).
2. **Rulebook là mục lục của bộ sinh câu hỏi** (bằng chứng ở §3.5). Đọc diff rulebook lúc chạy cho biết intent nào biến mất/xuất hiện; dùng để tắt helper và ưu tiên ví dụ.
3. **Tìm chương trình theo đáp án, không cần API.** Với câu train mà pipeline trả sai, liệt kê các biến thể luật (có/không khử trùng, lọc trạng thái nào, ngày đặt hay ngày giao, tiền dòng hay tiền đơn) và tìm biến thể ra đúng đáp án. Kết quả là chẩn đoán tự động "shop X sai vì luật Y" và thêm ví dụ kiểm chứng.
4. **Đa dạng bằng biến thể prompt ở nhiệt độ 0** thay vì sampling: có tín hiệu self-consistency mà vẫn tái lập.
5. **Gate unanswerable theo profile shop** (bảng nào có, khoảng ngày nào), không theo câu chữ.
6. **Kiểm tra bảo toàn số khi viết lại câu hỏi**, để bước chuẩn hoá bằng LLM không lặng lẽ đổi "152 đơn" thành "125 đơn".

### 3.10 Eval

- **Chia theo shop, phân tầng theo ngành và dạng file.** Đề xuất 3 fold, mỗi fold giữ lại ~8 shop; thêm một fold "bỏ nguyên một ngành" (ví dụ giữ lại toàn bộ nhà thuốc biz_119–124, vốn có intent riêng: hoạt chất, kê đơn, lô/hạn dùng) để mô phỏng ngành mới.
- Ngân hàng ví dụ và mọi calibrate chỉ dùng shop **ngoài** fold đang chấm.
- **[KC]** 7 shop train chỉ có 40 câu, 23 shop có ~118 câu; báo cáo PA theo shop lẫn tổng.
- Public test: chỉ dùng để (a) chạy thử không crash, (b) xem tỉ lệ abstain/unanswerable theo shop, (c) điểm leaderboard. Không sinh dữ liệu, không lấy nhãn.
- Chấm bằng bản cài đặt đúng luật so khớp trong `description.md` (alias, chuẩn hoá chuỗi, table so theo tập dòng). `eval/score.py` (branch `feat/official-scorer`) làm việc này; đã kiểm: chấm gold với chính nó ra PA = 1,0.

---

## 4. Taxonomy intent

**Cách gán nhãn [KC]:** bộ luật regex có thứ tự trên câu đã bỏ dấu và sửa teencode nhẹ (`scripts/analysis/intent_tagger.py`, 60 luật), chạy trên 3000 câu train và 1000 câu public. Đây là nhãn **xấp xỉ**: đã soát mẫu từng nhóm, còn nhầm lẫn giữa các nhóm gần nhau (ước ±10% mỗi nhóm), và 68 câu train (2,3%) rơi vào OTHER. Cột public chỉ để so phân bố.

**Đề xuất gán nhãn tự động cho team:** dùng nhãn regex này làm khởi điểm; sau đó dùng luôn tên helper chính trong chương trình đã kiểm chứng (§3.8) làm nhãn intent. Nhãn đó đúng theo định nghĩa và tự cập nhật khi thư viện lớn lên.

Độ khó: **D** = một helper sổ bán; **TB** = cần nối bảng phụ hoặc luật có góc; **K** = cần sổ phụ (nhập, tồn, thanh toán, lô) và luật nhiều bước.

### Tier A — chỉ cần sổ bán (2091 câu, 69,7% train; 65,4% public)

| Intent | Train | Public | Ví dụ train | Metric cần | Khó |
|---|---|---|---|---|---|
| revenue | 548 | 156 | "doanh thu tháng 5/2026 bao nhiêu" | `revenue(period)` | D |
| rev_change_pct | 184 | 95 | "tháng 2/2025 dthu thay đổi bao nhiêu % so vs tháng liền trước" | `pct_change`, kỳ so sánh §2 | TB |
| order_count | 167 | 62 | "tuan roi cua hang ban dc may don" | `order_count` | D |
| aov | 165 | 53 | "giá trị trung bình một đơn tháng 4/2026" | revenue / order_count, làm tròn nửa lên | D |
| cancel_rate | 140 | 19 | "tỉ lệ huỷ đơn tháng này là bao nhiu %" | huỷ / mọi đơn đặt trong kỳ | D |
| best_day | 124 | 19 | "dthu ngay nao cao nhat trong thang 3 nam 2026" | group theo ngày, argmax | D |
| topk_items / best_item | 139 | 25 | "Top 3 sp bán nhiều nhất tháng 2 năm 2026" | `rank(qty_base by item)`, hoà theo mã | TB |
| item_qty | 104 | 35 | "thang 6/2025 ban ra bnhiu kg nep cai hoa vang" | `find_item` + `qty_base` | TB |
| cancel_count | 101 | 23 | "thang 6/2025 bi huy may don" | đếm đơn huỷ | D |
| category_share / category_rev | 140 | 49 | "nhom chien xao dong gop bao nhiu % doanh thu" | nối danh mục, Phí phục vụ vẫn ở mẫu số | TB |
| shift | 77 | 22 | "dthu ca chiều tháng 7/2026" | lọc giờ tạo đơn 06–14, 14–22 | D |
| item_revenue | 54 | 23 | "Doanh thu của Gỏi khoai môn hải sản trong tháng 8 năm 2025" | `find_item` + `revenue` | TB |
| size_qty | 46 | 7 | "quán bán được bao nhiêu ly size L" | tên kết thúc `(M)`/`(L)` | D |
| unit_total_qty | 23 | 15 | "7 ngày gần nhất bán ra tổng cộng mấy m3" | cộng theo đơn vị cơ bản = X | TB |
| streak_bool / monthly_series / best_month | 49 | 31 | "dthu có tăng liên tục qua 3 tháng 4/2026, 5/2026, 6/2026 không" | revenue theo nhiều tháng | D |
| orders_threshold | 15 | 8 | "tháng 9/2025 có mấy đơn có doanh thu từ 430.000 đồng trở lên" | revenue theo đơn, so ngưỡng | D |
| item_in_n_orders | 10 | 4 | "co may mat hang dc mua o 124 don khac nhau tro len" | số đơn theo mặt hàng | D |
| tet | 5 | 8 | "doanh thu dịp Tết năm nay thay đổi bao nhiêu % so với Tết năm ngoái" | `tet(year)` từ calendar.csv | TB |

### Tier B — cần chiều phụ: khách, nhân viên, kênh, PTTT, thuốc (319 câu, 10,6% train; 12,8% public)

| Intent | Train | Public | Ví dụ train | Metric cần | Khó |
|---|---|---|---|---|---|
| cust_topk / top1 / top_orders | 70 | 26 | "5 khách mua nhìu tiền nhất tháng 1/2025" | xác định khách §3 (mã, hoặc tên chuẩn hoá), bỏ khách lẻ | TB |
| cust_freq_count / share | 30 | 28 | "thang 4/2026 co bnhiu khach mua tu 4 don tro len" | số đơn theo khách | TB |
| cust_group_rev / share | 41 | 18 | "Doanh thu từ khách nhóm thân thiết tháng 4/2026" | nối bảng khách; vãng lai không thuộc nhóm | TB |
| staff_top / staff_revenue | 34 | 24 | "dthu cua nhan vien ma NV001 thang 4/2025" | group theo nhân viên | D |
| channel_rev | 29 | 10 | "dthu cac don ban tai quay va cac don ban qua zalo oa" | lọc kênh, trả list 2 số | TB |
| payment_method_rev | 26 | 7 | "Doanh thu các đơn trả bằng COD và ví điện tử lần lượt" | PTTT ghi trên đơn | TB |
| rx_nonrx_revenue / rx_share | 44 | 11 | "thuốc kê đơn chiếm mấy % tổng dthu" | nối danh mục thuốc | TB |
| ingredient_revenue | 45 | 4 | "Doanh thu thuốc hoạt chất Cetirizin tháng này" | khớp hoạt chất **đúng nguyên văn** | TB |

### Tier C — cần sổ phụ và luật nhiều bước (506 câu, 16,9% train; 11,4% public)

| Intent | Train | Public | Ví dụ train | Metric cần | Khó |
|---|---|---|---|---|---|
| price_effect | 81 | 16 | "So 7 ngày kể từ ngày 16/03/2025 với 7 ngày ngay trước đó, số viên bán ra thay đổi bao nhiêu %" | hai cửa sổ N ngày, `qty_base` | TB |
| purchase_avg_price | 63 | 0 | "giá nhập bình quân một thùng bia heineken lon tháng 4/2026" | bình quân gia quyền theo SL nhập | TB |
| sell_price_on_day | 50 | 3 | "Giá bán một ly Bạc xỉu (M) vào ngày 22/08/2025" | đơn giá / hệ số, tính cả đơn huỷ | TB |
| purchase_total / supplier_top / minus_sales | 52 | 18 | "Tổng tiền hàng nhập vào tháng 7/2025" | phiếu nhập, bỏ phiếu huỷ | TB |
| stock_qty | 44 | 3 | "trong kho còn mấy lon bia heineken lon" | tồn tại ngày X từ nhập − bán hoặc thẻ kho | K |
| stock_large_unit / stock_value / stockout | 27 | 3 | "còn mấy hộp chẵn và mấy viên lẻ" | tồn + quy đổi nhiều cấp | K |
| unsold_count | 33 | 3 | "có mấy món ế, k bán dc cái nào" | đã từng bán trước kỳ, trong kỳ không có | TB |
| debt_total / customer_count / topk_table | 53 | 27 | "3 khách nào đang nợ nhiều nhất, mỗi người còn nợ bao nhiêu" | tổng đơn − các khoản trả đến ngày X; bỏ COD, sàn | K |
| debt_collected / debt_flow_customer | 54 | 12 | "khách X ghi nợ thêm bao nhiêu và trả nợ được bao nhiêu" | trả sau ngày mua, theo ngày trả | K |
| debt_aging | 13 | 10 | "số tiền còn nợ chia theo tuổi nợ 0–7, 8–15 và trên 15 ngày" | tuổi nợ từ ngày đặt | K |
| expiry_list / nearest_lot | 13 | 5 | "lô … gần hết hạn nhất có hạn dùng ngày nào" | tồn theo lô | K |
| gross_profit / profit_item_top / net_profit | 18 | 13 | "tháng 10/2025 lời gộp của cửa hàng" | giá vốn ghi trên dòng bán; sổ chi phí | TB |
| delivery_count | 5 | 1 | "đếm số đợt giao hàng trong tháng 1/2026" | bảng phiếu giao | D |

### Tier D — không trả lời được theo câu chữ, và chưa phân loại (84 câu, 2,8% train; 10,4% public)

| Nhóm | Train | Public | Ví dụ | Xử lý |
|---|---|---|---|---|
| Chủ quan / kiến thức ngoài | 7 | 0 | "Nhân viên Phùng Thu Trang làm việc có tận tâm với khách không?" | gate unanswerable |
| Thuộc tính khách không có cột | 9 | 6 | "khach nu chiem bnhiu % doanh thu" | gate theo profile |
| OTHER | 68 | 98 | train: chủ yếu biến thể câu chữ của tier A. Public: "thợ mô làm nhiều lượt xe nhất", "khách quá hạn góp", "mấy bữa quán bán được từ 9.100.000 đồng trở lên" | code-gen bảng tự do |

**Phủ được bao nhiêu trong 5 ngày [GT]:** tier A + B = 2410 câu = **80% train** (78% public theo nhãn regex) là mục tiêu thực tế cho thư viện helper. Trong tier C, làm `price_effect`, `sell_price_on_day`, `purchase_*`, `unsold_count`, `gross_profit` (≈ 8% train); phần công nợ/tồn kho/lô (≈ 9% train) để code-gen với ví dụ kiểm chứng và chấp nhận tỉ lệ abstain cao hơn. "Phủ" nghĩa là có helper đúng; độ chính xác đầu-cuối còn tuỳ S2 và S4.

Lưu ý phân bố public **[KC]**: `purchase_avg_price`, `stock_large_unit` biến mất; `rev_change_pct` tăng từ 6% lên 9,5%; OTHER tăng từ 2% lên 10%. Không tối ưu theo tần suất train một cách máy móc.

---

## 5. Backlog thí nghiệm

Xếp theo (PA kỳ vọng tăng) / (công sức). PA kỳ vọng là [GT], tính trên shop giữ lại so với baseline text-to-SQL.

| # | Thí nghiệm | Giả thuyết | Cách đo | Công | Ai |
|---|---|---|---|---|---|
| 1 | Harness eval theo fold shop + scorer đúng luật | Không có thước đo đúng thì mọi thứ khác là đoán | Chấm baseline hiện tại trên 3000 câu train; ra PA theo shop, theo intent | 0,5 ngày | P4 |
| 2 | S0 cho 30 shop train: load, clean, mapping README, ledger, invariant | Lỗi dữ liệu là nguồn sai lớn nhất; sửa xong thì tier A tính đúng | Regression: `revenue(month)` khớp đáp án trên mọi shop có câu doanh thu tháng (hiện 24/24 trên 6 shop với mapping tay) | 1,5 ngày | P1 |
| 3 | Helper tier A + bộ giải thời gian §2 | Phủ ~70% câu train bằng phép tính đã chứng minh đúng | Với mỗi intent tier A, tỉ lệ câu train mà chương trình mẫu ra đúng đáp án ≥ 95% | 1,5 ngày | P2 |
| 4 | Viết lại câu hỏi bằng LLM + kiểm tra bảo toàn số | Public lệch ngôn ngữ; không có bước này thì giải thời gian hỏng trên ~35% câu public | (a) tỉ lệ câu train mà kỳ thời gian trích ra khớp kỳ trong chương trình kiểm chứng; (b) trên public: tỉ lệ câu trích được kỳ (không cần nhãn); (c) điểm leaderboard | 1 ngày | P3 |
| 5 | Batch vLLM theo business, prefix cache | Giảm thời gian chạy > 5×, mở đường cho N = 5 | Thời gian chạy 1000 câu public | 0,5 ngày | P4 |
| 6 | Code-gen gọi helper + rulebook nguyên văn trong prompt | Tốt hơn text-to-SQL trên bảng thô | PA trên fold giữ lại, so baseline | 1 ngày | P3 |
| 7 | Ngân hàng ví dụ kiểm chứng + BM25 few-shot | +0,05 đến +0,10 PA trên fold giữ lại | A/B có/không ví dụ; ví dụ chỉ lấy từ shop ngoài fold | 0,5 ngày | P3 |
| 8 | Gate unanswerable theo profile | Bắt ≥ 70% câu unanswerable với < 1% báo nhầm | Precision/recall trên 70 câu train + 2930 câu còn lại | 0,5 ngày | P3 |
| 9 | N = 5 biến thể prompt + bỏ phiếu + kiểm tra hợp lý + calibrate | +0,05 đến +0,12 PA so với trả lời hết | Đường cong PA theo ngưỡng trên fold giữ lại | 1 ngày | P4 |
| 10 | Helper tier B (khách, nhân viên, kênh, PTTT, thuốc) | +10% câu được phủ | Như #3 | 1 ngày | P2 |
| 11 | Diff rulebook → tắt helper | Tránh sai hệ thống khi luật đổi | Chạy fold train với rulebook public: helper `purchase_avg_price`, `stock_large_unit`, `sell_price` phải bị tắt; PA trên public leaderboard | 0,5 ngày | P3 |
| 12 | Helper tier C chọn lọc (price_effect, sell_price, purchase, unsold, gross_profit) | +8% câu được phủ | Như #3 | 1 ngày | P2 + P1 |
| 13 | Đường bảng tự do cho shop không dựng được ledger | Ngành mới không crash, có câu trả lời | Chạy dev_011–014: tỉ lệ thực thi thành công, tỉ lệ abstain; điểm leaderboard | 0,5 ngày | P3 + P1 |
| 14 | Đo tái lập: chạy image 2 lần | Số câu đổi đáp án < 1% | Đếm khác biệt giữa 2 lần chạy trên fold giữ lại | 0,25 ngày | P4 |
| 15 | Lượng tử hoá, 2 replica | Thông lượng ×2, PA giảm ≤ 0,01 | PA và thời gian trên fold giữ lại | 0,5 ngày | P4 |
| 16 | "Biên dịch rulebook lúc chạy" (§3.5) | Tăng PA trên luật mới | Leaderboard public, shop dev_011–014 | 1 ngày | P3, chỉ khi dư |
| 17 | A/B model code 14B | Có thể tốt hơn Qwen3-14B cho S4 | PA fold giữ lại | 0,5 ngày | P4, chỉ khi dư |

Không nằm trong backlog: LoRA; schema chung đầy đủ 9 bảng; plan JSON + interpreter.

---

## 6. Kế hoạch 5 ngày

Mốc cứng: **15/11 tối** nộp Docker bản an toàn (lượt 1/2). **16/11 trước 18:00** nộp bản cuối (lượt 2/2), dành 6 giờ cho upload Drive + checksum.

| Ngày | P1 — dữ liệu | P2 — metric + thời gian | P3 — LLM | P4 — eval, runtime, Docker |
|---|---|---|---|---|
| **11/11 (còn lại)** | Rà `cleaning.py`: phân loại các ngày/số chưa parse (biz_107, biz_117) | Chốt chữ ký helper (§3.3) với P3 | Prompt viết lại câu hỏi v0; chạy thử 200 câu public, xem bằng mắt | #1 harness + scorer; chấm baseline hiện tại |
| **12/11** | #2: mapping README + ledger cho 30 shop train; invariant | #3: bộ giải thời gian §2 đủ; `revenue`, `order_count`, `aov`, huỷ | #4 hoàn chỉnh; #6 prompt code-gen v1 với helper giả | #5 batch vLLM; sandbox thực thi; log đúng format |
| **13/11** | #2 xong cho 14 shop public (chỉ kiểm invariant, không nhãn); `profile_text` | #3 xong tier A; regression xanh | #6 chạy thật; #7 ngân hàng ví dụ; #8 gate unanswerable | Chạy đầu-cuối trên fold; **nộp public lượt đầu của pipeline mới** |
| **14/11** | Bảng phụ cho tier B/C: khách, nhập hàng, giá, thanh toán | #10 tier B; bắt đầu #12 | #11 diff rulebook; #13 đường bảng tự do | #9 bỏ phiếu + calibrate; #14 đo tái lập. **Cổng:** nếu PA fold < baseline thì họp cắt giảm |
| **15/11** | Sửa lỗi theo phân tích sai từng shop | #12 tier C chọn lọc; đóng băng thư viện 18:00 | Sửa prompt theo lỗi; đóng băng prompt 18:00 | Build Docker, chạy `--network none` trên public trọn vẹn, đo giờ. **Nộp Docker lượt 1** |
| **16/11** | Chỉ sửa lỗi crash | Chỉ sửa lỗi crash | Chỉ sửa lỗi crash | Calibrate lại ngưỡng lần cuối; build bản cuối; chạy 2 lần so đáp án; **nộp lượt 2 trước 18:00**; README khai báo model |

Lượt nộp public (5/ngày): mỗi ngày dành 1 lượt cho "trả lời hết, không abstain" để biết độ chính xác thô trên public, 1 lượt cho cấu hình có abstain, còn lại cho A/B một thay đổi mỗi lượt. Ghi nhật ký từng lượt.

---

## 7. Rủi ro và phương án dự phòng — trả lời câu 8

| # | Rủi ro | Dấu hiệu sớm | Giảm thiểu | Dự phòng |
|---|---|---|---|---|
| 1 | **Quá khớp train, vỡ ở ngành mới.** Train gần như toàn bán lẻ có sổ bán; private có ngành chưa thấy | PA fold "bỏ một ngành" thấp hơn hẳn fold thường; PA public trên dev_011–014 thấp | Pipeline không phụ thuộc ledger; rulebook nguyên văn; đường bảng tự do; đo riêng shop ngành mới | Nâng ngưỡng abstain cho shop không dựng được ledger: mất điểm cộng nhưng không âm |
| 2 | **Lỗi hệ thống ở tầng dữ liệu** kéo sai cả shop (private có 10–20 shop, nên mỗi shop chiếm khoảng 5–10% số câu) | Invariant fail; doanh thu tháng lệch đáp án ở regression | Invariant + regression từng shop; mapping từ README | Invariant fail thì abstain mọi câu tier A của shop đó thay vì trả lời sai hàng loạt |
| 3 | **Trễ tích hợp.** 4 module viết song song, ghép ngày cuối | 13/11 chưa chạy được đầu-cuối | Chốt interface hôm nay; helper giả từ ngày 12; chạy đầu-cuối hằng ngày từ 13/11 | Bản an toàn 15/11 = baseline text-to-SQL + `cleaning.py` + batch + abstain khi lỗi |
| 4 | **Chuẩn hoá câu hỏi làm hỏng câu** (đổi số, đổi tên hàng) | Kiểm tra bảo toàn số fail nhiều; PA giảm khi bật S2 trên train | Kiểm tra bảo toàn số; đưa cả câu gốc lẫn câu viết lại vào prompt S4 | Tắt viết lại, chỉ giữ bảng thay thế teencode xác định |
| 5 | **Không tái lập** (|ΔPA| > 0,03) hoặc **quá 6 giờ** | Hai lần chạy khác > 1% câu; chạy public > 3 giờ | Nhiệt độ 0, thứ tự cố định, ghi kết quả tăng dần, đồng hồ tổng | Hạ N xuống 1–3; tắt thinking cho câu có ví dụ rất gần |
| 6 | **Abstain sai ngưỡng**: calibrate trên train nhưng private khó hơn → trả lời quá nhiều câu sai | Tỉ lệ đồng thuận trên public thấp hơn hẳn trên fold | Calibrate theo ô (có helper / pandas thô), không dùng một ngưỡng chung; lấy biên 0,55 | Ngưỡng bảo thủ hơn cho câu không có helper |
| 7 | **Vi phạm luật** (logic theo id, dùng public để train, vượt 15B, weights sau 26/10) | Review code | Không có `business_id` trong nhánh if nào; ví dụ few-shot không chứa id; README liệt kê model + số tham số | — |
| 8 | **Docker/GPU**: vLLM không chạy trên Blackwell với base image đã ghim (`v0.10.1.1` trong Dockerfile hiện tại), hoặc image quá lớn để upload | Build/chạy thử lỗi | Thử image trên máy có GPU càng sớm càng tốt (12/11), đối chiếu base image trong PDF guideline | Backend transformers đã có trong `src/llm.py` làm đường lui (chậm hơn) |

**Rủi ro lớn nhất** là #1 cộng #3: dồn 5 ngày vào thư viện metric đẹp cho ngành đã thấy, ghép muộn, và không có số đo nào cho ngành mới trước khi đóng băng. Hai việc chống lại nó nằm ở ngày 13/11: chạy đầu-cuối trên fold và nộp public lượt đầu.

---

## Phụ lục: số liệu đã đếm và cách tái lập

| Số liệu | Giá trị | Cách đếm |
|---|---|---|
| Câu train / public | 3000 / 1000 | đếm dòng `questions.jsonl` |
| Shop train / public | 30 / 14 | thư mục `data/` |
| Câu theo shop (train) | 7 shop × 40 câu, 23 shop × 118–119 câu | Counter theo `business_id` |
| Câu theo shop (public) | 21 đến 129 câu | như trên |
| Câu không dấu | 25,8% train; 26,2% public | kiểm tra dấu thanh sau NFD |
| Kiểu kỳ thời gian (train) | tháng M/YYYY 1907; ngày dd/mm/yyyy 248; hôm nay 223; hôm qua 172; tháng này 152; tuần rồi 123; quý 79; N ngày gần nhất 46; tháng không năm 4 | regex trên câu bỏ dấu |
| Định dạng ngày kiểu mới (`T8/2025`, `8/26`, `6-2025`, `Q1`) | 0,0% train; 35,3% public | regex |
| Phương ngữ (mô, rứa, ni, nhứt, hen…) | 0,1% train; 5,8% public | regex |
| Unanswerable train | 70 câu, 12 shop có, 18 shop không | `answers.jsonl` |
| README có từ điển cột | 26/30 train; 11/14 public | tìm `## Cột trong` |
| Diff rulebook | public thêm ~30 dòng luật, bỏ 3, sửa 4 | `diff` hai file |
| Doanh thu tháng tính tay khớp đáp án | 24/24 câu, 6 shop | `scripts/analysis/revenue_check.py` + `src/cleaning.py` |

Script phân tích đã chuyển vào `scripts/analysis/`:

- `revenue_check.py` (trước là `revcheck.py`): kiểm doanh thu tháng trên train; mapping tay theo shop, chỉ dùng phân tích.
- `intent_tagger.py` (trước là `intent2.py`): bộ gán nhãn intent regex ~60 luật.
- `profile_raw.py`, `load_all.py`: xem cấu trúc thô và kết quả `load_business` của 44 shop.

Lần chạy lại ngày 11/11 sau khi chuyển: doanh thu tháng khớp 36/36 câu trên 8 shop.
