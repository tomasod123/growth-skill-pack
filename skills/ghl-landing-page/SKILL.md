---
name: ghl-landing-page
description: Build landing pages for any business (lead forms, booking pages, post-VSL application pages, funnel step pages, thank-you and confirmation pages) that paste cleanly into a GoHighLevel Custom HTML block. Enforces GHL wrapper resets, self-contained tokens and fonts, layout-shift (CLS) and font-swap safety, form-above-the-fold on phones, "a confused buyer never buys" simplicity, funnel-stage copy rules and an open-loop audit. Use when the user says "GHL page", "GHL paste", "paste block", "booking page", "application page", "confirmation page", "thank-you page", "funnel page", "landing page for GHL", or is iterating on a ghl-paste.html file.
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./ghl-landing-page-output/`.

# GHL Landing Page

Pages that paste into a GoHighLevel funnel step as a Custom HTML block, carry their own brand tokens and fonts, do not leak styles, do not shift on load, and do not open conversion loops.

Each Claude Bash call is a fresh shell: prefix every script command in the same call with `set -a; source ~/.claude/skills/.env; set +a;` (this skill's scripts need no keys; this keeps the convention).

## When to use

- Any new step in a funnel hosted on GoHighLevel (or a white-label GHL): lead form pages, booking pages, application pages, VSL page bodies, thank-you/confirmation pages, tripwire pages.
- Iterating on an existing `ghl-paste.html`.
- Not for: full multi-page websites or prospect mockups (use `design-website`).
- **After the page is built:** run `ghl-funnel-build` (lint + render sweep at every width + fold check) and `ghl-survey-qc` if the page embeds a GHL survey (its settings are stored separately for desktop and mobile; it checks the first question and Next button clear the fold and that landing, booking, calendar and confirmation pages all say the same thing). For conversion review of the copy, `page-cro` / `form-cro`; for paid-traffic pages, `optimize-ppc-lp`.

## Hard rules: paid-traffic landing pages

Every paid-traffic landing page and its thank-you page is a **PPC-style page**, not a website page:
1. **Form above the fold on phones, always.** On mobile the form card comes straight after the H1 (the skeleton does this with `display:contents` + `order`). The first input must be fully visible at 320x568, 360x640, 390x844, 430x932 and 1440x789. Measure it (`ghl-funnel-build` `qc_sweep.mjs --fold "<selector>"`) before handover; a page that fails does not ship.
2. **No site header or nav menu, no chat widget, no footer link farm** on landing or thank-you pages. Logo plus one phone number or CTA at most.
3. **No repeated text around the form:** one consent mechanism (a checkbox OR one line, never both), one disclaimer line, "(optional)" in the label or the placeholder but not both, no second CTA saying the same thing.
4. **Form copy matches what the form does** ("Send my request" / "we'll be in touch"). Never "choose a time" unless it really books.
5. **Thank-you page pattern:** one confirmation line, then ONE big above-the-fold button straight to the booking page for the exact service they asked about (read `?service=`), short reassurance, `noindex`. The form submit redirects there; that page load is the ads conversion.
6. **Button text contrast passes WCAG AA** (4.5:1), computed from the real colours. White text on a deep brand colour is usually safest.
7. **Test submits never alert the client.** Use an internal test email domain, and only after you have seen the CRM workflow branch that filters it out. Unique phone per test: GHL merges contacts on phone.
8. **Sticky mobile CTA bar:** phones only (hidden at 768px+), pinned to the bottom: two calm buttons, Call (`tel:`) and one that scrolls to the form, in the business's own friendly language. Pad the page bottom so it never covers Submit, and hide it while the form is on screen (IntersectionObserver; in the skeleton). Check at 320/360/390/430.

## Principles

### 1. A confused buyer never buys

Default to radical simplicity. Heading + one-line sub + the form. Nothing else unless there is a specific, measurable reason to add it. Every extra element is a decision point. If you find yourself adding "reassurance" sections, value stacks, bonus cards or testimonials "to build trust" on a form page that follows a VSL or sales page, stop: the earlier step already did that work.

### 2. Funnel stage determines copy

- **Cold / offer page** (first touch, no context): offer-building rules apply (see Alex Hormozi's *$100M Offers*): value stacks, price anchors, risk reversal and guarantees are all valid, within your industry's ad rules.
- **Post-VSL application page** (they already watched the video): frame it as *applying to work with us*, not "here's the offer".
  - NO value stacks with prices
  - NO guarantees / risk reversal
  - NO pricing anchors ("typical clients invest $X")
  - NO founder headshot or second intro video (they just watched one)
  - NO defensive framing ("no pitch, no pressure", "not a pitch"). There IS a pitch, a decision is expected on the call; the less said the better.
- **Thank-you / confirmation page:** next-step clarity only. What happens next, when, and what to do meanwhile. Zero sell (a short pre-call video is fine and helps show rate).

### 3. Zero open loops on the page

Before shipping, find and close:
- **Links that exit the funnel**: header logo links, footer links, "learn more" anchors. The only action on a form page is the form (plus `#anchor` jumps and `tel:`).
- **Sidetrack CTAs**: "download the guide", "watch another video". Every alternative click is a leak.
- **Terminology mismatches**: if the fit list says "dental, aesthetic, wellness", every other list on the page uses the same set. Audit body copy for parallel structure.
- **Overlapping blocks**: if one section owns "reactivation", another cannot also claim it. Sections are mutually exclusive.
- **Contradictory framing**: "application" framing and "no pressure" defensiveness cannot coexist.

### 4. Duration-free language

Never name a call or plan length on the page ("45-minute call", "12-week plan", "90-day sprint"). Say "call" / "strategy call" and "plan" / "roadmap". It keeps you flexible and removes ambiguity about commitment size.

## House-style bans

Keep a plain text file of phrases your brand never uses (one per line, optional `phrase<TAB>reason`) and pass it to both audit scripts with `--ban`. Defaults already caught: "no pitch / no pressure / not a pitch", "genuinely", "here's the best part", AI-authorship credits ("Built with Claude"), em-dashes. Typical additions: old company names, competitor names, compliance-sensitive words for your industry (for UK clinics: prescription-only medicine names such as specific injectables).

## Brand

If you keep brand tokens in `~/.claude/brand/` (optional: a `tokens.css` with your colours, fonts, radii, and a short `brand-guidelines.md`), read them first and copy the values into the block's token list. Otherwise ask for, or pull from the client's site: primary colour, background, text colour, display and UI fonts. Never invent extra colours; compose from the tokens. Card and page backgrounds read better slightly off-white than pure `#FFFFFF`.

## Required structure

Start from `templates/ghl-paste-skeleton.html`. Non-negotiables it already follows:

1. **First line:** `<style>body,html{background:<page bg>!important}</style>`, so the page background is baked in and no GHL Page Settings CSS is needed.
2. **GHL wrapper `:has()` resets.** GHL wraps a paste in `.c-section`, `.c-wrapper`, `.c-row`, `.c-column`, `.hl_page-creator--custom-code`, and those wrappers come with default borders, padding and margins. `:has(.lp-root)` kills them only around this block. Also reset the row's `.inner` child, which GHL clamps to ~1170px even with "full width rows" on.
3. **Everything inside one top-level `.lp-root` div.** Scope every selector under it (rename the class per project if two blocks share a page).
4. **Every CSS variable declared in the block, at the top level** (not only inside a media query). An undeclared `var()` drops the whole declaration and the headline silently renders in 16px Times.
5. **The block links its own fonts.** Never rely on the GHL page or a preview wrapper to load them.
6. **All `<style>` above the markup.** GHL paints before late style blocks parse.
7. **Comments removed before paste** (they ship to the page source).

## Layout shift (CLS) and font-swap gotchas

Each of these shipped at least once and cost a measurable CLS or Lighthouse hit:

- **Late CSS:** a `<style>` block after the markup gave CLS ~0.46 on first paint. Hoist all CSS.
- **Font swap re-wraps the H1:** a fallback font with different metrics makes the H1 jump from 2 to 3 lines when the web font arrives (one measured case: CLS 0.53 from a one-frame reflow). Add a metric-matched fallback `@font-face` (`size-adjust`, `ascent-override`, `descent-override` computed from the real font's advance widths vs Arial/Liberation), then test with web fonts blocked: same line count = safe. Display serifs are often ~5% wider than their fallback; leave ~8% slack when fitting a headline to a line count, or pin phone line breaks with a `<br>` that is hidden on desktop.
- **Loading fonts via script:** if you register fonts with the `FontFace` API (to keep them out of first paint for FCP), `load()` every face first, then `document.fonts.add()` them all at once. Adding one face while others load can re-wrap a line for most of a second.
- **Lining figures in display serifs:** many display serifs (Playfair, Cormorant) default to old-style numerals, so "£0" reads "£o". Set `font-variant-numeric: lining-nums` on the element itself, after its `font:` shorthand (the shorthand resets it).
- **Embedded GHL survey/calendar boot jitter:** the iframe resizes several times while booting. Reserve its settled height with `min-height` on the WRAPPER, not on the iframe (`form_embed.js` sets the iframe to `position:absolute` while booting, so iframe min-height still shifts). For a survey, capping the iframe at `max-height:1px` until its height has held steady for ~0.4 s removes the remaining jitter; hiding it does not help.
- **Content under a booking widget in the first screen:** the GHL booking widget briefly jumps to ~700px tall while booting. Either keep content below it out of the first screen or pin the wrapper height until the widget settles.
- **Decorative pseudo-elements sized in % of a section that streams in after first paint** register as shifts. Paint them as the section's background instead.
- **Logo/image squashed:** keep `width`/`height` attributes (they prevent shift) and add `width:auto` in CSS when CSS sets only `height`.
- **Measuring:** a bare paste block has no viewport meta, so phones lay it out 980px wide. Measure CLS/Lighthouse on a preview page with `<meta name="viewport" content="width=device-width,initial-scale=1">`, or on the live GHL page.

## GHL embed quirks

- **Cookie consent:** survey/form iframes from GHL's embed dialog may carry `data-cookie-consent="true"`. With no cookie banner on the page, most visitors are never tracked, and turning the GHL setting off does not change the paste block. Ship `"false"` unless a real banner is wired up.
- **One funnel, its own embeds:** after cloning, check the survey and calendar IDs inside the block belong to THIS funnel.
- **Tracking never goes in the paste block.** Pixel in the funnel Events tab; GA4/head code and favicon in Funnel > Settings (see `ghl-funnel-build` "Tracking standard"). Page paths must contain `booking` / `confirm` for path-keyed events to fire.
- **Literal `{{` in your JS** may be parsed by GHL as a merge field. Write `'\x7b\x7b'` in JS strings.
- **GHL strips `<html>`, `<head>`, `<body>`.** Raw CSS outside a `<style>` tag renders as visible text.
- **Fixed max-width container:** if the page clamps narrower than expected, the `.inner` reset in the skeleton usually fixes it; as a fallback use full-bleed: `.lp-root{width:100vw;margin-left:calc(50% - 50vw);margin-right:calc(50% - 50vw)}`.
- **Borders still showing after the resets:** zero them in GHL's panels: Section Styles (padding 0, margin 0, width full), Row Styles (padding 0, margin 0), Column Styles (padding 0), Custom HTML element (margin 0, height auto).
- **Exit-intent pop-up + scroll-to-form button:** the fast scroll up on touch can trigger the pop-up. Hold it while the button scrolls (the skeleton sets `data-hold` on the form; have your pop-up script respect it).
- **Touch overlays with a textarea:** if a tap on an overlay should focus a textarea, call `preventDefault()` on `pointerdown`, or the compat mousedown blurs it.
- **Never rewrite an embed iframe's `src` from script** after load: the widget loads twice.

## GHL admin vs paste split

Cross-origin iframes (calendar, survey, form) cannot be styled from the paste. Configure in GHL:

- **Calendar form branding:** Calendars > [calendar] > Forms & Payment > edit the booking form > Styles: background, primary colour, input text, input background, input border; turn on "map primary colour to button colour". Use your brand tokens (8-digit hex with `FF` alpha where GHL asks).
- **Calendar widget density** (less scrolling): Calendars > [calendar] > Advanced > Custom CSS. This CSS runs inside the widget iframe:

```css
.form-builder--item, .form-group, .n-form-item { margin-bottom: 10px !important; }
input, select, textarea, .n-input, .n-base-selection {
  min-height: 38px !important; height: 38px !important;
  padding: 6px 12px !important; font-size: 13px !important;
}
label, .n-form-item-label {
  margin-bottom: 3px !important; padding-bottom: 3px !important;
  font-size: 12px !important; line-height: 1.3 !important;
}
.calendar-widget-container, .booking-form-wrapper, .widget-container { padding: 12px 16px !important; }
button, .submit-btn, .n-button { min-height: 40px !important; padding: 8px 16px !important; font-size: 14px !important; }
.time-slot, .calendar-day { padding: 6px 8px !important; font-size: 12.5px !important; }
```

  Newer GHL widgets use Naive UI classes (`.n-*`); include both generic and `.n-*` selectors.
- **Survey internals:** the survey's own Advanced > Custom CSS (per-device styling lives there too).
- The calendar iframe auto-resizes via GHL's `form_embed.js`. Do not force a smaller `height` from the parent; it fights the script. Tighten the widget's internal density instead.

## File layout and workflow

One folder per page (default `./ghl-landing-page-output/<page-name>/`, or the user's project folder):

```
<page-name>/
  ghl-paste.html     # the block to edit and paste
  preview.html       # optional: block inside a page with a viewport meta, for QC
  house-style.txt    # optional: banned phrases for --ban
```

Optional: make it a git repo (private) so every version is recoverable. Never mix several GHL pages in one folder.

Every edit:

```bash
cd <page-name>
# 1. Edit ghl-paste.html (small edits with Edit, not whole-file rewrites)
# 2. Audit
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ghl-landing-page/scripts/open_loop_audit.py ghl-paste.html --ban house-style.txt
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ghl-funnel-build/scripts/block_lint.py ghl-paste.html --ban house-style.txt
# 3. Optional commit
git add ghl-paste.html && git commit -m "vX.Y: <short summary>"
# 4. Copy to clipboard for pasting into GHL
pbcopy < ghl-paste.html        # macOS
# xclip -selection clipboard < ghl-paste.html   # Linux
# 5. Report byte count and version
wc -c < ghl-paste.html
```

Version tag `vMAJOR.MINOR` (major = structural rewrite, minor = copy/style tweak). If the page shows a version (for example a tiny footer tag), bump it in every place it appears.

## Open-loop audit (run before shipping)

`scripts/open_loop_audit.py` automates the greps. It FAILs on: exit links (use `--allow-host` for an approved domain such as a privacy policy), named call/plan durations, banned phrases, em-dashes, "choose a time" copy with no calendar embed; WARNs on two consent mechanisms; and lists every money figure so you can check by eye:

- **Money thresholds:** every "$Xk+/month" in the fit list matches the "under $Xk/month" in the disqualifier. Offers that take buyers in several markets show every currency ("$X / £X per month").
- **Niche or segment lists:** every item in one list appears in the other.
- **Duplicate content across blocks:** no two sections claim the same function.

If any check fails, fix before pasting.

## Iteration pattern (when asked to "tweak this")

1. Read the current `ghl-paste.html` (and any notes file you keep for the page, optional).
2. Make the edits with Edit, not a full rewrite.
3. Bump the version (minor for copy, major for structure).
4. Run both audit scripts.
5. Commit (optional), copy to clipboard, report bytes and version.
6. Record any decision a future session needs (for example "client rejected testimonials on this page") in the page folder's notes.

## Files

- `templates/ghl-paste-skeleton.html`: starter block (wrapper resets, `.inner` reset, tokens, metric-matched fallback font, mobile form-first order, wrapper min-height for embeds, sticky mobile CTA that hides over the form).
- `scripts/open_loop_audit.py`: open-loop and copy audit. Exit 1 on FAIL.
- Pairs with `ghl-funnel-build/scripts/block_lint.py` (structure lint) and `qc_sweep.mjs` (render + fold check).
