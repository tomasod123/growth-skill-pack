---
name: ghl-account-audit
description: Read-only pre-launch QC of a whole GoHighLevel (GHL) sub-account. One GET-only sweep of business profile, users, phone numbers, custom values, workflows, calendars, forms, surveys, funnels, pipelines, contacts, conversations, integrations and email, scored P0/P1/P2 with evidence, owner and a minute estimate, written as AUDIT.md plus a VA-readable FIXES.md plus raw JSON. Use it on a new account before the first ad or text goes out, when a database reactivation is about to run, when a snapshot has just been installed, when someone says "nothing happened after the lead came in", and quarterly on every live account. Triggers on "audit the GHL account", "audit the sub-account", "is the account ready to launch", "pre-launch QC", "what is wrong with this sub-account", "check the account before we turn the ads on", "why did nobody get notified".
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./ghl-account-audit-output/`.

# GHL account audit

## What it is

One script that reads everything a location Private Integration token (PIT) can see in a GoHighLevel
sub-account, and turns it into:

- `AUDIT.md` - findings ranked P0 / P1 / P2, each with the raw evidence, who fixes it and a minute
  estimate; an at-a-glance table of the account; and a list of every endpoint it read with its HTTP
  status, so "we did not check that" and "the token cannot see that" never get confused.
- `FIXES.md` - the same list rewritten so a VA can work it top to bottom with no background, one
  screen per item, with a Done-when line that demands the setting is read back.
- `raw/*.json` - every response, so a later question does not need another sweep.

P0 means it blocks or risks the launch. P1 means fix this week. P2 is tidying. INFO is for the record.

## When to use it

- **New account onboarding QC.** Run it the day the snapshot is installed and again the day before the
  first ad. A freshly installed snapshot is not a configured account.
- **Before any launch**, paid or organic, and before any database reactivation or text wave.
- **When someone says a lead got no reply.** The answer is almost always an unpublished workflow, an
  empty notification merge field, or a number with no forwarding.
- **Quarterly** on every live account, because accounts drift.

## The hard rule

**Reads only. GET requests only.** Never POST, PUT, PATCH or DELETE. Never message a contact, never
enrol anyone in anything, never change a setting, never submit a test form. If checking something would
need a write, record it as "UI-only, check before launch" and move on. The script never prints the
token and never writes it into a file or a log. Give it a PIT with View (read-only) scopes only, so a
mistake cannot write either.

This matters more than usual here: the same base URL that lists workflows also sends texts.

## Run it

Each Claude Bash call is a fresh shell, so load the env in the same call as the script:

```bash
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ghl-account-audit/scripts/audit.py \
  --client         "Clinic A" \
  --expect-address "1 Example Street, Exampletown AB1 2CD" \
  --expect-phone   "<the business's real main line>" \
  --country        ANY \
  --out            ./ghl-account-audit-output/clinic-a
```

- Token: read from the env var named by `--token-env` (default `GHL_API_KEY`). Pass the **name** of the
  variable, never the value. For several accounts, keep one var per account (e.g. `GHL_API_KEY_CLINIC_A`)
  and pass `--token-env GHL_API_KEY_CLINIC_A --location <its id>`.
- Location: `--location`, or `GHL_LOCATION_ID` from the env.
- `--expect-address` and `--expect-phone` are the business's real details from your own records, so the
  script can tell you the account disagrees with them.
- `--country` (UK, IE, AU, US, ANY; default ANY) sets the mobile-number check and the consent-law wording.
  Pass the market you text in, e.g. `--country US` for a US business (TCPA/A2P wording, US phone format).
- `--owner-ops`, `--owner-lead`, `--owner-client` set the names in the Who column (defaults: "VA / account
  admin", "Account lead", "The client").

It prints `P0=n P1=n P2=n` and the P0 titles, then exits 0. Stdlib only; uses `certifi` if installed.

## Endpoints, and the gotchas that cost time

Base `https://services.leadconnectorhq.com`, headers `Version: 2021-07-28`, `Authorization: Bearer <PIT>`,
`Accept: application/json`, plus a browser `User-Agent`.

| Reads cleanly | Notes |
|---|---|
| `/locations/{loc}` | The whole business profile, plus `snapshotId` (proves whether anything has been adapted) and `settings.allowDuplicateContact` |
| `/users/?locationId=` | Then `/users/{id}` for the full `permissions` object. `lcPhone: {}` means calls cannot ring that user |
| `/phone-system/numbers/location/{loc}` | `capabilities`, `isDefaultNumber`, `forwardingNumber`, `linkedRingAllUsers`, `friendlyName`. Recording, whisper and Call Connect are **not** here |
| `/locations/{loc}/customValues` | The placeholder trap lives here |
| `/locations/{loc}/customFields` | Where consent fields are found, or found missing |
| `/locations/{loc}/tags` | Empty means no segmentation exists |
| `/locations/{loc}/templates?originId={loc}&deleted=false` | SMS templates and snippets. Needs `originId`, not just `locationId` |
| `/emails/builder?locationId=` | Email templates; the snapshot's boilerplate shows up here |
| `/workflows/?locationId=` | List only, see below |
| `/calendars/groups?locationId=` | Can work even when `/calendars/` 401s |
| `/forms/`, `/forms/submissions`, `/surveys/`, `/surveys/submissions` | Submission counts are the honest measure of whether anything is live |
| `/funnels/funnel/list?locationId=` | `domainId: ""` means preview URL only |
| `/opportunities/pipelines`, `/opportunities/search?location_id=` | Note `location_id` with an underscore on search, `locationId` everywhere else |
| `/contacts/?locationId=&limit=100` | Page on `meta.startAfterId` + `meta.startAfter` |
| `/conversations/search?locationId=` | `unreadCount` + `lastMessageDirection: inbound` finds the ignored lead |
| `/social-media-posting/{loc}/accounts` | Facebook and Instagram inbox connections |
| `/payments/integrations/provider/whitelabel?altId={loc}&altType=location` | `altId`/`altType`, not `locationId` |
| `/objects/`, `/products/`, `/links/`, `/businesses/`, `/campaigns/`, `/voice-ai/agents`, `/blogs/site/all`, `/emails/schedule`, `/locations/{loc}/recurring-tasks`, `/store/store-setting` | Round out the sweep |

Gotchas, each of which has burned a session:

- **Cloudflare 1010-blocks the default urllib and curl user agents.** Send a browser User-Agent or
  every call reads as a dead token.
- **macOS Python may have no CA bundle.** Install `certifi` (the script uses it automatically), or the
  whole run fails on TLS and can look like a clean empty account.
- **`pit-` tokens are v2 only.** Against the old `rest.gohighlevel.com/v1/` API they return 401 "Api key
  is invalid", which reads as a dead token and triggers a pointless rotation.
- **Tokens are location-scoped.** One sub-account PIT per location; another location returns 403.
- **A missing scope looks like a missing feature.** A 401 "The token is not authorized for this scope"
  means tick that View scope on the PIT, not that the account has none.
- **Workflows are a list and nothing more.** `GET /workflows/?locationId=` returns only id, name,
  status, version and timestamps. There is **no trigger data and no step data**, and
  `GET /workflows/{id}` 404s. So "which workflows can message a contact today", "which set DND", and
  "which Remove-from-workflow steps silently exclude newer workflows" are UI-only questions. The
  script says so explicitly rather than implying it checked. (The UI's own endpoint,
  `backend.leadconnectorhq.com/workflow/{id}`, returns 401 not 404: it exists but needs the browser
  session token, not a PIT.)
- **`/medias/files` 422s without `&type=file`.**
- **`/calendars/?locationId=` can 401 on a token missing the calendars scope** while `/calendars/groups`
  returns 200. Record it as not readable; do not conclude there are no calendars.
- **There is no public endpoint for the LC Email sending domain.** `/emails/domains` and
  `/emails/verified-domains` both 404. Read `location.defaultEmailService` and check the UI.
- **There is no public endpoint for the Meta lead-ads connection, Google, Stripe or calendar sync**, and
  `/oauth/installedLocations`, `/snapshots/`, `/custom-menus/` and `/conversations/providers` all 401 on
  a location PIT.
- **Form and funnel notification settings are UI-only.** Never report "submissions go nowhere" from the
  API; report that it has to be checked.
- A **workflow's inline copy beats the custom value it appears to use.** An empty custom value is a red
  flag, not proof: the live step may carry typed text. Diagnose the actual send from the conversation.

## What the output looks like

`AUDIT.md` opens with the counts and a "What blocks the launch" bullet list, then one row per finding
with evidence quoted from the JSON, then the at-a-glance table, then the endpoint list with statuses.
`FIXES.md` is P0/P1/P2 sections, each item naming who, how many minutes, what they will see on screen,
and a Done-when that requires reading the new value back and posting a screenshot in the task.

Add a "notes the sweep cannot infer" section by hand for anything your own records know and the API
cannot: a config that was reported done but does not read back, a deliberate address variant, a
consent decision.

## What a first sweep can look like (hypothetical)

Picture an account built from a snapshot shortly before its first ads and a database reactivation. One
sweep, a couple of minutes, and the P0s might be:

1. **Zero contacts** (`total: 0`). No database was ever imported, so the reactivation cannot run at all,
   whatever the team thinks the blocker is.
2. **Every custom value empty**, including the terms link, business phone, booking page and the
   notification number and email. Messages would send blanks or literal placeholder text, and nobody
   would be told a lead arrived.
3. **Every workflow in draft**, including the opt-out / STOP workflow. A form submission lands and
   produces nothing, and a STOP reply opts nobody out.
4. **The texting number has `forwardingNumber: ""` and `linkedRingAllUsers: []`**, even though someone
   recorded it as "forwarding to the business". A caller reaches nobody.

P1s in that kind of account: a personal mobile on the Business Profile instead of the main line, a
template funnel still live with leftover template copy, no tags, and the number still carrying a personal
friendly name.

The lesson worth keeping: **a freshly installed snapshot reads as a full account and is an empty one.**
Dozens of workflows, pipelines and merge fields can all exist and not one of them will do anything.

## One behaviour to keep

The script **never asserts absence from an endpoint that did not return 200.** A 401, 403, 404 or 422
becomes an INFO row naming the endpoint and its status, and the matching "X does not exist" finding is
suppressed. Pointing a wrong-location token at an account gives 0 P0 and a list of unreadable endpoints,
instead of an unreadable account reading as an empty one.

## Related skills in this pack

- `ghl-survey-qc` - the survey/form settings and the mobile fold, from the public widget page.
- `ghl-funnel-backend` - wiring workflows, confirmations and calendars once the account can deliver.
- `lp-webhook-tracking` - custom-coded landing page forms feeding one inbound webhook.
