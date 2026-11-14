# NLU API: chuẩn hoá câu hỏi và khoảng thời gian

Mã: `src/nlu/normalize.py`, `src/timeutil.py`. Chỉ dùng luật (không model, không GPU). Ví dụ dưới đây là câu tổng hợp.

## `normalize(question, as_of, calendar=None, short_slash=None, tet_bare=True) -> NormalizedQuestion`

`RuleNormalizer(calendar_path=None, short_slash=None, tet_bare=True)` là callable `(question, as_of) -> NormalizedQuestion`
(gói sẵn lịch âm). `as_of` là `as_of_date` của câu hỏi (chuỗi `YYYY-MM-DD`).

| trường | ý nghĩa |
|---|---|
| `text` | câu đã chuẩn hoá: NFC, sửa telex/teencode theo từ điển dev (`src/nlu/resources/*.json`); số và tên riêng giữ nguyên |
| `original` | câu gốc |
| `period` | `ResolveResult` (bên dưới): các khoảng thời gian đã giải theo rulebook §2 |
| `entities` | `{"numbers": [...], "dates": [...], "quoted": [...]}` trích từ câu gốc |
| `flags` | `no_diacritics`, `partial_no_diacritics`, `residual_teencode` (còn teencode/không dấu sau luật) |
| `changes` | danh sách `(từ gốc, từ đã sửa)` |
| `needs_llm` | `True` nếu `flags` có cờ ở trên: lớp LLM (chưa làm) sẽ viết lại; router chuyển câu `residual_teencode` xuống agent |

## `resolve(text, as_of, calendar=None, short_slash=None, tet_bare=True) -> ResolveResult`

Làm việc trên văn bản bỏ dấu, nên dùng được cho câu không dấu/teencode nhẹ.

| trường `ResolveResult` | ý nghĩa |
|---|---|
| `periods: list[Period]` | các khoảng được nêu, theo thứ tự xuất hiện |
| `comparison: Period or None` | kỳ so sánh khi câu có "so với / tăng hay giảm / cùng kỳ" |
| `part_of_day: dict or None` | `{"sang": ("06:00","13:59"), "chieu": ("14:00","21:59"), "baseline": "sang"}` (ca sáng/chiều, §2) |
| `ambiguous: list[dict]` | biểu thức không giải được (`text`, `reason`, `candidates`); KHÔNG sinh Period cho chúng |

`Period` (dataclass, bất biến): `start: date | None` (None = từ đầu dữ liệu, dùng cho "đến hết ngày X"), `end: date`,
`granularity`, `rule_refs` (các dòng rulebook áp dụng), `source` (đoạn chữ gốc).

`granularity`: `day`, `week`, `week_to_date`, `month`, `month_to_date`, `month_series`, `quarter`, `year`, `year_to_date`,
`rolling` (N ngày gần nhất), `range` (từ X đến Y), `cumulative` (đến hết ngày X), `tet`.

Hàm phụ: `Period.where_sql(date_col="order_date", time_col="order_time", part_of_day=None)` sinh điều kiện lọc
(`order_date BETWEEN '…' AND '…'`; `start=None` chỉ có cận trên; ca sáng/chiều thêm điều kiện giờ trên `substr(order_time,1,5)`);
`previous_period(p, as_of)` (kỳ trước theo §1); `format_for_prompt(res)` (khối chữ cho prompt).

Ví dụ với `as_of = 2026-09-07`:

| câu | kết quả |
|---|---|
| "doanh thu hôm nay" | `day 2026-09-07..2026-09-07` |
| "tuần rồi" | `week 2026-08-31..2026-09-06` (thứ Hai–Chủ nhật) |
| "tháng này so với tháng trước" | `month_to_date 2026-09-01..2026-09-07`, `comparison` = cùng số ngày của tháng trước |
| "7 ngày gần nhất" | `rolling 2026-09-01..2026-09-07` |
| "đến hết ngày 20/09/2025" | `cumulative start=None end=2025-09-20` |
| "ca chiều tháng 4/2026" | `month 2026-04-01..2026-04-30`, `part_of_day = chieu` |
| "tháng 6/25" | `month 2025-06-01..2025-06-30` |

`format_for_prompt(res)` cho ví dụ đầu: `- "hom nay": 2026-09-07 → 2026-09-07 (day; §2 Ngày X, hôm nay, hôm qua)`. Khối này được
Agent chèn dưới tiêu đề `RESOLVED TIME PERIODS (rulebook section 2; use exactly these dates)` khi `Agent(..., normalizer=...)`.

## Quy ước (đã chốt)

- Tháng/quý không ghi năm: năm nay nếu không sau hôm nay, sau hôm nay thì năm trước (§2).
- `a/b` hai phần: có "ngày" đứng trước → ngày a tháng b; có "tháng" → tháng a năm 20b (chỉ 20 ≤ b ≤ 39); không từ khoá:
  b ≤ 12 → ngày a tháng b, 20 ≤ b ≤ 39 → tháng a năm 20b; còn lại (13–19, ≥ 40) → `ambiguous`.
- "Tết" không ghi năm: Tết gần nhất đã bắt đầu (23 tháng Chạp) trước hoặc đúng `as_of`, tra `calendar.csv`; nếu rulebook đang chạy
  không có dòng Tết hoặc lịch không phủ thì `ambiguous` (`tet_bare=False` ép như vậy).
- Biểu thức không chắc chắn không được đoán: nó nằm trong `ambiguous` và router chuyển câu xuống agent.
