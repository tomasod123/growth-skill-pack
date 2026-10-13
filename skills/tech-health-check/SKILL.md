---
name: tech-health-check
description: Daily read-only check of the tech that silently loses leads, with the fix for every problem written into a ClickUp task for whoever fixes it. Checks, per client - (1) no CRM key at all, meaning a new client was onboarded without a GoHighLevel Private Integration Token (fix - create a read-only PIT in the sub-account, add it to config); (2) CRM key rejected 401/403 (fix - check the sub-account is active, recreate the PIT); (3) Meta ad account not active, e.g. grace period after a failed card, payment needed, disabled (fix - pay the balance, add a backup card, Account Quality for restrictions); (4) Meta leads not reaching the CRM, with the date of the last one that did and how many were missed (fix - select all Facebook pages, check form field mapping, reconnect, Troubleshooting > Sync Leads for 15 days, tag recovered contacts and run a separate reactivation, never the normal new-lead workflow); (5) only some leads reaching the CRM (fix - map the missing form, add it to the workflow trigger); (6) ads spent nothing yesterday (fix - delivery column, billing, Account Quality); (7) pipeline frozen while leads arrive (fix - workflow published, execution logs, opportunity step); (8) landing or booking page down or SSL wrong (fix - attach the custom domain, restore the page, pause ads); (9) cold email inboxes disconnected in Instantly (fix - reconnect, warm-up, DNS). Agency level - sub-accounts in GoHighLevel with no health check, i.e. a new client nobody wired up. Use when the user says "health check", "tech check", "is anything broken", "check integrations", "are leads reaching the CRM", "which clients have no PIT", "new client setup check", "morning check", or "something's down".
---

# Tech health check

Read-only on Meta, GoHighLevel, Instantly and your pages. It never edits contacts, workflows, ads or settings.
The only things it can write are what you ask for: ClickUp fix tasks (`--create-tasks`) and a Slack summary (`--send`).

**Why it exists:** a lead sync can break on a Tuesday and look fine for two weeks, because the ads keep running and Meta keeps reporting leads. The leads just never reach the CRM, so nobody texts or calls them. An alert in a chat channel is easy to miss. A task with the fix in it, assigned to a named person, is not.

Use `~/.claude/skills/.venv/bin/python3` when it exists.

## How to run

From the skill folder:

```bash
python3 scripts/health_check.py --demo                    # fixture data, no API calls, safe to try
python3 scripts/health_check.py                           # every active client: print + write the report
python3 scripts/health_check.py --client "Example Clinic" # one client
python3 scripts/health_check.py --create-tasks            # one ClickUp task per problem, assigned, with the fix
python3 scripts/health_check.py --send                    # Slack summary if anything is WARNING or worse
```

Default is print and write `./tech-health-check-output/REPORT.md` and `findings.json`. Only use `--create-tasks` or `--send` when the user asks.
If `config.yaml` or the keys are missing, point the user to `SETUP.md`. Exit code is 1 when anything is CRITICAL, so a cron wrapper can react.

## Run it every morning

```bash
crontab -e
# 07:00 every day: check, create/update fix tasks, post the summary
0 7 * * * cd ~/.claude/skills/tech-health-check && set -a && . ~/.claude/skills/.env && set +a && ~/.claude/skills/.venv/bin/python3 scripts/health_check.py --create-tasks --send >> ~/tech-health.log 2>&1
```

How the tasks behave, so nobody gets spammed:
- One task per client and problem. It goes to `routing.clickup_list_id`, assigned to `routing.clickup_assignee_id`, CRITICAL due in 4 hours, WARNING in 24.
- Still happening the next morning: one comment on the same task, not a new task.
- Task closed but still happening: a fresh task.
- Problem gone: a "looks fixed" comment, then it stops tracking it.

## The checks and the fixes

| # | Problem | How it's spotted | Severity | The fix (full steps go in the task) |
|---|---|---|---|---|
| 1 | **New client with no CRM key** | Client in config with no token or no location id. Agency level: a sub-account in GoHighLevel that isn't in config at all | CRITICAL / WARNING | Create a read-only Private Integration in the sub-account, put the token in `.env`, add the client to config. Make it step 1 of onboarding |
| 2 | CRM key rejected | `/contacts/search` returns 401 or 403 | CRITICAL | Check the sub-account is still active, recreate the PIT, replace it in `.env` |
| 3 | Meta ad account not active | `account_status` is grace period (9), unsettled (3), disabled (2), risk review, closure | CRITICAL | Pay the balance, fix the card, ask the client for a backup card. Account Quality for restrictions. Then re-check the lead sync, because pauses are when it drops |
| 4 | **Meta leads not reaching the CRM** | 3+ Meta leads since yesterday, 0 CRM contacts with a Facebook/Instagram source or `meta` tag. Reports the last one that arrived and the leads since | CRITICAL | Select all Facebook pages + Sync leads, check Form Field Mapping, reconnect (sometimes twice), Leads access for LeadConnector in Meta Business Settings. Recover with Troubleshooting > Sync Leads (15 days) or the form CSV (90 days). Recovered contacts start no workflow: tag them, Smart List, separate reactivation after the client approves the wording |
| 5 | Only some leads reaching the CRM | 5+ Meta leads, under half in the CRM | WARNING | Map and enable the missing form, add it to the workflow trigger, sync the last 15 days |
| 6 | Ads not spending | Yesterday's spend 0 against a 7-day average above 5 | WARNING | Delivery column, rejected ads, billing, Account Quality, budgets and end dates |
| 7 | Pipeline frozen | Opportunity total unchanged for 22h+ while 3+ new Meta contacts arrived | WARNING | Workflow published? Execution logs, the Create Opportunity step's pipeline and stage |
| 8 | Page down or SSL wrong | Each URL in `sites`: SSL error, connection error, or 400+ | CRITICAL | SSL: attach the custom domain at the host and wait for the certificate. 404/5xx: restore the page or repoint the ads. Pause ads if not fixed within the hour |
| 9 | Cold email inboxes disconnected | Instantly accounts with an error status | WARNING | Reconnect (expired app password or OAuth), check warm-up, check DNS if many failed together |

### Not checkable by API, so put them on a weekly checklist

- **CRM wallet top-ups failing** (texts and calls stop when the wallet is empty). Agency view > the sub-account > Billing: card declined? Update the card or ask the client to. Turn on low-balance email alerts.
- **SMS number registration** (A2P in the US, regulatory bundles in the UK and Australia). A new client can't send texts until it's approved, which takes 1 to 3 working days. In the UK and Australia a texting number must be **Mobile**, never Local.
- **Calendar not connected** to the person's Google or Outlook calendar, so people book over existing appointments. Calendars > Connections.
- **Sticky contact off**, so names don't carry from form to calendar. Settings > Business Profile.

## Gotchas learned the hard way

- An inactive or cancelled sub-account also returns 401. Mark former clients `active: false` or the check cries wolf every morning, and people learn to ignore it.
- `Sync Leads` only reaches back **15 days**. If a sync has been broken longer, the Meta form CSV (90 days) is the only way back. That makes speed matter.
- A billing problem and a sync break can happen in the same week and still be separate faults. Check the timestamps (Ads Manager > Account activity) before telling a client which one caused what.
- Count Meta leads with `action_type == "lead"` only. Summing every action containing "lead" double counts.
- Never test a client's live form with a real-looking lead. Use a clearly fake name, a fresh `+alias` email each time, and delete it afterwards.
