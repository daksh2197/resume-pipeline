import pytest

from helpers import BASE
from resume_pipeline.leads import LeadsError, read_leads
from resume_pipeline.rubric import RubricError, load_rubric, parse_rubric


def test_the_sample_rubric_loads():
    r = load_rubric("samples/rubric.yaml")
    assert r.salary_floor == 90000 and r.shortlist_size == 10
    assert r.columns["title"] == "Job Title"


@pytest.mark.parametrize(
    "change,message",
    [
        ({"nice_to_haves": [{"name": "x", "points": -1}]}, "must be 0 or more"),
        ({"nice_to_haves": [{"name": "x", "points": float("nan")}]}, "finite"),
        ({"nice_to_haves": [{"name": "x", "points": "lots"}]}, "must be a number"),
        ({"salary": {"floor": "high"}}, "salary.floor must be a number"),
        ({"salary": {"flor": 5}}, "unknown keys"),
        ({"location": {"remote": "maybe"}}, "location.remote"),
        ({"nice_to_haves": [{"name": "x", "mach": ["y"]}]}, "unknown keys"),
        ({"knockouts": [""]}, "non-empty"),
        ({"shortlist_size": 0}, "shortlist_size"),
        ({"surprise": 1}, "Unknown top-level keys"),
        ({"columns": {"title": "T", "titel": "x"}}, "unknown fields"),
        ({"columns": {"company": "C"}}, "columns.title is required"),
    ],
)
def test_a_wrong_rubric_is_refused_with_a_message(change, message):
    with pytest.raises(RubricError, match=message):
        parse_rubric({**BASE, **change})


def test_not_a_mapping_and_bad_yaml_and_missing_file(tmp_path):
    with pytest.raises(RubricError):
        parse_rubric(["a list"])
    bad = tmp_path / "bad.yaml"
    bad.write_text("title_families: [unclosed")
    with pytest.raises(RubricError, match="not valid YAML"):
        load_rubric(bad)
    with pytest.raises(RubricError, match="Cannot read"):
        load_rubric(tmp_path / "nope.yaml")


def test_a_csv_with_odd_column_names_works_through_the_mapping(tmp_path):
    csv_file = tmp_path / "odd.csv"
    csv_file.write_text(
        "ROLE NAME,Hiring Org,City,Comp,Apply Here\n"
        'Technical Account Manager,Acme Sample,Calgary,"$100,000",https://example.com/a\n',
        encoding="utf-8",
    )
    rubric = parse_rubric(
        {
            "columns": {
                "title": "role name",
                "company": "HIRING ORG",
                "location": "City",
                "salary": "Comp",
                "url": "Apply Here",
            }
        }
    )
    (item,) = read_leads(csv_file, rubric)
    assert (item.title, item.company, item.location, item.salary) == (
        "Technical Account Manager",
        "Acme Sample",
        "Calgary",
        "$100,000",
    )
    assert not item.has_description_column


def test_a_missing_mapped_column_names_the_columns_that_exist(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("Foo,Bar\n1,2\n")
    with pytest.raises(LeadsError, match="Its columns are: Foo, Bar"):
        read_leads(f, parse_rubric({"columns": {"title": "Job"}}))
    with pytest.raises(LeadsError, match="maps salary"):
        read_leads(f, parse_rubric({"columns": {"title": "Foo", "salary": "Pay"}}))


def test_empty_short_and_mangled_files(tmp_path):
    r = parse_rubric({"columns": {"title": "Title", "company": "Company"}})
    empty = tmp_path / "e.csv"
    empty.write_text("")
    with pytest.raises(LeadsError, match="empty"):
        read_leads(empty, r)
    header_only = tmp_path / "h.csv"
    header_only.write_text("Title,Company\n")
    assert read_leads(header_only, r) == []
    ragged = tmp_path / "r.csv"
    ragged.write_text("Title,Company\nOnly a title\n,\nA,B,C,D\n")
    items = read_leads(ragged, r)
    assert [i.title for i in items] == ["Only a title", "", "A"]
    with pytest.raises(LeadsError, match="Cannot read"):
        read_leads(tmp_path / "missing.csv", r)


def test_byte_order_marks_old_encodings_and_nul_bytes_are_handled(tmp_path):
    r = parse_rubric({"columns": {"title": "Title"}})
    bom = tmp_path / "bom.csv"
    bom.write_bytes("Title\nDéveloppeur\n".encode("utf-8-sig"))
    assert read_leads(bom, r)[0].title == "Développeur"
    old = tmp_path / "old.csv"
    old.write_bytes("Title\nD\xe9veloppeur\n".encode("latin-1"))
    assert read_leads(old, r)[0].title == "Développeur"
    nul = tmp_path / "nul.csv"
    nul.write_bytes(b"Title\nA\x00B\n")
    assert read_leads(nul, r)[0].title == "AB"


def test_a_huge_field_is_cut_not_crashed_on(tmp_path):
    r = parse_rubric({"columns": {"title": "Title"}})
    f = tmp_path / "big.csv"
    f.write_text("Title\n" + "x" * 50_000 + "\n")
    assert len(read_leads(f, r)[0].title) == 20_000


def test_a_huge_number_in_the_rubric_is_refused_not_a_traceback():
    with pytest.raises(RubricError, match="too large"):
        parse_rubric({**BASE, "salary": {"hours_per_year": 10**400}})


def test_headers_with_stray_spaces_still_match(tmp_path):
    f = tmp_path / "s.csv"
    f.write_text("Job Title ,Employer\nA,B\n")
    (item,) = read_leads(f, parse_rubric({"columns": {"title": "Job Title", "company": "Employer"}}))
    assert item.title == "A"


def test_windows_encoded_files_work_for_the_rubric_and_the_pack(tmp_path):
    rub = tmp_path / "r.yaml"
    rub.write_bytes("columns: {title: 'Intitul\xe9'}\n".encode("latin-1"))
    assert load_rubric(rub).columns["title"] == "Intitul\u00e9"
    from resume_pipeline.cli import pack_main

    bank = tmp_path / "b.md"
    bank.write_bytes("S1: Fixed 3 bugs \x96 quickly.\n".encode("latin-1"))
    posting = tmp_path / "p.txt"
    posting.write_bytes(b"A posting \x92s text")
    assert pack_main([str(posting), "--story-bank", str(bank), "--out", str(tmp_path / "o.md")]) == 0
