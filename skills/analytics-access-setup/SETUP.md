# analytics-access-setup: setup

**What it does:** walks you through getting read-only API access to GA4, Search Console, Google Ads, Microsoft Clarity, Meta and GoHighLevel, one source at a time, and checks each one returns real data.
Instruction-only: no code to install, and it never handles your secrets for you.

## What you need

| Source | Account access you need | What you end up with | Where it comes from |
|---|---|---|---|
| Clarity | Admin on the Clarity project | `CLARITY_API_TOKEN` | Project > Settings > Data Export > Generate new API token |
| GoHighLevel | Admin on the sub-account | `GHL_PRIVATE_TOKEN`, location id | Sub-account Settings > Private Integrations (read-only scopes) |
| Meta | Admin on the Business portfolio | `META_ACCESS_TOKEN`, ad account id | Business Settings > System users > Generate new token (`ads_read`) |
| GA4 | Administrator on the property (to add a user); a Google Cloud project | `GA4_SERVICE_ACCOUNT_JSON` (key file path), property id | Cloud Console > Service accounts > Keys > JSON; GA4 Admin > Property access management (Viewer) |
| Search Console | Owner or Full user on the property (to add a user); same Cloud project | `client_secrets.json` + `token.json` in `~/.config/gsc-reader/` | Cloud Console > Google Auth Platform > Clients > Desktop app; `gsc.py login` |
| Google Ads | A Google Ads manager account; a user who can see the ads account | `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`, `GOOGLE_ADS_REFRESH_TOKEN`, `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | Manager account > Admin > API Center; Cloud Console Desktop app client; growth-data-hub `tools/google_oauth.py` |

The env var names match growth-data-hub's `.env.example` and `SETUP.md` exactly. `SKILL.md` has the click-by-click steps.

Where files live: `~/.config/growth-data-hub/.env` and `ga4-key.json`, `~/.config/gsc-reader/` for Search Console. Folders `chmod 700`, files `chmod 600`. Never in a git repo, never pasted into chat.

## Install

```bash
cp -r analytics-access-setup ~/.claude/skills/
mkdir -p ~/.config/growth-data-hub ~/.config/gsc-reader && chmod 700 ~/.config/growth-data-hub ~/.config/gsc-reader
cp ~/.claude/skills/growth-data-hub/.env.example ~/.config/growth-data-hub/.env && chmod 600 ~/.config/growth-data-hub/.env
```

Nothing to `pip install` for this skill. The verification steps use `curl`, growth-data-hub and the search-console skill (install those for their checks).

## First run (2 minutes)

Ask Claude: "check my analytics access". It lists which sources are ready and which are missing, without printing any secret. Then: "set up Clarity" (the quickest, 2 minutes) and run the verification it gives you. Do the rest one at a time.

## Common errors and fixes

| You see | Fix |
|---|---|
| Google `invalid_grant` | OAuth consent screen still in Testing (logins last 7 days). Publish the app or sign in again. |
| Google `SERVICE_DISABLED` | Enable the API (Analytics Data, Search Console or Google Ads) in the same Cloud project as the key or client. |
| `DEVELOPER_TOKEN_NOT_APPROVED` | Apply for Explorer or Basic access in the manager account's API Center. |
| `USER_PERMISSION_DENIED` (Google Ads) | Set `GOOGLE_ADS_LOGIN_CUSTOMER_ID` to the manager id. |
| GA4 `403` | Service account email not added as Viewer, or the `G-` id used instead of the numeric property id. |
| Search Console site missing | Your Google account is not a user on that property. |
| Meta empty account list | System user not assigned to the ad account (Assign assets > View performance). |
| Clarity `401` | Token regenerated or mistyped. |
| GHL `401`/`403` | A scope is missing, or the token is from another sub-account. |

## Setup time

About 60 minutes of hands-on time for all six (Clarity 2, GoHighLevel 5, Meta 10, GA4 10, Search Console 15, Google Ads 20), plus a few working days for Google Ads developer token approval.

## API cost

All six APIs are free. The only cost is your time. Clarity allows about 10 export calls per project per day; Search Console URL inspection about 2,000 per property per day.
