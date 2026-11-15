# Nhật ký các lượt nộp (leaderboard public_test, 1000 câu)

Số answered / abstain / unanswerable được đếm từ chính file jsonl (cách đếm trong README). Thời gian là giờ tạo file gốc trên server (không phải giờ nộp). Dấu `?` = chưa có thông tin, ai biết thì điền; điểm chỉ ghi khi đã có số từ leaderboard.

| # | Thời gian (tạo file, +07) | Người nộp | branch@commit | Cờ chạy | answered / abstain / unanswerable | Điểm public | Mô tả | File |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-11-13 01:27 | ? | feat/intent-router@? | ? | 221 / 779 / 0 | 0.165 | Router-only v1 (221 answered: 193 đúng / 28 sai theo EXPERIMENTS) | `router_only_2026-11-13.jsonl` |
| 2 | 2026-11-13 02:24 | ? | feat/intent-router@? | scripts/make_probes.py (nhóm G1) | 90 / 910 / 0 | ? | File dò leaderboard; chưa rõ đã nộp chưa và điểm | `probe_G1_2026-11-13.jsonl` |
| 3 | 2026-11-13 02:24 | ? | feat/intent-router@? | scripts/make_probes.py (nhóm G2) | 63 / 937 / 0 | ? | File dò leaderboard; chưa rõ đã nộp chưa và điểm | `probe_G2_2026-11-13.jsonl` |
| 4 | 2026-11-13 02:24 | ? | feat/intent-router@? | scripts/make_probes.py (v1 bỏ shop bị cờ) | 162 / 838 / 0 | ? | File dò leaderboard; chưa rõ đã nộp chưa và điểm | `probe_v1_minus_flagged_2026-11-13.jsonl` |
| 5 | 2026-11-13 02:57 | ? | feat/intent-router@? | scripts/make_probes.py (v1 bỏ 28 câu dev_004) | 193 / 807 / 0 | 0.151 | v1 bỏ 28 câu của dev_004: dev_004 đóng góp +14 net (khoảng 21 đúng / 7 sai) | `probe_v1_minus_dev004_2026-11-13.jsonl` |
| 6 | 2026-11-13 14:11 | ? | feat/intent-router@? | router-only, guard rulebook theo ý chính (`--guard`?) | 265 / 735 / 0 | 0.195 | Router-only v2: 45 câu mới, 1 câu bị bỏ (new-rule cue) so với v1 | `router_v2_2026-11-13.jsonl` |
| 7 | 2026-11-13 15:15 | ? | feat/intent-router@b1b48b6 (ước: commit cuối trước 15:15 ngày 13/11) | router-only | 301 / 699 / 0 | 0.213 | Router-only v3: thêm best_month, monthly_series, streak_bool, cust_group_rev, payment/channel, unit_total_qty | `router_v3_2026-11-13.jsonl` |
| 8 | 2026-11-14 23:54 | ? | feat/router-pharmacy@a414011 | `python scripts/make_router_submission.py --data-dir <public_test> --out <file> --guard`, router-only, không GPU | 319 / 679 / 2 | 0.229 | Router-only v4: thêm 11 template hoạt chất/kê đơn, nhập hàng, tồn kho/lô | `router_v4_2026-11-14.jsonl` |
