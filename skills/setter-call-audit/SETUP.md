# setter-call-audit: setup

## What it does
Pulls a setter's recorded calls from GoHighLevel, transcribes them on your machine with timestamps, and scores each call on an 8-part rubric.
You get an HTML coaching scorecard: patterns, speed to lead, top 3 priorities, drills and call-by-call quotes.

## What you need
- **GoHighLevel sub-account** with call recording switched on (Settings > Phone Numbers > edit number > call recording) and calls made through GHL (desktop or the mobile app), not personal phones.
- **GHL_API_KEY**: in the sub-account, Settings > Private Integrations > Create new integration. Scopes (UI label, API id): View Contacts (`contacts.readonly`), View Conversations (`conversations.readonly`), View Conversation Messages (`conversations/message.readonly`), View Users (`users.readonly`). All read-only. Copy the token once (it is shown only at creation).
- **GHL_LOCATION_ID**: Settings > Business Profile (Location ID), or the id after `/location/` in the GHL URL.
- **OPENAI_API_KEY** (optional, only for `--engine api`): https://platform.openai.com/api-keys
- **SLACK_BOT_TOKEN + SLACK_CHANNEL_ID** (optional): https://api.slack.com/apps > your app > OAuth & Permissions (chat:write); channel id from the channel's "About" panel. Only scores and patterns go to Slack, never transcript quotes or anything that identifies a patient or lead.
- **Python 3.9+** and packages (use a virtualenv):
  - Local transcription (free, private): `pip install requests openai openai-whisper`. Note: `openai-whisper` pulls in PyTorch, about 2 GB of download, and the first run downloads the Whisper model too.
  - Light option, no PyTorch: `pip install requests openai` and run transcription with `--engine api` (needs `OPENAI_API_KEY`; sends audio to OpenAI, so not for patient calls without a BAA).
- **ffmpeg** (Whisper needs it): `sudo apt install ffmpeg` or `brew install ffmpeg`.
- No MCP servers needed.

## Install
1. Copy this folder to `~/.claude/skills/setter-call-audit/`.
2. Add the variables from `.env.example` to `~/.claude/skills/.env` and fill in `GHL_API_KEY` and `GHL_LOCATION_ID`.
3. Test access (read-only):
   ```
   set -a; source ~/.claude/skills/.env; set +a
   python3 ~/.claude/skills/setter-call-audit/scripts/pull_calls.py --list-users
   python3 ~/.claude/skills/setter-call-audit/scripts/pull_calls.py --days 1 --dry-run
   ```
   The first prints user ids and names; the second lists yesterday's calls without downloading audio.

## First run (2 minutes)
Type to Claude: **"Audit my setter's calls from the last 7 days."**
Claude asks which setter (and confirms their user id), asks you to confirm the targets in `audit-config.json`, pulls and transcribes the calls, then scores them.
The scorecard lands in `./setter-call-audit-output/<date>/<setter>-audit-<date>.html` (recordings, transcripts and `manifest.csv` sit beside it).

## Common errors and fixes
- **HTTP 401/403 on messages or recordings:** the token lacks View Conversation Messages. Edit the Private Integration, add the scope, and use the new token.
- **`--list-users` prints nothing:** the token lacks View Users. Find the id in Settings > My Staff (edit the user; the id is in the URL) and pass `--user-id`.
- **"no recording for ..."** on most calls: recording is off on that number, or calls were made from personal phones. Turn recording on and route calls through GHL.
- **Whisper error about ffmpeg:** install ffmpeg (see above).
- **Names or numbers wrong in quotes:** Whisper mishears them; re-run that file with `--model small` and check by ear before sharing.
- **Speed to lead shows 0 minutes for everyone:** an automated text fired instantly. Read `first_call_min` instead.

## Privacy
Recordings and transcripts stay on your machine. Never post patient-identifying quotes (names, numbers, health details) to Slack or any chat tool. US healthcare: call recordings are PHI under HIPAA, so only send them to a service (OpenAI API, Slack, a cloud drive) that has signed a BAA with you; otherwise use local Whisper.

## Setup time
15 minutes with `--engine api`; 30 to 40 minutes with local Whisper (PyTorch install of about 2 GB plus the model download on first run).

## Cost per run
Free with local Whisper (GHL API calls are free). With `--engine api`, about US$0.006 per minute of audio.
