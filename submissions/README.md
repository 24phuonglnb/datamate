# submissions/

File `submission.jsonl` đã tạo cho leaderboard public_test (1000 dòng, mỗi dòng `{"id","type",...}` theo rulebook mục 9) và nhật ký `LOG.md`.
Branch này chỉ để lưu vết, không merge vào main. Không đưa vào đây dữ liệu thi, weights, token hay log chạy.

## Thêm một lượt nộp
1. Chép file vào `submissions/`, tên `<mô_tả>_<YYYY-MM-DD>.jsonl`. Một file một lượt, không ghi đè file cũ.
2. Kiểm tra: `python scripts/validate_submission.py submissions/<file> <public_test>/questions.jsonl` (đủ id, không trùng, đúng định dạng từng dòng; script không kiểm thứ tự dòng, hãy so với `questions.jsonl` nếu cần).
3. Đếm answered / abstain / unanswerable từ chính file (không lấy từ log chạy):
   ```bash
   python -c "import json,sys,collections as C; c=C.Counter(json.loads(l)['type'] for l in open(sys.argv[1],encoding='utf-8') if l.strip()); print(sum(c.values())-c['abstain']-c['unanswerable'], c['abstain'], c['unanswerable'])" submissions/<file>
   ```
4. Thêm một dòng vào `LOG.md`: số thứ tự kế tiếp, thời gian nộp, người nộp, `branch@commit` đã chạy (`git rev-parse --short HEAD`), lệnh/cờ chạy, ba số ở bước 3, mô tả ngắn. Cột điểm để `?` cho tới khi có điểm leaderboard, rồi sửa lại; file chưa nộp thì ghi vào bảng "Chưa nộp".
5. Commit chỉ file jsonl và `LOG.md`, push branch `submissions`.
