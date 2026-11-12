# Baseline report — Qwen3-8B-legacy — holdout_all — 2026-11-12

- PA: **-0.4090**, accuracy 0.0353, abstain 0.5205, wrong 0.4443 (n=709)
- Answered precision (correct / answered): 0.0735; answered rate 0.4795
- Timing: load 15.9 s, 20.97 s/question mean (includes ~15 s workbook ingest on the first question of each shop), median 15.94 s, p95 56.48 s
- Percent comparison mode in pa_score: `strict`

### By fold

| key | n | PA | acc | abstain | wrong |
|---|---|---|---|---|---|
| holdout | 709 | -0.409 | 0.035 | 0.520 | 0.444 |

### By gold type

| key | n | PA | acc | abstain | wrong |
|---|---|---|---|---|---|
| boolean | 5 | -0.200 | 0.200 | 0.400 | 0.400 |
| date | 28 | -0.500 | 0.000 | 0.500 | 0.500 |
| list | 62 | -0.597 | 0.048 | 0.306 | 0.645 |
| number | 451 | -0.497 | 0.020 | 0.463 | 0.517 |
| percent | 123 | -0.130 | 0.000 | 0.870 | 0.130 |
| string | 17 | -0.235 | 0.059 | 0.647 | 0.294 |
| table | 7 | -0.571 | 0.000 | 0.429 | 0.571 |
| unanswerable | 16 | 0.625 | 0.688 | 0.250 | 0.062 |

### By intent (regex)

| key | n | PA | acc | abstain | wrong |
|---|---|---|---|---|---|
| cong_no | 52 | -0.211 | 0.038 | 0.712 | 0.250 |
| doanh_thu | 284 | -0.440 | 0.021 | 0.518 | 0.461 |
| gia_tang_gia | 34 | -0.176 | 0.000 | 0.824 | 0.176 |
| huy_tra | 61 | -0.607 | 0.000 | 0.393 | 0.607 |
| khac | 118 | -0.424 | 0.068 | 0.441 | 0.491 |
| loi_nhuan | 7 | 0.000 | 0.000 | 1.000 | 0.000 |
| nhap_hang | 5 | 0.000 | 0.000 | 1.000 | 0.000 |
| so_don | 44 | -0.568 | 0.068 | 0.295 | 0.636 |
| so_sanh_ky | 46 | -0.065 | 0.022 | 0.891 | 0.087 |
| ton_kho | 9 | -0.333 | 0.111 | 0.444 | 0.444 |
| xep_hang | 49 | -0.612 | 0.082 | 0.225 | 0.694 |

### By shop

| key | n | PA | acc | abstain | wrong |
|---|---|---|---|---|---|
| biz_102 | 119 | -0.571 | 0.000 | 0.429 | 0.571 |
| biz_109 | 118 | -0.364 | 0.042 | 0.551 | 0.407 |
| biz_112 | 118 | -0.449 | 0.059 | 0.432 | 0.508 |
| biz_116 | 118 | -0.483 | 0.009 | 0.500 | 0.491 |
| biz_123 | 118 | -0.093 | 0.017 | 0.873 | 0.110 |
| biz_129 | 118 | -0.491 | 0.085 | 0.339 | 0.576 |
