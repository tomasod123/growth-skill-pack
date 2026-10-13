---
name: lp-webhook-tracking
description: A standard for paid-traffic landing pages that feed GoHighLevel (GHL). One custom-coded form on every page (loads in under a second, unlike an embedded GHL form that can take ~5s), ONE inbound webhook workflow per account for all pages, a tag per page built from a hidden page slug, Google Ads detail on every lead (campaign, ad group, keyword, match type, device, network, location, gclid), a service-aware thank-you page that Google Ads counts as the conversion, and a test routine that never alerts the client or sales team. Use when building or wiring landing pages, adding a new page to an existing set, "connect the form to GHL", "one webhook", "tag leads by landing page", "which campaign did this lead come from", "segment leads", "segment by tag", "smart list per landing page", "final URL suffix", or when a GHL-embedded form is slowing a page down.
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./lp-webhook-tracking-output/`.

# Landing pages -> one webhook -> tags -> tracking

**Outcome:** every lead lands in the GHL sub-account within seconds, tagged with the page it came from
and carrying the ad details, while the page loads fast and tests never reach the client or the sales
team.

Starting points in this skill:
- `templates/lp-form.html` - the form card + JS every page shares (full-name split, UTM/click-id capture,
  CORS POST, redirect only on success).
- `scripts/webhook_check.py` - print the sample payload, send one test POST to the webhook (only with
  `--yes`), and read the resulting contact back (read-only) to check tag and every mapped field.

Write generated page blocks, workflow specs and test notes to `./lp-webhook-tracking-output/` unless
the user names a project folder. Run scripts from that working folder by their absolute path, and since
each Claude Bash call is a fresh shell, prefix every script command in the same call with
`set -a; source ~/.claude/skills/.env; set +a;`, e.g.
`set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/lp-webhook-tracking/scripts/webhook_check.py payload --slug <slug>`.

If you build the pages themselves, `ghl-landing-page` or `design-website` cover the layout; `page-cro`
and `optimize-ppc-lp` cover the copy and conversion side.

## 1. How it fits together
1. Every page uses the **same form code**. The only per-page differences are two constants:
   `SERVICE_SLUG` (e.g. `fue-hair-transplant`, `ehr-integration-demo`) and `SERVICE_LABEL` (readable,
   e.g. "FUE Hair Transplant (London)").
2. The form `fetch`es JSON to **one** GHL inbound webhook (`mode:'cors'`, never `no-cors`: the response
   must be readable). It only redirects to the thank-you page when `r.ok`, so a redirect proves delivery.
   GHL inbound webhook URLs accept browser POSTs (CORS preflight allows any origin). A published workflow
   answers with a "trigger execution" style message; a draft one answers "test request received", which
   is a quick way to tell a draft from a live workflow.
3. The GHL workflow: **Inbound Webhook** trigger -> **Create/Update Contact** (map fields) -> **Add Tag**
   `lp-{{inboundWebhookRequest.service}}` -> **If/Else "Real enquiry" = Email does not contain
   `<your test marker>`** -> client alert, tags, nurture. None -> END.
   - Pick one test marker and use it on every test: a `+lptest` alias (the script's default) or your own
     company domain (set `LP_TEST_MARKER`).
   - **The dynamic tag works** (tested live: a `service` value of `<slug>` became the tag `lp-<slug>`
     within about 45 s). One Add Tag step covers every page, so a new page needs
     NO workflow change, just a new `SERVICE_SLUG`. Put the step before the Real-enquiry branch so tests
     get tagged too.
   - Fallback only if a future GHL change breaks it (tag blank or literal `lp-{{...}}`): an If/Else per
     `service` value, each adding `lp-<slug>`.
4. The thank-you page (`/thank-you/?service=<slug>&utm...`) is the Google Ads conversion. It reads
   `service` to pick the right booking button and wording (e.g. a free consult vs a standard paid
   consult, or a demo vs a pricing call). Never show an offer on the thank-you page that only some pages
   make.
5. Tag manager is host-gated (`/(^|\.)yourdomain\.com$/`) so previews and localhost never fire
   conversions. Landing pages are `noindex`.

## 2. Payload (what every form sends)
`first_name, last_name, full_name, phone, email, message, service, service_label, page_url, consent,
utm_source, utm_medium, utm_campaign, utm_content, utm_term, gclid, fbclid, wbraid, gbraid, campaign_id,
adgroup_id, matchtype, device, network, loc, submitted_at`

**Name field (hard rule):** the form asks for ONE `Full name` input (`id="fullName" autocomplete="name"`).
Page JS splits it before the POST: first word = `first_name`, the rest = `last_name`, plus `full_name`.
Never a first-name-only field. The GHL Create/Update Contact action must map `last_name` too (UI step).
`templates/lp-form.html` does the split.

Custom fields to create per account (Single line text, Contact): Landing Page (<- service_label), Google
Ads Click ID (<- gclid), utm_source / utm_medium / utm_campaign / utm_content / utm_term, Google Campaign
ID, Google Ad Group ID, Match Type, Device, Network, Location ID.

## 3. Google Ads side (the media buyer, one-time per account)
Account-level final URL suffix:
`utm_source=google&utm_medium=cpc&utm_campaign={_campaign}&utm_content={creative}&utm_term={keyword}&campaign_id={campaignid}&adgroup_id={adgroupid}&matchtype={matchtype}&device={device}&network={network}&loc={loc_physical_ms}`
plus a campaign-level custom parameter `_campaign` with a short readable name. Conversions = the
thank-you page URL(s). For Meta traffic, add `utm_source=facebook&utm_medium=paid&utm_campaign={{campaign.name}}&utm_content={{ad.name}}` in the ad's URL parameters; `fbclid` arrives on its own.

## 4. Build rules for the pages
- Build from the client's LIVE approved page, not from scratch; copy CSS, form card, form JS and the tag
  manager snippet verbatim.
- Form above the fold at 390 / 430 / 1440 px wide (fields at least visible at 320 / 360). No nav menu, no
  chat widget. High-contrast button on the brand colour.
- Speed: avatars under ~120px get 240px webp thumbnails; hero srcset capped at 1200w; only the font
  weights used; below-fold images lazy. Target under ~200KB at 390px.
- Regulated clients (healthcare, medical, therapy): facts only from the client's own site; never infer
  ethnicity, faith or language from a photo; no testimonials, outcome promises or superlatives where the
  rules forbid them (UK ASA/CAP, Meta health policies, HIPAA-sensitive wording in the US). Do one
  compliance QC read against the client's profiles and pricing before going live (`persona-qc` if you
  have it).
- HIPAA note for US healthcare: a webhook payload with name + contact + a condition-specific service
  slug can be PHI. Keep the free-text `message` field optional, keep the GHL account under a BAA if
  required, and do not send the service slug or message to ad platforms.

## 5. Test routine (never alert the client)
1. See the Real-enquiry branch first (screenshot from whoever built it): email does NOT contain your test
   marker.
2. Test from a preview or a `python3 -m http.server` copy (tag manager stays off there), with a
   `you+lptest-<n>@yourcompany.com` email AND a unique phone. GHL merges contacts on email and on phone,
   so reused values look like "the test didn't arrive".
3. Pass = redirect to `/thank-you/` + the contact in GHL with Landing Page, UTMs and gclid filled, tag
   `lp-<slug>` present, and NO client-side tags or alert (it went to END). Check via API:
   `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/lp-webhook-tracking/scripts/webhook_check.py verify --email you+lptest-<n>@yourcompany.com --slug <slug>`
   (read-only `POST /contacts/search` then `GET /contacts/{id}`).
4. Fastest workflow-only test (no page, no browser): `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/lp-webhook-tracking/scripts/webhook_check.py send
   --webhook <url> --email you+lptest-<n>@yourcompany.com --phone <unique> --slug <slug> --yes`, wait ~45 s, then
   `verify`. This creates one real contact, so only with the test marker email.
5. To check what a page sends without touching GHL: override `window.fetch` in the browser console and
   read the body.

## 6. Segmenting (what the tags buy you)
Every lead carries `lp-<slug>` (which page) plus custom fields (campaign, ad group, keyword, match type,
device, network, location). So in GHL you can:
- **Smart Lists** per page: Contacts > filter Tag is `lp-fue-hair-transplant`. One saved list per page or
  service family.
- **Page-specific follow-up:** a workflow triggered by *Contact Tag added = lp-free-consult* sends that
  page's own nurture/offer while other pages get the standard one.
- **Per-page alerts or routing:** If/Else on the tag to route to the right clinician, rep or setter.
- **Reporting:** count leads per tag per week, and per Campaign ID / Device / Match Type field, to show
  which page and keyword brings enquiries (pair with the media buyer's spend for cost per lead by page).
- **Bulk actions:** filter by tag > bulk add to a campaign, export, or re-engage.

Limits: tags say which PAGE, not which booking. Bookings made in an external system (practice management
or booking software, a separate scheduler) are not in GHL, so page-to-booked needs that system's data.

## 7. Going live
Take a timestamped backup of the current site before and after the deploy, deploy with your host
(Netlify, Vercel, any static host, or the GHL custom-code block), then curl every page for the webhook URL
and the tag manager id, and record the deploy ids in your project notes.

## Gotchas
- After mapping, read ONE test contact's customFields back: a field can be sent but not mapped (e.g.
  `loc` arrives, 5 of 6 Google Ads fields land, the 6th is silently missing). Check every field, not just
  the tag. `webhook_check.py verify` lists them.
- GHL webhook mapping only offers fields it has SEEN: send a sample POST containing every field before
  anyone maps (`webhook_check.py payload` prints it; `send --yes` posts it with your test email).
- The GHL form redirect for the client's main-site form is a separate setting (desktop and mobile can
  differ).
- A retired page (e.g. an A/B version dropped) gets a 301 to its sibling, never left live with a dead
  form.
- Former staff profile pages: remove and 301 to /team/, and tell the media buyer to drop their photos
  from ads.
- Never write a literal `{{` in JS pasted into a GHL custom-code block: GHL may parse it as a merge
  field. Use `'\x7b\x7b'`.
- Put all `<style>` before the markup in a GHL paste block; styles after the markup cause a visible
  layout shift on first paint.
