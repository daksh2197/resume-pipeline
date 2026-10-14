from resume_pipeline.leads import Lead
from resume_pipeline.rubric import parse_rubric

BASE = {
    "columns": {
        "title": "Title",
        "company": "Company",
        "location": "Location",
        "salary": "Salary",
        "url": "Url",
        "description": "Description",
    },
    "title_families": [{"name": "tam", "match": ["technical account manager"], "points": 5}],
    "salary": {"floor": 90000},
}


def rubric(**changes):
    data = {**BASE, **changes}
    return parse_rubric(data)


def lead(
    title="Technical Account Manager",
    company="Acme Sample",
    location="Calgary",
    salary="$100,000",
    url="https://example.com/1",
    description="Cloud and SQL work.",
    row=1,
):
    return Lead(row, title, company, location, salary, url, description, True)
