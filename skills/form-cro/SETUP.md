# form-cro setup

## What it does
Audits lead capture, contact, demo request, application, quote and survey forms and rewrites them to get more completions without losing the data sales needs.
Covers field count and order, labels, errors, multi-step layout, mobile, trust near the submit button, and healthcare data handling.

## What you need
- Claude Code. No accounts, API keys or packages.
- The form as a URL, screenshot or field list, plus (ideally) the current completion rate and which fields sales actually uses.
- Optional: `.agents/product-marketing-context.md` (or `.claude/product-marketing-context.md`) in your project with product, buyer and offer details.

## Install
1. Copy this folder to `~/.claude/skills/form-cro/`.
2. Nothing to add to `~/.claude/skills/.env`.
3. Test: in Claude Code type `/form-cro`; the skill should load.

## First run (2 minutes)
Type: `Use form-cro on our demo request form: first name, last name, work email, phone, company, company size, role, how did you hear about us, message. Completion is 18%.`
You get back, in chat: which fields to cut, defer or keep, a new field order, button and label copy, error message copy, a multi-step recommendation and test ideas. Ask for a file and it saves to `form-cro-output/` under your current folder.

## Common errors and fixes
- **Recommends cutting a field sales needs:** tell it which fields route or qualify leads (for example clinic size or EHR used). It will keep those and move them to step 2 instead.
- **GoHighLevel survey looks different on phone and desktop:** GHL stores survey styling per device. Use the ghl-survey-qc skill to check both.
- **Health questions on the form:** keep answers out of redirect URLs and pixel events, and confirm the form tool and CRM are covered by a BAA if you are a US covered entity.
- **Embedded third-party form cannot be restyled:** a cross-origin iframe cannot be styled from the page. Change it in the form tool's own settings or custom CSS.

## Setup time
2 minutes.

## Cost per run
Free (no paid APIs).

Source: adapted from the open-source marketingskills collection by Corey Haines (github.com/coreyhaines31/marketingskills).
