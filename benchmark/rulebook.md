# Quy tắc nghiệp vụ chung

## Doanh thu
Doanh thu là tổng giá trị tong_tien hoặc doanh_thu trong kỳ, chỉ tính đơn hoàn thành.
Đơn hủy (trang_thai = 'huỷ') không tính vào doanh thu.

## Lợi nhuận
Lợi nhuận gộp = (gia_ban - gia_nhap) * so_luong.
Nếu không có trường gia_nhap, không thể tính lợi nhuận.

## Thời gian
"Tháng 1" = 2026-01-01 đến 2026-01-31.
"Quý 1" = 2026-01-01 đến 2026-03-31.
"Tới ngày X" hoặc "đến ngày X" nghĩa là ngay <= 'YYYY-MM-DD'.
Ngày mặc định của "ngày 3/3" là 2026-03-03; "tháng 2" là năm 2026.

## Hàng bán chạy
Hàng bán chạy nhất theo số lượng: dùng SUM(so_luong), không phải SUM(doanh_thu).

## Phần trăm
Trả về số thực (ví dụ: 35.5 cho 35.5%), không nhân thêm 100.
