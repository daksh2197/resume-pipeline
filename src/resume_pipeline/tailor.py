"""Tailor: one posting in, a résumé and a cover letter out, built only from your story bank.

Three steps, and only the middle one uses a model:

1. `tailor posting.txt` ranks your story-bank lines by the words they share with the posting, lists the
   posting words your bank never mentions, and writes a prompt.
2. You paste the prompt into any assistant and save its answer as reply.md.
3. `tailor --render reply.md` checks the reply, then writes resume.html (print it to PDF), resume.md and
   cover-letter.md. A reply that fails the check is never rendered.

The base résumé (resume.yaml) owns everything that is not a bullet: your name, contact line, job titles,
employers, dates and education. The model never writes those, so it cannot promote you or move a date.
Each role lists the story-bank lines that belong to it, and a bullet under a role may only cite that
role's lines. The number rules are the same as `pack --check`: every number must be in the bank, and a
bullet's numbers must be in the lines it cites.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

import yaml

from .pack import (
    CITATION,
    HEADING,
    ITEM,
    PackError,
    StoryBank,
    _reply_idents,
    _reply_numbers,
    _word_numbers,
    numbers_in,
)

SECTIONS = ("Summary", "Experience", "Cover letter", "Gaps")
BULLETS_PER_ROLE = (1, 5)
LETTER_WORDS = (150, 320)  # "about 250 words" asked for; this is the tolerance

# Words too common to say anything about fit. Kept short on purpose: a longer list hides real gaps.
STOPWORDS = set(
    """about above across after again against also among and any are around as at be because been before
    being below between both but by can could did do does doing during each either etc every few for from
    further had has have having help helps her here hers him his how into its itself just least less like
    make makes making may more most must near need needs new not now off once only other our ours out over
    own per plus same she should since some such than that the their theirs them then there these they
    this those through too under until upon very via was way ways well were what when where which while
    who whom whose why will with within without would year years you your yours yourself able ability
    across work working works role team teams join company we us including include includes strong
    experience experienced looking based day days time preferred required requirements responsibilities
    candidate candidates position opportunity""".split()
)
WORD = re.compile(r"[a-z][a-z+#.\-]*[a-z+#]|[a-z]")


class TailorError(ValueError):
    """Bad input: an unreadable base résumé, a role citing a line that is not in the bank."""


@dataclass(frozen=True)
class Role:
    id: str
    title: str
    org: str
    dates: str
    where: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class BaseResume:
    name: str
    contact: tuple[str, ...]
    roles: tuple[Role, ...]
    education: tuple[str, ...] = ()
    also: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    sign_off: str = ""
    role_of: dict[str, str] = field(default_factory=dict)  # "S2" -> "aws"


def _strs(value, what: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, list) or not all(isinstance(v, str | int | float) for v in value):
        raise TailorError(f"resume.yaml: {what} must be a list of text lines.")
    return tuple(str(v) for v in value)


def parse_resume(text: str, bank: StoryBank) -> BaseResume:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise TailorError(f"resume.yaml is not valid YAML: {err}") from None
    if not isinstance(data, dict):
        raise TailorError("resume.yaml must be a mapping with name, contact and roles.")
    name = str(data.get("name") or "").strip()
    if not name:
        raise TailorError("resume.yaml needs a name.")
    raw_roles = data.get("roles")
    if not isinstance(raw_roles, list) or not raw_roles:
        raise TailorError("resume.yaml needs at least one role under roles:.")

    roles: list[Role] = []
    role_of: dict[str, str] = {}
    for i, r in enumerate(raw_roles, start=1):
        if not isinstance(r, dict):
            raise TailorError(f"resume.yaml: role {i} must be a mapping.")
        rid = str(r.get("id") or "").strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", rid):
            raise TailorError(f"resume.yaml: role {i} needs an id of lower-case letters, digits or dashes.")
        if any(x.id == rid for x in roles):
            raise TailorError(f"resume.yaml: role id {rid!r} is used twice.")
        lines = _strs(r.get("lines"), f"role {rid} lines")
        if not lines:
            raise TailorError(f"resume.yaml: role {rid} lists no story-bank lines.")
        for s in lines:
            if s not in bank.lines:
                raise TailorError(f"resume.yaml: role {rid} lists {s}, which is not in the story bank.")
            if s in role_of:
                raise TailorError(f"resume.yaml: {s} is listed under both {role_of[s]} and {rid}.")
            role_of[s] = rid
        roles.append(
            Role(
                rid,
                str(r.get("title") or "").strip(),
                str(r.get("org") or "").strip(),
                str(r.get("dates") or "").strip(),
                str(r.get("where") or "").strip(),
                lines,
            )
        )
        if not roles[-1].title or not roles[-1].org:
            raise TailorError(f"resume.yaml: role {rid} needs a title and an org.")

    education = _strs(data.get("education"), "education")
    also = _strs(data.get("also"), "also")
    for s in (*education, *also):
        if re.fullmatch(r"S\d+", s) and s not in bank.lines:
            raise TailorError(f"resume.yaml: {s} is not in the story bank.")
    return BaseResume(
        name,
        _strs(data.get("contact"), "contact"),
        tuple(roles),
        education,
        also,
        _strs(data.get("skills"), "skills"),
        str(data.get("sign_off") or "").strip(),
        role_of,
    )


# --- step 1: rank and prompt -------------------------------------------------------------------------


def _stem(word: str) -> str:
    word = word.strip(".-")
    for suffix in ("ations", "ation", "ments", "ment", "ings", "ing", "ers", "er", "ies", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    return word[:-1] if len(word) > 4 and word.endswith("e") else word


def terms(text: str) -> dict[str, str]:
    """Stem -> the first spelling seen, for every word worth matching."""
    found: dict[str, str] = {}
    for w in WORD.findall(CITATION.sub(" ", text.casefold())):
        w = w.strip(".-")
        if len(w) < 3 or w in STOPWORDS:
            continue
        found.setdefault(_stem(w), w)
    return found


@dataclass(frozen=True)
class Match:
    line: str
    shared: tuple[str, ...]


URL = re.compile(r"https?://\S+|www\.\S+")


def rank_lines(posting: str, bank: StoryBank) -> tuple[list[Match], list[str]]:
    """Story-bank lines by how much of the posting they cover, best first, plus the posting words (most
    used first) that no line mentions. A shared word counts as often as the posting uses it, so a line
    that matches "renewal" five times beats one that matches a word said once. Links are ignored.
    Same input, same answer: no model involved."""
    posting = URL.sub(" ", posting)
    wanted = terms(posting)
    counts: dict[str, int] = {}
    for w in WORD.findall(posting.casefold()):
        w = w.strip(".-")
        if len(w) >= 3 and w not in STOPWORDS:
            counts[_stem(w)] = counts.get(_stem(w), 0) + 1
    covered: set[str] = set()
    scored = []
    order = {sid: i for i, sid in enumerate(bank.lines)}
    for sid, text in bank.lines.items():
        shared = sorted(set(terms(text)) & set(wanted), key=lambda s: (-counts[s], s))
        covered |= set(shared)
        scored.append((-sum(counts[s] for s in shared), order[sid], Match(sid, tuple(wanted[s] for s in shared))))
    scored.sort(key=lambda x: x[:2])
    missing = sorted((s for s in wanted if s not in covered), key=lambda s: (-counts[s], s))
    return [m for *_, m in scored], [wanted[s] for s in missing]


def build_tailor_prompt(posting: str, bank: StoryBank, base: BaseResume) -> str:
    if not posting.strip():
        raise PackError("The posting is empty.")
    matches, missing = rank_lines(posting, bank)
    ranked = "\n".join(
        f"{m.line}: {bank.lines[m.line]}" + (f"   (shares: {', '.join(m.shared)})" if m.shared else "") for m in matches
    )
    roles = "\n".join(
        f"### {r.id}\n(= {r.title}, {r.org}, {r.dates or 'no dates'}. Cite only: {', '.join(r.lines)})"
        for r in base.roles
    )
    gaps = ", ".join(missing[:20]) or "none found"
    return f"""You are tailoring my résumé and cover letter to one job posting. Use ONLY the story bank below
as evidence about me. Do not invent experience, employers, tools, numbers, dates or titles. If the posting
asks for something the story bank does not show, say so under Gaps and leave it off the résumé.

The story-bank lines are already ordered by how many words they share with the posting. Lead with the
ones that match, but rewrite them in the posting's own words where that stays true.

Reply in exactly these four sections, with these headings:

## Summary
Two or three sentences for the top of the résumé, aimed at this role. Cite lines like [S2].

## Experience
One sub-heading per role below, in this order, using the role id exactly as written (### aws). Under each,
1 to 5 bullets, most relevant to this posting first. Every bullet ends with the line or lines it came from,
like [S3], and may cite only that role's lines. Use only numbers that appear in the cited line. Do not
write titles, employers or dates: the template adds them.

{roles}

## Cover letter
About 250 words to the hiring team, in my voice: short sentences, no hype, one honest line about a gap.
Start with "Hello <company> team,". End before the sign-off; the template adds my name and contact line.

## Gaps
What the posting asks for that my story bank does not show. Plain, no spin.

Every number you write must appear in the story bank. Do not add any other numbers.

Posting words my story bank never mentions (a hint for Gaps, not a list to copy): {gaps}

--- STORY BANK (best match first) ---
{ranked}

--- POSTING ---
{posting.strip()}
"""


# --- step 2: check -------------------------------------------------------------------------------------


@dataclass
class Tailored:
    summary: str = ""
    experience: dict[str, list[str]] = field(default_factory=dict)  # role id -> bullets
    letter: str = ""
    gaps: str = ""


def _split(reply: str, base: BaseResume) -> tuple[Tailored, list[str], set[str]]:
    out = Tailored()
    problems: list[str] = []
    seen: set[str] = set()
    current: str | None = None
    role: str | None = None
    buf: dict[str, list[str]] = {s: [] for s in SECTIONS}
    ids = {r.id for r in base.roles}
    for line in reply.splitlines():
        m = HEADING.match(line)
        if m:
            level = len(line.strip()) - len(line.strip().lstrip("#"))
            text = m.group(1).strip()
            if level >= 3 and current == "Experience":
                rid = text.split()[0].casefold() if text else ""
                if rid not in ids:
                    problems.append(f"Experience: {text!r} is not a role id in resume.yaml ({', '.join(ids)}).")
                    role = None
                elif rid in out.experience:
                    problems.append(f"Experience: role {rid} appears twice.")
                    role = None
                else:
                    out.experience[rid] = []
                    role = rid
                continue
            name = next((s for s in SECTIONS if text.casefold() == s.casefold()), None)
            if name is None:
                problems.append(f"Unexpected heading: {text!r}. Use only {', '.join(SECTIONS)}.")
                current = None
            elif name in seen:
                problems.append(f"Heading {name} appears twice.")
                current = None
            else:
                seen.add(name)
                current, role = name, None
            continue
        if current == "Experience":
            if role is not None and (it := ITEM.match(line)):
                out.experience[role].append(it.group(2).strip())
            elif line.strip() and role is None:
                problems.append("Experience: text before the first ### role heading.")
        elif current is not None:
            buf[current].append(line)
    out.summary = "\n".join(buf["Summary"]).strip()
    out.letter = "\n".join(buf["Cover letter"]).strip()
    out.gaps = "\n".join(buf["Gaps"]).strip()
    return out, problems, seen


def check_tailored(reply: str, bank: StoryBank, base: BaseResume) -> tuple[list[str], Tailored]:
    """Return (problems, parsed reply). An empty problem list means it passed."""
    t, problems, seen = _split(reply, base)
    for name in SECTIONS:
        empty = {"Summary": t.summary, "Cover letter": t.letter, "Gaps": t.gaps}.get(name, "x")
        if name not in seen or not empty:
            problems.append(f"Missing section: {name}.")
    if any(p.startswith("Missing section") for p in problems):
        return problems, t

    for cited in sorted(set(CITATION.findall(reply)) - set(bank.lines)):
        problems.append(f"The reply cites {cited}, which is not in the story bank.")

    if not CITATION.search(t.summary):
        problems.append("Summary cites no story-bank line.")

    for r in base.roles:
        bullets = t.experience.get(r.id)
        if bullets is None:
            problems.append(f"Experience: role {r.id} is missing. Every role in resume.yaml gets 1 to 5 bullets.")
            continue
        if not BULLETS_PER_ROLE[0] <= len(bullets) <= BULLETS_PER_ROLE[1]:
            problems.append(f"Experience {r.id}: {len(bullets)} bullets; use 1 to 5.")
        for i, b in enumerate(bullets, start=1):
            cited = CITATION.findall(b)
            where = f"Experience {r.id}, bullet {i}"
            if not cited:
                problems.append(f"{where} cites no story-bank line.")
                continue
            if not CITATION.sub("", b).strip(" .,;:-"):
                problems.append(f"{where} is only a citation.")
            if any(c not in bank.lines for c in cited):
                continue
            foreign = [c for c in cited if c not in r.lines]
            if foreign:
                problems.append(f"{where} cites {', '.join(foreign)}, which belongs to another role.")
                continue
            extra = (numbers_in(b) - bank.numbers(cited)) | (_reply_idents(b, bank) - bank.idents(cited))
            if extra:
                problems.append(
                    f"{where} has {', '.join(sorted(extra))}, not in the line it cites ({', '.join(cited)})."
                )

    words = len(re.findall(r"\S+", t.letter))
    if not LETTER_WORDS[0] <= words <= LETTER_WORDS[1]:
        problems.append(f"Cover letter: {words} words; aim for about 250 ({LETTER_WORDS[0]} to {LETTER_WORDS[1]}).")

    invented = (_reply_numbers(reply) - bank.numbers()) | (_reply_idents(reply, bank) - bank.idents())
    if invented:
        problems.append(
            f"The reply has number {', '.join(sorted(invented))}, which is not in the story bank. "
            "Rejected: the tool never invents experience."
        )
    spelled = _word_numbers(reply) - _word_numbers(" ".join(bank.lines.values()))
    if spelled:
        problems.append(
            f"The reply uses {', '.join(sorted(spelled))} as a number or a size. Remove it, or use only "
            "figures from the story bank, written as digits."
        )
    return problems, t


# --- step 3: render ------------------------------------------------------------------------------------


def _clean(text: str) -> str:
    """Drop citations and the spaces they leave behind."""
    text = CITATION.sub("", text)
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def _fixed_lines(items: tuple[str, ...], bank: StoryBank) -> list[str]:
    return [bank.lines[s] if s in bank.lines else s for s in items]


def render_markdown(t: Tailored, bank: StoryBank, base: BaseResume) -> str:
    out = [f"# {base.name}", " · ".join(base.contact), "", _clean(t.summary), "", "## Experience"]
    for r in base.roles:
        head = f"**{r.title}**, {r.org}"
        tail = " · ".join(x for x in (r.where, r.dates) if x)
        out += ["", head + (f" · {tail}" if tail else "")]
        out += [f"- {_clean(b)}" for b in t.experience.get(r.id, [])]
    if base.education:
        out += ["", "## Education", *(f"- {x}" for x in _fixed_lines(base.education, bank))]
    if base.also:
        out += ["", "## Also", *(f"- {x}" for x in _fixed_lines(base.also, bank))]
    if base.skills:
        out += ["", "## Skills", ", ".join(base.skills)]
    return "\n".join(out).strip() + "\n"


def render_letter(t: Tailored, base: BaseResume) -> str:
    sign = base.sign_off or " · ".join((base.name, *base.contact))
    return f"{_clean(t.letter)}\n\n{sign}\n"


PRINT_CSS = """
@page { size: Letter; margin: 0.6in 0.65in; }
:root { --ink:#16130f; --muted:#5b554d; --rule:#d9d3ca; --accent:#ff5a1f; }
* { box-sizing: border-box; }
body { margin: 0; background: #fff; color: var(--ink); font: 10.5pt/1.42 "Helvetica Neue", Arial, sans-serif; }
main { max-width: 7.2in; margin: 0 auto; padding: 0.4in 0; }
h1 { font-size: 21pt; margin: 0; letter-spacing: -0.01em; }
.contact { color: var(--muted); margin: 2pt 0 10pt; }
.summary { margin: 0 0 8pt; }
h2 { font-size: 9.5pt; text-transform: uppercase; letter-spacing: 0.08em; color: var(--accent);
     border-bottom: 1px solid var(--rule); padding-bottom: 2pt; margin: 12pt 0 4pt; }
.role { margin: 7pt 0 0; break-inside: avoid; }
.role-head { display: flex; justify-content: space-between; gap: 12pt; }
.role-head span { color: var(--muted); white-space: nowrap; }
ul { margin: 2pt 0 0; padding-left: 14pt; }
li { margin: 1pt 0; }
@media screen and (max-width: 640px) { main { padding: 16px; } .role-head { flex-direction: column; gap: 0; } }
"""


def render_html(t: Tailored, bank: StoryBank, base: BaseResume) -> str:
    e = html.escape
    parts = [
        f"<h1>{e(base.name)}</h1>",
        f'<p class="contact">{e(" · ".join(base.contact))}</p>',
        f'<p class="summary">{e(_clean(t.summary))}</p>',
        "<h2>Experience</h2>",
    ]
    for r in base.roles:
        tail = " · ".join(x for x in (r.where, r.dates) if x)
        items = "".join(f"<li>{e(_clean(b))}</li>" for b in t.experience.get(r.id, []))
        parts.append(
            f'<section class="role"><div class="role-head"><strong>{e(r.title)}, {e(r.org)}</strong>'
            f"<span>{e(tail)}</span></div><ul>{items}</ul></section>"
        )
    for heading, items in (("Education", base.education), ("Also", base.also)):
        if items:
            lis = "".join(f"<li>{e(x)}</li>" for x in _fixed_lines(items, bank))
            parts.append(f"<h2>{heading}</h2><ul>{lis}</ul>")
    if base.skills:
        parts.append(f"<h2>Skills</h2><p>{e(', '.join(base.skills))}</p>")
    body = "\n".join(parts)
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{e(base.name)} — Résumé</title><style>{PRINT_CSS}</style></head>"
        f"<body><main>\n{body}\n</main></body></html>\n"
    )
