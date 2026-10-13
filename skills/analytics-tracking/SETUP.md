# analytics-tracking: setup

**What it does:** helps Claude plan, implement and debug tracking: tracking plans, event naming, GA4 and Google Tag Manager setup, UTMs, consent, and lead-gen events that let ads, analytics and CRM be joined later.
Instruction-only: no code, no keys. It writes plans and snippets; a person publishes them.

## What you need

| Item | Where to get it |
|---|---|
| Claude Code | Already installed if you are reading this in `~/.claude/skills/`. |
| Edit access to the site or tag manager (to implement) | Google Tag Manager: tagmanager.google.com > container > Admin > User Management (Publish rights to go live). Or whoever edits the website code. |
| GA4 Editor access (to mark key events, add custom dimensions) | GA4 > Admin > Property access management. Viewer is enough to read; Editor to change settings. |
| Optional: read access for checking data | See the `analytics-access-setup` skill (GA4 service account, Search Console, Clarity, CRM). |

No environment variables or credentials are needed for this skill itself.

## Install

```bash
cp -r analytics-tracking ~/.claude/skills/
```

Optional: put a short `.agents/product-marketing-context.md` in your project (what you sell, who to, main conversions). The skill reads it first and asks fewer questions.

## First run (2 minutes)

Ask Claude:
1. "Write a tracking plan for a clinic website: enquiry form, online booking, click to call. We use GA4 and GTM."
2. Then a real one: "Audit the tracking on example.com: which events fire on the enquiry form?" (Claude will ask you to check GTM Preview and GA4 DebugView, since it cannot see your account.)

## Common errors and fixes

| You see | Fix |
|---|---|
| Events show in GTM Preview but not in GA4 | Wrong Measurement ID in the GA4 tag, or consent mode is blocking until consent. Check DebugView with consent granted. |
| Duplicate lead events | The form fires on both the success callback and the thank-you page, or two containers are installed. Keep one trigger. |
| Leads in the CRM have no UTMs | Add hidden fields for `utm_*`, `gclid`, `fbclid` and map them to contact fields. |
| GA4 key events much lower than CRM leads | Meta instant forms and phone calls never touch the website. Compare like with like. |
| Custom parameter not in reports | Register it as a custom dimension in GA4 Admin; it only fills from that day on. |

## Setup time

1 minute to install. A tracking plan takes 10 to 20 minutes with Claude; implementing it in GTM 1 to 3 hours depending on the site.

## API cost

None. All free except your time (GA4, GTM and Clarity are free tools).

## Credit

Based on the analytics-tracking skill from the open-source marketingskills collection on GitHub, with lead-gen, healthcare privacy and related-skill sections added. Check that repository's licence before redistributing.
