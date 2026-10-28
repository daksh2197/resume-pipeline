import pytest

from resume_pipeline.cli import tailor_main
from resume_pipeline.pack import parse_story_bank
from resume_pipeline.tailor import (
    TailorError,
    build_tailor_prompt,
    check_tailored,
    parse_resume,
    rank_lines,
    render_html,
    render_letter,
    render_markdown,
)

BANK_TEXT = open("samples/story-bank.md", encoding="utf-8").read()
RESUME_TEXT = open("samples/resume.yaml", encoding="utf-8").read()
POSTING = open("samples/posting.txt", encoding="utf-8").read()
GOOD = open("samples/sample-tailor-reply.md", encoding="utf-8").read()


@pytest.fixture
def bank():
    return parse_story_bank(BANK_TEXT)


@pytest.fixture
def base(bank):
    return parse_resume(RESUME_TEXT, bank)


def test_the_base_resume_is_read_with_its_roles_and_lines(base):
    assert [r.id for r in base.roles] == ["northwind", "cedar"]
    assert base.role_of["S3"] == "cedar"
    assert base.contact[-1] == "Calgary, AB"


@pytest.mark.parametrize(
    "change, message",
    [
        (("lines: [S3, S5]", "lines: [S3, S9]"), "S9, which is not in the story bank"),
        (("lines: [S3, S5]", "lines: [S3, S1]"), "S1 is listed under both"),
        (("id: cedar", "id: northwind"), "used twice"),
        (("title: Support Engineer", "title: ''"), "needs a title"),
    ],
)
def test_a_bad_base_resume_is_refused_with_a_plain_message(bank, change, message):
    with pytest.raises(TailorError, match=message):
        parse_resume(RESUME_TEXT.replace(*change), bank)


def test_lines_are_ranked_by_words_shared_with_the_posting(bank):
    matches, missing = rank_lines(POSTING, bank)
    assert matches[0].line == "S1"
    assert "kubernetes" in missing
    assert "executive" not in " ".join(missing)  # "executives" in the posting matches "executive" in S4


def test_ranking_is_repeatable(bank):
    assert rank_lines(POSTING, bank) == rank_lines(POSTING, bank)


def test_the_prompt_names_each_role_and_what_it_may_cite(bank, base):
    prompt = build_tailor_prompt(POSTING, bank, base)
    assert "### northwind" in prompt and "Cite only: S1, S2, S4" in prompt
    assert "Do not invent" in prompt and "kubernetes" in prompt
    assert prompt.index("S1:") < prompt.index("S5:")


def test_a_good_reply_passes(bank, base):
    problems, t = check_tailored(GOOD, bank, base)
    assert problems == []
    assert len(t.experience["northwind"]) == 3


def test_a_bullet_citing_another_roles_line_is_rejected(bank, base):
    bad = GOOD.replace("flagged drift [S3]", "flagged drift [S1]")
    problems, _ = check_tailored(bad, bank, base)
    assert any("cedar, bullet 1 cites S1, which belongs to another role" in p for p in problems)


def test_an_invented_number_in_the_cover_letter_is_rejected(bank, base):
    bad = GOOD.replace("That is the job I do now.", "That is the job I have done for 9 years.")
    problems, _ = check_tailored(bad, bank, base)
    assert any("number 9" in p for p in problems)


def test_a_bullet_with_a_number_from_another_line_is_rejected(bank, base):
    bad = GOOD.replace("with a 93% renewal rate [S1]\n- Ran", "with a 93% renewal rate and 400 checks [S1]\n- Ran")
    problems, _ = check_tailored(bad, bank, base)
    assert any("northwind, bullet 1 has 400" in p for p in problems)


def test_a_missing_role_or_unknown_role_heading_is_rejected(bank, base):
    bad = GOOD.replace("### cedar", "### acme")
    problems, _ = check_tailored(bad, bank, base)
    assert any("'acme' is not a role id" in p for p in problems)
    assert any("role cedar is missing" in p for p in problems)


def test_a_missing_section_stops_the_check(bank, base):
    bad = GOOD.split("## Gaps")[0]
    problems, _ = check_tailored(bad, bank, base)
    assert problems == ["Missing section: Gaps."]


def test_a_short_cover_letter_is_rejected(bank, base):
    head, rest = GOOD.split("## Cover letter")
    bad = head + "## Cover letter\nHello team. I would like the job.\n\n## Gaps" + rest.split("## Gaps")[1]
    problems, _ = check_tailored(bad, bank, base)
    assert any(p.startswith("Cover letter:") for p in problems)


def test_render_takes_titles_and_dates_from_the_base_and_drops_citations(bank, base):
    _, t = check_tailored(GOOD, bank, base)
    md = render_markdown(t, bank, base)
    assert "**Technical Account Manager**, Northwind Sample Co. · Remote · 2021 – present" in md
    assert "[S" not in md
    page = render_html(t, bank, base)
    assert "<title>Sam Sample — Résumé</title>" in page and "[S" not in page
    letter = render_letter(t, base)
    assert letter.startswith("Hello Tamarack Cloud team,") and letter.rstrip().endswith("Calgary, AB")


def test_hostile_text_is_escaped_in_the_html(bank, base):
    _, t = check_tailored(GOOD.replace("flagged drift", "flagged <script>x</script> drift"), bank, base)
    assert "<script>" not in render_html(t, bank, base)


def test_tailor_cli_builds_checks_and_renders(tmp_path, capsys):
    common = ["--story-bank", "samples/story-bank.md", "--resume", "samples/resume.yaml", "--out", str(tmp_path)]
    assert tailor_main(["samples/posting.txt", *common]) == 0
    assert (tmp_path / "prompt.md").exists()
    assert tailor_main(["--check", "samples/sample-tailor-reply.md", *common]) == 0
    assert not (tmp_path / "resume.html").exists()
    assert tailor_main(["--render", "samples/sample-tailor-reply.md", *common]) == 0
    for name in ("resume.html", "resume.md", "cover-letter.md"):
        assert (tmp_path / name).exists()
    bad = tmp_path / "bad.md"
    bad.write_text(GOOD.replace("[S3]", "[S1]"), encoding="utf-8")
    (tmp_path / "resume.html").unlink()
    assert tailor_main(["--render", str(bad), *common]) == 1
    assert not (tmp_path / "resume.html").exists()
    assert "Reply rejected" in capsys.readouterr().err
