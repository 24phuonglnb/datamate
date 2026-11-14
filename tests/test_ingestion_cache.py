"""Unit and integration tests for Task T6: src/ingestion.py cache and legacy integration."""
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from scripts.create_demo_data import create_demo
from src.ingestion import (
    BusinessDB,
    TableInfo,
    compute_business_hash,
)

ROOT = Path(__file__).resolve().parents[1]
TRAIN_DIR = ROOT / "data" / "train"


def test_business_hash_deterministic(tmp_path: Path) -> None:
    """Verify compute_business_hash is deterministic and changes when file content/mtime changes."""
    biz_dir = tmp_path / "biz_hash_test"
    biz_dir.mkdir()
    f1 = biz_dir / "sales.csv"
    f1.write_text("ngay,san_pham,so_luong,doanh_thu\n2026-03-01,A,1,1000\n", encoding="utf-8")

    h1 = compute_business_hash(biz_dir)
    h2 = compute_business_hash(biz_dir)
    assert h1 == h2
    assert len(h1) == 64

    # Change file content and size
    f1.write_text("ngay,san_pham,so_luong,doanh_thu\n2026-03-01,A,2,2000\n2026-03-02,B,5,50000\n", encoding="utf-8")
    h3 = compute_business_hash(biz_dir)
    assert h3 != h1


def test_cache_hit_and_reuse(tmp_path: Path) -> None:
    """Verify first instantiation builds and caches; second instantiation reuses cached SQLite file."""
    demo_root = tmp_path / "demo"
    create_demo(demo_root)
    biz_dir = demo_root / "data" / "shop_demo"
    cal_file = demo_root / "calendar.csv"
    cache_dir = tmp_path / "cache"

    # 1. Cold build (cache miss)
    db1 = BusinessDB(biz_dir, cal_file, cache_dir=cache_dir)
    b_hash = compute_business_hash(biz_dir, cal_file)
    cache_file = cache_dir / f"{b_hash}.sqlite"
    assert cache_file.is_file(), "Cache file must exist after first BusinessDB init"

    # Check query result
    cols, rows = db1.execute_readonly('SELECT SUM(CAST("doanh_thu" AS INTEGER)) FROM "sales"')
    assert rows[0][0] == 1750000
    stext1 = db1.schema_text()
    db1.close()

    # 2. Warm build (cache hit)
    with mock.patch("src.ingestion.build_database") as mock_build:
        db2 = BusinessDB(biz_dir, cal_file, cache_dir=cache_dir)
        mock_build.assert_not_called()  # Must not re-run build_database!

    cols2, rows2 = db2.execute_readonly('SELECT SUM(CAST("doanh_thu" AS INTEGER)) FROM "sales"')
    assert rows2 == rows
    assert db2.schema_text() == stext1
    db2.close()


def test_readonly_and_mutation_prohibition(tmp_path: Path) -> None:
    """Verify SQLite authorizer and query_only prohibit mutations on cached DB."""
    demo_root = tmp_path / "demo"
    create_demo(demo_root)
    biz_dir = demo_root / "data" / "shop_demo"
    cal_file = demo_root / "calendar.csv"
    cache_dir = tmp_path / "cache"

    db = BusinessDB(biz_dir, cal_file, cache_dir=cache_dir)
    try:
        # Non-SELECT / non-WITH query rejected by regex
        with pytest.raises(ValueError, match="Only SELECT/CTE"):
            db.execute_readonly('DELETE FROM "sales"')

        with pytest.raises(ValueError, match="Only SELECT/CTE"):
            db.execute_readonly('INSERT INTO "sales" VALUES ("2026-03-10", "X", 1, 100)')

        # Mutation disguised inside multi-statement or CTE rejected by authorizer
        with pytest.raises((sqlite3.DatabaseError, sqlite3.Warning)):
            db.execute_readonly('SELECT * FROM "sales"; DROP TABLE "sales"')
    finally:
        db.close()


def test_legacy_mode_switch(tmp_path: Path) -> None:
    """Verify legacy switch (param or DATAMATE_LEGACY_INGESTION=1) reverts to legacy uncleaned DB."""
    demo_root = tmp_path / "demo"
    create_demo(demo_root)
    biz_dir = demo_root / "data" / "shop_demo"
    cal_file = demo_root / "calendar.csv"

    # Via constructor parameter
    db_legacy = BusinessDB(biz_dir, cal_file, legacy=True)
    assert db_legacy._legacy is True
    names_legacy = [t.name for t in db_legacy.tables]
    assert "sales" in names_legacy
    assert "inventory__ton_kho" in names_legacy
    assert "payments__pay" in names_legacy
    assert "calendar" in names_legacy
    # View tables must NOT exist in legacy mode
    assert "v_valid_orders" not in names_legacy
    assert "raw_sales" not in names_legacy
    db_legacy.close()

    # Via environment variable
    with mock.patch.dict(os.environ, {"DATAMATE_LEGACY_INGESTION": "1"}):
        db_env_legacy = BusinessDB(biz_dir, cal_file)
        assert db_env_legacy._legacy is True
        db_env_legacy.close()


def test_no_cache_flag(tmp_path: Path) -> None:
    """Verify DATAMATE_NO_CACHE=1 builds in-memory without creating a cache file."""
    demo_root = tmp_path / "demo"
    create_demo(demo_root)
    biz_dir = demo_root / "data" / "shop_demo"
    cal_file = demo_root / "calendar.csv"
    cache_dir = tmp_path / "cache_empty"

    with mock.patch.dict(os.environ, {"DATAMATE_NO_CACHE": "1"}):
        db = BusinessDB(biz_dir, cal_file, cache_dir=cache_dir)
        cols, rows = db.execute_readonly('SELECT SUM(CAST("doanh_thu" AS INTEGER)) FROM "sales"')
        assert rows[0][0] == 1750000
        assert not cache_dir.exists() or list(cache_dir.iterdir()) == []
        db.close()


def test_corrupted_cache_recovery(tmp_path: Path) -> None:
    """Verify corrupted cache file is automatically detected, deleted, and rebuilt."""
    demo_root = tmp_path / "demo"
    create_demo(demo_root)
    biz_dir = demo_root / "data" / "shop_demo"
    cal_file = demo_root / "calendar.csv"
    cache_dir = tmp_path / "cache_corrupt"
    cache_dir.mkdir(parents=True)

    b_hash = compute_business_hash(biz_dir, cal_file)
    corrupted_file = cache_dir / f"{b_hash}.sqlite"
    corrupted_file.write_text("THIS IS NOT A VALID SQLITE FILE", encoding="utf-8")

    db = BusinessDB(biz_dir, cal_file, cache_dir=cache_dir)
    cols, rows = db.execute_readonly('SELECT SUM(CAST("doanh_thu" AS INTEGER)) FROM "sales"')
    assert rows[0][0] == 1750000
    # Cache file must have been replaced with valid SQLite
    conn_check = sqlite3.connect(str(corrupted_file))
    assert conn_check.execute("SELECT 1").fetchone()[0] == 1
    conn_check.close()
    db.close()


@pytest.mark.skipif(not (TRAIN_DIR / "data" / "biz_102").is_dir(), reason="train data not available")
def test_real_shop_cache_and_views(tmp_path: Path) -> None:
    """Verify BusinessDB on a real train shop (biz_102) exposes views and matches official answers."""
    biz_dir = TRAIN_DIR / "data" / "biz_102"
    cal_file = TRAIN_DIR / "calendar.csv"
    cache_dir = tmp_path / "cache_real"

    db = BusinessDB(biz_dir, cal_file, cache_dir=cache_dir)
    table_names = {t.name for t in db.tables}
    assert {"v_valid_orders", "v_valid_lines", "v_orders", "v_lines", "v_items"} <= table_names

    # Check monthly revenue query from v_valid_orders (Jan 2025: 435803500)
    cols, rows = db.execute_readonly(
        "SELECT CAST(ROUND(SUM(revenue)) AS INTEGER) FROM v_valid_orders WHERE order_month = '2025-01'"
    )
    assert rows[0][0] == 435803500
    db.close()
