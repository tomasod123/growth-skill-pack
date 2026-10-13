---
name: growth-data-hub
description: Pull Meta Ads, Google Ads, GA4, Microsoft Clarity and GoHighLevel into one funnel per channel (spend > clicks > sessions > leads > booked > showed > won), find the constraint against editable benchmarks, and write the 5 things to do this week. Use when the user says "growth report", "pull all my data", "where is the funnel leaking", "what's the constraint", "cost per booked call", "show rate by channel", "join Meta and GHL", "Google Ads vs CRM", "Clarity dead clicks on the landing page", "weekly numbers", or "what should we do this week". Read-only on every platform.
---

# growth-data-hub

One command pulls five sources into one place and tells you what to fix first.

```bash
cd ~/.claude/skills/growth-data-hub     # SETUP.md creates .venv; use python3 if the deps are installed globally
.venv/bin/python hub.py --demo          # sample data, no keys
.venv/bin/python hub.py --check         # which sources are ready, what is missing
.venv/bin/python hub.py --days 28       # real run (window ends yesterday)
.venv/bin/python hub.py --days 7 --only meta,ghl
.venv/bin/python hub.py --config clients/acme.yaml --env clients/acme.env --out out/acme   # one folder per business
```

Outputs in `out/` (demo runs go to `out/demo/` so they never mix with real data): `ACTIONS.md` (read this first), `report.html` (one page, phone friendly, no JS), `report.json` (everything, for follow-up questions).

## What it does
1. **Pulls** (each source optional; a missing key skips that source and says why):
   - Meta Marketing API: spend, impressions, link clicks, CTR, CPM, leads (`action_type == 'lead'` only) by campaign and ad.
   - Google Ads API: cost, clicks, impressions, conversions by campaign; search impression share lost to budget and rank; recent change history.
   - GA4 Data API: sessions, engaged sessions, key events by session source/medium x landing page.
   - Microsoft Clarity Data Export: sessions, scroll depth, dead clicks, rage clicks, quick backs by URL (last 1-3 days only; 1 call per run, cached for the day).
   - GoHighLevel: contacts created in the window, opportunity stages, appointments (booked, showed, no-show), by source and tag.
2. **Joins** them per channel using the rules in `config.yaml > channels` (GA4 source/medium regex; CRM click ids, UTMs, session source, tags). Leads, bookings, shows and wins come from the CRM; spend and clicks from the ad platforms. Unmatched traffic is "Organic and other".
3. **Finds the constraint**: the funnel step furthest below its floor in `benchmarks.yaml`, weighted by how much spend flows through it. Also flags: ads spending 2x the CPL target with no leads, Search campaigns losing share to budget while converting under target, share lost to rank, platform leads not reaching the CRM, and the landing pages with the worst Clarity signals plus which channels feed them.
4. **Writes 5 actions**: the constraint first, then by severity. Each has the triggering number, an owner role and minutes.

## How Claude should run it
1. If `config.yaml` or `.env` is missing, run `.venv/bin/python hub.py --demo`, show the user `out/demo/ACTIONS.md` (say clearly it is sample data), and point them to `SETUP.md`. Don't ask for keys in chat; they go in `.env`.
2. Otherwise run `.venv/bin/python hub.py --check`, then `.venv/bin/python hub.py --days <N>` (default 28; 7 for a weekly check-in). Run it in the foreground; it takes under a minute.
3. Read `out/ACTIONS.md` back to the user **in plain words**: the constraint in one sentence, then the 5 actions as a numbered list with the number that triggered each, who and how long. Quote the numbers exactly as written.
4. Say which sources were skipped or errored and any **Warnings** (bottom of ACTIONS.md; each carries its fix). If the run exits with code 2, ACTIONS.md says "No report": relay the per-source fixes, never older numbers.
5. For follow-ups ("which ads?", "which pages?", "by campaign?") read `out/report.json` (`meta.ads`, `google_ads.campaigns`, `ga4.by_landing_page`, `clarity.pages`, `ghl.by_stage`, `findings`) rather than re-running.
6. Offer `out/report.html` as the shareable one-pager.

## Reading the numbers right
- **CRM leads lower than Meta leads** is normal up to ~20%: GoHighLevel merges contacts on email and phone, so repeat enquiries don't make new contacts. Bigger gaps = an unmapped lead form or a broken integration.
- **Show rate** counts only calls that have happened (showed / (showed + no-show)). Future bookings don't drag it down.
- **Clarity** covers the last 1-3 days only. Treat it as a spot check of page behaviour, not a trend. The API allows about 10 calls per project per day; the hub caches each day's answer (`--refresh-clarity` forces a new call).
- **Google Ads CTR** uses Search campaigns only (Performance Max impressions would skew it). Impression share fields are empty for non-Search campaigns.
- **Benchmarks are a starting point.** Set `costs.cpl.max` and `costs.cost_per_booked.max` from real economics before trusting the cost flags.
- Never sum accounts in different currencies; run one config per currency.

## Rules
- Read-only everywhere. No write, mutate, pause or budget calls exist in this code; actions are for a human to take.
- Secrets live only in `.env` (or real environment variables). Never print them or paste them into chat.
- One broken source never sinks the report; it shows as `error` with the API's message.

## Files
`hub.py` (CLI) · `sources/` (meta, google_ads, ga4, clarity, ghl: each has `missing`, `fetch`, `parse`) · `funnel.py` (join) · `constraint.py` (constraint + actions) · `render.py` (HTML) · `benchmarks.yaml` · `config.example.yaml` · `.env.example` · `fixtures/` (demo data in real API shapes) · `tests/` (`.venv/bin/python -m pytest -q tests`) · `tools/google_oauth.py` (one-time Google Ads refresh token).
