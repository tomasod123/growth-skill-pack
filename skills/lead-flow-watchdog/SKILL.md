---
name: lead-flow-watchdog
description: Read-only daily check that Meta lead ad leads are reaching GoHighLevel. Per business, compares yesterday's Meta lead form submissions with GHL contacts that look like Meta leads and flags integration breaks, untagged leads, delivery drops, CPL spikes and spend with no leads. Use when the user says "lead flow check", "watchdog", "are leads reaching the CRM", "Meta to GHL sync check", "why did leads drop", "daily lead check", "lead alert", or "check the Facebook lead integration".
---

# Lead flow watchdog

Read-only on Meta and GoHighLevel. It never edits contacts, workflows or ads.

## How to run

From the skill folder:

```bash
python scripts/watchdog.py --demo                 # fixture data, no API calls, safe to try
python scripts/watchdog.py                        # check yesterday for every business
python scripts/watchdog.py --day 2026-03-10       # check a given day
python scripts/watchdog.py --business "Example Clinic"
python scripts/watchdog.py --send                 # also post to Slack if anything is WARNING or worse
```

Default is print and write a file. Only use `--send` when the user asks for it.
If `config.yaml` or `.env` is missing, point the user to `SETUP.md`.

## What it checks (yesterday, per business)

| Check | Fires when | Severity |
|---|---|---|
| Processing break | 3+ CRM contacts with a Meta source or UTM, none carry the Meta tag | CRITICAL |
| Partial processing break | 5+ Meta-source contacts, under 30% tagged | WARNING |
| Integration break | Meta recorded leads, CRM has 0 Meta-tagged contacts | CRITICAL |
| CRM gap | 5+ Meta leads, CRM has under half as many | WARNING |
| Spend with no leads | 0 Meta leads, spend at least 1x target CPL | CRITICAL (WARNING if CRM still got Meta contacts) |
| Delivery drop | leads under 50% of the 7-day daily average (average 2+ a day) | WARNING (INFO during ramp-up) |
| CPL vs target | CPL over 2x target (WARNING), over 1.5x (INFO) | |
| CPL vs trailing | CPL over 2x the previous 7 days' CPL | WARNING |
| Data check | a pull failed | INFO, dependent checks skipped |

All thresholds are plain defaults, editable in `config.yaml`. With no Meta ad account set, only CRM checks run (processing break, delivery drop on CRM counts).

## Counting rules (do not change)

- Meta leads = `action_type == "lead"` only. `onsite_conversion.lead_grouped` and `offsite_conversion.fb_pixel_lead` repeat the same leads.
- A CRM Meta lead = a contact created that day with a configured tag (exact match), or a source containing a configured word, or a configured UTM source. Tagged and source are tracked separately so untagged Meta leads are still seen.
- GHL merges contacts that share an email or phone. A repeat lead does not create a new contact, so the CRM count is often a little below Meta's. Only large gaps alert.

## GHL API notes

- `POST https://services.leadconnectorhq.com/contacts/search` with `pageLimit` as a number (a string gives 422 or an empty list).
- Headers: `Version: 2021-07-28`, `Authorization: Bearer <token>`, and a normal browser `User-Agent`.
- `dateAdded` range filter, paging stops at the reported `total`, results de-duplicated by contact id.

## Outputs

- `alerts/watchdog_<day>.md`: table of all businesses, then each alert with likely cause and next steps.
- Stdout: short summary, worst first (the same text `--send` posts).
- Aggregates only. No contact names, emails or phone numbers appear in any output.

## Reading the result for the user

Lead with CRITICAL items. An integration or processing break means real people are not being called: tell the user to fix the sync first and to pull yesterday's leads straight from Meta so nobody is missed. A single day of high CPL is noise; say so.

## Files

- `scripts/watchdog.py`: daily run and output
- `scripts/detect.py`: the checks (pure functions)
- `scripts/ghl_client.py`: read-only GHL contact search and Meta-lead matching
- `scripts/meta_graph.py`: read-only Meta Graph client (paging, rate-limit backoff, lead counting)
- `scripts/test_watchdog.py`: tests (`python -m pytest scripts -q`)
- `fixtures/`: demo data in real API response shapes
- `config.example.yaml`, `.env.example`: copy to `config.yaml` and `.env`
