"""Run a no-GPU end-to-end software demo with a fixed synthetic test plan.

NOT INCLUDED in competition Docker. This does not validate model quality.
"""
import json
from pathlib import Path

from scripts.create_demo_data import create_demo
from src.predict import run


class ScriptedTestModel:
    def __init__(self):
        self.calls = iter([
            '{"type":"number","sql":"SELECT SUM(CAST(doanh_thu AS INTEGER)) FROM sales WHERE ngay <= \'2026-03-03\'"}',
            '{"type":"string","sql":"SELECT san_pham FROM sales WHERE ngay <= \'2026-03-03\' GROUP BY san_pham ORDER BY SUM(CAST(so_luong AS INTEGER)) DESC LIMIT 1"}',
            '{"type":"unanswerable","reason":"Không có dữ liệu đo độ hài lòng"}',
        ])

    def generate(self, system, user):
        return next(self.calls), None


if __name__ == "__main__":
    root = Path('example_data')
    create_demo(root)
    output = Path('example_result')
    count = run(root, output, ScriptedTestModel())
    print(f'{count} synthetic questions processed. Output: {output / "submission.jsonl"}')
    print((output / 'submission.jsonl').read_text(encoding='utf-8'))
