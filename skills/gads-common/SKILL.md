---
name: gads-common
description: Shared read-only Google Ads API access (one stdlib script, gads.py) used by gads-audit and any other skill that needs Google Ads data. Use when asked "are the Google ads live", "what's the final URL", "is the form counted as a conversion", "yesterday's Google Ads spend/clicks", "list our Google Ads accounts", "Google Ads data for <account>", "check the PPC setup", or any Google Ads cross-check against the CRM. Never changes an account.
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./gads-common-output/`.

# gads-common

Read-only Google Ads access through the Google Ads REST API. Nothing here can create, edit,
pause or delete anything: the script only calls `googleAds:search` and
`customers:listAccessibleCustomers`.

## Before any command

Load the shared env file, then run the doctor if anything has never been run or fails:

```bash
set -a; source ~/.claude/skills/.env; set +a
G=~/.claude/skills/gads-common/scripts/gads.py
python3 $G doctor        # prints OK / TODO per line, with the fix for each TODO
```

If any of the five credentials are missing, walk the user through SETUP.md in this folder
(developer token, OAuth client, `gads.py login` for the refresh token, manager id).

## Commands

| Command | What it gives you |
|---|---|
| `python3 $G accounts` | Every client account linked under the manager (GOOGLE_ADS_LOGIN_CUSTOMER_ID): id, status, currency, name |
| `python3 $G snapshot [CUSTOMER] [--days N]` | Campaigns (status, serving status, primary status and reasons, budget, spend, clicks, conversions), live ads' final URLs and approval, conversion actions (primary? counted ONE or MANY? origin GA4 import or website tag?) |
| `python3 $G query [CUSTOMER] "GAQL"` | Any read query, JSON rows |
| `python3 $G login [--save]` | One-time browser sign-in that produces GOOGLE_ADS_REFRESH_TOKEN |

CUSTOMER is the 10-digit account id, dashes optional. It defaults to GOOGLE_ADS_CUSTOMER_ID.

From another skill's Python, load the module and call `search(customer, gaql)`; it paginates and
returns REST rows (camelCase keys). gads-audit does this through `../gads-common/scripts/gads.py`.

## Rules

- **Read-only.** The adwords OAuth scope could write. Never build a mutate call; changes go in a
  written recommendation for a human to make in the Google Ads UI.
- **Money is in micros** (divide by 1,000,000) and in the account's own currency. Read
  `customer.currency_code` before quoting a figure, and never round a figure going into client copy.
- **The REST API omits false, zero and default fields.** A missing `primaryForGoal` means NOT
  primary; a missing `qualityInfo` means no data yet. Spell every boolean out.
- **An account missing from `accounts` is not linked under your manager.** Ask whoever owns that
  account to accept a link request from the manager account (Google Ads > Admin > Access and
  security > Managers), or give your user direct access.
- **Impression share and quality score can be null.** Report "no data yet", never 0.
- **Field names change between API versions** (v25 renamed `campaign.start_date` to
  `campaign.start_date_time`). An UNRECOGNIZED_FIELD error kills the whole query; check the field
  reference for your version at developers.google.com/google-ads/api/fields.

## Optional: Google's official Google Ads MCP server

Google publishes an open-source Google Ads MCP server (github.com/googleads/google-ads-mcp) with
`search` and `list_accessible_customers` tools, so Claude can run GAQL directly in chat. It is
optional; everything in this pack works through gads.py alone. If you add it, give it the same
developer token and login customer id, and follow that repo's README for credentials.
