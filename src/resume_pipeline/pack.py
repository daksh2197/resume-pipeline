"""The application pack: build the prompt, then check whatever comes back.

The tool never writes your experience. It assembles a prompt from your own story
bank, and it checks the reply before you use it. A reply is rejected when:

* a section is missing, or there are not five bullets and three questions,
* a bullet does not cite a story-bank line like [S2], or cites one that is not there,
* any number anywhere in the reply (every section, any extra text) is not in the story bank,
* a number written as a word ("twelve", "half") is not a word the story bank uses too,
* a citation like [S9] points at a line that is not in the story bank,
* a bullet has a number that is not in the line it cites,
* a heading appears twice, or is not one of the five.

What it cannot check: units (93% renewal can become "93 accounts" and still pass, because only the
digits are compared), wording that sounds more senior than the line it came from, or a skill the
story bank never mentions. Read the pack before you send it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

STORY_LINE = re.compile(r"^\s*(?:[-*]\s*)?\[?(S\d+)\]?\s*[:.)\u2013\u2014-]\s*(.+?)\s*$")
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


WORD_NUMBERS = re.compile(
    r"(?<![A-Za-z])(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"hundred|thousand|million|billion|half|dozen|double|doubled|triple|tripled|twice)(?![A-Za-z])"
    r"|[\u00bc-\u00be\u2150-\u215e\u2460-\u2473]",
    re.IGNORECASE,
)
HEADING = re.compile(r"^\s*#{1,6}\s*(.*?)\s*#*\s*$")
ITEM = re.compile(r"^\s*(?:[-*\u2022]|(\d+)[.)])\s+(.+)$")


def _split_sections(reply: str) -> tuple[dict[str, str], list[str]]:
    """Split on headings. Returns the five sections and a list of heading problems."""
    sections: dict[str, list[str]] = {}
    problems: list[str] = []
    current: str | None = None
    for line in reply.splitlines():
        m = HEADING.match(line)
        if m:
            name = m.group(1).split()[0].capitalize() if m.group(1).split() else ""
            if name not in SECTIONS:
                problems.append(f"Unexpected heading: {m.group(1)!r}. Use only {', '.join(SECTIONS)}.")
                current = None
            elif name in sections:
                problems.append(f"Heading {name} appears twice.")
                current = None
            else:
                sections[name] = []
                current = name
        elif current is not None:
            sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}, problems


def _items(block: str) -> list[str]:
    return [m.group(2).strip() for line in block.splitlines() if (m := ITEM.match(line))]


def _reply_numbers(reply: str) -> set[str]:
    """Every number in the whole reply. A leading "1." only counts as a list marker when it is the next
    number in sequence, so "77. That was it." is still read as 77."""
    found: set[str] = set()
    expected = 1
    for line in reply.splitlines():
        m = re.match(r"^\s*(\d+)[.)]\s+(.*)$", line)
        if m and int(m.group(1)) == expected:
            expected += 1
            line = m.group(2)
        elif not ITEM.match(line):
            expected = 1
        found |= numbers_in(line)
    return found


def _word_numbers(text: str) -> set[str]:
    return {m.group(0).casefold() for m in WORD_NUMBERS.finditer(text)}


def check_pack(reply: str, bank: StoryBank) -> list[str]:
    """Return a list of problems. An empty list means the pack passed."""
    problems: list[str] = []
    sections, heading_problems = _split_sections(reply)
    problems += heading_problems
    for name in SECTIONS:
        if name not in sections or not sections[name]:
            problems.append(f"Missing section: {name}.")
    if any(p.startswith("Missing section") for p in problems):
        return problems

    for cited in sorted(set(CITATION.findall(reply)) - set(bank.lines)):
        problems.append(f"The reply cites {cited}, which is not in the story bank.")

    bullets = _items(sections["Bullets"])
    if len(bullets) != 5:
        problems.append(f"Bullets: expected 5, found {len(bullets)}.")
    for i, b in enumerate(bullets, start=1):
        cited = CITATION.findall(b)
        if not cited:
            problems.append(f"Bullet {i} cites no story-bank line (end it with something like [S1]).")
            continue
        if not CITATION.sub("", b).strip(" .,;:-"):
            problems.append(f"Bullet {i} is only a citation.")
        if [c for c in cited if c not in bank.lines]:
            continue  # already reported above
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

    invented = _reply_numbers(reply) - bank.numbers()
    if invented:
        problems.append(
            f"The reply has number {', '.join(sorted(invented))}, which is not in the story bank. "
            "The pack is rejected: the tool never invents experience."
        )
    bank_words = _word_numbers(" ".join(bank.lines.values()))
    spelled = _word_numbers(reply) - bank_words
    if spelled:
        problems.append(
            f"The reply uses {', '.join(sorted(spelled))} as a number. Write only numbers that are "
            "in the story bank, as digits."
        )
    return problems
