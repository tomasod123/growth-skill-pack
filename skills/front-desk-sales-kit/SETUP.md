# front-desk-sales-kit: setup

## What it does
Turns a business's own call recordings into an objection bank (most common first), then renders a one-page branded cheat sheet and a full booking playbook.
Works for a clinic front desk booking consultations or an inbound SaaS team booking demos.

## What you need
- **For rendering only:** Python 3.9+. No accounts, no keys.
- **For mining calls (optional):** a GoHighLevel sub-account with call recording on and calls made through GHL.
  - **GHL_API_KEY**: sub-account Settings > Private Integrations > Create new integration. Scopes (UI label, API id): View Contacts (`contacts.readonly`), View Conversations (`conversations.readonly`), View Conversation Messages (`conversations/message.readonly`). All read-only. Copy the token when shown.
  - **GHL_LOCATION_ID**: Settings > Business Profile (Location ID), or the id after `/location/` in the GHL URL.
  - **OPENAI_API_KEY** (optional, `--engine api` only): https://platform.openai.com/api-keys
  - Packages (use a virtualenv). Local transcription, free and private: `pip install requests openai openai-whisper`. Note `openai-whisper` pulls in PyTorch (about 2 GB) and downloads a model on first run. Light option without PyTorch: `pip install requests openai` and transcribe with `--engine api` (needs `OPENAI_API_KEY`; sends audio to OpenAI, so not for patient calls without a BAA).
  - Also `ffmpeg` (`sudo apt install ffmpeg` or `brew install ffmpeg`) and `jq` and `curl` for the probe script.
- No MCP servers needed.

## Install
1. Copy this folder to `~/.claude/skills/front-desk-sales-kit/`.
2. If you will mine calls, add the variables from `.env.example` to `~/.claude/skills/.env` and fill them in.
3. Test:
   ```
   python3 ~/.claude/skills/front-desk-sales-kit/scripts/build_kit.py ~/.claude/skills/front-desk-sales-kit/configs/example-clinic.json --out /tmp/fdsk-test
   set -a; source ~/.claude/skills/.env; set +a
   bash ~/.claude/skills/front-desk-sales-kit/scripts/probe_scopes.sh     # read-only GHL scope check
   ```
   The first renders the example kit into `/tmp/fdsk-test/`; the second prints HTTP 200 for contacts, conversations and messages.

## First run (2 minutes)
Type to Claude: **"Build a front-desk sales kit for [business name]: offer is [offer and terms], booked call is a [consultation/demo], brand colours [hex], logo at [path]. Use the starter objection checklist for now."**
You get `<slug>-cheatsheet.html` and `<slug>-playbook.html` in `./front-desk-sales-kit-output/<slug>/`, plus the config `<slug>.json` you can edit and re-render.
Later: **"Mine our GHL call recordings for objections and refresh the kit."**

## Common errors and fixes
- **401/403 on messages in `probe_scopes.sh`:** the token lacks View Conversation Messages. Add it to the Private Integration and use the new token.
- **Very few recordings found:** recording is off, or calls are made on personal phones. Turn recording on and route calls through GHL; use the starter checklist meanwhile.
- **"WARNING unreplaced tokens: X":** a `{{X}}` in a template or config value has no matching key. Add it to the config.
- **Logo missing on the page:** `LOGO_FILE` is resolved relative to the config file. Put the logo there or use a full URL.
- **Wrong font:** `BRAND_FONT` must be a Google Fonts family name (e.g. "Poppins"); otherwise the system font is used.
- **Whisper error about ffmpeg:** install ffmpeg.

## Setup time
5 minutes to render only; about 20 minutes with GHL mining and `--engine api`; 35 to 40 minutes with local Whisper (PyTorch download of about 2 GB plus the model).

## Cost per run
Free (local Whisper, GHL API reads are free). With `--engine api` transcription, about US$0.006 per minute of audio.
