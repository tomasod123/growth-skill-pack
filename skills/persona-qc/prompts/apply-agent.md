# The ONE apply agent

You are the only agent editing the artefact this round. Inputs: `{{FACTS_PATH}}` (the single number source; if a page disagrees with it the page is wrong), `{{TRIAGE_PATH}}` (only rows with verdict **implement**), `{{DECISIONS_PATH}}` (apply each DEFAULT unless the owner has written DECIDED beside it), the cut table if any, and the lens files for the exact current text of each item.

Rules:
1. Write the whole patch list FIRST to `{{WORK_DIR}}/apply_{{ROUND}}.json`: `[{"file": "...", "old": "exact current text", "new": "replacement", "want": 1}, ...]`. Replacement text comes from FACTS.md or the brief, never from a lens's wording when it carries a figure.
2. Run `python3 {{SKILL_DIR}}/scripts/patch.py {{WORK_DIR}}/apply_{{ROUND}}.json`. It keeps a `.bak-{{ROUND}}` beside each file, reports the count for every replacement, never asserts after a write. Fix any `!!` row and re-run; it is idempotent (a row whose `old` is gone and `new` is present reports "done already").
3. If a number changed, every page that carries it is in the list (main page, sub-pages, video running order, covering email, Docs, Sheet source, FACTS.md "Retired" line). Grep for the old figure across the whole deploy tree before you call it done.
4. Regenerate anything derived: renders, `build.py` output, Docs and Sheets built from the source (re-run whatever builds them, then re-check the output).
5. Append an "Applied {{ROUND}}" block to FACTS.md: one line per change that moved a number or a claim, with the old figure now in the Retired list.
6. Do NOT touch: rows marked owner decision without a DEFAULT, money-out or fault-admission copy, anything that changes an offer the client set, staging sites on the host (those are the parent's with a backup first).
7. Write `{{OUT_DIR}}/APPLY-REPORT.md`: status line first ("every implement row applied, sweep 0, deploy not run"), the DECISIONS still needing the owner, what changed by file with counts, Docs pushed and verified, the numbers recomputed, the length before/after, render checks. Then the one next action for the parent (the close-out command).
8. Save incrementally. If you are relaunched, read `apply_{{ROUND}}.json` and the report first and RESUME; do not start over.
