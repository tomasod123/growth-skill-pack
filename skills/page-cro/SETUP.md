# page-cro setup

## What it does
Audits any marketing page (homepage, landing, pricing, feature, blog) for conversion problems across seven areas, from value proposition to friction.
Returns quick wins, bigger changes, test ideas and 2-3 rewritten headlines and CTAs with the reasoning.

## What you need
- Claude Code. No accounts, API keys or packages.
- The page as a URL (Claude reads it with its built-in WebFetch tool), a screenshot, or pasted copy.
- Optional: a product context file at `.agents/product-marketing-context.md` (or `.claude/product-marketing-context.md`) in your project describing the product, buyer, offer and proof. The skill reads it first so it asks fewer questions.
- Optional numbers that sharpen the advice: current conversion rate, traffic source split, heatmaps or session recordings.

## Install
1. Copy this folder to `~/.claude/skills/page-cro/`.
2. Nothing to add to `~/.claude/skills/.env` (this skill uses no variables).
3. Test: start Claude Code and type `/page-cro` or ask "what skills do you have for CRO?". The skill should be listed.

## First run (2 minutes)
Type: `Run page-cro on https://example.com/pricing. Traffic is mostly Google Ads, goal is demo requests, current conversion about 2%.`
You get back, in chat: page type and goal, findings by dimension, Quick Wins, High-Impact Changes, Test Ideas and copy alternatives. Ask "save it as page-cro-output/<page>.md" if you want a file (it lands under your current folder).

## Common errors and fixes
- **WebFetch returns little text (JavaScript-heavy page):** paste the page copy or a full-page screenshot instead, or use a browser screenshot tool if you have one.
- **Generic advice:** give it the traffic source and the goal. Message match with the ad or search term is the biggest lever on paid pages, and it cannot judge that without the ad copy.
- **It audits the signup flow instead of the page:** say which page. Account signup flows are a separate problem; this skill covers the marketing page.
- **Healthcare pages:** check that no condition or treatment appears in URLs or pixel events (see the healthcare section in SKILL.md).

## Setup time
2 minutes.

## Cost per run
Free (no paid APIs; normal Claude usage only).

Source: adapted from the open-source marketingskills collection by Corey Haines (github.com/coreyhaines31/marketingskills).
