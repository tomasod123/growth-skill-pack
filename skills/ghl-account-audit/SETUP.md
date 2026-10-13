# ghl-account-audit setup

## What it does
Reads a whole GoHighLevel sub-account with GET requests only and ranks what would stop a launch (P0), cost money this week (P1) or is tidying (P2).
Writes AUDIT.md, a VA-ready FIXES.md and raw JSON of every endpoint; never sends, changes or enrols anything.

## What you need
- A GoHighLevel sub-account you (or the agency) can open with admin rights.
- **GHL_API_KEY** (a Private Integration token, PIT). In the sub-account: **Settings > Private Integrations > Create new Integration**. Name it e.g. "Read-only audit", then tick only the **View / readonly** scopes below, create, and copy the token (it starts `pit-` and is shown once). If Private Integrations is missing from the menu, an agency admin has to enable it (Agency Settings > Private Integrations, or Labs on older accounts). Scopes this skill reads (tick what you can; any you skip just show up as "not readable" INFO rows):
  - `locations.readonly` (business profile), `users.readonly`, `phonenumbers.read`
  - `locations/customValues.readonly`, `locations/customFields.readonly`, `locations/tags.readonly`, `locations/templates.readonly`, `locations/tasks.readonly`
  - `contacts.readonly`, `conversations.readonly`, `opportunities.readonly` (pipelines + opportunities)
  - `workflows.readonly`, `calendars.readonly`, `calendars/groups.readonly`
  - `forms.readonly`, `surveys.readonly`, `funnels/funnel.readonly`
  - `emails/builder.readonly`, `emails/schedule.readonly`, `medias.readonly`, `links.readonly`
  - `socialplanner/account.readonly`, `payments/integration.readonly`, `payments/orders.readonly`, `products.readonly`
  - `businesses.readonly`, `campaigns.readonly`, `objects/schema.readonly`, `voice-ai-agents.readonly`, `blogs/list.readonly`, `store/setting.readonly`
  - Do NOT tick any write scope. A read-only token cannot do damage if a command goes wrong.
- **GHL_LOCATION_ID**: **Settings > Business Profile**, "Location ID" field (copy icon), or the id in the browser URL after `/location/` (`app.gohighlevel.com/v2/location/<LOCATION_ID>/...`; white-label app domains use the same path).
- API: base `https://services.leadconnectorhq.com`, header `Version: 2021-07-28` and `Authorization: Bearer <token>`. The script sets these; the token only works on v2 (not the old `rest.gohighlevel.com/v1`).
- Python 3.8+. Stdlib only. On macOS also run `pip3 install certifi` so TLS works.
- No MCP servers.

## Install
1. Copy this folder to `~/.claude/skills/ghl-account-audit/`.
2. Add the vars from `.env.example` to `~/.claude/skills/.env` and fill them in.
3. Test (prints options, makes no calls): `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ghl-account-audit/scripts/audit.py --help`
4. Prove access (one read-only GET):
   `set -a; source ~/.claude/skills/.env; set +a; curl -s -A "Mozilla/5.0" -H "Authorization: Bearer $GHL_API_KEY" -H "Version: 2021-07-28" "https://services.leadconnectorhq.com/locations/$GHL_LOCATION_ID" | head -c 300`
   You should see JSON starting `{"location":{...`.

## First run (2 minutes)
Type to Claude: **"Audit the GHL account for Clinic A before we turn the ads on. Real address is <address>, main line is <phone>, market UK."** For a US business: **"Audit the GHL account for Clinic A before we turn the ads on. Real address is <address>, main line is <phone>, market US."** (No market given = ANY.)
You get the P0/P1/P2 counts and the launch blockers in chat. Files land in `./ghl-account-audit-output/` (AUDIT.md, FIXES.md, raw/*.json). Hand FIXES.md to whoever makes the changes.

## Common errors and fixes
- **Every call 403 / "error code: 1010"**: Cloudflare blocked the user agent. The script sends a browser User-Agent; for your own curl calls add `-A "Mozilla/5.0"`.
- **TLS / CERTIFICATE_VERIFY_FAILED on macOS (or an account that looks completely empty)**: `pip3 install certifi`, or prefix the command with `SSL_CERT_FILE=$(python3 -m certifi)`.
- **401 "Api key is invalid"**: you called the v1 API with a `pit-` token. Use `services.leadconnectorhq.com` with the `Version` header.
- **403 on everything**: the token belongs to another sub-account. PITs are per location; create one in this sub-account.
- **401 "The token is not authorized for this scope" on one endpoint**: add that View scope to the PIT (edit the integration). The report shows it as INFO and asserts nothing about that area.
- **Workflow triggers/steps not in the report**: expected. The API only lists name and status; open each workflow in the UI.

## Setup time
10 minutes.

## Cost per run
Free (GHL API calls are included in the subscription). About 90 seconds per account.
