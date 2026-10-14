# CTO notes

You don't have to write this code. You have to be able to do three things with it:

1. **Explain it** to an interviewer, a partner or a customer.
2. **Find a bug** in it when a ranking looks wrong.
3. **Know what to ask for** when you want it changed.

Read sections 1 and 2 once (about 15 minutes). Keep section 4 for the day something breaks. Do section 5 with your own hands, because that is where it sticks.

## 1. The whole tool in one picture

```
 leads CSV ──> read_leads ──> score_all ──> ranked.csv + report.html      (screen)
                  ^               ^
                  └── rubric.yaml ┘

 posting.txt + story-bank.md ──> build_prompt ──> prompt.md ──> any assistant ──> reply.md
 reply.md + story-bank.md   ──> check_pack ──> "passed" or a list of what is wrong   (pack)
```

There is no server, no database and no model inside. Each box is a small function you can run alone. The rules live in `rubric.yaml`, not in the code.

## 2. Six ideas this repo teaches

### The new one: a pipeline of small steps, with the rules in a config file

A pipeline is a chain of steps where each step takes one thing in and gives one thing out. Here the steps are *read the CSV*, *score each lead*, *write the report*. Each one does one job and can be tested without the others.

The rules (what counts, what disqualifies, what the salary floor is) sit in `rubric.yaml`. If a rule is in the code, only a programmer can change it. If it is in a file, the person who owns the job search can change it and run it again in a second.

- **See it:** [`src/resume_pipeline/cli.py`](../src/resume_pipeline/cli.py) is the whole chain in about thirty lines. The rubric is [`samples/rubric.yaml`](../samples/rubric.yaml).
- **Say it:** "The rules are data, the steps are tiny, so I change my search by editing a text file and I can test every step alone."

### Pure functions

`score_lead(lead, rubric)` gets a lead and a rubric in and gives a result out. Same input, same answer, every time. No clock, no network, no files.

- **See it:** `score_lead` in [`scoring.py`](../src/resume_pipeline/scoring.py).
- **Say it:** "Scoring is one pure function, so I can test every edge case in milliseconds."

### Validate at the edge

The CSV and the rubric are written by people, so they are wrong sometimes. `rubric.py` refuses a rubric with a negative weight or a mistyped key, and says which line. `leads.py` refuses a CSV whose columns do not match the mapping and lists the columns it did find. After that, the scoring code can trust what it is given.

- **See it:** `parse_rubric` in `rubric.py` and `read_leads` in `leads.py`.
- **Say it:** "Bad input is stopped at the door with a plain message, so the middle of the program never has to wonder."

### Unknown is not zero

A lead with no salary is not a lead that pays nothing, and it is not a lead that passes. It is **unknown**. The scorer keeps it, says "salary unknown: not checked against the floor", marks the lead incomplete, and the report counts how many ranked leads were scored on incomplete data.

- **See it:** the salary branch of `score_lead`, and `parse_salary` in [`salary.py`](../src/resume_pipeline/salary.py), which returns `None` rather than guessing.
- **Say it:** "Missing data is a third state. Treating it as a pass or a fail would quietly change the ranking."

### Three kinds of test

An **example test** runs one hand-picked case. A **golden-file test** runs the sample end to end and compares the HTML report to a saved copy. A **property test** checks a rule across hundreds of random inputs: "adding a nice-to-have never lowers a score".

- **See it:** [`tests/test_scoring.py`](../tests/test_scoring.py) for examples and the property test, [`tests/test_report_and_cli.py`](../tests/test_report_and_cli.py) for the golden file.
- **Run it:** `uv run pytest`. If you change the report on purpose, run `uv run python scripts/regen_golden.py` and read the diff before you commit.
- **Say it:** "Examples cover what I thought of. The property test covers what I didn't. The golden file stops the report changing by accident."

### A guardrail in code

The application pack must never invent experience. That rule is not in the prompt alone. `check_pack` in [`pack.py`](../src/resume_pipeline/pack.py) reads the reply and rejects it if a bullet has no `[S1]`-style citation, cites a line that is not there, or contains a number that is not in the story bank. A prompt asks nicely. A check enforces.

- **See it:** `check_pack` and `numbers_in`.
- **Try it:** `uv run pack --story-bank samples/story-bank.md --check samples/sample-reply.md` passes. Change "45 minutes" to "40 minutes" in a copy and it fails.
- **Say it:** "I don't trust the model to follow the rule, so the code checks the output."

## 3. Where things live

| You want to change... | Open this |
| --- | --- |
| What counts for or against a lead | `rubric.yaml` (yours) or `samples/rubric.yaml` (the example) |
| The order of the checks, or what a knockout does | `score_lead` in `src/resume_pipeline/scoring.py` |
| How salary text is read | `src/resume_pipeline/salary.py` |
| Which CSV columns are read | `columns:` in the rubric, and `src/resume_pipeline/leads.py` |
| The report's look | the CSS string in `src/resume_pipeline/report.py`; colours in `src/resume_pipeline/assets/brand.css` |
| What goes in `ranked.csv` | `ranked_csv` in `report.py` |
| The prompt for the application pack | `build_prompt` in `pack.py` |
| What the pack checker rejects | `check_pack` in `pack.py` |
| What happens on every push | `.github/workflows/ship.yml` |
| The daily schedule example | `examples/daily.yml` |

## 4. When something breaks

| What you see | Likely cause | Where to look | How to check |
| --- | --- | --- | --- |
| `error: No column named 'Job Title'` | The CSV header is spelled differently | `columns:` in the rubric | The message lists the columns the file has. Copy the right one in. |
| A lead you wanted is knocked out | A knockout phrase, the salary floor or a must-have | Its reasons in the report | The first line says which rule fired. Narrow the phrase or lower the floor. |
| Everything is knocked out | A must-have no posting contains, or a location list that is too narrow | `must_haves` and `location.allowed` | Run with the must-have removed and compare. |
| A lead is ranked but marked incomplete | The salary, location or description was blank or unreadable | The CSV row | Fill the cell in, or accept that the rank is a lower bound. |
| Hourly pay is knocked out unexpectedly | `hours_per_year` is 2,080 by default | `salary.hours_per_year` | `$22/hour` becomes 45,760 a year. |
| `Pack rejected: number 40 is not in the story bank` | The assistant added a number | The line it names | Fix the reply or the story bank. The tool never edits either for you. |
| `Missing section: Gaps` | The reply used different headings | `build_prompt` | The five headings must be Fit, Gaps, Bullets, Note, Questions. |
| Green check, no website | The repo is private, so the deploy job is skipped on purpose | `.github/workflows/ship.yml` | Make the repo public, set Pages to **GitHub Actions**, run the workflow once. |
| Red X at "Lint" | A formatting or style rule | The run log | `uv run ruff format .` then `uv run ruff check . --fix` |
| The golden-file test fails after a change | The report changed | `tests/golden/report.html` | If you meant it, `uv run python scripts/regen_golden.py` and read the diff. |

**The one debugging habit that matters:** reproduce it as a test first. A bug you can trigger with a test is a bug you can fix once and keep fixed.

## 5. Your turn

Five real changes, easiest first. Each one is a commit with your name on it. Work on a copy of the rubric (`cp samples/rubric.yaml rubric.yaml`) so the sample stays as it is. `rubric.yaml` is ignored by git on purpose.

1. **Add a nice-to-have.** In your copy, add `- { name: onboarding, match: [onboarding], points: 3 }` under `nice_to_haves`. Run `uv run screen samples/jobs.csv --rubric rubric.yaml`. *Done when:* Pinewood Data's Senior Customer Success Manager moves from rank 4 (5.5) to rank 2 (8.5), because its description says "onboarding".
2. **Raise the floor.** Set `salary.floor` to `120000`. *Done when:* the run says `7 ranked, 13 knocked out`, and Quarry Cloud (whitelist sample) is still ranked, with the reason "salary floor waived: company is on the whitelist".
3. **Ask for remote only.** Set `location.remote` to `only`. *Done when:* the run says `3 ranked, 17 knocked out`. Open the report and read why each of the 17 went.
4. **Add a knockout.** Add `- travel` under `knockouts`. *Done when:* Larkspur Systems' Solutions Engineer ("Travel up to 10%") is knocked out, and the run says `8 ranked, 12 knocked out`.
5. **Write a test.** In `tests/test_scoring.py`, add a test that a posting containing a knockout phrase is knocked out even when its company is whitelisted. A similar one exists (`test_a_knockout_beats_the_company_whitelist`); write yours with your own phrase before you read it. *Done when:* `uv run pytest` passes. Then check that your test can fail: in `score_lead`, temporarily change the line that builds `hits` to `hits = []`, run the tests, watch yours fail, and put the line back.

## 6. Questions you should be ready for

**Why no model for the ranking?**
A rule I wrote down can be explained, tested and argued with. A model's score can't. Every point here comes with a reason, and the same input always gives the same output.

**How do you know the ranking is right?**
I don't, and the README says so. It is as good as the rubric. The tool's job is to apply my rules the same way every time and show its working, so I can fix the rules.

**Why won't it apply for you?**
It breaks the rules of the sites involved, gets accounts restricted, and untailored volume converts worse. The tool ends at a draft. I press send.

**What stops the application pack from inventing things?**
`check_pack`. Every bullet has to cite a numbered line from my story bank, and any number in the pack has to appear in the bank. Wording is the part it can't check, which is why I read the pack before sending it.

**What did the AI do, and what did you do?**
Say it straight: Claude wrote most of the code as a pair programmer. You chose the problem, decided what the tool should and should not do, reviewed the changes and can walk through any file. Then walk through one.

## 7. Words you'll hear

| Word | Plain meaning |
| --- | --- |
| Repo | The project folder, with its full history |
| Commit | One saved change, with a message saying why |
| Pipeline | A chain of small steps, each feeding the next |
| Rubric | Your written rules for judging a lead |
| Knockout | A rule that removes a lead whatever else it scores |
| YAML | A plain-text format for settings, written as indented lines |
| CSV | A spreadsheet saved as plain text, one row per line |
| Golden file | A saved correct output that a test compares against |
| Property test | A test of a rule across many random inputs |
| CI / CD | Robot runs the tests / robot deploys if they pass |
| `uv` | The tool that installs Python and the packages this project needs |
