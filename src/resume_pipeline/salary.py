"""Turn the salary text on a job lead into a yearly range, or admit it cannot.

A missing or unreadable salary is `None`. It is never zero and never a pass.

Rules, in plain words:

* Numbers with a `$` in front or a `k`/`m` after are salary figures. If the text has any, only those count,
  so "3 openings, $90k-$110k" reads as 90,000 to 110,000.
* More than two salary figures is ambiguous (three levels, three salaries), so it is unknown.
* `401k` is a retirement plan, not a salary, and is ignored.
* A bare number beside a range dash or "to" next to a marked figure is part of the range ("$90,000 - 110,000").
* A bare number with no `$`, `k` or unit must be at least 10,000 a year, so "2024-2025" is unknown.
* Per hour, week, biweekly and month are converted to a year.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NUMBER = re.compile(r"(\$\s*)?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?!\d)\s*(?:([kKmM])(?![A-Za-z]))?")
_RETIREMENT = re.compile(r"\b401\s*\(?k\)?", re.IGNORECASE)
_HOURLY = re.compile(r"(/\s*h(?:ou)?r|per\s*hour|hourly|an\s+hour)", re.IGNORECASE)
_BIWEEKLY = re.compile(r"(bi-?weekly|every\s+two\s+weeks|per\s*fortnight)", re.IGNORECASE)
_WEEKLY = re.compile(r"(/\s*w(?:ee)?k|per\s*week|weekly|\d[kK]?\s+a\s+week)", re.IGNORECASE)
_MONTHLY = re.compile(r"(/\s*mo(?:nth)?|/\s*mth|per\s*month|monthly|\d[kK]?\s+a\s+month)", re.IGNORECASE)

_MIN_BARE_YEARLY = 10_000  # a bare number below this is more likely a year or a count than a salary
_MIN_PLAUSIBLE_YEARLY = 1_000
_MAX_PLAUSIBLE_YEARLY = 10_000_000


@dataclass(frozen=True)
class SalaryRange:
    low: float
    high: float
    basis: str  # "year", "hour", "week", "biweek" or "month": what the lead said before conversion


def parse_salary(text: str | None, hours_per_year: int = 2080) -> SalaryRange | None:
    """Return a yearly range, or None when the text has no usable salary."""
    if text is None:
        return None
    s = _RETIREMENT.sub(" ", str(text)).strip()
    if not s:
        return None

    tokens: list[list[float | bool]] = []  # [value, marked]
    spans: list[tuple[int, int]] = []
    for m in _NUMBER.finditer(s):
        dollar, whole, frac, suffix = m.group(1), m.group(2), m.group(3) or "", m.group(4)
        try:
            n = float(whole.replace(",", "") + frac)
        except ValueError:
            continue
        if suffix:
            n *= 1_000 if suffix.lower() == "k" else 1_000_000
        tokens.append([n, bool(dollar or suffix)])
        spans.append((m.start(), m.end()))
    if not tokens:
        return None
    # "90-110k": the k covers the whole range, so 90 is thousands too.
    if (
        len(tokens) == 2
        and tokens[1][1]
        and tokens[0][0] < 1000 <= tokens[1][0]
        and re.search(r"\d\s*(?:-|–|—|to)\s*\$?\d[\d,.]*\s*[kK]\b", s)
    ):
        tokens[0] = [tokens[0][0] * 1_000, True]

    # A bare number next to a range dash or "to" takes on its neighbour's mark: "$90,000 - 110,000".
    link = re.compile(r"\s*(?:-|–|—|to)\s*")
    for _ in tokens:
        for i, tok in enumerate(tokens):
            if tok[1]:
                continue
            for j in (i - 1, i + 1):
                if 0 <= j < len(tokens) and tokens[j][1]:
                    a, b = sorted((i, j))
                    if link.fullmatch(s[spans[a][1] : spans[b][0]]):
                        tok[1] = True
    marked = [t for t in tokens if t[1]]
    chosen = marked if marked else tokens
    if len(chosen) > 2:
        return None
    values = [float(t[0]) for t in chosen]
    low, high = min(values), max(values)

    if _HOURLY.search(s):
        basis, factor = "hour", float(hours_per_year)
    elif _BIWEEKLY.search(s):
        basis, factor = "biweek", 26.0
    elif _WEEKLY.search(s):
        basis, factor = "week", 52.0
    elif _MONTHLY.search(s):
        basis, factor = "month", 12.0
    else:
        basis, factor = "year", 1.0
    low, high = low * factor, high * factor
    if basis == "year" and not marked and high < _MIN_BARE_YEARLY:
        return None
    if not (_MIN_PLAUSIBLE_YEARLY <= high <= _MAX_PLAUSIBLE_YEARLY):
        return None
    return SalaryRange(low=low, high=high, basis=basis)
