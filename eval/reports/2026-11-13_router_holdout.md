# Router evaluation (CPU, no LLM) 2026-11-15

| fold | questions | template route | % | correct | accuracy % | template PA | PA lower bound | wrong | intent acc % |
|---|---|---|---|---|---|---|---|---|---|
| dev | 0 | 0 | 0.0 | 0 | 0.0 | 0.0 | 0.0 | 0 | 100.0 |
| holdout | 709 | 535 | 75.46 | 534 | 99.81 | 0.9963 | 0.7518 | 1 | 100.0 |

## dev: by intent (template route)

| intent | n | correct | acc % |
|---|---|---|---|

LLM/other reasons: {}
Wrong attribution: {}

### dev errors (id, intent, gold type, attribution)


## holdout: by intent (template route)

| intent | n | correct | acc % |
|---|---|---|---|
| revenue | 105 | 104 | 99.05 |
| order_count | 51 | 51 | 100.0 |
| cancel_count | 38 | 38 | 100.0 |
| cancel_rate | 23 | 23 | 100.0 |
| aov | 45 | 45 | 100.0 |
| best_day | 23 | 23 | 100.0 |
| topk_items | 17 | 17 | 100.0 |
| best_item | 1 | 1 | 100.0 |
| item_qty | 20 | 20 | 100.0 |
| rev_change_pct | 38 | 38 | 100.0 |
| item_revenue | 24 | 24 | 100.0 |
| category_rev | 8 | 8 | 100.0 |
| sell_price_on_day | 14 | 14 | 100.0 |
| unans_subjective | 3 | 3 | 100.0 |
| best_month | 2 | 2 | 100.0 |
| monthly_series | 4 | 4 | 100.0 |
| streak_bool | 5 | 5 | 100.0 |
| payment_method_rev | 6 | 6 | 100.0 |
| channel_rev | 2 | 2 | 100.0 |
| unit_total_qty | 6 | 6 | 100.0 |
| ingredient_revenue | 4 | 4 | 100.0 |
| rx_nonrx_revenue | 3 | 3 | 100.0 |
| rx_share | 3 | 3 | 100.0 |
| purchase_total | 3 | 3 | 100.0 |
| supplier_top | 1 | 1 | 100.0 |
| purchase_avg_price | 6 | 6 | 100.0 |
| stock_qty | 3 | 3 | 100.0 |
| stock_large_unit | 1 | 1 | 100.0 |
| stock_value | 1 | 1 | 100.0 |
| expiry_list | 1 | 1 | 100.0 |
| expiry_nearest_lot | 2 | 2 | 100.0 |
| cust_freq_count | 7 | 7 | 100.0 |
| cust_freq_share | 1 | 1 | 100.0 |
| staff_revenue | 2 | 2 | 100.0 |
| days_over_threshold | 3 | 3 | 100.0 |
| shift | 8 | 8 | 100.0 |
| price_effect | 15 | 15 | 100.0 |
| category_share | 22 | 22 | 100.0 |
| size_qty | 6 | 6 | 100.0 |
| unsold_count | 8 | 8 | 100.0 |

LLM/other reasons: {'not_target': 113, 'category_not_found': 16, 'extra_filter_or_subintent': 13, 'purchase_book_not_built': 8, 'group_not_found': 4, 'normalizer_residual_teencode': 4, 'none_named': 4, 'period_count': 3, 'purchase_pattern': 3, 'freq_not_at_least_n': 2, 'stock_needs_day': 1, 'item_not_found': 1, 'staff_not_found': 1, 'cost_price_missing': 1}
Wrong attribution: {'period_or_template': 1}

### holdout errors (id, intent, gold type, attribution)

- q_8df2a7aa2646 revenue number period_or_template(granularity-check)
