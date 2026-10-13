---
name: ghl-survey-qc
description: Pre-launch QC for any GoHighLevel (GHL) page with an embedded survey or form. Audits the survey's live settings without an API key or a test submission, measures whether the first question and its Next button clear the fold on real phone sizes, and checks the whole funnel (page, booking page, calendar, confirmation page) says the same thing. Use before any GHL funnel goes to a client, a referral partner or paid traffic, when someone says the CTA is below the fold, the Next button looks wrong on mobile, the form looks off-brand, a lead came in and nobody was told, or before handing GHL styling work to a VA or builder. Triggers on "check the funnel", "QC the survey", "QC the form", "below the fold", "the form looks wrong on mobile", "survey styling", "is the page ready to send".
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./ghl-survey-qc-output/`.

# GHL survey and funnel QC

Sibling of `ghl-landing-page` (builds the HTML) and `ghl-funnel-backend` (wires the workflows). This one
checks the GHL side: the survey's own settings, the fold on a phone, and whether the funnel tells one
story. Two scripts answer in about ninety seconds what otherwise takes an hour of clicking.

## Run these two first, always

```bash
# 1. every setting in the survey, plus the traps below, from the PUBLIC widget page.
#    No API key, no login, no submission.
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ghl-survey-qc/scripts/audit_survey.py <surveyId|widget-url> \
  [--kind survey|form] [--host https://links.yourdomain.com] [--json ./ghl-survey-qc-output/survey.json]

# 2. is the first question AND its Next button on the first screen, at four real phone sizes
set -a; source ~/.claude/skills/.env; set +a; node ~/.claude/skills/ghl-survey-qc/scripts/fold.mjs <page-url> [<page-url>...] [--shots ./ghl-survey-qc-output/shots]
```

`audit_survey.py` exits 1 on a BLOCKER. `fold.mjs` exits 1 if any size fails. Both are read-only and safe
to run against live pages. Write outputs (JSON, screenshots) under `./ghl-survey-qc-output/`.

- The survey id is in the builder URL, or in the embed code (`/widget/survey/<id>`). Forms use
  `--kind form` (`/widget/form/<id>`).
- White-label accounts serve widgets from their own link domain. Pass `--host` (or set
  `GHL_WIDGET_HOST`), or pass the full widget URL. For `fold.mjs`, set
  `FOLD_IFRAME_HOSTS=yourlinkdomain.com` so it recognises the survey iframe.

## Never test a survey by filling it in

`enablePartialContactCreation` is on by default. Reaching question 2 creates a real contact in the CRM,
and may fire notifications to the client. Everything in this skill is read-only for that reason. If a
real submission is genuinely needed, get the account owner's yes for that specific test first, and use a
fresh `+alias` email and a reserved test phone number.

## The thing nobody expects: desktop and mobile are different settings

In the survey builder, the device toggle at the top left (monitor / phone) and the small device dropdowns
beside individual panels switch you between **two separately stored sets of values**. A colour set in
desktop view does not reach mobile. This is why a survey can look perfect on a laptop and be stock GHL
blue on a phone.

Run `audit_survey.py` and it prints the exact split for that survey. Typically:

| Set separately per device | Shared, one value drives both |
|---|---|
| Footer: type, height, background, fonts, button type, button text, every button colour, progress bar colours | Survey border width, colour, corner radius, shadow (Advanced > Survey) |
| Card margin and padding | Primary colour, input background, input border, input text colour |
| Label colour, placeholder colour, short-label colour and font | Label font family, size, weight, label alignment |
| Header image, background image | Input style (Box / Line), form width, field spacing |
| The generated field CSS blob | **Custom CSS (Advanced > Custom CSS)** |

Consequences worth saying out loud to whoever is doing the work:

- **Brand changes must be done twice.** Do desktop, screenshot the panel, flip the toggle, re-enter the
  same values.
- **Some "mobile" edits silently change desktop.** Border, radius, shadow and the primary colour are
  shared. Changing them while in mobile view moves desktop too.
- **Custom CSS is a single box for both views.** There is no `mobileCustomStyle`. For mobile-only rules,
  write the media query yourself: `@media (max-width: 600px) { ... }`. Prefer the style panels, because
  GHL regenerates its own CSS blob from them.

## Traps the auditor checks for

1. **The resume dialog's Continue button is invisible.** When save-and-exit confirmation is on, a
   returning visitor gets "Submission in progress. Would you like to continue?". GHL styles that Continue
   button as `background: footerStyle.backgroundFill` and `color: footerStyle.buttonStyle.fontColor`.
   Both default to white, so it is white on white and the only visible option is Start over. Fix: set the
   footer button font colour to a dark brand colour. (Start over reads `buttonStyle.backgroundFill`, a
   key that does not exist, so it falls back to browser grey. That one is GHL's bug, leave it.)
2. **Mobile footer left on the default blue** while desktop is branded.
3. **The survey drawing its own border and shadow** inside a page that already frames it, giving two
   nested frames.
4. **Nobody notified.** Email notifications, auto responder and conversations feed all default off.
   Check there is a **published** workflow, not a draft one.
5. **Email or phone asked last.** Anyone who drops before that question is unreachable. Get email into
   the first two.
6. **US placeholders** (`+1 (555) 000-0000`) on a UK, IE or AU form.
7. **Field focus colour still GHL red** `#ED2929`.

## Fold rules

- Measure the **visible viewport**, not the device height. An iPhone 14 is 390x844, but with Safari's
  bars showing the page gets about 664. `fold.mjs` uses 390x664, 375x548, 360x540 and 430x700.
- The target is the **Next button**, not the first input. A question you cannot advance past is not
  above the fold.
- Order CSS media queries widest-first. A `max-width: 380px` block placed **above** a `max-width: 600px`
  block is overridden and does nothing. This ships by mistake more often than you would think.
- The embed script sizes the iframe late. Wait about 9 seconds before measuring (the script does), and
  disable the cache or you measure yesterday's HTML.
- On phones the survey's Next control is often an arrow in the bottom bar of the iframe, not a "Next"
  text button.

## Check the whole funnel says one thing

Pull the landing page, the booking page, the calendar and the confirmation page, and check one noun runs
through all four. A common failure: the page promises a "plan", the booking page says "Apply to work
with us", and the confirmation page calls it a "report".

Also check:
- The stated call length matches the calendar's `slotDuration`.
- The calendar's `eventTitle` is not the bare `{{contact.name}}`, or the invite in their diary is titled
  with their own name and nothing else.
- Booking availability covers hours the prospect can actually talk. Clinic owners and clinicians are
  on the floor in clinic hours and often work Saturdays; hospital and enterprise buyers live in
  back-to-back meetings.
- The final submit button text. A cloned survey keeps the source's label (e.g. "Get My Plan"); an
  application funnel should say what it is ("Apply now").

```bash
# calendar config, read-only
set -a; source ~/.claude/skills/.env; set +a; curl -s -H "Authorization: Bearer $GHL_API_KEY" -H "Version: 2021-04-15" -A "Mozilla/5.0" \
  "https://services.leadconnectorhq.com/calendars/<calendarId>" | python3 -m json.tool
```

## Before you tell anyone a page is fixed

Fetch the **live URL** and check the fix is actually in it. A handover saying "fixed" can be
true about a file and false about the site; a fix can sit unpasted in a file for days while the live page
is still wrong. One `curl` at the start of the session finds that in a minute.

Also: `/page` and `/page-2` can be two genuinely separate GHL pages carrying identical code, or
one page on two slugs. Compare the element ids (`row-*`, `col-*`, `custom-code-*`) in the page source.
Different ids means two pages and two pastes.

## Hard rule: every design check is done twice, desktop AND mobile

A survey restyled on desktop only keeps the cloned source's colours and button text on mobile. Every
audit, QC report and handoff must:
1. Render the survey widget AND the page at a phone width (390) and a desktop width (1280), and LOOK at
   both screenshots.
2. Compare colours, button text, button style and footer per view. A difference is a FAIL, even if one
   view looks fine.
3. In any brief for the builder, add the line: "Switch the builder to the phone icon and check before you
   save. Screenshot both views."

## The handoff checklist (give this to whoever builds it)

Put it in the task, not just in someone's head.

1. **Open it on a real phone.** The builder preview is not the live page. The first question and its
   Next button both on the first screen.
2. **Check the survey styling in BOTH device views.** They are separate saved settings. Doing one is
   doing half.
3. **Click every link and every button.** A message that reads "click the link below: link", or a
   variable that resolves to blank, is an incomplete job, not a small miss.
4. **Never leave a placeholder**: `[link]`, `[BUSINESS NAME]`, `[USE_CASE_FROM_CAMPAIGN_DESCRIPTION]`, or
   an empty custom value.
5. **If it is an A/B test, open both variations side by side.** Control and variation can be
   byte-identical for days, so the test tests nothing.
6. **Anything that sends** (SMS, WhatsApp, email): send it to yourself and read what actually arrives.
7. **Workflows:** name every action for what it does ("Tag referral-lead", not "Send SMS 1"), and never
   leave one in draft silently.
8. **Screenshot each item into the task before marking it complete.**

### Workflow checks the auditor cannot do

Only the workflow list endpoint exists, so workflow contents have to be read in the UI. Every public v2
shape 404s: `/workflows/{id}`, `/workflows/{id}?locationId=`, `/workflows/{id}/versions`,
`/workflows/{id}/actions`, `/automations/workflows/{id}`, `/locations/{id}/workflows/{id}`. The list
endpoint `/workflows/?locationId=` returns 200 and is all you get (id, name, status, updatedAt).
Snapshots list on an **agency** key but `/snapshots/{id}` is 401 on scope, and a snapshot is an import
payload rather than readable workflow JSON anyway.

**The one route that exists:** `GET https://backend.leadconnectorhq.com/workflow/{id}` returns **401**,
not 404. That is the endpoint the GHL UI itself calls, and it only accepts a logged-in browser session token,
which carries **full rights to the whole account** (not a scoped PIT). No script in this skill uses it,
and you should not either: prefer the API route and the UI. Never ask for a session token, never store
one in an env file, and if one was ever pasted anywhere, log out of that GHL session to kill it.

Otherwise, workflow contents come from a screenshot or the person in the UI. Checks worth asking for:

- **Status.** `GET /workflows/?locationId=` returns `status`. A draft workflow means nothing is tagged
  and nobody is notified.
- **Channel.** SMS where WhatsApp was intended, or the reverse. WhatsApp to a contact who has never
  messaged you needs a **Meta-approved template**; the 24-hour free-form window only opens after an
  inbound message.
- **Links.** Pull the location's custom values (`GET /locations/{id}/customValues`) and check the one the
  action references actually **has a value**. Link custom values are often empty strings in snapshot
  accounts, and a blank variable in a WhatsApp send fails the entire message (Meta error 132000).
  Inline copy typed into the action also beats the custom value, so read the action, not the custom
  value.

## Who does what

The survey settings, the page paste and the funnel copy are usually the VA's or builder's work. This
skill exists so the findings arrive as a numbered list they can action, with screenshots into the task.
The account lead owns the decision and anything client-facing going out.
