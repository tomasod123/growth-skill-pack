# spam-word-checker setup

## What it does
A standing rule set Claude applies to every cold email subject, opener, follow-up and CTA: banned spam-trigger words and phrases, phishing-style language, formatting bans, and closeout-line rules.
Flags each hit and rewrites it into plain, low-hype wording, with a final QA checklist before copy ships.
Source: Adapted from a publicly shared cold email starter kit; check the original's terms before redistributing.

## What you need
- Nothing beyond Claude Code. No API keys, no env vars, no MCP servers, no packages.
- Works best alongside `campaign-copywriting` from this pack, but checks any pasted copy on its own.

## Install
1. Copy the folder: `cp -r spam-word-checker ~/.claude/skills/spam-word-checker`
2. No env vars to add (the `.env.example` is empty on purpose).
3. Test: paste "Hi John, act now for a free consultation. Click here!" and ask Claude "spam word check this". It should flag `Hi` greeting, `act now`, `free consultation`, `click here` and multiple exclamation marks, then offer a rewrite.

## First run (2 minutes)
Type to Claude: **"Spam word check this cold email:"** followed by your subject and body.
You get a list of every flagged word/phrase with the rule it breaks and a clean rewrite of the email, shown in the chat (no files written).

## Common errors and fixes
- **Industry words get flagged (medical, insurance, claims, sales, marketing)** - they are on the list on purpose. Rewrite around them with concrete operational language, or tell Claude it is an approved exception for this campaign.
- **Company name contains a banned word** - shorten the displayed name (e.g. "Lakeside Insurance" -> "Lakeside") rather than dropping it.
- **Closeout line says "I'll take silence as a no"** - banned, because the sequence keeps sending. Use an action-conditional line ("a one-word reply works if you'd rather I stopped").
- **Hyphenated variants slip through** (`cash-cycle`) - still banned; the root word counts.

## Setup time
1 minute.

## Cost per run
Free.
