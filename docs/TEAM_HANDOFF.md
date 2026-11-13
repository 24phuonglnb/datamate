# Bàn giao nhóm DataMate (cập nhật 2026-11-13)

Tóm tắt: ai làm gì, branch nào chứa gì, chạy lệnh nào, số đo mới nhất, việc còn mở. Không có dữ liệu thi, đáp án hay câu hỏi trong tài liệu này.

## 1. Vai trò

| người | phần việc | nơi |
|---|---|---|
| Nhi | harness đánh giá, chuẩn hoá câu hỏi + `Period`, router (template trước LLM), bảo vệ dữ liệu/luật | `feat/real-data-eval`, `feat/question-normalization`, `feat/intent-router` |
| Phương | tích hợp, chạy 14B (TP=2), Docker, review và merge PR | `main`, branch của mọi người |
| Nghiệp | tầng dữ liệu, view, template SQL gốc | `feat/p3-data-cleaning` (`docs/VIEWS.md`) |
| An | prompt LLM theo `docs/VIEWS.md` cho phần router không xử lý | `src/agent.py` (đang viết lại) |

## 2. Branch nào chứa gì

| branch | nội dung | phụ thuộc |
|---|---|---|
| `docs/data-setup` | README "Dữ liệu chính thức", `scripts/download_data.sh`, `.gitignore` chặn `data/`, `*.zip`, `.env` | không |
| `feat/p3-data-cleaning` (Nghiệp) | làm sạch, ledger, view `v_*`, cache SQLite, `docs/VIEWS.md`, `scripts/analysis/rule_regression.py` | không |
| `feat/real-data-eval` | `eval/`: `run_baseline.py`, `pa_score.py` (chấm theo §9), `folds.json` (6 shop hold-out), mẫu 600 câu, `compare_runs.py`, `eval/README.md` | không (xung đột `.gitignore` nhỏ với `feat/p3-data-cleaning`) |
| `feat/question-normalization` | `src/nlu/normalize.py`, `src/timeutil.py` (§2 → `Period`), `Agent(normalizer=…)` tuỳ chọn, test | test cần `eval/folds.json` (đặt `ZAIC_FOLDS`); `scripts/validate_timeutil_templates.py` cần `feat/p3-data-cleaning` |
| `feat/intent-router` | `src/router/`, gọi trong `src/predict.py`, chế độ router-only, bảo vệ shop/luật/đáp án, `docs/ROUTER.md`, `docs/NLU_API.md`, `docs/ROUTER_BACKLOG.md`, `eval/run_baseline.py --router` | **xếp chồng**: đã merge sẵn 3 branch trên (diff so với `main` rất lớn cho tới khi chúng được merge) |
| `exp/legacy-vs-views` | kết quả 8B với nạp dữ liệu kiểu cũ trên shop hold-out; chỉ để tham khảo | không merge |

Thứ tự merge đề xuất (đã kiểm tra bằng `git merge-tree`, chỉ `.gitignore` xung đột, gộp tay được):
1. `docs/data-setup`
2. `feat/p3-data-cleaning`
3. `feat/real-data-eval` (giải `.gitignore`: giữ cả hai nhóm dòng)
4. `feat/question-normalization`
5. `feat/intent-router` (sau bước 1–4 diff chỉ còn phần router)

## 3. Lệnh chạy

Dữ liệu: `bash scripts/download_data.sh` (xem README). Cấu trúc `data/train/train/…`, `data/public_test/public_test/…`; trỏ `DATA_DIR`/`--train-dir` vào thư mục có `questions.jsonl`.

| việc | lệnh |
|---|---|
| đo 14B trên shop hold-out (agent) | `python -m eval.run_baseline --model-path <14B> --model-name Qwen3-14B --backend vllm --tensor-parallel-size 2 --subset holdout` |
| như trên nhưng có router | thêm `--router` (chỉ trên `feat/intent-router`) |
| so hai lần chạy | `python -m eval.compare_runs A.per_question.jsonl B.per_question.jsonl --show 10` |
| pipeline đầy đủ (router + LLM) | `bash predict.sh` (đọc `DATA_DIR`, `RESULT_DIR`, `MODEL_PATH`, `TP_SIZE`) |
| chỉ router, không model (image dự phòng) | `DATAMATE_ROUTER_ONLY=1 PYTHONPATH=/code python -m src.predict --data-dir /data --result-dir /result` |
| đo router trên train (CPU) | `python scripts/eval_router.py --train-dir data/train/train --fold dev` (hold-out chỉ chạy một lần khi chốt) |
| kiểm tra bất biến shop (CPU) | `python scripts/data_invariants.py report --data-dir <dir>` |
| so rulebook đang chạy với bản train | `python scripts/build_rule_reference.py diff --rulebook <rulebook.md>` |
| test | `ZAIC_FOLDS=eval/folds.json pytest tests` |

Biến môi trường của router (`DATAMATE_ROUTER`, `DATAMATE_ROUTER_ONLY`, `DATAMATE_CACHE_DIR`, `DATAMATE_LEGACY_INGESTION`, …): `docs/ROUTER.md`.
Image router-only: không cần weights, không cần GPU; cần `requirements.txt` hiện có (pandas, openpyxl; `torch/vllm` chỉ nạp khi chạy có model).
Đo trên public (1000 câu, một tiến trình CPU): 8 phút 24 giây, bộ nhớ đỉnh khoảng 0,75 GB (bản `98205ca`; lần đầu mỗi shop còn tính bất biến).

## 4. Số đo mới nhất

PA = (đúng − sai) / số câu; abstain 0 điểm. Chi tiết và nguồn: `docs/EXPERIMENTS.md` trên `feat/intent-router`.

| mốc | tập | PA |
|---|---|---|
| baseline Qwen3-8B (agent gốc) | mẫu 600 câu train | −0,407 |
| baseline 8B, nạp dữ liệu kiểu cũ | 709 câu hold-out | −0,409 |
| router (cận dưới: phần router trả lời, còn lại abstain) | hold-out | 0,42 → 0,478 (sau khi thêm intent), đúng 339/339 câu router trả lời |
| bảng xếp hạng v1, router-only | public 1000 câu | 0,165 (221 câu trả lời, 193 đúng) |
| bảng xếp hạng, v1 bỏ 28 câu của dev_004 | public | 0,151 |

Đính chính: dev_004 không có lỗi parse ngày. Cảnh báo "54% ngày không parse" trước đây là do bộ đếm cũ tính cả ô ngày để trống rồi được điền xuống theo đơn; `6ae1a0e` của Nghiệp đã sửa bộ đếm.

## 5. Việc còn mở

| việc | ai | ghi chú |
|---|---|---|
| quyết định dòng luật `1|don thuoc ky nao` (bản public thêm: đơn trả sau kỳ vẫn bị loại) | Nhi | dòng này đang tắt; **chừng nào chưa duyệt, router tắt mọi intent trên public và bản router-only trả lời 0/1000 câu**. Đã kiểm trên dev: 6041 đơn trả hàng, 0 đơn nằm trong `v_valid_orders`; dữ liệu train không có cột ngày trả nên chưa đếm được "trả sau kỳ" |
| 14B TP=2, đo hold-out có/không `--router`, Docker | Phương | chọn bản nộp trước 16/11 |
| prompt LLM cho phần router không xử lý | An | `docs/ROUTER_BACKLOG.md` (nhóm intent, view cần dùng, độ khó, luật chỉ có ở rulebook public); agent hiện nhận câu gốc, không nhận `Period`/câu chuẩn hoá (đề xuất interface trong `docs/ROUTER.md`) |
| duyệt mã router copy từ code của Nghiệp | Nghiệp | `src/router/templates.py`, `_tagger_rules.py`, regex trong `intents.py` |
| view còn thiếu: nhập hàng, tồn kho, lô/hạn dùng, công nợ theo ngày, giá vốn/chi phí | Nghiệp | bảng số câu ở `docs/ROUTER_BACKLOG.md` |
| 2 test `tests/test_rule_regression.py` fail (đòi cấu trúc `data/train/data/…`); test rò rỉ kết nối phụ thuộc thứ tự | Nghiệp | xem `docs/ROUTER_BACKLOG.md` |
| lớp LLM chuẩn hoá câu (teencode/không dấu) chưa làm; ablation chuẩn hoá chưa đo | Nhi | |
