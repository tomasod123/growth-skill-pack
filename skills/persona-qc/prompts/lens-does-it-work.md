# Lens: does it physically work (mechanical, no opinions)

Open {{ARTEFACT_URLS}} in headless Chrome at 1440x789 and 390x844 (fresh tab per run, own profile dir under the work dir, kill by PID, never `pkill -f` a pattern that matches your own shell). Do not edit anything. Write `{{OUT_DIR}}/QC-mechanical.md` as a table of PASS/FAIL with evidence:

| Check | 1440x789 | 390x844 | Evidence |
|---|---|---|---|
| No horizontal overflow (`scrollWidth == innerWidth`) | | | numbers |
| Both logos visible above the fold | | | |
| Every TOC anchor resolves to a real element | | | list |
| Every external link returns 200 with a browser UA (Ads Library links are browser-only; report, do not fail) | | | count + non-200 list |
| Status dropdowns persist across reload (localStorage key) | | | key + value read back |
| Asks: tick one, it greys and drops; reload, still ticked; untick, it returns | | | |
| Questions form: submit a throwaway row → lands in its destination (CRM, webhook, database) with the right fields → the thank-you state or redirect shows → delete the row | | | row id |
| Slider: moving each lever changes the outputs; "Back to today" restores; today's numbers equal FACTS.md to the penny | | | values |
| Videos load (poster + first frame), tabs scroll, sticky elements do not cover content on a phone | | | |
| No `.bak`, `.md`, `_qc` or work files served from the deploy tree | | | |
| Banned-token sweep on every deployed HTML: 0 hits | | | |
| Every "X of N" count on the page matches its data file | | | |
| Contrast ≥ 4.5:1 on every text/background pair introduced this round (compute it) | | | |
| Reading level on prose only (`fk_prose.py`) ≤ grade 7 | | | grade |

Then **FIX BEFORE SEND (max 10):** `file | what fails | evidence | the fix`.
Screenshots to `{{OUT_DIR}}/shots/`; name them by page and viewport; sanity-check title vs filename before you cite one.
