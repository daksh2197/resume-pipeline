import csv
from pathlib import Path

from helpers import lead, rubric
from resume_pipeline.cli import pack_main, screen_main
from resume_pipeline.leads import read_leads
from resume_pipeline.report import build_report, ranked_csv, safe_cell, safe_url
from resume_pipeline.rubric import load_rubric
from resume_pipeline.scoring import score_all

BAD_TOKENS = ("NaN", "Infinity", "undefined", "-0<", ">-0 ")


def test_the_sample_report_matches_the_golden_file():
    r = load_rubric("samples/rubric.yaml")
    html = build_report(score_all(read_leads("samples/jobs.csv", r), r), r, embed_fonts=False, sample=True)
    assert html == Path("tests/golden/report.html").read_text(encoding="utf-8")


def test_the_real_report_carries_its_fonts_inside_the_file():
    r = rubric()
    html = build_report(score_all([lead()], r), r)
    assert html.count("data:font/woff2;base64,") == 3
    assert "https://fonts.googleapis.com" not in html and "<script" not in html


def test_shortlist_comes_first_then_the_rest_then_knocked_out():
    r = rubric(shortlist_size=1, knockouts=["bad"])
    leads = [
        lead("Technical Account Manager", row=1),
        lead("Other", row=2),
        lead(description="bad", row=3),
    ]
    html = build_report(score_all(leads, r), r)
    assert html.index(">Shortlist") < html.index(">Everything else") < html.index(">Knocked out")


def test_incomplete_rows_are_named_in_the_report():
    r = rubric()
    html = build_report(score_all([lead(salary="")], r), r)
    assert "incomplete: salary" in html and "1 of 1 ranked leads were scored on incomplete" in html


def test_hostile_text_is_escaped_and_bad_links_are_not_clickable():
    r = rubric()
    evil = lead(
        title="Technical Account Manager <script>alert(1)</script>",
        company='"><img src=x onerror=alert(1)>',
        url="javascript:alert(1)",
    )
    html = build_report(score_all([evil], r), r)
    assert "<script>alert" not in html and "<img src=x" not in html
    assert "&lt;script&gt;" in html and 'href="javascript' not in html


def test_only_http_links_are_safe():
    assert safe_url("https://example.com/a?b=1") == "https://example.com/a?b=1"
    for bad in (
        "javascript:alert(1)",
        "data:text/html,x",
        "//evil.example",
        "ftp://x.y",
        "",
        "http://",
        "[::1",
    ):
        assert safe_url(bad) is None


def test_spreadsheet_formulas_in_lead_text_are_defused_in_the_csv():
    for start in "=+-@":
        assert safe_cell(f"{start}HYPERLINK(1)").startswith("'")
    r = rubric()
    out = ranked_csv(score_all([lead(title="=cmd|' /C calc'!A0", company="@SUM(1)")], r))
    rows = list(csv.reader(out.splitlines()))
    assert rows[1][3].startswith("'=") and rows[1][4].startswith("'@")
    assert rows[1][8].startswith("Reasons: ")  # generated text never starts with + or =


def test_an_empty_or_all_knocked_out_list_still_makes_a_sensible_report():
    r = rubric(knockouts=["x"])
    assert "no rows to score" in build_report([], r)
    all_out = build_report(score_all([lead(description="x")], r), r)
    assert "Every lead was knocked out" in all_out


def test_nothing_alarming_reaches_the_screen_for_odd_numbers():
    r = rubric(nice_to_haves=[{"name": "x", "match": ["x"], "points": 0.1}] * 3, salary={"floor": 0})
    html = build_report(score_all([lead(description="x", salary="999999999999999999")], r), r)
    for token in ("NaN", "Infinity", "undefined"):
        assert token not in html


def test_screen_writes_both_files_and_says_what_it_did(tmp_path, capsys):
    code = screen_main(["samples/jobs.csv", "--rubric", "samples/rubric.yaml", "--out", str(tmp_path), "--sample"])
    out = capsys.readouterr().out
    assert code == 0
    assert "20 leads: 9 ranked, 11 knocked out." in out
    assert (tmp_path / "ranked.csv").exists() and (tmp_path / "report.html").exists()
    rows = list(csv.DictReader((tmp_path / "ranked.csv").open(encoding="utf-8")))
    assert [r["rank"] for r in rows[:9]] == [str(i) for i in range(1, 10)]


def test_screen_is_repeatable(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        assert screen_main(["samples/jobs.csv", "--rubric", "samples/rubric.yaml", "--out", str(d)]) == 0
    assert (a / "ranked.csv").read_bytes() == (b / "ranked.csv").read_bytes()
    assert (a / "report.html").read_bytes() == (b / "report.html").read_bytes()


def test_screen_errors_are_one_plain_line_not_a_traceback(tmp_path, capsys):
    assert screen_main(["nope.csv", "--rubric", "samples/rubric.yaml"]) == 2
    assert screen_main(["samples/jobs.csv", "--rubric", "nope.yaml"]) == 2
    bad = tmp_path / "r.yaml"
    bad.write_text("columns: {title: Nope}\n")
    assert screen_main(["samples/jobs.csv", "--rubric", str(bad)]) == 2
    err = capsys.readouterr().err
    assert err.count("error:") == 3 and "Traceback" not in err and "Nope" in err


def test_pack_builds_a_prompt_and_checks_a_reply(tmp_path, capsys):
    prompt = tmp_path / "prompt.md"
    assert pack_main(["samples/posting.txt", "--story-bank", "samples/story-bank.md", "--out", str(prompt)]) == 0
    assert "S4: Ran 8 executive briefings" in prompt.read_text(encoding="utf-8")
    assert pack_main(["--story-bank", "samples/story-bank.md", "--check", "samples/sample-reply.md"]) == 0
    bad = tmp_path / "bad.md"
    bad.write_text(
        Path("samples/sample-reply.md").read_text(encoding="utf-8").replace("12 enterprise", "99 enterprise")
    )
    assert pack_main(["--story-bank", "samples/story-bank.md", "--check", str(bad)]) == 1
    assert "Pack rejected" in capsys.readouterr().err
    assert pack_main(["--story-bank", "samples/story-bank.md"]) == 2


def test_the_n8n_workflow_is_wired_end_to_end():
    import json

    flow = json.loads(Path("n8n/shortlist.workflow.json").read_text(encoding="utf-8"))
    names = {n["name"] for n in flow["nodes"]}
    assert len(names) == len(flow["nodes"])
    for source, wiring in flow["connections"].items():
        assert source in names
        for branch in wiring["main"]:
            assert all(link["node"] in names for link in branch)
    command = next(n for n in flow["nodes"] if n["name"] == "Run screen")["parameters"]["command"]
    assert "screen jobs.csv --rubric rubric.yaml" in command
