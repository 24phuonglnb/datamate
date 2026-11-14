# Load and Parse Audit Report (44 Shops)

- **Total shops audited**: 44
- **Total tables loaded**: 225
- **Total rows**: 5,324,050
- **Total load time**: 474.96s
- **Shops with `col_*` wildcard columns**: 0 (None)
- **Shops with unparsed cells in typed columns**: 3 (biz_117, dev_012, dev_014)
- **Shops with summary rows detected**: 13 (biz_104, biz_105, biz_107, biz_117, biz_130, dev_001, dev_002, dev_004, dev_007, dev_008, dev_012, dev_013, dev_014)

---

## 1. Shop & Table Summary

| Split | Shop | Load Time | Table | Rows | Cols | Sources | Summary Rows | Header/Wildcard Cols |
|---|---|---|---|---|---|---|---|---|
| train | biz_101 | 2.50s | `ban_hang` | 56,501 | 10 | ban_hang.csv | 0 | - |
| train | biz_102 | 9.42s | `DanhSachQuyDoi` | 77 | 4 | DanhSachQuyDoi.xlsx[Sheet1] | 0 | - |
| train | biz_102 | 9.42s | `DonHang_ChiTiet` | 86,029 | 9 | 18 files | 0 | - |
| train | biz_103 | 3.96s | `DanhSachQuyDoi` | 77 | 4 | DanhSachQuyDoi.xlsx[Sheet1] | 0 | - |
| train | biz_103 | 3.96s | `DonHang_ChiTiet` | 45,534 | 9 | 16 files | 0 | - |
| train | biz_104 | 6.56s | `DanhSachQuyDoi` | 2 | 4 | DanhSachQuyDoi.xlsx[Sheet1] | 0 | - |
| train | biz_104 | 6.56s | `DonHang_ChiTiet` | 62,894 | 9 | DonHang_ChiTiet.xlsx[Sheet1] | 443 | - |
| train | biz_105 | 15.18s | `BangGia` | 78 | 4 | BangGia.xlsx[Sheet1] | 0 | - |
| train | biz_105 | 15.18s | `DanhMuc` | 2 | 4 | DanhMuc.xlsx[Sheet1] | 0 | - |
| train | biz_105 | 15.18s | `SoBanHang` | 140,245 | 10 | 17 files | 40 | - |
| train | biz_105 | 15.18s | `SoNhapHang` | 1,373 | 9 | SoNhapHang.xlsx[Sheet1] | 0 | - |
| train | biz_105 | 15.18s | `TonKho` | 50 | 3 | TonKho.xlsx[Sheet1] | 0 | - |
| train | biz_106 | 27.89s | `BaoCaoTonKho` | 50 | 4 | BaoCaoTonKho.xlsx[Sheet1] | 0 | - |
| train | biz_106 | 27.89s | `DanhSachChiTietNhapHang` | 1,562 | 6 | DanhSachChiTietNhapHang.xlsx[Sheet1] | 0 | - |
| train | biz_106 | 27.89s | `DanhSachDonViTinh` | 2 | 4 | DanhSachDonViTinh.xlsx[Sheet1] | 0 | - |
| train | biz_106 | 27.89s | `DanhSachHoaDon` | 78,847 | 12 | DanhSachHoaDon.xlsx[Sheet1] | 0 | - |
| train | biz_106 | 27.89s | `DanhSachHoaDonChiTiet` | 129,416 | 11 | DanhSachHoaDonChiTiet_1.xlsx[Sheet1]<br>DanhSachHoaDonChiTiet_2.xlsx[Sheet1] | 0 | - |
| train | biz_106 | 27.89s | `DanhSachKhachHang` | 240 | 14 | DanhSachKhachHang.xlsx[Sheet1] | 0 | - |
| train | biz_106 | 27.89s | `DanhSachNhapHang` | 513 | 6 | DanhSachNhapHang.xlsx[Sheet1] | 0 | - |
| train | biz_106 | 27.89s | `DanhSachSanPham` | 50 | 23 | DanhSachSanPham.xlsx[Sheet1] | 0 | - |
| train | biz_106 | 27.89s | `SoQuy` | 78,673 | 5 | SoQuy.xlsx[Sheet1] | 0 | - |
| train | biz_107 | 3.60s | `SoBanHang` | 43,605 | 8 | SoBanHang.xlsx[Sheet1] | 526 | - |
| train | biz_108 | 11.89s | `BaoCaoTonKho` | 60 | 4 | BaoCaoTonKho.xlsx[Sheet1] | 0 | - |
| train | biz_108 | 11.89s | `DanhSachChiTietNhapHang` | 2,293 | 6 | DanhSachChiTietNhapHang.xlsx[Sheet1] | 0 | - |
| train | biz_108 | 11.89s | `DanhSachHoaDon` | 31,501 | 14 | DanhSachHoaDon.xlsx[Sheet1] | 0 | - |
| train | biz_108 | 11.89s | `DanhSachHoaDonChiTiet` | 78,983 | 10 | DanhSachHoaDonChiTiet.xlsx[Sheet1] | 0 | - |
| train | biz_108 | 11.89s | `DanhSachKhachHang` | 300 | 16 | DanhSachKhachHang.xlsx[Sheet1] | 0 | - |
| train | biz_108 | 11.89s | `DanhSachNhapHang` | 499 | 6 | DanhSachNhapHang.xlsx[Sheet1] | 0 | - |
| train | biz_108 | 11.89s | `DanhSachSanPham` | 60 | 18 | DanhSachSanPham.xlsx[Sheet1] | 0 | - |
| train | biz_109 | 15.67s | `DanhSachHoaDonChiTiet` | 83,284 | 11 | DanhSachHoaDonChiTiet.xlsx[Sheet1] | 0 | - |
| train | biz_109 | 15.67s | `DuLieuBanHang/DanhSachHoaDon` | 33,065 | 14 | DuLieuBanHang.xlsx[DanhSachHoaDon] | 0 | - |
| train | biz_109 | 15.67s | `DuLieuBanHang/DanhSachSanPham` | 60 | 18 | DuLieuBanHang.xlsx[DanhSachSanPham] | 0 | - |
| train | biz_109 | 15.67s | `DuLieuBanHang/DanhSachKhachHang` | 320 | 13 | DuLieuBanHang.xlsx[DanhSachKhachHang] | 0 | - |
| train | biz_109 | 15.67s | `DuLieuBanHang/BaoCaoTonKho` | 60 | 4 | DuLieuBanHang.xlsx[BaoCaoTonKho] | 0 | - |
| train | biz_109 | 15.67s | `DuLieuBanHang/DanhSachNhapHang` | 561 | 6 | DuLieuBanHang.xlsx[DanhSachNhapHang] | 0 | - |
| train | biz_109 | 15.67s | `DuLieuBanHang/DanhSachChiTietNhapHang` | 2,225 | 6 | DuLieuBanHang.xlsx[DanhSachChiTietNhapHang] | 0 | - |
| train | biz_109 | 15.67s | `DuLieuBanHang/SoQuy` | 36,974 | 5 | DuLieuBanHang.xlsx[SoQuy] | 0 | - |
| train | biz_109 | 15.67s | `DuLieuBanHang/DanhSachDonViTinh` | 77 | 4 | DuLieuBanHang.xlsx[DanhSachDonViTinh] | 0 | - |
| train | biz_110 | 1.00s | `danh_sach_hoa_don` | 29,317 | 8 | danh_sach_hoa_don.csv | 0 | - |
| train | biz_111 | 7.00s | `chi_tiet_don` | 106,585 | 8 | chi_tiet_don.csv | 0 | - |
| train | biz_111 | 7.00s | `don_hang` | 66,469 | 9 | don_hang.csv | 0 | - |
| train | biz_111 | 7.00s | `khach_hang` | 200 | 15 | khach_hang.csv | 0 | - |
| train | biz_111 | 7.00s | `san_pham` | 50 | 18 | san_pham.csv | 0 | - |
| train | biz_111 | 7.00s | `thanh_toan` | 66,195 | 5 | thanh_toan.csv | 0 | - |
| train | biz_112 | 10.79s | `Danh sách hàng hóa` | 50 | 16 | Danh sách hàng hóa.xlsx[Sheet1] | 0 | - |
| train | biz_112 | 10.79s | `So_chi_tiet_ban_hang` | 113,325 | 9 | 16 files | 0 | - |
| train | biz_113 | 2.62s | `SoBanHang` | 32,994 | 8 | SoBanHang.xlsx[Sheet1] | 0 | - |
| train | biz_114 | 1.16s | `ban_hang` | 26,119 | 10 | ban_hang.csv | 0 | - |
| train | biz_115 | 5.38s | `Bảng kê phiếu giao hàng` | 24,877 | 8 | Bảng kê phiếu giao hàng.xlsx[Sheet1] | 0 | - |
| train | biz_115 | 5.38s | `Chi tiết công nợ theo hạn` | 2,304 | 3 | Chi tiết công nợ theo hạn.xlsx[Sheet1] | 0 | - |
| train | biz_115 | 5.38s | `Danh sách hàng hóa` | 60 | 15 | Danh sách hàng hóa.xlsx[Sheet1] | 0 | - |
| train | biz_115 | 5.38s | `So_chi_tiet_ban_hang` | 28,721 | 10 | 16 files | 0 | - |
| train | biz_116 | 7.41s | `Bao_cao_ban_hang/So_chi_tiet_ban_hang` | 39,889 | 10 | Bao_cao_ban_hang.xlsx[So_chi_tiet_ban_hang] | 0 | - |
| train | biz_116 | 7.41s | `Bao_cao_ban_hang/Danh sách hàng hóa` | 55 | 17 | Bao_cao_ban_hang.xlsx[Danh sách hàng hóa] | 0 | - |
| train | biz_116 | 7.41s | `Bao_cao_ban_hang/Bảng kê phiếu giao hàng` | 35,370 | 8 | Bao_cao_ban_hang.xlsx[Bảng kê phiếu giao hàng] | 0 | - |
| train | biz_116 | 7.41s | `Bao_cao_ban_hang/Chi tiết công nợ theo hạn` | 3,803 | 3 | Bao_cao_ban_hang.xlsx[Chi tiết công nợ theo hạn] | 0 | - |
| train | biz_117 | 6.39s | `BangGia` | 100 | 4 | BangGia.xlsx[Sheet1] | 0 | - |
| train | biz_117 | 6.39s | `DanhMuc` | 14 | 4 | DanhMuc.xlsx[Sheet1] | 0 | - |
| train | biz_117 | 6.39s | `SoBanHang` | 33,845 | 10 | 17 files | 40 | - |
| train | biz_117 | 6.39s | `SoGiaoHang` | 28,411 | 8 | SoGiaoHang.xlsx[Sheet1] | 0 | - |
| train | biz_117 | 6.39s | `SoHanNo` | 2,722 | 3 | SoHanNo.xlsx[Sheet1] | 0 | - |
| train | biz_117 | 6.39s | `SoNhapHang` | 1,134 | 9 | SoNhapHang.xlsx[Sheet1] | 0 | - |
| train | biz_117 | 6.39s | `TonKho` | 60 | 3 | TonKho.xlsx[Sheet1] | 0 | - |
| train | biz_118 | 8.91s | `Bảng kê phiếu giao hàng` | 41,198 | 8 | Bảng kê phiếu giao hàng.xlsx[Sheet1] | 0 | - |
| train | biz_118 | 8.91s | `Chi tiết công nợ theo hạn` | 4,915 | 3 | Chi tiết công nợ theo hạn.xlsx[Sheet1] | 0 | - |
| train | biz_118 | 8.91s | `Danh sách hàng hóa` | 55 | 16 | Danh sách hàng hóa.xlsx[Sheet1] | 0 | - |
| train | biz_118 | 8.91s | `So_chi_tiet_ban_hang` | 46,001 | 10 | 20 files | 0 | - |
| train | biz_119 | 13.20s | `BaoCaoTonKho` | 70 | 4 | BaoCaoTonKho.xlsx[Sheet1] | 0 | - |
| train | biz_119 | 13.20s | `DanhSachChiTietNhapHang` | 3,122 | 8 | DanhSachChiTietNhapHang.xlsx[Sheet1] | 0 | - |
| train | biz_119 | 13.20s | `DanhSachHoaDon` | 34,047 | 11 | 19 files | 0 | - |
| train | biz_119 | 13.20s | `DanhSachHoaDonChiTiet` | 65,731 | 9 | DanhSachHoaDonChiTiet.xlsx[Sheet1] | 0 | - |
| train | biz_119 | 13.20s | `DanhSachHoaDonChiTietLo` | 65,483 | 5 | DanhSachHoaDonChiTietLo.xlsx[Sheet1] | 0 | - |
| train | biz_119 | 13.20s | `DanhSachKhachHang` | 300 | 12 | DanhSachKhachHang.xlsx[Sheet1] | 0 | - |
| train | biz_119 | 13.20s | `DanhSachLoHang` | 3,122 | 5 | DanhSachLoHang.xlsx[Sheet1] | 0 | - |
| train | biz_119 | 13.20s | `DanhSachNhapHang` | 554 | 6 | DanhSachNhapHang.xlsx[Sheet1] | 0 | - |
| train | biz_119 | 13.20s | `DanhSachSanPham` | 70 | 20 | DanhSachSanPham.xlsx[Sheet1] | 0 | - |
| train | biz_119 | 13.20s | `DanhSachThuoc` | 70 | 3 | DanhSachThuoc.xlsx[Sheet1] | 0 | - |
| train | biz_120 | 17.72s | `BaoCaoTonKho` | 80 | 4 | BaoCaoTonKho.xlsx[Sheet1] | 0 | - |
| train | biz_120 | 17.72s | `DanhSachChiTietNhapHang` | 3,866 | 8 | DanhSachChiTietNhapHang.xlsx[Sheet1] | 0 | - |
| train | biz_120 | 17.72s | `DanhSachHoaDon` | 48,389 | 12 | 18 files | 0 | - |
| train | biz_120 | 17.72s | `DanhSachHoaDonChiTiet` | 90,706 | 8 | DanhSachHoaDonChiTiet.xlsx[Sheet1] | 0 | - |
| train | biz_120 | 17.72s | `DanhSachHoaDonChiTietLo` | 92,759 | 5 | DanhSachHoaDonChiTietLo.xlsx[Sheet1] | 0 | - |
| train | biz_120 | 17.72s | `DanhSachKhachHang` | 350 | 12 | DanhSachKhachHang.xlsx[Sheet1] | 0 | - |
| train | biz_120 | 17.72s | `DanhSachLoHang` | 3,866 | 5 | DanhSachLoHang.xlsx[Sheet1] | 0 | - |
| train | biz_120 | 17.72s | `DanhSachNhapHang` | 526 | 6 | DanhSachNhapHang.xlsx[Sheet1] | 0 | - |
| train | biz_120 | 17.72s | `DanhSachSanPham` | 80 | 17 | DanhSachSanPham.xlsx[Sheet1] | 0 | - |
| train | biz_120 | 17.72s | `DanhSachThuoc` | 80 | 3 | DanhSachThuoc.xlsx[Sheet1] | 0 | - |
| train | biz_121 | 10.80s | `DonHang_ChiTiet` | 82,920 | 9 | DonHang_ChiTiet.xlsx[Sheet1] | 0 | - |
| train | biz_121 | 10.80s | `DuLieuXuat/DanhSachQuyDoi` | 83 | 4 | DuLieuXuat.xlsx[DanhSachQuyDoi] | 0 | - |
| train | biz_121 | 10.80s | `DuLieuXuat/DanhSachSanPham` | 80 | 17 | DuLieuXuat.xlsx[DanhSachSanPham] | 0 | - |
| train | biz_121 | 10.80s | `DuLieuXuat/DonNhapHang` | 566 | 3 | DuLieuXuat.xlsx[DonNhapHang] | 0 | - |
| train | biz_121 | 10.80s | `DuLieuXuat/DonNhapHang_ChiTiet` | 3,665 | 5 | DuLieuXuat.xlsx[DonNhapHang_ChiTiet] | 0 | - |
| train | biz_121 | 10.80s | `DuLieuXuat/DonHang_Lo` | 84,745 | 4 | DuLieuXuat.xlsx[DonHang_Lo] | 0 | - |
| train | biz_121 | 10.80s | `DuLieuXuat/DanhSachThuoc` | 80 | 3 | DuLieuXuat.xlsx[DanhSachThuoc] | 0 | - |
| train | biz_122 | 13.39s | `DanhSachQuyDoi` | 83 | 4 | DanhSachQuyDoi.xlsx[Sheet1] | 0 | - |
| train | biz_122 | 13.39s | `DanhSachSanPham` | 75 | 18 | DanhSachSanPham.xlsx[Sheet1] | 0 | - |
| train | biz_122 | 13.39s | `DanhSachThuoc` | 75 | 3 | DanhSachThuoc.xlsx[Sheet1] | 0 | - |
| train | biz_122 | 13.39s | `DonHang_ChiTiet` | 103,663 | 9 | 19 files | 0 | - |
| train | biz_122 | 13.39s | `DonHang_Lo` | 105,799 | 4 | DonHang_Lo_1.xlsx[Sheet1]<br>DonHang_Lo_2.xlsx[Sheet1] | 0 | - |
| train | biz_122 | 13.39s | `DonNhapHang` | 560 | 3 | DonNhapHang.xlsx[Sheet1] | 0 | - |
| train | biz_122 | 13.39s | `DonNhapHang_ChiTiet` | 4,051 | 5 | DonNhapHang_ChiTiet.xlsx[Sheet1] | 0 | - |
| train | biz_123 | 0.93s | `chi_nhanh` | 1 | 5 | pos.sqlite:chi_nhanh | 0 | - |
| train | biz_123 | 0.93s | `chi_tiet_don` | 64,149 | 11 | pos.sqlite:chi_tiet_don | 0 | - |
| train | biz_123 | 0.93s | `chi_tiet_don_lo` | 64,422 | 6 | pos.sqlite:chi_tiet_don_lo | 0 | - |
| train | biz_123 | 0.93s | `chi_tiet_nhap` | 2,953 | 9 | pos.sqlite:chi_tiet_nhap | 0 | - |
| train | biz_123 | 0.93s | `don_hang` | 33,630 | 22 | pos.sqlite:don_hang | 0 | - |
| train | biz_123 | 0.93s | `don_vi_sp` | 83 | 5 | pos.sqlite:don_vi_sp | 0 | - |
| train | biz_123 | 0.93s | `khach_hang` | 300 | 18 | pos.sqlite:khach_hang | 0 | - |
| train | biz_123 | 0.93s | `lich_su_gia` | 109 | 4 | pos.sqlite:lich_su_gia | 0 | - |
| train | biz_123 | 0.93s | `lo_hang` | 2,953 | 7 | pos.sqlite:lo_hang | 0 | - |
| train | biz_123 | 0.93s | `nha_cung_cap` | 5 | 5 | pos.sqlite:nha_cung_cap | 0 | - |
| train | biz_123 | 0.93s | `nhan_vien` | 3 | 7 | pos.sqlite:nhan_vien | 0 | - |
| train | biz_123 | 0.93s | `phieu_nhap` | 540 | 8 | pos.sqlite:phieu_nhap | 0 | - |
| train | biz_123 | 0.93s | `san_pham` | 80 | 22 | pos.sqlite:san_pham | 0 | - |
| train | biz_123 | 0.93s | `thanh_toan` | 33,816 | 7 | pos.sqlite:thanh_toan | 0 | - |
| train | biz_123 | 0.93s | `the_kho` | 65,514 | 10 | pos.sqlite:the_kho | 0 | - |
| train | biz_123 | 0.93s | `thong_tin_thuoc` | 80 | 4 | pos.sqlite:thong_tin_thuoc | 0 | - |
| train | biz_123 | 0.93s | `tra_hang` | 273 | 7 | pos.sqlite:tra_hang | 0 | - |
| train | biz_124 | 25.80s | `BanHang_BanTheoLo` | 97,880 | 5 | BanHang_BanTheoLo.xlsx[Sheet1] | 0 | - |
| train | biz_124 | 25.80s | `BanHang_ChiTietHoaDon` | 97,033 | 11 | BanHang_ChiTietHoaDon.xlsx[Sheet1] | 0 | - |
| train | biz_124 | 25.80s | `BanHang_DonViQuyDoi` | 83 | 4 | BanHang_DonViQuyDoi.xlsx[Sheet1] | 0 | - |
| train | biz_124 | 25.80s | `BanHang_HangHoa` | 80 | 16 | BanHang_HangHoa.xlsx[Sheet1] | 0 | - |
| train | biz_124 | 25.80s | `BanHang_HoaDon` | 51,044 | 14 | BanHang_HoaDon.xlsx[Sheet1] | 0 | - |
| train | biz_124 | 25.80s | `BanHang_KhachHang` | 380 | 15 | BanHang_KhachHang.xlsx[Sheet1] | 0 | - |
| train | biz_124 | 25.80s | `BanHang_LichSuGia` | 114 | 5 | BanHang_LichSuGia.xlsx[Sheet1] | 0 | - |
| train | biz_124 | 25.80s | `BanHang_LoHang` | 3,943 | 5 | BanHang_LoHang.xlsx[Sheet1] | 0 | - |
| train | biz_124 | 25.80s | `BanHang_PhieuThu` | 51,238 | 5 | BanHang_PhieuThu.xlsx[Sheet1] | 0 | - |
| train | biz_124 | 25.80s | `BanHang_Thuoc` | 80 | 3 | BanHang_Thuoc.xlsx[Sheet1] | 0 | - |
| train | biz_124 | 25.80s | `SoTay_ChiPhi` | 75 | 4 | SoTay_ChiPhi.xlsx[Sheet1] | 0 | - |
| train | biz_124 | 25.80s | `SoTay_NhapHang` | 3,943 | 11 | SoTay_NhapHang.xlsx[Sheet1] | 0 | - |
| train | biz_124 | 25.80s | `ton_kho` | 80 | 4 | ton_kho.csv | 0 | - |
| train | biz_125 | 3.55s | `ban_hang` | 79,052 | 10 | ban_hang.csv | 0 | - |
| train | biz_126 | 5.51s | `SoBanHang` | 66,429 | 8 | SoBanHang.xlsx[Sheet1] | 0 | - |
| train | biz_127 | 5.93s | `chi_tiet_don` | 131,192 | 8 | chi_tiet_don.csv | 0 | - |
| train | biz_127 | 5.93s | `don_hang` | 33,874 | 10 | don_hang.csv | 0 | - |
| train | biz_127 | 5.93s | `khach_hang` | 200 | 14 | khach_hang.csv | 0 | - |
| train | biz_127 | 5.93s | `san_pham` | 61 | 17 | san_pham.csv | 0 | - |
| train | biz_127 | 5.93s | `thanh_toan` | 33,473 | 5 | thanh_toan.csv | 0 | - |
| train | biz_128 | 12.83s | `BaoCaoTonKho` | 55 | 4 | BaoCaoTonKho.xlsx[Sheet1] | 0 | - |
| train | biz_128 | 12.83s | `DanhSachChiTietNhapHang` | 1,454 | 6 | DanhSachChiTietNhapHang.xlsx[Sheet1] | 0 | - |
| train | biz_128 | 12.83s | `DanhSachHoaDon` | 26,505 | 11 | 18 files | 0 | - |
| train | biz_128 | 12.83s | `DanhSachHoaDonChiTiet` | 99,650 | 9 | DanhSachHoaDonChiTiet.xlsx[Sheet1] | 0 | - |
| train | biz_128 | 12.83s | `DanhSachHoaDonPhongBan` | 23,880 | 4 | DanhSachHoaDonPhongBan.xlsx[Sheet1] | 0 | - |
| train | biz_128 | 12.83s | `DanhSachKhachHang` | 180 | 17 | DanhSachKhachHang.xlsx[Sheet1] | 0 | - |
| train | biz_128 | 12.83s | `DanhSachNhapHang` | 479 | 6 | DanhSachNhapHang.xlsx[Sheet1] | 0 | - |
| train | biz_128 | 12.83s | `DanhSachSanPham` | 56 | 19 | DanhSachSanPham.xlsx[Sheet1] | 0 | - |
| train | biz_129 | 7.14s | `chi_tiet_don` | 145,479 | 9 | chi_tiet_don.csv | 0 | - |
| train | biz_129 | 7.14s | `don_hang` | 38,499 | 8 | don_hang.csv | 0 | - |
| train | biz_129 | 7.14s | `khach_hang` | 220 | 15 | khach_hang.csv | 0 | - |
| train | biz_129 | 7.14s | `san_pham` | 61 | 18 | san_pham.csv | 0 | - |
| train | biz_129 | 7.14s | `thanh_toan` | 38,072 | 5 | thanh_toan.csv | 0 | - |
| train | biz_130 | 16.89s | `Danh sách hàng hóa` | 61 | 16 | Danh sách hàng hóa.xlsx[Sheet1] | 0 | - |
| train | biz_130 | 16.89s | `So_chi_tiet_ban_hang` | 172,530 | 9 | So_chi_tiet_ban_hang_1.xlsx[Sheet1]<br>So_chi_tiet_ban_hang_2.xlsx[Sheet1] | 594 | - |
| public_test | dev_001 | 9.91s | `Danh sách hàng hóa` | 60 | 19 | Danh sách hàng hóa.xlsx[Sheet1] | 0 | - |
| public_test | dev_001 | 9.91s | `So_chi_tiet_ban_hang` | 90,851 | 10 | So_chi_tiet_ban_hang.xlsx[Sheet1] | 554 | - |
| public_test | dev_002 | 8.91s | `BanHang` | 84,672 | 9 | 17 files | 526 | - |
| public_test | dev_002 | 8.91s | `DanhSachQuyDoi` | 2 | 4 | DanhSachQuyDoi.xlsx[Sheet1] | 0 | - |
| public_test | dev_003 | 29.70s | `BanHang_PhieuThu` | 62,580 | 5 | BanHang_PhieuThu.xlsx[Sheet1] | 0 | - |
| public_test | dev_003 | 29.70s | `BanHang_TongHop` | 102,204 | 26 | BanHang_TongHop_2025.xlsx[BanHang]<br>BanHang_TongHop_2026.xlsx[BanHang] | 0 | - |
| public_test | dev_003 | 29.70s | `BanHang_TongHop_2025/BanHang_HangHoa` | 50 | 18 | BanHang_TongHop_2025.xlsx[BanHang_HangHoa] | 0 | - |
| public_test | dev_003 | 29.70s | `BanHang_TongHop_2025/BanHang_KhachHang` | 220 | 17 | BanHang_TongHop_2025.xlsx[BanHang_KhachHang] | 0 | - |
| public_test | dev_003 | 29.70s | `BanHang_TongHop_2025/BanHang_DonViQuyDoi` | 2 | 4 | BanHang_TongHop_2025.xlsx[BanHang_DonViQuyDoi] | 0 | - |
| public_test | dev_003 | 29.70s | `BanHang_TongHop_2025/BanHang_LichSuGia` | 79 | 5 | BanHang_TongHop_2025.xlsx[BanHang_LichSuGia] | 0 | - |
| public_test | dev_003 | 29.70s | `BaoCaoCa` | 1,078 | 6 | BaoCaoCa.xlsx[Sheet1] | 0 | - |
| public_test | dev_003 | 29.70s | `SoTay_ChiPhi` | 77 | 4 | SoTay_ChiPhi.xlsx[Sheet1] | 0 | - |
| public_test | dev_003 | 29.70s | `SoTay_NhapHang` | 1,484 | 9 | SoTay_NhapHang.xlsx[Sheet1] | 0 | - |
| public_test | dev_003 | 29.70s | `ton_kho` | 50 | 4 | ton_kho.csv | 0 | - |
| public_test | dev_004 | 6.00s | `BangGia` | 99 | 4 | BangGia.xlsx[Sheet1] | 0 | - |
| public_test | dev_004 | 6.00s | `DanhMuc` | 14 | 4 | DanhMuc.xlsx[Sheet1] | 0 | - |
| public_test | dev_004 | 6.00s | `SoBanHang` | 33,475 | 11 | 18 files | 45 | - |
| public_test | dev_004 | 6.00s | `SoGiaoHang` | 28,398 | 8 | SoGiaoHang.xlsx[Sheet1] | 0 | - |
| public_test | dev_004 | 6.00s | `SoHanNo` | 2,568 | 3 | SoHanNo.xlsx[Sheet1] | 0 | - |
| public_test | dev_004 | 6.00s | `SoNhapHang` | 1,070 | 9 | SoNhapHang.xlsx[Sheet1] | 0 | - |
| public_test | dev_004 | 6.00s | `TonKho` | 60 | 3 | TonKho.xlsx[Sheet1] | 0 | - |
| public_test | dev_005 | 10.03s | `BanHang` | 75,970 | 9 | 17 files | 0 | - |
| public_test | dev_005 | 10.03s | `DanhSachQuyDoi` | 83 | 4 | DanhSachQuyDoi.xlsx[Sheet1] | 0 | - |
| public_test | dev_005 | 10.03s | `DanhSachSanPham` | 80 | 18 | DanhSachSanPham.xlsx[Sheet1] | 0 | - |
| public_test | dev_005 | 10.03s | `DanhSachThuoc` | 80 | 3 | DanhSachThuoc.xlsx[Sheet1] | 0 | - |
| public_test | dev_005 | 10.03s | `DonHang_Lo` | 77,653 | 4 | DonHang_Lo.xlsx[Sheet1] | 0 | - |
| public_test | dev_005 | 10.03s | `DonNhapHang` | 492 | 3 | DonNhapHang.xlsx[Sheet1] | 0 | - |
| public_test | dev_005 | 10.03s | `DonNhapHang_ChiTiet` | 3,312 | 5 | DonNhapHang_ChiTiet.xlsx[Sheet1] | 0 | - |
| public_test | dev_006 | 1.01s | `chi_nhanh` | 1 | 5 | pos.sqlite:chi_nhanh | 0 | - |
| public_test | dev_006 | 1.01s | `chi_tiet_don` | 72,411 | 11 | pos.sqlite:chi_tiet_don | 0 | - |
| public_test | dev_006 | 1.01s | `chi_tiet_don_lo` | 72,710 | 6 | pos.sqlite:chi_tiet_don_lo | 0 | - |
| public_test | dev_006 | 1.01s | `chi_tiet_nhap` | 3,234 | 9 | pos.sqlite:chi_tiet_nhap | 0 | - |
| public_test | dev_006 | 1.01s | `don_hang` | 37,833 | 22 | pos.sqlite:don_hang | 0 | - |
| public_test | dev_006 | 1.01s | `don_vi_sp` | 83 | 5 | pos.sqlite:don_vi_sp | 0 | - |
| public_test | dev_006 | 1.01s | `khach_hang` | 320 | 18 | pos.sqlite:khach_hang | 0 | - |
| public_test | dev_006 | 1.01s | `lich_su_gia` | 120 | 4 | pos.sqlite:lich_su_gia | 0 | - |
| public_test | dev_006 | 1.01s | `lo_hang` | 3,234 | 7 | pos.sqlite:lo_hang | 0 | - |
| public_test | dev_006 | 1.01s | `nha_cung_cap` | 5 | 10 | pos.sqlite:nha_cung_cap | 0 | - |
| public_test | dev_006 | 1.01s | `nhan_vien` | 3 | 7 | pos.sqlite:nhan_vien | 0 | - |
| public_test | dev_006 | 1.01s | `phieu_nhap` | 494 | 8 | pos.sqlite:phieu_nhap | 0 | - |
| public_test | dev_006 | 1.01s | `san_pham` | 80 | 25 | pos.sqlite:san_pham | 0 | - |
| public_test | dev_006 | 1.01s | `thanh_toan` | 37,939 | 7 | pos.sqlite:thanh_toan | 0 | - |
| public_test | dev_006 | 1.01s | `the_kho` | 73,901 | 10 | pos.sqlite:the_kho | 0 | - |
| public_test | dev_006 | 1.01s | `thong_tin_thuoc` | 80 | 4 | pos.sqlite:thong_tin_thuoc | 0 | - |
| public_test | dev_006 | 1.01s | `tra_hang` | 352 | 7 | pos.sqlite:tra_hang | 0 | - |
| public_test | dev_007 | 15.12s | `chi_tiet_hoa_don` | 121,067 | 30 | chi_tiet_hoa_don.csv | 616 | - |
| public_test | dev_007 | 15.12s | `chi_tiet_nhap_hang` | 1,731 | 13 | chi_tiet_nhap_hang.csv | 0 | - |
| public_test | dev_007 | 15.12s | `danh_muc_hang` | 61 | 9 | danh_muc_hang.csv | 0 | - |
| public_test | dev_008 | 42.59s | `ChiTietHoaDon` | 153,326 | 32 | ChiTietHoaDon_1.xlsx[Sheet1]<br>ChiTietHoaDon_2.xlsx[Sheet1] | 587 | - |
| public_test | dev_008 | 42.59s | `ChiTietNhapHang` | 1,836 | 13 | ChiTietNhapHang.xlsx[Sheet1] | 0 | - |
| public_test | dev_008 | 42.59s | `DanhMucHang` | 61 | 8 | DanhMucHang.xlsx[Sheet1] | 0 | - |
| public_test | dev_009 | 0.90s | `danh_sach_hoa_don` | 23,338 | 8 | danh_sach_hoa_don.csv | 0 | - |
| public_test | dev_010 | 3.14s | `chi_tiet_don` | 45,025 | 9 | chi_tiet_don.csv | 0 | - |
| public_test | dev_010 | 3.14s | `don_hang` | 25,702 | 11 | don_hang.csv | 0 | - |
| public_test | dev_010 | 3.14s | `khach_hang` | 260 | 13 | khach_hang.csv | 0 | - |
| public_test | dev_010 | 3.14s | `san_pham` | 60 | 17 | san_pham.csv | 0 | - |
| public_test | dev_010 | 3.14s | `thanh_toan` | 26,246 | 5 | thanh_toan.csv | 0 | - |
| public_test | dev_011 | 0.43s | `SoBanHang/Ghi tắt` | 59 | 3 | SoBanHang.xlsx[Ghi tắt] | 0 | - |
| public_test | dev_011 | 0.43s | `SoBanHang/Sổ bán hàng` | 6,043 | 12 | SoBanHang.xlsx[Sổ bán hàng] | 0 | - |
| public_test | dev_012 | 0.37s | `DanhSachTho` | 4 | 3 | DanhSachTho.xlsx[Sheet1] | 0 | - |
| public_test | dev_012 | 0.37s | `SoSuaXe` | 6,078 | 6 | 14 files | 18 | - |
| public_test | dev_013 | 2.70s | `BanHang` | 32,174 | 10 | 14 files | 21 | - |
| public_test | dev_013 | 2.70s | `QuanLy/DanhMuc` | 77 | 7 | QuanLy.xlsx[DanhMuc] | 0 | - |
| public_test | dev_013 | 2.70s | `QuanLy/KhachHang` | 420 | 5 | QuanLy.xlsx[KhachHang] | 0 | - |
| public_test | dev_013 | 2.70s | `QuanLy/NhapHang` | 1,503 | 9 | QuanLy.xlsx[NhapHang] | 0 | - |
| public_test | dev_013 | 2.70s | `QuanLy/KhuyenMai` | 10 | 4 | QuanLy.xlsx[KhuyenMai] | 0 | - |
| public_test | dev_014 | 1.05s | `SoBanHang/Ghi tắt` | 59 | 3 | SoBanHang.xlsx[Ghi tắt] | 0 | - |
| public_test | dev_014 | 1.05s | `SoBanHang` | 10,321 | 11 | 15 files | 39 | - |
| public_test | dev_014 | 1.05s | `SoNo/Sổ nợ` | 337 | 7 | SoNo.xlsx[Sổ nợ] | 0 | - |
| public_test | dev_014 | 1.05s | `SoNo/Trả góp` | 1,155 | 12 | SoNo.xlsx[Trả góp] | 0 | - |
| public_test | dev_014 | 1.05s | `SoNo/Bảo hành` | 192 | 8 | SoNo.xlsx[Bảo hành] | 0 | - |
| public_test | dev_014 | 1.05s | `ThuMayCu` | 300 | 8 | ThuMayCu.xlsx[Sheet1] | 0 | - |

---

## 2. Header & Wildcard Columns (`col_*`) & Empty Columns

| Shop | Table | Column Name | Issue Type | Preamble Detected |
|---|---|---|---|---|
| biz_106 | `DanhSachHoaDon` | `Ghi chú` | Completely empty column | DANH SÁCH HÓA ĐƠN |
| biz_106 | `DanhSachKhachHang` | `Email` | Completely empty column | None |
| biz_106 | `DanhSachKhachHang` | `Tên công ty` | Completely empty column | None |
| biz_106 | `DanhSachKhachHang` | `Ghi chú` | Completely empty column | None |
| biz_106 | `DanhSachKhachHang` | `Số CMND/CCCD` | Completely empty column | None |
| biz_106 | `DanhSachSanPham` | `Hình ảnh (url1,url2...)` | Completely empty column | None |
| biz_106 | `DanhSachSanPham` | `Vị trí kệ` | Completely empty column | None |
| biz_106 | `DanhSachSanPham` | `Ghi chú` | Completely empty column | None |
| biz_106 | `DanhSachSanPham` | `Thương hiệu` | Completely empty column | None |
| biz_106 | `DanhSachSanPham` | `Mã HH Liên quan` | Completely empty column | None |
| biz_106 | `DanhSachSanPham` | `Thuộc tính` | Completely empty column | None |
| biz_106 | `DanhSachSanPham` | `Mô tả sản phẩm` | Completely empty column | None |
| biz_106 | `DanhSachSanPham` | `Bảo hành` | Completely empty column | None |
| biz_106 | `DanhSachSanPham` | `Trọng lượng` | Completely empty column | None |
| biz_106 | `DanhSachSanPham` | `Mẫu ghi chú` | Completely empty column | None |
| biz_108 | `DanhSachHoaDon` | `Trạng thái HĐĐT` | Completely empty column | None |
| biz_108 | `DanhSachKhachHang` | `Giới tính` | Completely empty column | None |
| biz_108 | `DanhSachKhachHang` | `CCCD` | Completely empty column | None |
| biz_108 | `DanhSachKhachHang` | `Tên công ty` | Completely empty column | None |
| biz_108 | `DanhSachSanPham` | `Bảo hành` | Completely empty column | None |
| biz_108 | `DanhSachSanPham` | `Mô tả chi tiết` | Completely empty column | None |
| biz_108 | `DanhSachSanPham` | `Trọng lượng` | Completely empty column | None |
| biz_108 | `DanhSachSanPham` | `Vị trí` | Completely empty column | None |
| biz_108 | `DanhSachSanPham` | `Hình ảnh (url1,url2...)` | Completely empty column | None |
| biz_108 | `DanhSachSanPham` | `Thuộc tính` | Completely empty column | None |
| biz_108 | `DanhSachSanPham` | `Mẫu ghi chú` | Completely empty column | None |
| biz_108 | `DanhSachSanPham` | `Ghi chú` | Completely empty column | None |
| biz_108 | `DanhSachSanPham` | `Mã HH Liên quan` | Completely empty column | None |
| biz_109 | `DuLieuBanHang/DanhSachHoaDon` | `Trạng thái HĐĐT` | Completely empty column | None |
| biz_109 | `DuLieuBanHang/DanhSachSanPham` | `Vị trí` | Completely empty column | None |
| biz_109 | `DuLieuBanHang/DanhSachSanPham` | `Trọng lượng` | Completely empty column | None |
| biz_109 | `DuLieuBanHang/DanhSachSanPham` | `Thuộc tính` | Completely empty column | None |
| biz_109 | `DuLieuBanHang/DanhSachSanPham` | `Mẫu ghi chú` | Completely empty column | None |
| biz_109 | `DuLieuBanHang/DanhSachSanPham` | `Hình ảnh (url1,url2...)` | Completely empty column | None |
| biz_109 | `DuLieuBanHang/DanhSachSanPham` | `Bảo hành` | Completely empty column | None |
| biz_109 | `DuLieuBanHang/DanhSachSanPham` | `Thương hiệu` | Completely empty column | None |
| biz_109 | `DuLieuBanHang/DanhSachKhachHang` | `Ghi chú KH` | Completely empty column | None |
| biz_109 | `DuLieuBanHang/DanhSachKhachHang` | `Tên công ty` | Completely empty column | None |
| biz_111 | `khach_hang` | `Email` | Completely empty column | None |
| biz_111 | `khach_hang` | `Ghi chú KH` | Completely empty column | None |
| biz_111 | `khach_hang` | `CCCD` | Completely empty column | None |
| biz_111 | `san_pham` | `Thuộc tính` | Completely empty column | None |
| biz_111 | `san_pham` | `Hình ảnh` | Completely empty column | None |
| biz_111 | `san_pham` | `Thương hiệu` | Completely empty column | None |
| biz_111 | `san_pham` | `Trọng lượng` | Completely empty column | None |
| biz_111 | `san_pham` | `Vị trí` | Completely empty column | None |
| biz_111 | `san_pham` | `Mẫu ghi chú` | Completely empty column | None |
| biz_111 | `san_pham` | `Mô tả sản phẩm` | Completely empty column | None |
| biz_111 | `san_pham` | `Bảo hành` | Completely empty column | None |
| biz_111 | `san_pham` | `Mã HH Liên quan` | Completely empty column | None |
| biz_112 | `Danh sách hàng hóa` | `Trọng lượng` | Completely empty column | None |
| biz_112 | `Danh sách hàng hóa` | `Ghi chú` | Completely empty column | None |
| biz_112 | `Danh sách hàng hóa` | `Mã HH Liên quan` | Completely empty column | None |
| biz_112 | `Danh sách hàng hóa` | `Mô tả sản phẩm` | Completely empty column | None |
| biz_112 | `Danh sách hàng hóa` | `Bảo hành` | Completely empty column | None |
| biz_112 | `Danh sách hàng hóa` | `Vị trí` | Completely empty column | None |
| biz_115 | `Danh sách hàng hóa` | `Thương hiệu` | Completely empty column | None |
| biz_115 | `Danh sách hàng hóa` | `Vị trí` | Completely empty column | None |
| biz_115 | `Danh sách hàng hóa` | `Mẫu ghi chú` | Completely empty column | None |
| biz_115 | `Danh sách hàng hóa` | `Ghi chú` | Completely empty column | None |
| biz_115 | `Danh sách hàng hóa` | `Bảo hành` | Completely empty column | None |
| biz_115 | `Danh sách hàng hóa` | `Mô tả sản phẩm` | Completely empty column | None |
| biz_115 | `Danh sách hàng hóa` | `Trọng lượng` | Completely empty column | None |
| biz_116 | `Bao_cao_ban_hang/Danh sách hàng hóa` | `Bảo hành` | Completely empty column | None |
| biz_116 | `Bao_cao_ban_hang/Danh sách hàng hóa` | `Hình ảnh (url1,url2...)` | Completely empty column | None |
| biz_116 | `Bao_cao_ban_hang/Danh sách hàng hóa` | `Thuộc tính` | Completely empty column | None |
| biz_116 | `Bao_cao_ban_hang/Danh sách hàng hóa` | `Mẫu ghi chú` | Completely empty column | None |
| biz_116 | `Bao_cao_ban_hang/Danh sách hàng hóa` | `Mô tả sản phẩm` | Completely empty column | None |
| biz_116 | `Bao_cao_ban_hang/Danh sách hàng hóa` | `Trọng lượng` | Completely empty column | None |
| biz_116 | `Bao_cao_ban_hang/Danh sách hàng hóa` | `Mã HH Liên quan` | Completely empty column | None |
| biz_116 | `Bao_cao_ban_hang/Danh sách hàng hóa` | `Ghi chú` | Completely empty column | None |
| biz_116 | `Bao_cao_ban_hang/Danh sách hàng hóa` | `Vị trí` | Completely empty column | None |
| biz_118 | `Danh sách hàng hóa` | `Hình ảnh (url1,url2...)` | Completely empty column | None |
| biz_118 | `Danh sách hàng hóa` | `Vị trí` | Completely empty column | None |
| biz_118 | `Danh sách hàng hóa` | `Trọng lượng` | Completely empty column | None |
| biz_118 | `Danh sách hàng hóa` | `Bảo hành` | Completely empty column | None |
| biz_118 | `Danh sách hàng hóa` | `Mô tả sản phẩm` | Completely empty column | None |
| biz_118 | `Danh sách hàng hóa` | `Mã HH Liên quan` | Completely empty column | None |
| biz_118 | `Danh sách hàng hóa` | `Ghi chú` | Completely empty column | None |
| biz_118 | `Danh sách hàng hóa` | `Mẫu ghi chú` | Completely empty column | None |
| biz_119 | `DanhSachKhachHang` | `Công ty` | Completely empty column | None |
| biz_119 | `DanhSachKhachHang` | `Ghi chú KH` | Completely empty column | None |
| biz_119 | `DanhSachSanPham` | `Trọng lượng` | Completely empty column | None |
| biz_119 | `DanhSachSanPham` | `Bảo hành` | Completely empty column | None |
| biz_119 | `DanhSachSanPham` | `Ghi chú` | Completely empty column | None |
| biz_119 | `DanhSachSanPham` | `Mẫu ghi chú` | Completely empty column | None |
| biz_119 | `DanhSachSanPham` | `Vị trí kệ` | Completely empty column | None |
| biz_119 | `DanhSachSanPham` | `Mô tả chi tiết` | Completely empty column | None |
| biz_119 | `DanhSachSanPham` | `Thuộc tính` | Completely empty column | None |
| biz_119 | `DanhSachSanPham` | `Hình ảnh (url1,url2...)` | Completely empty column | None |
| biz_119 | `DanhSachSanPham` | `Mã HH Liên quan` | Completely empty column | None |
| biz_119 | `DanhSachSanPham` | `Thương hiệu` | Completely empty column | None |
| biz_120 | `DanhSachHoaDon` | `Ghi chú` | Completely empty column | None |
| biz_120 | `DanhSachKhachHang` | `Ghi chú` | Completely empty column | None |
| biz_120 | `DanhSachKhachHang` | `CCCD` | Completely empty column | None |
| biz_120 | `DanhSachKhachHang` | `E-mail` | Completely empty column | None |
| biz_120 | `DanhSachKhachHang` | `Tên công ty` | Completely empty column | None |
| biz_120 | `DanhSachSanPham` | `Trọng lượng` | Completely empty column | None |
| biz_120 | `DanhSachSanPham` | `Mô tả chi tiết` | Completely empty column | None |
| biz_120 | `DanhSachSanPham` | `Mẫu ghi chú` | Completely empty column | None |
| biz_120 | `DanhSachSanPham` | `Bảo hành` | Completely empty column | None |
| biz_120 | `DanhSachSanPham` | `Mã HH Liên quan` | Completely empty column | None |
| biz_120 | `DanhSachSanPham` | `Hình ảnh` | Completely empty column | None |
| biz_121 | `DuLieuXuat/DanhSachSanPham` | `Vị trí` | Completely empty column | None |
| biz_121 | `DuLieuXuat/DanhSachSanPham` | `Ghi chú` | Completely empty column | None |
| biz_121 | `DuLieuXuat/DanhSachSanPham` | `Bảo hành` | Completely empty column | None |
| biz_121 | `DuLieuXuat/DanhSachSanPham` | `Thương hiệu` | Completely empty column | None |
| biz_121 | `DuLieuXuat/DanhSachSanPham` | `Mẫu ghi chú` | Completely empty column | None |
| biz_121 | `DuLieuXuat/DanhSachSanPham` | `Trọng lượng` | Completely empty column | None |
| biz_121 | `DuLieuXuat/DanhSachSanPham` | `Mã HH Liên quan` | Completely empty column | None |
| biz_121 | `DuLieuXuat/DanhSachSanPham` | `Hình ảnh (url1,url2...)` | Completely empty column | None |
| biz_121 | `DuLieuXuat/DanhSachSanPham` | `Thuộc tính` | Completely empty column | None |
| biz_121 | `DuLieuXuat/DanhSachSanPham` | `Mô tả chi tiết` | Completely empty column | None |
| biz_122 | `DanhSachSanPham` | `Ghi chú` | Completely empty column | None |
| biz_122 | `DanhSachSanPham` | `Mô tả sản phẩm` | Completely empty column | None |
| biz_122 | `DanhSachSanPham` | `Vị trí` | Completely empty column | None |
| biz_122 | `DanhSachSanPham` | `Mã HH Liên quan` | Completely empty column | None |
| biz_122 | `DanhSachSanPham` | `Thương hiệu` | Completely empty column | None |
| biz_122 | `DanhSachSanPham` | `Thuộc tính` | Completely empty column | None |
| biz_122 | `DanhSachSanPham` | `Hình ảnh` | Completely empty column | None |
| biz_122 | `DanhSachSanPham` | `Trọng lượng` | Completely empty column | None |
| biz_122 | `DanhSachSanPham` | `Bảo hành` | Completely empty column | None |
| biz_122 | `DanhSachSanPham` | `Mẫu ghi chú` | Completely empty column | None |
| biz_123 | `don_hang` | `SoHoaDonDienTu` | Completely empty column | None |
| biz_123 | `don_hang` | `TinhTrangHDDT` | Completely empty column | None |
| biz_123 | `don_hang` | `DienGiai` | Completely empty column | None |
| biz_123 | `khach_hang` | `cccd` | Completely empty column | None |
| biz_123 | `khach_hang` | `ghi_chu_kh` | Completely empty column | None |
| biz_123 | `khach_hang` | `email` | Completely empty column | None |
| biz_123 | `khach_hang` | `NamNu` | Completely empty column | None |
| biz_123 | `khach_hang` | `cong_ty` | Completely empty column | None |
| biz_123 | `nhan_vien` | `NgayThoiViec` | Completely empty column | None |
| biz_123 | `san_pham` | `hinh_anh` | Completely empty column | None |
| biz_123 | `san_pham` | `bao_hanh` | Completely empty column | None |
| biz_123 | `san_pham` | `ghi_chu_hh` | Completely empty column | None |
| biz_123 | `san_pham` | `vi_tri` | Completely empty column | None |
| biz_123 | `san_pham` | `thuong_hieu` | Completely empty column | None |
| biz_123 | `san_pham` | `mau_ghi_chu` | Completely empty column | None |
| biz_123 | `san_pham` | `mo_ta` | Completely empty column | None |
| biz_123 | `thanh_toan` | `DienGiai` | Completely empty column | None |
| biz_124 | `BanHang_HangHoa` | `Thương hiệu` | Completely empty column | None |
| biz_124 | `BanHang_HangHoa` | `Thuộc tính` | Completely empty column | None |
| biz_124 | `BanHang_HangHoa` | `Mã HH Liên quan` | Completely empty column | None |
| biz_124 | `BanHang_HangHoa` | `Mô tả sản phẩm` | Completely empty column | None |
| biz_124 | `BanHang_HangHoa` | `Mẫu ghi chú` | Completely empty column | None |
| biz_124 | `BanHang_HangHoa` | `Ghi chú` | Completely empty column | None |
| biz_124 | `BanHang_HangHoa` | `Trọng lượng` | Completely empty column | None |
| biz_124 | `BanHang_KhachHang` | `Công ty` | Completely empty column | None |
| biz_124 | `BanHang_KhachHang` | `E-mail` | Completely empty column | None |
| biz_124 | `BanHang_KhachHang` | `CCCD` | Completely empty column | None |
| biz_124 | `BanHang_KhachHang` | `Ghi chú` | Completely empty column | None |
| biz_127 | `don_hang` | `Diễn giải` | Completely empty column | None |
| biz_127 | `khach_hang` | `CCCD` | Completely empty column | None |
| biz_127 | `khach_hang` | `Tên công ty` | Completely empty column | None |
| biz_127 | `khach_hang` | `Email` | Completely empty column | None |
| biz_127 | `khach_hang` | `Ghi chú` | Completely empty column | None |
| biz_127 | `san_pham` | `Trọng lượng` | Completely empty column | None |
| biz_127 | `san_pham` | `Mô tả chi tiết` | Completely empty column | None |
| biz_127 | `san_pham` | `Ghi chú` | Completely empty column | None |
| biz_127 | `san_pham` | `Mẫu ghi chú` | Completely empty column | None |
| biz_127 | `san_pham` | `Thương hiệu` | Completely empty column | None |
| biz_127 | `san_pham` | `Thuộc tính` | Completely empty column | None |
| biz_127 | `san_pham` | `Hình ảnh (url1,url2...)` | Completely empty column | None |
| biz_127 | `san_pham` | `Mã HH Liên quan` | Completely empty column | None |
| biz_128 | `DanhSachKhachHang` | `Email` | Completely empty column | None |
| biz_128 | `DanhSachKhachHang` | `CCCD` | Completely empty column | None |
| biz_128 | `DanhSachKhachHang` | `Ghi chú KH` | Completely empty column | None |
| biz_128 | `DanhSachKhachHang` | `Công ty` | Completely empty column | None |
| biz_128 | `DanhSachKhachHang` | `Giới tính` | Completely empty column | None |
| biz_128 | `DanhSachKhachHang` | `MST` | Completely empty column | None |
| biz_128 | `DanhSachSanPham` | `Ghi chú` | Completely empty column | None |
| biz_128 | `DanhSachSanPham` | `Thương hiệu` | Completely empty column | None |
| biz_128 | `DanhSachSanPham` | `Mã HH Liên quan` | Completely empty column | None |
| biz_128 | `DanhSachSanPham` | `Mẫu ghi chú` | Completely empty column | None |
| biz_128 | `DanhSachSanPham` | `Vị trí` | Completely empty column | None |
| biz_128 | `DanhSachSanPham` | `Thuộc tính` | Completely empty column | None |
| biz_128 | `DanhSachSanPham` | `Hình ảnh` | Completely empty column | None |
| biz_128 | `DanhSachSanPham` | `Mô tả chi tiết` | Completely empty column | None |
| biz_128 | `DanhSachSanPham` | `Trọng lượng` | Completely empty column | None |
| biz_129 | `khach_hang` | `Ghi chú KH` | Completely empty column | None |
| biz_129 | `khach_hang` | `Email` | Completely empty column | None |
| biz_129 | `khach_hang` | `Công ty` | Completely empty column | None |
| biz_129 | `khach_hang` | `Số CMND/CCCD` | Completely empty column | None |
| biz_129 | `san_pham` | `Bảo hành` | Completely empty column | None |
| biz_129 | `san_pham` | `Mã HH Liên quan` | Completely empty column | None |
| biz_129 | `san_pham` | `Vị trí kệ` | Completely empty column | None |
| biz_129 | `san_pham` | `Mô tả chi tiết` | Completely empty column | None |
| biz_129 | `san_pham` | `Ghi chú` | Completely empty column | None |
| biz_129 | `san_pham` | `Mẫu ghi chú` | Completely empty column | None |
| biz_129 | `san_pham` | `Thuộc tính` | Completely empty column | None |
| biz_129 | `san_pham` | `Thương hiệu` | Completely empty column | None |
| biz_129 | `san_pham` | `Hình ảnh` | Completely empty column | None |
| biz_130 | `Danh sách hàng hóa` | `Mô tả sản phẩm` | Completely empty column | None |
| biz_130 | `Danh sách hàng hóa` | `Bảo hành` | Completely empty column | None |
| biz_130 | `Danh sách hàng hóa` | `Mã HH Liên quan` | Completely empty column | None |
| biz_130 | `Danh sách hàng hóa` | `Mẫu ghi chú` | Completely empty column | None |
| biz_130 | `Danh sách hàng hóa` | `Thương hiệu` | Completely empty column | None |
| biz_130 | `Danh sách hàng hóa` | `Vị trí kệ` | Completely empty column | None |
| biz_130 | `Danh sách hàng hóa` | `Ghi chú` | Completely empty column | None |
| dev_001 | `Danh sách hàng hóa` | `Vị trí` | Completely empty column | None |
| dev_001 | `Danh sách hàng hóa` | `Ghi chú` | Completely empty column | None |
| dev_001 | `Danh sách hàng hóa` | `Thuộc tính` | Completely empty column | None |
| dev_001 | `Danh sách hàng hóa` | `Mô tả sản phẩm` | Completely empty column | None |
| dev_001 | `Danh sách hàng hóa` | `Mã HH Liên quan` | Completely empty column | None |
| dev_001 | `Danh sách hàng hóa` | `Bảo hành` | Completely empty column | None |
| dev_001 | `Danh sách hàng hóa` | `Trọng lượng` | Completely empty column | None |
| dev_001 | `Danh sách hàng hóa` | `Mẫu ghi chú` | Completely empty column | None |
| dev_001 | `Danh sách hàng hóa` | `Hình ảnh` | Completely empty column | None |
| dev_003 | `BanHang_TongHop_2025/BanHang_HangHoa` | `Thuộc tính` | Completely empty column | None |
| dev_003 | `BanHang_TongHop_2025/BanHang_HangHoa` | `Trọng lượng` | Completely empty column | None |
| dev_003 | `BanHang_TongHop_2025/BanHang_HangHoa` | `Hình ảnh (url1,url2...)` | Completely empty column | None |
| dev_003 | `BanHang_TongHop_2025/BanHang_HangHoa` | `Bảo hành` | Completely empty column | None |
| dev_003 | `BanHang_TongHop_2025/BanHang_HangHoa` | `Mô tả sản phẩm` | Completely empty column | None |
| dev_003 | `BanHang_TongHop_2025/BanHang_HangHoa` | `Vị trí kệ` | Completely empty column | None |
| dev_003 | `BanHang_TongHop_2025/BanHang_HangHoa` | `Mẫu ghi chú` | Completely empty column | None |
| dev_003 | `BanHang_TongHop_2025/BanHang_KhachHang` | `Email` | Completely empty column | None |
| dev_003 | `BanHang_TongHop_2025/BanHang_KhachHang` | `Ghi chú` | Completely empty column | None |
| dev_003 | `BanHang_TongHop_2025/BanHang_KhachHang` | `CCCD` | Completely empty column | None |
| dev_003 | `BanHang_TongHop_2025/BanHang_KhachHang` | `Công ty` | Completely empty column | None |
| dev_005 | `DanhSachSanPham` | `Ghi chú` | Completely empty column | None |
| dev_005 | `DanhSachSanPham` | `Mẫu ghi chú` | Completely empty column | None |
| dev_005 | `DanhSachSanPham` | `Bảo hành` | Completely empty column | None |
| dev_005 | `DanhSachSanPham` | `Mã HH Liên quan` | Completely empty column | None |
| dev_005 | `DanhSachSanPham` | `Mô tả chi tiết` | Completely empty column | None |
| dev_005 | `DanhSachSanPham` | `Thương hiệu` | Completely empty column | None |
| dev_005 | `DanhSachSanPham` | `Thuộc tính` | Completely empty column | None |
| dev_005 | `DanhSachSanPham` | `Trọng lượng` | Completely empty column | None |
| dev_005 | `DanhSachSanPham` | `Vị trí` | Completely empty column | None |
| dev_006 | `don_hang` | `SoHoaDonDienTu` | Completely empty column | None |
| dev_006 | `don_hang` | `TinhTrangHDDT` | Completely empty column | None |
| dev_006 | `don_hang` | `DienGiai` | Completely empty column | None |
| dev_006 | `khach_hang` | `cccd` | Completely empty column | None |
| dev_006 | `khach_hang` | `email` | Completely empty column | None |
| dev_006 | `khach_hang` | `ghi_chu_kh` | Completely empty column | None |
| dev_006 | `khach_hang` | `NamNu` | Completely empty column | None |
| dev_006 | `khach_hang` | `cong_ty` | Completely empty column | None |
| dev_006 | `nha_cung_cap` | `email` | Completely empty column | None |
| dev_006 | `nha_cung_cap` | `nhom_ncc` | Completely empty column | None |
| dev_006 | `nha_cung_cap` | `ma_so_thue` | Completely empty column | None |
| dev_006 | `nhan_vien` | `NgayThoiViec` | Completely empty column | None |
| dev_006 | `san_pham` | `mo_ta` | Completely empty column | None |
| dev_006 | `san_pham` | `ghi_chu_hh` | Completely empty column | None |
| dev_006 | `san_pham` | `ma_hh_lien_quan` | Completely empty column | None |
| dev_006 | `san_pham` | `thuoc_tinh` | Completely empty column | None |
| dev_006 | `san_pham` | `mau_ghi_chu` | Completely empty column | None |
| dev_006 | `san_pham` | `vi_tri` | Completely empty column | None |
| dev_006 | `san_pham` | `trong_luong` | Completely empty column | None |
| dev_006 | `san_pham` | `hinh_anh` | Completely empty column | None |
| dev_006 | `san_pham` | `bao_hanh` | Completely empty column | None |
| dev_006 | `san_pham` | `thuong_hieu` | Completely empty column | None |
| dev_006 | `thanh_toan` | `DienGiai` | Completely empty column | None |
| dev_007 | `chi_tiet_hoa_don` | `Nội dung` | Completely empty column | None |
| dev_007 | `chi_tiet_hoa_don` | `Giới tính` | Completely empty column | None |
| dev_007 | `chi_tiet_hoa_don` | `Trạng thái HĐĐT` | Completely empty column | None |
| dev_008 | `ChiTietHoaDon` | `Trạng thái HĐĐT` | Completely empty column | None |
| dev_008 | `ChiTietHoaDon` | `Giới tính` | Completely empty column | None |
| dev_010 | `khach_hang` | `Ghi chú KH` | Completely empty column | None |
| dev_010 | `khach_hang` | `Mã số thuế` | Completely empty column | None |
| dev_010 | `khach_hang` | `Email` | Completely empty column | None |
| dev_010 | `khach_hang` | `Số CMND/CCCD` | Completely empty column | None |
| dev_010 | `khach_hang` | `Công ty` | Completely empty column | None |
| dev_010 | `san_pham` | `Mô tả chi tiết` | Completely empty column | None |
| dev_010 | `san_pham` | `Mẫu ghi chú` | Completely empty column | None |
| dev_010 | `san_pham` | `Thương hiệu` | Completely empty column | None |
| dev_010 | `san_pham` | `Ghi chú` | Completely empty column | None |
| dev_010 | `san_pham` | `Bảo hành` | Completely empty column | None |
| dev_010 | `san_pham` | `Hình ảnh (url1,url2...)` | Completely empty column | None |
| dev_010 | `san_pham` | `Thuộc tính` | Completely empty column | None |
| dev_010 | `san_pham` | `Trọng lượng` | Completely empty column | None |
| dev_010 | `san_pham` | `Mã HH Liên quan` | Completely empty column | None |

---

## 3. Unparsed Cells in Typed Columns (Date, DateTime, Number, Qty)

| Shop | Table | Column | Kind | Non-blank | Unparsed | Fail % | Sample Unparsed Values |
|---|---|---|---|---|---|---|---|
| biz_117 | `SoBanHang` | `Giờ` | `datetime` | 33,845 | 40 | 0.12% | 'Tổng tháng'<br>'Ghi chú: số liệu ghi tay'<br>'Ghi chú: tiền tính bằng đồng' |
| dev_012 | `SoSuaXe` | `Ngày` | `date` | 6,078 | 18 | 0.30% | 'Ghi chú: tiền tính bằng đồng'<br>'Ghi chú: số liệu ghi tay' |
| dev_014 | `SoBanHang` | `Ngày` | `date` | 10,321 | 39 | 0.38% | 'Tổng cộng'<br>'Ghi chú: số liệu ghi tay'<br>'Ghi chú: tiền tính bằng đồng' |
