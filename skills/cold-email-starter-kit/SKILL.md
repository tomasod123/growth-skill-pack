---
name: cold-email-starter-kit
description: End-to-end cold email toolkit from zero to a launched campaign. Domain purchase (Dynadot), inbox setup (Zapmail), list building (Prospeo), campaign strategy and copy, optional enrichment, and upload to Smartlead or Instantly, with TypeScript scripts and numbered reference guides. Use when setting up cold email or outbound for the first time, launching a new campaign, training a team member on cold email, or when you need the API reference, launch checklist or troubleshooting matrix for Smartlead, Instantly, Prospeo, Dynadot or Zapmail.
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./cold-email-starter-kit-output/`.

# Cold Email Starter Kit

A complete system for running cold email. Follow it top-to-bottom and you will have purchased domains, created warmed inboxes, built a lead list, written a campaign, and sent your first emails. Designed for beginners — no prior cold email experience required.

---

## What you'll build

By the end of the flow you'll have:
- 10-20 throwaway sending domains purchased on Dynadot
- 20-40 warmed sending inboxes on Zapmail
- A 2,000-person lead list from Prospeo
- A 4-step email sequence with variants and personalization
- A live campaign in Smartlead or Instantly sending daily
- Analytics and reply handling set up

Total cost month 1: roughly $330-410 with `.com` domains (less with cheaper TLDs, at a deliverability cost). Recurring: ~$126/mo plus annual domain renewals. See `references/00-getting-started.md` for breakdown.

---

## The end-to-end flow

1. **Deliverability basics** → understand why we buy domains + inboxes (read once)
2. **Strategy** → pick your offer and ICP
3. **Copywriting** → write the sequence
4. **Infrastructure** → buy domains, create inboxes
5. **List building** → pull prospects from Prospeo
6. **Enrichment (optional)** → add personalization data
7. **Launch** → upload to Smartlead or Instantly
8. **Analyze + iterate** → pull metrics back, tweak

---

## Before you start: prerequisites

**Technical:**
- Node.js 20+ (`node --version` should print v20 or higher) → install from nodejs.org
- `tsx` (`npm install -g tsx`)
- Terminal comfort (you know what `cd` and `cp` do)
- A text editor (VS Code recommended)

**Accounts (sign up before continuing):**
- Dynadot (domain registrar)
- Zapmail (inbox provider)
- Prospeo (lead source)
- Smartlead OR Instantly (sending platform — pick one)

**Budget:** ~$400 for your first campaign.

If any of the above is missing, start at `references/00-getting-started.md`. It has exact signup links and API-key retrieval instructions.

---

## One-hour quick start

If you just want to launch your first campaign in a single session, stop reading this file and open `references/14-60-minute-tutorial.md`. It's a step-by-step walkthrough that assumes zero context and gives you exact commands to run.

## Safety rules for Claude (always)

- Never buy domains, create inboxes, export paid leads, or start sending without the user confirming that exact step and its cost in this conversation. The purchase and export scripts ask for confirmation; do not bypass it by piping `y`.
- Upload campaigns as drafts / paused. The user reviews the campaign in the Smartlead or Instantly UI and starts it.
- Every script writes its CSVs to the CURRENT folder, so cd into an output folder first and load keys in the SAME Bash call (each Bash call is a fresh shell): `set -a; source ~/.claude/skills/.env; set +a; mkdir -p cold-email-starter-kit-output && cd cold-email-starter-kit-output && npx tsx ~/.claude/skills/cold-email-starter-kit/scripts/<name>.ts ...`. The references write `scripts/<name>.ts` for short; always use the full `~/.claude/skills/cold-email-starter-kit/scripts/` path.
- `smartlead-create-campaign.ts` attaches EVERY email account in the Smartlead workspace (up to 200). In an agency workspace with several clients' inboxes, detach the wrong ones in the UI before starting, or upload the sequence by hand.

---

## Reading order (for understanding)

The references/ folder is numbered in the order to read them the first time:

| # | File | What it covers |
|---|---|---|
| 00 | `00-getting-started.md` | Accounts, API keys, `.env`, verify, cost breakdown |
| 01 | `01-deliverability-fundamentals.md` | SPF/DKIM/DMARC, warmup, domain strategy, volume math |
| 02 | `02-campaign-strategy.md` | Generate 15-20 campaign ideas from your website |
| 03 | `03-campaign-copywriting.md` | Stepwise copywriting: direction → subject → body → final |
| 04 | `04-sequence-structure.md` | Timing, follow-ups, threading, A/B testing, spintax |
| 05 | `05-domain-and-inbox-setup.md` | Dynadot purchase, Zapmail inboxes, export |
| 06 | `06-list-building-prospeo.md` | Prospeo filters, state-by-state crawling, full-export |
| 07 | `07-enrichment-library.md` | Optional enrichments + pricing |
| 08 | `08-smartlead-api.md` | Smartlead API reference |
| 09 | `09-instantly-api.md` | Instantly API reference |
| 10 | `10-reply-handling.md` | Positive/negative/OOO/bounce playbook |
| 11 | `11-legal-compliance.md` | CAN-SPAM, GDPR, unsubscribe requirements |
| 12 | `12-launch-checklist.md` | Pre-flight QA |
| 13 | `13-troubleshooting.md` | Error matrix |
| 14 | `14-60-minute-tutorial.md` | Literal step-by-step first campaign |

---

## Decision tree — where am I and what do I read?

| If you're at this point... | Read this |
|---|---|
| "I don't know what cold email even is" | `01-deliverability-fundamentals.md`, then `02-campaign-strategy.md` |
| "I have a product, need campaign ideas" | `02-campaign-strategy.md` |
| "I have a campaign, need to write emails" | `03-campaign-copywriting.md` + `04-sequence-structure.md` |
| "I need inboxes but don't have them" | `05-domain-and-inbox-setup.md` |
| "I need a lead list" | `06-list-building-prospeo.md` |
| "My emails need personalization" | `07-enrichment-library.md` |
| "Ready to upload to Smartlead" | `08-smartlead-api.md` |
| "Ready to upload to Instantly" | `09-instantly-api.md` |
| "Got my first replies, now what?" | `10-reply-handling.md` |
| "Am I legal? GDPR? CAN-SPAM?" | `11-legal-compliance.md` |
| "Something's broken" | `13-troubleshooting.md` |

---

## Choose your sending platform: Smartlead vs Instantly

| Criterion | Smartlead | Instantly |
|---|---|---|
| Entry price (2026) | ~$39/mo, 2K leads | ~$37/mo, 1K leads |
| Free trial | 14 days | 14 days |
| Inboxes | Unlimited on paid plans | Unlimited on paid plans |
| API auth | Query param (`?api_key=`) | Bearer token header |
| API endpoint count | ~50 | ~150+ |
| Master inbox | Yes (strong) | Yes (Unibox, strong) |
| Built-in warmup | Free | Included |
| AI reply categorization | Yes | Yes (lead-labels) |
| Branching follow-ups | Limited | Yes (Subsequences, first-class) |
| Inbox rotation | Yes | Yes |
| Deliverability testing | External tools | Built-in (inbox-placement-tests) |
| Done-for-you inboxes | No | Yes (DFY orders) |
| Built-in lead enrichment | No | Yes (SuperSearch) |
| Smartlead-exclusive | Simpler for beginners | — |
| Instantly-exclusive | — | Subsequences + Inbox Placement + SuperSearch |

**Default recommendation for first-time users: Smartlead.** Simpler mental model, cheaper at small scale, enough power for your first 6 months. Migrate to Instantly if you outgrow Smartlead's advanced features.

You only need one. Pick now so you know which API reference to read later.

---

## Proven defaults for your first campaign

Use these unless you have a specific reason to deviate:

- **20 domains × 2 inboxes = 40 sending inboxes** — enough to warm 2 weeks then send ~1,200/day
- **30 emails/day/inbox** (post-warmup) — never exceed
- **2,000 leads per campaign** — good statistical size to learn from
- **4-step sequence** — Day 0, Day 3, Day 7, Day 11
- **2-week warmup minimum** before any real sending
- **`.com` domains** (~$10-14 each on Dynadot) — default choice. Fall back to `.co` if .com is taken. Avoid `.info`, `.xyz`, and other cheap TLDs — they hurt deliverability.
- **2 inboxes per domain max** (above that hurts reputation)
- **50-90 word emails** — extend to 125 only if AI personalization justifies it
- **Preview email to yourself first** before any real send
- **Reply within 30 seconds** when a positive reply comes in — this looks 10x more human than replying hours later

---

## Common beginner mistakes (avoid these)

1. **Sending from your main domain.** Instant risk of blacklisting your real business mail. Buy lookalike throwaway domains (e.g. `tryexample.com` to send on behalf of `example.com`).
2. **Skipping warmup.** New inboxes sending cold = instant spam folder. Minimum 2 weeks warmup.
3. **Buying one $30 domain.** Buy 10-20 `.com` / `.co` lookalike domains instead. Diversity = deliverability.
4. **Writing emails longer than 90 words.** Nobody reads long cold emails.
5. **Using em dashes (—).** Gmail spam filters flag these. Use periods or commas.
6. **Sending without SPF/DKIM/DMARC.** Zapmail sets these automatically if you connect domains through it. Verify with `dig`.
7. **Treating a 0% reply rate in week 1 as failure.** Expect 2-5% reply rate over the full sequence; wins compound over follow-ups 2-4.
8. **Buying a list from a random "lead seller."** Use Prospeo — verified, legal, clean data.
9. **Emailing EU consumers.** B2B to EU is generally fine under legitimate interest, but consumer addresses are off-limits. See `11-legal-compliance.md`.
10. **Not handling replies fast.** Replies that sit for hours go cold. Set up notifications.

---

## When something breaks

Open `references/13-troubleshooting.md`. It has an error matrix keyed by symptom → cause → fix, plus diagnostic `dig`/`curl` commands for verifying setup.

---

## Next steps after your first campaign

Once you've shipped and have ~2 weeks of data:
- Read `10-reply-handling.md` and set up unified inbox monitoring
- Run `scripts/smartlead-pull-analytics.ts` (or the Instantly equivalent) to get a CSV of daily stats
- Rewrite the worst-performing email variant
- Launch campaign #2 in parallel (different targeting, same infrastructure)
- Study what's working and compound it

---

## Scripts included

All in `~/.claude/skills/cold-email-starter-kit/scripts/`. TypeScript, run as `set -a; source ~/.claude/skills/.env; set +a; cd cold-email-starter-kit-output && npx tsx ~/.claude/skills/cold-email-starter-kit/scripts/<name>.ts` (Node 20+; `npx` fetches `tsx` on first use, or `npm install -g tsx`). No npm dependencies beyond Node built-ins. `bun <full path>.ts` also works.

| Script | Purpose | Spends money? |
|---|---|---|
| `setup-env.sh` | Prints where to get each key and which vars to add | no |
| `verify-credentials.ts` | Ping all APIs, print ✅/❌ table | no |
| `dynadot-generate-domains.ts` | Generate + availability-check domain candidates | no |
| `dynadot-bulk-purchase.ts` | Purchase a batch of domains | YES (asks first) |
| `zapmail-full-setup.ts` | NS switch → connect → inboxes → export (4-phase) | YES (Zapmail mailboxes) |
| `prospeo-full-export.ts` | Full paginated Prospeo search to CSV | YES (credits, asks first) |
| `smartlead-create-campaign.ts` | Create campaign, save sequence, attach inboxes, add leads | no (does not start it) |
| `smartlead-add-leads.ts` | Batch lead upload | no |
| `smartlead-pull-analytics.ts` | Daily stats to CSV | no |
| `instantly-create-campaign.ts` | Instantly campaign creation (only activates with `--auto-activate`) | no |
| `instantly-add-leads.ts` | Instantly batch lead upload | no |
| `instantly-pull-analytics.ts` | Instantly daily stats to CSV | no |
| `enrichments/company-phone.ts` | Blitz company phone enrichment | yes (per lookup) |
| `enrichments/ai-company-analysis.ts` | OpenRouter GPT-4o-mini company analysis | yes (small) |
| `enrichments/company-news.ts` | OpenWebNinja (RapidAPI) recent-news enrichment | yes (per lookup) |
| `enrichments/linkedin-profile.ts` | RapidAPI LinkedIn profile enrichment | yes (per lookup) |

Every script:
- Reads keys from the environment (`process.env`). If a var is missing it falls back to `~/.claude/skills/.env`, then a `.env` in the skill folder
- Is safe to re-run (idempotent where possible)
- Confirms before spending money (domain purchases, lead exports)
- Writes structured output to CSV/JSON you can inspect
- Fails loudly on errors, never silently

---

## Getting help

- Check `13-troubleshooting.md` first — it covers 90% of issues
- Re-read the platform comparison if you're on the wrong tool
- For copy: run the QA checklist in `03-campaign-copywriting.md`
- For lists: re-read filter advice in `06-list-building-prospeo.md`
- Cold email subreddits (r/coldemail, r/salesdevelopment) are friendly if you post redacted details

---

## A note on ethics

Cold email works best when it's actually useful. Skip consumer addresses, honor unsubscribes promptly, include a real address in your footer, and write something the recipient is glad they got.

That's most of what compliance comes down to in practice.

---

## What to do next

**New to cold email:** follow `references/00-getting-started.md` through `14-60-minute-tutorial.md` in order. Each document points at the next.

**Have infrastructure already:** jump to `02-campaign-strategy.md`, then write the copy with the `campaign-copywriting` skill and screen it with `spam-word-checker`.

**Campaign live for 2+ weeks and replies dropping:** run the `email-deliverability-audit` skill.

## Related skills (in this pack)

- `campaign-copywriting` - stepwise copy flow (same method as `references/03-campaign-copywriting.md`)
- `spam-word-checker` - banned words and closeout-line rules for every draft
- `email-deliverability-audit` - SPF/DKIM/DMARC, inbox health, reply-rate and placement audit
