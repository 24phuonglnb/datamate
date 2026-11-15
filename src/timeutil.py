"""Resolve Vietnamese time expressions into concrete periods (rulebook section 2).

    resolve("doanh thu thang nay so voi thang truoc", "2026-09-07", calendar=cal)
        -> ResolveResult(periods=[month_to_date 2026-09-01..2026-09-07],
                         comparison=2026-08-01..2026-08-07, ...)

Design
- Works on accent-folded lower-case text, so it handles diacritic-less and
  teencode-ish input as well as clean text.
- Pure rules, no model.  Every Period carries `rule_refs` (rulebook section 2 rows).
- Nothing is guessed: an expression whose meaning the rulebook does not fix is
  reported in `ResolveResult.ambiguous` and produces no Period.
- No business_id / question_id logic.
"""
from __future__ import annotations

import calendar as _cal
import csv
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# ---- rulebook section 2 row names (used in rule_refs) -------------------
R_DAY = "§2 Ngày X, hôm nay, hôm qua"
R_CUM = "§2 Đến hết ngày X, tính đến hôm nay"
R_RANGE = "§2 Từ X đến Y"
R_LAST_N = "§2 N ngày gần nhất"
R_WEEK = "§2 Tuần"
R_MONTH = "§2 Tháng M/Y"
R_MTD = "§2 Tháng này"
R_YTD = "§2 Từ đầu năm"
R_NOYEAR = "§2 Tháng M, quý Q không ghi năm"
R_TET = "§2 Tết năm Y"
R_SHIFT = "§2 Ca sáng, ca chiều"
R_PREV = "§1 Phần trăm thay đổi: so với kỳ trước"
R_PRICE = "§5 Hiệu ứng tăng giá"

_TODAY = r"(?:hom nay|hnay|bua nay|hum nay)"
_MONTH = r"(?:thangs?|th)"


def fold(text: str) -> str:
    """Lower-case, strip Vietnamese diacritics (đ -> d), NFC-insensitive."""
    t = unicodedata.normalize("NFD", text.lower().replace("đ", "d").replace("Đ", "d"))
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


# ---- data classes --------------------------------------------------------
@dataclass(frozen=True)
class Period:
    start: date | None  # None = from the beginning of the data (cumulative)
    end: date
    granularity: str
    rule_refs: tuple[str, ...]
    source: str = ""

    def days(self) -> int | None:
        return None if self.start is None else (self.end - self.start).days + 1

    def where_sql(self, date_col: str = "order_date", time_col: str = "order_time",
                  part_of_day: tuple[str, str] | None = None) -> str:
        """SQL filter for this period on ISO-date column *date_col* (literals; dates are trusted values).

        start None (cumulative, "đến hết ngày X") -> only an upper bound. part_of_day = (from, to) 'HH:MM'
        adds a filter on *time_col* (ca sáng 06:00-13:59, ca chiều 14:00-21:59, rulebook section 2).
        """
        if self.start is None:
            clause = f"{date_col} <= '{self.end.isoformat()}'"
        else:
            clause = f"{date_col} BETWEEN '{self.start.isoformat()}' AND '{self.end.isoformat()}'"
        if part_of_day:
            clause += f" AND substr({time_col}, 1, 5) BETWEEN '{part_of_day[0]}' AND '{part_of_day[1]}'"
        return clause

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start.isoformat() if self.start else None, "end": self.end.isoformat(),
                "granularity": self.granularity, "rule_refs": list(self.rule_refs), "source": self.source}


@dataclass
class ResolveResult:
    periods: list[Period] = field(default_factory=list)
    comparison: Period | None = None
    part_of_day: dict[str, Any] | None = None
    ambiguous: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"periods": [p.to_dict() for p in self.periods],
                "comparison": self.comparison.to_dict() if self.comparison else None,
                "part_of_day": self.part_of_day, "ambiguous": self.ambiguous}


class LunarCalendar:
    """Lookup over the provided calendar.csv (solar <-> lunar)."""

    def __init__(self, path: str | Path):
        self._solar: dict[tuple[int, int, int, bool], date] = {}
        try:
            with open(path, encoding="utf-8", newline="") as f:
                for r in csv.DictReader(f):
                    key = (int(r["lunar_year"]), int(r["lunar_month"]), int(r["lunar_day"]),
                           str(r["lunar_leap"]).strip().lower() == "true")
                    self._solar.setdefault(key, date.fromisoformat(r["date"]))
        except (KeyError, ValueError, OSError):
            self._solar = {}  # calendar without lunar columns (e.g. the demo data): lunar expressions stay unresolved

    def solar(self, lunar_year: int, month: int, day: int, leap: bool = False) -> date | None:
        return self._solar.get((lunar_year, month, day, leap))

    def tet(self, y: int) -> tuple[date, date] | None:
        """Section 2: 23 tháng Chạp (lunar year y-1) .. mùng 10 tháng Giêng (lunar year y), inclusive."""
        a, b = self.solar(y - 1, 12, 23), self.solar(y, 1, 10)
        return (a, b) if a and b else None


# ---- date helpers ----------------------------------------------------------
def _d(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def month_range(y: int, m: int) -> tuple[date, date]:
    return date(y, m, 1), date(y, m, _cal.monthrange(y, m)[1])


def quarter_range(y: int, q: int) -> tuple[date, date]:
    m0 = 3 * (q - 1) + 1
    return date(y, m0, 1), month_range(y, m0 + 2)[1]


def _prev_month(y: int, m: int) -> tuple[int, int]:
    return (y - 1, 12) if m == 1 else (y, m - 1)


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _same_day_last_year(d: date) -> date:
    return d.replace(year=d.year - 1, day=28) if (d.month, d.day) == (2, 29) else d.replace(year=d.year - 1)


def month_noyear(m: int, as_of: date) -> int:
    """Section 2: month M without year -> this year unless it is after today, then last year."""
    return as_of.year if date(as_of.year, m, 1) <= as_of else as_of.year - 1


def quarter_noyear(q: int, as_of: date) -> int:
    return as_of.year if quarter_range(as_of.year, q)[0] <= as_of else as_of.year - 1


def previous_period(p: Period, as_of: date) -> Period | None:
    """The 'kỳ trước' of a period (section 1: percent change vs previous period)."""
    g, refs = p.granularity, (R_PREV,) + p.rule_refs
    if p.start is None:
        return None
    if g == "day":
        d = p.start - timedelta(days=1)
        return Period(d, d, "day", refs)
    if g == "week":
        return Period(p.start - timedelta(days=7), p.end - timedelta(days=7), "week", refs)
    if g == "week_to_date":
        return Period(p.start - timedelta(days=7), p.end - timedelta(days=7), "week_to_date", refs)
    if g == "month":
        y, m = _prev_month(p.start.year, p.start.month)
        return Period(*month_range(y, m), "month", refs)
    if g == "month_to_date":  # section 2: same number of days of the previous month
        y, m = _prev_month(p.start.year, p.start.month)
        s, e = month_range(y, m)
        return Period(s, min(e, s.replace(day=min(p.end.day, e.day))), "month_to_date", refs + (R_MTD,))
    if g == "quarter":
        q = (p.start.month - 1) // 3 + 1
        y, q = (p.start.year - 1, 4) if q == 1 else (p.start.year, q - 1)
        return Period(*quarter_range(y, q), "quarter", refs)
    if g == "year":
        return Period(date(p.start.year - 1, 1, 1), date(p.start.year - 1, 12, 31), "year", refs)
    if g == "year_to_date":
        return Period(_same_day_last_year(p.start), _same_day_last_year(p.end), "year_to_date", refs)
    n = p.days() or 1  # range / rolling / tet: same number of days immediately before
    return Period(p.start - timedelta(days=n), p.start - timedelta(days=1), g, refs)


# ---- the resolver ------------------------------------------------------------
_NUMQ = {"1": 1, "2": 2, "3": 3, "4": 4, "i": 1, "ii": 2, "iii": 3, "iv": 4}
_COMPARE_RE = re.compile(r"so voi|so sanh|tang hay giam|tang/giam|hon hay kem|thay doi|tang giam|hon kem|\bcung ky\b")
_PREV_WORD = r"(?:truoc|roi|trc|lien truoc|ke truoc|vua roi|vua qua|qua)"

_DAYS = r"(\d{1,2})\s*[/-]\s*(\d{1,2})(?:\s*[/-]\s*(\d{4}))?"


class _Ctx:
    def __init__(self, text: str, as_of: date, cal: LunarCalendar | None, short_slash: str | None):
        self.t = text
        self.orig = text  # untouched folded text (comparison cue detection)
        self.as_of, self.cal, self.short_slash = as_of, cal, short_slash
        self.res = ResolveResult()
        self.items: list[tuple[int, Period]] = []  # (position in text, period)
        self.prev_refs: list[tuple[int, Period]] = []  # relative-previous phrases ("tháng trước")
        self.same_period_last_year = False

    def mask(self, m: re.Match) -> None:
        self.t = self.t[: m.start()] + " " * (m.end() - m.start()) + self.t[m.end():]

    def add(self, p: Period | None, m: re.Match, prev_ref: bool = False) -> None:
        if p is None:
            return
        (self.prev_refs if prev_ref else self.items).append((m.start(), p))
        self.mask(m)

    def orig_date(self, m: re.Match) -> date | None:
        """Date of a full d/m/yyyy match (None when it is not a real date)."""
        return _day_from(m.group(1), m.group(2), m.group(3), self)

    def amb(self, m: re.Match, reason: str, candidates: list[str] | None = None) -> None:
        self.res.ambiguous.append({"text": m.group(0).strip(), "reason": reason, "candidates": candidates or []})
        self.mask(m)


def _src(m: re.Match) -> str:
    return m.group(0).strip()


def _day_from(d: str, mo: str, y: str | None, ctx: _Ctx) -> date | None:
    d_, m_ = int(d), int(mo)
    if y:
        return _d(int(y), m_, d_)
    yy = month_noyear(m_, ctx.as_of) if 1 <= m_ <= 12 else ctx.as_of.year
    return _d(yy, m_, d_)


def _range_endpoint(tok: str, ctx: _Ctx, default_year: int | None = None) -> date | None:
    tok = tok.strip()
    if re.fullmatch(r"(?:ngay )?" + _TODAY, tok):
        return ctx.as_of
    m = re.fullmatch(r"(?:ngay )?" + _DAYS, tok)
    if m:
        d, mo, y = m.groups()
        if y is None and default_year is not None:
            return _d(default_year, int(mo), int(d))
        return _day_from(d, mo, y, ctx)
    return None


def _light_teencode(t: str) -> str:
    """Only the abbreviations that change a time expression's meaning (resolve() may see un-normalised text)."""
    t = re.sub(r"\btrc\b", "truoc", t)
    return re.sub(r"\bth\b(?=\s+(?:truoc|nay|sau|\d))", "thang", t)


def resolve(text: str, as_of: str | date, calendar: LunarCalendar | None = None,
            short_slash: str | None = None, tet_bare: bool = True) -> ResolveResult:
    """Resolve all time expressions in *text* relative to *as_of* (the question's 'today').

    short_slash: kept for compatibility, no longer used (the convention of _s_short_slash is fixed).
    tet_bare: a "Tết" without a year resolves to the latest Tết whose start (23 tháng Chạp) is <= as_of, when the
    running rulebook defines Tết (see RuleNormalizer) and calendar.csv covers it; otherwise it is ambiguous.
    """
    as_of_d = as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of)[:10])
    ctx = _Ctx(_light_teencode(fold(text)), as_of_d, calendar, short_slash)
    ctx.tet_bare = tet_bare
    for step in (_s_month_range, _s_n_days_from, _s_range, _s_stock_asof, _s_cumulative, _s_tet, _s_quarter, _s_day_full, _s_month, _s_relative_day,
                 _s_week, _s_rolling, _s_year, _s_short_slash, _s_day_short, _s_part_of_day):
        step(ctx)
    _finish(ctx)
    return ctx.res


def _month_ref(mo: str, y: str | None, ctx: _Ctx) -> tuple[int, int] | None:
    m_ = int(mo)
    if not 1 <= m_ <= 12:
        return None
    return (int(y) if y else month_noyear(m_, ctx.as_of), m_)


def _s_month_range(ctx: _Ctx) -> None:
    """'tu thang 4/2025 toi thang 6/2025' and 'N thang lien nhau ket thuc o thang 6/2025'."""
    mref = r"thangs?\s*(\d{1,2})(?:\s*(?:/|nam)\s*(\d{4}))?"
    for m in list(re.finditer(r"\btu\s+" + mref + r"\s+(?:den|toi|-)\s+(?:het\s+)?" + mref, ctx.t)):
        a, b = _month_ref(m.group(1), m.group(2) or m.group(4), ctx), _month_ref(m.group(3), m.group(4), ctx)
        if a and b and a <= b:
            ctx.add(Period(month_range(*a)[0], month_range(*b)[1], "month_series", (R_RANGE, R_MONTH), _src(m)), m)
    for m in list(re.finditer(r"\b(\d{1,2})\s*thang\s+lien\s*(?:nhau\s+)?(?:ket thuc|cuoi)\s*(?:o|tai|la|vao)?\s*" + mref, ctx.t)):
        n, end = int(m.group(1)), _month_ref(m.group(2), m.group(3), ctx)
        if end and 1 <= n <= 24:
            y, mo = end
            for _ in range(n - 1):
                y, mo = _prev_month(y, mo)
            ctx.add(Period(month_range(y, mo)[0], month_range(*end)[1], "month_series", (R_RANGE, R_MONTH), _src(m)), m)


def _s_range(ctx: _Ctx) -> None:
    pat = re.compile(
        r"\btu\s+(?:ngay\s+)?(?P<a>dau nam|dau " + _MONTH + r" nay|dau tuan nay|" + _DAYS + r"|" + _TODAY + r"|nay)"
        r"(?:\s+nam nay)?\s+(?:den|toi|-)\s+(?:het\s+|cuoi\s+)?(?P<b>(?:ngay\s+)?(?:" + _DAYS + r"|" + _TODAY + r"|nay))")
    for m in list(pat.finditer(ctx.t)):
        a_txt, b_txt = m.group("a"), m.group("b").strip()
        b_today = bool(re.fullmatch(r"(?:ngay\s+)?(?:" + _TODAY + r"|nay)", b_txt))
        if a_txt == "dau nam" and b_today:
            ctx.add(Period(date(ctx.as_of.year, 1, 1), ctx.as_of, "year_to_date", (R_YTD,), _src(m)), m)
            continue
        if re.fullmatch(r"dau " + _MONTH + " nay", a_txt) and b_today:
            ctx.add(Period(ctx.as_of.replace(day=1), ctx.as_of, "month_to_date", (R_MTD,), _src(m)), m)
            continue
        if a_txt == "dau tuan nay" and b_today:
            ctx.add(Period(_monday(ctx.as_of), ctx.as_of, "week_to_date", (R_WEEK,), _src(m)), m)
            continue
        if a_txt == "dau nam":
            s_ = date(ctx.as_of.year, 1, 1)
        elif a_txt == "nay" or re.fullmatch(_TODAY, a_txt):
            s_ = ctx.as_of
        else:
            b_year = re.search(r"/(\d{4})", b_txt)
            s_ = _range_endpoint(a_txt, ctx, int(b_year.group(1)) if b_year and not re.search(r"/\d{4}", a_txt) else None)
        e_ = ctx.as_of if b_today else _range_endpoint(b_txt, ctx)
        if s_ and e_ and s_ <= e_:
            ctx.add(Period(s_, e_, "range", (R_RANGE,), _src(m)), m)
        else:
            ctx.amb(m, "range endpoints not resolvable")


def _s_n_days_from(ctx: _Ctx) -> None:
    """'7 ngay ke tu ngay D' = D and the next N-1 days; compared with the N days right before D (section 5)."""
    for m in list(re.finditer(r"\b(\d{1,3})\s*ngay\s*(?:dau\s*)?ke tu\s*(?:ngay\s*)?(" + _DAYS + r")", ctx.t)):
        n = int(m.group(1))
        d = _range_endpoint(m.group(2), ctx)
        if d and n >= 1:
            ctx.add(Period(d, d + timedelta(days=n - 1), "range", (R_PRICE,), _src(m)), m)
            ctx.res.comparison = Period(d - timedelta(days=n), d - timedelta(days=1), "range", (R_PRICE,), f"{n} ngay ngay truoc")
    # "N ngay ke tu ngay do / ngay tang gia": the day is the one full date (with year) the question names; no or several dates: not resolved
    for m in list(re.finditer(r"\b(\d{1,3})\s*ngay\s*(?:dau\s*)?ke tu\s*(?:ngay\s*)?(?:do|ay|tang gia|doi gia|len gia|tang|doi)\b", ctx.t)):
        days = {ctx.orig_date(x) for x in re.finditer(_DAYS, ctx.t) if x.group(3)}
        n = int(m.group(1))
        if len(days) == 1 and None not in days and n >= 1 and ctx.res.comparison is None:
            d = next(iter(days))
            ctx.add(Period(d, d + timedelta(days=n - 1), "range", (R_PRICE,), _src(m)), m)
            ctx.res.comparison = Period(d - timedelta(days=n), d - timedelta(days=1), "range", (R_PRICE,), f"{n} ngay ngay truoc")


def _s_stock_asof(ctx: _Ctx) -> None:
    """'ton kho ngay D' / 'con ton ... ngay D' ask for the status at end of day D (cumulative)."""
    for m in list(re.finditer(r"\b(?:ton kho|con ton)\s+(?:tai |luc |cuoi )?ngay\s+(" + _DAYS + r")", ctx.t)):
        d = _range_endpoint(m.group(1), ctx)
        if d:
            ctx.add(Period(None, d, "cumulative", (R_CUM,), _src(m)), m)


def _s_cumulative(ctx: _Ctx) -> None:
    pat = re.compile(r"(?:tinh\s+)?(?:den|toi)\s+(?:het|cuoi)\s+(?:ngay\s+)?(?P<d>" + _DAYS + r"|" + _TODAY + r")"
                     r"|(?:tinh\s+)?(?:den|toi)\s+(?:ngay\s+)?" + _TODAY + r"|\bcuoi ngay\s+" + _TODAY + r"|\bhet\s+" + _TODAY)
    for m in list(pat.finditer(ctx.t)):
        d = m.group("d")
        end = ctx.as_of if d is None or re.fullmatch(_TODAY, d) else _range_endpoint(d, ctx)
        if end:
            ctx.add(Period(None, end, "cumulative", (R_CUM,), _src(m)), m)


def _s_tet(ctx: _Ctx) -> None:
    # "N ngay truoc tet": comparison window of N days right before 23 Chạp.  Taken first so
    # that its "Tết" is not mistaken for a year-less Tết.
    before = re.search(r"(\d+)\s*ngay\s*(?:ngay\s*)?truoc\s*tet", ctx.t)
    n_before = int(before.group(1)) if before else None
    if before:
        ctx.mask(before)
    pat = re.compile(r"(?:dip |mua )?\btet(?: am lich| ta)?(?: nam)?(?: (?P<y>nay|truoc|ngoai|\d{4}))?(?!\w)")
    bare: list[re.Match] = []
    for m in list(pat.finditer(ctx.t)):
        y_txt = m.group("y")
        if y_txt is None:
            bare.append(m)
            continue
        y = ctx.as_of.year if y_txt == "nay" else ctx.as_of.year - 1 if y_txt in ("truoc", "ngoai") else int(y_txt)
        if ctx.cal is None:
            ctx.amb(m, "no lunar calendar supplied")
            continue
        rng = ctx.cal.tet(y)
        if rng is None:
            ctx.amb(m, f"Tết {y} not covered by calendar file")
            continue
        ctx.add(Period(rng[0], rng[1], "tet", (R_TET,), _src(m)), m)
    if bare and not any(p.granularity == "tet" for _, p in ctx.items):
        rng = None
        if getattr(ctx, "tet_bare", True) and ctx.cal is not None:
            # the latest Tết that has started (23 tháng Chạp) on or before today
            for y in range(ctx.as_of.year + 1, ctx.as_of.year - 4, -1):
                cand = ctx.cal.tet(y)
                if cand and cand[0] <= ctx.as_of:
                    rng = cand
                    break
        if rng is None:
            ctx.amb(bare[0], "Tết without a year: no Tết has started yet in the calendar, or the rulebook does not define Tết")
        else:
            ctx.add(Period(rng[0], rng[1], "tet", (R_TET,), _src(bare[0])), bare[0])
    tet = next((p for _, p in ctx.items if p.granularity == "tet"), None)
    if n_before and tet:
        ctx.res.comparison = Period(tet.start - timedelta(days=n_before), tet.start - timedelta(days=1), "range",
                                    (R_TET,), before.group(0).strip())


def _s_quarter(ctx: _Ctx) -> None:
    pat = re.compile(r"\bquy\s*(?P<q>[1-4]|iv|iii|ii|i)\b(?:\s*(?:/|-|nam)\s*(?P<y>\d{4}))?|\bq\s*(?P<q2>[1-4])\s*[/\- ]\s*(?P<y2>\d{4})")
    for m in list(pat.finditer(ctx.t)):
        q = _NUMQ[(m.group("q") or m.group("q2"))]
        y_txt = m.group("y") or m.group("y2")
        if y_txt:
            ctx.add(Period(*quarter_range(int(y_txt), q), "quarter", (R_MONTH,), _src(m)), m)
        else:
            ctx.add(Period(*quarter_range(quarter_noyear(q, ctx.as_of), q), "quarter", (R_NOYEAR,), _src(m)), m)


def _s_day_full(ctx: _Ctx) -> None:
    for m in list(re.finditer(r"(?:\bngay\s*)?(?<![\d/])(\d{1,2})\s*[/-]\s*(\d{1,2})\s*[/-]\s*(\d{4})(?!\d)", ctx.t)):
        d = _d(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if d:
            ctx.add(Period(d, d, "day", (R_DAY,), _src(m)), m)
    for m in list(re.finditer(r"\bngay\s+(\d{1,2})\s+thang\s+(\d{1,2})(?:\s+nam\s+(\d{4}))?", ctx.t)):
        d = _day_from(m.group(1), m.group(2), m.group(3), ctx)
        if d:
            ctx.add(Period(d, d, "day", (R_DAY,) if m.group(3) else (R_DAY, R_NOYEAR), _src(m)), m)


def _s_month(ctx: _Ctx) -> None:
    # explicit year: "thang 6/2025", "thang 6 nam 2025", "Th2/2026"
    for m in list(re.finditer(r"\b(?:thangs?|th)\s*(\d{1,2})\s*(?:/|-|nam|\s)\s*(\d{4})(?!\d)", ctx.t)):
        mo, y = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            ctx.add(Period(*month_range(y, mo), "month", (R_MONTH,), _src(m)), m)
    # bare "6/2025" (lists such as "thang 5/2025, 6/2025 va 7/2025")
    for m in list(re.finditer(r"(?<![\d/])(\d{1,2})\s*/\s*(\d{4})(?![\d/])", ctx.t)):
        mo, y = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            ctx.add(Period(*month_range(y, mo), "month", (R_MONTH,), _src(m)), m)
    # "thang nay" / previous-month phrases
    for m in list(re.finditer(r"\b" + _MONTH + r"\s+nay\b", ctx.t)):
        s = ctx.as_of.replace(day=1)
        ctx.add(Period(s, ctx.as_of, "month_to_date", (R_MTD,), _src(m)), m)
    for m in list(re.finditer(r"\b" + _MONTH + r"\s+(?:lien\s+truoc|ke\s+truoc|vua\s+roi|vua\s+qua|truoc|roi|trc|qua)\b", ctx.t)):
        y, mo = _prev_month(ctx.as_of.year, ctx.as_of.month)
        ctx.add(Period(*month_range(y, mo), "month", (R_MONTH,), _src(m)), m, prev_ref=True)
    # month without year
    for m in list(re.finditer(r"\bthangs?\s*(\d{1,2})(?![\d/])(?!\s*nam\b)", ctx.t)):
        mo = int(m.group(1))
        if 1 <= mo <= 12:
            ctx.add(Period(*month_range(month_noyear(mo, ctx.as_of), mo), "month", (R_NOYEAR,), _src(m)), m)


def _s_relative_day(ctx: _Ctx) -> None:
    for m in list(re.finditer(r"\b(?:ngay\s+)?(?:hom\s+qua|hqua|bua\s+qua|hum\s+qua)\b", ctx.t)):
        d = ctx.as_of - timedelta(days=1)
        ctx.add(Period(d, d, "day", (R_DAY,), _src(m)), m)
    for m in list(re.finditer(r"\b(?:ngay\s+)?" + _TODAY + r"\b", ctx.t)):
        ctx.add(Period(ctx.as_of, ctx.as_of, "day", (R_DAY,), _src(m)), m)


def _s_week(ctx: _Ctx) -> None:
    for m in list(re.finditer(r"\btuan\s+nay\b", ctx.t)):
        ctx.add(Period(_monday(ctx.as_of), ctx.as_of, "week_to_date", (R_WEEK,), _src(m)), m)
    for m in list(re.finditer(r"\btuan\s+(?:lien\s+truoc|ke\s+truoc|vua\s+roi|vua\s+qua|truoc|roi|trc|qua)\b", ctx.t)):
        s = _monday(ctx.as_of) - timedelta(days=7)
        ctx.add(Period(s, s + timedelta(days=6), "week", (R_WEEK,), _src(m)), m, prev_ref=True)


def _s_rolling(ctx: _Ctx) -> None:
    for m in list(re.finditer(r"\b(\d{1,3})\s*ngay\s*(?:gan nhat|vua qua|gan day)\b", ctx.t)):
        n = int(m.group(1))
        if n >= 1:
            ctx.add(Period(ctx.as_of - timedelta(days=n - 1), ctx.as_of, "rolling", (R_LAST_N,), _src(m)), m)


def _s_year(ctx: _Ctx) -> None:
    for m in list(re.finditer(r"\btu\s+dau\s+nam(?:\s+(?:toi|den)\s+(?:nay|hom nay|het hom nay|nay))?", ctx.t)):
        ctx.add(Period(date(ctx.as_of.year, 1, 1), ctx.as_of, "year_to_date", (R_YTD,), _src(m)), m)
    for m in list(re.finditer(r"\bcung (?:ky|thang) nam (?:truoc|ngoai)\b", ctx.t)):
        ctx.mask(m)
        ctx.same_period_last_year = True
    for m in list(re.finditer(r"\bnam\s+(\d{4})\b", ctx.t)):
        y = int(m.group(1))
        ctx.add(Period(date(y, 1, 1), date(y, 12, 31), "year", (R_MONTH,), _src(m)), m)
    for m in list(re.finditer(r"\bnam\s+(?:ngoai|truoc|roi)\b", ctx.t)):
        y = ctx.as_of.year - 1
        ctx.add(Period(date(y, 1, 1), date(y, 12, 31), "year", (R_YTD,), _src(m)), m, prev_ref=True)
    for m in list(re.finditer(r"\bnam\s+nay\b", ctx.t)):
        ctx.add(Period(date(ctx.as_of.year, 1, 1), ctx.as_of, "year_to_date", (R_YTD,), _src(m)), m)


def _s_short_slash(ctx: _Ctx) -> None:
    """Two-part dates "a/bb" without a 4-digit year.  Convention (decided by the team):
      keyword "ngay" before it          -> ngày a tháng b (year by the rule for a month without year)
      keyword "thang" before it         -> tháng a năm 20b, only for 20 <= b <= 39
      no keyword, b <= 12               -> ngày a tháng b (handled by _s_day_short)
      no keyword, 20 <= b <= 39         -> tháng a năm 20b
      anything else (13..19, >= 40, bad day/month) -> ambiguous (the question goes to the LLM)"""
    for m in list(re.finditer(r"(?<![\d/])(\d{1,2})\s*/\s*(\d{2})(?![\d/])", ctx.t)):
        a, b = int(m.group(1)), int(m.group(2))
        prefix = ctx.t[max(0, m.start() - 8): m.start()]
        kw = "day" if re.search(r"(?:\bngay|\bhom)\s*$", prefix) else \
            "month" if re.search(r"(?:\bthang|\bth|\bt)\s*$", prefix) else None
        if kw is None and b <= 12 and 1 <= a <= 31:
            continue  # day/month without keyword: _s_day_short
        if kw == "day" and 1 <= b <= 12:
            d = _day_from(str(a), str(b), None, ctx)
            if d:
                ctx.add(Period(d, d, "day", (R_DAY, R_NOYEAR), _src(m)), m)
                continue
        elif kw in ("month", None) and 1 <= a <= 12 and 20 <= b <= 39:
            ctx.add(Period(*month_range(2000 + b, a), "month", (R_MONTH,), _src(m)), m)
            continue
        ctx.amb(m, "short slash date a/b: not covered by the convention (ngay a/b = day/month; thang a/bb or no keyword "
                   "with bb in 20..39 = month/year; no keyword with b <= 12 = day/month)", ["day_month", "month_year"])


def _s_day_short(ctx: _Ctx) -> None:
    for m in list(re.finditer(r"(?<![\d/])(\d{1,2})\s*/\s*(\d{1,2})(?![\d/])", ctx.t)):
        d = _day_from(m.group(1), m.group(2), None, ctx)
        if d and int(m.group(2)) <= 12:
            ctx.add(Period(d, d, "day", (R_DAY, R_NOYEAR), _src(m)), m)


def _s_part_of_day(ctx: _Ctx) -> None:
    if re.search(r"\bca\s+sang\b", ctx.t):
        ctx.res.part_of_day = {"sang": ("06:00", "13:59"), "rule": R_SHIFT}
    if re.search(r"\bca\s+chieu\b", ctx.t):
        pod = ctx.res.part_of_day or {"rule": R_SHIFT}
        pod["chieu"] = ("14:00", "21:59")
        ctx.res.part_of_day = pod


def _finish(ctx: _Ctx) -> None:
    res = ctx.res
    items = sorted(ctx.items, key=lambda x: x[0])
    prevs = [p for _, p in sorted(ctx.prev_refs, key=lambda x: x[0])]
    cue = re.search(r"so voi|so sanh voi|so vs", ctx.orig)
    wants_cmp = bool(_COMPARE_RE.search(ctx.orig)) or ctx.same_period_last_year
    both_shifts = bool(res.part_of_day and "sang" in res.part_of_day and "chieu" in res.part_of_day)
    # de-duplicate identical spans ("nam nay, tu dau nam den het hom nay")
    seen: set[tuple] = set()
    uniq: list[tuple[int, Period]] = []
    for pos, p in items:
        if (p.start, p.end) not in seen:
            seen.add((p.start, p.end))
            uniq.append((pos, p))
    items = uniq
    if both_shifts:  # "ca chieu so voi ca sang": same period, baseline = morning shift (section 2)
        res.part_of_day["baseline"] = "sang"
        res.periods = [p for _, p in items] + ([] if items else prevs)
        return
    if any(p.granularity == "month_series" for _, p in items):
        prevs = []  # "thang sau co luon cao hon thang truoc": relative to the series, not to today
    periods = [p for _, p in items]
    two = res.comparison is None and wants_cmp and cue is not None and len(items) == 2
    if two and items[0][0] < cue.start() <= items[1][0]:
        res.comparison, periods = items[1][1], [items[0][1]]  # "X so voi Y": Y named after the cue
    elif two and items[0][0] >= cue.start():
        res.comparison, periods = items[0][1], [items[1][1]]  # "so voi Y, X ..."
    elif res.comparison is None and wants_cmp and len(periods) == 1 and periods[0].start:
        main = periods[0]
        if ctx.same_period_last_year:
            res.comparison = Period(_same_day_last_year(main.start), _same_day_last_year(main.end), main.granularity,
                                    (R_PREV,) + main.rule_refs)
        else:  # "so voi thang truoc", "tang hay giam", ...: kỳ trước of the main period
            res.comparison = previous_period(main, ctx.as_of)
    if res.comparison is not None or (wants_cmp and len(periods) == 1):
        prevs = []  # the "...truoc" phrase only named the comparison window
    res.periods = periods + prevs


def format_for_prompt(res: ResolveResult) -> str:
    """Compact Vietnamese block for the SQL prompt: concrete dates, one per resolved expression."""
    lines: list[str] = []
    for p in res.periods:
        rng = f"đến hết {p.end}" if p.start is None else f"{p.start} → {p.end}"
        lines.append(f"- \"{p.source}\": {rng} ({p.granularity}; {'; '.join(p.rule_refs)})")
    if res.comparison:
        c = res.comparison
        lines.append(f"- kỳ so sánh: {c.start} → {c.end} ({c.granularity})")
    if res.part_of_day:
        parts = {k: v for k, v in res.part_of_day.items() if k in ("sang", "chieu")}
        lines.append("- ca: " + ", ".join(f"{k} {a}–{b}" for k, (a, b) in parts.items()))
    for a in res.ambiguous:
        lines.append(f"- KHÔNG xác định được \"{a['text']}\": {a['reason']}")
    return "\n".join(lines)
