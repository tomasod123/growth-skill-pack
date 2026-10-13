# cold-email-starter-kit setup

## What it does
Takes you from nothing to a live cold email campaign: sending domains, warmed inboxes, a lead list, copy, and upload to Smartlead or Instantly.
Ships 16 TypeScript scripts (domains, inboxes, leads, campaigns, analytics, enrichment) plus 15 numbered guides, a launch checklist and a troubleshooting matrix.
Source: Adapted from a publicly shared cold email starter kit; check the original's terms before redistributing.

## What you need
Accounts (sign up before starting; you need only ONE sending platform):
- **Dynadot** (domain registrar, prepaid wallet) - dynadot.com
- **Zapmail** (Google/Microsoft inbox hosting for cold email) - zapmail.ai
- **Prospeo** (B2B lead data, credit based) - prospeo.io
- **Smartlead** or **Instantly** (sending platform)

Env vars (all go in `~/.claude/skills/.env`; leave optional ones blank):
- `DYNADOT_API_KEY` - dynadot.com > sign in > My Info (Tools) > API > generate an API key, then add your current IP under the API IP whitelist (calls fail with IP_NOT_ALLOWED otherwise). Top up the account wallet before buying.
- `ZAPMAIL_API_KEY` - zapmail.ai dashboard > Settings > API > create / copy token.
- `PROSPEO_API_KEY` - app.prospeo.io > Settings > API (prospeo.io/app/settings/api) > copy key.
- `SMARTLEAD_API_KEY` - app.smartlead.ai > Settings > API Keys > Create (if you send with Smartlead).
- `INSTANTLY_API_KEY` - app.instantly.ai > Settings > Integrations > API Keys > create an **API v2** key with campaign + lead scopes (if you send with Instantly).
- `SENDER_FIRST_NAME`, `SENDER_LAST_NAME`, `SENDER_EMAIL_PREFIX_1`, `SENDER_EMAIL_PREFIX_2` - the persona and inbox names created on every domain (e.g. Jane / Doe / jane / janedoe).
- `DEFAULT_REPLY_TO_EMAIL` - optional reply-to address.
- Optional enrichment: `BLITZ_API_KEY` (+ `BLITZ_BASE_URL`, blank = default) from blitz.us dashboard > API; `OPENROUTER_API_KEY` from openrouter.ai > Keys; `RAPIDAPI_KEY` from rapidapi.com > your profile > Apps > default application > Authorization (subscribe to the "LinkedIn Bulk Data Scraper" and "OpenWebNinja Google Search" APIs).
- `COMPANY_*` - your physical mailing address for the CAN-SPAM footer (used when writing copy, not read by scripts).

Software:
- Node.js 20+ (`node --version`). Install from nodejs.org or `brew install node` / `apt install nodejs`.
- A TypeScript runner. Default: `tsx` via `npx tsx scripts/x.ts` (auto-downloads) or `npm install -g tsx`. Alternatives: `bun scripts/x.ts`, or Node 22.6+ `node --experimental-strip-types scripts/x.ts`.
- No npm packages: the scripts use only Node built-ins (`fetch`, `fs`, `readline`).
- `dig` for DNS checks (`brew install bind` / `apt install dnsutils`).
- No MCP servers needed.

## Install
1. Copy the folder: `cp -r cold-email-starter-kit ~/.claude/skills/cold-email-starter-kit`
2. Add the vars: `bash ~/.claude/skills/cold-email-starter-kit/scripts/setup-env.sh` (appends only missing vars from `.env.example` to `~/.claude/skills/.env`), then fill in the values.
3. Test access (read-only, spends nothing):
   ```bash
   set -a; source ~/.claude/skills/.env; set +a; npx tsx ~/.claude/skills/cold-email-starter-kit/scripts/verify-credentials.ts
   ```
   You get a ✅/❌ table per service. Services you did not configure show ❌ and can be ignored.

## First run (2 minutes)
Type to Claude: **"Use the cold-email-starter-kit skill. I'm new to cold email: check my credentials and tell me what I still need before my first campaign."**
You get the credentials table, a list of missing accounts/keys, and the recommended setup (domains x inboxes, warmup timeline, budget). Nothing is bought.
For the full walkthrough say: **"Walk me through the 60-minute first campaign tutorial."** The scripts write their files (domain lists, lead CSVs, inbox exports, analytics) to the current folder, so `mkdir -p cold-email-starter-kit-output && cd cold-email-starter-kit-output` first; Claude does this for you and runs each script from there, so files land in `./cold-email-starter-kit-output/`. Campaigns are created as drafts; you start them in the Smartlead/Instantly UI.

## Common errors and fixes
- **Dynadot `IP_NOT_ALLOWED`** - your IP is not on the API whitelist. Add it (Dynadot API settings); if your IP changes often, whitelist the range or run from a fixed server.
- **Instantly 401** - Instantly uses `Authorization: Bearer <key>` with a v2 key, not the query-param style Smartlead uses. Regenerate a v2 key.
- **Smartlead "Invalid API key"** - wrong/expired key, or a sub-client key used without `client_id`.
- **Zapmail export returns 0 mailboxes** - inboxes take 4-6 hours to provision; export only picks up `ACTIVE` ones. Re-run later with `--only-export`.
- **Dynadot NS mismatch on connect** - nameserver propagation not finished; wait 15-20 minutes and retry.
- **Variables show as literal `{{var}}` in sent mail** - CSV column names must exactly match the variable names (`first_name`, `company_name`, ...).
- **Prospeo returns 0 results** - filters too strict; remove one at a time, drop "of" from titles ("VP Sales"), add synonym titles.
- **Wrong inboxes on a new Smartlead campaign** - `smartlead-create-campaign.ts` attaches every inbox in the workspace; detach other clients' inboxes before starting.
- **`Missing required env var`** - you did not source the env file in this shell: `set -a; source ~/.claude/skills/.env; set +a`.

## Setup time
45 minutes for accounts and keys; then 2+ weeks of inbox warmup before real sending.

## Cost per run
Reading guides, verifying keys and pulling analytics: free. A first campaign build: roughly $330-410 in month 1 (20 `.com` domains ~$10-14 each, ~40 Zapmail inboxes ~$38/mo, Smartlead or Instantly ~$37-39/mo, Prospeo ~$49 for 1,000 contacts), ~$126/mo after. Optional enrichment: OpenRouter gpt-4o-mini ~$0.15 per 1,000 leads; Blitz/RapidAPI subscriptions $10-75/mo each. Prices drift; check each provider.
