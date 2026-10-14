import random

from helpers import lead, rubric
from resume_pipeline.scoring import score_all, score_lead


def test_a_knockout_beats_a_perfect_score():
    r = rubric(knockouts=["cold calling"], nice_to_haves=["cloud", "sql"])
    s = score_lead(lead(description="Cloud and SQL. Cold calling required."), r)
    assert s.knocked_out
    assert s.reasons == ("knockout: contains cold calling",)


def test_a_knockout_beats_the_company_whitelist():
    r = rubric(knockouts=["unpaid"], company_whitelist=["Acme Sample"])
    assert score_lead(lead(description="Unpaid trial week."), r).knocked_out


def test_a_whitelisted_company_skips_the_salary_floor():
    r = rubric(company_whitelist=["acme sample"])
    s = score_lead(lead(salary="$50,000"), r)
    assert not s.knocked_out
    assert "salary floor waived: company is on the whitelist" in s.reasons


def test_the_same_pay_from_another_company_is_knocked_out():
    s = score_lead(lead(salary="$50,000"), rubric(company_whitelist=["Someone Else"]))
    assert s.knocked_out
    assert s.reasons[0].startswith("knockout: salary stated below floor")


def test_unknown_salary_is_flagged_not_failed_and_not_passed():
    s = score_lead(lead(salary=""), rubric())
    assert not s.knocked_out
    assert s.incomplete == ("salary",)
    assert "salary unknown: not checked against the floor" in s.reasons
    assert not any("clears the floor" in reason for reason in s.reasons)


def test_unreadable_salary_text_counts_as_unknown():
    for text in ("Competitive", "DOE", "see posting", "$$$"):
        assert score_lead(lead(salary=text), rubric()).incomplete == ("salary",)


def test_hourly_pay_is_converted_before_the_floor_check():
    low = score_lead(lead(salary="$30/hour"), rubric())  # 62,400 a year
    high = score_lead(lead(salary="$50/hour"), rubric())  # 104,000 a year
    assert low.knocked_out and not high.knocked_out


def test_a_range_passes_when_its_top_clears_the_floor():
    assert not score_lead(lead(salary="$80,000 - $95,000"), rubric()).knocked_out


def test_weights_decide_the_order():
    r = rubric(
        title_families=[
            {"name": "a", "match": ["alpha"], "points": 2},
            {"name": "b", "match": ["beta"], "points": 7},
        ]
    )
    ranked = score_all([lead("alpha", row=1), lead("beta", row=2)], r)
    assert [s.lead.title for s in ranked] == ["beta", "alpha"]
    assert [s.rank for s in ranked] == [1, 2]


def test_ties_keep_the_order_of_the_csv_whatever_order_they_arrive_in():
    leads = [lead(row=i, company=f"Co {i}") for i in (3, 1, 2)]
    first = score_all(leads, rubric())
    second = score_all(list(reversed(leads)), rubric())
    assert [s.lead.row for s in first] == [1, 2, 3]
    assert [s.lead.row for s in second] == [1, 2, 3]


def test_knocked_out_leads_have_no_rank_and_sit_last():
    r = rubric(knockouts=["bad"])
    ranked = score_all([lead(description="bad", row=1), lead(row=2)], r)
    assert [s.knocked_out for s in ranked] == [False, True]
    assert ranked[1].rank is None


def test_a_missing_must_have_knocks_out_when_there_is_a_description():
    r = rubric(must_haves=[{"name": "sql", "match": ["sql"]}])
    assert score_lead(lead(description="Only python here."), r).knocked_out


def test_must_have_is_unchecked_not_failed_when_there_is_no_description():
    r = rubric(must_haves=[{"name": "sql", "match": ["sql"]}])
    s = score_lead(lead(description=""), r)
    assert not s.knocked_out and "description" in s.incomplete


def test_matching_is_whole_word_so_sql_does_not_match_mysql():
    r = rubric(nice_to_haves=[{"name": "sql", "match": ["sql"], "points": 1}])
    assert score_lead(lead(description="We run MySQL."), r).score == 5
    assert score_lead(lead(description="We write SQL."), r).score == 6


def test_phrases_with_symbols_match():
    r = rubric(nice_to_haves=[{"name": "c++", "match": ["c++"], "points": 1}])
    assert score_lead(lead(description="Strong C++ skills"), r).score == 6


def test_remote_rules():
    only = rubric(location={"remote": "only"})
    assert score_lead(lead(location="Calgary"), only).knocked_out
    assert not score_lead(lead(location="Remote (Canada)"), only).knocked_out
    reject = rubric(location={"remote": "reject"})
    assert score_lead(lead(location="Remote"), reject).knocked_out
    assert score_lead(lead(location="Remote"), rubric(location={"remote_points": 2})).score == 7


def test_location_outside_the_allowed_list_is_knocked_out_and_blank_is_unknown():
    r = rubric(location={"allowed": ["Calgary"]})
    assert score_lead(lead(location="Halifax"), r).knocked_out
    blank = score_lead(lead(location=""), r)
    assert not blank.knocked_out and "location" in blank.incomplete


def test_rows_with_missing_fields_do_not_crash():
    blank = lead(title="", company="", location="", salary="", url="", description="")
    s = score_lead(blank, rubric())
    assert s.knocked_out and "title" in s.incomplete
    sparse = lead(company="", location="", salary="", url="", description="")
    assert not score_lead(sparse, rubric(must_haves=["sql"])).knocked_out


def test_adding_a_nice_to_have_never_lowers_a_score():
    """Property: for random rubrics and postings, one more nice-to-have cannot hurt."""
    rng = random.Random(20261014)
    words = ["cloud", "sql", "python", "go", "rust", "excel", "agile", "sales", "data", "api"]
    for _ in range(500):
        description = " ".join(rng.choices(words, k=rng.randint(0, 8)))
        existing = [
            {"name": w, "match": [w], "points": rng.choice([0, 0.5, 1, 3])}
            for w in rng.sample(words, rng.randint(0, 4))
        ]
        extra = {
            "name": "extra",
            "match": [rng.choice(words)],
            "points": rng.choice([0, 0.5, 1, 4]),
        }
        item = lead(description=description)
        before = score_lead(item, rubric(nice_to_haves=existing))
        after = score_lead(item, rubric(nice_to_haves=[*existing, extra]))
        assert after.score >= before.score
        assert after.knocked_out == before.knocked_out


def test_not_remote_is_not_remote():
    only = rubric(location={"remote": "only"})
    for text in ("Not remote", "non-remote, Calgary", "No remote work"):
        assert score_lead(lead(location=text), only).knocked_out


def test_big_numbers_never_print_in_exponent_form():
    r = rubric(salary={"floor": 1_500_000})
    s = score_lead(lead(salary="$1,234,567"), r)
    assert s.knocked_out and "e+" not in s.reasons[0] and "1234567 < 1500000" in s.reasons[0]
    heavy = rubric(nice_to_haves=[{"name": "x", "match": ["cloud"], "points": 1e7}])
    assert score_lead(lead(), heavy).reasons[-1] == "+10000000 nice-to-have: x"
