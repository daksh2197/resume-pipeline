"""The rubric: your rules, loaded from YAML and checked before anything is scored.

Nothing in here scores a job. It only reads the file and refuses a rubric that
would give silent wrong answers (a negative weight, a typo'd key, a floor that
is not a number).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

COLUMN_KEYS = ("title", "company", "location", "salary", "url", "description")
REMOTE_MODES = ("accept", "only", "reject")
TOP_LEVEL_KEYS = {
    "columns",
    "title_families",
    "must_haves",
    "nice_to_haves",
    "knockouts",
    "salary",
    "location",
    "company_whitelist",
    "shortlist_size",
}


class RubricError(ValueError):
    """The rubric file is wrong. The message says where and how to fix it."""


@dataclass(frozen=True)
class Term:
    """Something to look for in a posting, worth `points` if found."""

    name: str
    phrases: tuple[str, ...]
    points: float


@dataclass(frozen=True)
class Rubric:
    columns: dict[str, str]
    title_families: tuple[Term, ...]
    must_haves: tuple[Term, ...]
    nice_to_haves: tuple[Term, ...]
    knockouts: tuple[str, ...]
    salary_floor: float | None
    hours_per_year: int
    allowed_locations: tuple[str, ...]
    remote: str
    remote_points: float
    company_whitelist: tuple[str, ...]
    shortlist_size: int
    extra: dict[str, Any] = field(default_factory=dict)


def _number(value: Any, where: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RubricError(f"{where} must be a number, got {value!r}")
    if value != value or value in (float("inf"), float("-inf")):
        raise RubricError(f"{where} must be a finite number, got {value!r}")
    if value < minimum:
        raise RubricError(f"{where} must be {minimum:g} or more, got {value!r}")
    return float(value)


def _strings(value: Any, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise RubricError(f"{where} must be a list of non-empty text values")
    return tuple(v.strip() for v in value)


def _terms(value: Any, where: str, default_points: float) -> tuple[Term, ...]:
    """Each entry is either a bare phrase or {name, match, points}."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise RubricError(f"{where} must be a list")
    out: list[Term] = []
    for i, item in enumerate(value):
        here = f"{where}[{i}]"
        if isinstance(item, str) and item.strip():
            out.append(Term(item.strip(), (item.strip(),), default_points))
        elif isinstance(item, dict):
            unknown = set(item) - {"name", "match", "points", "weight"}
            if unknown:
                raise RubricError(f"{here} has unknown keys: {', '.join(sorted(unknown))}")
            phrases = _strings(item.get("match"), f"{here}.match")
            name = item.get("name") or (phrases[0] if phrases else "")
            if not isinstance(name, str) or not name.strip():
                raise RubricError(f"{here} needs a name or a match list")
            if not phrases:
                phrases = (name.strip(),)
            raw = item.get("points", item.get("weight", default_points))
            out.append(Term(name.strip(), phrases, _number(raw, f"{here}.points")))
        else:
            raise RubricError(f"{here} must be a phrase or a mapping, got {item!r}")
    return tuple(out)


def parse_rubric(data: Any) -> Rubric:
    if not isinstance(data, dict):
        raise RubricError("The rubric must be a YAML mapping at the top level")
    unknown = set(data) - TOP_LEVEL_KEYS
    if unknown:
        raise RubricError(
            f"Unknown top-level keys: {', '.join(sorted(unknown))}. Allowed: {', '.join(sorted(TOP_LEVEL_KEYS))}"
        )

    columns = data.get("columns") or {}
    if not isinstance(columns, dict):
        raise RubricError("columns must be a mapping of field name to CSV header")
    bad = set(columns) - set(COLUMN_KEYS)
    if bad:
        raise RubricError(f"columns has unknown fields: {', '.join(sorted(bad))}. Use: {', '.join(COLUMN_KEYS)}")
    cols = {k: str(v).strip() for k, v in columns.items() if v is not None and str(v).strip()}
    if "title" not in cols:
        raise RubricError("columns.title is required: say which CSV header holds the job title")

    salary = data.get("salary") or {}
    if not isinstance(salary, dict):
        raise RubricError("salary must be a mapping")
    bad = set(salary) - {"floor", "hours_per_year"}
    if bad:
        raise RubricError(f"salary has unknown keys: {', '.join(sorted(bad))}")
    floor = salary.get("floor")
    floor_n = None if floor is None else _number(floor, "salary.floor")
    hours = int(_number(salary.get("hours_per_year", 2080), "salary.hours_per_year", minimum=1))

    location = data.get("location") or {}
    if not isinstance(location, dict):
        raise RubricError("location must be a mapping")
    bad = set(location) - {"allowed", "remote", "remote_points"}
    if bad:
        raise RubricError(f"location has unknown keys: {', '.join(sorted(bad))}")
    remote = location.get("remote", "accept")
    if remote not in REMOTE_MODES:
        raise RubricError(f"location.remote must be one of {', '.join(REMOTE_MODES)}, got {remote!r}")

    size = int(_number(data.get("shortlist_size", 10), "shortlist_size", minimum=1))

    return Rubric(
        columns=cols,
        title_families=_terms(data.get("title_families"), "title_families", 3.0),
        must_haves=_terms(data.get("must_haves"), "must_haves", 2.0),
        nice_to_haves=_terms(data.get("nice_to_haves"), "nice_to_haves", 1.0),
        knockouts=_strings(data.get("knockouts"), "knockouts"),
        salary_floor=floor_n,
        hours_per_year=hours,
        allowed_locations=_strings(location.get("allowed"), "location.allowed"),
        remote=remote,
        remote_points=_number(location.get("remote_points", 0), "location.remote_points"),
        company_whitelist=_strings(data.get("company_whitelist"), "company_whitelist"),
        shortlist_size=size,
    )


def load_rubric(path: str | Path) -> Rubric:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as err:
        raise RubricError(f"Cannot read the rubric at {path}: {err.strerror or err}") from err
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise RubricError(f"The rubric is not valid YAML: {err}") from err
    return parse_rubric(data)
