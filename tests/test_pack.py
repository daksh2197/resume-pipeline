import re

import pytest

from resume_pipeline.pack import (
    PackError,
    _reply_numbers,
    build_prompt,
    check_pack,
    identifiers_in,
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
    assert any("number 40, which is not in the story bank" in p for p in problems)


def test_an_invented_number_in_the_note_is_rejected(bank):
    bad = GOOD.replace("Hello. I am applying", "Hello. With 25 years behind me, I am applying")
    problems = check_pack(bad, bank)
    assert any("number 25, which is not in the story bank" in p for p in problems)


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
    assert _reply_numbers("1. First question\n2) Second, about 7 things\n77. odd") == {"7", "77"}


def reply_with(extra_before="", extra_after="", note_extra=""):
    return extra_before + GOOD.replace("## Note\n", "## Note\n" + note_extra) + extra_after


def test_a_number_hidden_outside_the_five_sections_is_still_caught(bank):
    for sneaky in ("Here are 7 tips first.\n\n", "## Salary\nI want 150000.\n\n"):
        assert any(
            "not in the story bank" in p or "Unexpected heading" in p for p in check_pack(reply_with(sneaky), bank)
        )
    assert any(
        "appears twice" in p for p in check_pack(reply_with(extra_after="\n## Note\nI led 900 engineers.\n"), bank)
    )
    assert any("number 77" in p for p in check_pack(reply_with(extra_before="77. That was it.\n"), bank))


def test_a_fake_citation_anywhere_is_caught(bank):
    problems = check_pack(GOOD.replace("Strong fit on", "[S777] Strong fit on"), bank)
    assert any("cites S777" in p for p in problems)


def test_number_words_and_glyphs_are_caught_unless_the_bank_uses_them(bank):
    for sneaky in ("I managed twelve accounts. ", "About half of them. ", "A \u00bd share. "):
        assert any("as a number" in p for p in check_pack(reply_with(note_extra=sneaky), bank))
    with_word = parse_story_bank(BANK_TEXT + "S6: Cut costs by half.\n")
    assert not any("as a number" in p for p in check_pack(reply_with(note_extra="Costs fell by half. "), with_word))


def test_a_bullet_that_is_only_a_citation_is_rejected(bank):
    bad = GOOD.replace("- Technical contact for 12 enterprise accounts, with a 93% renewal rate [S1]", "- [S1]")
    assert any("only a citation" in p for p in check_pack(bad, bank))


def test_crlf_line_endings_and_odd_heading_case_pass(bank):
    crlf = GOOD.replace("\n", "\r\n").replace("## Fit", "### FIT")
    assert check_pack(crlf, bank) == []


def test_suffixed_and_glyph_numbers_are_caught(bank):
    for sneaky in ("A tenfold gain. ", "Hundreds of users. ", "Thrice a year. ", "Dozens of accounts. ", "² and Ⅻ. "):
        assert any("as a number" in p for p in check_pack(reply_with(note_extra=sneaky), bank)), sneaky


def test_a_heading_with_a_colon_is_fine(bank):
    assert check_pack(GOOD.replace("## Fit", "## Fit:"), bank) == []


# --- numbers must match as whole tokens, not as digits hiding inside another token -----------------


def _bank_with(line):
    return parse_story_bank(BANK_TEXT + f"\nS6: {line}\n")


@pytest.mark.parametrize(
    ("bank_line", "reply_sentence", "stray"),
    [
        ("Moved from L4 to L5 in the support ladder.", "I reached level 4.", "4"),
        ("Moved from L4 to L5 in the support ladder.", "I reached level 5.", "5"),
        ("Joined in 2021 and shipped the Galaxy S21 portal.", "Done in 21 days.", "21"),
        ("Paid out $1,200 in credits.", "Paid 200 in credits.", "200"),
        ("Cut run time by 3.5 hours.", "Cut run time by 5 hours.", "5"),
        ("Passed the 21st audit.", "Passed 22 audits.", "22"),
    ],
)
def test_digits_hiding_inside_another_bank_token_do_not_pass(bank_line, reply_sentence, stray):
    bank = _bank_with(bank_line)
    problems = check_pack(reply_with(note_extra=reply_sentence + " "), bank)
    assert any(re.search(rf"\b{stray}\b", p) and "not in the story bank" in p for p in problems), problems


def test_a_story_id_never_supplies_its_number(bank):
    # S4 is a real id, but the number 4 is not in the bank on its own.
    small = parse_story_bank("S4: Did a thing.\nS1: Did two things.")
    assert "4" not in small.numbers()
    assert "4" in _reply_numbers("I did 4 things.") - small.numbers()
    assert numbers_in("S4: see S21 and [S9]") == set()


def test_a_bare_mention_of_a_real_story_id_is_fine(bank):
    assert check_pack(reply_with(note_extra="See S4 for detail. "), bank) == []


@pytest.mark.parametrize(
    ("bank_line", "reply_sentence"),
    [
        ("Hit a 21% lift.", "A 21% lift."),
        ("Hit a 21% lift.", "Up 21 percent: 21."),
        ("Saved $1,200 a month.", "Saved $1,200 a month."),
        ("Saved $1,200 a month.", "Saved 1200 a month."),
        ("Saved 1200 a month.", "Saved $1,200."),
        ("Cut cost by 3.5x.", "A 3.5x cut."),
        ("Cut cost by 3.5x.", "Cut cost (3.5)."),
        ("Rolled out to 5 teams.", "Rolled out to 5."),
        ("Rolled out to 5 teams.", "Teams (5), done."),
        ("Raised $2.7M.", "Raised 2.7M."),
        ("Got promoted to L4 in a year.", "I was L4."),
        ("Got promoted to L4 in a year.", "I was l4."),
    ],
)
def test_whole_token_numbers_still_match(bank_line, reply_sentence):
    bank = _bank_with(bank_line)
    problems = check_pack(reply_with(note_extra=reply_sentence + " "), bank)
    assert not any("not in the story bank" in p for p in problems), problems


def test_a_letter_digit_word_in_the_reply_must_be_in_the_bank(bank):
    problems = check_pack(reply_with(note_extra="I reached L7. "), bank)
    assert any("l7" in p for p in problems)


def test_numbers_in_reads_whole_tokens_only():
    assert numbers_in("L4 S21 2021") == {"2021"}
    assert numbers_in("$1,200 and 3.5x and (5) and 5.") == {"1200", "3.5", "5"}
    assert numbers_in("3.5") == {"3.5"}
    assert numbers_in("1,2000") == {"1", "2000"}
    assert numbers_in("21st 40km 5G 10days") == {"21", "40", "5"}
    assert numbers_in("on 3-5 days, 10/10") == {"3", "5", "10"}


@pytest.mark.parametrize("digits", ["4", "21", "200", "77", "7", "1200"])
@pytest.mark.parametrize("wrap", ["L{}", "S{}", "x{}y", "v{}.1", "SOC{}", "A{}B", "{}x7"])
def test_a_number_inside_an_alphanumeric_token_never_supplies_that_number(digits, wrap):
    token = wrap.format(digits)
    assert digits not in numbers_in(f"Reached {token} today")
    bank = _bank_with(f"Reached {token} today.")
    problems = check_pack(reply_with(note_extra=f"I did {digits} things. "), bank)
    assert digits not in bank.numbers()
    assert any(re.search(rf"(?<![\d,]){digits}\b", p) and "not in the story bank" in p for p in problems), (
        token,
        problems,
    )


@pytest.mark.parametrize(
    ("bank_line", "reply_sentence"),
    [
        ("Drove 40 km a day.", "Drove 40km a day."),
        ("Drove 40km a day.", "Drove 40 km a day."),
        ("Cut latency to 100 ms.", "Cut latency to 100ms."),
        ("Cut latency to 100ms.", "Cut latency to 100 ms."),
        ("Served 21 accounts.", "The 21st account."),
        ("Placed 3rd of 3.", "Placed 3 of 3."),
        ("Used 5mm and 5bn and 5MM.", "5 5 5."),
        ("Shipped 3.5.1 to prod.", "Shipped 3.5.1 to prod."),
        ("Moved to SOC2 and v3.", "Moved to SOC2 and v3."),
    ],
)
def test_digit_first_units_and_whole_versions_pass(bank_line, reply_sentence):
    problems = check_pack(reply_with(note_extra=reply_sentence + " "), _bank_with(bank_line))
    assert not any("not in the story bank" in p for p in problems), problems


def test_versions_are_one_word_and_letter_first_words_keep_their_digits():
    assert numbers_in("version 3.5.1 and 3.5") == {"3.5"}
    assert identifiers_in("version 3.5.1") == {"3.5.1"}
    assert numbers_in("40km 100ms 21st 3rd 5mm 5bn 5MM") == {"40", "100", "21", "3", "5"}
    assert numbers_in("L4 S21 Q3 SOC2 v3 24x7") == set()
    assert identifiers_in("L4 S21 Q3 SOC2 v3 24x7") == {"l4", "s21", "q3", "soc2", "v3", "24x7"}


def test_a_version_in_the_bank_does_not_supply_its_first_two_parts():
    problems = check_pack(reply_with(note_extra="I did 3.5 things. "), _bank_with("Shipped 3.5.1 to prod."))
    assert any("3.5" in p and "not in the story bank" in p for p in problems)
