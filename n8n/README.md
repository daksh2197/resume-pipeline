# n8n workflow

`shortlist.workflow.json` runs `screen` and hands back the top ten ranked leads as items you can send anywhere n8n can send things.

**What was verified.** I imported this file into n8n 2.35.7 (installed with `npm i n8n`) on 14 October 2026 and ran it with `n8n execute --id=resumePipeline01`, starting from the manual trigger. It finished with status `success` and returned the same nine ranked leads as `ranked.csv` for the sample data, in the same order. With the data folder variable missing, the run failed with the tool's own error message, which is what you want.

**Good to know.** The shortlist size is fixed at ten inside the Code node and ignores `shortlist_size` in your rubric. The schedule uses the time zone of your n8n instance.

**What was not verified.** The "Every morning at 7" trigger is a standard n8n schedule node wired to the same step. I did not wait for it to fire.

## The steps

1. **Run screen** (Execute Command). Runs `screen jobs.csv --rubric rubric.yaml` inside your data folder, then prints `ranked.csv`.
2. **Keep the shortlist** (Code). Reads that CSV text, drops knocked-out leads and keeps the first ten.

Add whatever you like after step 2: a Slack node, an email to yourself, a row in a sheet. This repo ships none of those, because each needs your own account.

## Set it up

n8n 2.x turns the Execute Command node off by default. Turn it on and tell the workflow where things are:

```bash
export NODES_EXCLUDE='[]'                         # allow the Execute Command node
export RESUME_PIPELINE_TOOL=/path/to/resume-pipeline   # this repo, after `uv sync`
export RESUME_PIPELINE_DATA=/path/to/your/leads        # a folder with jobs.csv and rubric.yaml
npx n8n import:workflow --input=n8n/shortlist.workflow.json
npx n8n start
```

Then open the workflow in the n8n editor and press **Execute workflow**. Your real leads and rubric stay in the data folder, outside this repo.

Only the Execute Command node touches your machine, and it runs one command. Read it before you activate the schedule.
