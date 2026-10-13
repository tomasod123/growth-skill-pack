---
name: analytics-access-setup
description: Walk someone through getting READ access to their marketing data, one source at a time, with a verification step for each. GA4 (service account with Viewer, optional Google's official analytics-mcp), Search Console (OAuth desktop client, webmasters.readonly), Google Ads API (developer token, OAuth client, refresh token, login-customer-id), Microsoft Clarity (Data Export token), Meta (system user token with ads_read), GoHighLevel (Private Integration Token with read scopes). Use when the user says "set up analytics access", "connect GA4", "connect Search Console", "get a Google Ads developer token", "Meta API token", "Clarity API", "GHL API key", "why can't I read my data", or before the first run of growth-data-hub or search-console. Instruction-only: it never creates, prints or sends credentials for the user.
---

# analytics-access-setup

A guided checklist that gets read-only access to six data sources and proves each one works. It writes no code and calls no API itself; the user clicks through each console and runs the verification commands.

Pairs with:
- **growth-data-hub** (Meta, Google Ads, GA4, Clarity, GoHighLevel). Its `SETUP.md` is the reference for the env var names and the `.env` file. This skill follows it exactly and adds where to keep files, the optional GA4 MCP and the per-source checks.
- **search-console** (`scripts/gsc.py`, OAuth desktop client).

## Rules

1. **Read access only.** Ask for the lowest role that can read: Viewer, Read only, View performance, `*.readonly` scopes. Never request write, admin or manage scopes "to be safe".
2. **Credentials never go in a repo, a chat or a document.** Not in the skill folder if that folder is under git, not pasted into Claude, not in a ticket or email. If the user pastes a secret into chat, tell them to revoke it and make a new one.
3. **One home for secrets:** `~/.config/<tool>/`, folder `chmod 700`, files `chmod 600`.
   - growth-data-hub: `~/.config/growth-data-hub/.env` and `~/.config/growth-data-hub/ga4-key.json`
   - search-console: `~/.config/gsc-reader/client_secrets.json` and `token.json` (or set `GSC_CONFIG_DIR`)
   growth-data-hub's own SETUP.md puts `.env` next to `hub.py`. That is fine if `~/.claude` is not a git repo. If it is, or you are not sure, keep the file in `~/.config/growth-data-hub/` and run `.venv/bin/python hub.py --env ~/.config/growth-data-hub/.env`.
4. **Ask before writing any file or running any command** on the user's machine. Show the command first.
5. **Verify every source** with its check below before calling it done. A source is only "ready" when the check returns real data.
6. **Access requests to other people are drafts.** If a client or colleague has to grant access (add a user to GA4, Search Console, Ads), write the request for the user to send. Never send it yourself.

## How Claude should run it

1. Ask which sources they want (default: all six) and whether this is for their own business or a client's (client = the client grants access to the user's account).
2. Audit what exists, without printing any secret values:
   ```bash
   ls -la ~/.config/growth-data-hub ~/.config/gsc-reader 2>/dev/null
   grep -o '^[A-Z_]*=.' ~/.config/growth-data-hub/.env 2>/dev/null   # shows which keys are filled, not their values
   ```
3. Show a status table: source, ready / missing / failing, next step.
4. Walk through each missing source in the order below (quickest first), one at a time. Wait for "done" before the next.
5. Run the verification for that source. On failure, use the error table.
6. Finish with the status table again and the next command (`.venv/bin/python hub.py --check`, then `--days 28`; `gsc.py properties`).

Time guide: Clarity 2 min, GoHighLevel 5, Meta 10, GA4 10, Search Console 15, Google Ads 20 plus approval wait.

## 1. Microsoft Clarity (2 min)

1. clarity.microsoft.com > the project > **Settings > Data Export > Generate new API token**. Needs project admin.
2. Copy it once (not shown again) into `CLARITY_API_TOKEN=` in the growth-data-hub `.env`.

Verify (uses 1 of about 10 calls per project per day):
```bash
T=$(grep '^CLARITY_API_TOKEN=' ~/.config/growth-data-hub/.env | cut -d= -f2-)
curl -s -H "Authorization: Bearer $T" "https://www.clarity.ms/export-data/api/v1/project-live-insights?numOfDays=1" | head -c 300
```
Expect JSON with `metricName` entries. `401` = wrong or regenerated token.

## 2. GoHighLevel (5 min)

1. Sub-account (not agency view) > **Settings > Private Integrations > Create new integration**, name `reporting`.
2. Scopes, read only: View Contacts (`contacts.readonly`), View Opportunities (`opportunities.readonly`), View Calendars (`calendars.readonly`), View Calendar Events (`calendars/events.readonly`). Same list as growth-data-hub's SETUP.md.
3. Copy the token (shown once) into `GHL_PRIVATE_TOKEN=`. Note the Location ID (Settings > Business Profile, or the id after `/location/` in the URL) for `ghl.location_id` in config.yaml.

Tokens are per sub-account: one per business.

Verify: in the growth-data-hub folder, with `ghl.location_id` set in config.yaml, run `.venv/bin/python hub.py --env ~/.config/growth-data-hub/.env --only ghl --days 7` and look for `ghl ok`. `401`/`403` = missing scope or a token from another sub-account. A warning about stage names means the token works and `ghl.stages` needs your real stage names.

## 3. Meta Marketing API (10 min)

1. business.facebook.com > Settings > **Users > System users** > Add, name `reporting`, role Employee.
2. **Assign assets** > Ad accounts > the account > **View performance** only.
3. A Meta app is needed to mint the token: developers.facebook.com > My Apps > Create app > type **Business**, linked to the same Business portfolio, with the **Marketing API** product added. It can stay in Development mode; no App Review is needed to read your own ad accounts. In Business Settings > System users, also **assign the app** to the system user, or `ads_read` will not be offered in the next step.
4. System user > **Generate new token** > the app > expiry Never > tick **ads_read** only > Generate. Into `META_ACCESS_TOKEN=`.
5. Ad account id: Ads Manager account dropdown (the number, with or without `act_`) for `meta.ad_account_id`.

Verify (token in a header, not the URL, so it stays out of logs):
```bash
T=$(grep '^META_ACCESS_TOKEN=' ~/.config/growth-data-hub/.env | cut -d= -f2-)
curl -s -H "Authorization: Bearer $T" "https://graph.facebook.com/v26.0/me/adaccounts?fields=name,account_status" | head -c 400
```
Expect the ad account in `data`. Empty list = step 2 missed. `(#200)` = token lacks `ads_read`.

## 4. GA4 (10 min) and the optional GA4 MCP

1. console.cloud.google.com > create or pick a project > APIs & Services > Library > enable **Google Analytics Data API** (and **Google Analytics Admin API** if you want the MCP to list accounts).
2. IAM & Admin > **Service accounts** > Create (name `ga4-reader`, no project roles) > Keys > Add key > **JSON**.
3. Move the key and lock it down:
   ```bash
   mkdir -p ~/.config/growth-data-hub && chmod 700 ~/.config/growth-data-hub
   mv ~/Downloads/<downloaded-key>.json ~/.config/growth-data-hub/ga4-key.json
   chmod 600 ~/.config/growth-data-hub/ga4-key.json
   ```
   Set `GA4_SERVICE_ACCOUNT_JSON=` to that full path.
4. GA4 > Admin > **Property access management** > + > the service account's email (it ends in `iam.gserviceaccount.com`, shown on the service account page) > role **Viewer** > untick Notify > Add.
5. Property ID: GA4 Admin > Property details > **Property ID** (digits only, not the `G-` measurement id) for `ga4.property_id`.

Verify: `.venv/bin/python hub.py --env ~/.config/growth-data-hub/.env --only ga4 --days 7` in the growth-data-hub folder, and look for `ga4 ok`.

**Optional: Google's official GA4 MCP** (`analytics-mcp`, github.com/googleanalytics/google-analytics-mcp) lets Claude query GA4 directly. Only install it if the user wants it, and only this official one.
```bash
pipx install analytics-mcp      # needs pipx
claude mcp add analytics-mcp \
  -e GOOGLE_APPLICATION_CREDENTIALS=$HOME/.config/growth-data-hub/ga4-key.json \
  -e GOOGLE_PROJECT_ID=<your-cloud-project-id> \
  -- pipx run analytics-mcp
```
Check the repository README for the current install line. Verify by restarting Claude Code and asking "list my GA4 account summaries".

## 5. Google Search Console (15 min)

Uses an OAuth desktop client with the `webmasters.readonly` scope. Google has no official Search Console MCP; use the `search-console` skill's `gsc.py` (official Google Python libraries).

1. Same Cloud project > Library > enable **Google Search Console API**.
2. **Google Auth Platform** (OAuth consent screen): app name of your choice, audience **External** (or Internal on Google Workspace), add the signing-in Google account as a **test user**, leave the scopes step empty (gsc.py asks for read-only at login), and do not upload a logo (a logo triggers Google's verification).
3. Clients > Create client > **Desktop app** > Create > Download JSON. Save as `~/.config/gsc-reader/client_secrets.json`, `chmod 600`, folder `chmod 700`.
4. The Google account you sign in with must be a user on each Search Console property: Search Console > Settings > **Users and permissions** > Add user > **Restricted** (Full if you need sitemaps or URL inspection on every property).
5. `python3 ~/.claude/skills/search-console/scripts/gsc.py login` > sign in > Allow. "Google hasn't verified this app" is expected in Testing mode: Continue.

Verify: `python3 ~/.claude/skills/search-console/scripts/gsc.py properties` lists the sites.

Testing mode makes a sign-in expire after 7 days (`invalid_grant`). Either run `login` again weekly or publish the app (Branding needs a home page URL and a privacy policy URL first).

## 6. Google Ads API (20 min, plus approval wait)

1. **Developer token**: needs a Google Ads **manager** account (free; create one and link the client account under it). Manager account > Admin > **API Center** > accept terms > copy token into `GOOGLE_ADS_DEVELOPER_TOKEN=`. A new token is test-only until you apply for **Explorer or Basic** access from the same page (usually a few working days).
2. Same Cloud project > Library > enable **Google Ads API**. Consent screen as in Search Console step 2, then **Publish app** (in Testing mode refresh tokens die after 7 days).
3. Clients > Create client > **Desktop app**. Client id and secret into `GOOGLE_ADS_CLIENT_ID=` and `GOOGLE_ADS_CLIENT_SECRET=`.
4. Refresh token: in the growth-data-hub folder run `.venv/bin/python tools/google_oauth.py`, sign in as a Google user who can see the ads account, paste the printed `GOOGLE_ADS_REFRESH_TOKEN=` line into the `.env`. The tool reads the `.env` next to `hub.py` or real environment variables, so with the file in `~/.config` run `set -a; . ~/.config/growth-data-hub/.env; set +a` first.
5. **login-customer-id**: if access comes through the manager account, set `GOOGLE_ADS_LOGIN_CUSTOMER_ID=` to the manager's 10-digit id, digits only. Leave empty for direct access.
6. Customer id of the ads account itself (top right of Google Ads) for `google_ads.customer_id`.

The Google Ads API has no read-only OAuth scope. Keep it read-only by giving the signing-in Google user **Read only** access in Google Ads (Admin > Access and security) and by using read-only code (growth-data-hub only runs search queries).

Verify: `.venv/bin/python hub.py --env ~/.config/growth-data-hub/.env --only google_ads --days 7` and look for `google_ads ok`.

## Errors

| You see | Fix |
|---|---|
| Google `invalid_grant` | Consent screen still in Testing (7-day tokens) or access revoked. Publish the app, sign in again. |
| Google `SERVICE_DISABLED` / `accessNotConfigured` | Enable that API in the same Cloud project as the key or OAuth client. |
| Google Ads `DEVELOPER_TOKEN_NOT_APPROVED` | Token is test-only. Apply for Explorer or Basic access in API Center. |
| Google Ads `USER_PERMISSION_DENIED` | Set `GOOGLE_ADS_LOGIN_CUSTOMER_ID` to the manager id, or sign in as a user with access. |
| GA4 `403 ... sufficient permissions` | Service account not added as Viewer, or you used the `G-` id instead of the numeric Property ID. |
| Search Console site missing from `properties` | The signed-in account is not a user on that property, or the site is `sc-domain:` vs `https://` form. |
| "Access blocked: app has not completed verification" | The account signing in is not a test user. Add it under Audience > Test users. |
| Meta `(#100)` / empty `data` | System user not assigned to the ad account, or wrong id. |
| Clarity `daily limit` | About 10 calls per project per day. Wait until tomorrow. |
| GHL `401`/`403` | Missing scope, or a token from a different sub-account. |
| `.env` value not picked up | No comment text after a value; no quotes; no spaces around `=`. |

## Revoking access

- Google (Search Console, Google Ads OAuth): myaccount.google.com/permissions > remove the app. Service account: delete its key in Cloud Console and remove it from GA4.
- Meta: Business Settings > System users > the user > revoke tokens.
- Clarity: Settings > Data Export > delete the token.
- GoHighLevel: Settings > Private Integrations > delete.
