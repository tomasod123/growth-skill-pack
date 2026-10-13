---
name: setter-call-audit
description: Audit a setter's or SDR's booking calls. Pulls call recordings from GoHighLevel, transcribes them locally with Whisper (timestamps included), scores every call on an 8-dimension rubric (speed to lead, opening, discovery, qualification, objection handling, booking commitment, show-up setup, delivery), and writes a coaching scorecard with quotes, timestamps and drills. Use when the user asks to "audit my setter", "review setter calls", "score our SDR calls", "check call quality", "speed to lead audit", "qualification quality", "why are booked calls not showing", or "coach my appointment setter".
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./setter-call-audit-output/`.

# setter-call-audit

## Goal
Replace gut-feel call reviews with a scorecard backed by transcripts, timestamps and the
rubric in `references/rubric.md`. Works for a clinic front desk or setter booking
consultations, an agency setter booking strategy calls, and a SaaS SDR booking demos, as long
as the calls are made or logged through GoHighLevel (GHL) with call recording on.

## Inputs (ask for anything missing, one question at a time)
1. Setter (name, and their GHL user id; run `--list-users` to map ids to names).
2. Lookback window in days (default 1; use 7 for a weekly review).
3. Optional: specific contact or message ids for an ad-hoc audit.
4. `audit-config.json` with the business's targets. If none exists, copy
   `templates/audit-config.example.json` to the output folder and ask the user to confirm or
   change every target (speed targets, booking window, minimum sample, qualification criteria,
   compliance notes, offer terms). Do not audit against example values silently.

## Pipeline

### 0. Credentials and paths
Each Bash call is a fresh shell, so every script command below loads the shared env file in
the same call. Output folder: `./setter-call-audit-output/<YYYY-MM-DD>/` (written as `OUT` below;
use the literal path in commands).

### 1. Map users (read-only)
```bash
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/setter-call-audit/scripts/pull_calls.py --list-users
```
Prints `user_id  name  role`.
**Hard rule:** if a user id is not confirmed by the user, ask before attributing any call to
a person. Never assume.

### 2. Pull calls and recordings (read-only)
```bash
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/setter-call-audit/scripts/pull_calls.py --user-id USER_ID_HERE --days 7 --out ./setter-call-audit-output/$(date +%F)
```
Writes `$OUT/manifest.csv` (label, message id, contact id, direction, duration, call time,
contact created, `speed_to_lead_min`, `first_call_min`, `outbound_call_attempts`) and
`$OUT/recordings/*.wav`. File names use message id, direction and duration only (no lead names).
Use `--dry-run` first on a big window to see the call count. A long pull can take several
minutes: give the Bash call a long timeout rather than piping through `tail`.

### 3. Transcribe (local by default)
```bash
set -a; source ~/.claude/skills/.env; set +a; OUT=./setter-call-audit-output/$(date +%F); python3 ~/.claude/skills/setter-call-audit/scripts/transcribe_calls.py $OUT/recordings $OUT/transcripts --model base
```
Each line is `[mm:ss] text`. Use `--model small` when accents or line noise make `base` hard
to read. Local Whisper is free and private but pulls in PyTorch (about 2 GB). `--engine api`
is the light option (only `pip install openai`, needs `OPENAI_API_KEY`) but sends audio to
OpenAI: only with the user's OK, and never for patient calls without a signed BAA.
Skip voicemails and calls where the lead never spoke; list them separately (they still count
for persistence).

### 4. Score every call
Read `references/rubric.md`. For each call, score all 8 dimensions PASS / PARTIAL / MISS / N/A
with one quote and its `[mm:ss]` timestamp per score. Use the manifest for speed to lead
(`first_call_min`, since automated texts make `speed_to_lead_min` look instant) and attempts.
Transcripts do not label speakers: infer the setter from context (who introduces the
business) and say so when unsure.

### 5. Find the patterns
Count each dimension across calls. Rank the top 3 recurring misses by impact on booked and
shown calls (usually: booking commitment and show-up setup first, then discovery and
qualification, then delivery).

### 6. Write the deliverable
Fill `templates/scorecard.html` and save as `$OUT/<setter-slug>-audit-YYYY-MM-DD.html`
(plus a Markdown copy if asked). It must contain:
- Header banner: DIRECTIONAL if calls < `min_calls_for_judgement`; ramp note if the setter is inside `ramp_days`.
- Scorecard table (8 dimensions, pass / partial / miss counts, one-line pattern).
- Speed-to-lead table.
- Top 3 coaching priorities with quotes and timestamps.
- 3 drills: what the lead says, the target line, what good sounds like.
- Call-by-call cards.
- A training-session agenda (role-plays built from the real objections heard).
Optional: apply your brand tokens (e.g. `~/.claude/brand/tokens.css`). Optional delivery:
post a short summary to Slack if `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID` are set, or upload
the HTML to your shared drive. The Slack summary carries scores and patterns only: never post
transcript quotes, lead names, numbers or health details to Slack (patient-identifying quotes
stay in the local HTML). Ask before sending anything to the setter.

## Hard rules
- **Read-only on GHL.** No writes, no tags, no notes.
- **Behaviour, not character.** Quote what was said against the rubric. Never assess attitude, effort, honesty or personality, in the report or in chat.
- **Coaching frame.** Every miss becomes a drill ("practise this line"), not a verdict.
- **Sample size.** Below the minimum sample, say the read is directional, in the header.
- **Privacy.** Recordings and transcripts stay local. No lead names, phone numbers or health details in the deliverable; refer to calls by label. For healthcare calls treat recordings and transcripts as PHI: keep them on an encrypted machine, delete them when the audit is done if your policy says so, and never paste them into Slack or chat tools. In the US, HIPAA applies: only use a third-party service (API transcription, Slack, cloud drives) for PHI if it has signed a BAA with you.
- **Attribution.** Confirm the user id to person mapping before attributing.

## Commands the user might type
- "audit my setter" (lookback 1 day, asks which setter)
- "audit [setter name] this week" (lookback 7 days)
- "score these calls: [message ids]" (ad-hoc)

## Gotchas
- 401/403 on `/conversations/{id}/messages` or the recording endpoint = the Private Integration token lacks **View Conversation Messages** (`conversations/message.readonly`). Contacts and conversations can work while recordings fail.
- `/users/` needs the **View Users** scope (`users.readonly`); without it, ask the user for the setter's id (Settings > My Staff > edit user shows it in the URL).
- No recording on a call = recording is off for that number or the call was made from a personal mobile. Calls off-system are invisible to the audit: say so, and recommend routing every call through GHL.
- Conversation search sorts by last message, so a lead who replied today pulls in old calls; the script filters each call by its own date.
- Whisper mishears names and numbers. Do not pass a "names" prompt on short clips (it hallucinates them into the text); check proper nouns by ear before quoting.
- Whisper needs `ffmpeg` on the PATH.

## Self-improvement
After each audit, if a new pattern appeared that the rubric does not cover, add one generic
bullet to `references/rubric.md` under the right dimension (no names, no identifying quotes).
