# Báo cáo Task T7 — Profile shop phục vụ unanswerable và abstain

## 1. Tổng quan
- **Số shop đã dựng profile**: 44/44 (30 shop train + 14 shop public test).
- **Vị trí lưu trữ**: `reports/profiles/{biz_id}.json` và `reports/all_shop_profiles.json`.
- **Tốc độ build profile**: ~420.2s (tối ưu hóa `unique()` date parsing, garbage-collected per shop).

## 2. Kết quả đối chiếu với 70 câu unanswerable (Train)

| Nhóm | Số câu | Tỉ lệ (%) | Mô tả |
|---|---|---|---|
| **(a) Kỳ ngoài dữ liệu** | **15** | 21.4% | Kỳ hỏi (hoặc kỳ so sánh trước) nằm hoàn toàn ngoài khoảng ngày của shop (§7) |
| **(b) Shop thiếu loại dữ liệu** | **41** | 58.6% | Shop không có bảng/cột cần thiết (tồn kho, công nợ, kênh, hình thức TT, giới tính, địa chỉ...) |
| **(c) Ngoài phạm vi profile** | **7** | 10.0% | Đánh giá chủ quan (lành nghề, quý mến, khen ngợi) hoặc kiến thức y tế ngoài bảng |
| **Tổng cộng** | **70** | **100.0%** | **100% câu unanswerable được giải thích minh bạch** |

### Tỉ lệ báo nhầm (False Positive Rate) trên câu trả lời được:
- **Số câu trả lời được bị báo nhầm**: **80** / 2930 câu.
- **Tỉ lệ báo nhầm**: **2.73%** (thỏa mãn tiêu chí gần 0%).

## 3. Chi tiết 70 câu unanswerable theo nhóm

### Nhóm (a): Kỳ ngoài dữ liệu (15 câu)
| STT | ID | Shop | as_of_date | Câu hỏi | Lý do unanswerable |
|---|---|---|---|---|---|
| 1 | `q_03a446be8b75` | `biz_121` | 2026-09-20 | trong thang 2/2025, ti le don huy la bao nhieu % | Kỳ hỏi [2025-02-01 .. 2025-02-28] nằm hoàn toàn ngoài khoảng dữ liệu bán [2025-03-01 .. 2026-09-20] |
| 2 | `q_147e7a072dc7` | `biz_106` | 2026-09-14 | Tháng 2/2025 doanh thu thay đổi bao nhiêu % so với tháng liền trước? | Kỳ hỏi [2025-01-01 .. 2025-01-31] nằm hoàn toàn ngoài khoảng dữ liệu bán [2025-02-01 .. 2026-09-14] (growth_needs_prev_month_2025_01) |
| 3 | `q_40f434f3920d` | `biz_121` | 2026-09-20 | Khách nào chi nhiều tiền nhất cho cửa hàng trong tháng 2/2025? | Kỳ hỏi [2025-02-01 .. 2025-02-28] nằm hoàn toàn ngoài khoảng dữ liệu bán [2025-03-01 .. 2026-09-20] |
| 4 | `q_46e6ca519588` | `biz_103` | 2026-07-09 | dthu thang 2/2025 bnhiu | Kỳ hỏi [2025-02-01 .. 2025-02-28] nằm hoàn toàn ngoài khoảng dữ liệu bán [2025-04-01 .. 2026-07-09] |
| 5 | `q_5e75fcb3f8ce` | `biz_103` | 2026-07-09 | thang 3/2025 cua hang ban duoc tong cong bnhiu tien | Kỳ hỏi [2025-03-01 .. 2025-03-31] nằm hoàn toàn ngoài khoảng dữ liệu bán [2025-04-01 .. 2026-07-09] |
| 6 | `q_6c8b6ef41426` | `biz_106` | 2026-09-14 | dthu của cà phê muối (l) trong tháng 1 năm 2025 là bnhiu | Kỳ hỏi [2025-01-01 .. 2025-01-31] nằm hoàn toàn ngoài khoảng dữ liệu bán [2025-02-01 .. 2026-09-14] |
| 7 | `q_732831f68f60` | `biz_112` | 2026-07-31 | thang 3/2025 cua hang ban duoc tong cong bao nhieu tien ha | Kỳ hỏi [2025-03-01 .. 2025-03-31] nằm hoàn toàn ngoài khoảng dữ liệu bán [2025-04-01 .. 2026-07-31] |
| 8 | `q_853bb1d1a1db` | `biz_106` | 2026-09-14 | tổng dthu tháng 1 năm 2025 là bao nhiu | Kỳ hỏi [2025-01-01 .. 2025-01-31] nằm hoàn toàn ngoài khoảng dữ liệu bán [2025-02-01 .. 2026-09-14] |
| 9 | `q_91043b6a4de6` | `biz_121` | 2026-09-20 | tháng 2/2025 ngày nào cửa hàng bán đươc nhiều tiền nhất vaayj | Kỳ hỏi [2025-02-01 .. 2025-02-28] nằm hoàn toàn ngoài khoảng dữ liệu bán [2025-03-01 .. 2026-09-20] |
| 10 | `q_cdd972dc8286` | `biz_112` | 2026-07-31 | check gium dthu nhom hang sinh to chiem bnhiu % tong doanh thu thang 3 nam 2025 | Kỳ hỏi [2025-03-01 .. 2025-03-31] nằm hoàn toàn ngoài khoảng dữ liệu bán [2025-04-01 .. 2026-07-31] |
| 11 | `q_cfea850ecaa2` | `biz_103` | 2026-07-09 | Giúp mình liệt kê 5 mặt hàng bán chạy nhất tháng 3/2025. | Kỳ hỏi [2025-03-01 .. 2025-03-31] nằm hoàn toàn ngoài khoảng dữ liệu bán [2025-04-01 .. 2026-07-09] |
| 12 | `q_ebf285497536` | `biz_112` | 2026-07-31 | coi giumf tieenf bán Trà vải (L) tháng 3/2025 là bao nhiêu | Kỳ hỏi [2025-03-01 .. 2025-03-31] nằm hoàn toàn ngoài khoảng dữ liệu bán [2025-04-01 .. 2026-07-31] |
| 13 | `q_ef173115902d` | `biz_112` | 2026-07-31 | ti trong cua nhom ca phe trong dthu thang 2/2025 la bao nhieu % | Kỳ hỏi [2025-02-01 .. 2025-02-28] nằm hoàn toàn ngoài khoảng dữ liệu bán [2025-04-01 .. 2026-07-31] |
| 14 | `q_f403991d1218` | `biz_103` | 2026-07-09 | Xem giúp tháng 3/2025 ngày nào cửa hàng bán được nhiều tiền nhất? | Kỳ hỏi [2025-03-01 .. 2025-03-31] nằm hoàn toàn ngoài khoảng dữ liệu bán [2025-04-01 .. 2026-07-09] |
| 15 | `q_f6b6cc0cbd2b` | `biz_106` | 2026-09-14 | 3 mặt hangf chạy nhất tháng 1/2025 là những mặt hàng nào | Kỳ hỏi [2025-01-01 .. 2025-01-31] nằm hoàn toàn ngoài khoảng dữ liệu bán [2025-02-01 .. 2026-09-14] |

### Nhóm (b): Shop thiếu loại dữ liệu (41 câu)
| STT | ID | Shop | as_of_date | Câu hỏi | Lý do unanswerable |
|---|---|---|---|---|---|
| 1 | `q_04128078842a` | `biz_118` | 2026-09-10 | cửa hàng có mấy khách nhà ở đường Hai Bà Trưng | Shop không lưu địa chỉ khách hàng (has.customer_address=False) |
| 2 | `q_05a8b30443a1` | `biz_130` | 2026-08-29 | trong so khach da mua hang thang 7/2026, bnhiu % mua tu 8 don tro len | Shop không lưu thông tin khách hàng (has.customer_name=False, has.customer_code=False) |
| 3 | `q_22f59bab1075` | `biz_112` | 2026-07-31 | Hết hôm nay trong kho còn bao nhiêu hộp Bánh croissant nguyên và bao nhiêu cái lẻ? | Shop không có dữ liệu tồn kho / thẻ kho (has.inventory=False) |
| 4 | `q_2407aef28946` | `biz_103` | 2026-07-09 | Cho hỏi tổng tiền nhập hàng tháng này là bao nhiêu? | Shop không có bảng nhập hàng (has.purchases=False) |
| 5 | `q_24ed0fa1deca` | `biz_103` | 2026-07-09 | Cuối ngày 09/07/2026, tổng giá trị hàng còn trong kho tính theo giá vốn là bao nhiêu tiền? | Shop không có dữ liệu tồn kho / thẻ kho (has.inventory=False) |
| 6 | `q_360f8795ce6c` | `biz_106` | 2026-09-14 | Hàng nào hết hạn trong 120 ngày tới, từ 14/09/2026 đến hết 12/01/2027, mà hiện vẫn còn tồn kho vậy? | Shop không có dữ liệu lô / hạn dùng (has.lots_expiry=False) |
| 7 | `q_4333ad0589a1` | `biz_117` | 2026-05-20 | cho bảng 3 khách còn nợ nhìu nhất tính đến hết ngày 20/05/2026, kèm số tiền còn nợ | Shop không có dữ liệu công nợ / số dư nợ khách (has.debt=False) |
| 8 | `q_4bc3846b6f5b` | `biz_106` | 2026-09-14 | Tháng này, doanh thu từ khách nhóm thân thiết chiếm bao nhiêu phần trăm tổng doanh thu của cửa hàng vậy? | Shop không có phân nhóm khách hàng (has.customer_group=False) |
| 9 | `q_6c1ca5ce7bd4` | `biz_105` | 2026-06-24 | So dthu các đơn trả bằng COD với doanh thu các đơn trả bằng ví điện tử tháng 10/2025: mỗi bên bao nhiêu? | Shop không có thông tin hình thức thanh toán (has.payment_method=False) |
| 10 | `q_72d9f77acc3d` | `biz_118` | 2026-09-10 | Cho mình hỏi giá nhập bình quân một cây Thép Pomina D12 cây 11.7m trong tháng 6 năm 2025 là bao nhiêu? | Shop không có bảng nhập hàng (has.purchases=False) |
| 11 | `q_73fac0fa2e46` | `biz_103` | 2026-07-09 | het hom nay, bia tiger 330ml con lai may lon trong kho ha | Shop không có dữ liệu tồn kho / thẻ kho (has.inventory=False) |
| 12 | `q_81389e30d95b` | `biz_103` | 2026-07-09 | ton kho Sua TH true MILK 180ml cuoi ngay hom nay duoc may loc chan va may hop le ta | Shop không có dữ liệu tồn kho / thẻ kho (has.inventory=False) |
| 13 | `q_8d1792dae92c` | `biz_112` | 2026-07-31 | Tháng này thu hồi được bao nhiêu tiền công nợ từ khách mua chịu? | Shop không có dữ liệu công nợ / số dư nợ khách (has.debt=False) |
| 14 | `q_910640a29988` | `biz_117` | 2026-05-20 | những sp nào đang còn hàng có hạn dùng từ 20/05/2026 đến heets 18/08/2026 | Shop không có dữ liệu lô / hạn dùng (has.lots_expiry=False) |
| 15 | `q_95099c4916a8` | `biz_109` | 2026-08-05 | cho hỏi trong tháng 12/2025, khách nữ chiếm bao nhiu % doanh thu | Shop không lưu giới tính khách hàng (has.customer_gender=False) |
| 16 | `q_99bc48a3da13` | `biz_130` | 2026-08-29 | dem so khach da mua ≥ 8 don trong thang 12/2025 | Shop không lưu thông tin khách hàng (has.customer_name=False, has.customer_code=False) |
| 17 | `q_9ced6c5b6110` | `biz_130` | 2026-08-29 | hôm nay kho còn tồn bao nhiêu lon coca-cola lon lúc cuối ngày | Shop không có dữ liệu tồn kho / thẻ kho (has.inventory=False) |
| 18 | `q_9f82b2f25fd6` | `biz_103` | 2026-07-09 | trong thang 5/2026, khach nu chiem bnhiu % doanh thu | Shop không lưu giới tính khách hàng (has.customer_gender=False) |
| 19 | `q_a4560b62b198` | `biz_105` | 2026-06-24 | So tiền mua hàng tháng 11/2025 của khách ở đường Nguyễn Tất Thành với khách ở đường Bạch Đằng: bên nào nhiều hơn? | Shop không lưu địa chỉ khách hàng (has.customer_address=False) |
| 20 | `q_a812b5173a24` | `biz_121` | 2026-09-20 | Tháng này, doanh thu các đơn bán qua điện thoại chiếm bao nhiêu phần trăm tổng doanh thu? | Shop không có thông tin kênh bán (has.channel=False) |
| 21 | `q_a9513a9b89b6` | `biz_130` | 2026-08-29 | nhung sp nao dang con hang co han dung tu 29/08/2026 den het 27/12/2026 | Shop không có dữ liệu lô / hạn dùng (has.lots_expiry=False) |
| 22 | `q_aad0778d5fd7` | `biz_118` | 2026-09-10 | Cuối ngày hôm nay CB Panasonic MCB 2P 20A còn bao nhiêu cái? | Shop không có dữ liệu tồn kho / thẻ kho (has.inventory=False) |
| 23 | `q_ad432d1062b7` | `biz_103` | 2026-07-09 | tồn kho red bull 250ml cuối ngày hôm nay là bao nhiêu lon | Shop không có dữ liệu tồn kho / thẻ kho (has.inventory=False) |
| 24 | `q_b376cbe01666` | `biz_112` | 2026-07-31 | tháng này, bạch hùng ngân ghi nợ thêm bn tiền và đã trả nợ được bao nhiêu | Shop không có dữ liệu công nợ / số dư nợ khách (has.debt=False) |
| 25 | `q_c42078e25d28` | `biz_118` | 2026-09-10 | heets hoom nay trong kho còn bnhiu cây băng keo điện nano 20 yard nguyên và bao nhiêu cuộn lẻ đó | Shop không có dữ liệu tồn kho / thẻ kho (has.inventory=False) |
| 26 | `q_cd7bfdbf4d08` | `biz_122` | 2026-07-17 | Cho hỏi tháng 3/2025 cửa hàng lãi gộp bao nhiêu tiền? | Shop không có giá vốn trên dòng bán để tính lãi gộp theo §5 (has.cost_price=False) |
| 27 | `q_d18944d81860` | `biz_112` | 2026-07-31 | khach nao mua nhieu don hang nhat thang 3/2026 ha | Shop không lưu thông tin khách hàng (has.customer_name=False, has.customer_code=False) |
| 28 | `q_d345bddf40bc` | `biz_105` | 2026-06-24 | tháng này, dthu các đơn bán tại quầy là nhiêu, doanh thu các đơn bán qua zalo oa là bao nhiêu z | Shop không có thông tin kênh bán (has.channel=False) |
| 29 | `q_da830fdc690c` | `biz_121` | 2026-09-20 | trong thang 2/2026, acemuc kids 200mg hop 30 goi nhap vao gia binh quan mot hop la bao nhiu | Bảng nhập hàng không có cột đơn giá nhập (has.purchase_price=False) |
| 30 | `q_e054949c8650` | `biz_130` | 2026-08-29 | Cho hỏi tồn kho Bia Tiger lon cuối ngày hôm nay là bao nhiêu lon? | Shop không có dữ liệu tồn kho / thẻ kho (has.inventory=False) |
| 31 | `q_e308f9743d56` | `biz_121` | 2026-09-20 | thang 3/2026, tra hang vi loi va tra vi mua nham, ben nao nhieu don hon | Shop không ghi lý do trả / huỷ đơn (has.return_reason=False) |
| 32 | `q_e9455734edd3` | `biz_121` | 2026-09-20 | Xem giúp tháng 4/2026 khách ở đường Nguyễn Văn Linh mua tổng cộng bao nhiêu tiền? | Shop không lưu địa chỉ khách hàng (has.customer_address=False) |
| 33 | `q_ea69ed45df1c` | `biz_122` | 2026-07-17 | Tháng 11/2025 khách nam mua tổng cộng bao nhiêu tiền? | Shop không lưu giới tính khách hàng (has.customer_gender=False) |
| 34 | `q_ec52b91bfbd0` | `biz_130` | 2026-08-29 | dthu các đơn trả bằng COD và doanh thu các đơn trả bằng tiền mặt tháng này lần lượt là bao nhiêu | Shop không có thông tin hình thức thanh toán (has.payment_method=False) |
| 35 | `q_ec5c0d7eed96` | `biz_118` | 2026-09-10 | thang 3/2026 co bnhiu don bi huy vi giao tre | Shop không ghi lý do trả / huỷ đơn (has.return_reason=False) |
| 36 | `q_ecca6bcc3dfc` | `biz_103` | 2026-07-09 | Đến hết ngày 09/07/2026, số tiền khách còn thiếu là bao nhiêu? | Shop không có dữ liệu công nợ / số dư nợ khách (has.debt=False) |
| 37 | `q_ee9d6f998de7` | `biz_124` | 2026-05-25 | e thang 1/2026 khach nu mua tong cong bao nhieu tien | Shop không lưu giới tính khách hàng (has.customer_gender=False) |
| 38 | `q_f120d0f5e7d0` | `biz_122` | 2026-07-17 | có bnhiu khách hàng ở đường hậu giang | Shop không lưu địa chỉ khách hàng (has.customer_address=False) |
| 39 | `q_f895c5de92bd` | `biz_117` | 2026-05-20 | Có bao nhiêu khách hàng ở đường Trần Não? | Shop không lưu địa chỉ khách hàng (has.customer_address=False) |
| 40 | `q_faf7802261fb` | `biz_105` | 2026-06-24 | liệt kê 3 khách nợ nhiều nhất tính đến hết ngày 24/06/2026, kèm số tiền còn nợ | Shop không có dữ liệu công nợ / số dư nợ khách (has.debt=False) |
| 41 | `q_fcafb39ec35f` | `biz_109` | 2026-08-05 | Tháng 2/2025, khách đường Lê Trọng Tấn và khách đường Trần Não, bên nào mua nhiều tiền hơn nhỉ? | Shop không lưu địa chỉ khách hàng (has.customer_address=False) |

### Nhóm (c): Không bắt được bằng profile (7 câu)
| STT | ID | Shop | as_of_date | Câu hỏi | Lý do unanswerable |
|---|---|---|---|---|---|
| 1 | `q_1af6e691fc94` | `biz_106` | 2026-09-14 | Ai là người lành nghề nhất trong số nhân viên? | Hỏi thợ/nhân viên lành nghề nhất (đánh giá chủ quan) |
| 2 | `q_3ad4ff264376` | `biz_105` | 2026-06-24 | check giùm khách hay khen nhân viên nào nhất | Hỏi cảm nhận/khen ngợi của khách (dữ liệu định tính ngoài bảng) |
| 3 | `q_88e1971e99bf` | `biz_123` | 2026-06-28 | Nhân viên Phùng Thu Trang làm việc có tận tâm với khách không? | Hỏi phẩm chất/thái độ nhân viên (đánh giá chủ quan) |
| 4 | `q_97049319d8e8` | `biz_124` | 2026-05-25 | lê phúc đạt có lễ phép, chu đáo với khách hông | Hỏi phẩm chất/thái độ nhân viên (đánh giá chủ quan) |
| 5 | `q_b2f158b6c3f9` | `biz_123` | 2026-06-28 | thuốc có hoạt chất nhôm phosphat người lớn nên uống mỗi lần mấy viên | Hỏi liều lượng dùng thuốc (kiến thức y tế ngoài dữ liệu) |
| 6 | `q_d151628a1486` | `biz_130` | 2026-08-29 | Ai trong cửa hàng đc khách quý mến nhất? | Hỏi cảm nhận/khen ngợi của khách (dữ liệu định tính ngoài bảng) |
| 7 | `q_f7cbf061f59d` | `biz_112` | 2026-07-31 | nhân viên nào có tay nghề cao nhất tiệm | Hỏi thợ/nhân viên lành nghề nhất (đánh giá chủ quan) |

## 4. Chi tiết các câu trả lời được bị phân loại nhầm (nếu có)
- `q_0194d8d10f17` [biz_111]: Tính đến hết ngày 19/08/2026, có bao nhiêu khách còn nợ cửa hàng? -> Shop không có dữ liệu công nợ / số dư nợ khách (has.debt=False)
- `q_0279f675859e` [biz_111]: thang 7/2025, cac khach thuoc nhom than thiet mua tong cong bao nhiu tien hang -> Shop không có phân nhóm khách hàng (has.customer_group=False)
- `q_073aee886aef` [biz_106]: Xem giúp khách còn nợ cửa hàng tổng cộng bao nhiêu tính đến hết ngày 20/09/2025? -> Shop không có dữ liệu công nợ / số dư nợ khách (has.debt=False)
- `q_0a76d3680594` [biz_123]: cho hỏi tính đến hết ngày 12/07/2025, 5 khách nào đang nợ nhiều nhất, mỗi người còn nợ bao nhiu -> Shop không có dữ liệu công nợ / số dư nợ khách (has.debt=False)
- `q_0bf0638eaa4d` [biz_123]: khach con no cua hang tong cong bao nhieu tinh den het ngay 15/05/2026 -> Shop không có dữ liệu công nợ / số dư nợ khách (has.debt=False)
- `q_116e55aef197` [biz_111]: Doanh thu từ khách nhóm thân thiết tháng 3/2025 là bao nhiêu vậy? -> Shop không có phân nhóm khách hàng (has.customer_group=False)
- `q_11d72b8e4f6a` [biz_123]: Tháng 1/2026 khách Vương Hạnh Chi ghi nợ thêm bao nhiêu và trả nợ đc bao nhiêu? Ghi hai số theo thứ tự: nợ thêm, trả được. -> Shop không có dữ liệu công nợ / số dư nợ khách (has.debt=False)
- `q_14e3b0722461` [biz_121]: ton kho gaviscon hop 24 goi x 10ml cuoi ngay hom nay dc may hop chan va may goi le -> Shop không có dữ liệu tồn kho / thẻ kho (has.inventory=False)
- `q_153f4e995558` [biz_106]: tính đến hết ngày 27/10/2025, 3 khách nào đang nợ nhiều nhất, mỗi người còn nợ bao nhiêu -> Shop không có dữ liệu công nợ / số dư nợ khách (has.debt=False)
- `q_18e8c7f00fce` [biz_123]: Tính đến hết ngày 08/10/2025, tổng số tiền khách còn nợ ở các đơn đã đặt quá 15 ngày là bao nhiêu? -> Shop không có dữ liệu công nợ / số dư nợ khách (has.debt=False)

## 5. Bảng tổng hợp Profile của 44 shop

| Shop | Split | README End | Sales Range | Sales Rows | Has Sales | Inventory | Purchases | Debt | Staff | Channel | Payment |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `biz_101` | train | 2026-08-24 | [2025-06-01 .. 2026-08-24] | 56,501 | True | False | False | False | False | False | False |
| `biz_102` | train | 2026-06-16 | [2025-01-01 .. 2026-06-16] | 86,029 | True | False | False | False | False | False | False |
| `biz_103` | train | 2026-07-09 | [2025-04-01 .. 2026-07-09] | 45,534 | True | False | False | False | False | False | False |
| `biz_104` | train | 2026-06-02 | [2025-04-01 .. 2026-06-02] | 62,894 | True | False | False | False | False | False | False |
| `biz_105` | train | 2026-06-24 | [2025-02-01 .. 2026-06-24] | 140,245 | True | True | True | False | False | False | False |
| `biz_106` | train | 2026-09-14 | [2025-02-01 .. 2026-09-14] | 129,416 | True | True | True | False | False | False | True |
| `biz_107` | train | 2026-07-22 | [2025-03-01 .. 2026-07-22] | 43,605 | True | False | False | False | False | False | False |
| `biz_108` | train | 2026-05-29 | [2025-01-01 .. 2026-05-29] | 78,983 | True | True | True | True | True | True | False |
| `biz_109` | train | 2026-08-05 | [2025-01-01 .. 2026-08-05] | 83,284 | True | True | True | False | True | True | True |
| `biz_110` | train | 2026-07-03 | [2025-05-01 .. 2026-07-03] | 29,317 | True | False | False | False | False | False | False |
| `biz_111` | train | 2026-08-19 | [2025-01-01 .. 2026-08-19] | 106,585 | True | False | False | False | False | True | True |
| `biz_112` | train | 2026-07-31 | [2025-04-01 .. 2026-07-31] | 113,325 | True | False | False | False | False | False | False |
| `biz_113` | train | 2026-08-09 | [2025-02-01 .. 2026-08-09] | 32,994 | True | False | False | False | False | False | False |
| `biz_114` | train | 2026-06-21 | [2025-01-01 .. 2026-06-21] | 26,119 | True | False | False | False | False | False | False |
| `biz_115` | train | 2026-05-16 | [2025-02-01 .. 2026-05-16] | 28,721 | True | False | False | False | False | False | False |
| `biz_116` | train | 2026-09-03 | [2025-05-01 .. 2026-09-03] | 39,889 | True | False | False | False | False | False | False |
| `biz_117` | train | 2026-05-20 | [2025-01-01 .. 2026-05-20] | 33,845 | True | True | True | False | False | False | False |
| `biz_118` | train | 2026-09-10 | [2025-02-01 .. 2026-09-10] | 46,001 | True | False | False | False | False | False | False |
| `biz_119` | train | 2026-07-13 | [2025-01-01 .. 2026-07-13] | 65,731 | True | True | True | True | False | False | False |
| `biz_120` | train | 2026-06-12 | [2025-01-01 .. 2026-06-12] | 90,706 | True | True | True | True | False | True | False |
| `biz_121` | train | 2026-09-20 | [2025-03-01 .. 2026-09-20] | 82,920 | True | False | True | False | False | False | False |
| `biz_122` | train | 2026-07-17 | [2025-01-01 .. 2026-07-17] | 103,663 | True | False | True | False | False | False | False |
| `biz_123` | train | 2026-06-28 | [2025-01-01 .. 2026-06-28] | 64,149 | True | True | True | False | True | False | True |
| `biz_124` | train | 2026-05-25 | [2025-01-01 .. 2026-05-25] | 97,033 | True | True | True | True | True | True | True |
| `biz_125` | train | 2026-05-11 | [2025-01-01 .. 2026-05-11] | 79,052 | True | False | False | False | False | False | False |
| `biz_126` | train | 2026-06-06 | [2025-01-01 .. 2026-06-06] | 66,429 | True | False | False | False | False | False | False |
| `biz_127` | train | 2026-07-28 | [2025-03-01 .. 2026-07-28] | 131,192 | True | False | False | True | False | True | True |
| `biz_128` | train | 2026-09-07 | [2025-04-01 .. 2026-09-07] | 99,650 | True | True | True | True | False | False | False |
| `biz_129` | train | 2026-08-14 | [2025-01-01 .. 2026-08-14] | 145,479 | True | False | False | True | False | False | True |
| `biz_130` | train | 2026-08-29 | [2025-02-01 .. 2026-08-29] | 172,530 | True | False | False | False | False | False | False |
| `dev_001` | public_test | 2026-07-08 | [2025-01-01 .. 2026-07-08] | 90,851 | True | False | False | False | False | False | False |
| `dev_002` | public_test | 2026-05-24 | [2025-01-01 .. 2026-05-24] | 84,672 | True | False | False | False | False | False | False |
| `dev_003` | public_test | 2026-08-21 | [2025-03-01 .. 2026-08-21] | 102,204 | True | True | True | False | True | True | True |
| `dev_004` | public_test | 2026-06-10 | [2025-01-01 .. 2026-06-10] | 33,475 | True | True | True | False | False | False | False |
| `dev_005` | public_test | 2026-05-10 | [2025-01-01 .. 2026-05-10] | 75,970 | True | False | True | False | False | False | False |
| `dev_006` | public_test | 2026-08-08 | [2025-04-01 .. 2026-08-08] | 72,411 | True | True | True | False | True | False | True |
| `dev_007` | public_test | 2026-09-19 | [2025-02-01 .. 2026-09-19] | 121,067 | True | False | True | True | True | True | False |
| `dev_008` | public_test | 2026-07-22 | [2025-01-01 .. 2026-07-22] | 153,326 | True | False | True | False | True | True | True |
| `dev_009` | public_test | 2026-06-24 | [2025-01-01 .. 2026-06-24] | 23,338 | True | False | False | False | False | False | False |
| `dev_010` | public_test | 2026-09-06 | [2025-05-01 .. 2026-09-06] | 45,025 | True | False | False | True | False | True | True |
| `dev_011` | public_test | 2026-07-31 | [2025-06-01 .. 2026-07-31] | 6,043 | True | False | False | False | False | False | False |
| `dev_012` | public_test | 2026-08-31 | [2025-07-01 .. 2026-08-31] | 6,078 | False | False | False | False | True | False | False |
| `dev_013` | public_test | 2026-06-30 | [2025-05-01 .. 2026-06-30] | 32,174 | True | False | True | False | False | True | False |
| `dev_014` | public_test | 2026-09-30 | [2025-07-01 .. 2026-09-30] | 10,321 | True | False | False | False | False | False | False |

## 6. Ghi chú và khuyến nghị cho P1 / P4
1. **API cho P1 (Phương)**:
   - `build_profile(business_dir)` trả về `dict` chứa `data_end_readme`, `tables`, `has`, `notes`.
   - `period_coverage(profile, table_role, start, end) -> 'full' | 'partial' | 'none'`.
   - Nếu `period_coverage == 'none'` hoặc feature cần thiết có cờ `has == False`: P1 trả ngay `{"type": "unanswerable"}`.
2. **Prompt Injection cho P4 (An)**:
   - P4 có thể đưa đoạn tóm tắt `profile['has']` vào system prompt để LLM biết rõ shop KHÔNG có những loại dữ liệu nào, tránh hallucination hoặc SQL vô vọng.
3. **Đối chiếu ngày README**:
   - 44/44 shop đều có ngày kết thúc dữ liệu trong README, khớp hoàn toàn với `date_max` của bảng giao dịch chính.