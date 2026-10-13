# optimize-ppc-lp setup

## What it does
Takes one landing page that receives paid traffic (Google Ads, Meta) and runs the full chain: page read, 3-4 competitor pages, CRO audit with PPC-specific checks, rewritten copy, form fixes, paste-ready sticky CTA code and a prioritised checklist.
Enforces the paid-page hard rules (form above the fold on phones, no nav, one consent line, thank-you redirect as the conversion).

## What you need
- Claude Code with the built-in WebFetch and WebSearch tools enabled (used to read the page and find competitors).
- No API keys. Optional: an Apify MCP server, only if you want deeper competitor scraping of JavaScript-heavy pages.
- Helpful inputs: the ad copy or keywords sending traffic, the target buyer, the conversion goal, and the CMS (WordPress, Webflow, GoHighLevel, Unbounce, custom).
- Optional for the fold check in hard rule 1: the ghl-funnel-build skill (its `qc_sweep.mjs` needs Node 22+ and Chrome or Chromium).

## Install
1. Copy this folder to `~/.claude/skills/optimize-ppc-lp/`.
2. Nothing to add to `~/.claude/skills/.env`.
3. Test: in Claude Code type `/optimize-ppc-lp` with no URL; it should ask you for the landing page URL and the inputs above.

## First run (2 minutes)
Type: `Optimize this PPC landing page: https://example.com/demo. Traffic is Google Ads search on "clinical documentation AI". Goal is demo requests. Built in Webflow.`
You get back: executive summary, competitor table with tactics to steal, CRO audit, rewritten copy (3 headline options, CTA replacement table, FAQ), form recommendations, sticky CTA HTML/CSS and a numbered checklist. The full plan is saved to `./optimize-ppc-lp-output/<page-slug>.md`.

## Common errors and fixes
- **Page content comes back empty or partial:** the site renders with JavaScript. Paste the copy or a screenshot, or connect an Apify MCP server for rendered scraping.
- **Competitors are irrelevant:** give it 2-3 competitor URLs or the exact keywords you bid on.
- **Sticky bar covers the submit button on phones:** add bottom padding equal to the bar height and hide the bar while the form is visible (hard rule 8).
- **Test leads alert the client:** only submit tests from your internal test domain after checking the CRM workflow filters it out; use a new phone number each time because GoHighLevel merges contacts on phone.
- **Conversion not counted in Google Ads:** the form must redirect to a thank-you page and the conversion must fire on that page load, not on the button click.

## Setup time
3 minutes.

## Cost per run
Free (WebFetch/WebSearch only). If you use an Apify MCP for scraping, a few cents per competitor page.
