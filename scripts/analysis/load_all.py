"""Load every business of train + public_test with src.cleaning.load_business and
print table shapes, merged sources, and tables whose header detection looks wrong
(columns named col_* or a title preamble). Pickles the result for later analysis.

Usage (from repo root): python scripts/analysis/load_all.py OUT_DIR
"""
import sys, os, time, pickle
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
from src.cleaning import load_business
out={}
for split in ['train','public_test']:
    for b in sorted(os.listdir(f'data/{split}/data')):
        t0=time.time()
        try:
            ts=load_business(f'data/{split}/data/{b}')
        except Exception as e:
            print(b,'ERR',repr(e)); continue
        out[b]=ts
        print(f'{b} {time.time()-t0:.1f}s', ' ; '.join(f'{t.name}({len(t.df)}r,{len(t.columns)}c,{len(t.sources)}src)' for t in ts)[:600])
        for t in ts:
            bad=[c for c in t.columns if c.startswith('col_')]
            if bad or t.preamble: print('     pre/bad:',t.name,t.preamble[:2],bad[:4], '| hdr:',t.columns[:6])
pickle.dump(out,open(f'{sys.argv[1]}/tables.pkl','wb'))
