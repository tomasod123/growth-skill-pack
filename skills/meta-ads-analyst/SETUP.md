# meta-ads-analyst setup

## What it does
Turns Meta ads screenshots, CSV exports or live API pulls into a read graded against your own targets: money, pipeline and diagnostics layers, the bottleneck step, and one of five calls per ad.
Optional live data mode joins Meta spend with GoHighLevel leads, bookings, quality tags and speed to lead for a recurring audit.

## What you need
- Screenshot / export mode: nothing but Claude Code and Python 3. Works out of the box.
- Live data mode (optional):
  - `META_ACCESS_TOKEN`: Meta Business Settings > Users > System users > Add > Assign assets > your ad account (View performance) > Generate new token, choose your app, scope `ads_read`, token expiration **Never** (otherwise it dies after 60 days and the recurring audit fails). No app yet: developers.facebook.com > My Apps > Create app > Business, add the Marketing API product.
  - `META_AD_ACCOUNT_ID`: Ads Manager account dropdown (number under the account name) or Business Settings > Accounts > Ad accounts.
  - `META_CAMPAIGN_ID` (optional): Ads Manager > Campaigns > add the "Campaign ID" column.
  - `META_GRAPH_VERSION` (optional): Graph API version, default `v21.0`. When Meta retires it (calls fail with an "unsupported version" error), set the current version from developers.facebook.com/docs/graph-api/changelog, for example `v22.0`.
  - `GHL_API_KEY`: in the GoHighLevel sub-account, Settings > Private Integrations > Create new integration. Read-only scopes: contacts.readonly, opportunities.readonly, calendars.readonly, calendars/events.readonly, conversations.readonly, conversations/message.readonly, locations.readonly. Copy the token once (it is shown only once).
  - `GHL_LOCATION_ID`: sub-account Settings > Business Profile (Location ID), or the id in the app URL after `/location/`.
  - `GHL_PIPELINE_ID` (optional): run `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/meta-ads-analyst/scripts/ghl_pull.py --list-pipelines`.
  - `SLACK_BOT_TOKEN` + `SLACK_CHANNEL_ID` (optional): api.slack.com/apps > Create app > OAuth & Permissions > scope `chat:write` > Install > Bot User OAuth Token; channel id from the channel's "About" panel. Invite the bot to the channel.
- Python packages: only `pip install certifi` (fixes SSL on macOS / some Linux installs). Everything else is the standard library. Exports are read as CSV.
- Your CRM must tag lead quality (for example a tag set by a form answer) and your ads must carry `utm_content={{ad.name}}` for the per-ad qualified join.
- No MCP servers required.

## Install
1. Copy this folder to `~/.claude/skills/meta-ads-analyst/`.
2. `cp ~/.claude/skills/meta-ads-analyst/config/analyst.example.json ~/.claude/skills/meta-ads-analyst/config/analyst.json` and fill in your targets (CAC, front-end cash ROAS floor, CPL, booking, show and close rates, patience and budget-step rules).
3. Live data mode: add the vars from `.env.example` to `~/.claude/skills/.env`.
4. Test (no network):
```bash
python3 ~/.claude/skills/meta-ads-analyst/scripts/funnel_math.py --spend 1000 --leads 25 --bookings 10 --shows 7 --closes 2 --cash 3000 --config ~/.claude/skills/meta-ads-analyst/config/analyst.json
```
Live access test (read-only):
```bash
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/meta-ads-analyst/scripts/meta_pull.py --no-extras --out ./meta-ads-analyst-output/test/meta.json | head -20
python3 ~/.claude/skills/meta-ads-analyst/scripts/ghl_pull.py --list-pipelines
```

## First run (2 minutes)
Type: `Here are my Ads Manager screenshots for the last 14 days. Be my Meta ads analyst: grade it against my targets, find the constraint, and tell me what to scale, kill or change this week.`
Live mode: `Run meta-ads-analyst in live data mode for the last 7 days.`
You get a "Do this week" list, a verdict, the money / pipeline / diagnostics tables, a GROW / KEEP / ADJUST / TOO EARLY / STOP call per ad and a creative diversity check. Files land in `./meta-ads-analyst-output/<date>/` (report.md, plus meta.json / ghl.json in live mode).

## Recurring audit (optional): scripts/run.sh
`run.sh` loads `~/.claude/skills/.env`, pulls Meta (and GHL if `GHL_API_KEY` + `GHL_LOCATION_ID` are set) into `$OUT_ROOT/<date>/` (default `./meta-ads-analyst-output/` under the folder you run it from), then runs headless `claude -p` to write `report.md` / `report.html`. `SKIP_CLAUDE=1` does the pulls only; `GHL_PULL_ARGS` passes extra flags to `ghl_pull.py` (space-separated, no quoted values, so tags must not contain spaces; for example `GHL_PULL_ARGS="--qualified-tag qualified --exclude-names test"`).
- **Permissions:** headless Claude cannot answer permission prompts, so it needs tools pre-allowed. `run.sh` passes `--allowedTools "$CLAUDE_ALLOWED_TOOLS"`, default `Read,Write,Edit,Glob,Grep,Bash(python3:*)` (read/write files, run python3 only). Add `,Bash(curl:*)` if you want the Slack post. `--permission-mode acceptEdits` on its own still blocks Bash. `CLAUDE_ARGS` adds other flags (space-separated, no quoted values), for example `CLAUDE_ARGS="--permission-mode bypassPermissions"`, which skips every prompt: only on a machine and account you trust. Check `claude --help` for your version.
- **Test it by hand first:** `SKIP_CLAUDE=1 bash ~/.claude/skills/meta-ads-analyst/scripts/run.sh`, then without `SKIP_CLAUDE`.
- **Cron:** cron starts with a bare PATH (no `claude`, maybe not your `python3`) and runs from `$HOME`. Find the folders with `which claude python3`, create `~/meta-ads-analyst-output/` once, then `crontab -e`:
```
PATH=<folder printed by which claude>:/usr/local/bin:/usr/bin:/bin
15 8 * * 1,3,5 cd $HOME && OUT_ROOT=$HOME/meta-ads-analyst-output /bin/bash $HOME/.claude/skills/meta-ads-analyst/scripts/run.sh >> $HOME/meta-ads-analyst-output/run.log 2>&1
```
Write the PATH line out in full with the folders `which` printed (cron does not expand variables there). With nvm, `claude` lives under `~/.nvm/versions/node/<version>/bin`. If `python3 -m certifi` fails under cron, set `SSL_CERT_FILE=` to the certifi path on its own crontab line.

## Common errors and fixes
- GHL returns HTTP 403 with "error code: 1010": the request had no browser User-Agent. Use the script as shipped (it sends one); if you call the API yourself, add a browser UA header.
- `SSL: CERTIFICATE_VERIFY_FAILED`: `pip install certifi` then `export SSL_CERT_FILE=$(python3 -m certifi)`.
- Bookings are 0 but the calendar has appointments: you were reading pipeline stages. Bookings come from per-contact appointments; a booking often does not move the stage without a workflow.
- Per-ad qualified table is empty: the ads have no `utm_content`, or the CRM has no quality tag. Add URL parameters to every ad and pass `--qualified-tag` / `--unqualified-tag` matching your tags.
- Lead counts look doubled vs another tool: this skill counts `action_type == "lead"` only; other tools add `onsite_conversion.lead_grouped` too.
- Totals bigger than the campaign: another campaign is spending; check `contamination_flag` and pass `--campaign`.
- Trend makes no sense after "we changed the budget": check `activities_last_14d`; the edit may never have been published.
- Meta error "unsupported version" / "version is deprecated": set `META_GRAPH_VERSION` in `~/.claude/skills/.env` to the current version.
- Cron run writes nothing / `claude: command not found` in run.log: the crontab PATH line is missing the folder from `which claude`.
- Headless run pulls data but no report appears: the allowed tools do not include Write / Bash(python3:*); see the permissions note above.
- Token works for a few weeks then fails with code 190: it was generated with an expiry; regenerate the system user token with expiration Never.

## Setup time
5 minutes for screenshot mode; 25 minutes with live data mode (Meta system user + GHL private integration).

## Cost per run
Free (Meta Graph API and GoHighLevel API are free to call). Live mode makes one GHL call per pipeline contact for appointments, so large pipelines take a few minutes.
