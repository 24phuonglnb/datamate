# Nhật ký các lượt nộp (leaderboard public_test, 1000 câu)

Số answered / abstain / unanswerable được đếm từ chính file jsonl (cách đếm trong README). Thời gian là giờ nộp (+07). Dấu `?` = chưa có thông tin, ai biết thì điền.

| # | Thời gian nộp | Người nộp | branch@commit | Cờ chạy | answered / abstain / unanswerable | Điểm public | Mô tả | File |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-11-13 01:46 | Trịnh Tố Thảo Nhi | feat/intent-router@? | ? | 221 / 779 / 0 | 0.165 | Router-only v1 (221 answered: 193 đúng / 28 sai theo EXPERIMENTS) | `router_only_2026-11-13.jsonl` |
| 2 | 2026-11-13 03:41 | Trịnh Tố Thảo Nhi | feat/intent-router@? | scripts/make_probes.py (v1 bỏ 28 câu dev_004) | 193 / 807 / 0 | 0.151 | Probe: v1 bỏ 28 câu của dev_004; dev_004 đóng góp +14 net (khoảng 21 đúng / 7 sai) | `probe_v1_minus_dev004_2026-11-13.jsonl` |
| 3 | 2026-11-13 14:29 | Trịnh Tố Thảo Nhi | feat/intent-router@? | router-only, guard rulebook theo ý chính | 265 / 735 / 0 | 0.195 | Router-only v2: 45 câu mới, 1 câu bị bỏ (new-rule cue) so với v1 | `router_v2_2026-11-13.jsonl` |
| 4 | 2026-11-13 22:06 | Trịnh Tố Thảo Nhi | feat/intent-router@? | router-only | 301 / 699 / 0 | 0.213 | Router-only v3: thêm best_month, monthly_series, streak_bool, cust_group_rev, payment/channel, unit_total_qty | `router_v3_2026-11-13.jsonl` |
| 5 | 2026-11-14 23:56 | Trịnh Tố Thảo Nhi | feat/router-pharmacy@a414011 | `python scripts/make_router_submission.py --data-dir <public_test> --out <file> --guard`, router-only, không GPU | 319 / 679 / 2 | 0.229 | Router-only v4: thêm 11 template hoạt chất/kê đơn, nhập hàng, tồn kho/lô | `router_v4_2026-11-14.jsonl` |
| 6 | 2026-11-15 | Phương | feat/selective-llm-fallback@? | router + Qwen3-14B + selective fallback (`DATAMATE_SELECTIVE_FALLBACK=1`), không gate | ? | 0.113 | Router + LLM, điểm thấp hơn router-only v4 (0.229) | file: chờ Phương |
| 7 | 2026-11-15 (tạo file; chưa nộp) | ? | feat/router-expansion@2915ea8 (PR #11) | `DATAMATE_ROUTER_ONLY=1 python -m src.predict --data-dir <public_test> --result-dir <dir>` (router-only, không GPU; file sắp lại theo thứ tự questions.jsonl) | 433 / 565 / 2 | ? (chưa nộp) | v6 router-only \| feat/router-expansion@2915ea8 (PR #11) \| + shift, price_effect, category_share, size_qty, unsold_count, days_over_threshold, cust_freq, staff_revenue; mở rộng payment/channel/item_qty \| dev 1824/2291 đúng hết | `router_v6_2026-11-15.jsonl` |

## Chưa nộp

File dò leaderboard đã tạo nhưng chưa nộp (không có điểm).

| Thời gian tạo file | branch@commit | Cờ chạy | answered / abstain / unanswerable | Điểm public | Mô tả | File |
|---|---|---|---|---|---|---|
| 2026-11-13 02:24 | feat/intent-router@? | scripts/make_probes.py (nhóm G1) | 90 / 910 / 0 | chưa nộp | Probe G1 | `probe_G1_2026-11-13.jsonl` |
| 2026-11-13 02:24 | feat/intent-router@? | scripts/make_probes.py (nhóm G2) | 63 / 937 / 0 | chưa nộp | Probe G2 | `probe_G2_2026-11-13.jsonl` |
| 2026-11-13 02:24 | feat/intent-router@? | scripts/make_probes.py (v1 bỏ shop bị cờ) | 162 / 838 / 0 | chưa nộp | Probe v1 bỏ các shop bị cờ | `probe_v1_minus_flagged_2026-11-13.jsonl` |
