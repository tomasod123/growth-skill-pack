# gads-common setup

## What it does
Gives Claude (and the gads-audit skill) read-only access to every Google Ads account under your manager account.
One stdlib Python script, `gads.py`: doctor, accounts, snapshot, and any GAQL read query. It never changes an account.

## What you need

**Accounts**
- A Google Ads **manager account** (MCC). If you do not have one, create it free from the Google Ads sign-in page (search "Google Ads manager account"; use a Google user that is not already tied to a regular ad account). Every account you want to read must be linked under it (Admin > Access and security > Managers on the client account, or send a link request from the manager).
- A Google user (Gmail or Workspace) that has access to the manager account. This is the user you sign in with in step 3.
- A Google Cloud project (free) at https://console.cloud.google.com/.

**Step 1. Developer token (GOOGLE_ADS_DEVELOPER_TOKEN)**
1. Sign in to the **manager** account at https://ads.google.com (a client account has no API Center).
2. Go to **Tools > API Center** (Tools is the wrench icon; in the newer UI it is **Admin > API Center**, or Tools > Setup > API Center).
3. Fill in the form (contact email, company website, accept the terms). A token appears straight away. Copy it into GOOGLE_ADS_DEVELOPER_TOKEN.
4. Check the **Access level** shown on that page:
   - **Test account access** (where every new token starts): the token only works against *test accounts* (special accounts made under a test manager account, which never serve ads or spend). Against any real account you get `DEVELOPER_TOKEN_NOT_APPROVED`. Useful only to prove your OAuth setup works.
   - **Explorer access**: production access to real accounts with a modest daily operation limit. Plenty for read-only audits of a handful of accounts. Apply from the same API Center page; it is often granted quickly.
   - **Basic access**: production access with a higher daily limit (about 15,000 operations a day). Apply from API Center with a short description of the tool ("internal read-only reporting and audits for accounts we manage"). Review can take a few business days.
   - Standard access is only needed for large tools; not required here.
   Current limits per level: https://developers.google.com/google-ads/api/docs/api-policy/access-levels
5. Never paste the token into chat. It goes in ~/.claude/skills/.env only.

**Step 2. OAuth client (GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET)**
1. In https://console.cloud.google.com/ pick (or create) a project.
2. **Enable the API:** APIs & Services > Library > search "Google Ads API" > Enable. (Skipping this gives `SERVICE_DISABLED` / "has not been used in project".)
3. **OAuth consent screen:** APIs & Services > OAuth consent screen (newer console: Google Auth Platform > Branding / Audience).
   - User type: **Internal** if you are on Google Workspace and only your team signs in; otherwise **External**.
   - App name, support email, developer contact email. Scopes can be left empty (the script asks for the adwords scope at sign-in).
   - If External and left in **Testing**, add your Google user under **Test users**, and know that refresh tokens from a Testing app **expire after 7 days**. To stop the expiry, click **Publish app** (In production). For a private internal tool you can ignore the "unverified app" warning at sign-in.
4. **Client id:** APIs & Services > Credentials > Create credentials > **OAuth client ID** > Application type **Desktop app** > Create. Copy the **Client ID** into GOOGLE_ADS_CLIENT_ID and the **Client secret** into GOOGLE_ADS_CLIENT_SECRET. (Desktop app clients allow the localhost redirect the login command uses; a "Web application" client will fail with redirect_uri_mismatch.)

**Step 3. Refresh token (GOOGLE_ADS_REFRESH_TOKEN)**
Use the included login command (stdlib, PKCE, local loopback redirect):
```bash
set -a; source ~/.claude/skills/.env; set +a        # client id + secret must already be in the file
python3 ~/.claude/skills/gads-common/scripts/gads.py login --save
```
A browser tab opens. Sign in as the Google user that has access to the manager account and allow access. With `--save` the refresh token is written to ~/.claude/skills/.env (file set to owner-only); without it the line is printed for you to paste in yourself.
- On a remote server with no browser: run `gads.py login --port 8085 --save` on the server, and on your laptop `ssh -L 8085:localhost:8085 <server>`, then open the printed URL in your laptop browser.
- Alternatives that give the same token: Google's `generate_user_credentials.py` example in the google-ads-python library, or the OAuth 2.0 Playground (gear icon > "Use your own OAuth credentials", scope `https://www.googleapis.com/auth/adwords`). The login command is simpler.

**Step 4. Login customer id (GOOGLE_ADS_LOGIN_CUSTOMER_ID)**
The **manager** account id, the 10-digit number at the top right of Google Ads when you are in the manager account, written **without dashes** (XXX-XXX-XXXX becomes XXXXXXXXXX). It tells the API to reach client accounts through that manager. Optional only if your user has direct access to every account you read.

Optional: GOOGLE_ADS_CUSTOMER_ID (a default client account, 10 digits no dashes) and GOOGLE_ADS_API_VERSION (override if the built-in version is sunset).

**Packages**
- Python 3.9+. Nothing else is required. Optional: `python3 -m pip install certifi` if your Python has no CA bundle (macOS python.org installs often fail with CERTIFICATE_VERIFY_FAILED without it).
- No MCP server needed. Google's own Google Ads MCP server is an optional extra (see SKILL.md).

No DataForSEO or other paid API is used by this skill.

## Install
1. Copy this folder to `~/.claude/skills/gads-common/`.
2. Add the variables from `.env.example` to `~/.claude/skills/.env` and fill in steps 1, 2 and 4.
3. Run step 3 (`gads.py login --save`).
4. Prove access (read-only):
```bash
set -a; source ~/.claude/skills/.env; set +a
python3 ~/.claude/skills/gads-common/scripts/gads.py doctor
python3 ~/.claude/skills/gads-common/scripts/gads.py accounts
```
`doctor` prints OK or TODO per line with the fix. Fix TODO lines top to bottom.

## First run (2 minutes)
Type to Claude: **"List our Google Ads accounts, then give me a 7-day snapshot of the first one: are the ads live, where do they point, and which conversions count?"**
You get the account list (id, status, currency, name), then a JSON snapshot summarised in chat: each campaign's serving status and why, budget, spend, clicks and conversions, every live ad's final URL and approval, and each conversion action's primary flag and counting type. Nothing is written to disk unless you ask; ask for it saved and it lands in `./gads-common-output/`.

## Common errors and fixes
- **`DEVELOPER_TOKEN_NOT_APPROVED` / "only approved for use with test accounts"**: the token is still at Test account access. Apply for Explorer or Basic access in the manager account under Tools > API Center.
- **`SERVICE_DISABLED` / "Google Ads API has not been used in project"**: enable the Google Ads API in the same Cloud project that owns the OAuth client (APIs & Services > Library).
- **`invalid_grant` / "Token has been expired or revoked" a week after setup**: the consent screen is External + Testing, so the refresh token died after 7 days. Run `gads.py login --save` again, and publish the app to stop it recurring.
- **`USER_PERMISSION_DENIED`**: GOOGLE_ADS_LOGIN_CUSTOMER_ID is wrong (dashes left in, or a client id instead of the manager id), the account is not linked under that manager, or the signed-in user has no access to the manager.
- **`redirect_uri_mismatch` during login**: the OAuth client is a "Web application". Create a **Desktop app** client instead.
- **HTTP 404 on every call**: the API version in the script has been sunset. Set GOOGLE_ADS_API_VERSION to the newest version (developers.google.com/google-ads/api/docs/sunset-dates).
- **`UNRECOGNIZED_FIELD`** in a custom query: the field was renamed in this API version (e.g. `campaign.start_date` is now `campaign.start_date_time`). Check the field reference for your version.
- **`CERTIFICATE_VERIFY_FAILED`**: `python3 -m pip install certifi`.

## Setup time
About 30 minutes the first time (most of it the Cloud Console screens), plus any wait for Explorer/Basic token approval.

## Cost per run
Free. The Google Ads API has no charge; each run is a handful of read operations against your daily limit.
