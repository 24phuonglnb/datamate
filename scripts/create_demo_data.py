"""Create tiny SYNTHETIC data for smoke tests. No competition data is included."""
import csv
import json
import sqlite3
from pathlib import Path

from openpyxl import Workbook


def create_demo(root: Path) -> None:
    business = root / 'data' / 'shop_demo'
    business.mkdir(parents=True, exist_ok=True)
    (business / 'README.md').write_text('Cửa hàng bán vật liệu xây dựng. sales.csv là lịch sử giao dịch.\n', encoding='utf-8')
    with (business / 'sales.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['ngay', 'san_pham', 'so_luong', 'doanh_thu'])
        writer.writerows([
            ['2026-03-01', 'Xi măng A', 4, 400000],
            ['2026-03-02', 'Gạch B', 3, 150000],
            ['2026-03-03', 'Xi măng A', 6, 600000],
            ['2026-03-05', 'Gạch B', 12, 600000],
        ])
    wb = Workbook()
    ws = wb.active
    ws.title = 'Ton kho'
    ws.append(['san_pham', 'ton_kho'])
    ws.append(['Xi măng A', 22])
    ws.append(['Gạch B', 33])
    wb.save(business / 'inventory.xlsx')
    # sqlite3 context manager commits/rollbacks but does NOT close the connection;
    # close explicitly to avoid ResourceWarning from lingering file descriptors.
    con = sqlite3.connect(business / 'payments.sqlite')
    try:
        con.execute('CREATE TABLE IF NOT EXISTS pay (customer TEXT, amount INTEGER)')
        con.executemany('INSERT INTO pay VALUES (?, ?)', [('Khách A', 50000), ('Khách B', 30000)])
        con.commit()
    finally:
        con.close()
    (root / 'rulebook.md').write_text('Doanh thu là tổng doanh_thu. Hàng bán chạy nhất dựa trên tổng so_luong.\n', encoding='utf-8')
    with (root / 'calendar.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['solar_date', 'lunar_date'])
        writer.writerow(['2026-03-04', '2026-01-16'])
    questions = [
        {'id': 'demo_1', 'business_id': 'shop_demo', 'question': 'Tổng doanh thu tới ngày 3/3 là bao nhiêu?', 'as_of_date': '2026-03-04'},
        {'id': 'demo_2', 'business_id': 'shop_demo', 'question': 'Sản phẩm nào bán chạy nhất tới ngày 3/3?', 'as_of_date': '2026-03-04'},
        {'id': 'demo_3', 'business_id': 'shop_demo', 'question': 'Tỷ lệ khách hàng hài lòng là bao nhiêu?', 'as_of_date': '2026-03-04'},
    ]
    with (root / 'questions.jsonl').open('w', encoding='utf-8') as f:
        for q in questions:
            f.write(json.dumps(q, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('path', nargs='?', default='example_data')
    create_demo(Path(parser.parse_args().path))
