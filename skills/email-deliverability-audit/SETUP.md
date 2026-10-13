# email-deliverability-audit setup

## What it does
Audits a running Smartlead cold email program: SPF/DKIM/DMARC on every sending domain, inbox warmup health and blocks, sent/reply/bounce rates per campaign and inbox (flags under 1% replies after 200 sends, over 3% bounces), and an optional inbox-placement test.
Writes CSVs plus a markdown report with critical issues, warnings and a prioritised action list.
Source: Adapted from a publicly shared cold email starter kit; check the original's terms before redistributing.

## What you need
- A **Smartlead** account with campaigns running (the API needs a paid plan). Smart Delivery placement tests need Smart Delivery access/credits.
- `SMARTLEAD_API_KEY` - app.smartlead.ai > Settings > API Keys > Create (or copy the existing key). For an agency sub-client, use the main key and pass `--client-id`.
- Node.js 20+ and a TypeScript runner: `npx tsx` (auto-downloads; or `npm install -g tsx`). Alternatives: `bun`, or Node 22.6+ `node --experimental-strip-types`. No npm packages needed.
- `dig` for DNS checks: `brew install bind` (macOS) or `sudo apt install dnsutils` (Linux).
- No MCP servers needed.

## Install
1. Copy the folder: `cp -r email-deliverability-audit ~/.claude/skills/email-deliverability-audit`
2. Add `SMARTLEAD_API_KEY` from this `.env.example` to `~/.claude/skills/.env` and fill it in.
3. Test access (read-only):
   ```bash
   set -a; source ~/.claude/skills/.env; set +a; npx tsx ~/.claude/skills/email-deliverability-audit/scripts/check-domain-auth.ts --domains=yourdomain.com --out=/tmp/auth-test.csv   # DNS only, no key
   set -a; source ~/.claude/skills/.env; set +a; npx tsx ~/.claude/skills/email-deliverability-audit/scripts/audit-inboxes.ts --all --max-inboxes=5 --out=/tmp/inbox-test.csv          # proves the Smartlead key
   ```

## First run (2 minutes)
Type to Claude: **"Run the email-deliverability-audit on my Smartlead account (skip the spam placement test)."**
Claude pulls the inbox inventory, checks DNS on every sending domain, pulls campaign and inbox stats, and writes `report.md` plus `inboxes.csv`, `auth.csv`, `performance-campaigns.csv` and `performance-inboxes.csv` into `./email-deliverability-audit-output/`. The summary and top actions are shown in chat. Nothing is paused or changed.

## Common errors and fixes
- **DKIM shows missing on every domain** - the default selector is `default` (Zapmail). Google Workspace uses `google`, Microsoft 365 uses `selector1`/`selector2`: pass `--dkim-selector=google`.
- **Per-inbox numbers look tiny** - Smartlead's mailbox-statistics endpoint only returns recent rows; trust `performance-campaigns.csv` for the 1% rule and treat the inbox file as a hint.
- **Spam test stalls or truncates at ~9%** - keep `is_warmup: true`, stay under ~300 senders (about 500 seeds max), and allow 5-20 minutes. Errors on provider ids mean the pool ids changed; check the Smart Delivery docs.
- **429 / 5xx from Smartlead** - the scripts back off and retry 3 times; on big accounts use `--max-campaigns` or `--campaign-ids`.
- **`dig: command not found`** - install dnsutils / bind (see above); every DNS column will otherwise read "missing".
- **New domain fails all checks** - DNS can take up to 48 hours to propagate after setup; re-check later.

## Setup time
10 minutes.

## Cost per run
Free for the audit (Smartlead API reads + DNS lookups). The optional placement test uses Smart Delivery credits and sends real seed emails from your inboxes.
