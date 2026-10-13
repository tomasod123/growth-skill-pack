# ghl-funnel-backend setup

## What it does
Wires and checks everything behind a GoHighLevel funnel: the nudge workflow's exit condition, the booking-confirmation workflow, field mapping and sticky contact, calendar event titles and merge fields, the single meeting-link source, prefill links, redirects and QR codes.
Diagnoses through read-only API calls and hands back paste-ready workflow specs and message copy for whoever builds in the UI.

## What you need
- A GoHighLevel sub-account with the funnel, survey/form and calendar built (or being built).
- **GHL_API_KEY**: sub-account **Settings > Private Integrations > Create new Integration**, name it e.g. "Read-only funnel QC", tick only these read-only scopes, create and copy the `pit-` token (shown once). If the menu item is missing, an agency admin enables Private Integrations (Agency Settings).
  - `calendars.readonly`, `calendars/events.readonly` (calendar config, event titles, bookings)
  - `contacts.readonly` (did email and phone save)
  - `conversations.readonly`, `conversations/message.readonly` (which messages went out, with status)
  - `locations.readonly` (timezone), `locations/customValues.readonly` (link custom values)
  - `workflows.readonly` (publish status), `phonenumbers.read` (can the location send SMS)
  - `surveys.readonly`, `forms.readonly` (optional, submission checks)
- **GHL_LOCATION_ID**: **Settings > Business Profile** ("Location ID", copy icon), or the id after `/location/` in the app URL.
- API: base `https://services.leadconnectorhq.com`, headers `Authorization: Bearer <token>`, `Version: 2021-07-28` (calendar endpoints use `Version: 2021-04-15`), and a browser User-Agent (`curl -A "Mozilla/5.0"`).
- curl and Python 3. On macOS `pip3 install certifi`. For QR checks: `pip3 install zxing-cpp pillow`.
- Works best alongside `ghl-account-audit` and `ghl-survey-qc` from this pack. No MCP servers.

## Install
1. Copy this folder to `~/.claude/skills/ghl-funnel-backend/`.
2. Add the vars from `.env.example` to `~/.claude/skills/.env` and fill them in.
3. Prove read access (one GET, lists calendars):
   `set -a; source ~/.claude/skills/.env; set +a; curl -s -A "Mozilla/5.0" -H "Authorization: Bearer $GHL_API_KEY" -H "Version: 2021-04-15" "https://services.leadconnectorhq.com/calendars/?locationId=$GHL_LOCATION_ID" | head -c 300`
   You should see JSON starting `{"calendars":[...`.

## First run (2 minutes)
Type to Claude: **"Wire the backend for our demo-request funnel: nudge workflow, booking confirmation, and check the calendar and meeting link. Calendar id <id>."**
You get the two-workflow spec (nudge with exit condition, booked workflow that removes from the nudge), confirmation SMS/email/WhatsApp copy using the real event title, a meeting-link audit and the QC gate checklist. Files land in `./ghl-funnel-backend-output/`.

## Common errors and fixes
- **Lead booked but still got "book a call"**: the nudge has no exit condition. Add the If/Else "has appointment on this calendar" after the wait AND a "Remove from nudge workflow" as the first step of the booked workflow. Changing the delay does not fix it.
- **Contact saved with no email**: the email already belongs to another contact in the location (duplicate rule), or partial contact creation saved a half-finished survey. Search the email first; test with a fresh `+alias` every time.
- **Calendar does not prefill**: sticky contact is on the calendar's custom FORM, not the calendar settings. Check `localStorage.getItem('_ud')` on the booking page; it only works on the same domain.
- **WhatsApp never delivered**: free-form messages need a reply in the last 24 h; first contact needs an approved template. A blank merge field fails the whole send (Meta error 132000).
- **Short link lost its prefill**: query strings appended to a trigger-link short URL are dropped. Put the merge fields inside the trigger link's destination URL instead.
- **401 "not authorized for this scope" on DELETE or any write**: expected with a read-only token. Make the change in the UI.
- **Every call 403 / error 1010**: Cloudflare blocked curl's user agent. Add `-A "Mozilla/5.0"`.

## Setup time
10 minutes.

## Cost per run
Free (GHL API reads are included in the subscription).
