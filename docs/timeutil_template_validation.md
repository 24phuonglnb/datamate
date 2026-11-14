# timeutil vs gold on the data-layer template group

Questions selected by rule_regression.py: 942; answered correctly with the timeutil Period filter: **942/942 = 100.00%**; timeutil returned no period: 0.
SQL filter actually rewritten from the Period: 942/942.
Periods differing from rule_regression's own (single-period intents): 0.

| group | n | correct | % | no period |
|---|---|---|---|---|
| intent aov | 124 | 124 | 100.0 | 0 |
| intent best_day | 121 | 121 | 100.0 | 0 |
| intent best_item | 10 | 10 | 100.0 | 0 |
| intent cancel_count | 100 | 100 | 100.0 | 0 |
| intent cancel_rate | 120 | 120 | 100.0 | 0 |
| intent item_qty | 96 | 96 | 100.0 | 0 |
| intent order_count | 11 | 11 | 100.0 | 0 |
| intent rev_change_pct | 115 | 115 | 100.0 | 0 |
| intent revenue | 197 | 197 | 100.0 | 0 |
| intent topk_items | 48 | 48 | 100.0 | 0 |
| fold dev | 711 | 711 | 100.0 | 0 |
| fold holdout | 231 | 231 | 100.0 | 0 |

## Mismatches (0)


## Period differs from rule_regression's parse (0)


Notes
- Selection (942 questions with an explicit month/date), SQL templates and answer comparison are the data-layer
  branch's `scripts/analysis/rule_regression.py`, unmodified; only the date filter is replaced by `Period.where_sql()`
  and the text goes through the rule normalizer first (as in the pipeline). Its own parser scores 942/942 as well.
- First run (raw text, before fixes): 939/942; the 3 misses were timeutil bugs, fixed in this branch
  ("cùng tháng năm trước", "trc"/"th" abbreviations in comparison cues) and covered by tests.
- Tết / lunar expressions are not in this group; they need `calendar.csv` (to be joined when the data layer adds its calendar table).
- Question text is not stored here (private data).
