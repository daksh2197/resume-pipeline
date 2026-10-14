# The rubric

Every score comes from one file you write once: `rubric.yaml`. The code in [`src/resume_pipeline/scoring.py`](../src/resume_pipeline/scoring.py) reads it, goes through a fixed list of checks, and writes down a reason for every point. No model is involved. The same CSV and the same rubric always give the same answer.

## The checks, in order

1. **No title.** A lead with no job title cannot be scored. It is knocked out and says why.
2. **Knockouts.** Any phrase from `knockouts` found in the title, company or description ends the lead. Nothing else can save it, including the company whitelist.
3. **Salary floor.** The stated pay is turned into a yearly range. If the *top* of the range is under `salary.floor`, the lead is knocked out. A company on `company_whitelist` skips this check. A missing or unreadable salary is **unknown**: it is not checked, it is not a pass, and the lead is marked incomplete.
4. **Location and remote.** A lead is remote if the word "remote" is in its location or title. With `remote: reject`, remote leads are knocked out. With `remote: only`, leads that are not remote are knocked out. Otherwise, if `location.allowed` has entries, a lead that is not remote must match one of them. A blank location is unknown and marked incomplete.
5. **Must-haves.** With a description, a lead missing a must-have is knocked out. With no description, the must-have cannot be checked, so the lead is marked incomplete and carries on.
6. **Points.** The best matching title family counts once. Each nice-to-have found adds its points. A remote lead adds `location.remote_points`.

Matching is whole-word and ignores upper and lower case, so `sql` does not match `MySQL`, and `c++` works.

Leads are ranked by score, highest first. Equal scores keep the order they had in your CSV. Knocked-out leads have no rank and sit at the bottom.

## How a yearly salary is worked out

| The lead says | The tool reads it as |
| --- | --- |
| `$105,000 - $125,000` | 105,000 to 125,000 a year |
| `98k-118k` or `90-110k` | 98,000 to 118,000, and 90,000 to 110,000 |
| `$22/hour` or `$40 - $50 per hour` | multiplied by `salary.hours_per_year` (2,080 unless you change it) |
| `$7,000 per month` | multiplied by 12 |
| `Competitive`, `DOE`, blank | unknown |
| a number under 1,000 a year, or over 10,000,000 | unknown, because it is more likely a typo than a salary |

Only the first two numbers in the text are used. If a lead lists three salaries for three levels, check it yourself.

## One posting, scored by hand

From `samples/jobs.csv`, row 1 (invented): Technical Account Manager at Tamarack Cloud, Calgary, AB, `$105,000 - $125,000`. The description says: "Own technical relationships with enterprise customers. Cloud, SQL and customer success experience. Python scripting is a plus."

| Check | What happens | Points |
| --- | --- | ---: |
| Knockouts | none of `cold calling`, `security clearance`, `unpaid`, `quota-carrying`, `authorised to work in the United States` appear | 0 |
| Salary floor 90,000 | top of range is 125,000, which clears it | 0 |
| Location | "Calgary, AB" matches `Calgary` in the allowed list | 0 |
| Must-have `cloud or data` | "Cloud" is in the description | 0 |
| Title family | "Technical Account Manager" matches `technical account manager` | +5 |
| Nice-to-have `cloud` | present | +1 |
| Nice-to-have `sql` | present | +1 |
| Nice-to-have `python` | present | +1 |
| Nice-to-have `live data`, `presentations` | neither appears | 0 |
| **Total** | | **8** |

"customer success" appears in the description. It earns nothing, because title families are matched against the title only. The sample run gives this lead 8 and the report lists exactly the reasons above.

## Tuning it

Ranking quality depends on this file. A rubric that is too loose puts everything on the shortlist. One that is too strict knocks out the lead you wanted. The loop that works:

1. Run `uv run screen jobs.csv --rubric rubric.yaml`.
2. Open the report and read the **reasons**, not just the order.
3. Find a lead that is in the wrong place. The reasons will show which line put it there.
4. Change that line in the YAML. Run again.

Things worth knowing when you tune:

- **Weights are relative.** A title family worth 5 beside nice-to-haves worth 1 means a good title beats four small matches. Change the ratio and the order changes.
- **A knockout is a strong word.** `unpaid` also knocks out "unpaid leave policy". If that bites, narrow the phrase.
- **Incomplete leads are a lower bound.** A lead marked incomplete could rank higher or lower once you read the posting. The report counts them so you remember.
- **A whitelist only waives the salary floor.** A whitelisted company still has to pass knockouts, location and must-haves.

## What the score does not know

- It cannot read between the lines. A posting that says "fast-paced" scores the same as one that says "calm".
- It does not know whether a salary is in the currency you think it is.
- It scores the text it was given. A description pasted into the CSV is read in full. A description that is only a link is not fetched, because this tool never visits job sites.
