# persona-qc: setup

## What it does
Runs several reader "lenses" in parallel (owner, client, recipient, worker, compliance, mechanical) over a page, deck or email set before it is sent.
Merges their findings into one triage table, then one apply agent fixes the agreed items by exact string replacement and proves each fix landed.

## What you need
- Claude Code with the Agent tool (subagents) available. No accounts and no API keys.
- Python 3.8+ (stdlib only, nothing to pip install).
- Optional: headless Chrome or Playwright for the does-it-work lens (`pip install playwright && playwright install chromium`).
- Optional: the `outcome-first` skill from this pack (used as the message gate before lenses run).

## Install
1. Copy this folder to `~/.claude/skills/persona-qc/`.
2. No env vars to add (`.env.example` is empty on purpose).
3. Test: `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/persona-qc/scripts/fk_prose.py --help && python3 ~/.claude/skills/persona-qc/scripts/triage_check.py --help` prints usage twice.

## First run (2 minutes)
Type: `Persona QC this landing page: ./site/index.html. The reader is a clinic owner. Facts are in ./FACTS.md.`
Claude freezes a snapshot, fills the lens prompts, runs them in parallel and writes `qc/QC-<lens>.md`, then `qc/TRIAGE.md`, `qc/DECISIONS.md` and, after the apply round, `qc/APPLY-REPORT.md`. Output lands in `./persona-qc-output/qc/` unless you name another folder. Nothing is sent anywhere.

## Common errors and fixes
- **`patch.py` prints `!! 0/1 ... (SKIPPED)`.** The `old` text no longer matches exactly (whitespace, curly quotes, an earlier edit). Copy the current text from the file into the row and re-run; the script is idempotent.
- **A block got duplicated after a re-run.** The row's `new` contained its `old` (append-style edit). Make `old` unique to the pre-edit state, restore from `<file>.bak-<round>`, re-run.
- **`fk_prose.py` reports a tiny word count on a page with forms.** Suspect the HTML parser (unclosed tags). Pass the plain text instead, or check the page validates.
- **`triage_check.py` flags "team row names nobody".** Put a capitalised name or role ("Media buyer", "Setter") in the where/why cell.
- **Lenses critique stale content.** Someone edited during the wave. Freeze the artefact (step 1) and re-run only the affected lens.

## Setup time
3 minutes.

## Cost per run
Free in API terms (runs on your Claude Code plan). A full six-lens wave uses a lot of tokens; use fewer lenses for small artefacts.
