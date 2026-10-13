# ghl-funnel-build setup

## What it does
Runs a GoHighLevel funnel build (landing, booking, confirmation, survey, share preview, tracking) through the QC gates that catch silent failures: a paste-block linter and a headless-browser sweep at real phone and desktop widths.
Includes the funnel tracking standard (path-keyed GA4 + Meta events), launch checklist, page-speed findings and a VA handover process.

## What you need
- A GoHighLevel account (agency or sub-account; white-label GHL works the same).
- Python 3.8+ (stdlib only) for `block_lint.py`.
- Node 22 or newer (global `fetch` and `WebSocket`) and Google Chrome or Chromium for `qc_sweep.mjs`.
  - macOS: install Chrome normally. Ubuntu/Debian: `sudo apt install chromium` (or install Google Chrome). Node: `nvm install 22` or your package manager.
- Optional, for the read-only API checks:
  - `GHL_API_KEY`: in the sub-account, Settings > Private Integrations > Create new integration, scopes `funnels/funnel.readonly`, `calendars.readonly`, `calendars.write` (OPTIONAL write scope, only if you will repoint calendar redirects; Claude must ask you before any PUT/POST), `contacts.readonly`. Copy the token shown once.
  - `GHL_LOCATION_ID`: Settings > Business Profile (the Location ID field), or the id after `/location/` in the sub-account URL.
  - `CHROME_PATH` (or `CHROME_BIN`): only if Chrome is not in a standard location.
- No MCP servers required.

## Install
1. Copy this folder to `~/.claude/skills/ghl-funnel-build/`.
2. If you will use the API checks, add the variables from `.env.example` to `~/.claude/skills/.env`. Script commands are run as `set -a; source ~/.claude/skills/.env; set +a; <command>` in one call.
3. Test (no network needed):
   ```bash
   set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ghl-funnel-build/scripts/block_lint.py ~/.claude/skills/ghl-funnel-build/templates/tracking-head-code.html
   set -a; source ~/.claude/skills/.env; set +a; node ~/.claude/skills/ghl-funnel-build/scripts/qc_sweep.mjs
   ```
   The first prints a lint report (a warning about HTML comments is expected for that file); the second prints the usage line.

## First run (2 minutes)
Save a page's Custom HTML into `block.txt`, then type: `Run ghl-funnel-build QC on block.txt and on https://<your-funnel-domain>/demo-booking, form selector #lead-form input.`
You get back: lint FAIL/warn lines per block, a per-width table (overflow, broken images, fallback fonts, HTTP errors, BELOW FOLD), and a list of fixes. Reports and any notes land in `./ghl-funnel-build-output/<funnel-name>/`.

## Common errors and fixes
- **`Chrome/Chromium not found`:** install Chrome/Chromium or set `CHROME_PATH` (or `CHROME_BIN`).
- **`ECONNREFUSED` / no output on a Linux server:** Chrome aborted with "No usable sandbox". The script adds `--no-sandbox` on Linux; if you run Chrome yourself, add it too. Also pick a free `--port` if another job uses 9422 (`EADDRINUSE`).
- **Signed out of your Google accounts after a run:** you pointed `--user-data-dir` at your real Chrome profile. Always use a new empty folder.
- **Numbers look wrong or old:** CDN cache. The script adds `?cb=<timestamp>`; also republish the funnel (Save is not Publish) and use a fresh profile.
- **Headline renders in Times:** a CSS variable is undeclared or the block does not link its own fonts. `block_lint.py` names the variable.
- **Events not firing:** page paths must contain `booking` / `confirm`; the pixel must be in the funnel Events tab (cloned funnels lose it).
- **Survey looks right on desktop, wrong on phone:** GHL stores survey and page settings per device. Switch the editor's device toggle before editing.

## Setup time
10 minutes (5 if Node 22 and Chrome are already installed).

## Cost per run
Free (local scripts; the optional GHL API checks are read-only and free).
