# Setup: meta-weekly-account-report

**What it does:** every week, compares each Meta ad account's last 7 days with the 7 days before, down to ad level.
It tells you the best ad, what to pause, what is fatigued, what is under-pacing, and if leads dropped while spend held.

**Setup time:** about 20 minutes (most of it is creating the Meta token).
**API cost:** free. The Meta Marketing API and Slack incoming webhooks cost nothing. Only your time.

## What you need

- A Meta Business Manager (Business Portfolio) that owns or has access to the ad accounts.
- Admin access to that Business Manager (to create a system user).
- Python 3.10 or newer.
- Optional: a Slack workspace where you can add an incoming webhook.

### Environment variables (`.env`)

| Variable | Required | Where to get it |
|---|---|---|
| `META_ACCESS_TOKEN` | Yes | A system user token with `ads_read`. Steps below. |
| `SLACK_WEBHOOK_URL` | No | Only for `--send`. Steps below. |

**1. Meta system user token (`META_ACCESS_TOKEN`)**

1. Go to business.facebook.com > Business Settings > Accounts > Apps. If you have no app, click Add > Create a new app, and choose the **Business** type. Any name works.
2. Business Settings > Users > **System users** > Add. Give it a name, role Employee is enough.
3. With the system user selected, click **Assign assets** > Ad accounts > tick each ad account > turn on **View performance** (read only). Save.
4. Also assign the app from step 1 to the system user (Assign assets > Apps).
5. Click **Generate new token**. Choose the Business-type app, set token expiry to **Never**, tick **ads_read**. Generate.
6. Copy the token straight into `.env` as `META_ACCESS_TOKEN=...`. Meta shows it once.

**2. Ad account ids (`config.yaml`)**

Ads Manager > account dropdown, or Business Settings > Accounts > Ad accounts. Use the number with the `act_` prefix, for example `act_YOUR_AD_ACCOUNT_ID`.

**3. Slack incoming webhook (`SLACK_WEBHOOK_URL`, optional)**

api.slack.com/apps > Create New App > From scratch > pick the workspace > Incoming Webhooks > turn on > Add New Webhook to Workspace > choose the channel > copy the URL.

## Install

```bash
cp -r meta-weekly-account-report ~/.claude/skills/
cd ~/.claude/skills/meta-weekly-account-report
pip install -r requirements.txt
cp .env.example .env                 # paste your token
cp config.example.yaml config.yaml   # add your ad accounts and target CPLs
```

## First run (2 minutes)

```bash
python scripts/weekly_report.py --demo     # fixture data, proves the install works
python -m pytest scripts -q                # optional: all tests should pass
python scripts/weekly_report.py            # real data, print only
```

Open the file shown under "Full report:". When the numbers match Ads Manager for the same dates, add `--send` if you want the summary in Slack.
In Claude Code you can just say "run the weekly account report".

Weekly schedule (optional, cron, Friday 07:00):

```
0 7 * * 5 cd <skill-dir> && python scripts/weekly_report.py --send >> weekly_report.log 2>&1
```

## Common errors and fixes

| Error | Cause | Fix |
|---|---|---|
| `META_ACCESS_TOKEN is not set` | `.env` missing or empty | Copy `.env.example` to `.env` in the skill folder and paste the token. |
| `Meta API error 190` | Token invalid or expired | Generate a new system user token with expiry Never. |
| `Meta API error 200` or `(#10)` permission error | System user not assigned to that ad account, or `ads_read` not ticked | Assign the ad account with View performance, then generate a new token with `ads_read`. |
| `Meta API error 100` unknown path | Ad account id wrong or missing `act_` prefix | Use `act_` plus the number. |
| `Meta API error 17` / `80004` after retries | Rate limit (many accounts or big ad counts) | Run again later, or run fewer accounts at once. The script already backs off. |
| Version error / "deprecated" | The Graph version in `config.yaml` is retired | Set `graph_version` to the current version. |
| Leads lower than Ads Manager "Results" | Ads Manager may count other result types | This report counts lead form submissions (`lead`) only, on purpose. |
| Pacing shows "ad set budgets, not checked" | Budgets set on ad sets, not the campaign | Expected. Pacing reads campaign budgets only. |
| `--send given but SLACK_WEBHOOK_URL is not set` | No webhook in `.env` | Add it or drop `--send`. |
