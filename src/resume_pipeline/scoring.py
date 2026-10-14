"""Score every lead against the rubric. Deterministic, no model, every point explained.

The order of checks is fixed, so the same CSV and rubric always give the same
ranking and the same reasons:

1. A lead with no title cannot be scored. It is flagged, not guessed at.
2. Knockouts. Any one of them ends the lead, whatever else it earns.
3. Salary floor, unless the company is whitelisted.
4. Location and remote rules.
5. Must-haves (a missing one is a knockout), then points: title family,
   nice-to-haves, remote bonus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .leads import Lead
from .rubric import Rubric, Term
from .salary import parse_salary


@dataclass(frozen=True)
class Scored:
    lead: Lead
    score: float
    knocked_out: bool
    reasons: tuple[str, ...]  # why the score is what it is, in the order they were applied
    incomplete: tuple[str, ...] = field(default=())  # what was missing, so the rank is a lower bound
    rank: int | None = None  # 1 = best; None for knocked-out leads


def fmt_number(n: float) -> str:
    """Plain digits, never 1.5e+06. Whole numbers have no decimals; others keep up to two."""
    if n == int(n):
        return str(int(n))
    return f"{n:.2f}".rstrip("0").rstrip(".")


def _contains(haystack: str, phrase: str) -> bool:
    """Whole-word, case-insensitive. 'sql' must not match 'mysql'; 'c++' must work."""
    pattern = r"(?<![A-Za-z0-9])" + re.escape(phrase.casefold()) + r"(?![A-Za-z0-9])"
    return re.search(pattern, haystack.casefold()) is not None


def _first_hit(term: Term, text: str) -> str | None:
    return next((p for p in term.phrases if _contains(text, p)), None)


_NOT_REMOTE = re.compile(r"(?<![A-Za-z])(?:not|non|no)[\s-]+remote", re.IGNORECASE)


def _is_remote(lead: Lead) -> bool:
    """The word "remote" in the location or title, unless it is negated ("not remote", "non-remote")."""
    text = f"{lead.location}\n{lead.title}"
    return _contains(text, "remote") and not _NOT_REMOTE.search(text)


def score_lead(lead: Lead, rubric: Rubric) -> Scored:
    reasons: list[str] = []
    incomplete: list[str] = []

    if not lead.title:
        return Scored(lead, 0.0, True, ("knockout: no job title, so nothing can be scored",), ("title",))

    searchable = f"{lead.title}\n{lead.company}\n{lead.description}"

    # 2. Knockouts beat everything.
    hits = [k for k in rubric.knockouts if _contains(searchable, k)]
    if hits:
        shown = ", ".join(hits)
        return Scored(lead, 0.0, True, (f"knockout: contains {shown}",), tuple(incomplete))

    # 3. Salary floor. A whitelisted company skips the floor entirely.
    whitelisted = any(lead.company.casefold() == c.casefold() for c in rubric.company_whitelist)
    if rubric.salary_floor is not None:
        pay = parse_salary(lead.salary, rubric.hours_per_year)
        if whitelisted:
            reasons.append("salary floor waived: company is on the whitelist")
        elif pay is None:
            incomplete.append("salary")
            reasons.append("salary unknown: not checked against the floor")
        elif pay.high < rubric.salary_floor:
            return Scored(
                lead,
                0.0,
                True,
                (f"knockout: salary stated below floor ({fmt_number(pay.high)} < {fmt_number(rubric.salary_floor)})",),
                tuple(incomplete),
            )
        else:
            reasons.append(f"salary clears the floor ({fmt_number(pay.high)} >= {fmt_number(rubric.salary_floor)})")

    # 4. Location and remote rules.
    remote = _is_remote(lead)
    if remote and rubric.remote == "reject":
        return Scored(
            lead,
            0.0,
            True,
            ("knockout: remote role and the rubric rejects remote",),
            tuple(incomplete),
        )
    if not remote and rubric.remote == "only":
        if not lead.location:
            incomplete.append("location")
            reasons.append("location unknown: rubric wants remote only, could not check")
        else:
            return Scored(
                lead,
                0.0,
                True,
                ("knockout: not remote and the rubric wants remote only",),
                tuple(incomplete),
            )
    if not remote and rubric.remote != "only" and rubric.allowed_locations:
        if not lead.location:
            incomplete.append("location")
            reasons.append("location unknown: not checked against the allowed list")
        elif not any(_contains(lead.location, a) for a in rubric.allowed_locations):
            return Scored(
                lead,
                0.0,
                True,
                (f"knockout: location {lead.location} is not in the allowed list",),
                tuple(incomplete),
            )
        else:
            reasons.append(f"location ok: {lead.location}")

    # 5a. Must-haves. Without a description we cannot check them, so we say so.
    for term in rubric.must_haves:
        if not lead.description:
            if "description" not in incomplete:
                incomplete.append("description")
            reasons.append(f"must-have not checked (no description): {term.name}")
        elif _first_hit(term, searchable) is None:
            return Scored(lead, 0.0, True, (f"knockout: missing must-have {term.name}",), tuple(incomplete))
        else:
            reasons.append(f"must-have present: {term.name}")

    # 5b. Points.
    score = 0.0
    families = [(t, _first_hit(t, lead.title)) for t in rubric.title_families]
    matched = [(t, h) for t, h in families if h]
    if matched:
        best = max(matched, key=lambda th: th[0].points)  # the best family counts once
        score += best[0].points
        reasons.insert(0, f"+{fmt_number(best[0].points)} title family: {best[0].name}")
    for term in rubric.nice_to_haves:
        if _first_hit(term, searchable) is not None:
            score += term.points
            reasons.append(f"+{fmt_number(term.points)} nice-to-have: {term.name}")
    if remote and rubric.remote_points:
        score += rubric.remote_points
        reasons.append(f"+{fmt_number(rubric.remote_points)} remote")
    if not matched:
        reasons.insert(0, "+0 title family: no match")

    return Scored(lead, score, False, tuple(reasons), tuple(incomplete))


def score_all(leads: list[Lead], rubric: Rubric) -> list[Scored]:
    """Score, then rank. Higher score first; ties keep the order they had in the CSV."""
    scored = [score_lead(lead, rubric) for lead in leads]
    live = sorted((s for s in scored if not s.knocked_out), key=lambda s: (-s.score, s.lead.row))
    dead = sorted((s for s in scored if s.knocked_out), key=lambda s: s.lead.row)
    ranked = [Scored(s.lead, s.score, False, s.reasons, s.incomplete, rank=i) for i, s in enumerate(live, start=1)]
    return ranked + dead
