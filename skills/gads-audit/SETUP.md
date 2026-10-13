# gads-audit setup

## What it does
A read-only Google Ads audit agent: account health, keyword research and market size, landing page checks, and an organic/paid SERP check.
It writes an action spreadsheet, a draft email to whoever runs the account, and an internal summary page. It never changes the account.

## What you need

**Accounts**
- A Google Ads manager account with the audited account linked under it.
- A DataForSEO account (pay-as-you-go, minimum top-up applies) for keyword research and SERP checks: https://dataforseo.com/

**Google Ads API access (5 variables).** Install the **gads-common** skill first and follow its SETUP.md exactly; it walks through:
- `GOOGLE_ADS_DEVELOPER_TOKEN`: manager account > **Tools > API Center** (newer UI: Admin > API Center). Test-account-only tokens fail on real accounts; apply for **Explorer** or **Basic** access on the same page.
- `GOOGLE_ADS_CLIENT_ID` / `GOOGLE_ADS_CLIENT_SECRET`: Google Cloud Console > APIs & Services > Library > enable **Google Ads API**; set up the **OAuth consent screen**; then Credentials > Create credentials > OAuth client ID > **Desktop app**.
- `GOOGLE_ADS_REFRESH_TOKEN`: run `python3 ~/.claude/skills/gads-common/scripts/gads.py login --save`.
- `GOOGLE_ADS_LOGIN_CUSTOMER_ID`: the manager account id, 10 digits, no dashes.

**DataForSEO (modules 2 and 4)**
- `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD`: sign in at https://app.dataforseo.com/ > **API Access** (https://app.dataforseo.com/api-access). The login is your account email; the API password is generated on that page and is NOT your dashboard password.
- Add credit under Billing. A full audit uses about US$0.55-1.00.

**Optional**
- `PSI_API_KEY`: Google Cloud Console > APIs & Services > Library > enable **PageSpeed Insights API** > Credentials > Create credentials > **API key**. Adds PageSpeed field data to module 3. Without it, module 3 still measures locally.
- `GADS_AUDIT_OWNER`, `GADS_AUDIT_SENDER`: names used in the "who" column and on the draft email.
- `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`: only for `build_outputs.py --supabase`. Your Supabase project > Project Settings > API. Run `references/supabase-schema.sql` once in the SQL editor first.

**Software**
- Python 3.9+. Optional: `python3 -m pip install openpyxl certifi` (openpyxl for actions.xlsx; without it you get CSVs only. certifi if you see CERTIFICATE_VERIFY_FAILED).
- Module 3 only: Google Chrome or Chromium (`/usr/bin/google-chrome`, `/usr/bin/chromium`, or the standard macOS app path; else set `CHROME_PATH` (or `CHROME_BIN`) in `~/.claude/skills/.env`, or pass `--chrome PATH`), and **Node.js 22+** (`node -v`; install from https://nodejs.org or `nvm install 22`; set `NODE_BIN` if an older node is first on PATH).
- No MCP servers are required.

## Install
1. Install **gads-common** first (`~/.claude/skills/gads-common/`), then copy this folder to `~/.claude/skills/gads-audit/` so the two sit side by side (the scripts load `../gads-common/scripts/gads.py`; set `GADS_COMMON_PY` if you put it elsewhere).
2. Add the variables from `.env.example` to `~/.claude/skills/.env` (Google Ads ones are shared with gads-common).
3. Prove access (both calls are read-only; the DataForSEO balance call is free):
```bash
set -a; source ~/.claude/skills/.env; set +a
python3 ~/.claude/skills/gads-common/scripts/gads.py doctor
python3 ~/.claude/skills/gads-audit/scripts/dfs_client.py --balance
python3 ~/.claude/skills/gads-audit/scripts/audit_account.py --help
```

## First run (2 minutes)
Type to Claude: **"Run a Google Ads audit on account XXXXXXXXXX. The ads should point at https://example.com/landing-page and the priority area is Chicago. Start with the account audit only."**
Claude runs module 1 (free, about 20 seconds) and replies with the rank-vs-budget verdict and the critical findings first. Files land in `./gads-audit-output/<slug>-<date>/` (ACCOUNT-AUDIT.md and account-audit.json). Say "now do keyword research, landing page and competitors, then build the outputs" for the full run, which adds KEYWORDS.md, LANDING-PAGE.md, COMPETITORS.md, actions.xlsx, CONTRACTOR-EMAIL.md and SUMMARY.html to the same folder.

## Common errors and fixes
- **`[gads-audit] missing dependency: .../gads-common/scripts/gads.py`**: gads-common is not installed beside this skill. Install it, or set `GADS_COMMON_PY` to its gads.py.
- **`DEVELOPER_TOKEN_NOT_APPROVED`, `USER_PERMISSION_DENIED`, `invalid_grant`**: Google Ads access problems; run `gads.py doctor` and follow gads-common's SETUP.md error list.
- **`[dfs] 401`**: wrong DataForSEO password. Use the API password from app.dataforseo.com/api-access, not the dashboard one.
- **Keyword research returns nothing at $0 cost (40400 Not Found)**: wrong endpoint path. The script uses `dataforseo_labs/google/keyword_suggestions/live`; do not switch it to `keywords_data/...`.
- **"No paid listings" on every competitor query**: the instrument, not the market. Run a control term that certainly carries ads; if it also returns zero, only trust the organic half and use Auction Insights in the Google Ads UI.
- **Module 3 says the page is blocked (401/403/429)**: a bot challenge (Cloudflare etc.), not an outage. Every other measurement on that page is unreliable; check it by hand on a phone.
- **`[lp] need node 22+`**: install Node 22 or set `NODE_BIN`.
- **`UNRECOGNIZED_FIELD` in module 1**: the API version renamed a field (v25: `campaign.start_date_time`). Update the GAQL in audit_account.py, or pin GOOGLE_ADS_API_VERSION.
- **Impression share in the email no longer matches the account**: it matures through the day. Re-pull right before sending and quote the direction when impressions are under about 100.

## Setup time
About 10 minutes on top of gads-common (DataForSEO sign-up and top-up, optional Chrome/Node). Allow 40 minutes if starting from nothing.

## Cost per run
Google Ads API: free. DataForSEO: about US$0.10-0.60 for keyword research plus about US$0.0035 per SERP query per pass; a full audit with 10 seeds and 3 competitor passes of 5 terms is about US$0.55-1.00. PageSpeed Insights: free within quota.
