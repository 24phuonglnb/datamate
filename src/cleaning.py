"""Shop-agnostic loading and cell-level cleaning of raw business files.

This module is deliberately independent from the answering strategy (text-to-SQL,
plan DSL, code generation): it only turns messy CSV / XLSX / SQLite exports into
tidy pandas DataFrames plus a compact profile.  Nothing here is keyed on business
or question ids; every decision is derived from the cell contents.

Public API
----------
parse_number(v)            -> float | None      "560,000" "25.000đ" "25k" "1tr440" "16,56tr"
parse_qty(v)               -> (float|None, unit|None)   "2 thùng" -> (2.0, "thùng")
parse_date(v, year=None)   -> datetime.date | None   "1 thg 6 2025", 45689, "1/1" (+year)
parse_datetime(v, year)    -> datetime.datetime | None
norm_key(s)                -> accent-free lowercase key for fuzzy matching of names
load_business(dir)         -> list[RawTable]   (sheets / split files with one layout merged)
infer_kinds(df)            -> {column: ColumnKind}
fill_order_level(df, key)  -> df    rulebook §8 "ô để trống ở các dòng sau của cùng một nhóm dòng"
drop_export_duplicates(df, key) -> df   rulebook §8 "hai dòng của cùng một đơn giống nhau ở mọi ô"
split_summary_rows(df)     -> (data, removed)   hand-written "Tổng tháng" / "Ghi chú:" rows
profile_text(tables)       -> str   prompt-ready description of every table
"""
from __future__ import annotations

import csv
import datetime as dt
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

try:  # optional at import time so CSV/SQLite-only use keeps working
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover
    load_workbook = None

# --------------------------------------------------------------------------- text

def nfc(s: Any) -> str:
    return unicodedata.normalize("NFC", str(s))


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def norm_key(s: Any) -> str:
    """Accent-free, lowercase, punctuation-free key (for matching, never for output)."""
    t = strip_accents(nfc(s)).lower()
    t = re.sub(r"[^0-9a-z]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and v != v:
        return True
    return isinstance(v, str) and not v.strip()


# ------------------------------------------------------------------------- numbers

_NUM_SUFFIX = re.compile(r"^(-?)\s*(\d+(?:[.,]\d+)?)\s*(tr|trieu|triệu|k|nghìn|ngàn|m)\s*(\d{1,3})?$", re.I)
_GROUPED = re.compile(r"^-?\d{1,3}(?:([.,  ])\d{3})(?:\1\d{3})*(?:[.,]\d+)?$")
_PLAIN = re.compile(r"^-?\d+(?:[.,]\d+)?$")
_CURRENCY = re.compile(r"(vnđ|vnd|đồng|dong|₫|đ|d)$", re.I)
_CURRENCY_PRE = re.compile(r"^(vnđ|vnd|đồng|dong|₫|đ|d)\s*", re.I)


def parse_number(v: Any) -> float | None:
    """Parse the number spellings seen in shop files. Returns None when not a number.

    "560,000" "25.000đ" "129 000" "45,000.0000" -> thousands groups
    "25k" "3950k" -> x1e3 ; "1,84tr" "4,544tr" -> x1e6 (comma/dot is decimal) ; "1tr440" -> 1_440_000
    """
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return None if v != v else float(v)
    s = nfc(v).strip().lower()
    if not s:
        return None
    s = s.replace("−", "-")
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1].strip()
    if s.startswith("+"):
        s = s[1:].strip()
    m = _NUM_SUFFIX.match(s)
    if m:
        sign, body, suf, tail = m.groups()
        mult = 1e6 if suf[0] in "tm" else 1e3
        val = float(body.replace(",", ".")) * mult
        if tail:  # "1tr440" -> 1_440_000 ; "2tr5" -> 2_500_000
            val += float(tail) * mult / (10 ** len(tail))
        val = round(val)
        return -val if (sign or neg) else val
    s = _CURRENCY.sub("", s).strip()
    s = _CURRENCY_PRE.sub("", s).strip()
    if not s:
        return None
    if _GROUPED.match(s):
        sep = re.search(r"\d([.,  ])\d{3}", s).group(1)
        head, dec = s, ""
        # a trailing decimal part uses the *other* separator: 45,000.0000 / 45.000,50
        m2 = re.match(r"^(.*\d{3})([.,])(\d+)$", s)
        if m2 and m2.group(2) != sep and sep in m2.group(1):
            head, dec = m2.group(1), m2.group(3)
        val = float(re.sub(r"[.,  ]", "", head) + ("." + dec if dec else ""))
        return -abs(val) if neg else val
    if _PLAIN.match(s):
        val = float(s.replace(",", "."))
        return -abs(val) if neg else val
    return None


_QTY = re.compile(r"^(-?\d+(?:[.,]\d+)?)\s+(\D.*)$")


def parse_qty(v: Any) -> tuple[float | None, str | None]:
    """"2 thùng" -> (2.0, "thùng"); "1 bao 25kg" -> (1.0, "bao 25kg"); 3 -> (3.0, None)."""
    n = parse_number(v)
    if n is not None:
        return n, None
    if isinstance(v, str):
        m = _QTY.match(nfc(v).strip())
        if m:
            return float(m.group(1).replace(",", ".")), m.group(2).strip()
    return None, None


# --------------------------------------------------------------------------- dates

_EXCEL_EPOCH = dt.datetime(1899, 12, 30)
_ISO = re.compile(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?")
_DMY = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$")
_THG = re.compile(r"^(?:ngày\s+)?(\d{1,2})\s*(?:thg|tháng|thang|th)\.?\s*(\d{1,2})(?:\s*(?:,|năm|nam)?\s*(\d{2,4}))?$", re.I)


def _year(y: str | None, default: int | None) -> int | None:
    if y is None:
        return default
    yi = int(y)
    return yi + 2000 if yi < 100 else yi


def parse_datetime(v: Any, year: int | None = None) -> dt.datetime | None:
    """Parse a date/datetime cell. `year` is the fallback for year-less dates ("1/1"),
    normally the year of the sheet that holds the row (rulebook §8)."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, dt.datetime):
        return v
    if isinstance(v, dt.date):
        return dt.datetime(v.year, v.month, v.day)
    if isinstance(v, (int, float)):
        if v != v or not (20000 <= v <= 80000):  # Excel serials for 1954..2119
            return None
        return _EXCEL_EPOCH + dt.timedelta(days=float(v))
    s = nfc(v).strip()
    if not s:
        return None
    if re.fullmatch(r"\d{5}(\.\d+)?", s):
        return parse_datetime(float(s))
    try:
        m = _ISO.match(s)
        if m:
            y, mo, d, h, mi, se = m.groups()
            return dt.datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(se or 0))
        m = _DMY.match(s)
        if m:
            d, mo, y, h, mi, se = m.groups()
            yy = _year(y, year)
            if yy is None:
                return None
            return dt.datetime(yy, int(mo), int(d), int(h or 0), int(mi or 0), int(se or 0))
        m = _THG.match(s)
        if m:
            d, mo, y = m.groups()
            yy = _year(y, year)
            if yy is None:
                return None
            return dt.datetime(yy, int(mo), int(d))
    except ValueError:
        return None
    return None


def parse_date(v: Any, year: int | None = None) -> dt.date | None:
    r = parse_datetime(v, year)
    return r.date() if r else None


def looks_yearless_date(v: Any) -> bool:
    return isinstance(v, str) and bool(re.fullmatch(r"\s*\d{1,2}[/\-.]\d{1,2}\s*", v) or
                                       re.fullmatch(r"\s*\d{1,2}\s*(?:thg|tháng|thang)\.?\s*\d{1,2}\s*", v, re.I))


_PERIOD_HINT = re.compile(r"(?<!\d)(?:t|th|thang|tháng)?[\s_.\-]*(\d{1,2})[\s_.\-/]+(20\d{2})(?!\d)", re.I)
_PERIOD_HINT_REV = re.compile(r"(?<!\d)(20\d{2})[\s_.\-/]+(?:t|th|thang|tháng)?[\s_.\-]*(\d{1,2})(?!\d)", re.I)
_YEAR_HINT = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
_MONTH_ONLY = re.compile(r"(?<!\w)(?:t|th|thang|tháng)[\s_.\-]*(\d{1,2})(?!\d)", re.I)


def period_hint(*labels: str | None) -> tuple[int | None, int | None]:
    """(year, month) carried by a sheet or file name such as "Tháng 01-2025", "T7-2025",
    "04.2025", "BanHang_T1_2025", "SoBanHang_2026". First label that matches wins."""
    for lab in labels:
        if not lab:
            continue
        t = strip_accents(nfc(lab))
        m = _PERIOD_HINT.search(t)
        if m and 1 <= int(m.group(1)) <= 12:
            return int(m.group(2)), int(m.group(1))
        m = _PERIOD_HINT_REV.search(t)
        if m and 1 <= int(m.group(2)) <= 12:
            return int(m.group(1)), int(m.group(2))
    # cross-label combination: e.g. sheet='Thang 1', file='SoBanHang_2026'
    y, mo = None, None
    for lab in labels:
        if not lab:
            continue
        t = strip_accents(nfc(lab))
        if y is None:
            my = _YEAR_HINT.search(t)
            if my:
                y = int(my.group(1))
        if mo is None:
            mm = _MONTH_ONLY.search(t)
            if mm and 1 <= int(mm.group(1)) <= 12:
                mo = int(mm.group(1))
    if y is not None:
        return y, mo
    return None, None


# ------------------------------------------------------------------ header detection

def _n_filled(row: Iterable[Any]) -> int:
    return sum(0 if is_blank(c) else 1 for c in row)


def _header_like(row: list[Any]) -> bool:
    cells = [c for c in row if not is_blank(c)]
    if not cells:
        return False
    for c in cells:
        if not isinstance(c, str):
            return False
        if parse_number(c) is not None or parse_datetime(c, 2000) is not None:
            return False
    return True


def find_header(rows: list[list[Any]]) -> int:
    """Index of the real header row in the first rows of a sheet.

    Skips report titles ("SỔ CHI TIẾT BÁN HÀNG", "Kỳ báo cáo: ..."), blank rows and the
    group-header row of two-level headers (['Hàng', None, None, 'Tiền', ...]). The header
    is the first text-only row filled to (almost) the full table width."""
    if not rows:
        return 0
    probe = rows[:40]
    width = max((_n_filled(r) for r in probe), default=0)
    if width == 0:
        return 0
    need = max(2, int(0.7 * width + 0.999)) if width >= 3 else width
    for i, r in enumerate(probe):
        if _n_filled(r) >= need and _header_like(r):
            return i
    return 0


def _clean_header(header: list[Any]) -> list[str]:
    out, used = [], set()
    for i, h in enumerate(header):
        base = re.sub(r"\s+", " ", nfc(h)).strip() if not is_blank(h) else f"col_{i + 1}"
        name, k = base, 2
        while name.lower() in used:
            name, k = f"{base}_{k}", k + 1
        used.add(name.lower())
        out.append(name)
    return out


# ---------------------------------------------------------------------------- tables

META_COLS = ("__file", "__sheet", "__row", "__year", "__month")


@dataclass
class RawTable:
    """One logical table. Sheets / numbered files sharing a layout are concatenated;
    the origin of each row is kept in the META_COLS columns."""
    name: str
    df: pd.DataFrame
    sources: list[str] = field(default_factory=list)   # "file.xlsx[sheet]" in load order
    preamble: list[str] = field(default_factory=list)  # title lines found above the header

    @property
    def columns(self) -> list[str]:
        return [c for c in self.df.columns if c not in META_COLS]


def _frame(header: list[Any], body: list[list[Any]], file: str, sheet: str | None, first_row: int) -> pd.DataFrame:
    cols = _clean_header(header)
    w = len(cols)
    data = [list(r[:w]) + [None] * (w - len(r)) for r in body]
    df = pd.DataFrame(data, columns=cols, dtype=object)
    df = df.where(~df.map(is_blank), None)
    keep = df.notna().any(axis=1)
    df["__row"] = range(first_row, first_row + len(df))
    df = df[keep.values].reset_index(drop=True)
    y, m = period_hint(sheet, Path(file).stem)
    df["__file"], df["__sheet"], df["__year"], df["__month"] = file, sheet, y, m
    return df


def _trim(rows: list[list[Any]]) -> list[list[Any]]:
    out = []
    for r in rows:
        r = list(r)
        while r and is_blank(r[-1]):
            r.pop()
        out.append(r)
    return out


def _is_repeated_header(row: Iterable[Any], header: list[Any]) -> bool:
    r_cells = [norm_key(c) for c in row if not is_blank(c)]
    h_cells = [norm_key(c) for c in header if not is_blank(c)]
    return len(r_cells) >= 2 and r_cells == h_cells


def _from_grid(rows: list[list[Any]], file: str, sheet: str | None) -> tuple[pd.DataFrame, list[str]] | None:
    rows = _trim(rows)
    if not any(rows):
        return None
    h = find_header(rows)
    header = rows[h]
    width = max(len(header), max((len(r) for r in rows[h + 1:h + 200]), default=0))
    header = header + [None] * (width - len(header))
    pre = [" | ".join(nfc(c) for c in r if not is_blank(c)) for r in rows[:h] if _n_filled(r)]
    body = [r for r in rows[h + 1:] if not _is_repeated_header(r, header)]
    return _frame(header, body, file, sheet, h + 2), pre


def _read_csv(path: Path) -> list[list[Any]]:
    for enc in ("utf-8-sig", "utf-8", "cp1258", "latin-1"):
        try:
            with path.open("r", encoding=enc, newline="") as f:
                sample = f.read(8192)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                except csv.Error:
                    dialect = csv.excel
                return [list(r) for r in csv.reader(f, dialect)]
        except UnicodeError:
            continue
    raise ValueError(f"Unable to decode {path}")


def _layout_key(df: pd.DataFrame) -> tuple[str, ...]:
    return tuple(sorted(norm_key(c) for c in df.columns if c not in META_COLS))


_SPLIT_SUFFIX = re.compile(
    r"(?:[_\-\s]+(?:20\d{2}[_\-\s.]+)?(?:(?:t|th|thang|tháng)[_\-\s]*)?\d{1,2})?(?:[_\-\s.]+20\d{2})?$", re.I)


def _family(stem: str) -> str:
    """"SoBanHang_1"/"SoBanHang_2026"/"BanHang_T1_2025" -> shared family name."""
    base = _SPLIT_SUFFIX.sub("", stem)
    return base or stem


def load_business(business_dir: str | Path) -> list[RawTable]:
    """Load every data file of one business. Sheets of a workbook, and numbered /
    dated sibling files, are merged into one RawTable when their column sets are equal."""
    business_dir = Path(business_dir)
    parts: list[tuple[str, str, pd.DataFrame, list[str]]] = []  # (table name, source, df, preamble)
    for path in sorted(business_dir.iterdir()):
        ext = path.suffix.lower()
        if not path.is_file() or path.name.startswith("~$"):
            continue
        if ext == ".csv":
            got = _from_grid(_read_csv(path), path.name, None)
            if got:
                parts.append((path.stem, path.name, got[0], got[1]))
        elif ext in (".xlsx", ".xlsm"):
            if load_workbook is None:
                raise RuntimeError("openpyxl is required to read .xlsx files")
            wb = load_workbook(path, read_only=True, data_only=True)
            try:
                sheets = wb.worksheets
                for ws in sheets:
                    got = _from_grid([list(r) for r in ws.iter_rows(values_only=True)], path.name, ws.title)
                    if got:
                        nm = path.stem if len(sheets) == 1 else f"{path.stem}/{ws.title}"
                        parts.append((nm, f"{path.name}[{ws.title}]", got[0], got[1]))
            finally:
                wb.close()
        elif ext in (".sqlite", ".db", ".sqlite3"):
            conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
            try:
                names = [r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
                for t in names:
                    cur = conn.execute('SELECT * FROM "%s"' % t.replace('"', '""'))
                    header = [d[0] for d in cur.description]
                    parts.append((t, f"{path.name}:{t}", _frame(header, [list(r) for r in cur], path.name, t, 1), []))
            finally:
                conn.close()

    # merge parts that share a layout inside one file family (sheets per month, _1/_2 files)
    merged: dict[tuple, RawTable] = {}
    order: list[tuple] = []
    for name, source, df, pre in parts:
        file = str(df["__file"].iloc[0]) if len(df) else source.split("[")[0].split(":")[0]
        is_sqlite = ":" in source and not source.endswith("]")
        fam = name if is_sqlite else _family(Path(file).stem)
        key = (fam, _layout_key(df))
        if key not in merged:
            merged[key] = RawTable(name=name, df=df, sources=[source], preamble=pre)
            order.append(key)
        else:
            t = merged[key]
            # same column *set*; align by normalised name so shuffled columns still stack
            ren = {norm_key(c): c for c in t.df.columns if c not in META_COLS}
            df = df.rename(columns={c: ren[norm_key(c)] for c in df.columns if c not in META_COLS})
            t.df = pd.concat([t.df, df], ignore_index=True)
            t.sources.append(source)
            t.name = fam
    out = [merged[k] for k in order]
    seen: dict[str, int] = {}
    for t in out:  # unique names
        seen[t.name] = seen.get(t.name, 0) + 1
        if seen[t.name] > 1:
            t.name = f"{t.name}#{seen[t.name]}"
    return out


# ------------------------------------------------------------------- column profiling

@dataclass
class ColumnKind:
    kind: str            # empty | number | qty | date | datetime | code | bool | category | text
    fill: float          # share of non-blank cells
    nunique: int
    examples: list[str]
    lo: Any = None
    hi: Any = None
    yearless: float = 0.0   # share of date cells without a year
    units: list[str] = field(default_factory=list)  # units embedded in qty cells


_CODE = re.compile(r"^[A-Za-z]{1,5}[-_]?\d{2,}$")
_BOOL = {"true", "false", "0", "1", "có", "không", "co", "khong", "x", "yes", "no"}


def infer_kinds(df: pd.DataFrame, sample: int = 3000) -> dict[str, ColumnKind]:
    out: dict[str, ColumnKind] = {}
    n = len(df)
    for c in df.columns:
        if c in META_COLS:
            continue
        col = df[c]
        vals = col.dropna()
        if len(vals) == 0:
            out[c] = ColumnKind("empty", 0.0, 0, [])
            continue
        s = vals if len(vals) <= sample else vals.sample(sample, random_state=0)
        k = len(s)
        nums = [parse_number(v) for v in s]
        dts = [parse_datetime(v, 2000) for v in s]
        strs = [v for v in s if isinstance(v, str)]
        p_num = sum(x is not None for x in nums) / k
        p_dt = sum(x is not None and not isinstance(v, (int, float)) for x, v in zip(dts, s)) / k
        p_serial = sum(isinstance(v, (int, float)) and 40000 <= v <= 60000 for v in s) / k
        qty = [parse_qty(v) for v in s]
        p_qty = sum(q[0] is not None for q in qty) / k
        units = sorted({q[1] for q in qty if q[1]})
        uniq = vals.astype(str).nunique()
        ex = [str(v)[:40] for v in vals.astype(str).drop_duplicates().head(5)]
        kind = "text"
        info: dict[str, Any] = {}
        if p_dt + p_serial >= 0.98 and p_dt >= 0.3:
            has_time = sum(1 for x in dts if x is not None and (x.hour or x.minute or x.second)) / k
            kind = "datetime" if has_time > 0.2 else "date"
            real = [x for x, v in zip(dts, s) if x is not None and not looks_yearless_date(v)]
            if real:
                info["lo"], info["hi"] = min(real).isoformat(sep=" "), max(real).isoformat(sep=" ")
            info["yearless"] = sum(looks_yearless_date(v) for v in s) / k
        elif strs and len(strs) == k and {x.strip().lower() for x in strs} <= _BOOL and uniq <= 3:
            kind = "bool"
        elif p_num >= 0.98:
            kind = "number"
            good = [x for x in nums if x is not None]
            info["lo"], info["hi"] = min(good), max(good)
        elif p_qty >= 0.98 and units:
            kind = "qty"
            info["units"] = units[:12]
        elif strs and sum(bool(_CODE.match(x.strip())) for x in strs) / k >= 0.95:
            kind = "code"
        elif uniq <= max(12, int(0.002 * n)):
            kind = "category"
        out[c] = ColumnKind(kind, len(vals) / n if n else 0.0, int(uniq), ex, **info)
    return out


# ------------------------------------------------------- order-level repairs (§8)

def fill_order_level(df: pd.DataFrame, key: str, min_consistency: float = 0.995) -> pd.DataFrame:
    """Rulebook §8: blank cells on the later rows of one order repeat the first row.

    1. A blank order key continues the order above it (forward fill, inside one sheet).
    2. A column that is constant inside (almost) every order is an order-level column;
       its blanks take the value of the order's FIRST row. If the first row is blank the
       blank is real (e.g. walk-in customer) and stays blank.
    Line-level columns are never touched."""
    df = df.copy()
    grp_cols = [c for c in ("__file", "__sheet") if c in df.columns]
    if grp_cols:
        df[key] = df.groupby(grp_cols, sort=False, dropna=False)[key].ffill()
    else:
        df[key] = df[key].ffill()
    g = df.groupby(key, sort=False, dropna=True)
    sizes = g[key].transform("size")
    multi = sizes > 1
    if not multi.any():
        return df
    first_idx = g.head(1).set_index(key)
    for c in df.columns:
        if c == key or c in META_COLS:
            continue
        col = df[c]
        if not col[multi].isna().any():
            continue
        nun = g[c].nunique(dropna=True)
        if (nun <= 1).mean() < min_consistency:
            continue  # line-level column
        first = df[key].map(first_idx[c]) if first_idx.index.is_unique else None
        if first is None:
            continue
        df[c] = col.where(col.notna(), first)
    return df


def drop_export_duplicates(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """Rulebook §8: two rows of the SAME order equal in every cell are an export glitch."""
    cols = [c for c in df.columns if c not in META_COLS]
    has_key = df[key].notna()
    dup = df.loc[has_key].astype({c: str for c in cols}).duplicated(subset=cols, keep="first")
    return df.drop(index=dup[dup].index).reset_index(drop=True)


_SUMMARY = re.compile(r"^(tong|cong|tong cong|tong ket|total|subtotal|ghi chu|note|luu y|chu y|nguoi lap|ky ten)\b")


def split_summary_rows(df: pd.DataFrame, max_filled: int = 2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separate hand-written subtotal / footnote rows ("Tổng tháng | 901.896.400đ",
    "Tổng ngày 01/03", "Ghi chú: số liệu ghi tay") from data rows.

    A row is a summary row when it has at most `max_filled` filled cells (in a table of
    5+ columns) and one of them is a label starting with tổng / cộng / ghi chú / total...
    Returns (data_rows, removed_rows); summing a money column without this double counts."""
    cols = [c for c in df.columns if c not in META_COLS]
    if len(cols) < 5 or df.empty:
        return df, df.iloc[0:0]
    sparse = df[cols].notna().sum(axis=1) <= max_filled
    if not sparse.any():
        return df, df.iloc[0:0]
    cand = df.loc[sparse, cols]
    hit = cand.apply(lambda r: any(isinstance(v, str) and _SUMMARY.match(norm_key(v)) for v in r), axis=1)
    idx = hit[hit].index
    return df.drop(index=idx).reset_index(drop=True), df.loc[idx]


# ----------------------------------------------------------------------- prompt text

def profile_text(tables: list[RawTable], max_examples: int = 4) -> str:
    """Compact, prompt-ready description: one line per column with kind, fill, range, examples."""
    lines: list[str] = []
    for t in tables:
        src = t.sources[0] if len(t.sources) == 1 else f"{t.sources[0]} … {t.sources[-1]} ({len(t.sources)} phần)"
        lines.append(f"TABLE {t.name} | rows={len(t.df)} | source={src}")
        for p in t.preamble[:3]:
            lines.append(f"  title: {p[:120]}")
        for c, k in infer_kinds(t.df).items():
            extra = ""
            if k.lo is not None:
                extra += f" range=[{k.lo} .. {k.hi}]"
            if k.yearless:
                extra += f" yearless={k.yearless:.0%}"
            if k.units:
                extra += f" units={k.units}"
            ex = "; ".join(k.examples[:max_examples])
            lines.append(f"  - {c!r}: {k.kind} fill={k.fill:.0%} uniq={k.nunique}{extra} | {ex}")
        lines.append("")
    return "\n".join(lines)
