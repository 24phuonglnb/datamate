"""Ingest business CSV/XLSX/SQLite files into a cached read-only SQLite view.

Integrates the Task T4 cleaned data layer and rulebook views (v_lines, v_valid_orders,
v_items, etc.) while preserving the exact BusinessDB interface required by Agent (T6).
Also supports disk-based SQLite caching in /tmp/datamate_cache and a legacy ingestion
switch (DATAMATE_LEGACY_INGESTION=1) for A/B testing.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

from src.views import build_database, schema_text as views_schema_text

_CACHE_VERSION = "20261111_v1"
DEFAULT_CACHE_DIR = Path(os.environ.get("DATAMATE_CACHE_DIR", "/tmp/datamate_cache"))


def sql_ident(raw: str) -> str:
    return '"' + str(raw).replace('"', '""') + '"'


def safe_name(value: str) -> str:
    result = re.sub(r"[^\w]+", "_", value, flags=re.UNICODE).strip("_")
    return result.lower() or "table"


def cell_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float, str, bytes)):
        return v
    return str(v)


def clean_columns(headers: Iterable[Any]) -> list[str]:
    result, used = [], set()
    for idx, h in enumerate(headers):
        base = str(h).strip() if h is not None else ""
        base = base or f"column_{idx+1}"
        proposed, count = base, 2
        while proposed.lower() in used:
            proposed = f"{base}_{count}"
            count += 1
        used.add(proposed.lower())
        result.append(proposed)
    return result


def _infer_col_type(values: list[Any]) -> str:
    """Return a rough SQLite affinity hint for schema display."""
    non_null = [v for v in values if v is not None and str(v).strip()]
    if not non_null:
        return "TEXT"
    numeric = 0
    for v in non_null:
        try:
            float(str(v).replace(",", ""))
            numeric += 1
        except (ValueError, TypeError):
            pass
    if numeric == len(non_null):
        return "NUMERIC"
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$|^\d{1,2}/\d{1,2}/\d{4}$")
    if all(date_re.match(str(v)) for v in non_null):
        return "DATE"
    return "TEXT"


def compute_business_hash(business_dir: Path, calendar_path: Path | None = None) -> str:
    """Compute deterministic SHA256 from filenames, sizes, and mtimes of all files in business_dir + calendar."""
    h = hashlib.sha256()
    h.update(f"version:{_CACHE_VERSION}\n".encode("utf-8"))

    entries: list[tuple[str, int, int]] = []
    if business_dir.is_dir():
        for p in sorted(business_dir.rglob("*")):
            if p.is_file() and not p.name.startswith("~$") and not p.name.startswith("."):
                try:
                    st = p.stat()
                    rel = str(p.relative_to(business_dir))
                    mtime = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
                    entries.append((rel, st.st_size, mtime))
                except OSError:
                    continue

    cal_target = calendar_path
    if cal_target is None or not cal_target.is_file():
        for cand in (
            business_dir / "calendar.csv",
            business_dir.parent / "calendar.csv",
            business_dir.parent.parent / "calendar.csv",
        ):
            if cand.is_file():
                cal_target = cand
                break

    if cal_target is not None and cal_target.is_file():
        try:
            st = cal_target.stat()
            mtime = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
            entries.append((f"__calendar__:{cal_target.name}", st.st_size, mtime))
        except OSError:
            pass

    for name, size, mtime in sorted(entries, key=lambda x: x[0]):
        h.update(f"{name}:{size}:{mtime}\n".encode("utf-8"))

    return h.hexdigest()


def _create_legacy_alias_views(conn: sqlite3.Connection) -> list[str]:
    """Create backward-compatible alias views for legacy table names (e.g. inventory__ton_kho, payments__pay)."""
    aliases_created = []
    try:
        row = conn.execute("SELECT value FROM _schema_meta WHERE key = 'meta'").fetchone()
        meta = json.loads(row[0]) if row else {}
    except Exception:
        meta = {}

    tables_meta = meta.get("tables", [])
    for t_info in tables_meta:
        clean_name = t_info.get("clean_name")
        sources = t_info.get("sources", [])
        if not clean_name:
            continue
        for src in sources:
            alias = None
            if "[" in src and src.endswith("]"):
                # e.g. "inventory.xlsx[Ton kho]"
                file_part, sheet_part = src[:-1].split("[", 1)
                stem = safe_name(Path(file_part).stem)
                sheet = safe_name(sheet_part)
                alias = f"{stem}__{sheet}"
            elif ":" in src and not src.endswith("]"):
                # e.g. "payments.sqlite:pay"
                file_part, tbl_part = src.split(":", 1)
                stem = safe_name(Path(file_part).stem)
                tbl = safe_name(tbl_part)
                alias = f"{stem}__{tbl}"

            if alias and alias != clean_name:
                try:
                    conn.execute(f'CREATE VIEW IF NOT EXISTS "{alias}" AS SELECT * FROM "{clean_name}"')
                    aliases_created.append(alias)
                except sqlite3.Error:
                    pass
    return aliases_created


@dataclass
class TableInfo:
    name: str
    source: str
    columns: list[str]
    col_types: list[str]
    nrows: int
    examples: list[dict[str, Any]]


def _populate_tables(conn: sqlite3.Connection) -> list[TableInfo]:
    """Inspect SQLite database to populate self.tables for backward compatibility."""
    tables: list[TableInfo] = []
    try:
        row = conn.execute("SELECT value FROM _schema_meta WHERE key = 'meta'").fetchone()
        meta = json.loads(row[0]) if row else {}
    except Exception:
        meta = {}

    tables_meta = meta.get("tables", [])
    meta_by_name = {t.get("clean_name"): t for t in tables_meta if t.get("clean_name")}
    meta_by_raw = {t.get("raw_name"): t for t in tables_meta if t.get("raw_name")}
    ledger_meta = meta.get("ledger_meta", {})

    all_objects = conn.execute(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') "
        "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_schema%' ORDER BY name"
    ).fetchall()

    priority_views = ["v_valid_orders", "v_valid_lines", "v_orders", "v_lines", "v_items"]

    def sort_key(item: tuple[str, str]) -> tuple[int, str]:
        name, otype = item
        if name in priority_views:
            return (0, str(priority_views.index(name)))
        if otype == "view" and name.startswith("v_"):
            return (1, name)
        if name in ("lines", "items"):
            return (2, name)
        if not name.startswith("raw_") and "__" not in name:
            return (3, name)
        if "__" in name:
            return (4, name)
        if name == "calendar":
            return (5, name)
        return (6, name)

    all_objects.sort(key=sort_key)

    for name, otype in all_objects:
        try:
            col_info = conn.execute(f'PRAGMA table_info("{name}")').fetchall()
            cols = [r[1] for r in col_info]
            col_types = [r[2] or "TEXT" for r in col_info]
        except sqlite3.Error:
            cols, col_types = [], []

        nrows = 0
        if name in meta_by_name:
            nrows = meta_by_name[name].get("n_rows", 0)
        elif name in meta_by_raw:
            nrows = meta_by_raw[name].get("n_raw_rows", 0)
        elif name == "lines":
            nrows = ledger_meta.get("n_lines", 0)
        elif name == "items":
            nrows = ledger_meta.get("n_items", 0)
        elif name in priority_views and "n_lines" in ledger_meta:
            nrows = ledger_meta.get("n_lines", 0)
        else:
            try:
                cnt_row = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()
                nrows = cnt_row[0] if cnt_row else 0
            except sqlite3.Error:
                nrows = 0

        source = f"{otype}:{name}"
        if name in meta_by_name:
            srcs = meta_by_name[name].get("sources", [])
            source = srcs[0] if srcs else name
        elif name in meta_by_raw:
            source = f"raw_{meta_by_raw[name].get('clean_name', name)}"
        elif name == "calendar":
            source = "calendar.csv"

        examples: list[dict[str, Any]] = []
        if cols:
            try:
                sample_rows = conn.execute(f'SELECT * FROM "{name}" LIMIT 2').fetchall()
                for srow in sample_rows:
                    examples.append(dict(zip(cols, [cell_value(v) for v in srow])))
            except sqlite3.Error:
                pass

        tables.append(TableInfo(
            name=name,
            source=source,
            columns=cols,
            col_types=col_types,
            nrows=nrows,
            examples=examples,
        ))

    return tables


class BusinessDB:
    def __init__(
        self,
        business_dir: Path | str,
        calendar_path: Path | str | None = None,
        legacy: bool | None = None,
        cache_dir: Path | str | None = None,
    ):
        self.business_dir = Path(business_dir)
        if not self.business_dir.is_dir():
            raise FileNotFoundError(f"Business directory missing: {self.business_dir}")
        self.calendar_path = Path(calendar_path) if calendar_path else None
        self.tables: list[TableInfo] = []
        self.used_names: set[str] = set()

        # Decide whether to use legacy ingestion (for A/B testing)
        if legacy is None:
            legacy_env = os.environ.get("DATAMATE_LEGACY_INGESTION", "0").lower()
            self._legacy = legacy_env in ("1", "true", "yes")
        else:
            self._legacy = bool(legacy)

        if self._legacy:
            self.connection = sqlite3.connect(":memory:")
            self._load_legacy()
        else:
            self.connection = self._init_views_and_cache(cache_dir)
            self.tables = _populate_tables(self.connection)
            self.used_names = {t.name for t in self.tables}

        # SQLite authorizer + query_only prohibit mutations and external attachments.
        self.connection.execute("PRAGMA query_only = ON")
        try:
            self.connection.enable_load_extension(False)
        except AttributeError:
            pass
        self.connection.set_authorizer(self._authorizer)

    def _init_views_and_cache(self, custom_cache_dir: Path | str | None = None) -> sqlite3.Connection:
        no_cache_env = os.environ.get("DATAMATE_NO_CACHE", "0").lower()
        use_cache = no_cache_env not in ("1", "true", "yes")

        if not use_cache:
            conn = build_database(self.business_dir, self.calendar_path, db_path=":memory:")
            _create_legacy_alias_views(conn)
            conn.commit()
            return conn

        target_cache_dir = Path(custom_cache_dir or DEFAULT_CACHE_DIR)
        b_hash = compute_business_hash(self.business_dir, self.calendar_path)
        cache_file = target_cache_dir / f"{b_hash}.sqlite"

        # Check for cache hit
        if cache_file.is_file():
            try:
                conn = sqlite3.connect(str(cache_file))
                # Validate SQLite integrity
                conn.execute("SELECT 1 FROM sqlite_master LIMIT 1")
                return conn
            except sqlite3.Error as exc:
                logger.warning("Cache file %s corrupted (%s), rebuilding...", cache_file, exc)
                try:
                    cache_file.unlink(missing_ok=True)
                except OSError:
                    pass

        # Cache miss: build DB and store to cache_file
        try:
            target_cache_dir.mkdir(parents=True, exist_ok=True)
            tmp_cache = target_cache_dir / f"{b_hash}.tmp.{os.getpid()}_{time.time_ns()}.sqlite"
            build_conn = build_database(self.business_dir, self.calendar_path, db_path=tmp_cache)
            _create_legacy_alias_views(build_conn)
            build_conn.commit()
            build_conn.close()

            # Atomic rename into permanent cache file
            tmp_cache.replace(cache_file)
            return sqlite3.connect(str(cache_file))
        except (OSError, sqlite3.Error) as exc:
            logger.warning("Failed to build cached SQLite file in %s (%s); falling back to :memory:", target_cache_dir, exc)
            mem_conn = build_database(self.business_dir, self.calendar_path, db_path=":memory:")
            _create_legacy_alias_views(mem_conn)
            mem_conn.commit()
            return mem_conn

    @staticmethod
    def _authorizer(action: int, a1: str | None, a2: str | None, db: str | None, trigger: str | None) -> int:
        permitted = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
        return sqlite3.SQLITE_OK if action in permitted else sqlite3.SQLITE_DENY

    def close(self) -> None:
        self.connection.close()

    def schema_text(self, max_chars: int = 13000) -> str:
        if self._legacy:
            return self._legacy_schema_text(max_chars)
        return views_schema_text(self.connection, max_chars=max_chars)

    def execute_readonly(
        self, query: str, time_limit_s: int = 12, max_rows: int = 500
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        sql = query.strip()
        if not re.match(r"^(select|with)\b", sql, re.I):
            raise ValueError("Only SELECT/CTE queries are accepted")

        began = time.monotonic()
        self.connection.set_progress_handler(
            lambda: int(time.monotonic() - began > time_limit_s), 2000
        )
        try:
            cursor = self.connection.execute(sql)
            try:
                columns = [d[0] for d in (cursor.description or [])]
                result = cursor.fetchmany(max_rows + 1)
            finally:
                cursor.close()
            if len(result) > max_rows:
                raise ValueError(
                    f"Query returned more than {max_rows} rows; aggregate or filter results"
                )
            return columns, result
        finally:
            self.connection.set_progress_handler(None, 0)

    # ------------------------------------------------------------------ Legacy ingestion methods
    def _load_legacy(self) -> None:
        self._load_business()
        if self.calendar_path and self.calendar_path.is_file():
            self._load_csv(self.calendar_path, "calendar")

    def _table_name(self, base: str) -> str:
        base = safe_name(base)
        name, n = base, 2
        while name in self.used_names:
            name = f"{base}_{n}"
            n += 1
        self.used_names.add(name)
        return name

    def _add_table(self, wanted_name: str, source: str, headers: list[str], rows: Iterable[tuple[Any, ...]]) -> None:
        if not headers:
            return
        name = self._table_name(wanted_name)
        cols = clean_columns(headers)
        coldefs = ", ".join(f"{sql_ident(col)}" for col in cols)
        self.connection.execute(f"CREATE TABLE {sql_ident(name)} ({coldefs})")
        placeholders = ", ".join(["?"] * len(cols))
        ins = f"INSERT INTO {sql_ident(name)} VALUES ({placeholders})"
        buffer, examples, count = [], [], 0
        sample_values: list[list[Any]] = [[] for _ in cols]
        for row in rows:
            values = list(row)
            values = [cell_value(v) for v in values[:len(cols)]]
            values += [None] * (len(cols) - len(values))
            count += 1
            if len(examples) < 2:
                examples.append(dict(zip(cols, values)))
            if count <= 100:
                for i, v in enumerate(values):
                    sample_values[i].append(v)
            buffer.append(tuple(values))
            if len(buffer) >= 2000:
                self.connection.executemany(ins, buffer)
                buffer.clear()
        if buffer:
            self.connection.executemany(ins, buffer)
        col_types = [_infer_col_type(sv) for sv in sample_values]
        self.tables.append(TableInfo(name, source, cols, col_types, count, examples))

    def _load_csv(self, path: Path, table_name: str | None = None) -> None:
        for encoding in ("utf-8-sig", "utf-8", "cp1258", "latin-1"):
            try:
                with path.open("r", encoding=encoding, newline="") as f:
                    csv.reader(f).__next__()
                break
            except (UnicodeError, StopIteration):
                continue
        else:
            raise ValueError(f"Unable to read CSV {path}")
        with path.open("r", encoding=encoding, newline="") as f:
            reader = csv.reader(f)
            headers = next(reader, [])
            self._add_table(table_name or path.stem, path.name, headers, reader)

    def _load_xlsx(self, path: Path) -> None:
        if load_workbook is None:
            raise RuntimeError("openpyxl is required to read .xlsx files")
        try:
            wb = load_workbook(path, read_only=True, data_only=True)
        except Exception as exc:
            raise RuntimeError(f"Cannot open {path}: {exc}") from exc
        try:
            for sheet in wb.worksheets:
                itr = sheet.iter_rows(values_only=True)
                headers = next(itr, None)
                if headers is not None:
                    self._add_table(
                        f"{path.stem}__{sheet.title}",
                        f"{path.name}/{sheet.title}",
                        list(headers),
                        itr,
                    )
        finally:
            wb.close()

    def _load_sqlite(self, path: Path) -> None:
        uri = path.resolve().as_uri() + "?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True)
        except sqlite3.OperationalError as exc:
            raise RuntimeError(f"Cannot open SQLite {path}: {exc}") from exc
        try:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            for (table,) in tables:
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({sql_ident(table)})")]
                if cols:
                    cursor = conn.execute(f"SELECT * FROM {sql_ident(table)}")
                    self._add_table(f"{path.stem}__{table}", f"{path.name}/{table}", cols, cursor)
        finally:
            conn.close()

    def _load_business(self) -> None:
        for path in sorted(self.business_dir.iterdir()):
            ext = path.suffix.lower()
            try:
                if path.is_file() and ext == ".csv":
                    self._load_csv(path)
                elif path.is_file() and ext == ".xlsx" and not path.name.startswith("~$"):
                    self._load_xlsx(path)
                elif path.is_file() and ext in (".sqlite", ".db", ".sqlite3"):
                    self._load_sqlite(path)
            except Exception as exc:
                logger.warning("Skipping %s: %s", path, exc)

    def _legacy_schema_text(self, max_chars: int = 13000) -> str:
        parts = []
        for info in self.tables:
            col_defs = ", ".join(
                f"{sql_ident(c)} ({t})" for c, t in zip(info.columns, info.col_types)
            )
            snippets = json.dumps(info.examples, ensure_ascii=False, default=str)
            note = "  -- Use CAST(col AS INTEGER/REAL) for NUMERIC columns stored as TEXT in CSV" if any(
                t == "NUMERIC" for t in info.col_types
            ) else ""
            parts.append(
                f"TABLE {sql_ident(info.name)} | rows={info.nrows} | source={info.source}{note}\n"
                f"  COLUMNS: {col_defs}\n"
                f"  SAMPLE: {snippets[:750]}"
            )
        return "\n\n".join(parts)[:max_chars]
