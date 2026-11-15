# Router evaluation (CPU, no LLM) 2026-11-15

| fold | questions | template route | % | correct | accuracy % | template PA | PA lower bound | wrong | intent acc % |
|---|---|---|---|---|---|---|---|---|---|
| dev | 2291 | 1824 | 79.62 | 1824 | 100.0 | 1.0 | 0.7962 | 0 | 100.0 |
| holdout | 0 | 0 | 0.0 | 0 | 0.0 | 0.0 | 0.0 | 0 | 100.0 |

## dev: by intent (template route)

| intent | n | correct | acc % |
|---|---|---|---|
| revenue | 365 | 365 | 100.0 |
| order_count | 136 | 136 | 100.0 |
| cancel_count | 62 | 62 | 100.0 |
| cancel_rate | 117 | 117 | 100.0 |
| aov | 122 | 122 | 100.0 |
| best_day | 103 | 103 | 100.0 |
| topk_items | 43 | 43 | 100.0 |
| best_item | 21 | 21 | 100.0 |
| item_qty | 103 | 103 | 100.0 |
| rev_change_pct | 134 | 134 | 100.0 |
| item_revenue | 32 | 32 | 100.0 |
| category_rev | 11 | 11 | 100.0 |
| sell_price_on_day | 21 | 21 | 100.0 |
| unans_subjective | 4 | 4 | 100.0 |
| best_month | 7 | 7 | 100.0 |
| monthly_series | 12 | 12 | 100.0 |
| streak_bool | 12 | 12 | 100.0 |
| cust_group_rev | 6 | 6 | 100.0 |
| payment_method_rev | 15 | 15 | 100.0 |
| channel_rev | 22 | 22 | 100.0 |
| unit_total_qty | 12 | 12 | 100.0 |
| ingredient_revenue | 41 | 41 | 100.0 |
| rx_nonrx_revenue | 20 | 20 | 100.0 |
| rx_share | 18 | 18 | 100.0 |
| purchase_total | 38 | 38 | 100.0 |
| supplier_top | 3 | 3 | 100.0 |
| purchase_avg_price | 46 | 46 | 100.0 |
| stock_qty | 40 | 40 | 100.0 |
| stock_large_unit | 17 | 17 | 100.0 |
| stock_value | 4 | 4 | 100.0 |
| expiry_list | 4 | 4 | 100.0 |
| expiry_nearest_lot | 2 | 2 | 100.0 |
| cust_freq_count | 9 | 9 | 100.0 |
| cust_freq_share | 10 | 10 | 100.0 |
| staff_revenue | 7 | 7 | 100.0 |
| days_over_threshold | 7 | 7 | 100.0 |
| shift | 60 | 60 | 100.0 |
| price_effect | 57 | 57 | 100.0 |
| category_share | 28 | 28 | 100.0 |
| size_qty | 27 | 27 | 100.0 |
| unsold_count | 26 | 26 | 100.0 |

LLM/other reasons: {'not_target': 228, 'extra_filter_or_subintent': 115, 'category_not_found': 47, 'item_not_found': 15, 'item_specific_revenue': 14, 'normalizer_residual_teencode': 13, 'group_not_found': 9, 'period_count': 8, 'none_named': 4, 'multi_intent': 3, 'empty_result': 2, 'purchase_pattern': 2, 'freq_not_at_least_n': 2, 'item_named': 2, 'price_no_comparison': 2, 'shift_pattern': 1}
Wrong attribution: {}

### dev errors (id, intent, gold type, attribution)


## holdout: by intent (template route)

| intent | n | correct | acc % |
|---|---|---|---|

LLM/other reasons: {}
Wrong attribution: {}

### holdout errors (id, intent, gold type, attribution)

