"""Write ranked.csv and one self-contained HTML report (fonts and styles inside the file)."""

from __future__ import annotations

import base64
import csv
import io
from html import escape
from importlib import resources
from urllib.parse import urlparse

from .rubric import Rubric
from .scoring import Scored

FONT_FILES = (
    ("Bricolage Grotesque", "bricolage-grotesque-latin-wght-normal.woff2"),
    ("Geist", "geist-latin-wght-normal.woff2"),
    ("Geist Mono", "geist-mono-latin-wght-normal.woff2"),
)


def _asset(name: str) -> bytes:
    return (resources.files("resume_pipeline") / "assets" / name).read_bytes()


def fonts_css() -> str:
    """The three brand typefaces as base64, so the report works with no network."""
    out = []
    for family, file in FONT_FILES:
        data = base64.b64encode(_asset(f"fonts/{file}")).decode("ascii")
        out.append(
            f"@font-face{{font-family:'{family}';font-weight:100 900;font-display:swap;"
            f"src:url(data:font/woff2;base64,{data}) format('woff2');}}"
        )
    return "\n".join(out)


def safe_cell(value: object) -> str:
    """Stop a spreadsheet from running a lead's text as a formula (=, +, -, @ at the start)."""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def safe_url(url: str) -> str | None:
    """Only plain web links become clickable. javascript:, data: and the rest do not."""
    try:
        parts = urlparse(url.strip())
    except ValueError:
        return None
    if parts.scheme in ("http", "https") and parts.netloc:
        return url.strip()
    return None


def ranked_csv(results: list[Scored]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(
        [
            "rank",
            "status",
            "score",
            "title",
            "company",
            "location",
            "salary",
            "url",
            "reasons",
            "incomplete",
            "row",
        ]
    )
    for s in results:
        w.writerow(
            [
                s.rank if s.rank is not None else "",
                "knocked out" if s.knocked_out else ("ranked on incomplete data" if s.incomplete else "ranked"),
                "" if s.knocked_out else f"{s.score:g}",
                safe_cell(s.lead.title),
                safe_cell(s.lead.company),
                safe_cell(s.lead.location),
                safe_cell(s.lead.salary),
                safe_cell(s.lead.url),
                "Reasons: " + " | ".join(s.reasons),
                safe_cell(", ".join(s.incomplete)),
                s.lead.row,
            ]
        )
    return buf.getvalue()


def _row_html(s: Scored) -> str:
    link = safe_url(s.lead.url)
    title = escape(s.lead.title or "(no title)")
    head = f'<a href="{escape(link, quote=True)}" rel="noopener noreferrer">{title}</a>' if link else title
    meta = " · ".join(escape(x) for x in (s.lead.company, s.lead.location, s.lead.salary) if x)
    badge = ""
    if s.knocked_out:
        badge = '<span class="tag out">knocked out</span>'
    elif s.incomplete:
        badge = f'<span class="tag warn">incomplete: {escape(", ".join(s.incomplete))}</span>'
    score = "" if s.knocked_out else f'<span class="score">{s.score:g}</span>'
    rank = f'<span class="rank">{s.rank}</span>' if s.rank is not None else '<span class="rank">–</span>'
    reasons = "".join(f"<li>{escape(r)}</li>" for r in s.reasons)
    return (
        f'<li class="lead{" dead" if s.knocked_out else ""}">'
        f'<div class="top">{rank}<div class="who"><h3>{head}</h3>'
        f'<p class="meta">{meta}</p></div>{score}</div>'
        f'{badge}<ul class="why">{reasons}</ul></li>'
    )


def build_report(
    results: list[Scored],
    rubric: Rubric,
    *,
    title: str = "Today's shortlist",
    embed_fonts: bool = True,
    sample: bool = False,
) -> str:
    live = [s for s in results if not s.knocked_out]
    dead = [s for s in results if s.knocked_out]
    n = rubric.shortlist_size
    short, rest = live[:n], live[n:]
    partial = [s for s in live if s.incomplete]
    css = _asset("brand.css").decode("utf-8")
    fonts = fonts_css() if embed_fonts else ""

    def section(heading: str, rows: list[Scored], note: str = "") -> str:
        if not rows:
            return ""
        items = "".join(_row_html(s) for s in rows)
        return f"<section><h2>{escape(heading)} <span>{len(rows)}</span></h2>{note}<ol>{items}</ol></section>"

    if results:
        note = (
            f'<p class="note">{len(partial)} of {len(live)} ranked leads were scored on incomplete '
            "data (a missing salary, location or description). They are marked, and their true "
            "rank could be higher or lower.</p>"
            if partial
            else ""
        )
        body = section("Shortlist", short, note) + section("Everything else", rest) + section("Knocked out", dead)
        if not live:
            body = '<p class="empty">Every lead was knocked out. The reasons are below.</p>' + body
    else:
        body = '<p class="empty">The CSV had no rows to score.</p>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
{fonts}
{css}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--ground);color:var(--chalk);font-family:var(--body);line-height:1.5}}
header{{display:flex;align-items:center;gap:12px;padding:16px;border-bottom:1px solid var(--line)}}
header a{{display:flex;align-items:center;gap:12px;color:var(--chalk);text-decoration:none}}
.tile{{display:grid;place-items:center;width:36px;height:36px;border-radius:var(--radius-s);
background:var(--signal);color:var(--signal-ink);font-family:var(--display);font-weight:800}}
main{{max-width:860px;margin:0 auto;padding:24px 16px 64px}}
h1{{font-family:var(--display);font-size:clamp(1.9rem,6vw,3rem);line-height:1.05;margin:0 0 8px}}
.sub{{color:var(--muted);margin:0 0 24px}}
h2{{font-family:var(--display);font-size:1.4rem;margin:32px 0 8px}}
h2 span{{font-family:var(--mono);font-size:.9rem;color:var(--muted);font-weight:400}}
ol{{list-style:none;margin:0;padding:0;display:grid;gap:12px}}
.lead{{background:var(--panel);border:1px solid var(--line-2);border-radius:var(--radius-m);padding:14px 16px}}
.lead.dead{{opacity:.85}}
.top{{display:flex;gap:12px;align-items:flex-start}}
.who{{flex:1;min-width:0}}
h3{{margin:0;font-size:1.05rem;font-weight:600;overflow-wrap:anywhere}}
h3 a{{color:var(--chalk);text-decoration-color:var(--signal);text-underline-offset:3px}}
a:focus-visible{{outline:3px solid var(--signal);outline-offset:3px}}
.meta{{margin:2px 0 0;color:var(--muted);font-size:.9rem;overflow-wrap:anywhere}}
.rank{{font-family:var(--mono);color:var(--muted);min-width:1.6em}}
.score{{font-family:var(--display);font-weight:800;font-size:1.6rem;color:var(--go)}}
.tag{{display:inline-block;margin-top:8px;font-family:var(--mono);font-size:.78rem;padding:2px 8px;
border-radius:99px;border:1px solid var(--line-2)}}
.tag.out{{color:var(--muted)}}.tag.warn{{color:var(--signal);border-color:var(--signal)}}
.why{{margin:8px 0 0;padding-left:18px;color:var(--muted);font-size:.9rem;overflow-wrap:anywhere}}
.note,.empty{{color:var(--muted)}}
footer{{color:var(--muted);font-size:.85rem;border-top:1px solid var(--line);padding:16px;text-align:center}}
footer a{{color:var(--chalk)}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important;transition:none!important}}}}
</style>
</head>
<body>
<header><a href="https://dakshdua.ca"><span class="tile" aria-hidden="true">DD</span><span>dakshdua.ca</span></a></header>
<main>
<h1>{escape(title)}</h1>
<p class="sub">{len(results)} leads read. {len(live)} ranked, {len(dead)} knocked out. Scores come from the rubric, not a model. Rank depends on how well the rubric is tuned.</p>
{body}
</main>
<footer>{"Sample data is invented. " if sample else ""}Built in Calgary by <a href="https://dakshdua.ca">Daksh Dua</a>. MIT licence.</footer>
</body>
</html>
"""
