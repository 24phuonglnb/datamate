"""Data-layer invariants per shop (CPU).  Derive thresholds from the train shops, then report any shop set.

    DATAMATE_CACHE_DIR=<dir> python scripts/data_invariants.py derive --data-dir data/train/train       # writes src/router/invariant_thresholds.json
    DATAMATE_CACHE_DIR=<dir> python scripts/data_invariants.py report --data-dir <public dir> --out <md>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ingestion import BusinessDB  # noqa: E402
from src.router import invariants as inv  # noqa: E402


def run(data_dir: Path, shops=None):
    cal = data_dir / "calendar.csv"
    res = {}
    for d in sorted(p for p in (data_dir / "data").iterdir() if p.is_dir()):
        if shops and d.name not in shops:
            continue
        db = BusinessDB(d, cal if cal.is_file() else None)
        try:
            res[d.name] = inv.compute(d, db.connection)
        except Exception as exc:  # a shop the data layer cannot even load is itself low confidence
            res[d.name] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}", "no_ledger": 1}
        db.close()
        print(d.name, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in res[d.name].items()}, flush=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["derive", "report"])
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out")
    ap.add_argument("--metrics-out")
    a = ap.parse_args()
    res = run(Path(a.data_dir))
    if a.metrics_out:
        Path(a.metrics_out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.mode == "derive":
        ok = {s: m for s, m in res.items() if not m.get("no_ledger")}
        thr = {"_source": f"{len(ok)} train shops with views; worst value per metric", "shops_without_ledger": sorted(set(res) - set(ok))}
        for k in inv.HIGH_IS_BAD:
            vals = [m[k] for m in ok.values() if m.get(k) is not None]
            thr[k] = {"worst": max(vals), "n": len(vals)}
        vals = [m["amount_ratio"] for m in ok.values() if m.get("amount_ratio") is not None]
        thr["amount_ratio"] = {"min": min(vals), "max": max(vals), "n": len(vals)}
        inv.THRESHOLDS_PATH.write_text(json.dumps(thr, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(thr, ensure_ascii=False, indent=1))
    else:
        thr = inv.load_thresholds()
        cols = ["amount_ratio", *inv.HIGH_IS_BAD, "no_ledger"]
        L = ["| shop | " + " | ".join(cols) + " | flag |", "|---|" + "---|" * (len(cols) + 1)]
        for s, m in res.items():
            fl = inv.flags(m, thr)
            wn = inv.warnings(m, thr)
            cells = ["-" if m.get(c) is None else (f"{m[c]:.4g}" if isinstance(m[c], float) else str(m[c])) for c in cols]
            L.append(f"| {s} | " + " | ".join(cells) + f" | {'LOW_CONFIDENCE: ' + '; '.join(fl) if fl else 'ok'}{' [warn: ' + '; '.join(wn) + ']' if wn else ''} |")
        text = "\n".join(L)
        print(text)
        if a.out:
            Path(a.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
