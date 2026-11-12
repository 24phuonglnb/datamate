# Experiments log

One row per experiment. PA = point average (+1/-1/0, rulebook section 9). Scorer: `eval/pa_score.py`
(percent mode `strict`) until the official `score.py` is available.

| date | branch | model | question set | PA | notes |
|---|---|---|---|---|---|
| 2026-11-11 | feat/real-data-eval | Qwen3-8B | sample 600 (dev 480 / hold-out 120) | -0.4067 (dev -0.406, hold-out -0.408) | baseline agent, unchanged; correct 3.2%, abstain 53%, wrong 43.8%; 20.6 s/question; report `eval/reports/2026-11-11_Qwen3-8B.md` |
