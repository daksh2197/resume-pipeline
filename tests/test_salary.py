import pytest

from resume_pipeline.salary import parse_salary


@pytest.mark.parametrize(
    "text,low,high",
    [
        ("$105,000 - $125,000", 105000, 125000),
        ("98k-118k", 98000, 118000),
        ("$98k to $118k", 98000, 118000),
        ("90-110k", 90000, 110000),
        ("$72,000", 72000, 72000),
        ("$22/hour", 45760, 45760),
        ("$40 - $50 per hour", 83200, 104000),
        ("$7,000 per month", 84000, 84000),
        ("CAD 120000", 120000, 120000),
        ("3 openings, $90k-$110k", 90000, 110000),
        ("$80,000 plus 401k", 80000, 80000),
        ("$2,000 per week", 104000, 104000),
        ("$3,500 biweekly", 91000, 91000),
        ("$7k/mth", 84000, 84000),
        ("$66.32-$89.38per hour", 137945.6, 185910.4),
        ("2 positions $60k and $120k", 60000, 120000),
    ],
)
def test_salary_text_becomes_a_yearly_range(text, low, high):
    r = parse_salary(text)
    assert r is not None and (r.low, r.high) == pytest.approx((low, high))


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "   ",
        "Competitive",
        "DOE",
        "0",
        "-5",
        "$5",
        "1e999",
        "9" * 40,
        "\x00",
        "NaN",
        "Infinity",
    ],
)
def test_unreadable_or_absurd_salary_is_unknown_never_zero(text):
    assert parse_salary(text) is None


def test_hours_per_year_is_configurable():
    r = parse_salary("$50/hour", hours_per_year=1800)
    assert r is not None and r.high == 90000
