# campaign-copywriting setup

## What it does
Writes a cold email campaign with you in four confirmed steps: direction, subject + first line, body structure, then final copy (3 variants for email 1 plus a 4-email follow-up sequence).
Every step offers 2-3 options with a recommendation; the final copy is QA-scored (0-100) and saved as markdown plus a `variants.yaml` for upload.
Source: Adapted from a publicly shared cold email starter kit; check the original's terms before redistributing.

## What you need
- Nothing beyond Claude Code. No API keys, no env vars, no MCP servers, no packages.
- Helpful inputs: the business website URL, a campaign brief or ICP, case studies / proof points, and any past campaign results.
- Optional: the `spam-word-checker` skill from this pack (screens every line) and `cold-email-starter-kit` (upload scripts and the campaign-strategy guide).

## Install
1. Copy the folder: `cp -r campaign-copywriting ~/.claude/skills/campaign-copywriting`
2. No env vars to add (the `.env.example` is empty on purpose).
3. Test: start Claude Code and type `/campaign-copywriting` (or "what does the campaign-copywriting skill do?"). Claude should describe the 4-step flow.

## First run (2 minutes)
Type to Claude: **"Use campaign-copywriting to write a cold email campaign for https://example.com targeting [job title] at [company type]. Proof point: [result]."**
You get Step 1 (target audience, pain, value prop, proof, angle, AI variables) and a question to confirm. Confirm each step; after Step 4 the copy is written to `./campaign-copywriting-output/<campaign-slug>/copy.md` and `variants.yaml`.

## Common errors and fixes
- **Copy contains em dashes or "Quick question" / "Curious" subjects** - these are hard bans; ask Claude to re-run the QA checklist and the spam-word-checker skill.
- **Variables don't fill in the sending tool** - use `{{company_name}}` (never `{{company}}`) and make the lead CSV column names match exactly.
- **Follow-ups open with "Just following up"** - banned; each follow-up must stand alone with a new value prop (save time / make money / save money rotation).
- **Creative-ideas emails promise things the business can't deliver** - give Claude the 3-5 capabilities you actually offer (the constraint box) before Step 2.
- **Healthcare copy flagged as risky** - never reference an identifiable patient or anyone's health; use business-level signals only, and keep claims verifiable.

## Setup time
2 minutes.

## Cost per run
Free (Claude usage only).
