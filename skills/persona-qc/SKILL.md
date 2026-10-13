---
name: persona-qc
description: Run a parallel persona QC wave on any client-facing or customer-facing artefact (landing page, deck, email sequence, SMS set, ad scripts, sales one-pager, Google Doc) before it goes anywhere. N lenses run in parallel (the owner who wrote the brief, the client with their own tools open, the recipient, the person who must do the work, compliance, does-it-physically-work), each returning a drift log and a FIX BEFORE SEND list; then one triage table (implement / already fixed / team / client / owner decision / rejected with reason); then ONE apply agent that patches by exact string replacement with reported counts; then a close-out re-run. Use when the user says "QC this", "persona QC", "read it as the client", "devil's advocate", "drift log", "triage the QC", "FIX BEFORE SEND", "ten-year-old test", or before any send.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./persona-qc-output/`.

# Persona QC wave

## Goal
Find, before the client or customer does, every sentence they could falsify, every number they could check and lose trust on, every ask that costs them more than the page admits, and every compliance trap. Then fix it once, in one place, and prove the fix landed.

## The bar
- **Each lens has ONE job and its own frame.** The client lens is told to open their own tools (Ads Manager, the CRM, the booking system, their P&L, their analytics) and redo the arithmetic. This catches wrong SMS lengths, wrong percentages and wrong trends that a plain fact-check passes.
- **Drift log, not a score.** Quote the exact sentence where the reader stopped taking it in and what happened in their head. It locates every failure precisely; a score locates nothing.
- **FIX BEFORE SEND is at most ten items**, each with the exact current text, the replacement text, and the file. Everything else goes under "would be better".
- **Outcome first, before any lens runs.** Write the artefact's outcome line and run the `outcome-first` cut test yourself (if that skill is installed). Lenses then hunt what's wrong with what's left, not sentences that should have been cut. A lens that finds a sentence failing the outcome line lists it as a delete, not a rewrite.
- **The ten-year-old bar:** satisfies the brief, plenty of contrast, examples for every group, so simple a ten-year-old could follow it, no more words than needed. Measure reading level on PROSE ONLY with `~/.claude/skills/persona-qc/scripts/fk_prose.py` (tables and timestamps hide a grade-11 page inside a grade-6 average).
- **One apply agent.** Never parallel editors on one file. It works from FACTS.md, the triage table and a patch list; every replacement reports its count; `.bak` beside every file; no `assert` chains after a write.
- **Triage before touching anything.** Money-out or fault-admission items (credits, refunds, "that's on us") and anything that changes an offer the client set are owner decisions, never applied on a blanket "implement the QC".
- Rejected rows carry the rule or the brief line that rejects them. "Already fixed" rows carry where.

## Inputs
| Input | Notes |
|---|---|
| artefact URLs or paths | a deployed preview beats local: lenses read what the client will read |
| FACTS.md path | the single number source; lenses check the artefact against it, never recompute from memory |
| the brief (the owner's words, verbatim) | for the owner lens's completeness table |
| persona facts per lens | name, role, what they said verbatim and when, what tools they have open, what they are short of (time, money, patience) |
| the rules block | tone rules, banned phrases, market compliance, what is never on a client page |
| output dir | `<workdir>/qc/` (default `./persona-qc-output/qc/` under the current directory) |

If there is no FACTS.md yet, create one first: every number and claim the artefact makes, with its source (file, dashboard, call timestamp). Lenses are useless without it.

## Steps
Run every script from the working folder (the one that holds `qc/`, `work/` and FACTS.md; default `./persona-qc-output/`), calling it by its absolute path `~/.claude/skills/persona-qc/scripts/...`, so config, patch lists and outputs live in your project, never inside the skill folder. Each Bash call is a fresh shell, so the `set -a; source ~/.claude/skills/.env; set +a;` prefix goes in the same call as the script.

1. **Freeze the artefact.** No edits while lenses run (a lens on a hot-edited file critiques stale content). Deploy the preview or copy the tree to `qc/snapshot/`.
2. **Launch the lenses in parallel** (one Agent each, in the background, strongest model available), each with the matching prompt from `prompts/` with the `{{PLACEHOLDERS}}` filled in (`{{RULES_BLOCK}}` = your house rules for this artefact, e.g. tone, banned phrases, what must never be linked or pre-selected; `{{SKILL_DIR}}` = `~/.claude/skills/persona-qc`): `lens-owner.md`, `lens-client.md`, `lens-recipient.md`, `lens-worker.md`, `lens-compliance.md`, `lens-does-it-work.md`. Each writes `qc/QC-<lens>.md` in the shape of `templates/QC-output.md`. Skip a lens when that person doesn't exist (an internal SOP has no recipient); add one only when a distinct person exists (the co-director who gets it forwarded, the procurement lead, the delegate who must consent).
3. **Mechanical checks alongside:** `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/persona-qc/scripts/fk_prose.py <html>` (grade <= 7 target), a banned-phrase grep over the deployed HTML, contradictions vs FACTS.md (every "X of N" on the page must match), render at 1440x789 and 390x844.
4. **Triage** (one agent or you) into `templates/TRIAGE.md`: one row per FIX BEFORE SEND and drift item from every lens; verdicts from the allowed set only. `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/persona-qc/scripts/triage_check.py qc/TRIAGE.md` refuses a row without a verdict or a rejected row without a reason and prints the counts. Anything needing the owner goes to `templates/DECISIONS.md` with a DEFAULT the apply agent applies.
5. **Apply, once.** Launch ONE agent with `prompts/apply-agent.md`: it writes `work/apply_<round>.json` (file, old, new, want) and runs `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/persona-qc/scripts/patch.py work/apply_<round>.json --round <round>` (reports counts, keeps `.bak-<round>`, aborts nothing after a write), updates FACTS.md's "Applied" block, regenerates any render or Doc that changed, and writes `qc/APPLY-REPORT.md`. If the round changed a number, every page carrying it is in the patch list.
6. **Team rows (optional):** `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/persona-qc/scripts/triage_check.py qc/TRIAGE.md --rows team --csv qc/team-tasks.csv` exports them; import the CSV into your task tool (ClickUp, Asana, Linear, Jira all take CSV), or paste the rows into a message to the team. If you assign by API, assign by numeric member id and read the task back to confirm: many task APIs drop name-based assignees silently.
7. **Re-run the close-out** (the artefact's own build/check script, or steps 3 again) and spot-check each replaced string on the live page.
8. **Second round only on the failing lens.** For high-stakes sends, run sequential rounds with a different lens each (cold phone read, then fact-check with dashboards open, then bad day + forwarded, then the decision); stop when the FIX BEFORE SEND list is empty.

## Things that went wrong (do not repeat)
- Apply agents died on API overload errors mid-edit; the one that succeeded worked because the patch list lived in a file. Always `work/apply_*.json` first, edits second.
- A triage marked "implement" on an offer change the client had set: it was an owner decision. The allowed verdicts now force that.
- A QC lens's own wording was used as the replacement text and carried a figure from an older data pull. Replacements come from FACTS.md.
- A "fix" removed a sourced line out of caution; the number was right. Rejected-by-fact stays.
- Reading level eyeballed as fine was grade 11 on prose.
- `fk_prose.py` once counted bare `<input>` (a void tag) into its skip counter and dropped every paragraph after the first form field, so form pages read as grade 7 on under 100 words. Fixed (VOID set); if a page with a form reports under ~200 prose words, suspect the parser first.
- `patch.py` re-run on a row whose `new` contains its `old` (append-style edits) applies again and duplicates the block. Make `old` unique to the pre-edit state.

## Related
`outcome-first` (the message gate before lenses run). Any page or email skill in this pack (`ghl-landing-page`, `page-cro`, `campaign-copywriting`) can hand its output here before send.
