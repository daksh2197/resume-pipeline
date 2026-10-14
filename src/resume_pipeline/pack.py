"""The application pack: build the prompt, then check whatever comes back.

The tool never writes your experience. It assembles a prompt from your own story
bank, and it checks the reply before you use it. A reply is rejected when:

* a section is missing, or there are not five bullets and three questions,
* a bullet does not cite a story-bank line like [S2], or cites one that is not there,
* any number in the pack (bullets, fit, note, questions) is not in the story bank,
* a bullet has a number that is not in the line it cites.

What it cannot check: wording that sounds more senior than the line it came from,
or a skill the story bank never mentions. Read the pack before you send it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

STORY_LINE = re.compile(r"^\s*(?:[-*]\s*)?\[?(S\d+)\]?\s*[:.)-]\s*(.+?)\s*$")
CITATION = re.compile(r"\[(S\d+)\]")
# 94, 2.7, 1,200, 31400. A trailing % or M or k is dropped on purpose.
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
SECTIONS = ("Fit", "Gaps", "Bullets", "Note", "Questions")
NOTE_WORDS = (100, 140)  # "120 words" asked for; this is the tolerance


class PackError(ValueError):
    """Bad input to the pack builder (empty posting, empty story bank)."""


@dataclass(frozen=True)
class StoryBank:
    lines: dict[str, str]  # "S1" -> text

    def numbers(self, ids: list[str] | None = None) -> set[str]:
        keys = ids if ids is not None else list(self.lines)
        found: set[str] = set()
        for k in keys:
            found |= numbers_in(self.lines.get(k, ""))
        return found


def numbers_in(text: str) -> set[str]:
    """Every number in `text`, commas removed, citations like [S2] ignored."""
    cleaned = CITATION.sub(" ", text)
    cleaned = re.sub(r"^\s*\d+[.)]\s+", "", cleaned, flags=re.MULTILINE)  # "1." list markers
    return {m.group(0).replace(",", "").rstrip(".") for m in NUMBER.finditer(cleaned)}


def parse_story_bank(text: str) -> StoryBank:
    """Lines look like `S1: Led the migration of 40 accounts.` Everything else is ignored."""
    lines: dict[str, str] = {}
    for raw in text.splitlines():
        m = STORY_LINE.match(raw)
        if m and m.group(1) not in lines:
            lines[m.group(1)] = m.group(2)
    if not lines:
        raise PackError(
            "The story bank has no lines like `S1: something you did`. "
            "Number each line S1, S2, S3 so every bullet can cite its source."
        )
    return StoryBank(lines)


def build_prompt(posting: str, bank: StoryBank) -> str:
    if not posting.strip():
        raise PackError("The posting is empty.")
    story = "\n".join(f"{k}: {v}" for k, v in bank.lines.items())
    return f"""You are helping me prepare one job application. Use ONLY the story bank below as evidence
about me. Do not invent experience, employers, tools, numbers or dates. If the posting asks for
something the story bank does not show, say so under Gaps.

Reply in exactly these five sections, with these headings:

## Fit
Two to four sentences on how well I fit, with the reasons. Cite story-bank lines like [S2].

## Gaps
What the posting asks for that my story bank does not show. Plain, no spin.

## Bullets
Exactly five bullets for my application. Each bullet ends with the story-bank line it came from,
like [S3]. Use only numbers that appear in that line.

## Note
A note to the hiring team of about 120 words, in my voice: short sentences, no hype.

## Questions
Exactly three questions I should ask them.

Every number you write must appear in the story bank. Do not add any other numbers.

--- STORY BANK ---
{story}

--- POSTING ---
{posting.strip()}
"""


def _split_sections(reply: str) -> dict[str, str]:
    parts = re.split(r"^\s*#{1,3}\s*(\w+)[^\n]*$", reply, flags=re.MULTILINE)
    out: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        name = parts[i].capitalize()
        if name in SECTIONS and name not in out:
            out[name] = parts[i + 1].strip()
    return out


def _items(block: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^\s*(?:[-*•]|\d+[.)])\s+(.+)$", block, re.MULTILINE)]


def check_pack(reply: str, bank: StoryBank) -> list[str]:
    """Return a list of problems. An empty list means the pack passed."""
    problems: list[str] = []
    sections = _split_sections(reply)
    for name in SECTIONS:
        if name not in sections or not sections[name]:
            problems.append(f"Missing section: {name}.")
    if problems:
        return problems

    bullets = _items(sections["Bullets"])
    if len(bullets) != 5:
        problems.append(f"Bullets: expected 5, found {len(bullets)}.")
    for i, b in enumerate(bullets, start=1):
        cited = CITATION.findall(b)
        if not cited:
            problems.append(f"Bullet {i} cites no story-bank line (end it with something like [S1]).")
            continue
        unknown = [c for c in cited if c not in bank.lines]
        if unknown:
            problems.append(f"Bullet {i} cites {', '.join(unknown)}, which is not in the story bank.")
            continue
        extra = numbers_in(b) - bank.numbers(cited)
        if extra:
            problems.append(
                f"Bullet {i} has {', '.join(sorted(extra))}, not in the line it cites ({', '.join(cited)})."
            )

    questions = _items(sections["Questions"])
    if len(questions) != 3:
        problems.append(f"Questions: expected 3, found {len(questions)}.")

    words = len(re.findall(r"\S+", sections["Note"]))
    if not NOTE_WORDS[0] <= words <= NOTE_WORDS[1]:
        problems.append(f"Note: {words} words; aim for about 120 ({NOTE_WORDS[0]} to {NOTE_WORDS[1]}).")

    allowed = bank.numbers()
    for name in SECTIONS:
        invented = numbers_in(sections[name]) - allowed
        if invented:
            problems.append(
                f"{name}: number {', '.join(sorted(invented))} is not in the story bank. "
                "The pack is rejected: the tool never invents experience."
            )
    return problems
