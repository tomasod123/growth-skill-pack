---
name: meta-weekly-account-report
description: Read-only weekly Meta ads report. For each ad account, compares the last 7 days (ending yesterday) with the 7 days before at account, campaign and ad level, flags best ad, kill candidates, fatigue, budget pacing and sudden lead drops, and writes a 1-3 item "do this week" list. Use when the user says "weekly account report", "weekly ads report", "Meta weekly report", "how did the ads do this week", "week over week Meta", "media buyer report", "which ads should I kill", or "run the Friday ads report".
---

# Meta weekly account report

Read-only. It only sends GET requests to the Meta Marketing API and never changes a campaign.

## How to run

From the skill folder:

```bash
python scripts/weekly_report.py --demo        # fixture data, no API calls, safe to try
python scripts/weekly_report.py               # real run: writes the markdown, prints the summary
python scripts/weekly_report.py --date 2026-03-12   # as if today were that date (window ends the day before)
python scripts/weekly_report.py --send        # also post the summary to SLACK_WEBHOOK_URL
```

Default is print only. Only post to Slack when the user asks for it in this session (`--send`).
If `config.yaml` or `.env` is missing, point the user to `SETUP.md`.

## What it reports (per ad account, in that account's currency)

- Spend, impressions, link clicks, link CTR, CPM, frequency, leads, CPL: this week vs last, with arrows and %.
- Totals grouped by currency. Different currencies are never added together.
- Best ad: lowest CPL with at least 3 leads (and not a kill candidate).
- Kill candidates: spend of 2x target CPL or more with 0 leads, or CPL above 2x target.
- Fatigue: ad frequency 4.0 or higher.
- Budget pacing: active campaigns with a daily budget, spend vs 7x daily budget. Meta returns budgets in minor units (cents, pence), so they are divided by 100 (by 1 for currencies like JPY).
- Sudden drop: spend held or rose but leads fell 40% or more. Message: check the lead form to CRM sync.
- Do this week: up to 3 actions, most urgent first.

All thresholds are plain defaults in `config.yaml` under `defaults:`.

## Counting rules (do not change)

- Leads = `action_type == "lead"` only. Never match on the word "lead": `onsite_conversion.lead_grouped` and `offsite_conversion.fb_pixel_lead` count the same people again.
- Link clicks = `inline_link_clicks`. CTR and CPM are recomputed from spend, impressions and link clicks.
- Paging follows `paging.next`. Rate limit errors (codes 4, 17, 32, 613, 80000 to 80014 including 80004) are retried with exponential backoff.

## Outputs

- `reports/weekly_report_<week-end-date>.md`: full tables per account.
- Stdout: a short phone-readable summary (the same text that `--send` posts).

## Reading the result for the user

Lead with the "do this week" items. If a sudden-drop alert fired, say that first: a fall in leads while spend holds is usually a broken lead form, form-to-CRM connection or disconnected page, not a bad ad. Do not suggest pausing ads until that is ruled out.

## Files

- `scripts/weekly_report.py`: the report
- `scripts/meta_graph.py`: read-only Graph client (paging, backoff, lead counting)
- `scripts/test_weekly_report.py`: tests (`python -m pytest scripts -q`)
- `fixtures/`: demo data in real Graph API response shapes
- `config.example.yaml`, `.env.example`: copy to `config.yaml` and `.env`
