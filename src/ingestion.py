"""Ingest business CSV/XLSX/SQLite files into a temporary read-only SQLite view.

Only source files inside the provided business directory and shared calendar are read.
The normalized schema is assembled at runtime; no business IDs are hardcoded.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None


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
    # Date heuristic: YYYY-MM-DD or DD/MM/YYYY
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$|^\d{1,2}/\d{1,2}/\d{4}$")
    if all(date_re.match(str(v)) for v in non_null):
        return "DATE"
    return "TEXT"


@dataclass
class TableInfo:
    name: str
    source: str
    columns: list[str]
    col_types: list[str]
    nrows: int
    examples: list[dict[str, Any]]


class BusinessDB:
    def __init__(self, business_dir: Path, calendar_path: Path | None = None):
        self.business_dir = business_dir
        if not business_dir.is_dir():
            raise FileNotFoundError(f"Business directory missing: {business_dir}")
        self.connection = sqlite3.connect(":memory:")
        self.tables: list[TableInfo] = []
        self.used_names: set[str] = set()
        self._load_business()
        if calendar_path and calendar_path.is_file():
            self._load_csv(calendar_path, "calendar")
        # SQLite authorizer + query_only prohibit mutations and external attachments.
        self.connection.execute("PRAGMA query_only = ON")
        try:
            self.connection.enable_load_extension(False)
        except AttributeError:
            pass
        self.connection.set_authorizer(self._authorizer)

    @staticmethod
    def _authorizer(action: int, a1: str | None, a2: str | None, db: str | None, trigger: str | None) -> int:
        permitted = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
        return sqlite3.SQLITE_OK if action in permitted else sqlite3.SQLITE_DENY

    def close(self) -> None:
        self.connection.close()

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

    def schema_text(self, max_chars: int = 13000) -> str:
        parts = []
        for info in self.tables:
            # Include type hints so the model knows to CAST text columns.
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

    def execute_readonly(
        self, query: str, time_limit_s: int = 12, max_rows: int = 500
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        sql = query.strip()
        if not re.match(r"^(select|with)\b", sql, re.I):
            raise ValueError("Only SELECT/CTE queries are accepted")
        import time

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
