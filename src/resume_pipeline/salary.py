"""Turn the salary text on a job lead into a yearly range, or admit it cannot.

A missing or unreadable salary is `None`. It is never zero and never a pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 1,200 or 90000 or 45.50, optionally followed by k / K / m / M
_NUMBER = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*([kKmM])?(?![\w])")
_HOURLY = re.compile(r"(/\s*h(?:ou)?r|per\s+hour|hourly|an\s+hour)", re.IGNORECASE)
_MONTHLY = re.compile(r"(/\s*mo(?:nth)?|per\s+month|monthly)", re.IGNORECASE)

# A yearly salary under this is almost certainly a typo or an hourly rate with no unit.
_MIN_PLAUSIBLE_YEARLY = 1_000
_MAX_PLAUSIBLE_YEARLY = 10_000_000


@dataclass(frozen=True)
class SalaryRange:
    low: float
    high: float
    basis: str  # "year", "hour" or "month": what the lead said before conversion


def parse_salary(text: str | None, hours_per_year: int = 2080) -> SalaryRange | None:
    """Return a yearly range, or None when the text has no usable salary."""
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None

    values: list[float] = []
    for m in _NUMBER.finditer(s):
        whole, frac, suffix = m.group(1), m.group(2) or "", m.group(3)
        try:
            n = float(whole.replace(",", "") + frac)
        except ValueError:
            continue
        if suffix:
            n *= 1_000 if suffix.lower() == "k" else 1_000_000
        values.append(n)
    if not values:
        return None
    # "k" applies to the whole range in "90-110k": 90 and 110 are both thousands.
    if re.search(r"\d\s*(?:-|–|—|to)\s*\$?\d[\d,.]*\s*[kK]\b", s) and values[0] < 1000 <= values[-1]:
        values[0] *= 1_000
    values = values[:2]

    low, high = min(values), max(values)
    if _HOURLY.search(s):
        basis, factor = "hour", float(hours_per_year)
    elif _MONTHLY.search(s):
        basis, factor = "month", 12.0
    else:
        basis, factor = "year", 1.0
    low, high = low * factor, high * factor
    if not (_MIN_PLAUSIBLE_YEARLY <= high <= _MAX_PLAUSIBLE_YEARLY):
        return None
    return SalaryRange(low=low, high=high, basis=basis)
