---
name: ghl-funnel-build
description: Build and ship a complete GoHighLevel (or white-label GHL) funnel end to end - landing page, booking page, confirmation page, survey, social preview, tracking - with the QC gates that catch the silent failures. Use when building a new funnel, rebuilding or cloning one, handing funnel paste work to a VA, or before any funnel goes live to paid traffic, a client or a referral partner. Also use when someone says a page "looks wrong on mobile", the survey is cut off, the calendar sits too low, a WhatsApp/LinkedIn share shows no preview, events are not firing, or a split test is not producing a difference. Triggers on "build the funnel", "new funnel", "funnel QC", "paste blocks", "the page looks off", "opt-in page", "booking page", "confirmation page", "share preview", "og image", "split test", "funnel tracking". Umbrella over ghl-landing-page (builds the HTML) and ghl-survey-qc (audits the survey).
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./ghl-funnel-build-output/`.

# GHL funnel build and QC

Each Claude Bash call is a fresh shell, so prefix every script command in the same call with `set -a; source ~/.claude/skills/.env; set +a;` (as in the commands below).

The two scripts in this skill need no API keys. Work in one folder per funnel (default `./ghl-funnel-build-output/<funnel-name>/`), with the paste blocks as `.txt`/`.html` files in it.

## Hard rules: paid-traffic landing pages

Every paid-traffic landing page and its thank-you page is a **PPC-style page**, not a website page:
1. **Form above the fold on phones, always.** On mobile put the form card straight after the H1 (CSS `order`, e.g. `.hero .grid > div:first-child{display:contents}` then H1 = 1, form = 2, the rest after). The first input must be fully visible at 320x568, 360x640, 390x844, 430x932 and 1440x789. Measure it with `qc_sweep.mjs --fold "<selector>"` before handover; a page that fails does not ship.
2. **No site header or nav menu, no chat widget, no footer link farm** on landing or thank-you pages. Logo plus one phone number or CTA at most.
3. **No repeated text around the form:** one consent mechanism (a checkbox OR one line, never both), one disclaimer line, "(optional)" in the label or the placeholder but not both, no second CTA saying the same thing.
4. **Form copy matches what the form does** ("Send my request" / "we'll be in touch"). Never "choose a time" unless the form really books.
5. **Thank-you page pattern:** one confirmation line, then ONE big above-the-fold button straight to the booking page for the exact service they asked about (read it from a `?service=` URL parameter), short reassurance, `noindex`. The form submit must redirect there, because the thank-you page load is the ads conversion.
6. **Button text contrast passes WCAG AA** (4.5:1), computed from the real colours. White text on a deep brand colour is usually the safest choice.
7. **Test submits never alert the client.** Use an internal test email domain, and only submit after you have seen (screenshot) the CRM workflow branch that filters that domain out ("real enquiry = email does NOT contain <your test domain>"). Use a unique phone number per test: GHL merges contacts on phone.
8. **Sticky mobile CTA bar:** phones only (hidden at 768px and up), pinned to the bottom: two calm buttons, Call (`tel:`) and one that scrolls to the form, in the business's own friendly language. Pad the page bottom so it never covers the submit button, and hide it while the form is on screen (IntersectionObserver on the form/survey wrapper). Check at 320/360/390/430.

**Every check below exists because something shipped broken and nobody noticed.** None of these throw an error in a browser. The page just quietly looks wrong, or quietly converts worse.

Siblings: `ghl-landing-page` writes the HTML. `ghl-survey-qc` audits the survey's own settings. This skill is the process around both.

## The pages are only half of it

This skill ships **pages**. A funnel whose pages are perfect and whose workflows never fire is worth nothing: a lead can convert, book a call, and still be messaged telling them to book a call.

When the pages pass, go to **`ghl-funnel-backend`**: survey field mapping, the nudge workflow's exit condition, the booking confirmation workflow, message copy, calendar merge fields, URL architecture, redirects and QR codes. For form-submit webhooks and conversion wiring outside GHL forms, see `lp-webhook-tracking`.

---

## The two commands to run before anything ships

```bash
# 1. Lint every paste block. Catches most of the faults below, in a second.
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ghl-funnel-build/scripts/block_lint.py <block.txt> [<block2>...] [--ban house-style.txt]

# 2. Render every page at every real width and report what is broken.
set -a; source ~/.claude/skills/.env; set +a; node ~/.claude/skills/ghl-funnel-build/scripts/qc_sweep.mjs \
  <url> [<url>...] --user-data-dir ./qc-profile-$(date +%s) --fold "#lead-form input"
```

Both exit non-zero on failure, so they can gate a handover. `qc_sweep.mjs` needs Node 22+ and Chrome/Chromium (set `CHROME_PATH` or `CHROME_BIN` if not auto-found). If a Bash call may run past 2 minutes (many URLs x 9 widths), give it a long timeout.

---

## The eleven silent faults

Ranked by how long each one took to find.

### 1. GHL page shell smuggled into the block
**What happens:** the block is lifted from the *rendered page* instead of out of the Custom HTML box. It carries dozens of empty `<!---->` comments, a duplicate `<div id="teleports">`, and GHL's entire `window.__NUXT__` config.

**Why it matters:** that script starts `window.__NUXT__={}`, which **blanks GHL's own runtime config** and replaces it with a frozen snapshot: API base URLs, the forms service, the surveys service, the reCAPTCHA key, the build id. Pages re-pasted this way accumulate several copies. A clean GHL page has one.

**Rule:** copy blocks out of the Custom HTML box, never from view-source. `block_lint.py` fails on it. Check any live page with `grep -c 'window.__NUXT__={}'`: anything above 1 is contamination.

### 2. CSS custom properties used but never declared
**What happens:** a block uses `var(--gold)`, `var(--fd)`, `var(--bg)` and never defines them. Measured live, the headline renders as **16px black Times**, and nobody notices because it looks like a design choice.

**Why it is invisible:** an invalid `var()` kills the **whole declaration**, so `font: 400 2rem/1.1 var(--fd)` is dropped entirely and you get the browser default.

**Rule:** every block declares its own tokens. `block_lint.py` fails on it. `qc_sweep.mjs` flags an h1 that fell back to a serif.

### 3. A variable declared only inside a media query
**What happens:** `--svpx` is set inside `@media(max-width:600px)` only. At every wider width the `calc(100% + (var(--svpx) * 2))` is invalid and silently dropped. It looks "nearly right", which is why it survives several QC passes.

**Rule:** any variable used in a calc needs a base declaration outside all media queries. `block_lint.py` fails on it.

### 4. The block does not load its own fonts
**What happens:** a rebuilt block drops the Google Fonts link the old one carried. It passes QC because the **preview wrapper injects the fonts**, masking it.

**Rule:** every block links its own fonts, and QC renders the block **raw**, in a wrapper that supplies nothing. Keep a `preview/raw/` alongside the wrapped preview and measure the raw one.

### 5. Image width attributes override CSS height
**What happens:** adding `width="368" height="90"` to the logo for layout stability makes it render **368x26 instead of 106x26**: squashed on every page, because CSS set only `height`.

**Rule:** keep the attributes (they prevent layout shift) and add `width:auto` in CSS. `block_lint.py` warns on it.

### 6. Desktop and mobile are separate stored settings
True for GHL **pages** and for **surveys**. A page can serve a beautiful desktop layout and a completely different old page on a phone. A survey can be on-brand on desktop and colourless on mobile.

**Rule:** never check one viewport. Diff the visible h1/h2 at 1440 and at 390. In the survey editor, confirm which device toggle is active before reading any value: Layout, Margin & Padding and the whole Footer section each store per-device values.

### 7. Survey footer "stick to card" reserves dead height
**What happens:** ~80 CSS px of blank white between the survey content and the band below it, on mobile only. The footer is set to stick to the card, so it reserves `Footer Height` plus padding whether or not it needs it.

**Fix:** set the survey footer to **stick to page**. Not a code change.

### 8. Cross-origin iframes cannot be styled from the page
The survey and the calendar are served from your GHL (or white-label) widget domain. **No CSS or JS in your block can reach inside them.** Anything about how the widget itself looks has to go through GHL.

Two routes, in order:
1. **Widget appearance** settings (Advanced settings > Widget appearance). The booking widget reads these internally as `--appointment_widgets-primary-color`, `-background-color`, `-border-color`, `-text-color`, and `--date-time-picker-primary`.
2. **The survey's own Advanced > Custom CSS**, which runs *inside* the iframe. This is the only way to fix survey internals.

Worked example: the mobile Next arrow renders as a bare dark glyph while desktop shows a branded "Next" pill. Same element, different per-device styling:

```css
/* Advanced > Custom CSS on the survey */
.ghl-footer .ghl-btn.ghl-footer-next{
  background:var(--your-brand, #2F5D50) !important;
  color:#fff !important;
  min-width:92px;
  border-radius:4px;
}
```

### 9. The booking widget's internal padding changes with iframe width
Measured on the real widget: at 1000px wide its own content sits with ~130px of padding each side; at 880px about 77px, and the whole thing is ~50px shorter. Below ~960px it reflows from two columns to stacked.

**Rule:** measure the widget at several widths before choosing a container width, then cap the container so the layout cannot flip (capping at 880px gave one layout at every desktop size).

Also: the widget reserves ~150px of blank above its first content on desktop. `overflow:hidden` on the wrapper plus a negative `margin-top` on the iframe crops it. Re-measure after **any** change to the widget's own toggles: switching title/description/details off can take the mobile height from ~770px to ~480px.

### 10. GHL clamps width on the row's `.inner` child
"Allow rows to take entire width" can be on and the row still clamped to 1170px. No UI toggle reaches it.

```css
.c-section:has(.your-class) > .inner,
.c-row:has(.your-class) > .inner,
.c-column:has(.your-class) > .inner,
div:has(> .your-class) > .inner{max-width:none!important;width:100%!important}
```

### 11. Save is not Publish
Saving the editor does not push anything live. OG tags can sit unpublished for an hour because of this. Every settings change ends with **Publish the funnel**, then verify against the live URL.

---

## Social preview, favicon, tracking

**Set OG in the page's SEO panel, not in code.** In current GHL the panel is **"SEO & AI search optimization"** (magnifier icon), with sections: Content, Keywords, Author, Images, Links & tags, Language, Schema markup. Title and Description live under **Content**; the share image under **Images**.

GHL writes these tags itself. A second copy pasted into a code block is **ignored**, because scrapers take the first tag they find. Setting the image also makes GHL emit `twitter:card` and `twitter:image`, so X is covered by the same step.

Verify the way a scraper sees it, not in a browser:

```bash
curl -s -A "facebookexternalhit/1.1" "<url>?cb=$(date +%s%N)" -o og.html
grep -oE '<meta property="og:(title|description|image)" content="[^"]*' og.html
# then fetch the image and check it is 1200x630 and the right file
```

**WhatsApp caches previews hard.** Add `?v=2` to force a fresh fetch. For Facebook/LinkedIn use the Sharing Debugger / Post Inspector and hit Scrape Again.

**Favicon** is a funnel-level setting, not per page: Funnel > Settings > Favicon URL. Check it on every funnel: cloned funnels keep the source funnel's icon (a client's logo can end up on another client's funnel).

### Tracking standard (one paste per funnel, no per-page work)

1. **Pixel:** Funnel > **Events** tab > Add Event > your pixel > Level **Funnel** > **On pageview** > Conversions API **Don't Send** (unless you deliberately run CAPI with event-ID deduplication). The pixel loads at runtime, so it never shows in the page HTML (`grep fbq` finds nothing): check the Events tab or the `pixelId` in the page's Nuxt payload instead. **A cloned funnel does NOT copy its Events tab**: re-add the pixel on every clone.
2. **Head tracking code** (Funnel > Settings): start from `templates/tracking-head-code.html`. It loads GA4 and fires events by page path: `confirm` -> Meta `Schedule` + GA4 `book_appointment`; `booking` -> `Lead` + `generate_lead`; everything else -> page view only. `confirm` is checked first, so `/booking-confirmation` sends Schedule. **Name booking pages `*-booking` and confirmation pages `*-confirmed` / `*-confirmation`, or the events will not fire.** It waits up to 10 s for the GHL pixel, so the event is not lost on slow loads. It can also read `email`/`phone`/`first_name` from the URL (the survey and calendar redirects pass them) and re-init the pixel with them (manual advanced matching), because the pixel cannot see inside GHL iframes. Turn that off for patient-facing healthcare pages unless legal has cleared it (HIPAA).
3. **Never paste a second GA4 snippet or a second pixel script** into the same funnel: double counting. Delete old per-page body codes when switching to the head code.
4. **Conversions API:** a past failure mode was pixel + CAPI sending the same event with no shared event ID (double counting). If you add CAPI, share event IDs, or send CRM stages (booked, qualified) back to Meta instead of CAPI page views.
5. **UTMs:** Meta ad URL parameters `utm_source=facebook&utm_medium=paid&utm_campaign={{campaign.name}}&utm_content={{ad.name}}`. Every hand-out link (bio, referral partner, DM automation, email) carries its own `utm_medium`. GHL stores UTMs on the contact at form or survey submit.
6. **Domain moves:** one **Entire Domain (/*)** redirect from old to new keeps path and query. But repoint every survey "Redirect URL", calendar `formSubmitRedirectURL` (API: `PUT /calendars/{id}`, a write call: needs the optional `calendars.write` scope, and **ask the user before any PUT/POST** with `formSubmitType: RedirectURL` + `formSubmitRedirectURL`; it reads back as `formSubmitRedirectUrl`) and workflow link at the new domain directly, so nothing runs through a redirect.
7. **Verify live**, do not trust settings screens: pull the funnel list (`/funnels/funnel/list?locationId=`) for real paths, curl each page, and run `ghl-survey-qc` for survey redirects.

**Not covered here:** Google Ads conversion tracking (see `lp-webhook-tracking` / `gads-audit`) and heat mapping (Hotjar/Clarity).

### Launch learnings

1. **Cookie consent is in the paste block, not just GHL.** Blocks embedding a survey iframe can carry `data-cookie-consent="true"`, so turning off "Respect host site cookie consent" in GHL changes nothing on the live page. With no cookie banner on the site, `true` means most visitors are never tracked. Ship `data-cookie-consent="false"` (`block_lint.py` fails on `true`) unless you have a real banner wired up. GHL's integrate dialog keeps re-showing the old snippet; that is display only.
2. **Favicon goes in Funnel > Settings > Favicon URL ONLY.** A URL pasted into Body tracking code prints as visible text at the bottom of every page. Keep favicon and tracking in funnel Settings, not page HTML, so they survive every re-paste and apply to A/B variations.
3. **One funnel = its own survey + its own calendar + its own workflows.** A cloned funnel keeps the source funnel's survey and calendar IDs inside the paste blocks, so leads land in the wrong funnel. After cloning: new survey (redirect to this funnel's `-booking` page with `first_name/email/phone` params), new calendar (redirect to this funnel's `-confirmation` page), clone the "Survey completed" (wait a few minutes > booked? stop : follow up, alert team) and "Booked" (tag, alert) workflows with the new triggers. Survey **email notifications default OFF**: turn them on. Calendars may only open ~7 days ahead: set a rolling window. If your API token has no `surveys` scope, take survey IDs from the user or from the live page HTML.
4. **Qualifier first, one question, Yes/No buttons** (not a dropdown: one tap). "No" = **Disqualify after submit** + a not-a-fit redirect with `?first_name={{contact.first_name}}`, so name and email are still captured. The not-a-fit page falls back to "Thanks." if the name is missing. Survey button and border colours are stored per device; a cloned survey keeps the source brand's colours.
5. **Mobile sticky CTA hides while the form is on screen** (IntersectionObserver on the survey wrapper), shows after scrolling past, tap scrolls back. A sticky bar over the form's Next button kills conversions. If the page also has an exit-intent pop-up, hold it while the scroll-to-form button runs: the fast scroll up can trigger "Before you go".
6. **Split tests:** only the H1 (and title/og:title) differs between A and B. GHL step > variation > 50/50 > include the bare domain so root traffic is split too. Then hit the entry path five times and confirm both variants actually serve: a split test that serves the same code on both sides measures nothing.
7. **Every page needs an SEO title + description + share image** set in the page SEO panel. Share images must be readable at thumbnail size: 4 items max, big type, the key word at the LEFT of each line. Avoid "next N spots" scarcity wording on share cards.
8. **Run a read-only stress test before traffic** (no submissions): every page at 360/390/430/1280 with and without `?first_name=`, embedded survey/calendar IDs vs the intended funnel, survey audit, tracking firing once each, favicon, og tags, every link. It routinely catches launch blockers.
9. **Pull a calendar's after-booking redirect without an API key:** open its public widget page (`<your widget domain>/widget/booking/<calendarId>`) and look for `form_submit_redirect_url` in the HTML.

---

## Page speed

Measure, do not guess. On one measured funnel, first load went from ~275 KB to ~187 KB and the full page from ~1,160 KB to ~460 KB.

Where it actually was:

| Cost | Before | After | Fix |
|---|---|---|---|
| Proof screenshots (9) | ~885 KB | ~254 KB | WebP at the size they display, not the size they were exported |
| Logo | ~102 KB | ~16 KB | It was 819x200 rendering at 26px tall |
| Fonts | ~144 KB | ~115 KB | Drop weights the page never renders |
| Testimonial video | YouTube player on load | 0 until clicked | Click-to-play facade with an `i.ytimg.com` thumbnail |
| **GHL survey** | **~15 KB** | - | **not the problem** |

**The GHL survey is about 5% of the page.** If anyone argues for replacing GHL forms with custom-coded ones or Typeform on speed grounds, put that figure in front of them. Fonts and images are usually 90% of the weight. Custom forms would also cost sticky contact, native field mapping and the redirect behaviour, and you would have to rebuild conversion tracking yourself.

Other measured speed traps:
- **Several hosted-video players on one page** (Vidalytics, Wistia and similar): each paused player can buffer several MB of 1080p on load. Lazy-mount them: put the embed in a `<template>` and inject it with an IntersectionObserver when it nears the viewport.
- **Never rewrite a widget iframe's `src` after load.** Changing a GHL iframe's `src` from page script makes the widget **load twice**. If a widget needs prefill data, GHL's own sticky-contact store (`localStorage._ud`, see `ghl-funnel-backend`) usually already delivers it. The paste block should contain the iframe, the embed script and CSS, and nothing that touches the iframe after it exists.
- **Lighthouse on a shared server swings a lot** (TBT can vary 3x for the same page). Run a known control page in the same batch. Do not wrap Lighthouse in `timeout`: the killed run's Chrome keeps the profile lock and later runs fail silently. Score video pages with real Chrome (Chrome for Testing), not a Chromium build without H.264, or the player takes its error path and the numbers are wrong.
- Measure a bare paste block only inside a preview page that has a viewport meta tag; without it phones lay the page out 980px wide.

---

## Copy rules

- **Speak as "we", not "you versus us".** Lines that set the reader against you ("whether you work with us or not") prime a defensive read. Phrase the same reassurance from a shared point of view.
- **Instruct, do not promise.** "Ask us about these two on the call, and where each fits" beats "we will show you what each one is worth". It gives them a job and starts the call on their problem.
- **Never write a threshold in one currency** if the offer takes buyers in several markets: write "$X / £X per month" (every currency you sell in).
- **Reading level matters.** Confirmation pages should read at a low grade (aim for grade 3-6). Measure with a Flesch-Kincaid script over prose only: table cells and headings drag the average down and hide a grade-11 paragraph inside a grade-5 average.
- No em-dashes. No "it's not X, it's Y". Never name a prescription-only medicine on a public page (UK and many other markets ban advertising them to the public). `block_lint.py` checks the first two.

---

## One source folder per funnel, and every builder reads from it

If pages are generated by a build script, `grep -n "SRC\|open(" build_*.py` before editing, and edit the file the builder reads, not the file it writes. A builder that reads from an older folder silently reverts your edit on the next build and ships stale copy. If a builder's source points outside the current work folder, move the source in and repoint it before touching anything else.

## Video poster frames: never `hqdefault.jpg`

YouTube's `hqdefault` is 480x360 **with black letterbox bars** baked in. Inside a 16:9 slot with `object-fit:cover` it gets cropped and upscaled and reads as low quality ("spammy"). Use `maxresdefault.jpg` (1280x720, 16:9, 75-190 KB) and set the `<img>` width/height attributes to 1280x720. Check it exists first (not every video has one); fall back to `sddefault` (640x480, needs the same crop). Lazy-load it. Upgrade only the posters people see on first scroll; a grid of ten FAQ thumbs at maxres is 1 MB.

If a block's `mailto:` has become `/cdn-cgi/l/email-protection#...`, someone copied it from the rendered page. Cloudflare re-obfuscates at serve time anyway, so restore the plain `mailto:` in the source or the link dies the day the domain leaves Cloudflare.

## QC process, in order

1. **Snapshot what is live first.** Pull the existing block from every page you will touch and save it to `BEFORE-rollback/`. This is the only way back.
2. **Lint every block.** `block_lint.py`.
3. **Deploy a raw preview** (the block with no wrapper fonts, no helper CSS) to any static host, and QC that, not a dressed-up version.
4. **Sweep every page at nine or ten widths:** 1920x950, 1512x820, 1440x789, 1024x768, 768x1024, 430x932, 390x844, 375x667, 360x640, 320x568. `qc_sweep.mjs`.
5. **Check the fold properly.** For a form, the first input; for a survey, the first question **and its Next button**; for a calendar, the date grid. Measure the element bottom, not its top (`--fold`). On phones the GHL survey's Next is an arrow in the bottom bar, not a text button.
6. **Exercise the interactive parts.** Click the exit-intent trigger and confirm the real survey is inside the pop-up. Drag every slider. Click every jump link and assert where it lands.
7. **Verify the payloads.** If you hand over code on a page with copy buttons, assert byte-identity against the files on disk after every rebuild. Stale copy buttons are silent.
8. **Verify against the live URL after publishing.** Not the preview, not the editor.

### Ways QC lies to you

- **The CDN serves a stale copy.** A QC run can report the survey 19px lower than it is and the booking iframe two revisions old. Always append `?cb=<timestamp>` and use a fresh browser profile when numbers look wrong.
- **A reused CDP tab leaks device metrics.** Open a new tab per measurement and close it after (`qc_sweep.mjs` does).
- **A smooth scroll has not finished.** A jump-link test can fail with a 2 s wait and pass everywhere with 5 s. Wait generously before asserting scroll position.
- **GHL survey under headless Chrome:** invisible Turnstile can fail, so Next never advances. For step screenshots, un-hide later survey slides inside the iframe instead of clicking through, and block all non-GET requests so nothing submits.
- **Reloading a survey in one profile:** from the second load a "Submission in progress" dialog can cover the form. Clear storage inside the iframe or use a fresh profile per load.
- **Exit pop-ups that fire once per session** (sessionStorage) will not open on the second test on the same origin. Use a fresh profile or another origin (localhost vs 127.0.0.1).
- **Comparing served HTML to your file:** some hosts inject comments (Netlify adds a "hosted on Netlify" comment). Strip them before diffing.

---

## Handing paste work to a VA or junior

Enforce this order and gate it:

1. BEFORE screenshots, every page, laptop and phone.
2. **Copy each page's existing Custom HTML into a .txt and attach all of them.** No pasting starts until those files are attached.
3. Paste.
4. AFTER screenshots, same set.
5. A named checklist with yes/no per line, not "looks good".

Proof goes in comments on the task in your project tool, not in chat. If a task is superseded, **rename it** `SUPERSEDED` and point it at the new one: an open task with old code in it will get worked.

**Never leave two people editing the same funnel pages.** Put the other person's task on hold explicitly and tell them in your team channel.

---

## Show-rate gate, before you call it done

General best practice for booked-call funnels (set your own targets in your notes or config):

- **Keep the booking window short** (a few days, not weeks). Booking far ahead is a main cause of no-shows. Warmer traffic (referrals) can stretch it a little; watch the show rate.
- **Confirm every booking** with a reminder sequence on email **and** SMS. Unconfirmed bookings show far less often than confirmed ones.
- **The confirmation page pre-sells.** A short pre-call video plus a few educational videos usually lifts show rate on cold traffic. It is not a receipt.

---

## Files

- `scripts/block_lint.py`: lints a paste block for the faults above (page shell, undeclared or media-only CSS variables, missing font link, unbalanced tags, media-query order, em-dashes, AI-credit and house-style bans, `data-cookie-consent="true"`, late `<style>`, `{{` in scripts, squashed images). Exit 1 on failure. `--ban <file>` adds your own banned phrases.
- `scripts/qc_sweep.mjs`: renders N URLs at N widths, flags overflow, broken images, fallback fonts, HTTP errors and (with `--fold`) a key element below the first screen. Needs `--user-data-dir` pointing at an **empty** scratch directory.
- `templates/tracking-head-code.html`: funnel-level GA4 + Meta event code keyed on page path.
