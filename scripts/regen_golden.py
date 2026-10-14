"""Rewrite the golden report after you change the report on purpose. Then read the diff."""

from pathlib import Path

from resume_pipeline.leads import read_leads
from resume_pipeline.report import build_report
from resume_pipeline.rubric import load_rubric
from resume_pipeline.scoring import score_all

rubric = load_rubric("samples/rubric.yaml")
results = score_all(read_leads("samples/jobs.csv", rubric), rubric)
Path("tests/golden/report.html").write_text(
    build_report(results, rubric, embed_fonts=False, sample=True), encoding="utf-8"
)
print("rewrote tests/golden/report.html")
