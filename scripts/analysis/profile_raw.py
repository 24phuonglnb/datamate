"""Dump the first rows of every file / sheet / SQLite table of train + public_test,
without any cleaning, to see raw layouts (headers, preambles, merged cells).

Usage: python scripts/analysis/profile_raw.py > profile.txt   (run from repo root)
"""
import os
from pathlib import Path
os.chdir(Path(__file__).resolve().parents[2] / 'data')
import sys, os, glob, sqlite3, csv, json
from openpyxl import load_workbook
def show(name, header, rows, n):
    print(f'  -- {name} | rows~{n}')
    print('     H:', header)
    for r in rows: print('     ', r)
for split in ['train','public_test']:
    for b in sorted(os.listdir(f'{split}/data')):
        print(f'##### {split}/{b}')
        for p in sorted(glob.glob(f'{split}/data/{b}/*')):
            fn=os.path.basename(p)
            try:
                if fn.endswith('.csv'):
                    with open(p,encoding='utf-8-sig',newline='') as f:
                        rd=csv.reader(f); rows=[next(rd,None) for _ in range(5)]
                        n=sum(1 for _ in rd)+4
                    show(fn, rows[0], rows[1:], n)
                elif fn.endswith('.xlsx'):
                    wb=load_workbook(p,read_only=True,data_only=True)
                    for ws in wb.worksheets:
                        it=ws.iter_rows(values_only=True); rows=[]
                        for i,r in enumerate(it):
                            if i<6: rows.append([str(x)[:40] if x is not None else None for x in r])
                        show(f'{fn}[{ws.title}]', rows[0] if rows else None, rows[1:], i if rows else 0)
                elif fn.endswith('.sqlite'):
                    c=sqlite3.connect(p)
                    for (t,) in c.execute("select name from sqlite_master where type='table'"):
                        cols=[r[1] for r in c.execute(f'pragma table_info("{t}")')]
                        n=c.execute(f'select count(*) from "{t}"').fetchone()[0]
                        show(f'{fn}:{t}', cols, c.execute(f'select * from "{t}" limit 3').fetchall(), n)
            except Exception as e: print('  !!',fn,e)
