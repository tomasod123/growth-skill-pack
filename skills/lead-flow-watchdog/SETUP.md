# Setup: lead-flow-watchdog

**What it does:** once a day, checks that the leads Meta says it delivered actually reached GoHighLevel, tagged and ready to call.
It flags broken syncs, untagged leads, sudden drops, CPL spikes and money spent with no leads.

**Setup time:** about 25 minutes (Meta token 15, GHL token 5 per sub-account, config 5).
**API cost:** free. Meta Marketing API, GHL API and Slack incoming webhooks cost nothing. Only your time.

## What you need

- A Meta Business Manager (Business Portfolio) with access to the ad accounts, and admin rights to create a system user.
- A GoHighLevel sub-account (location) per business, with admin access to its Settings.
- Python 3.10 or newer.
- Optional: a Slack workspace where you can add an incoming webhook.

### Environment variables (`.env`)

| Variable | Required | Where to get it |
|---|---|---|
| `META_ACCESS_TOKEN` | Recommended | Meta system user token with `ads_read`. Step 1. Without it only CRM checks run. |
| `GHL_TOKEN` (or any name you set in `token_env`) | Yes | GHL Private Integration Token for that sub-account. Step 2. |
| `SLACK_WEBHOOK_URL` | No | Only for `--send`. Step 4. |

**1. Meta system user token (`META_ACCESS_TOKEN`)**

1. business.facebook.com > Business Settings > Accounts > Apps. If you have no app: Add > Create a new app, type **Business**.
2. Business Settings > Users > **System users** > Add. Role Employee is enough.
3. Select the system user > **Assign assets** > Ad accounts > tick each account > turn on **View performance**. Save. Also assign the app from step 1.
4. **Generate new token**: choose the Business-type app, expiry **Never**, tick **ads_read**. Generate.
5. Paste it into `.env` as `META_ACCESS_TOKEN=...`. Meta shows it once.

The ad account id (for `config.yaml`) is in Ads Manager's account dropdown or Business Settings > Accounts > Ad accounts. Keep the `act_` prefix.

**2. GHL Private Integration Token (one per sub-account)**

1. Open the sub-account (not the agency view) > **Settings > Private Integrations** > Create new integration.
2. Name it (for example "Lead watchdog") and tick scopes **contacts.readonly** and **locations.readonly**. Nothing else is needed.
3. Copy the token into `.env` (for example `GHL_TOKEN=...`). Use a different variable name per sub-account and set it in `token_env`.

**3. GHL location id**

In the sub-account: Settings > Business Profile (the Location ID is shown there), or copy it from the browser URL after `/location/`. Put it in `ghl.location_id`.

**4. Slack incoming webhook (optional)**

api.slack.com/apps > Create New App > From scratch > Incoming Webhooks > on > Add New Webhook to Workspace > pick the channel > copy the URL into `SLACK_WEBHOOK_URL`.

### Meta lead rules (`config.yaml`)

Open a few recent Meta leads in GHL and note what marks them: the tag your workflow adds, the Source field (often contains "facebook"), and UTM source if you use it. Put those in `meta_lead_rules`. The tag rule tells you leads were processed; source and UTM tell you they arrived.

## Install

```bash
cp -r lead-flow-watchdog ~/.claude/skills/
cd ~/.claude/skills/lead-flow-watchdog
pip install -r requirements.txt
cp .env.example .env                 # paste tokens
cp config.example.yaml config.yaml   # add businesses, location ids, ad accounts, rules
```

## First run (2 minutes)

```bash
python scripts/watchdog.py --demo     # fixture data, shows each alert type
python -m pytest scripts -q           # optional: all tests should pass
python scripts/watchdog.py            # real check of yesterday, print only
```

Compare the Meta lead count with Ads Manager (yesterday, Leads column) and the CRM count with a GHL contact filter for the same day. When they line up, schedule it.
In Claude Code you can just say "run the lead flow watchdog".

Daily schedule (cron, 09:00 every day, posts to Slack only when something is wrong):

```
0 9 * * * cd <skill-dir> && python scripts/watchdog.py --send >> watchdog.log 2>&1
```

## Common errors and fixes

| Error | Cause | Fix |
|---|---|---|
| `No GHL token found` | `token_env` name not in `.env` | Make the variable name in `.env` match `ghl.token_env`. |
| `GHL 401` | Token wrong, or from a different sub-account than the location id | Create the token inside the same sub-account as the location id. |
| `GHL 403` | Missing scope | Edit the Private Integration, tick `contacts.readonly`, use the new token. |
| `GHL 422` | Bad request body or wrong location id | Check `location_id`. `ghl_page_limit` must be a number (max 100). |
| CRM count 0 but leads are in GHL | Rules do not match your contacts | Open a Meta lead in GHL and copy its exact tag and source into `meta_lead_rules`. |
| CRM a bit lower than Meta every day | GHL merges contacts with the same email or phone | Normal. Only big gaps alert. |
| Day totals off by some leads | Time zone mismatch | Set `timezone` to the ad account's time zone. |
| `Meta API error 190` | Token invalid or expired | New system user token, expiry Never. |
| `Meta API error 200` / `(#10)` | System user not assigned to the ad account or `ads_read` missing | Assign with View performance, regenerate the token with `ads_read`. |
| `Meta API error 17` / `80004` after retries | Rate limit | Run later. The script already backs off. |
| `--send given but SLACK_WEBHOOK_URL is not set` | No webhook | Add it to `.env` or drop `--send`. |
