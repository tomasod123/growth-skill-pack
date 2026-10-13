---
name: ad-snippet-miner
description: Weekly TEXT digest of ad-worthy customer soundbites (PRAISE / RESULTS / BEFORE-frustration) mined from the last 7 days of Fathom call recordings. Writes a Markdown + HTML digest locally (optionally posts it to one Slack DM or private channel). Each quote is verbatim, rated 1-5 for ad use, with a Fathom deep link, suggested 5-20 s clip bounds and the customer's consent status. Text only, no video cutting. Use when the user says "ad snippet miner", "mine my calls for soundbites", "testimonial quotes from calls", "find ad quotes in our Fathom calls", "ad soundbites digest", or when a weekly scheduled run fires.
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./ad-snippet-miner-output/`.

# Ad snippet miner (text digest)

Mines Fathom call transcripts for verbatim customer soundbites usable in ads and
testimonials: PRAISE, RESULTS (concrete numbers) and BEFORE-frustration quotes. One
Claude pass per call (Sonnet by default, through the `claude` CLI) scores each candidate
1-5 for ad usability and suggests 5-20 s clip bounds. Everything lands in a sqlite ledger
with quote-hash dedupe (a quote never resurfaces) and a per-customer consent flag
(none / verbal / written). Output is an internal digest. Zero candidates = no digest.

Works for any business that records customer calls in Fathom: a SaaS team's customer
check-ins and QBRs, or an agency's client calls (where the "customer" is the clinic).

## Before running

1. Load env in the SAME Bash call as every script command (each Bash call is a fresh shell):
   `set -a; source ~/.claude/skills/.env; set +a;` (needs `FATHOM_API_KEY`;
   `SLACK_BOT_TOKEN` + `SLACK_CHANNEL_ID` only if posting to Slack). If `MINER_WORKDIR` is set
   there, the ledger and digests live in that folder for interactive AND cron runs (and
   `MINER_CONFIG` is the default config); otherwise `./ad-snippet-miner-output/`.
2. Config: if `$MINER_CONFIG` / `./ad-snippet-miner-config.json` (or a path the user gives) does
   not exist, copy `~/.claude/skills/ad-snippet-miner/config.example.json` there and ask the user for: one line describing
   the business, the names of their own team (so their lines are never mined as customer
   quotes), and any known customers with consent status.

## Pipeline

1. **Fetch:** Fathom REST, `GET https://api.fathom.ai/external/v1/meetings?include_transcript=true&created_after=<N days ago>`
   with header `X-Api-Key`, cursor-paginated (`next_cursor`).
2. **Mine:** for each call not already in `processed_calls`: one `claude -p --model sonnet`
   pass, prompt on stdin, JSON array out. Calls with fewer than 8 transcript segments are
   skipped. Failed calls are retried next run, never marked processed.
3. **Ledger:** `<out>/ledger.db` (`<out>` = `--out`, else `$MINER_WORKDIR`, else `./ad-snippet-miner-output`): `quotes` (UNIQUE quote_hash), `processed_calls`, `consent`
   (seeded from config `consent_seed`).
4. **Digest:** top 10 unused quotes rated `min_rating`+ (default 3), sorted by rating. Each
   entry: quote, customer slug, category, rating, Fathom deep link (`url?timestamp=<s>`),
   clip bounds, consent flag. Written to `<out>/digest-<ISO week>.md` and `.html` (the HTML
   picks up `tokens.css` beside it if you drop your brand tokens there). When written, ALL
   unused quotes are stamped with the ISO week so nothing resurfaces.
5. **Optional Slack:** `--slack` posts the same digest to `SLACK_CHANNEL_ID` (a user id opens
   a DM). Internal only.
6. **Optional schedule:** `scripts/run_weekly.sh` is a cron wrapper (full crontab line in SETUP.md; it reads `MINER_WORKDIR`, so it shares the interactive ledger). Cron it hourly; it gates
   on `MINER_TZ` (Monday, 08:00-10:59) with a per-ISO-week stamp, so it runs Monday morning
   year-round, retries twice, and never sends more than one digest a week.

## Commands

```
set -a; source ~/.claude/skills/.env; set +a; S=~/.claude/skills/ad-snippet-miner/scripts
python3 $S/miner.py --check-fathom                                  # read-only access test
python3 $S/miner.py --days 7 --dry-run --config ad-snippet-miner-config.json   # preview, writes nothing
python3 $S/miner.py --days 7 --write  --config ad-snippet-miner-config.json    # digest files
python3 $S/miner.py --days 7 --slack  --config ad-snippet-miner-config.json    # files + Slack
python3 $S/miner.py --check-slack                                   # verify Slack target, no message
python3 $S/miner.py consent list
python3 $S/miner.py consent clinic_a written                        # after written consent lands
```

Run any command line above in ONE Bash call together with the block's first line. With
`MINER_CONFIG` set, `--config` can be dropped. Default output dir: `$MINER_WORKDIR`, else
`./ad-snippet-miner-output/` (change with `--out`; the `consent` subcommand uses the same
default or `SNIPPET_LEDGER`). First run on a big backlog: use
`--days 30 --limit-calls 10 --dry-run` to see quality before mining everything.

## Hard rules

- Internal only. Never post the digest to a customer-facing channel, never message a customer.
- Sonnet (or another cheap model) for the mining pass; the task is extraction, not reasoning.
- Noise budget: max one digest per week on the schedule; zero candidates = total silence.
- Speaker labels are ASR guesses: names get misspelled and customer lines get pinned on
  your own team. The prompt asks the model to judge from context and mark doubt with "?",
  and the digest footer says to verify on video before using anything.
- A quote needs WRITTEN consent before it goes anywhere near an ad. The consent column
  tracks status; the digest flags it, a human acts on it.
- Health and medical ads: a patient result or testimonial may be restricted (Meta health
  policies, UK ASA/CAP, Australian AHPRA bans testimonials outright, US FTC needs
  substantiation and HIPAA authorisation for patient stories). Treat RESULTS quotes as leads
  for a compliant ad, not copy to paste. If the `persona-qc` skill is installed, run its
  compliance lens on any ad built from a quote.
- Video clip cutting is out of scope; the clip bounds tell your editor where to cut.
