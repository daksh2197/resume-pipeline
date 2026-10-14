import pytest

from resume_pipeline.pack import (
    PackError,
    build_prompt,
    check_pack,
    numbers_in,
    parse_story_bank,
)

BANK_TEXT = open("samples/story-bank.md", encoding="utf-8").read()
GOOD = open("samples/sample-reply.md", encoding="utf-8").read()


@pytest.fixture
def bank():
    return parse_story_bank(BANK_TEXT)


def test_story_bank_lines_are_read_and_comments_ignored(bank):
    assert list(bank.lines) == ["S1", "S2", "S3", "S4", "S5"]
    assert bank.lines["S2"].startswith("Built a SQL report")


def test_a_story_bank_without_numbered_lines_is_refused():
    with pytest.raises(PackError, match="S1"):
        parse_story_bank("# notes\nI did some things.\n")


def test_the_prompt_contains_the_bank_the_posting_and_the_rules(bank):
    prompt = build_prompt("Technical Account Manager at Acme.", bank)
    assert "S3: Wrote a Python script" in prompt
    assert "Technical Account Manager at Acme." in prompt
    assert "Exactly five bullets" in prompt and "Exactly three questions" in prompt
    assert "Do not invent" in prompt


def test_an_empty_posting_is_refused(bank):
    with pytest.raises(PackError):
        build_prompt("   \n", bank)


def test_a_good_pack_passes(bank):
    assert check_pack(GOOD, bank) == []


def test_a_bullet_with_an_invented_number_is_rejected(bank):
    bad = GOOD.replace("12 enterprise accounts, with a 93%", "40 enterprise accounts, with a 93%")
    problems = check_pack(bad, bank)
    assert any("Bullet 1 has 40" in p for p in problems)
    assert any("number 40 is not in the story bank" in p for p in problems)


def test_an_invented_number_in_the_note_is_rejected(bank):
    bad = GOOD.replace("Hello. I am applying", "Hello. With 25 years behind me, I am applying")
    problems = check_pack(bad, bank)
    assert any(p.startswith("Note: number 25") for p in problems)


def test_a_number_in_the_bank_but_not_in_the_cited_line_is_rejected(bank):
    bad = GOOD.replace(
        "Cut weekly account reviews from 3 hours to 45 minutes with a SQL report [S2]",
        "Cut weekly account reviews from 3 hours to 45 minutes with a SQL report [S1]",
    )
    assert any("not in the line it cites" in p for p in check_pack(bad, bank))


def test_a_bullet_without_a_citation_or_with_a_fake_one_is_rejected(bank):
    no_cite = GOOD.replace(" [S5]", "")
    assert any("Bullet 5 cites no story-bank line" in p for p in check_pack(no_cite, bank))
    fake = GOOD.replace("[S5]", "[S9]")
    assert any("S9, which is not in the story bank" in p for p in check_pack(fake, bank))


def test_wrong_counts_and_missing_sections_are_reported(bank):
    four = "\n".join(line for line in GOOD.splitlines() if "[S5]" not in line or line.startswith("## "))
    assert any("expected 5, found 4" in p for p in check_pack(four, bank))
    assert check_pack("just some text", bank)[0].startswith("Missing section")
    short_note = GOOD.split("## Note")[0] + "## Note\nToo short.\n\n## Questions\n- a?\n- b?\n- c?\n"
    assert any(p.startswith("Note: 2 words") for p in check_pack(short_note, bank))


def test_numbers_are_compared_without_commas_percent_signs_or_citations():
    assert numbers_in("2,000 users, 93% renewal, $2.7M, [S12]") == {"2000", "93", "2.7"}
    assert numbers_in("") == set()
    assert numbers_in("1. First question\n2) Second, about 7 things") == {"7"}
