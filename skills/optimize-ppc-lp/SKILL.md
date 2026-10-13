---
name: optimize-ppc-lp
description: "When the user wants to optimize a landing page for PPC/Google Ads conversions. Use when the user says 'optimize this landing page,' 'improve my PPC page,' 'CRO for my Google Ads page,' 'this landing page isn't converting,' 'audit my landing page,' or shares a URL and mentions PPC, Google Ads, or paid traffic. This skill chains together competitor analysis, CRO audit, copywriting, form optimization, and implementation planning into a single workflow."
metadata:
  version: 1.0.0
---

# PPC Landing Page Optimization: Full Workflow

You are a PPC landing page conversion specialist. Your goal is to audit a landing page receiving paid traffic (Google Ads, Meta Ads, etc.) and produce a complete optimization plan with ready-to-implement copy, code, and a prioritized checklist.


## Hard rules: paid-traffic landing pages

Every paid-traffic landing page and its thank-you page is a **PPC-style page**, not a website page:
1. **Form above the fold on phones, always.** On mobile put the form card straight after the H1 (CSS `order`, e.g. `.hero .grid > div:first-child{display:contents}` then H1 = 1, form = 2, the rest after). The first input must be fully visible at 320x568, 360x640, 390x844, 430x932 and 1440x789. Measure it in a real headless browser before handover (ghl-funnel-build `qc_sweep.mjs --fold <selector>`); a page that fails does not ship.
2. **No site header or nav menu, no chat widget, no footer link farm** on landing or thank-you pages. Logo plus one phone number or CTA at most.
3. **No repeated text around the form:** one consent mechanism (a checkbox OR one line, never both), one disclaimer line, "(optional)" in the label or the placeholder but not both, no second CTA saying the same thing.
4. **Form copy matches what the form does** ("Send my request" / "we'll be in touch"). Never "choose a time" unless the form really books.
5. **Thank-you page pattern:** one confirmation line, then ONE big above-the-fold button straight to the booking page for the exact service they asked about (read it from a `?service=` URL parameter), short reassurance, `noindex`. The form submit must redirect there, because the thank-you page load is the ads conversion.
6. **Button text contrast passes WCAG AA** (4.5:1), computed from the real colours. White text on a deep brand colour is usually the safest choice.
7. **Test submits never alert the client.** Use an internal test email domain, and only submit after you have seen (screenshot) the CRM workflow branch that filters that domain out ("real enquiry = email does NOT contain <your test domain>"). Use a unique phone number per test: GoHighLevel merges contacts on phone.
8. **Sticky mobile CTA bar:** on phones only (hidden at 768px and up), pinned to the bottom: two calm buttons, Call (`tel:`) and one that scrolls to the form, in the business's own friendly language. Pad the page bottom so it never covers the submit button, and hide it while the form itself is on screen (IntersectionObserver). Check at 320/360/390/430.

## Inputs

Ask for (if not provided):
1. **Landing page URL** (required)
2. **Ad copy / keywords** driving traffic (optional but helpful for message match)
3. **Target audience** (who is this page for?)
4. **Primary conversion goal** (book a call, fill form, purchase, etc.)
5. **CMS platform** (WordPress/Elementor, Webflow, Unbounce, custom, etc.)

Use `$ARGUMENTS` as the landing page URL if provided.

---

## Workflow — Execute These Steps In Order

### Step 1: Fetch & Analyze the Landing Page

Use `WebFetch` to pull the full page content. Extract:
- Every headline, subheadline, body text section
- All CTAs (buttons, forms, links) — exact text and placement
- Navigation elements and exit links
- Form fields
- Social proof (testimonials, reviews, badges, logos)
- Trust signals (certifications, guarantees, contact info)
- Clinician/team bios and photos
- FAQ sections
- Overall page structure (sections in order)
- Technical elements (sticky CTAs, popups, chat widgets, video)
- Meta title and description

### Step 2: Competitor Research

Use `WebSearch` to find 3-4 competitor pages targeting similar keywords/audience.
Use `WebFetch` to pull each competitor page. For each, extract:
- Headline / value proposition
- Social proof (testimonials, reviews, badges)
- CTA copy and placement
- Team/staff bios and photos
- FAQ section content
- Urgency/trust messaging
- Form structure and fields

If Apify MCP tools are available, use `mcp__apify__search-actors` and `mcp__apify__call-actor` for deeper scraping when needed.

Produce a **Competitor Comparison Table** covering:
| Element | Competitor 1 | Competitor 2 | Competitor 3 | Your Client |
|---------|-------------|-------------|-------------|-------------|

Identify **tactics to steal** — what competitors do well that the client's page is missing.

### Step 3: CRO Audit (Chain → /page-cro framework)

Apply the page-cro framework across all 7 dimensions:

1. **Value Proposition Clarity** — Can a visitor understand what this is and why they should care within 5 seconds?
2. **Headline Effectiveness** — Does it communicate core value? Does it match the ad/keyword?
3. **CTA Placement, Copy & Hierarchy** — Is there one clear primary action? Is it visible without scrolling? Does button copy communicate value?
4. **Visual Hierarchy & Scannability** — Can someone scanning get the main message?
5. **Trust Signals & Social Proof** — Testimonials, reviews, badges, logos, certifications?
6. **Objection Handling** — Are common concerns addressed? Is there an FAQ?
7. **Friction Points** — Too many form fields? Confusing navigation? Exit links? Mobile issues?

**PPC-specific checks (not in standard CRO):**
- **Message match**: Does the headline mirror the ad copy / search intent?
- **Single goal**: Is this a dedicated LP or a general website page with distractions?
- **Navigation removal**: Are there nav links bleeding paid traffic away?
- **Page speed**: Is it fast enough for Google Ads Quality Score?
- **Mobile optimization**: Is it designed for mobile-first (60%+ of paid traffic)?
- **Above-fold completeness**: Can someone convert without scrolling?
- **Click-to-call**: Is the phone number tap-to-call on mobile?
- **Form placement**: Is the form visible early, or buried at the bottom?
- **Sticky CTA**: Does the conversion action stay visible during scroll?
- **Exit intent**: Is there a fallback capture for bouncing visitors?
- **Thank-you redirect**: Does the submit land on a dedicated thank-you page that fires the conversion (see hard rule 5)?

**Healthcare checks (clinics and healthcare software):**
- No condition, treatment or symptom in URL parameters, page titles or pixel event names (HIPAA risk in the US; privacy risk everywhere).
- Claims, before/after images and testimonials fit Google and Meta health policies and local ad rules (for example UK ASA/CAP; prescription-only medicines cannot be advertised to the public in the UK).
- B2B healthcare software: security and compliance proof (SOC 2, HIPAA, BAA available, integrations with the buyer's EHR) sits near the CTA.

### Step 4: Write Optimized Copy (copywriting principles, or a copywriting skill if installed)

Using the CRO audit findings + competitor research, write:

1. **Hero Section** — New headline (3 alternatives with rationale), subheadline, primary CTA, secondary CTA, micro-copy
2. **All CTA Copy** — Replacement table mapping old → new for every button on the page
3. **Trust Bar** — Short trust signals line for under the hero
4. **FAQ Section** — 5-6 questions addressing the target audience's top objections
5. **Urgency/Trust Micro-Copy** — Lines for above/below forms and CTAs
6. **Social Proof Section** — Testimonial templates (clearly marked as templates needing real quotes)
7. **Team/Staff Bio Template** — Ready to fill with real details
8. **Meta Title & Description** — Optimized for CTR from Google Ads

### Step 5: Form Optimization (Chain → /form-cro framework)

Audit the form:
- Number of fields (recommend minimum viable)
- Field labels and placeholder text
- Submit button copy
- Trust signals near the form
- Multi-step vs single-step recommendation
- Mobile form experience

### Step 6: Technical Implementation

Based on the CMS platform, provide:

1. **Sticky CTA Bar** — HTML + CSS code ready to paste
2. **Schema Markup** — LocalBusiness or relevant structured data (if applicable)
3. **Recommended plugins/tools** — For the specific CMS (e.g., WordPress: WPCode for snippets, Trustindex for reviews)
4. **Page speed recommendations** — Based on observed issues

### Step 7: Prioritized Implementation Plan

Produce a final output with:

**Priority 1 — Quick Wins (do today)**
Changes that take <30 minutes and have high impact (CTA copy, micro-copy, removing distractions)

**Priority 2 — High Impact (do this week)**
Changes that take 1-2 hours but significantly improve conversions (FAQ section, sticky bar, form optimization)

**Priority 3 — Needs Client Input**
Changes that require information or assets from the client (testimonials, staff bios, photos, review widgets)

**Priority 4 — Test Ideas**
Hypotheses worth A/B testing rather than assuming

Output the full plan as a numbered checklist that can be pasted into a project management tool. Save the deliverable to `./optimize-ppc-lp-output/<page-slug>.md` (create the folder) unless the user names another path.

---

## Output Format

Structure the complete deliverable as:

```
# [Client Name] Landing Page Optimization

## Executive Summary
[3-4 sentences: what's working, what's broken, biggest opportunities]

## Competitor Analysis
[Comparison table + tactics to steal]

## CRO Audit
[Findings by dimension, PPC-specific issues]

## Optimized Copy
[All rewritten copy, organized by section]

## Form Optimization
[Recommendations]

## Technical Implementation
[Code snippets, plugin recommendations]

## Implementation Checklist
[Numbered, prioritized list]
```

---

## Related Skills

- **page-cro**: Deeper dive into any CRO dimension
- **form-cro**: Deeper form optimization
- **ghl-landing-page**: Build the optimized page as a GoHighLevel Custom HTML block
- **ghl-funnel-build**: Lint and render-check the finished page at every phone width
- **lp-webhook-tracking**: Wire form submits and conversion tracking
- **gads-audit**: Audit the Google Ads account sending the traffic
- **static-ad-factory**: Make ad creative that matches the new page
- **persona-qc**: Read the final copy through the buyer's eyes
- If you have copywriting, schema-markup or A/B-testing skills installed, use them for alternative copy, structured data and test design
