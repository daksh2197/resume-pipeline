# How this could pay for itself

The tool is free and stays free. This page is the honest version of how a free command-line tool turns into money, what each path needs to be true, and what I don't know yet.

No market-size numbers here. I haven't measured a market, so I'm not going to make one up.

## Who it's for

People who get job leads as a CSV or spreadsheet export and want a shortlist with reasons. It is built first for my own job search.

The moment it's for: the list has arrived, most of it is noise, and the few worth an hour each are somewhere in there.

## What's free forever

The `screen` command, the report, the `pack` prompt builder and the guardrail. Anything that touches your leads stays on your machine, and a paywall on that would kill the reason to trust it.

## Two ways it could earn

### 1. Rubric packs per role family

A rubric is the hard part for a new user. Starting from a blank YAML file is slow. A pack would be a tuned rubric plus a short guide for one kind of search: customer success, data analyst, solutions engineering, trades, and so on.

- **Price to test:** a one-off download at a low price, set after the waitlist shows interest.
- **What has to be true:** people would rather buy a starting point than write one in an afternoon.
- **Cost to deliver:** near zero. It's a file and a page of advice.

### 2. Done-for-you setup

Someone builds a job seeker's rubric from jobs they liked and hated, and sets up the daily schedule in their own private repo.

- **Price to test:** a small fixed fee for one session.
- **What has to be true:** people who are comfortable pasting a CSV are not always comfortable with YAML and a command line.
- **Cost to deliver:** a person's time. It does not scale, which is fine for a test.

## What it costs to run

| Thing | Cost |
| --- | --- |
| Hosting the sample report (GitHub Pages) | $0 |
| Servers, database | none |
| Model calls | none in the tool. If you paste the prompt into an assistant, that is your own account |

## The one-week demand test

1. Put the free tool and the sample report in front of people who are job hunting right now.
2. Offer a single sample rubric pack behind a waitlist link. Nothing to buy yet.
3. Count two numbers: clicks on the link I post, and waitlist sign-ups. The tool has no tracking and that isn't changing, so I count at the door, not inside the room.

**Go:** 25 or more sign-ups in a week. Build the pack.
**No-go:** fewer than 5. The tool is fine and the offer is wrong. Change the offer, not the code.
**In between:** one more week with a different audience.

## What I don't know yet

- Whether anyone wants a rubric they did not write. The idea of the tool is that your rules are yours.
- Whether job seekers keep their leads as CSVs often enough for this to matter, or whether most just read email.
- Whether the guardrail on the application pack is a reason to use it or a reason to find it fussy.

## Ground rules

- No auto-apply, ever. It breaks site rules, gets accounts restricted, and untailored volume converts worse.
- No scraping job boards and no guessing recruiter emails.
- No ads and no selling data. The tool collects none, so there is nothing to sell.
