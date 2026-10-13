---
name: front-desk-sales-kit
description: Build a front-desk or inbound sales kit for a business. Produces a one-page, client-branded objection cheat sheet (kept by the phone) and a full booking playbook (openers, step-by-step call, follow-up texts, objection bank, drills, speed to lead). The objection bank is mined from the business's own GoHighLevel call recordings, with the points leads raise most often at the top. Works for a clinic front desk booking consultations and for an inbound SaaS or SDR team booking demos. Use when the user says "sales script for [business]", "front desk cheat sheet", "objection cheat sheet", "booking playbook", "mine our calls for objections", "SDR playbook", "inbound call script", or when a new client is onboarding and needs lead-handling scripts before ads or a reactivation campaign go live.
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./front-desk-sales-kit-output/`.

# front-desk-sales-kit

Two deliverables per business, rendered from one config file:
1. **Cheat sheet** (`<slug>-cheatsheet.html`): ONE page in the client's brand (colours, logo,
   font). Opener, keep-by-the-phone tips, speed to lead, top objections with a one-line answer
   each, and the exact offer terms.
2. **Playbook** (`<slug>-playbook.html`): the full training companion. How to use it, openers
   by lead source, the booking call step by step, common questions, follow-up texts, the full
   objection bank, drills, speed-to-lead habits.

The objection bank is **mined from real calls**, most common first, not invented. If there
are no recordings yet, start from the unranked starter checklists in
`references/objection-inventory.md` (clinic checklist A, inbound SaaS checklist B) and order
them once you have a few weeks of recorded calls.

## When to use
- A new client is onboarding and the team needs scripts before leads start flowing.
- "Create or refresh the sales script / cheat sheet / playbook for [business]".
- "Mine our call recordings for objections".
- An SDR or inbound team needs a demo-booking playbook.

## Process

### Step 0: credentials and paths
Each Bash call is a fresh shell, so every script command below loads the shared env file in the
same call. Output goes to `./front-desk-sales-kit-output/`.

### Step 1: mine real objections (skip if no recordings)
1. **Probe scopes (read-only):**
   ```bash
   set -a; source ~/.claude/skills/.env; set +a; bash ~/.claude/skills/front-desk-sales-kit/scripts/probe_scopes.sh
   ```
   Recordings need the **View Conversation Messages** scope (`conversations/message.readonly`)
   on the Private Integration; if messages return 401/403, ask the user to add it in GHL
   (Settings > Private Integrations).
2. **Pull recordings:**
   ```bash
   set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/front-desk-sales-kit/scripts/mine_calls.py --min-seconds 30 --out ./front-desk-sales-kit-output/calls
   ```
   Pulls every recorded call over 30 s across the whole location (all users), PII-safe file
   names, plus `manifest.csv`. Add `--dry-run` first on a big account. Give the Bash call a long
   timeout.
3. **Transcribe:**
   ```bash
   set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/front-desk-sales-kit/scripts/transcribe_calls.py ./front-desk-sales-kit-output/calls ./front-desk-sales-kit-output/transcripts
   ```
   Local Whisper is free and private but needs PyTorch (about 2 GB). `--engine api` is the
   light option (OpenAI API, `OPENAI_API_KEY`); it sends audio to OpenAI, so only with the
   user's OK and never for patient calls without a signed BAA.
4. **Code objections:** follow the method in `references/objection-inventory.md`. Merge
   variants, count, put the most common first, tag buckets (Clarity, Timing, Money, Trust,
   Fit). Exclude voicemails from counts. Keep all PII out of every output. Append a short
   anonymised summary to the inventory.

### Step 2: build the config
Copy `~/.claude/skills/front-desk-sales-kit/configs/example-clinic.json` to `./front-desk-sales-kit-output/<slug>.json` and replace every value
(`references/tokens-registry.md` lists every token with clinic and SaaS examples).
- **Offer name:** standardise to ONE term and use it in every text, ad and call. Leads get
  confused when the same offer goes by different names.
- **Exact offer terms** (what is included, any deposit or minimum, who qualifies, exclusions,
  expiry): read them from the client's written terms. Never guess. A misquoted term loses
  bookings.
- **Openers** use a literal `[your name]` so any team member can read them.
- **Brand tokens:** take colours, font and logo from the client's site or brand guide. Put the
  logo next to the config (e.g. `assets/logo.png`); the script copies it to the output.
- **OBJECTIONS:** your mined list, most common first (or the starter checklist). `short` is the one-liner for the
  cheat sheet; `handle` is the full answer for the playbook.
- **SaaS inbound:** set `BOOKED_CALL` to "demo", `SPECIALIST` to the role who runs it, rewrite
  `OPENERS` for demo requests, trials and content downloads, use checklist B, and swap clinic
  compliance notes for your claims and security rules.

### Step 3: render
```bash
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/front-desk-sales-kit/scripts/build_kit.py ./front-desk-sales-kit-output/<slug>.json --out ./front-desk-sales-kit-output/<slug>
```
The script warns on any unreplaced UPPERCASE `{{TOKEN}}` (GHL merge fields like
`{{contact.first_name}}` are kept on purpose) and flags em-dashes.

### Step 4: review and share
Open both files in a browser and check: the offer is identical everywhere, any deposit or
condition is in the first two lines of every opener, every close is a choice of two, and no outcome promises.
Print the cheat sheet to PDF for the desk. Optionally deploy the folder to any static host
(e.g. Netlify drop) for a review link. **Nothing goes to the client without human approval.**

## Sequencing tip (agencies)
Hand the kit over on the onboarding call and have the team train on it BEFORE ads or a
database reactivation go live. An untrained front desk burns the leads you pay for.

## What the kit bakes in
- **Clear opener**: who is calling and why, then the offer in one line with any condition
  stated, then a choice of two times.
- **Branches** for already-booked, existing client, and fresh ad lead (who may not remember the
  ad).
- **Choice-of-two closes, never yes/no.** Already-booked leads are confirmed, not re-booked.
- **Objection bank** ordered by your own call data, merged duplicates, a coaching note each.
- **Phone basics** for the keep-by-the-phone block (`references/front-desk-principles.md`):
  general call-handling habits; replace `KEEP_BY_THE_PHONE` / `KEEP_TIPS` with your team's own.
  Pressure tactics are deliberately left out.
- **Speed to lead, cited** to public research (MIT / InsideSales.com Lead Response Management
  Study; Harvard Business Review, "The Short Life of Online Sales Leads", 2011). Quote it as
  background, not a promise.

## Hard rules
- GHL access is read-only. Recordings and transcripts stay local; only de-identified patterns ship.
- No outcome promises, no prescription-medicine brand names in clinic copy, no unapproved
  clinical or security claims in SaaS copy. Follow local advertising rules (e.g. UK ASA/CAP,
  FTC, Meta health policies) and HIPAA for anything holding patient data.
- Nothing client-facing is sent or published without explicit human approval.
- No AI-authorship lines in the deliverables.
