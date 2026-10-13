# growth-data-hub: setup

**What it does:** pulls Meta Ads, Google Ads, GA4, Microsoft Clarity and GoHighLevel into one funnel per channel (spend to won), finds the step that leaks most against your benchmarks, and writes the 5 things to do this week.
Every source is optional: connect one, run it, add the rest later.

## What you need

| Source | Account access you need | Env var / config key | Where to get it |
|---|---|---|---|
| Meta | Admin on the Business portfolio that owns the ad account | `META_ACCESS_TOKEN` | System user token with **ads_read** (steps below) |
| | | `meta.ad_account_id` (config) | Ads Manager, account dropdown: the number (with or without `act_`) |
| Google Ads | A Google user that can see the account; a manager (MCC) account for the developer token | `GOOGLE_ADS_DEVELOPER_TOKEN` | Manager account > Admin > **API Center** (only shows in a manager account) |
| | | `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET` | Google Cloud > APIs & Services > Credentials > OAuth client ID (**Desktop app**) |
| | | `GOOGLE_ADS_REFRESH_TOKEN` | `.venv/bin/python tools/google_oauth.py` |
| | | `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | Only when access comes through a manager account: the manager's 10-digit id |
| | | `google_ads.customer_id` (config) | Top right of the Google Ads UI (the client account, not the manager) |
| GA4 | Administrator on the GA4 property (to add a user) | `GA4_SERVICE_ACCOUNT_JSON` | Path to a service account JSON key (steps below); the service account needs **Viewer** on the property |
| | | `ga4.property_id` (config) | GA4 Admin > Property details > **Property ID** (numbers, not the `G-` id) |
| Clarity | Admin on the Clarity project | `CLARITY_API_TOKEN` | Clarity project > **Settings > Data Export > Generate new API token** |
| GoHighLevel | Admin on the sub-account | `GHL_PRIVATE_TOKEN` | Sub-account **Settings > Private Integrations > Create new integration** (scopes below) |
| | | `ghl.location_id` (config) | Settings > Business Profile (Location ID), or the id after `/location/` in the browser URL |

### Meta: system user token (10 min)
1. business.facebook.com > Settings > **Users > System users** > Add. Name it `reporting`, role Employee.
2. **Assign assets** > Ad accounts > pick the account > permission **View performance** (read only).
3. You need a Meta app to mint the token: developers.facebook.com > My Apps > Create app > type **Business**, connect it to the same Business portfolio, and add the **Marketing API** product. The app can stay in Development mode; no App Review is needed to read your own ad accounts with ads_read. In Business Settings > System users, also **assign the app** to the system user (otherwise ads_read is not offered in the next step).
4. Back on the system user: **Generate new token** > choose the app > expiry **Never** > tick **ads_read** > Generate. Copy it into `.env` as `META_ACCESS_TOKEN`.

### Google Ads: developer token, OAuth client, refresh token (20 min, plus approval wait)
1. **Developer token:** sign in to a Google Ads **manager** account (free to create from the Google Ads "Manager accounts" page if you don't have one; link the client account under it). Admin > **API Center**: accept the terms and copy the token. A new token only works on test accounts until Google upgrades its access level; apply for Explorer or Basic access from the same page (usually a few working days). Until then the Google Ads source shows `DEVELOPER_TOKEN_NOT_APPROVED` and the rest of the report still runs.
2. **Cloud project:** console.cloud.google.com > new project > APIs & Services > Library > enable **Google Ads API**. OAuth consent screen: user type External (or Internal on Google Workspace), add yourself as a test user, then **Publish app** (In production). In Testing mode Google kills refresh tokens after 7 days.
3. Credentials > Create credentials > **OAuth client ID** > **Desktop app**. Copy client id and secret into `.env`.
4. `.venv/bin/python tools/google_oauth.py` > sign in as the Google user who can see the ads account > Allow. Paste the printed `GOOGLE_ADS_REFRESH_TOKEN=` line into `.env`. (Running on a remote server? First open a tunnel from your laptop: `ssh -L 8085:localhost:8085 you@server`, then run the script with `--no-browser` and open the printed link in your laptop's browser.)
5. If you reach the account through a manager account, set `GOOGLE_ADS_LOGIN_CUSTOMER_ID` to the manager's id (digits only).

### GA4: service account (10 min)
1. Same Cloud project > Library > enable **Google Analytics Data API**.
2. IAM & Admin > **Service accounts** > Create (name `ga4-reader`, no roles needed) > open it > Keys > Add key > **JSON**. Save the file outside this folder (e.g. `~/.config/growth-data-hub/ga4-key.json`, `chmod 600`) and put that path in `GA4_SERVICE_ACCOUNT_JSON`.
3. GA4 > Admin > **Property access management** > + Add users > paste the service account's email (`...@...iam.gserviceaccount.com`) > role **Viewer** > untick "Notify" > Add.

### Clarity (2 min)
Clarity project > Settings > **Data Export** > Generate new API token (4-32 characters, letters, numbers, `-_.`). Copy it once; it isn't shown again. The API only returns the last 1-3 days and allows about 10 calls per project per day; the hub uses 1 per run and caches it for the day.

### GoHighLevel: Private Integration Token (5 min)
Sub-account Settings > **Private Integrations** > Create new integration > name `reporting` > scopes:
- View Contacts (`contacts.readonly`)
- View Opportunities (`opportunities.readonly`)
- View Calendars (`calendars.readonly`)
- View Calendar Events (`calendars/events.readonly`)

Read-only scopes only; the hub never writes. Without the two calendar scopes the report still runs, with a warning, and bookings come only from pipeline stages.

Copy the token (shown once) into `GHL_PRIVATE_TOKEN`. Then in `config.yaml > ghl.stages`, type your **exact pipeline stage names** for booked, showed, no_show, won: Opportunities > pick the pipeline > the column headers. If none match, the run prints a warning listing your real stage names. Appointment statuses (showed / no-show) are read from the calendars automatically.

## Install
From the folder you unzipped or downloaded:
```bash
cp -r growth-data-hub ~/.claude/skills/
cd ~/.claude/skills/growth-data-hub
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env          # fill in what you have; comments on their own lines
cp config.example.yaml config.yaml              # ids, currency, stage names, channel rules
```
Every command below uses `.venv/bin/python` (on Windows: `.venv\Scripts\python`).
Edit `benchmarks.yaml > costs` to your economics (max cost per lead, max cost per booked call).

## First run (2 minutes)
```bash
.venv/bin/python hub.py --demo            # 1. full report with sample data: out/demo/ACTIONS.md and out/demo/report.html
.venv/bin/python -m pytest -q tests       # 2. optional: 40 tests, all should pass
.venv/bin/python hub.py --check           # 3. which sources are ready
.venv/bin/python hub.py --days 28         # 4. real report: out/ACTIONS.md, out/report.html, out/report.json
```
Or just ask Claude: "run the growth data hub for the last 28 days".

## Common errors and fixes
| You see | Fix |
|---|---|
| `meta: skipped: missing META_ACCESS_TOKEN` | Fill it in `.env` (the file sits next to hub.py), or that source is simply off. |
| `externally-managed-environment` from pip | Use the venv: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`. |
| `PyYAML is missing` | You ran system `python3`; use `.venv/bin/python`. |
| `--check` says a key is there but calls fail | A comment sits after the value on the same line in `.env`. Move it to its own line. |
| Meta `code 190` / `Invalid OAuth access token` | Token wrong or revoked: generate a new system user token (Meta step 4). |
| Meta `(#200) ... ads_read` or `(#100) ... does not exist` | The system user isn't assigned to that ad account, or the id is wrong. Re-check step 2 and `meta.ad_account_id`. |
| Meta `(#17)` / `(#80004)` / `(#4)` rate limit | The hub waits and retries (1-4 minutes). If it still fails, run again later or use a shorter `--days`. |
| Google `invalid_client` | Client id or secret wrong (or comment text after the value in `.env`). |
| Google `invalid_grant` | Refresh token expired or revoked (most often: consent screen still in Testing). Publish the app, run `tools/google_oauth.py` again. |
| Google `DEVELOPER_TOKEN_NOT_APPROVED` | Token is test-only. Apply for Explorer/Basic access in API Center. |
| Google `USER_PERMISSION_DENIED` | Set `GOOGLE_ADS_LOGIN_CUSTOMER_ID` to the manager id, or sign in (step 4) as a user with access to the account. |
| Google `SERVICE_DISABLED` | Enable the Google Ads API (or Analytics Data API) in the same Cloud project as the OAuth client / service account. |
| GA4 `403 ... does not have sufficient permissions` | Add the service account email as Viewer on the property; check you used the property id, not the `G-` id. |
| Clarity `daily limit reached` | About 10 calls per day per project. Wait until tomorrow; today's cache is reused. |
| Clarity `401` or `403` (empty message) | Token wrong, regenerated, or not made by a project admin; make a new one in Settings > Data Export. |
| GHL `401` / `403` | Token missing a scope from the list above, or it belongs to another sub-account. |
| GHL `422` on contacts | You changed the code: `pageLimit` must be a number. |
| CRM leads much lower than Meta leads | Check every Meta lead form is connected to the CRM. Some gap is normal: GHL merges repeat contacts on email/phone. |
| Every contact lands in "Organic and other" | Your CRM doesn't store UTMs/click ids the default way. Add your tags or source names to `channels > ghl` in config.yaml. |
| Booked/showed all zero | Read the warning in ACTIONS.md: either `ghl.stages` names don't match (it lists yours) or the token lacks the calendar scopes. |
| A real run failed and ACTIONS.md says "No report" | Nothing could be pulled; each source's error and fix is listed in that file. |

## Setup time
Demo: 2 minutes. Clarity + GHL: 10 minutes. Meta: 10 minutes. GA4: 10 minutes. Google Ads: 20 minutes plus the developer token approval (days). About **60 minutes** of hands-on time for all five.

## API cost
All five APIs are free. The only cost is your time. Clarity's free tier allows about 10 export calls per project per day; Google Ads Explorer/Basic access has a daily operation cap far above what this report uses (two queries a run).
