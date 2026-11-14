"""Approximate intent tagger: ~60 ordered regex rules on accent-stripped questions.

Labels are approximate (about +-10% per group, see docs/BRAINSTORM_PIPELINE.md §4).
Also exposes deacc() (accent strip + light teencode/telex repair) and ttag() (time
expression type).

Usage (from data/ dir): python ../scripts/analysis/intent_tagger.py train [n_examples] [only_intent]
"""
import json, re, sys, unicodedata, collections, random

def deacc(s):
    s = s.lower().replace('đ', 'd')
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    # light telex/teencode repair, enough for tagging
    for a, b in [('ddown', 'don'), ('ddon', 'don'), ('dduwowcj', 'duoc'), ('toongr', 'tong'), ('bnhiu', 'bao nhieu'),
                 ('bao nhiu', 'bao nhieu'), ('nhiu', 'nhieu'), ('nhieeu', 'nhieu'), (' bn ', ' bao nhieu '), (' dc ', ' duoc '),
                 ('dthu', 'doanh thu'), ('hqua', 'hom qua'), ('hnay', 'hom nay'), (' ko ', ' khong '), (' k ', ' khong '),
                 ('heets', 'het'), ('hoom', 'hom'), ('mawtj', 'mat'), ('hangf', 'hang'), ('naof', 'nao'), ('tieenf', 'tien'),
                 ('khachs', 'khach'), ('thangs', 'thang'), ('nhaapj', 'nhap'), (' sp ', ' san pham '), (' trc', ' truoc'), (' vs ', ' voi ')]:
        s = (' ' + s + ' ').replace(a, b).strip()
    return s

U = r'(kg|lon|chai|hop|goi|cai|vien|ly|bao|cay|thung|loc|vi|m3|m2|m|met|tam|cuon|tuyp|lo|phan|dia|to|bat|suat|chiec|bo|mieng|bich|tui|binh|can|lit|trai|qua|con|xe|khoi|thanh|ong|noi|cuc|ket|chen|que|hu|cap|doi|thien|tan|bang|to|bong|tap|quyen|o)'
HOWMANY = r'(bao nhieu|may|nhieu)'
RULES = [  # first match wins; ordered specific -> general
 ('unans_subjective', r'tan tam|le phep|chu dao|lanh nghe|tay nghe|quy men|hay khen|nen uong'),
 ('price_effect', r'tang gia|ke tu ngay'),
 ('tet', r'\btet\b'),
 ('expiry_nearest_lot', r'gan het han nhat'),
 ('expiry_list', r'han dung tu|het han trong \d+ ngay|se het han'),
 ('debt_aging', r'tuoi no|qua 15 ngay|hon 15 ngay|qua \d+ ngay|hon \d+ ngay ma'),
 ('debt_flow_customer', r'no them.{0,60}tra'),
 ('debt_collected', r'tra no|thu no|thu hoi|tra bot no'),
 ('debt_topk_table', r'(\d+ khach).{0,40}\bno\b|no nhieu nhat'),
 ('debt_customer_count', r'(bao nhieu|may|so) khach.{0,40}(\bno\b|thieu)|khach con cong no'),
 ('debt_total', r'\bno\b|cong no|con thieu|chua thu'),
 ('stock_large_unit', r'(chan|nguyen).{0,60}\ble\b'),
 ('stock_value', r'gia tri.{0,30}(ton|kho)|theo gia von'),
 ('stockout_count', r'het hang'),
 ('unsold_count', r'\be\b (han|den muc)|bi e\b|mon e\b|hang e\b|khong ban ra duoc|khong ban duoc (lan|cai)|khong ai mua'),
 ('stock_qty', r'\bton\b|trong kho|\bkho con\b|con lai may|con bao nhieu|con may'),
 ('purchase_avg_price', r'nhap.{0,80}binh quan|binh quan.{0,40}nhap'),
 ('purchase_minus_sales', r'nhap tru ban'),
 ('supplier_top', r'nha cung cap|\bncc\b'),
 ('purchase_total', r'\bnhap\b'),
 ('net_profit', r'lai rong|loi nhuan rong'),
 ('profit_item_top', r'(hang|san pham|mat hang) (nao|gi).{0,40}(lai|loi)|loi nhat|loi nhuan gop lon nhat'),
 ('gross_profit', r'lai gop|loi gop|loi nhuan gop'),
 ('delivery_count', r'dot giao'),
 ('rx_share', r'ke don.{0,60}(%|phan tram|ti le|ty le)|(%|phan tram|ti le).{0,60}ke don'),
 ('rx_nonrx_revenue', r'ke don'),
 ('ingredient_revenue', r'hoat chat'),
 ('sell_price_on_day', r'gia ban (mot|1)|don gia'),
 ('size_qty', r'size (m|l)\b'),
 ('cancel_rate', r'(ti le|ty le|%|phan tram).{0,40}huy|huy.{0,40}(ti le|ty le|%|phan tram)'),
 ('cancel_count', r'\bhuy\b'),
 ('streak_bool', r'lien tuc'),
 ('monthly_series', r'moi thang|tung thang|theo thu tu thoi gian|3 thang lien'),
 ('best_month', r'thang nao'),
 ('best_day', r'ngay nao|hom nao'),
 ('staff_top', r'(nhan vien|nguoi ban|ai).{0,40}(nhat|gioi)(?!.*khach)'),
 ('staff_revenue', r'nhan vien|\bnv\d'),
 ('shift', r'\bca (sang|chieu)'),
 ('payment_method_rev', r'tra bang|tien mat|chuyen khoan|\bcod\b|vi dien tu'),
 ('channel_rev', r'ban qua|ban tai|tai quay|kenh'),
 ('cust_group_share', r'nhom (than thiet|si|le|vip).{0,80}(%|phan tram)|(%|phan tram|phan cua).{0,80}khach nhom'),
 ('cust_group_rev', r'khach nhom|nhom khach'),
 ('cust_attr', r'khach (nu|nam)\b|khach o duong|o duong'),
 ('cust_freq_share', r'khach.{0,60}don.{0,40}(%|phan tram)|(%|phan tram|ti le).{0,60}khach.{0,40}don'),
 ('cust_freq_count', r'khach.{0,30}(tu|it nhat|≥|>=) ?\d+ don'),
 ('cust_top_orders', r'khach.{0,40}(nhieu lan|nhieu don)'),
 ('cust_topk', r'\d+ khach|liet ke.{0,20}khach'),
 ('cust_top1', r'khach.{0,40}nhat|ai (la|mua)'),
 ('item_in_n_orders', r'(mat hang|san pham|mon).{0,40}\d+ don khac nhau'),
 ('orders_threshold', r'don.{0,50}(tu|tren|duoi|hon) [\d\.]+ ?dong'),
 ('category_share', r'nhom.{0,80}(chiem|ti trong|ty trong|%|phan tram|dong gop)|(ti trong|ty trong).{0,40}nhom'),
 ('category_rev', r'\bnhom\b'),
 ('topk_items', r'top ?\d+|\d+ (mat hang|san pham|hang|mon|best)|liet ke.{0,20}(mat hang|san pham|mon)'),
 ('best_item', r'(mat hang|san pham|hang|mon|thuoc) (nao|gi)|chay nhat|hot nhat|best seller'),
 ('aov', r'trung binh|binh quan'),
 ('rev_change_pct', r'(%|phan tram)'),
 ('order_count', r'(bao nhieu|may|so|tong cong) (cai )?(don|hoa don|bill)\b|so don'),
 ('unit_total_qty', r'(tinh theo|cong moi).{0,30}' + U + r'\b|tong cong ' + HOWMANY + ' ' + U + r'\b(?! \w)|ban (ra|duoc) (tong cong )?' + HOWMANY + ' ' + U + r'\s*(\?|$|vay|nhi|ha|ta|z|do)'),
 ('item_revenue', r'(mat hang|hang|mon) .{2,80}(thu ve|thu duoc)|tien ban (?!hang)\w|doanh thu cua (?!cua hang)'),
 ('item_qty', HOWMANY + ' ' + U + r'\b|so ' + U + r' .{3,90}ban|so luong'),
 ('revenue', r'doanh thu|bao nhieu tien|tien hang|tien ban|doanh so'),
]

def tag(q):
    t = deacc(q)
    for name, rx in RULES:
        if re.search(rx, t):
            return name
    return 'OTHER'

TIME = [
 ('month_explicit', r'thang \d{1,2}(/| nam )\d{4}'),
 ('quarter', r'quy \d'),
 ('date_explicit', r'\d{1,2}/\d{1,2}/\d{4}'),
 ('this_month', r'thang nay'),
 ('last_week', r'tuan (truoc|roi|vua)'),
 ('this_week', r'tuan nay'),
 ('today', r'hom nay|bua nay'),
 ('yesterday', r'hom qua|bua qua'),
 ('n_days', r'\d+ ngay gan nhat'),
 ('ytd', r'dau nam|nam nay'),
 ('tet', r'\btet\b'),
 ('month_noyear', r'thang \d{1,2}\b'),
]
def ttag(q):
    t = deacc(q)
    for n, rx in TIME:
        if re.search(rx, t): return n
    return 'none'

if __name__ == '__main__':
    split = sys.argv[1]; n = int(sys.argv[2]) if len(sys.argv) > 2 else 2; only = sys.argv[3] if len(sys.argv) > 3 else None
    Q = [json.loads(l) for l in open(f'{split}/questions.jsonl')]
    try: A = {json.loads(l)['id']: json.loads(l) for l in open(f'{split}/answers.jsonl')}
    except FileNotFoundError: A = {}
    cnt = collections.Counter(); ex = collections.defaultdict(list); ty = collections.defaultdict(collections.Counter); nb = collections.defaultdict(set)
    for x in Q:
        k = tag(x['question']); cnt[k] += 1; ex[k].append(x); nb[k].add(x['business_id'])
        if A: ty[k][A[x['id']]['type'][:4]] += 1
    random.seed(0)
    for k, c in cnt.most_common():
        if only and k != only: continue
        print(f'## {k} {c} biz={len(nb[k])} {dict(ty[k])}')
        for x in random.sample(ex[k], min(n, len(ex[k]))):
            print('   ', x['business_id'][-3:], x['question'][:200], '=>', json.dumps(A[x['id']]['answer'], ensure_ascii=False)[:70] if A else '')
    print('TIME', collections.Counter(ttag(x['question']) for x in Q).most_common())
