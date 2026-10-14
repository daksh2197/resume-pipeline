"""Command line: `screen` ranks a CSV, `pack` builds or checks an application pack."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .leads import LeadsError, read_leads
from .pack import PackError, build_prompt, check_pack, parse_story_bank
from .report import build_report, ranked_csv
from .rubric import RubricError, load_rubric
from .scoring import score_all


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 2


def screen_main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="screen", description="Rank a CSV of job leads against a rubric.")
    p.add_argument("leads", help="CSV file of job leads")
    p.add_argument("--rubric", required=True, help="rubric YAML file")
    p.add_argument("--out", default=".", help="folder for ranked.csv and report.html (default: here)")
    p.add_argument("--title", default="Today's shortlist")
    p.add_argument("--sample", action="store_true", help="label the report as invented sample data")
    p.add_argument("--version", action="version", version=__version__)
    args = p.parse_args(argv)

    try:
        rubric = load_rubric(args.rubric)
        leads = read_leads(args.leads, rubric)
    except (RubricError, LeadsError) as err:
        return _fail(str(err))

    results = score_all(leads, rubric)
    out = Path(args.out)
    try:
        out.mkdir(parents=True, exist_ok=True)
        (out / "ranked.csv").write_text(ranked_csv(results), encoding="utf-8", newline="")
        (out / "report.html").write_text(
            build_report(results, rubric, title=args.title, sample=args.sample), encoding="utf-8"
        )
    except OSError as err:
        return _fail(f"cannot write to {out}: {err.strerror or err}")

    live = [r for r in results if not r.knocked_out]
    partial = sum(1 for r in live if r.incomplete)
    print(f"{len(results)} leads: {len(live)} ranked, {len(results) - len(live)} knocked out.")
    if partial:
        print(f"{partial} ranked leads were scored on incomplete data (see report).")
    print(f"Wrote {out / 'ranked.csv'} and {out / 'report.html'}")
    return 0


def pack_main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="pack",
        description="Build an application-pack prompt, or check a reply against your story bank.",
    )
    p.add_argument("posting", nargs="?", help="text file with the job description (to build a prompt)")
    p.add_argument("--story-bank", required=True, help="story-bank.md with lines like `S1: ...`")
    p.add_argument("--out", default="prompt.md", help="where to write the prompt (default: prompt.md)")
    p.add_argument("--check", metavar="REPLY", help="check a reply file instead of building a prompt")
    args = p.parse_args(argv)

    try:
        bank = parse_story_bank(Path(args.story_bank).read_text(encoding="utf-8-sig"))
    except OSError as err:
        return _fail(f"cannot read the story bank: {err.strerror or err}")
    except PackError as err:
        return _fail(str(err))

    if args.check:
        try:
            reply = Path(args.check).read_text(encoding="utf-8-sig")
        except OSError as err:
            return _fail(f"cannot read the reply: {err.strerror or err}")
        problems = check_pack(reply, bank)
        if problems:
            print("Pack rejected:", file=sys.stderr)
            for line in problems:
                print(f"  - {line}", file=sys.stderr)
            return 1
        print("Pack passed: every bullet cites a story-bank line and every number is in the bank.")
        return 0

    if not args.posting:
        return _fail("give a posting file to build a prompt, or use --check REPLY")
    try:
        posting = Path(args.posting).read_text(encoding="utf-8-sig")
        prompt = build_prompt(posting, bank)
        Path(args.out).write_text(prompt, encoding="utf-8")
    except OSError as err:
        return _fail(f"{err.strerror or err}")
    except PackError as err:
        return _fail(str(err))
    print(f"Wrote {args.out}. Paste it into any assistant, save the reply, then run:")
    print(f"  uv run pack --story-bank {args.story_bank} --check reply.md")
    return 0
