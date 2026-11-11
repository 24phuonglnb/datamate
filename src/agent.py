"""Prompting, safe SQL execution and typed answer serialization."""
from __future__ import annotations

import datetime
import json
import logging
import math
import re
import time
from pathlib import Path
from typing import Any

from .ingestion import BusinessDB

logger = logging.getLogger(__name__)

VALID_TYPES = {"number", "percent", "string", "date", "boolean", "list", "table", "unanswerable", "abstain"}

SYSTEM = """You are a Vietnamese business data analyst. Answer ONLY using the provided database tables.
Return exactly one compact JSON object, without markdown:
1) Answerable: {"type":"number|string|percent|date|boolean|list|table", "sql":"SELECT ..."}
2) Definitely missing required evidence: {"type":"unanswerable", "reason":"..."}
3) Uncertain / execution cannot be trusted: {"type":"abstain"}
SQLite dialect only; SQL must be read-only (SELECT / WITH SELECT). Quote all identifiers with double quotes.
Use the real business rulebook for definitions (returns, cancellations, taxes, profit, dates).
The calendar table, if present, may be queried for lunar dates. Never assume the current day; use as_of_date.
Do not guess missing facts. If the question is about the highest quantity, use SUM(quantity), not SUM(revenue).
SCALAR TYPES (number, string, percent, date, boolean): SQL must return EXACTLY 1 row and 1 column.
  Ranking queries ("bán chạy nhất", "cao nhất", "nhiều nhất", "ít nhất", "phổ biến nhất"):
    SELECT only the answer column, ORDER BY the aggregate expression, and add LIMIT 1.
    Example: SELECT "ten_sp" FROM "sales" GROUP BY "ten_sp" ORDER BY SUM(CAST("so_luong" AS INTEGER)) DESC LIMIT 1
    Do NOT include the aggregation column in SELECT — that creates a 2-column result which will fail.
For list, return one column and multiple rows.
For table, return rows with named columns. Do not emit SQL that changes tables or reads external files.
Never claim that an empty SQL result is necessarily unanswerable; differentiate true zero from missing observations.
All CSV columns are stored as SQLite TEXT; use CAST(col AS INTEGER) or CAST(col AS REAL) for numeric operations.
"""

# Vietnamese informal date patterns → ISO 8601 conversion.
# Used to normalize hints in the question before including them in the prompt.
_DATE_HINT_RE = re.compile(
    r"""
    (?:ngày\s*)?(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{4}))?   # 3/3  or 15/01/2026
    |tháng\s*(\d{1,2})(?:\s*năm\s*(\d{4}))?                  # tháng 2 năm 2026
    """,
    re.VERBOSE | re.IGNORECASE,
)

_DEFAULT_YEAR = 2026


def normalize_date_hints(text: str, as_of_date: str) -> str:
    """Add a parenthetical ISO date after informal Vietnamese date references."""
    year = int(as_of_date[:4]) if as_of_date and len(as_of_date) >= 4 else _DEFAULT_YEAR

    def _replace(m: re.Match) -> str:
        d, mo, yr, month_only, yr2 = m.groups()
        if month_only:
            y = int(yr2) if yr2 else year
            return f"{m.group(0)} (tháng {month_only}/{y})"
        day, mon = int(d), int(mo)
        y = int(yr) if yr else year
        try:
            datetime.date(y, mon, day)
        except ValueError:
            return m.group(0)
        iso = f"{y:04d}-{mon:02d}-{day:02d}"
        return f"{m.group(0)} ({iso})"

    return _DATE_HINT_RE.sub(_replace, text)


def json_object(text: str) -> dict[str, Any]:
    """Extract the first JSON object from model output.

    Handles thinking tags, code fences, and partial wrapping.
    Raises ValueError when no valid dict can be found.
    """
    # Strip thinking tags (Qwen3 reasoning mode).
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    # Strip markdown fences.
    text = re.sub(r"^```[a-z]*\n?", "", text, flags=re.M).strip()
    text = text.rstrip("`").strip()

    # Fast path: entire string is JSON.
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (ValueError, TypeError):
        pass

    # Scan for the first '{' and use JSONDecoder for partial parse.
    start = text.find("{")
    if start < 0:
        raise ValueError(f"No JSON object found in model output: {text[:200]!r}")
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON decode error: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError("Model produced non-object JSON")
    return obj


def scalar(v: Any) -> Any:
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        raise ValueError("Non-finite numeric result")
    if isinstance(v, (bool, int, float, str)) or v is None:
        return v
    return str(v)


def typed_result(typ: str, columns: list[str], rows: list[tuple[Any, ...]]) -> Any:
    if typ == "table":
        return [{c: scalar(v) for c, v in zip(columns, row)} for row in rows]
    if typ == "list":
        if len(columns) != 1:
            raise ValueError("List query must return exactly one column")
        return [scalar(row[0]) for row in rows]
    if len(columns) != 1 or len(rows) != 1:
        raise ValueError(
            f"Scalar query must return exactly 1 row and 1 column; got {len(rows)} rows, {len(columns)} cols"
        )
    v = rows[0][0]
    if v is None:
        raise ValueError("No non-null scalar value")
    if typ in {"number", "percent"}:
        if isinstance(v, str):
            v = float(v.replace(",", "").strip())
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"Expected numeric SQL result, got {type(v).__name__}: {v!r}")
        return scalar(v)
    if typ in {"string", "date"}:
        return str(v)
    if typ == "boolean":
        if isinstance(v, bool):
            return v
        if v in (0, 1):
            return bool(v)
        if isinstance(v, str) and v.lower() in ("true", "1"):
            return True
        if isinstance(v, str) and v.lower() in ("false", "0"):
            return False
        raise ValueError(f"Expected boolean / 0 / 1 result, got {v!r}")
    raise ValueError(f"Unsupported response type {typ!r}")


class Agent:
    def __init__(self, model: Any, root: Path, max_attempts: int = 2):
        self.model = model
        self.root = root
        self.max_attempts = max_attempts
        self.db_cache: dict[str, BusinessDB] = {}
        self.rulebook = self._read_text(root / "rulebook.md", 14000)
        self.calendar_path = root / "calendar.csv"

    @staticmethod
    def _read_text(path: Path, size: int = 8000) -> str:
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8", errors="replace")[:size]
        except OSError as exc:
            logger.warning("Cannot read %s: %s", path, exc)
            return ""

    def close(self) -> None:
        for db in self.db_cache.values():
            db.close()
        self.db_cache.clear()

    def _db(self, business_id: str) -> BusinessDB:
        # Prevent directory traversal; only paths directly under /data/data are accepted.
        base = (self.root / "data").resolve()
        target = (base / str(business_id)).resolve()
        if target.parent != base:
            raise ValueError(f"Invalid business_id: {business_id!r}")
        if business_id not in self.db_cache:
            # Keep at most 2 open DBs to avoid memory accumulation with large workbooks.
            if len(self.db_cache) >= 2:
                first = next(iter(self.db_cache))
                self.db_cache.pop(first).close()
            self.db_cache[business_id] = BusinessDB(
                target,
                self.calendar_path if self.calendar_path.is_file() else None,
            )
        return self.db_cache[business_id]

    def solve(self, question: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        began = time.monotonic()
        qid = str(question.get("id", ""))
        log: dict[str, Any] = {
            "id": qid, "answer": None, "elapsed_ms": 0,
            "thinking": None, "code": None, "output": None,
        }
        answer: dict[str, Any] = {"id": qid, "type": "abstain"}
        reasoning: list[str] = []
        executions: list[dict[str, Any]] = []
        try:
            biz = str(question["business_id"])
            db = self._db(biz)
            description = self._read_text(self.root / "data" / biz / "README.md")
            as_of = str(question.get("as_of_date", ""))
            raw_question = str(question.get("question", ""))
            # Annotate informal Vietnamese date references to help the model.
            annotated_question = normalize_date_hints(raw_question, as_of)

            prompt = (
                f"BUSINESS README:\n{description}\n\n"
                f"RULEBOOK:\n{self.rulebook}\n\n"
                f"DATABASE SCHEMA AND SAMPLE ROWS:\n{db.schema_text()}\n\n"
                f"AS_OF_DATE: {as_of}\n"
                f"QUESTION: {annotated_question}"
            )
            error: str | None = None
            last_failed_sql: str | None = None
            for attempt in range(self.max_attempts):
                user = prompt
                if error:
                    user += (
                        f"\n\nPREVIOUS SQL ATTEMPT FAILED (attempt {attempt}/{self.max_attempts}): "
                        f"{error}. Rewrite the SQL or return abstain."
                    )
                raw, think = self.model.generate(SYSTEM, user)
                if think is not None:
                    reasoning.append(think)

                try:
                    parsed = json_object(raw)
                except ValueError as exc:
                    error = f"JSON parse error: {exc}"
                    logger.debug("q=%s attempt=%d json_error=%s", qid, attempt, exc)
                    continue

                typ = str(parsed.get("type", "")).lower()
                if typ not in VALID_TYPES:
                    error = f"Invalid answer type {typ!r}"
                    continue

                if typ in ("unanswerable", "abstain"):
                    answer = {"id": qid, "type": typ}
                    if typ == "unanswerable" and parsed.get("reason"):
                        answer["reason"] = str(parsed["reason"])[:400]
                    break

                sql = str(parsed.get("sql", "")).strip()
                if not sql:
                    error = "Empty SQL in model response"
                    continue

                # Duplicate SQL detection: if the model re-generates the same failing SQL,
                # a retry would produce the same error — abstain immediately.
                if sql == last_failed_sql:
                    logger.debug("q=%s attempt=%d duplicate_sql — abstaining immediately", qid, attempt)
                    break

                try:
                    cols, rows = db.execute_readonly(sql)
                    executions.append({"code": sql, "output": rows})
                    result = typed_result(typ, cols, rows)
                    answer = {"id": qid, "type": typ, "answer": result}
                    break
                except Exception as exc:
                    last_failed_sql = sql
                    exc_str = str(exc)[:400]
                    if "Scalar query must return exactly" in exc_str:
                        exc_str += (
                            " — Add LIMIT 1 and SELECT only the answer column "
                            "(not the aggregation expression used for ORDER BY)."
                        )
                    exc_msg = f"{type(exc).__name__}: {exc_str}"
                    executions.append({"code": sql, "error": exc_msg})
                    error = exc_msg
                    logger.debug("q=%s attempt=%d sql_error=%s", qid, attempt, exc_msg)

            # Exhausted all attempts without a valid answer → abstain.

        except Exception as exc:
            log["error"] = f"{type(exc).__name__}: {str(exc)[:600]}"
            logger.exception("Unhandled error in agent.solve for q=%s", qid)
        finally:
            log["elapsed_ms"] = max(0, int((time.monotonic() - began) * 1000))
            log["answer"] = answer
            log["thinking"] = (
                (reasoning[0] if len(reasoning) == 1 else reasoning) if reasoning else None
            )
            if executions:
                if len(executions) > 1:
                    log["code"] = [r["code"] for r in executions]
                    log["output"] = [r.get("output", r.get("error")) for r in executions]
                else:
                    log["code"] = executions[0]["code"]
                    log["output"] = executions[0].get("output", executions[0].get("error"))

        return answer, log
