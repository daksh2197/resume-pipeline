"""Read a CSV of job leads into plain records, using the rubric's column mapping."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

from .rubric import COLUMN_KEYS, Rubric

MAX_ROWS = 20_000  # a daily list is dozens of rows; this stops an accidental 2 GB file
MAX_FIELD = 20_000  # characters; a job description longer than this is cut, not crashed on


class LeadsError(ValueError):
    """The CSV cannot be used. The message says what to change."""


@dataclass(frozen=True)
class Lead:
    row: int  # 1-based position among the data rows, so "row 3" matches the sheet
    title: str
    company: str
    location: str
    salary: str
    url: str
    description: str
    has_description_column: bool


def _clean(value: str | None) -> str:
    return (value or "").replace("\x00", "").strip()[:MAX_FIELD]


def _bounded(reader: csv.DictReader):  # type: ignore[type-arg]
    for n, record in enumerate(reader, start=1):
        if n > MAX_ROWS:
            raise LeadsError(f"The CSV has more than {MAX_ROWS} rows. Split it.")
        yield record


def read_leads(path: str | Path, rubric: Rubric) -> list[Lead]:
    try:
        raw = Path(path).read_bytes()
    except OSError as err:
        raise LeadsError(f"Cannot read {path}: {err.strerror or err}") from err
    try:
        text = raw.decode("utf-8-sig")  # spreadsheets add a byte-order mark
    except UnicodeDecodeError:
        text = raw.decode("latin-1")  # old Excel exports; every byte maps to something

    csv.field_size_limit(MAX_FIELD * 4)
    reader = csv.DictReader(io.StringIO(text, newline=""), skipinitialspace=True)
    headers = [h.strip() for h in (reader.fieldnames or [])]
    if not headers:
        raise LeadsError(f"{path} is empty: expected a header row")
    lookup = {h.casefold(): h for h in reader.fieldnames or []}

    resolved: dict[str, str | None] = {}
    for key in COLUMN_KEYS:
        header = rubric.columns.get(key)
        resolved[key] = lookup.get(header.casefold()) if header else None
    if resolved["title"] is None:
        raise LeadsError(
            f"No column named {rubric.columns['title']!r} in {path}. "
            f"Its columns are: {', '.join(headers)}. Fix columns.title in the rubric."
        )
    for key in COLUMN_KEYS:
        header = rubric.columns.get(key)
        if header and resolved[key] is None and key != "title":
            raise LeadsError(
                f"The rubric maps {key} to {header!r}, but {path} has no such column. "
                f"Its columns are: {', '.join(headers)}."
            )

    leads: list[Lead] = []
    try:
        records = list(_bounded(reader))
    except csv.Error as err:
        raise LeadsError(f"{path} is not a readable CSV: {err}") from err
    for i, record in enumerate(records, start=1):

        def field(key: str, record: dict[str, str | None] = record) -> str:
            header = resolved[key]
            return _clean(record.get(header)) if header else ""

        leads.append(
            Lead(
                row=i,
                title=field("title"),
                company=field("company"),
                location=field("location"),
                salary=field("salary"),
                url=field("url"),
                description=field("description"),
                has_description_column=resolved["description"] is not None,
            )
        )
    return leads
