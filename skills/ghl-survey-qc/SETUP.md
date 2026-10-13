# ghl-survey-qc setup

## What it does
Reads a GoHighLevel survey's or form's full settings from its public widget page (no key, no submission) and flags the known traps: invisible Continue button, unbranded mobile footer, nobody notified, contact details asked last.
Measures whether the first question and its Next button clear the fold at four real phone sizes, and checks the funnel tells one story.

## What you need
- The survey or form id (builder URL, or the embed code `/widget/survey/<id>`), and the live page URL that embeds it.
- Python 3.8+ (stdlib only). On macOS also `pip3 install certifi` so TLS works.
- Node 22+ (global WebSocket): `node --version`. Install from https://nodejs.org or `nvm install 22`.
- Google Chrome or Chromium installed. Linux: `sudo apt install chromium` (or Google Chrome .deb). If it is not on a standard path, set **CHROME_PATH** (or **CHROME_BIN**).
- Optional **GHL_API_KEY** (only for the calendar read): sub-account **Settings > Private Integrations > Create new Integration**, tick read-only scopes `calendars.readonly`, `workflows.readonly`, `locations/customValues.readonly`, copy the `pit-` token (shown once). If the menu item is missing, an agency admin enables Private Integrations (Agency Settings).
- Optional **GHL_LOCATION_ID**: **Settings > Business Profile** ("Location ID"), or the id after `/location/` in the app URL.
- API base for the calendar read: `https://services.leadconnectorhq.com`, header `Version: 2021-04-15` for calendars (2021-07-28 elsewhere), `Authorization: Bearer <token>`.
- Optional **GHL_WIDGET_HOST** / **FOLD_IFRAME_HOSTS**: only for white-label accounts whose widgets load from their own link domain (look at the embed code's iframe src).
- No MCP servers.

## Install
1. Copy this folder to `~/.claude/skills/ghl-survey-qc/`.
2. Add any vars you need from `.env.example` to `~/.claude/skills/.env` (all optional).
3. Test: `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ghl-survey-qc/scripts/audit_survey.py --help` and `node --check ~/.claude/skills/ghl-survey-qc/scripts/fold.mjs`
4. Prove it works on a real survey (read-only, public page): `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ghl-survey-qc/scripts/audit_survey.py <surveyId>`

## First run (2 minutes)
Type to Claude: **"QC the survey on https://example.com/apply before it goes live. Survey id <id>. Check desktop and mobile."**
You get every survey setting, the desktop-vs-mobile split, the trap findings (BLOCKER/HIGH/MED/LOW) and a fold table per phone size. JSON and screenshots land in `./ghl-survey-qc-output/`.

## Common errors and fixes
- **"could not read the widget page" / no __NUXT_DATA__**: the account is white-label. Pass `--host https://<your link domain>` or the full widget URL from the embed code.
- **CERTIFICATE_VERIFY_FAILED on macOS**: `pip3 install certifi`.
- **fold.mjs prints "could not find the form"**: the survey iframe is on a white-label domain. Set `FOLD_IFRAME_HOSTS=<that domain>`.
- **Chrome exits at once on a Linux server, connect refused**: no usable sandbox. The script adds `--no-sandbox` on Linux; if you use a custom wrapper, add it there.
- **The fold looks fixed in the file but fails live**: the fix was never pasted, or you measured a cached page. The script disables the cache; curl the live URL to confirm the code is there.
- **From the second load a "Submission in progress" dialog covers the form**: a previous visit started the survey in that browser profile. The script uses a fresh temporary profile per run; in your own browser use a private window.
- **Desktop looks branded, mobile is GHL blue**: not a bug, they are separate saved settings. Redo the values in the builder's phone view.

## Setup time
10 minutes (most of it installing Chrome/Node if missing).

## Cost per run
Free.
