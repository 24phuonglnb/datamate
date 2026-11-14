# Router evaluation (CPU, no LLM) 2026-11-13

| fold | questions | template route | % | correct | accuracy % | template PA | PA lower bound | wrong | intent acc % |
|---|---|---|---|---|---|---|---|---|---|
| dev | 0 | 0 | 0.0 | 0 | 0.0 | 0.0 | 0.0 | 0 | 100.0 |
| holdout | 709 | 356 | 50.21 | 356 | 100.0 | 1.0 | 0.5021 | 0 | 100.0 |

## dev: by intent (template route)

| intent | n | correct | acc % |
|---|---|---|---|

LLM/other reasons: {}
Wrong attribution: {}

### dev errors (id, intent, gold type, attribution)


## holdout: by intent (template route)

| intent | n | correct | acc % |
|---|---|---|---|
| revenue | 84 | 84 | 100.0 |
| order_count | 51 | 51 | 100.0 |
| cancel_count | 38 | 38 | 100.0 |
| cancel_rate | 12 | 12 | 100.0 |
| aov | 45 | 45 | 100.0 |
| best_day | 23 | 23 | 100.0 |
| topk_items | 17 | 17 | 100.0 |
| best_item | 1 | 1 | 100.0 |
| item_qty | 13 | 13 | 100.0 |
| rev_change_pct | 18 | 18 | 100.0 |
| item_revenue | 12 | 12 | 100.0 |
| category_rev | 8 | 8 | 100.0 |
| sell_price_on_day | 14 | 14 | 100.0 |
| unans_subjective | 3 | 3 | 100.0 |
| best_month | 1 | 1 | 100.0 |
| monthly_series | 4 | 4 | 100.0 |
| streak_bool | 5 | 5 | 100.0 |
| payment_method_rev | 1 | 1 | 100.0 |
| unit_total_qty | 6 | 6 | 100.0 |

LLM/other reasons: {'not_target': 241, 'extra_filter_or_subintent': 37, 'multi_intent': 28, 'normalizer_residual_teencode': 14, 'category_not_found': 9, 'item_specific_revenue': 8, 'several_named': 5, 'unit_mismatch': 4, 'group_not_found': 4, 'period_count': 1, 'item_not_found': 1, 'none_named': 1}
Wrong attribution: {}

### holdout errors (id, intent, gold type, attribution)

