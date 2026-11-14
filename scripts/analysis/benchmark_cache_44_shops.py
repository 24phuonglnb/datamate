"""Benchmark cold vs warm (cached) DB build time, cache size, and peak memory for all 44 shops."""
from __future__ import annotations

import json
import os
import resource
import shutil
import time
from pathlib import Path

from src.ingestion import BusinessDB, compute_business_hash

ROOT = Path(__file__).resolve().parents[2]
TRAIN_DIR = ROOT / "data" / "train"
TEST_DIR = ROOT / "data" / "public_test"
BENCHMARK_CACHE_DIR = Path("/tmp/datamate_bench_cache")


def get_peak_memory_mb() -> float:
    # ru_maxrss on Linux is in kilobytes
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_maxrss / 1024.0


def benchmark_shop(
    biz_dir: Path,
    cal_file: Path | None,
    cache_dir: Path,
) -> dict[str, object]:
    biz_name = biz_dir.name

    # 1. Cold build
    t0 = time.perf_counter()
    db_cold = BusinessDB(biz_dir, cal_file, cache_dir=cache_dir)
    t_cold = time.perf_counter() - t0

    # Collect stats
    b_hash = compute_business_hash(biz_dir, cal_file)
    cache_file = cache_dir / f"{b_hash}.sqlite"
    cache_size_bytes = cache_file.stat().st_size if cache_file.is_file() else 0
    cache_size_mb = cache_size_bytes / (1024.0 * 1024.0)

    # Get row count from lines or first table
    n_rows = 0
    tables_list = [t.name for t in db_cold.tables]
    has_views = "v_valid_orders" in tables_list
    if has_views:
        try:
            n_rows = db_cold.connection.execute("SELECT COUNT(*) FROM lines").fetchone()[0]
        except Exception:
            pass
    if n_rows == 0:
        for t in db_cold.tables:
            if not t.name.startswith("v_") and not t.name.startswith("raw_") and "__" not in t.name:
                n_rows += t.nrows

    db_cold.close()

    # 2. Warm build (from cache)
    t1 = time.perf_counter()
    db_warm = BusinessDB(biz_dir, cal_file, cache_dir=cache_dir)
    t_warm = time.perf_counter() - t1
    db_warm.close()

    return {
        "shop": biz_name,
        "n_rows": n_rows,
        "has_views": has_views,
        "cold_s": round(t_cold, 3),
        "warm_ms": round(t_warm * 1000.0, 2),
        "cache_mb": round(cache_size_mb, 2),
        "peak_rss_mb": round(get_peak_memory_mb(), 1),
    }


def main() -> None:
    # Clear benchmark cache
    if BENCHMARK_CACHE_DIR.exists():
        shutil.rmtree(BENCHMARK_CACHE_DIR)
    BENCHMARK_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    shops: list[tuple[Path, Path | None]] = []
    if (TRAIN_DIR / "data").is_dir():
        train_cal = TRAIN_DIR / "calendar.csv"
        for p in sorted((TRAIN_DIR / "data").iterdir()):
            if p.is_dir():
                shops.append((p, train_cal if train_cal.is_file() else None))

    if (TEST_DIR / "data").is_dir():
        test_cal = TEST_DIR / "calendar.csv"
        for p in sorted((TEST_DIR / "data").iterdir()):
            if p.is_dir():
                shops.append((p, test_cal if test_cal.is_file() else None))

    print(f"Benchmarking {len(shops)} shops across train and public_test...")
    print(f"{'Shop':<10} | {'Rows':>8} | {'Views?':<6} | {'Cold (s)':>9} | {'Warm (ms)':>10} | {'Cache (MB)':>10} | {'RSS (MB)':>9}")
    print("-" * 75)

    results = []
    total_cold_s = 0.0
    total_warm_s = 0.0
    total_cache_bytes = 0

    for idx, (biz_dir, cal_file) in enumerate(shops, 1):
        stat = benchmark_shop(biz_dir, cal_file, BENCHMARK_CACHE_DIR)
        results.append(stat)
        total_cold_s += float(stat["cold_s"])
        total_warm_s += float(stat["warm_ms"]) / 1000.0
        total_cache_bytes += int(float(stat["cache_mb"]) * 1024 * 1024)

        print(
            f"{stat['shop']:<10} | {stat['n_rows']:>8} | {'Yes' if stat['has_views'] else 'No':<6} | "
            f"{stat['cold_s']:>9.3f} | {stat['warm_ms']:>10.2f} | {stat['cache_mb']:>10.2f} | {stat['peak_rss_mb']:>9.1f}"
        )

    print("-" * 75)
    print(f"Total cold build time: {total_cold_s:.2f} s ({total_cold_s / 60.0:.2f} min)")
    print(f"Total warm build time: {total_warm_s:.3f} s ({total_warm_s * 1000.0 / len(shops):.2f} ms/shop avg)")
    print(f"Total cache size: {total_cache_bytes / (1024.0 * 1024.0):.2f} MB")
    print(f"Final Peak RSS: {get_peak_memory_mb():.1f} MB")

    out_file = ROOT / "reports" / "ingestion_benchmark_44_shops.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "n_shops": len(shops),
        "total_cold_seconds": round(total_cold_s, 2),
        "total_warm_seconds": round(total_warm_s, 3),
        "avg_warm_ms": round(total_warm_s * 1000.0 / len(shops), 2),
        "total_cache_mb": round(total_cache_bytes / (1024.0 * 1024.0), 2),
        "peak_rss_mb": round(get_peak_memory_mb(), 1),
        "shops": results,
    }
    out_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved benchmark report to {out_file}")


if __name__ == "__main__":
    main()
