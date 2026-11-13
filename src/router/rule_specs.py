"""What each template needs from the rulebook, as short phrases (accent-stripped, lower case).

For every rulebook row a template relies on:
  must        regexes that all have to match the row text of the RUNNING rulebook: the row's main ideas, with variants
  contradict  regexes that must NOT match: wording that reverses the idea ("huy van tinh", "tinh ca don tra", ...)
  canon       a short paraphrase of the row used by tests and docs (it satisfies `must`)
A row that is missing, lacks a main idea or contains a contradicting phrase switches off the intents that use it; extra
sentences, examples or new rows do not.  Written from the train rulebook text only; never tuned on questions or answers.
Negation is handled with lookbehinds ("khong tru giam gia tren ca don" is the rule, "tru giam gia tren ca don" is a change).
"""
from __future__ import annotations

# (section, row-name prefix) -> spec.  The section is informative: rows are found by name in any section.
SPECS: dict[tuple[str, str], dict] = {
    ("1", "don tinh vao doanh thu"): {
        "must": [r"khong huy|ngoai tru[^.;]{0,12}huy|loai[^.;]{0,12}huy|bo[^.;]{0,12}huy",
                 r"khong tra|ngoai tru[^.;]{0,12}tra|loai[^.;]{0,12}tra|bo[^.;]{0,12}tra",
                 r"ca don|toan bo don"],
        "contradict": [r"(huy|tra( hang)?) (van|cung|deu) (duoc )?tinh", r"(ke ca|bao gom|tinh ca|gom ca) don (huy|tra)",
                       r"chi (bo|loai|tru) (dong|phan) (da )?tra", r"huy (van )?(duoc )?tinh vao doanh thu"],
        "canon": "don khong huy va khong tra hang. don co tra hang, ke ca chi tra mot phan, la don tra hang: bo ca don"},
    ("1", "don thuoc ky nao"): {
        "must": [r"ngay dat"],
        "contradict": [r"(?<!khong )(?<!khong theo )theo ngay (giao|thu tien|tra|nhap)", r"tinh theo ngay (giao|thu|tra)"],
        "canon": "theo ngay dat, khong theo ngay giao hay ngay thu tien"},
    ("1", "doanh thu mot don"): {
        "must": [r"thanh tien[^.;]{0,20}dong", r"tru giam gia tren (tung )?dong|da tru giam gia"],
        "contradict": [r"(?<!khong )tru giam gia tren ca don", r"(?<!khong )cong thue", r"(?<!khong )(gom|cong) phi (giao|van chuyen)"],
        "canon": "tong thanh tien cac dong hang (da tru giam gia tren tung dong). khong tru giam gia tren ca don, khong cong thue vat, khong gom phi giao hang"},
    ("1", "ban duoc bao nhieu tien"): {
        "must": [r"doanh thu"],
        "contradict": [r"(?<!khong phai )tien khach da tra"],
        "canon": "la doanh thu theo muc nay, khong phai tien khach da tra"},
    ("1", "so don"): {
        "must": [r"khong huy|loai[^.;]{0,12}huy|bo[^.;]{0,12}huy", r"khong tra|loai[^.;]{0,12}tra|bo[^.;]{0,12}tra"],
        "contradict": [r"(huy|tra) (van|cung|deu) (duoc )?tinh", r"ke ca don (huy|tra)(?! hang khong)"],
        "canon": "chi tinh don khong huy, khong tra"},
    ("1", "don bi huy"): {
        "must": [r"trang thai huy", r"(don )?tra hang khong phai don huy|khong phai don huy"],
        "contradict": [r"don tra hang (la|cung la|tinh la) don huy"],
        "canon": "don co trang thai huy. don tra hang khong phai don huy"},
    ("1", "ti le don huy trong ky"): {
        "must": [r"moi don dat|moi trang thai|tat ca don", r"ngay dat", r"2 chu so thap phan|lam tron 2"],
        "contradict": [r"chi (tinh )?(trong )?don (da )?(hoan thanh|hop le|khong huy)", r"khong (tinh|gom) don (tra|dang giao)"],
        "canon": "phan tram don huy trong moi don dat trong ky (theo ngay dat, moi trang thai). lam tron 2 chu so thap phan"},
    ("1", "phan tram thay doi"): {
        "must": [r"ky truoc", r"am"],
        "contradict": [r"so voi ky (sau|ke tiep)", r"giam[^.;]{0,15}(ra )?so duong"],
        "canon": "so voi ky truoc; giam thi ra so am"},
    ("3", "gia tri trung binh mot don"): {
        "must": [r"lam tron ve dong", r"nua dong lam tron len"],
        "contradict": [r"lam tron xuong", r"nua dong lam tron xuong", r"lam tron (den|toi) (ca )?(nghin|tram)"],
        "canon": "lam tron ve dong, nua dong lam tron len"},
    ("3", "mat hang"): {
        "must": [r"phi phuc vu"],
        "contradict": [r"phi phuc vu (la|tinh la|duoc tinh la|cung la) (mot )?mat hang"],
        "canon": "mon, hang, san pham cung nghia voi mat hang. dong phi phuc vu khong phai mat hang"},
    ("3", "ban chay"): {
        "must": [r"so luong", r"don vi co ban"],
        "contradict": [r"(?<!khong )theo (so dong|so tien|doanh thu)"],
        "canon": "theo so luong quy ve don vi co ban, khong theo so dong hay so tien; bo don huy, tra"},
    ("3", "ban duoc bao nhieu"): {
        "must": [r"don vi co ban", r"quy ve|cong so luong"],
        "contradict": [r"(?<!khong )tinh (ca )?mat hang co don vi co ban khac"],
        "canon": "cong so luong quy ve don vi co ban cua cac mat hang co don vi co ban la <don vi>"},
    ("3", "nhom hang"): {
        "must": [r"ten nhom|cot nhom hang"],
        "contradict": [r"(?<!khong )gop nhom"],
        "canon": "theo cot nhom hang, dung ten nhom cau hoi neu; khong gop nhom khac ten"},
    ("5", "gia ban x ngay d"): {
        "must": [r"don gia", r"don vi co ban", r"truoc chiet khau"],
        "contradict": [r"(?<!khong )sau chiet khau", r"khong tinh dong (cua )?don (huy|tra)"],
        "canon": "don gia ghi tren dong ban x cua cac don dat ngay d, cho mot don vi co ban, truoc chiet khau dong; tinh ca dong cua don huy, don tra"},
    ("8", "hai dong cua cung mot don"): {
        "must": [r"tinh mot lan|loi xuat file", r"(hai|2) don khac nhau|don khac nhau"],
        "contradict": [r"(?<!khong )tinh (ca )?hai lan[^.;]{0,30}cung mot don"],
        "canon": "loi xuat file, tinh mot lan. hai dong giong nhau cua hai don khac nhau la hai lan ban"},
    ("8", "o de trong o cac dong sau"): {
        "must": [r"dong dau", r"khong phai thieu"],
        "contradict": [r"o de trong (la|nghia la|thi la) (khach le|don hoan thanh)"],
        "canon": "giong o do o dong dau nhom. khong phai thieu du lieu"},
    ("8", "ten goi, nhan"): {
        "must": [r"cung mot thu|cung chi mot"],
        "contradict": [],
        "canon": "cac ten cung chi mot thu la cung mot thu"},
    ("8", "trang thai don"): {
        "must": [r"hoan thanh", r"huy", r"tra hang", r"dang giao"],
        "contradict": [],
        "canon": "moi don co dung mot trong bon trang thai: hoan thanh, huy, tra hang, dang giao"},
    ("10", "don vi co ban"): {
        "must": [r"don vi co ban", r"he so quy doi", r"he so 1"],
        "contradict": [],
        "canon": "moi mat hang co mot don vi co ban va co the co don vi lon. he so quy doi doc o bang quy doi; don vi khong co dong quy doi la don vi co ban, he so 1"},
    ("2", "ngay x, hom nay, hom qua"): {
        "must": [r"chi trong ngay|trong ngay do"],
        "contradict": [],
        "canon": "hoi so phat sinh: chi trong ngay do"},
    ("2", "den het ngay x"): {
        "must": [r"tu dau du lieu", r"den het ngay"],
        "contradict": [],
        "canon": "tinh trang luc het ngay do, tinh moi phat sinh tu dau du lieu den het ngay do"},
    ("2", "tu x den y"): {
        "must": [r"gom ca"],
        "contradict": [r"khong (gom|tinh) (ca )?(ngay )?(y|cuoi)"],
        "canon": "gom ca x va y"},
    ("2", "n ngay gan nhat"): {
        "must": [r"hom nay"],
        "contradict": [r"(?<!ke ca )(?<!khong tinh )khong (gom|tinh) hom nay"],
        "canon": "n ngay lien nhau ke ca hom nay, ngay cuoi la hom nay"},
    ("2", "tuan"): {
        "must": [r"thu hai", r"chu nhat"],
        "contradict": [r"bat dau (tu )?chu nhat"],
        "canon": "bat dau thu hai. tuan truoc: ca tuan lien truoc, thu hai den chu nhat"},
    ("2", "thang m/y"): {
        "must": [r"ca thang|ngay 1 den het"],
        "contradict": [],
        "canon": "ca thang, tu ngay 1 den het ngay cuoi thang"},
    ("2", "thang nay"): {
        "must": [r"ngay 1 den het hom nay", r"cung so ngay"],
        "contradict": [],
        "canon": "tu ngay 1 den het hom nay. so voi thang truoc thi lay cung so ngay cua thang truoc"},
    ("2", "tu dau nam"): {
        "must": [r"01/01|1/1|dau nam", r"hom nay"],
        "contradict": [],
        "canon": "tu 01/01 cua nam nay den het hom nay"},
    ("2", "thang m, quy q khong ghi nam"): {
        "must": [r"nam nay", r"sau hom nay", r"nam truoc"],
        "contradict": [],
        "canon": "cua nam nay neu khong sau hom nay; sau hom nay thi cua nam truoc"},
}
