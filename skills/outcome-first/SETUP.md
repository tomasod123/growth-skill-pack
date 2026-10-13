# outcome-first: setup

## What it does
Makes every message written for a person (emails, Slack, one-pagers, briefs, SOPs) lead with the one action the reader must take.
It writes the outcome line first, drafts only what gets that done, cuts everything else and swaps jargon for the reader's words.

## What you need
- Claude Code. Nothing else: no accounts, no API keys, no packages.

## Install
1. Copy this folder to `~/.claude/skills/outcome-first/`.
2. No env vars to add (`.env.example` is empty on purpose).
3. Test: start Claude Code and type `/outcome-first`. Claude should load the skill and ask for, or apply it to, a draft.
4. Optional: add one line to your global `~/.claude/CLAUDE.md`: "Run outcome-first on every draft written for a person."

## First run (2 minutes)
Paste a long draft email and type: `Outcome first this. The reader is the client's practice manager.`
You get back the rewritten message (copyable, no footer inside it) plus a short footer in chat: the OUTCOME line, how many sentences were cut (words before and after), and the jargon swaps. Nothing is written to disk.

## Common errors and fixes
- **The rewrite drops answers to the reader's questions.** In a reply, every question they asked must still be answered. Say "this is a reply to their email" and paste their email too.
- **Legal or offer terms got cut.** Terms an ad or offer must carry, the scope beside a fee, and numbers the reader will check are never cut. Tell Claude which lines are mandatory.
- **Claude can't write the outcome line.** That means the purpose of the message is unclear. Answer its question (who does what, by when) before asking for a draft.
- **The footer ended up inside the message.** The footer belongs in chat or the handover only. Ask Claude to re-output the copyable text alone.

## Setup time
2 minutes.

## Cost per run
Free (no paid APIs).
