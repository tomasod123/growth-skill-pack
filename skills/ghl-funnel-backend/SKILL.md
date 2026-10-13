---
name: ghl-funnel-backend
description: Wire up the back half of a GoHighLevel (GHL) funnel so a lead who converts actually gets messaged - survey field mapping, the nudge workflow's exit condition, the booking confirmation workflow, SMS/email/WhatsApp copy, calendar merge fields, the meeting-link source, URL architecture, redirects and QR codes. Use after the pages are built (see ghl-funnel-build) and before any funnel takes a real lead. Also use when someone says "they booked but got told to book again", "the confirmation never sent", "the contact has no email", "the WhatsApp didn't deliver", "the form isn't saving the phone number", "prospects got the wrong meeting link", or when setting up a short URL or a QR code for a funnel. Triggers on "funnel workflows", "booking confirmation", "nudge workflow", "sticky contact", "field mapping", "appointment merge fields", "funnel redirect", "short url", "qr code", "prefill link".
---

# GHL funnel backend wiring

The classic failure this skill exists for: the pages were finished and shipping before anyone noticed
that **a lead could convert, book a call, and still receive a message telling them to book a call** -
and that half the contacts arriving had no email address at all.

Pages are `ghl-funnel-build`. This is everything behind them. A funnel that looks perfect and messages
nobody is worth nothing, and nothing here throws an error.

Each Claude Bash call is a fresh shell: prefix every API call or script in the same call with `set -a; source ~/.claude/skills/.env; set +a;`. All reads use
base `https://services.leadconnectorhq.com`, headers `Authorization: Bearer $GHL_API_KEY`,
`Version: 2021-07-28` (calendar endpoints: `Version: 2021-04-15`) and a browser User-Agent
(`-A "Mozilla/5.0"`; Cloudflare blocks curl's default). Write specs, paste blocks and copy to
`./ghl-funnel-backend-output/` unless the user names a folder.

---

## Run this before you build anything

The account may not be able to deliver at all. Check first, it takes minutes:

```
ghl-account-audit        # contacts, workflow publish states, custom values, phone numbers
```

A typical freshly-installed snapshot has 0 contacts, every workflow in draft and every custom value
empty. A lead form would notify nobody. **A draft workflow is invisible, not broken - it simply never
runs.**

Then confirm the location can physically send:
- `GET /phone-system/numbers/location/{id}` - zero numbers means every SMS will come back
  `status: failed`. An account can show a batch of "sent" texts that were all failures, and a draft
  report can nearly claim they went out. Read `status` on the messages.
- WhatsApp: a **free-form** message only delivers inside a 24 hour window opened by their reply. To a
  lead who has never messaged you it fails silently. First contact must be an **approved template**.

---

## Fault 1: the nudge that fires after they have already booked

**This is the one that costs the most and is hardest to see.** A typical timeline:

| When | Event |
|---|---|
| Minute 0 | submits the survey |
| About a minute later | **books the call** |
| About 10 minutes in | WhatsApp delivered: "the next step is to book a quick call" |

The WhatsApp delivered perfectly. Delivery was never the problem. The nudge workflow simply had **no
check for whether they had already booked**.

### Changing the delay does not fix it, and the instinct is backwards

The reflex is to lengthen the wait so "more people book first". That is exactly wrong. A **shorter**
wait means **fewer** people have booked by the time it fires, so fewer get the wrong message. At 10
minutes everyone who books inside 10 minutes gets it wrong; at 5 minutes only those booking inside 5 do.

But no delay fixes it. Plenty of leads book within about a minute. **Only an exit condition fixes it.** Say so
explicitly when someone proposes a timing change, because it reads like a solution.

### The two workflows, and why you need both

**Workflow A, the nudge**
1. Trigger: survey or form submitted
2. Wait (5 minutes is better than 10, see above)
3. **If/Else: does this contact have an appointment on the funnel's calendar?**
   - Yes, end the workflow, send nothing
   - No, send the nudge

**Workflow B, they booked**
1. Trigger: appointment booked on that calendar
2. **First action: Remove from Workflow A**
3. Add the tag (`<funnel> call booked`)
4. Then the messages

They catch different people. Someone who books **during** the wait is caught by A's If/Else. Someone who
books **before** the workflow even reaches its wait is caught by B's removal. Build one and half the
cases still break.

Related trap: **Remove-From-Workflow actions target workflows BY NAME**, so an existing opt-out
workflow silently excludes anything built after it. Re-check those whenever you add a workflow.

---

## Fault 2: contacts arrive with no email, and the calendar does not prefill

Both symptoms usually have the same cause, and it is **not** a settings fault. The survey had sticky
contact ON, the questions mapped correctly to `full_name` / `email` / `phone` / `website`, and the
calendar's custom form had sticky contact ON. It is easy to spend an afternoon re-checking settings that
are right.

### The duplicate-email rule is what actually drops the email

GHL enforces **one contact per email address per location** (unless "allow duplicate contact" is on).
If the email already belongs to another contact, the new submission can save with the email **blank**
rather than erroring. It looks exactly like broken field mapping, and the calendar then has no email to
prefill.

Typical ways it bites:
- A team member's old contact from months ago already owns their email, so their new test submission
  saves phone-only (a phone that differs by one digit does not merge either).
- Day-two tests reuse the same email as day-one tests, so they save blank too.
- A contact with **neither** email nor phone comes from **partial contact creation** being on: stopping
  mid-survey still creates a contact from whatever has been typed.

**Before touching any setting:** search the location for the test email. If it exists, that is the
fault. Test with a fresh `+alias@` every single time.

### Where Sticky Contact actually lives

The help docs say it and nobody reads them: **if the calendar uses a custom form, the Sticky Contact
toggle is on the form, not the calendar.** Calendar Settings > Forms & Payments will not show it. Check
the form.

### How the native mechanism works, so you can verify it instead of rebuilding it

`form_embed.js` (loaded by every GHL widget embed) runs a postMessage protocol between the parent page
and its iframes: `set-sticky-contacts` from the survey, `fetch-sticky-contacts` from the calendar, and
the parent answers from **localStorage key `_ud`** on the page's own origin, matched by `location_id`.
First-party storage, so third-party cookie blocking does not break it. Same domain only: it will not
cross subdomains.

Verify it in 20 seconds on desktop: submit the survey, land on the booking page, DevTools > Console,
`localStorage.getItem('_ud')`. A JSON object with `first_name`, `email`, `phone` and the right
`location_id` means the store is working. If the calendar still does not prefill after that, the fault
is the calendar's form settings or a duplicate email, in that order.

### Do not write prefill code

Custom "read `_ud` and rewrite the iframe src" scripts work in isolation and are pointless: the native
mechanism already does this, and rewriting an iframe `src` makes the calendar **load twice**, which is a
real speed cost on the page where speed matters most. Do not ship them.

Also known: the survey's "redirect to URL" **strips the query string** on redirect, so
`?contact_id={{contact.id}}` never arrives. Do not build on it.

---

## Prefill from a text link, and how to make that link short

**Prefill is query parameters, nothing else.** A GHL form or survey embedded on a page fills every field
whose **field key** matches a parameter on the page URL (`first_name`, `last_name`, `full_name`,
`email`, `phone`, custom keys). `form_embed.js` makes the widget iframe ask the parent for its query
string (postMessage `fetch-query-params`), so it works on any page, GHL funnel or your own site. A 301
between funnel steps keeps the query string. A raw `+44` / `+1` phone arrives intact. Check it with a
headless browser, no submission.

So the text link is the landing URL plus merge fields, rendered per contact **when the message is sent**,
not when it is clicked:

```
https://book.example.com/consult-plan?first_name={{contact.first_name}}&email={{contact.email}}&phone={{contact.phone}}
```

**Making it short.** Two facts, both tested:
- Appending parameters to an existing trigger-link short URL (`<your link domain>/l/CODE?first_name=...`)
  **drops them** on the redirect. Never do this.
- The Trigger Links screen (GHL's newer interface; help article "Understanding Trigger Links in HiRise
  Design") has a `{}` picker in the Add Trigger Link modal that inserts contact merge fields **inside the
  destination URL**; GHL says the values "render correctly at send time". Build the trigger link with the
  full prefilled URL as its destination, then put `{{trigger_link.KEY}}` in the text. The recipient sees
  a short branded link, lands prefilled, and the click is logged on the contact (usable as a workflow
  trigger).
- Live-test it once with two internal contacts (different names, fresh +alias emails) before any wave:
  each must land on their own details. Fallback is the raw long URL, which is proven. Known GHL bug: a
  literal `&` inside a merged value truncates the query string; irrelevant for name, email and phone.

**Sticky contact is the second hop only.** After a submission the parent page stores the contact in
localStorage `_ud` (same domain) and the calendar reads it. It never fills the first page a texted
person opens. The survey redirect strips query strings, so `?contact_id=` on the redirect does nothing
(Fault 2).

## Fault 3: the calendar's name is not the calendar's event title

A calendar can be **named** "Calendar A" while the event title landing in every invitee's diary is
**"Event title B"**. Copy written from the calendar name will not match the invite sitting in their
calendar.

Read both before writing a single message:

```bash
set -a; source ~/.claude/skills/.env; set +a; curl -s -A "Mozilla/5.0" -H "Authorization: Bearer $GHL_API_KEY" -H "Version: 2021-04-15" \
  "https://services.leadconnectorhq.com/calendars/<calendarId>"      # name, widgetSlug, eventTitle, slotDuration
set -a; source ~/.claude/skills/.env; set +a; curl -s -A "Mozilla/5.0" -H "Authorization: Bearer $GHL_API_KEY" -H "Version: 2021-07-28" \
  "https://services.leadconnectorhq.com/locations/$GHL_LOCATION_ID"   # timezone, which merge fields render in
```

### Appointment merge fields

`{{appointment.start_time}}` is the dependable one. Others (`{{appointment.date}}`,
`{{appointment.meeting_location}}`) exist in some configurations and not others.

**Never type a merge field from memory.** Pick it from the workflow's own variable picker, send one
test, and read what it actually printed. A blank mapped variable **fails the whole WhatsApp send** (Meta
error 132000) with no partial message.

---

## Fault 4: the call link lives in more than one place

Symptom: "prospects get the wrong meeting link", "the link in the email is not the one in the invite",
the host emailing "I'm currently on this link" before calls. Nothing is broken; the link is set in
several places and each place sends its own.

A common mix: the calendar's Google Meet integration (a unique link per booking, in the invite), a
custom value "Meeting Link" holding a Zoom room (in every automated email), and hand-sent links on the
day (more rooms). Prove it from 60 days of bookings, do not guess.

### Audit it in three reads, all read-only
1. `GET /calendars/?locationId=` (Version 2021-04-15): for every calendar,
   `teamMembers[].locationConfigurations[]` gives `kind` (`google_conference`, `zoom`, `custom`, ...) and
   `location`. Empty `location` with `kind: custom` means **no link at all**, so
   `{{appointment.meeting_location}}` renders blank.
2. `GET /locations/{id}/customValues`: grep values for `meet.google.com` or `zoom.us/j/`. Any hit is a
   second source.
3. `GET /calendars/events?locationId=&calendarId=&startTime=&endTime=` for 60 days, then each booked
   contact's conversation messages: which links actually went out, and do they match the event's
   `address`. Email bodies come from `/conversations/messages/email/{id}`. A search of the host's sent
   mail for `"zoom.us/j/"` catches the hand-sent ones.

### The fix is one source, on the calendar
Set the link in **Calendar > Meeting Location** and nowhere else; every email and SMS reads
`{{appointment.meeting_location}}`; delete any custom value that holds a link. A permanent Google Meet
room (meet.google.com > "Create a meeting for later") works as a Custom location exactly like a static
Zoom room and is less friction for prospects. Outside guests knock, so the host must be present. Prove
it with one fresh-email booking: invite, email and SMS must show the same link.

---

## Message copy that works for a booking confirmation

Three messages, all on Workflow B. Replace the `<...>` parts.

**SMS, immediately.** Names the sender in the first line, so no sign-off at the end.
> Hi {{contact.first_name}}, it's <Your Name> from <Company>. Great to have you booked in. Your <EVENT TITLE> is {{appointment.start_time}}. I'm sending everything over by email now, so keep an eye on your inbox.

**Email, immediately.** Confirms, sets up what happens before the call, carries the link.
> Subject: You're booked in, {{contact.first_name}}
>
> Great to have you booked in. Your <EVENT TITLE> is {{appointment.start_time}}.
> Here's the link for the call: {{appointment.meeting_location}}
> Between now and then we'll <do the prep work: review your account / pull your numbers / look at your current setup>, so the <length> minutes is us walking you through what we've found rather than me asking you the basics.
> <One line on what they get from the call itself, in your own words.>
> If the time stops working for you, just hit reply and we'll sort another one.

**WhatsApp (or SMS), about 5 minutes later.** Its job is a reply, not a confirmation.
> hi {{contact.first_name}}, <Your Name> here again. you're booked in for {{appointment.start_time}}. before the call, what's the one <part of the business / problem> you'd most like to cover first?

Rules that make these work:
- **Do not repeat the opener across two messages.** If the nudge opens "it's <Name> from <Company>", the
  WhatsApp opens "<Name> here again". Two identical openers in a row reads like a bot.
- **One question only** in the WhatsApp. A reply opens the 24 hour window and everything after it can be
  free text. Two questions roughly halves the reply rate and gets you a partial answer.
- Lower case and chatty in WhatsApp, properly punctuated in email. It should read like the founder or
  rep typing on a phone.
- Contractions at a natural rate. A zero-contraction draft reads machine-written even when every other
  rule passes.
- Never the "it's not X, it's Y" antithesis.
- Healthcare: no clinical claims or outcome promises in automated messages, and nothing in the text
  that reveals the condition to someone glancing at the recipient's lock screen.

---

## URL architecture, redirects and QR codes

### Prefer renaming the funnel step over adding a redirect

To put a funnel on a short path, the instinct is a redirect. **Renaming the step's own path is better**,
when nothing already published points at the long one:

- Zero redirect hops, so the page opens faster on mobile data
- **GHL only offers 301 redirects, never 302.** A 301 is cached hard by the browser, so a printed QR or
  a shared short link is locked to that target for anyone who has followed it once
- A real funnel step has no such problem. You can change what the step **contains** forever, which is
  strictly more flexible than repointing a redirect

So: rename the step to the short path, then add a 301 from the **old** path to the new one to catch
anything already shared. The 301's permanence stops mattering because it points at an address that is
never moving.

Before renaming, check what already points at the long path: WhatsApp templates already approved by
Meta, the survey's `formAction` redirect, custom values, QR codes already printed, and anything a
referral partner has already sent out. A template's **text** cannot change without Meta re-review,
though its **variable mapping** can.

### Split tests survive the rename

The split test lives at the funnel step, so renaming the step's path renames it for every variant.
Verify by hitting the short path four or five times with a cache-busting query and confirming you land
on more than one variant.

### QR codes

Choose the **Website / URL** type, not the Funnel type. The Funnel type resolves the URL from dropdowns
and gives you nowhere to append **UTM parameters**, so every scan becomes indistinguishable from a link
click in reporting. A query string **survives a GHL 301 intact**, so UTMs work even through a redirect:

```
?utm_source=qr&utm_medium=print&utm_campaign=<campaign>
```

Colour, checked numerically every time:

| Combination | Ratio | Verdict |
|---|---|---|
| Black on white | 21:1 | always safe |
| Dark brand colour on cream | ~12:1 | on brand and safe |
| Light brand colour on dark | ~6:1 | **inverted, many phone cameras refuse it** |

**Decode the finished PNG before it goes anywhere.** OpenCV's `cv2.QRCodeDetector` **fails on styled
codes** (rounded finders and rounded modules defeat it) and that failure is not evidence of a problem.
Use `zxing-cpp` (`pip install zxing-cpp`), which reads them cleanly, and confirm the same string across
three renders (original, thresholded, downscaled).

```python
import zxingcpp
from PIL import Image
print([r.text for r in zxingcpp.read_barcodes(Image.open("qr.png"))])
```

**Do not open the decoded URL** if it is a tracked short link (`<your link domain>/qr/...`): fetching it
registers a scan against the QR's own analytics and pollutes the count. Verify the destination by
scanning it once on a phone, which is a scan you would expect anyway.

**Grid size caps the payload**, which is how you prove what a code can and cannot contain without
decoding it. Version 4 (33x33) holds at most 78 bytes at EC level L, 62 at M. A 106 character URL with
UTMs will not fit, so a 33x33 code is carrying a short or dynamic link, never a tagged one.

Contrast alone is not the test. **Module polarity is.** Dark modules on a light background, always.
Then check: centre logo no more than about a quarter of the width, error correction raised if there is a
logo at all, no heavy dot rounding, no gradient that goes pale at one end, and a real white quiet zone
around the edge.

---

## Testing a funnel without wrecking your data

**A fresh email every test, no exceptions.** Reusing one trips the duplicate-email rule above and the
test reports a fault that does not exist.

**Never delete a real contact to re-test.** It loses their history and tags and does not test what you
think: a genuinely new lead has a new email and a new phone, so a cleared old contact exercises a
different path.

Test with a fresh identity in a private window:
- Phone: a reserved fictional range that can never reach a real person, e.g. UK Ofcom drama range
  `07700 900xxx`, US `555-0100` to `555-0199`, AU `0491 570 xxx`. For a test that must actually receive
  an SMS, use a team member's own phone, never a real lead's.
- Email: a `+test@` alias on a mailbox you can actually open, because you need to confirm the email
  arrived

Then read the result from the API, not the UI: does the new contact carry `email`, `phone` and
`firstName`, did the appointment land on the right calendar, and what messages exist on the conversation
with what `status`.

**Get the account owner's OK for each test submission that could notify a client or sales team.** A test
enquiry on a client's form emails the client.

Clean up after: test bookings sit in the real diary. With a read-only token they cannot be removed by
API (below), so they go on a UI task the same day.

---

## Diagnose by API, fix by hand

Use a **read-only** Private Integration token (View scopes only) for diagnosis. A write such as
`DELETE /calendars/events/{id}` then returns `401 "The token is not authorized for this scope."` and so
does every other write. That is deliberate, not a broken token.

So every change in this skill is **a paste block or a written instruction for whoever builds in the UI**,
never an API call. Diagnose by API, fix by hand.

What the API **can** answer, and the UI makes slow:
- `GET /calendars/events?locationId=&calendarId=&startTime=&endTime=` - who booked and when,
  `dateAdded` vs `startTime`
- `GET /conversations/search?locationId=&contactId=` then `GET /conversations/{id}/messages` - every
  message with `status`, which is how you prove a nudge fired after a booking
- `GET /contacts/{id}` - whether email and phone actually saved

What it **cannot**: workflow triggers and steps. `/workflows/?locationId=` returns only id, name, status
and timestamps. "What else fires at this contact" is a UI question, every time.

macOS gotcha: `pip3 install certifi` and `export SSL_CERT_FILE=$(python3 -m certifi)` before any urllib
call, or it dies on certificate verification.

---

## QC gate before any funnel takes a real lead

Run in this order. Each is under two minutes and each catches a real fault.

1. `ghl-account-audit`: workflows published, custom values filled, a phone number on the location.
2. `ghl-survey-qc` (`~/.claude/skills/ghl-survey-qc/scripts/audit_survey.py <survey id or url>`): field keys are `full_name` / `email` /
   `phone`, redirect target is the live booking path, **show in conversations feed is ON**,
   notifications ON.
3. Calendar: read `GET /calendars/{id}` for `eventTitle` and `slotDuration`; copy uses the event title,
   not the calendar name. If the calendar uses a custom form, sticky contact is checked on **that form**.
   `locationConfigurations` has a real link (Fault 4), and no custom value holds another.
4. One submission with a **fresh** email: contact has email + phone via `GET /contacts/{id}`;
   `localStorage._ud` populated on the booking page; Enter-details form prefilled.
5. Book one slot, then via the API: nudge workflow did **not** message after the booking, confirmation
   SMS/email/WhatsApp did, each with `status` delivered.
6. Cancel the test booking in GHL **and** delete it from the connected Google/Outlook calendar. They are
   separate.
7. Short URL: hit it six times with a cache-buster; confirm it lands where intended and query strings
   survive.

## Handing it to the builder

Put the copy in the **same task as the workflow spec**, never a second task. The build and the words
belong together or one ships without the other.

Every message block needs:
- The exact trigger and the exact position in the workflow
- The copy in a fenced block they can copy whole
- **What to verify and report back**, specifically: send one test, say exactly what the merge field
  printed, say whether the link field came out blank
- A **Don't** line: don't publish before the account lead says go, don't submit a template to Meta,
  don't change the calendar, don't send a test to a real client or lead

Ask for the merge-field render **as text they type out**, not a screenshot. A screenshot of a rendered
date does not tell you which field produced it.

---

## Not covered yet, add when first built

- **Meta pixel** on funnel steps, and which events fire on which step
- **Conversions API**, server side, and deduplication against the pixel
- **Heatmapping** (Hotjar / Microsoft Clarity) and where the script goes in a GHL funnel
- **GA4** and whether funnel steps report as separate pages

These are the first things to add for any funnel taking paid traffic. For custom-coded landing pages
feeding GHL with full ad attribution, see `lp-webhook-tracking`.

---

## Related skills in this pack

- `ghl-funnel-build` - the pages and their QC, run first
- `ghl-survey-qc` - decode a survey's settings and field mapping with no auth; mobile fold check
- `ghl-account-audit` - can this account deliver at all
- `lp-webhook-tracking` - custom forms, one webhook, page tags, Google Ads detail
