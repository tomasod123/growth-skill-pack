# Setup: tech-health-check

**What it does:** every morning, checks the tech that silently loses leads (CRM keys, Meta ad account status, Meta-to-CRM lead sync, pipeline, landing pages, cold email inboxes). It turns every problem into a ClickUp task with the fix, assigned to whoever fixes it. It also flags any new client that was set up without a CRM key.

**Setup time:** about 30 minutes (Meta token 15 if you don't have one, 5 per GoHighLevel sub-account, ClickUp 5, config 5).
**API cost:** free. Meta, GoHighLevel, ClickUp, Instantly and Slack webhooks don't charge for these calls.

## What you need

- Python 3.10+ and `pip install pyyaml` (in the shared venv: `~/.claude/skills/.venv/bin/pip install pyyaml`).
- Admin on each client's GoHighLevel sub-account.
- A Meta system user with View performance on the ad accounts (the same token as `lead-flow-watchdog` and `meta-weekly-account-report`).
- A ClickUp list for fix tasks, and the user id of the person who fixes things.

### Keys (`~/.claude/skills/.env`)

| Variable | Required | Where to get it |
|---|---|---|
| `GHL_TOKEN_<CLIENT>` (one per client, any name) | Yes | Step 1 |
| `META_ACCESS_TOKEN` | For checks 3 to 6 | Step 2 |
| `CLICKUP_API_TOKEN` | For `--create-tasks` | Step 3 |
| `GHL_AGENCY_TOKEN` | No, but it's how unmanaged sub-accounts (new clients) get found | Step 4 |
| `INSTANTLY_API_KEY` | No | Step 5 |
| `SLACK_WEBHOOK_URL` | No, only for `--send` | Step 6 |

**1. GoHighLevel Private Integration Token, one per client**
1. Open the client's sub-account (not the agency view) > **Settings > Private Integrations > Create new integration**. Name it "Health check (read-only)".
2. Tick only: `contacts.readonly`, `opportunities.readonly`, `locations.readonly`. Create.
3. Copy the token (it's shown once) into `.env` as `GHL_TOKEN_EXAMPLE=...`.
4. The location id is in the browser URL after `/location/`. It goes in `config.yaml`.

**2. Meta system user token** (skip if you already have one)
business.facebook.com > Business Settings > Users > System users > Add (Employee). Assign assets > Ad accounts > View performance. Generate new token, expiry Never, tick `ads_read`. Paste as `META_ACCESS_TOKEN`. Ad account ids keep the `act_` prefix.

**3. ClickUp**
ClickUp > avatar > Settings > Apps > API Token > Generate. Paste as `CLICKUP_API_TOKEN`.
List id: open the list, the number after `/li/` in the URL (or the list's ... > Copy link). User id: Workspace settings > People, or ask Claude to look it up with the token.

**4. Agency token (finds new clients without a key)**
In the agency view: Settings > Private Integrations > Create, tick `locations.readonly`. Paste as `GHL_AGENCY_TOKEN`. Company id: Agency view > Settings > Company, or the `companyId` in any location's API response.

**5. Instantly (optional)**
Instantly > Settings > Integrations > API keys > Create (v2, read scope). Paste as `INSTANTLY_API_KEY` and set `instantly: true` in config.

**6. Slack (optional)**
api.slack.com/apps > Create App > Incoming Webhooks > on > Add to channel. Paste as `SLACK_WEBHOOK_URL`.

## Install and test

```bash
cd ~/.claude/skills/tech-health-check
cp config.example.yaml config.yaml          # add clients, location ids, ad accounts, pages
python3 scripts/health_check.py --demo      # see every kind of finding with fake data
set -a; . ~/.claude/skills/.env; set +a; python3 scripts/health_check.py   # real, read-only
```

Read `tech-health-check-output/REPORT.md`. When it looks right, add `--create-tasks` and put it on the morning cron (see SKILL.md).

## First thing to type

> Run the tech health check in demo mode, then set it up for my clients and show me which ones have no CRM key yet.
