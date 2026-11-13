# Router: trả lời bằng template trước, LLM cho phần còn lại

Mã: `src/router/` (gọi từ `src/predict.py` qua `src/router/pipeline.py`, trước `agent.py`; `agent.py` không bị sửa).
Chỉ dùng luật + SQL trên view của tầng dữ liệu, không model, không GPU. Quy ước thời gian và `Period`: xem `docs/NLU_API.md`.

## Luồng một câu hỏi

```
question ──► RuleNormalizer (text chuẩn hoá, Period) ──► shop guard ──► Router.route ──► template / unanswerable
                                                           │                  └─ abstain (có lý do) / llm
                                                           └─ shop có cờ → abstain cả shop      llm → agent.solve(question gốc)
```

Mỗi câu ghi `log["router"] = {route, reason, intent, params, shop_warnings?}` vào `/result/logs/questions.jsonl`.
`route`: `template` (đáp án từ SQL), `unanswerable` (§7), `abstain` (router tự bỏ trống, KHÔNG gọi LLM), `llm` (chuyển cho agent).

## Intent do router xử lý (độ chính xác dev/hold-out: 100%, xem `eval/reports/2026-11-13_router_*.md`)

| intent | kiểu đáp án | ghi chú |
|---|---|---|
| `revenue` | number | `v_valid_orders`, kỳ theo ngày đặt |
| `order_count` | number | kèm biến thể ngưỡng "doanh thu từ X đồng trở lên" (`order_count_threshold`); so sánh ngặt (trên/dưới) → agent |
| `cancel_count`, `cancel_rate` | number, percent | `v_orders`, mọi trạng thái; rate làm tròn 2 chữ số |
| `aov` | number | làm tròn nửa lên |
| `best_day` | date `YYYY-MM-DD` | |
| `topk_items`, `best_item` | list, string | theo `qty_base`, hoà theo mã |
| `item_qty` | number | chỉ khi đơn vị hỏi = đơn vị cơ bản của mặt hàng |
| `rev_change_pct` | percent | kỳ hỏi và kỳ so (từ `Period`) |
| `item_revenue`, `category_rev` | number | mới (template của Nhi, cần Nghiệp duyệt) |
| `sell_price_on_day` | number | giá một đơn vị cơ bản ngày D, `v_lines`; nhiều giá/không có đơn → agent |
| `best_month` | date `YYYY-MM` | tháng có doanh thu lớn nhất trong các tháng được nêu; hoà → agent |
| `monthly_series` | list (int) | doanh thu từng tháng, từ tháng cũ đến mới |
| `streak_bool` | boolean | doanh thu tăng liên tục qua các tháng theo thứ tự nêu |
| `cust_group_rev` | number | `v_valid_orders.customer_group`, tên nhóm sau chữ "nhóm" |
| `payment_method_rev`, `channel_rev` | number | đúng một hình thức/kênh được nêu (tiền mặt/chuyển khoản/ví/COD/ghi nợ; tại quầy/Zalo OA/điện thoại); nhiều giá trị hoặc phần trăm → agent |
| `unit_total_qty` | number | tổng `qty_base` mọi mặt hàng có đơn vị cơ bản = đơn vị hỏi; nêu tên mặt hàng → agent |
| câu chủ quan (hay khen, lễ phép…) | unanswerable | §7 |
| kỳ nằm hoàn toàn trước dữ liệu của shop | unanswerable | §7 |

Mọi intent khác (ca, tăng giá, nhóm hàng chiếm %, nhập hàng, tồn kho, công nợ, khách…) đi xuống agent:
danh sách theo số câu, view cần dùng và độ khó nằm ở `docs/ROUTER_BACKLOG.md` (backlog chia cho An và Nghiệp).

Router KHÔNG trả lời (chuyển xuống agent) khi: intent ngoài danh sách (`not_target:<nhãn>`), có bộ lọc phụ (`extra_filter_or_subintent`),
trùng nhiều intent (`multi_intent`), còn teencode (`normalizer_residual_teencode`), Period thiếu/mơ hồ/nhiều (`period_missing`,
`period_ambiguous`, `period_count`), không khớp tên hàng/nhóm (`item_not_found`, `category_not_found`), sai đơn vị (`unit_mismatch`),
luật bị mất/mâu thuẫn (`rulebook_guard:<intent><-<lý do>`), câu chứa cue của luật mới (`new_rule_cue:<dòng>`).
Router tự `abstain` khi: shop có cờ dữ liệu (`shop_low_confidence`), kỳ giao với ngày không parse được
(`period_overlaps_unparsed_dates`), đáp án không hợp lý (`sanity:<luật>`).

## Các lớp bảo vệ

| lớp | file | làm gì |
|---|---|---|
| bất biến shop | `invariants.py`, `invariant_thresholds.json` | tỉ lệ trạng thái lạ, đơn vị chưa quy đổi, tháng DT ≤ 0, dòng trùng so với mức tệ nhất của 30 shop train → cả shop abstain; `amount_ratio` chỉ cảnh báo; shop không dựng được view (`no_ledger`) → router bỏ qua, agent xử lý như cũ |
| ngày không parse | `invariants.py` | ô ngày không rỗng parse lỗi (kể cả khi đã có năm sheet; bỏ dòng tổng cộng) → chỉ câu có Period giao với khoảng đó abstain |
| luật đổi | `rule_guard.py`, `rule_specs.py`, `rule_reference.json` | **tự động, không cần người duyệt.** Mỗi dòng rulebook mà một template dùng có "ý chính" (cụm từ không dấu, có biến thể) và "cụm mâu thuẫn" trong `rule_specs.py`. Intent chỉ bị tắt khi dòng nó dùng **mất**, **không còn ý chính**, hoặc **có cụm mâu thuẫn**; thêm câu/ví dụ/dòng mới thì không tắt. Dòng chỉ có trong rulebook đang chạy (so tên với băm của rulebook train) tạo "cue": câu chứa các từ của tên dòng theo thứ tự và gần nhau chuyển xuống agent (`new_rule_cue`). `reviewed_rule_changes.json` chỉ là sổ ghi chú, không ảnh hưởng quyết định |
| hợp lý đáp án | `sanity.py` | percent, cancel_rate 0–100, AOV trong [min,max] giá trị đơn, ngày trong kỳ, tên có trong `v_items`, số không âm |

## Chạy

Biến môi trường (tất cả tuỳ chọn):

| biến | tác dụng |
|---|---|
| `DATA_DIR`, `RESULT_DIR` | thư mục dữ liệu (có `questions.jsonl`, `rulebook.md`, `calendar.csv`, `data/<shop>/`) và thư mục kết quả (mặc định `/data`, `/result`) |
| `MODEL_PATH`, `TP_SIZE`, `MAX_ATTEMPTS` | model LLM, tensor-parallel, số lần thử của agent (`predict.sh` đã đọc) |
| `DATAMATE_ROUTER=0` | tắt router (chạy như baseline) |
| `DATAMATE_ROUTER_ONLY=1` | không nạp model; câu router không trả lời thì abstain |
| `DATAMATE_CACHE_DIR` | thư mục cache SQLite theo shop (mặc định `/tmp/datamate_cache`) |
| `DATAMATE_NO_CACHE=1` | không dùng cache đĩa |
| `DATAMATE_LEGACY_INGESTION=1` | nạp dữ liệu kiểu cũ, không có view (router không áp dụng được) |
| `DATAMATE_LLM_GATE=<json>` | bật cổng abstain cho câu rơi xuống LLM (mặc định tắt: LLM trả lời hết) |
| `DATAMATE_REVIEWED_RULES=<json>` | chỉ để phân tích: thay sổ ghi chú `reviewed_rule_changes.json` (không đổi quyết định) |

Pipeline đầy đủ (router + LLM): `bash predict.sh` (hoặc `python -m src.predict --data-dir … --result-dir … --model-path … --tensor-parallel-size 2`).

Chỉ router, không model (image dự phòng):

```bash
DATAMATE_ROUTER_ONLY=1 DATAMATE_CACHE_DIR=/tmp/dm_cache PYTHONPATH=/code \
  python -m src.predict --data-dir /data --result-dir /result
# hoặc: python -m src.predict --router-only ...
```

Ghi `/result/submission.jsonl` (đủ mọi id; câu không trả lời là `{"id","type":"abstain"}`) và `/result/logs/questions.jsonl`.
Thời gian: 751 giây cho 1000 câu public trên một tiến trình CPU (bản v1); số đo bản hiện tại ở `docs/TEAM_HANDOFF.md`.
Thư viện: chỉ `pandas` (kéo theo `numpy`) và `openpyxl` (đã có trong `requirements.txt`); `torch/vllm` chỉ được nạp khi chạy có model.

Công cụ CPU: `scripts/eval_router.py` (đo trên train, `--fold dev|holdout|both`), `scripts/data_invariants.py` (derive/report),
`scripts/build_rule_reference.py` (build/diff rulebook: in intent bị tắt và lý do, dòng đổi/mất/mới), `scripts/make_router_submission.py` (bản nộp router-only từ public, có `--guard`),
`scripts/make_probes.py` (file dò leaderboard).

## Agent nhận gì từ router (cho An): `hints`

Câu rơi xuống agent (route `llm`) được gọi qua `pipeline.call_agent(agent, question, hints)`:

- Nếu `agent.solve` có tham số `hints` (hoặc `**kwargs`) → `agent.solve(question, hints=hints)`.
- Nếu không → `agent.solve(question)` như cũ (agent hiện tại không đổi gì). Chữ ký được kiểm bằng `inspect`, không bắt `TypeError`,
  để lỗi thật bên trong một lần gọi model chậm không bị coi là "không có hints" và gọi lặp lại.

`question` vẫn là dict gốc của `questions.jsonl` (câu gốc). `hints` (JSON thường, mọi trường có thể rỗng):

| trường | nội dung |
|---|---|
| `normalized_text` | câu đã chuẩn hoá (`NormalizedQuestion.text`) |
| `period` | danh sách `{start, end, granularity, source}`; `start = null` cho "đến hết ngày X" (xem `docs/NLU_API.md`) |
| `comparison_period` | kỳ so sánh cùng dạng, hoặc `null` |
| `part_of_day` | `{sang: [..], chieu: [..], baseline}` hoặc `null` |
| `where_sql` | `[{period, sql}]`: điều kiện lọc sẵn trên `order_date` (và `order_time` nếu có ca một phía) cho từng kỳ + kỳ so sánh |
| `ambiguous_period` | các đoạn chữ thời gian không giải được (agent tự xử lý hoặc abstain) |
| `flags` | cờ chuẩn hoá (`no_diacritics`, `partial_no_diacritics`, `residual_teencode`) |
| `entities` | `numbers`, `dates` trích từ câu gốc; `item` `{item_code, item_name, base_unit}` và `category` nếu khớp duy nhất trong `v_items` |
| `fallthrough_reason`, `fallthrough_intent` | vì sao router không trả lời (ví dụ `not_target:stock_qty`, `extra_filter_or_subintent`) và intent nếu có |

Mẫu cho An:

```python
def solve(self, question, hints=None):
    hints = hints or {}
    period_sql = "; ".join(w["sql"] for w in hints.get("where_sql", []))
    text = hints.get("normalized_text") or question["question"]
```

Mã: `src/router/hints.py` (xây hints), `src/router/pipeline.py` (`call_agent`). `Agent(..., normalizer=…)` của branch
`feat/question-normalization` vẫn là đường riêng (không bật trong `predict.py`).

## Cổng abstain cho LLM (`llm_gate.json`)

Mặc định LLM trả lời mọi câu rơi xuống (để đo được). Khi đã có kết quả đo 14B trên hold-out:

```bash
python -m eval.run_baseline --model-path <14B> --model-name Qwen3-14B --backend vllm --tensor-parallel-size 2 --subset holdout --router
python -m eval.llm_gate --per-question eval/reports/<date>_Qwen3-14B_holdout_router.per_question.jsonl --fold holdout --out src/router/llm_gate.json
DATAMATE_LLM_GATE=src/router/llm_gate.json bash predict.sh      # bật cổng
```

`eval/llm_gate.py` gom theo "loại câu" (nhãn tagger của câu không thuộc intent router, hoặc intent router, hoặc lý do rơi xuống), tính số câu,
số câu đã trả lời, độ chính xác = đúng / đã trả lời và PA nếu bật. Bật khi đã trả lời ≥ 10 câu và độ chính xác ≥ 0,6; còn lại (kể cả loại câu
chưa thấy trong lần đo) abstain. Câu bị chặn ghi `route=abstain`, `reason=llm_gate:<loại>`. Chưa có đầu ra 14B thật nên chưa có `llm_gate.json`;
chạy lệnh trên khi có.

## Mã copy từ code của Nghiệp (cần Nghiệp duyệt)

- `src/router/templates.py`: `SQL_TEMPLATES` (10 câu SQL) copy nguyên văn từ `scripts/analysis/rule_regression.py`; thêm 5 template của Nhi (`item_revenue_*`, `category_revenue`, `price_on_day_*`).
- `src/router/_tagger_rules.py`: `deacc`, `U`, `HOWMANY`, `RULES` copy nguyên văn từ `scripts/analysis/intent_tagger.py`.
- `src/router/intents.py`: các regex "bộ lọc phụ" (`_SKIP`, `_ITEM_REV*`) lấy từ `should_skip_question`; `topk_k`, `match_item` theo `rule_regression.py`.
