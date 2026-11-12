# Backlog router: phần rơi xuống LLM (chỉ dev, 24 shop)

> Cập nhật 2026-11-13: đã thêm vào router (100% trên dev, hold-out chạy một lần 339/339): `orders_threshold` (qua order_count),
> `unans_subjective`, `item_revenue`, `category_rev`, `sell_price_on_day`. Các số bên dưới là của lần đo trước khi thêm các intent này.

Nguồn: `scripts/eval_router.py` (run 2026-11-13). Chỉ dùng dev; không có câu hỏi hay đáp án, chỉ id. Nhóm theo nhãn của tagger hiện có
(`src/router/_tagger_rules.py`, nhãn gần đúng ±10%, có gắn nhầm). Độ khó = ước lượng công viết template + kiểm chứng, không phải độ khó dữ liệu.
Tổng dev rơi xuống LLM: 1331 câu; trong đó 984 câu intent ngoài TARGET_INTENTS (bảng 1) và 347 câu thuộc TARGET_INTENTS bị luật an toàn chặn (bảng 2).

## Bảng 1. Intent ngoài TARGET_INTENTS (xếp theo số câu giảm dần)

| # | intent (tagger) | câu | shop | gold type | ví dụ id | view / cột cần dùng | độ khó | luật rulebook | ghi chú |
|---|---|---|---|---|---|---|---|---|---|
| 1 | shift | 66 | 8 | {'number': 45, 'percent': 21} | q_14d138cb0a76, q_1c4d072b63b0, q_1fe312ba9eed | v_orders(order_date, order_time, revenue, status) | vừa | §2 Ca sáng 06:00–13:59 / ca chiều 14:00–21:59; chiều so với sáng | order_time NULL ở shop không ghi giờ -> LLM; 21/66 là percent chiều-vs-sáng |
| 2 | price_effect | 63 | 9 | {'percent': 63} | q_1ae34ce74d14, q_63501211fe59, q_66380f9d73b9 | v_valid_lines(order_date, item_name, qty_base) | vừa | §5 Hiệu ứng tăng giá (N ngày từ D gồm D so với N ngày ngay trước D); §2 N ngày kể từ | timeutil đã có n_days_from; cần khớp mặt hàng + ngày D; 100% percent |
| 3 | category_share | 57 | 13 | {'percent': 57} | q_83878331afed, q_94ec5f7f1c70, q_23f99ee972ab | v_valid_lines(category, line_amount) / v_valid_orders(revenue) | vừa | §3 Nhóm hàng; §1 doanh thu | khớp tên nhóm với v_items.category; mẫu số = doanh thu kỳ |
| 4 | purchase_avg_price | 48 | 11 | {'number': 45, 'unanswerable': 3} | q_4f4919db1974, q_df2c3f7132ac, q_f8adca719b61 | (chưa có view nhập hàng) bảng phiếu nhập raw_* | khó | §5 Giá nhập bình quân theo số lượng nhập, theo đơn vị nhập, bỏ phiếu huỷ | chặn bởi tầng dữ liệu: cần v_purchases |
| 5 | item_revenue | 41 | 17 | {'number': 35, 'list': 5, 'unanswerable': 1} | q_62a9a454f35b, q_1aa59362b405, q_49a4ebe0f6d3 | v_valid_lines(line_amount, item_name/item_code) | dễ | §1 Bán được bao nhiêu tiền; §3 Mặt hàng | dùng lại match_item; trùng 1 phần với bộ lọc item_specific_revenue |
| 6 | stock_qty | 41 | 12 | {'unanswerable': 6, 'number': 35} | q_73fac0fa2e46, q_ad432d1062b7, q_835e49f85406 | (chưa có view tồn kho) bảng tồn/nhập/xuất | khó | §5 Tồn; §2 Đến hết ngày X (tình trạng cuối ngày, từ đầu dữ liệu) | 6/41 gold unanswerable; chặn bởi tầng dữ liệu: v_stock |
| 7 | ingredient_revenue | 41 | 5 | {'number': 41} | q_29237cfd9d01, q_299e5230f52e, q_3335fb31c17c | v_valid_lines JOIN v_items(active_ingredient) | dễ | §6 Nhà thuốc: Doanh thu theo hoạt chất | hoạt chất ghép nhiều chất ('a + b'): so khớp tập |
| 8 | purchase_total | 40 | 9 | {'unanswerable': 1, 'string': 1, 'number': 38} | q_2407aef28946, q_20cfa482235e, q_2c664c3eaf2c | (chưa có view nhập hàng) | khó | §5 Tiền nhập hàng trong kỳ | chặn bởi v_purchases; một số câu hỏi nhà cung cấp -> kiểu string |
| 9 | size_qty | 37 | 4 | {'number': 37} | q_3fc9d7922b49, q_41c360c34398, q_4bfce7dd9238 | v_valid_lines(item_name, qty_base) | vừa | §6 Cà phê: Size M, size L | size nằm trong tên '(M)'; cộng mọi món |
| 10 | sell_price_on_day | 35 | 22 | {'number': 35} | q_fcbf1e1cd8d4, q_978b78934127, q_01a252a82858 | v_lines(order_date, item, unit_price_base) (KHÔNG dùng v_valid_lines) | dễ | §5 Giá bán X ngày D: một đơn vị cơ bản, trước chiết khấu, tính cả đơn huỷ/trả | 22 shop; dễ nhưng cần khớp mặt hàng+đơn vị |
| 11 | category_rev | 34 | 13 | {'number': 34} | q_5ec9e9d3a54d, q_13fc08e94004, q_bc83ba885777 | v_valid_lines(category, line_amount) | dễ | §3 Nhóm hàng | khớp category mờ (nhóm 'trà' vs 'trà sữa') |
| 12 | cust_topk | 30 | 15 | {'list': 28, 'string': 2} | q_327ffb3f517d, q_4afd238d098c, q_4f742bfda263 | v_valid_orders(customer_key, customer_name, revenue) | vừa | §3 Xác định khách (loại khách lẻ, gộp tên); Xếp hạng, hoà -> theo luật | định dạng tên khách, hoà điểm |
| 13 | unsold_count | 26 | 4 | {'number': 26} | q_238225519d3a, q_848330889af7, q_c00dc4e2a578 | v_items LEFT JOIN v_valid_lines | vừa | §5 Mặt hàng không bán được trong kỳ (ế) | danh sách mặt hàng gốc = danh mục |
| 14 | channel_rev | 24 | 6 | {'unanswerable': 2, 'list': 9, 'percent': 9, 'number': 4} | q_d345bddf40bc, q_14ea21a5b6a1, q_5c9cf907f474 | v_valid_orders(channel, revenue) | dễ | §1 Doanh thu theo hình thức thanh toán/nhóm; kênh | câu hỏi 2 kênh -> list/percent |
| 15 | rx_nonrx_revenue | 20 | 5 | {'number': 20} | q_29503ba420d0, q_50d644357434, q_8806b5b18ac8 | v_valid_lines JOIN v_items(is_prescription) | dễ | §6 Thuốc kê đơn | kê đơn / không kê đơn |
| 16 | staff_top | 19 | 13 | {'string': 18, 'unanswerable': 1} | q_4b2450e3eaed, q_88f4eaa9981e, q_18d173308b03 | v_valid_orders(staff) hoặc customer_key | vừa | §3 Nhân viên bán giỏi nhất | tagger gắn nhầm 'ai là khách ...' vào nhóm này (~16/19 là khách) |
| 17 | OTHER:câu doanh thu/đơn/mặt hàng bị tagger bỏ sót do teencode/tiếng Anh/ngày tương đối (intent mục tiêu!) | 19 | 16 | {'number': 14, 'string': 5} | q_7e3623dbabe0, q_c972201b657c, q_20ad1fe3cbcd | template có sẵn (revenue/order_count/best_item) | dễ | §1; §2 hôm qua/tuần rồi/7 ngày gần nhất/từ đầu năm | mở rộng nhận intent: teencode (ddown, hqua), 'revenue', 'bán được nhiều tiền', 'nhiều nhất là gì'; đây là recall dễ nhất |
| 18 | stock_large_unit | 18 | 7 | {'unanswerable': 2, 'list': 16} | q_81389e30d95b, q_79281eb9a5e5, q_0794a9a26cef | (chưa có view tồn kho) + v_items | khó | §5 Tồn theo đơn vị lớn (list [chẵn, lẻ]); §10 đơn vị | chặn bởi v_stock |
| 19 | rx_share | 18 | 5 | {'percent': 18} | q_33dcc7d5b828, q_3b5bfbfb6938, q_84675b30970f | v_valid_lines + v_items(is_prescription) | vừa | §6 Thuốc kê đơn; §1 phần trăm 2 chữ số | percent = kê đơn / tổng doanh thu |
| 20 | payment_method_rev | 17 | 5 | {'unanswerable': 2, 'number': 6, 'percent': 3, 'list': 6} | q_6c1ca5ce7bd4, q_37c963b963ef, q_72d7deb192d7 | v_valid_orders(payment_method, revenue) | dễ | §1 Doanh thu theo hình thức thanh toán; §4 COD | 2/17 gold unanswerable (shop không ghi) |
| 21 | unit_total_qty | 17 | 10 | {'number': 17} | q_8848e665f8d1, q_9587f9b496c8, q_0cbadf876dcd | v_valid_lines(qty_base, base_unit) | dễ | §3 Bán được bao nhiêu <đơn vị>; §10 | tổng qty_base mọi mặt hàng cùng base_unit |
| 22 | debt_collected | 17 | 4 | {'number': 17} | q_df1caa0fd643, q_f24714cccf9d, q_838a6f2a3392 | v_orders(due_date, paid_amount), v_payments | khó | §4 Nợ thêm, trả nợ, thu nợ trong kỳ | dùng ngày thu tiền, không phải ngày đơn |
| 23 | cust_group_rev | 16 | 4 | {'number': 16} | q_0beba71e5fd7, q_406dd570776d, q_443c68401534 | v_valid_orders(customer_group, revenue) | dễ | §1 Doanh thu theo nhóm khách | tên nhóm khớp mờ |
| 24 | cust_group_share | 15 | 5 | {'unanswerable': 1, 'percent': 14} | q_4bc3846b6f5b, q_4afebc6d1d4b, q_7b171247d1cc | v_valid_orders(customer_group) | vừa | §1 Doanh thu theo nhóm khách; percent | 1 câu gold unanswerable |
| 25 | best_month | 14 | 7 | {'date': 14} | q_0a0038f69d4e, q_9045737fcddf, q_81d6b5a181f4 | v_valid_orders GROUP BY order_month | dễ | §2 Từ X đến Y; Xếp hạng; kết quả type date 'YYYY-MM' | 14/14 date; timeutil có month_range |
| 26 | debt_topk_table | 14 | 6 | {'unanswerable': 2, 'table': 12} | q_faf7802261fb, q_153f4e995558, q_3a2bccc332db | v_orders(due_date, paid_amount, customer_key) + v_payments | khó | §4 Nợ một đơn tại ngày X; Nợ theo khách | trả table {columns,rows} |
| 27 | monthly_series | 12 | 8 | {'list': 12} | q_0483a8398dfe, q_40995ec33f88, q_7f073a4b0a54 | v_valid_orders GROUP BY order_month | dễ | §2 Tháng M/Y; chuỗi tháng liền nhau | list có thứ tự, 'từ cũ đến mới' |
| 28 | streak_bool | 12 | 8 | {'boolean': 12} | q_b4a4c7135e0a, q_c5639bf3d2a2, q_c8273e950235 | v_valid_orders GROUP BY order_month | dễ | §1 Chênh lệch/tăng giảm; boolean | 'tăng liên tục' = từng cặp tháng kề nhau |
| 29 | orders_threshold | 12 | 7 | {'number': 12} | q_cea0f8cb615c, q_5c87fb634a59, q_7cc0801e4226 | v_valid_orders(revenue >= X) | dễ | §1 Quá N, hơn N, trên N, dưới N (§2) | template order_count_threshold đã có; chỉ cần router nhận (hiện tagger gắn non-target) |
| 30 | cust_freq_count | 11 | 6 | {'number': 10, 'unanswerable': 1} | q_660dd2abb279, q_1ccb81c372d3, q_4b77ed39a2ff | v_valid_orders GROUP BY customer_key HAVING COUNT>=N | vừa | §3 Xác định khách; §2 từ N đơn trở lên | 1 gold unanswerable |
| 31 | cust_top1 | 11 | 10 | {'string': 10, 'unanswerable': 1} | q_3ec323f48d62, q_aacf9543a235, q_341141d1a85c | v_valid_orders(customer_name, revenue) | vừa | §3 Xác định khách, hoà điểm | kiểu string, alias tên |
| 32 | OTHER:đợt giao hàng (≈ delivery_count) | 11 | 2 | {'number': 11} | q_106656934f8f, q_5d5a5ffd5606, q_65c8757b42cc | v_orders(n_delivery_rounds, first/last_delivery_date), v_deliveries | vừa | §6 VLXD Giao nhiều đợt: mỗi đợt của mỗi đơn là một đợt, kể cả đơn sau đó trả hàng | ngày giao thuộc tháng X; nhiều câu rơi vào cụm OTHER |
| 33 | cust_freq_share | 10 | 5 | {'percent': 10} | q_75d48f1bfc6d, q_7f283f673cee, q_8036e34515e9 | v_valid_orders (percent of customers) | vừa | §3 Xác định khách; percent | mẫu số = số khách có mua trong kỳ |
| 34 | debt_flow_customer | 10 | 2 | {'list': 10} | q_426baab167a3, q_97378cee7c0e, q_97541e3502fb | v_orders + v_payments theo khách | khó | §4 Nợ theo khách, nợ thêm, trả nợ | list [nợ thêm, đã trả]; khớp tên khách |
| 35 | debt_customer_count | 10 | 3 | {'number': 10} | q_56724d89c623, q_831658029945, q_cc989ac5d7a0 | v_orders(due_date, paid_amount) | khó | §4 Đơn tính vào nợ; Nợ một đơn tại ngày X; §2 Đến hết ngày X |  |
| 36 | debt_total | 9 | 5 | {'unanswerable': 1, 'number': 8} | q_ecca6bcc3dfc, q_073aee886aef, q_32a692d7807b | v_orders(due_date, paid_amount) | khó | §4 Đơn tính vào nợ; Nợ một đơn tại ngày X |  |
| 37 | cust_attr | 8 | 7 | {'unanswerable': 8} | q_9f82b2f25fd6, q_a4560b62b198, q_f895c5de92bd | (không có cột) -> unanswerable | dễ | §7 Thông tin file không ghi thì không trả lời được | 8/8 gold là unanswerable -> thắng nhanh: route unanswerable khi shop thiếu thuộc tính khách |
| 38 | OTHER:giá bán một đơn vị (≈ sell_price_on_day) | 8 | 8 | {'number': 8} | q_1703b4f93db8, q_13afb3a15b07, q_e0eb2f43ba7b | v_lines(unit_price_base) | dễ | §5 Giá bán X ngày D | tagger bỏ sót; cùng họ sell_price_on_day |
| 39 | debt_aging | 7 | 2 | {'list': 2, 'number': 5} | q_1f99d93acad3, q_23cea7790c35, q_87fe5ac2d2b1 | v_orders(order_date, due_date, paid_amount) | khó | §4 Tuổi nợ (tính từ ngày đặt); khoảng 0-7/8-15/>15 |  |
| 40 | cust_top_orders | 7 | 4 | {'string': 7} | q_6b97346f858f, q_2528eab85436, q_6d5e6a76a910 | v_valid_orders COUNT per customer_key | vừa | §3 Xác định khách; xếp hạng theo số đơn | string |
| 41 | staff_revenue | 7 | 2 | {'number': 7} | q_16a0a8ef25c5, q_1c39f9ff5e6a, q_3de8d66158dc | v_valid_orders(staff) | vừa | §3 Nhân viên | mã NVxxx vs tên |
| 42 | item_in_n_orders | 6 | 2 | {'number': 6} | q_446a146d3418, q_5a2a8754491f, q_8a84b3d3341a | v_valid_lines COUNT(DISTINCT order_id) per item >= N | vừa | §3 Mặt hàng; §2 từ N trở lên |  |
| 43 | expiry_list | 5 | 4 | {'unanswerable': 3, 'number': 1, 'list': 1} | q_360f8795ce6c, q_910640a29988, q_7dae0d81eb69 | (chưa có view lô/hạn dùng) | khó | §6 Nhà thuốc: Hàng hết hạn trong N ngày tới | 3/5 gold unanswerable |
| 44 | delivery_count | 5 | 2 | {'number': 5} | q_047586efd4bf, q_4632f7122d38, q_440545f5b178 | v_orders(n_delivery_rounds, first/last_delivery_date), v_deliveries | vừa | §6 VLXD Giao nhiều đợt: mỗi đợt của mỗi đơn là một đợt, kể cả đơn sau đó trả hàng | ngày giao thuộc tháng X; nhiều câu rơi vào cụm OTHER |
| 45 | OTHER:mặt hàng có mặt trong ≥N đơn (≈ item_in_n_orders) | 5 | 2 | {'number': 5} | q_4192ef63e140, q_a965ab7a53ee, q_bfa382e47ca0 | v_valid_lines COUNT(DISTINCT order_id) per item >= N | vừa | §3 Mặt hàng; §2 từ N trở lên |  |
| 46 | stock_value | 4 | 4 | {'unanswerable': 1, 'number': 3} | q_24ed0fa1deca, q_0a6d039818f6, q_2dda154fcb5a | (chưa có view tồn kho + giá vốn) | khó | §5 Giá trị hàng tồn kho (theo giá vốn) |  |
| 47 | unans_subjective | 4 | 4 | {'unanswerable': 4} | q_3ad4ff264376, q_1af6e691fc94, q_97049319d8e8 | (không cần dữ liệu) -> unanswerable | dễ | §7 Không trả lời được (câu hỏi chủ quan) | 4/4 gold unanswerable -> thắng nhanh: route unanswerable theo từ khoá chủ quan |
| 48 | supplier_top | 4 | 3 | {'string': 4} | q_3bdc21e5f7f8, q_4722c7644c0d, q_4d8da48b964e | (chưa có view nhập hàng) | khó | §5 Tiền nhập hàng; nhà cung cấp | string |
| 49 | gross_profit | 3 | 2 | {'number': 2, 'unanswerable': 1} | q_501e4b45bd00, q_81cc91f86744, q_cd7bfdbf4d08 | (giá vốn: v_items.cost_price + v_valid_lines) | vừa | §5 Giá vốn; Lãi gộp | giá vốn không phải shop nào cũng có |
| 50 | net_profit | 3 | 1 | {'number': 3} | q_40de33fe6cdc, q_a149a00151dd, q_c2d367ddde3f | (chi phí: bảng chi phí raw) | khó | §5 Lãi ròng một tháng | 1 shop |
| 51 | OTHER:đếm ngày có doanh thu ≥ X | 3 | 3 | {'number': 3} | q_e02828e34a34, q_bab2bec0be28, q_5b1fc63aef42 | v_valid_orders GROUP BY order_date HAVING SUM(revenue) >= X | dễ | §1 doanh thu; §2 Quá N/từ N | đếm số ngày |
| 52 | tet | 2 | 2 | {'percent': 2} | q_0fbd522a4f2f, q_eef55227353d | timeutil.tet + v_valid_orders | vừa | §2 Tết năm Y: 23 Chạp .. mùng 10 Giêng; so với N ngày trước Tết | cần calendar; percent |
| 53 | profit_item_top | 2 | 1 | {'string': 2} | q_0b576981b592, q_3c3a0109c0b5 | v_valid_lines + v_items(cost_price) | vừa | §3 Hàng lời nhất; §5 Giá vốn |  |
| 54 | expiry_nearest_lot | 2 | 1 | {'date': 2} | q_0eef1e74b13e, q_bf22965b9ea7 | (chưa có view lô) | khó | §6 Lô gần hết hạn nhất |  |
| 55 | OTHER:khác | 2 | 2 | {'number': 1, 'unanswerable': 1} | q_2673cb45d798, q_e308f9743d56 | ? | ? | ? | chưa gán |
| 56 | stockout_count | 1 | 1 | {'number': 1} | q_a0aa88c9c8d7 | (chưa có view tồn kho) | khó | §5 Mặt hàng hết hàng cuối ngày |  |
| 57 | purchase_minus_sales | 1 | 1 | {'number': 1} | q_d99a85034d64 | (chưa có view nhập hàng) | khó | §5 Nhập trừ bán |  |

## Bảng 2. Câu thuộc TARGET_INTENTS bị luật an toàn chặn

| lý do | câu | intent hay gặp | ghi chú |
|---|---|---|---|
| extra_filter_or_subintent | 143 | [('revenue', 112), ('best_item', 22), ('item_qty', 6)] | có bộ lọc phụ (nhóm, khách, ca, so sánh…) -> phần lớn thuộc các nhóm ở bảng 1 (shift, category, cust_*) |
| multi_intent | 109 | [] | tagger khớp 2 intent mục tiêu không thuộc cặp tương thích; cần xem lại COMPAT |
| normalizer_residual_teencode | 41 | [] | lớp chuẩn hoá còn teencode -> chờ lớp LLM chuẩn hoá |
| unit_mismatch | 29 | [('item_qty', 29)] | đơn vị hỏi ≠ base_unit: cần quy đổi qua v_lines.unit/factor (§10) |
| item_specific_revenue | 14 | [('revenue', 14)] | doanh thu của một mặt hàng -> item_revenue (dễ) |
| before_data_start | 8 | [('revenue', 3), ('topk_items', 2), ('best_day', 2)] |  |
| empty_result | 2 | [('rev_change_pct', 2)] | template không có dòng |
| item_not_found | 1 | [('item_qty', 1)] | không khớp tên hàng |

## Thứ tự gợi ý

1. **Thắng nhanh, không cần view mới** (dễ, 337 câu dev): intent mục tiêu bị bỏ sót (nhận diện), orders_threshold, item_revenue, sell_price_on_day, category_rev, ingredient_revenue, rx_nonrx_revenue, channel/payment/cust_group_rev, unit_total_qty, best_month/monthly_series/streak_bool, cust_attr + unans_subjective (route unanswerable, 12/12 gold unanswerable trên dev).
2. **Vừa** (411 câu): shift, price_effect, category_share, size_qty, cust_* (khách), unsold_count, delivery_count.
3. **Khó / chặn bởi tầng dữ liệu** (234 câu) (cần view nhập hàng, tồn kho, lô/hạn dùng, công nợ theo ngày): purchase_*, stock_*, expiry_*, debt_*, profit.

Cần Nghiệp: v_purchases, v_stock, v_batches, công nợ theo ngày (v_debt_at). Template dùng lại SQL của Nghiệp phải giữ nguyên SQL gốc và được duyệt.

## Chặn bởi tầng dữ liệu (việc của Nghiệp; router không sửa file của Nghiệp)

- **dev_004 (public): chẩn đoán cũ "ngày d/m không ghi năm không parse được" là SAI (đã sửa 2026-11-13).** Khi parse
  với năm của sheet (đúng như `build_ledger` làm), cả 15337 ô ngày không rỗng của sổ bán hàng đều parse được. 54% dòng
  được `build_ledger` đếm vào `issues["unparsed_dates"]` là các ô ngày **bỏ trống** (ngày chỉ ghi ở dòng đầu mỗi đơn,
  ledger điền xuống; ledger cuối không còn dòng nào thiếu ngày). Bộ đếm `unparsed_dates` của Nghiệp vì vậy đếm cả ô trống;
  router không dùng nó nữa mà tự đếm ô không rỗng parse lỗi (`src/router/invariants.py`). dev_004 không còn bị cờ.
  Lỗi của dev_004 nếu có (leaderboard: bỏ 28 câu của shop này tăng/giảm điểm +14 ròng, tức ≈21 đúng/7 sai, 75% so với ≈89% các shop khác)
  chưa rõ nguyên nhân; chưa có bằng chứng về lỗi parse ngày.
- **Test của Nghiệp phụ thuộc thứ tự chạy:** `tests/test_smoke.py::RegressionTests::test_create_demo_no_connection_leak`
  fail khi chạy sau `tests/test_ingestion_cache.py` (`pytest tests/test_ingestion_cache.py tests/test_smoke.py`).
  Đã fail từ commit merge branch của Nghiệp vào `feat/question-normalization` (trước mọi code router), không fail trên
  branch của Nghiệp. Chưa rõ nguyên nhân gốc; có thể có kết nối SQLite bị rò rỉ ở test cache.
- `tests/test_rule_regression.py` (2 test) fail vì đòi cấu trúc `data/train/data/...`, không khớp dữ liệu chính thức.

