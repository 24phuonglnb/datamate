"""Check that cleaned sales ledgers reproduce official monthly-revenue answers.

ANALYSIS ONLY. The hand mapping M below is keyed on business id; it stands in for
what an automatic column-mapping step should output. Never import this into src/.

For every train question of the form "doanh thu tháng M/YYYY" (no other filter),
recompute revenue with three variants: full cleaning, no fill-down, no de-duplication,
and compare with data/train/answers.jsonl.

Usage (from repo root, data unzipped under data/):
    python scripts/analysis/revenue_check.py [biz_101 biz_103 ...]
"""
import sys, json, re, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd
from src.cleaning import load_business, fill_order_level, drop_export_duplicates, parse_date, parse_number, norm_key
from intent_tagger import deacc
DATA = ROOT / 'data' / 'train'
class L(dict):
    def __missing__(s,b): return load_business(DATA / 'data' / b)
T=L()
Q=[json.loads(l) for l in open(DATA / 'questions.jsonl')]; A={json.loads(l)['id']:json.loads(l) for l in open(DATA / 'answers.jsonl')}
# hand mapping == what a mapping step would output: table, order key, date, status, amount
M={'biz_101':('ban_hang','Mã hóa đơn','Ngày tháng','Kết quả','Thanh tien'),
   'biz_103':('DonHang_ChiTiet','Mã đơn hàng','Ngày đặt hàng','Trạng thái đơn hàng','Tổng tiền'),
   'biz_117':('SoBanHang','Mã phiếu','Ngày lập','Ghi chú TT','Tiền'),
   'biz_107':('SoBanHang',None,'ngay_ban','Trạng thái xử lý','Tổng tiền'),
   'biz_105':('SoBanHang','Mã hóa đơn','Ngày giao dịch','Status','Trị giá'),
   'biz_112':('So_chi_tiet_ban_hang','Mã đơn hàng','Ngày','Trạng thái','Thành tiền'),
   'biz_102':('DonHang_ChiTiet','Mã đơn hàng','Ngày đặt hàng','Trạng thái đơn hàng','Tổng tiền'),
   'biz_114':('ban_hang','Mã GD','Ngày','trang_thai','Tổng'),
   'biz_125':('ban_hang',None,None,None,None)}
def status(v):
    k=norm_key(v) if v is not None else ''
    if re.search(r'huy|cancel|khong giao duoc',k): return 'huy'
    if re.search(r'tra|return|hoan hang|hoan tra',k) and 'hoan thanh' not in k: return 'tra'
    if re.search(r'dang|cho giao|shipping|chua giao',k): return 'giao'
    return 'xong'
ONLY=sys.argv[1:]
for b,(tn,ok,dc,sc,ac) in M.items():
    if dc is None or (ONLY and b not in ONLY): continue
    t=[x for x in T[b] if x.name==tn][0]; raw=t.df
    res={}
    for var in ['full','nofill','nodedup']:
        df=raw
        if ok and var!='nofill': df=fill_order_level(df,ok)
        n0=len(df)
        if ok and var!='nodedup': df=drop_export_duplicates(df,ok)
        ndup=n0-len(df)
        d=[parse_date(v,y if y==y else None) for v,y in zip(df[dc],df['__year'])]
        df=df.assign(_d=pd.to_datetime(pd.Series(d,index=df.index)),_a=[parse_number(v) for v in df[ac]],_s=[status(v) for v in df[sc]])
        if ok:  # order-level status: any line says returned/cancelled
            bad=df[df._s.isin(['huy','tra'])][ok].unique(); good=df[~df[ok].isin(bad)]
        else: good=df[~df._s.isin(['huy','tra'])]
        res[var]=(good,ndup,df)
    hit=collections.Counter(); tot=0; miss=[]
    for q in Q:
        if q['business_id']!=b or A[q['id']]['type']!='number': continue
        s=deacc(q['question'])
        m=re.search(r'thang (\d{1,2})(?:/| nam )(\d{4})',s)
        if not m or not re.search(r'doanh thu|dthu',s): continue
        if re.search(r'nhom|khach|\bdon\b|\bca\b|nhan vien|tra bang|so voi|%|phan tram|ngay|hoat chat|ke don|size|trung binh|binh quan|moi|quy|mat hang|mon |ban chay|top|doanh thu cua (?!cua hang)|dthu cua (?!cua hang)',s): continue
        mo,y=int(m.group(1)),int(m.group(2)); asof=pd.Timestamp(q['as_of_date']); tot+=1
        for var,(good,ndup,_) in res.items():
            g=good[(good._d.dt.year==y)&(good._d.dt.month==mo)&(good._d<=asof)]
            v=round(g._a.sum())
            if v==A[q['id']]['answer']: hit[var]+=1
            elif var=='full': miss.append((q['question'][:70],v,A[q['id']]['answer']))
    df=res['full'][2]
    print(b,'questions',tot,dict(hit),'| dup rows dropped',res['full'][1],'| blank keys filled',int(raw[ok].isna().sum()) if ok else '-', '| unparsed date',int(df._d.isna().sum()),'amt',int(df._a.isna().sum()),'| status',dict(collections.Counter(df._s)))
    for x in miss[:9]: print('    MISS',x)
