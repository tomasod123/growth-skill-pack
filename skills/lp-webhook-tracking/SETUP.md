# lp-webhook-tracking setup

## What it does
Gives every paid landing page the same fast custom form that posts to ONE GoHighLevel inbound webhook, tags each lead `lp-<page>` and stores the full Google Ads / UTM detail on the contact.
Includes the Google Ads final URL suffix, the thank-you-page conversion pattern, and a test routine (with a helper script) that never alerts the client.

## What you need
- A GoHighLevel sub-account where you can build workflows and custom fields.
- **GHL_WEBHOOK_URL**: in the sub-account, **Automation > Workflows > Create workflow > Add trigger > Inbound Webhook**, copy the URL it shows. Save the workflow, then send one sample payload (below) so the mapping screen sees every field. **Cost note:** GHL lists Inbound Webhook as a premium trigger, which can be billed per execution on some plans; check your plan's workflow pricing before sending traffic through it.
- **GHL_API_KEY** (only for `verify`): **Settings > Private Integrations > Create new Integration**, tick read-only scopes `contacts.readonly` and `locations/customFields.readonly`, create, copy the `pit-` token (shown once). If the menu item is missing, an agency admin enables Private Integrations (Agency Settings).
- **GHL_LOCATION_ID**: **Settings > Business Profile** ("Location ID"), or the id after `/location/` in the app URL.
- API base `https://services.leadconnectorhq.com`, header `Version: 2021-07-28`, `Authorization: Bearer <token>` (the script sets these).
- Optional **LP_TEST_MARKER**: what every test email contains (default `+lptest`). The workflow's If/Else "Real enquiry" branch must use the same string.
- Google Ads access to set the account-level final URL suffix (Admin or Standard). Tools > Account settings > Tracking.
- Python 3.8+ (stdlib only; `pip3 install certifi` on macOS). No MCP servers.

## Install
1. Copy this folder to `~/.claude/skills/lp-webhook-tracking/`.
2. Add the vars from `.env.example` to `~/.claude/skills/.env` and fill them in.
3. Test (no network): `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/lp-webhook-tracking/scripts/webhook_check.py payload --slug example-service`
4. Prove read access: `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/lp-webhook-tracking/scripts/webhook_check.py verify --email nobody+lptest@example.com` should print NOT FOUND (not an HTTP error).

## First run (2 minutes)
Type to Claude: **"Wire the new landing page /fue-consult/ to our GHL webhook with page tagging and Google Ads tracking, then give me the test steps."**
You get the page's form block (from `templates/lp-form.html` with its slug and label set), the workflow steps and custom fields to create, the final URL suffix, and the exact test commands. Files land in `./lp-webhook-tracking-output/`.

## Common errors and fixes
- **Contact arrives but the tag is missing or reads `lp-{{...}}`**: the Add Tag step is after the If/Else, or GHL stopped resolving the merge field. Move it before the branch; fallback is one If/Else per `service` value.
- **Test "didn't arrive"**: GHL merged it into an older contact with the same email or phone. Use a fresh `+lptest-<n>` email AND a fresh phone each time.
- **A field is sent but empty on the contact** (often `loc` or `last_name`): not mapped in Create/Update Contact. `verify` lists every EMPTY field; map it and re-test.
- **Mapping screen does not offer a field**: GHL only offers fields it has seen. Run `send --yes` with every field once, then map.
- **Webhook replies "test request received"**: the workflow is still a draft. Publish it.
- **Every API call 403 / error 1010**: Cloudflare blocked the user agent; the script sends a browser UA, add `-A "Mozilla/5.0"` to your own curl.
- **Form shows the error and never redirects**: the fetch failed or was not OK (wrong webhook URL, or `mode:'no-cors'` was used). Keep `mode:'cors'`.

## Setup time
30 minutes the first time (workflow, custom fields, URL suffix); 5 minutes per extra page.

## Cost per run
Free for the scripts. The GHL Inbound Webhook trigger is a premium trigger that may bill per execution depending on your plan.
