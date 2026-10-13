---
name: ai-visibility-report
description: >
  Generate a white-label AI Visibility and GEO report for any brand (a SaaS product, a clinic,
  a practice, a professional-services firm): how often ChatGPT, Gemini, Claude and Perplexity
  mention and cite the brand versus competitors, by model and by prompt, with citation landscape,
  AI search demand and next actions, as a client-ready PDF plus data JSON. Runs on the DataForSEO
  MCP or directly on the DataForSEO REST API via the bundled scripts/dfs.py. Use when the user says
  "AI visibility report", "GEO report", "AEO report", "are we visible in AI search", "does ChatGPT
  mention [brand]", "brand mentions in ChatGPT/Gemini/Perplexity", "AI mention share", "citation
  share", "LLM visibility for [brand]", or wants an AI-search proof deliverable for a prospect.
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./ai-visibility-report-output/`.

# ai-visibility-report

This skill is built on DataForSEO's public "AI Visibility Report" Claude Code template
(https://dataforseo.com/templates/ai-visibility-report-with-dataforseo-claude-code/). The
template body follows below with only small edits; this first section adds how to run it
without the MCP, cost rules and hard-won gotchas. Read it before the template body.

**Gotcha:** do NOT send `max_output_tokens` to `ai_optimization/chat_gpt/llm_responses/live`;
gpt-5.x models return 40501 Invalid Field. The other three providers accept it. Claude may
return 50301 overloaded; retry once.

## Running it in your environment (read first)

**Credentials.** The scripts read `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD` from the
environment. Each Bash call is a fresh shell, so load the shared env file in the SAME Bash
call as every script command:

```
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ai-visibility-report/scripts/<name>.py ...
```

Never hardcode the credentials, never echo them into chat, files or logs.

**Access: MCP or REST, same calls.** The template body says "V1 connector" or "V3 connector"
and stops if neither is present. If the DataForSEO MCP is NOT connected, do not stop. Use the
bundled helper `scripts/dfs.py` instead. It mirrors the V3 tool one to one:

```
# body says:   api_request(method="POST", path="/v3/x/y/live", data=[{...}])
# run instead: set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ai-visibility-report/scripts/dfs.py POST /v3/x/y/live '[{...}]' --out step.json
# or in Python:
import sys, os; sys.path.insert(0, os.path.expanduser("~/.claude/skills/ai-visibility-report/scripts"))
from dfs import api_request, result_items, run_cost
```

Prove access with the free balance call: `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ai-visibility-report/scripts/dfs.py --balance`.

Rules for the REST path: follow the template's **V3** branch everywhere (V1 named tools map
to V3 paths via the translation tables in the body and in `references/endpoints.md`).
REST responses are the plain envelope, NOT the MCP's AI-mode shape, so read
`tasks[0].result[0].items` where the body says `items` (helper: `result_items()`).
A bare `curl -u "$DATAFORSEO_LOGIN:$DATAFORSEO_PASSWORD" https://api.dataforseo.com/v3/...`
works too after loading the env file. If a call returns HTTP 401 the credentials are wrong
(use the API password from the DataForSEO dashboard, not your login password), not the MCP.
The helper exports `SSL_CERT_FILE` from certifi itself (some Python builds fail TLS without it).
Sub-agents the body spawns get the same helper path and the same rules.

**Cost discipline.** Rough cost per run: US$2 to US$6 for one brand (about 20 to 40 live LLM
calls at roughly US$0.10 each, plus a few US$0.10 llm_mentions dataset calls). Competitors add
no live calls. Print the `cost` field of every response and the running total (the helper
prints `cost=$x cumulative=$y` on stderr and keeps a local ledger at
`./ai-visibility-report-output/dfs-cost-ledger.jsonl`, override with `DFS_LEDGER`; set
`DFS_RUN_ID=<brand-slug>-<date>` so one run sums cleanly). State the total in the final
summary. Confirm scope with the user before any run estimated above US$5.

**Known gotchas.**
- The LLM endpoints are `ai_optimization/{chat_gpt|claude|gemini|perplexity}/llm_responses/live`
  with body `{user_prompt, model_name, web_search, max_output_tokens}`. Valid model names come
  from `/models` on each. gpt-5.x rejects `temperature`.
- `ai_optimization/llm_mentions/search/live` needs `target:[{"domain":"x.com"}]` and costs about
  US$0.10 a call.
- A `message_chain` (multi-turn) message is capped at 500 characters ("Invalid Field" above
  that). Pass a short summary of a prior answer, not the whole thing.
- `rank_group` is organic position and `rank_absolute` counts ads and SERP features too; never mix them.
- Google Ads CPC values from DataForSEO are USD regardless of `location_code`; convert and state the rate.
- Location codes: UK 2826, Canada 2124, US 2840, Australia 2036. Language "en".
- For the true spend of a run, quote the summed per-response `cost` fields, or the balance
  delta (`--balance` before and after).

**Output rules.** Write for a business owner: plain English, no jargon, every number
traceable to an endpoint and date, no outcome promises, and never invent a figure when an
endpoint returns null (write "not available from <endpoint> on <date>" instead). White-label
the report in the client's brand for client work (your own brand tokens, colours and fonts,
for your own material; optional: keep them in `~/.claude/brand/tokens.css`). Never include any
DataForSEO, Claude or AI-authorship reference in the PDF.

**Where files go.** Working files (config, checkpoint, prose, data JSON, PDF) go in
`./ai-visibility-report-output/<brand-slug>/` under the current working directory (the
"project folder" in the body below), never inside this skills folder. Run the scripts from the
project folder as `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ai-visibility-report/scripts/<name>.py`. Python needs `reportlab`
(`pip install reportlab certifi`). The PDF uses DejaVu Sans, which is NOT bundled: see SETUP.md
(the script searches system font folders and falls back to Helvetica with a warning).

**Approval.** Nothing client-facing is sent or published without explicit human approval.
Deliver the PDF locally; optionally upload it wherever you share files.

---

# AI Visibility & GEO Report Skill

## What This Skill Does

Measures how visible a brand is inside AI-assistant answers -- **mention share**
(how often it is named) and **citation share** (how often its domain is cited as a
source) -- across the major LLMs DataForSEO supports, for the topics that matter,
and how that compares to competitors. Output is a white-label PDF an agency can
hand straight to a client.

**Output files** (saved to the project folder):
- `[brand-domain]_ai_visibility_[YYYY-MM].pdf`
- `[brand-domain]_ai_visibility_[YYYY-MM].json` (data companion)

**Audience:** SEO/GEO agencies. Buyer = agency owner. Operator = GEO strategist.

---

**EXECUTION DIRECTIVE — READ THIS FIRST**

This skill is a strict protocol. Follow every step exactly as written.

- **Do not skip steps.** Every step exists for a reason. If a step says "wait for user reply", wait.
- **Do not substitute endpoints.** Use only the endpoint types listed. Do not call any other DataForSEO tool.
- **Do not invent data.** If an endpoint returns no data, log it and continue — never estimate or assume values.
- **Do not add unsolicited extras.** No extra sections, no bonus recommendations outside the defined output format, no tools beyond what is specified.
- **If something is unclear**, re-read the relevant step. Do not improvise.

---

## Core Principle: Determinism

The **structure of the report is fixed by `scripts/build_report.py`**, not by the
data. Every section title, every table column header, and the fixed vocabularies
(prompt types, prominence levels) are constants inside the script
(`SECTION_TITLES`, `COLUMNS`, `PROMINENCE_ORDER`, `PROMPT_TYPES`). Likewise **every
number is fixed by `scripts/aggregate.py`**, which computes all shares, rates and
matrices from the classification checkpoint — you do not compute them by hand. Your
only free-text inputs are narratives and insights. You must never invent new columns,
rename sections, or hand-calculate metrics. This guarantees an identical skeleton and
reproducible numbers on every run.

**Mention vs citation are always kept separate.** Never merge them into one number
except inside the single, clearly-labelled AI Visibility Score.

**Who may edit `build_report.py`.** The "do not edit the script" rule below applies to
the **operator at runtime** — do not hand-hack the PDF per run, as that breaks
determinism. It does **not** apply to the skill **maintainer**, who may and should
change the script to fix bugs or evolve the layout. Operator vs maintainer is the
distinction: runtime run = never touch it; maintenance = edit freely.

---

## Two Data Tracks (read `references/endpoints.md` before running)

- **Track A -- Dataset** (`ai_opt_llm_ment_*`): pre-aggregated brand/competitor
  mention & citation metrics, most-cited domains/pages, cross-brand comparison.
  Platform is `chat_gpt` **or** `google`. The `chat_gpt` dataset platform is only
  available for **United States / English**; every other locale must use the
  `google` platform. The skill picks this per locale (see Step 2.5, `track_a_platform`)
  and never hard-codes `chat_gpt`. Cheap and broad.
- **Track B -- Live probing** (`ai_optimization_llm_response`,
  `ai_optimization_chat_gpt_scraper`): the actual answer a model gives to **your
  generated prompt**, for all four LLM types. This is what powers the by-prompt and
  by-model views and lets the prompt set be shown transparently. Costs 1 call per
  prompt per model. Live endpoints take **no location/language parameter** — they
  answer for the models' default region; market/language mainly scope Track A.

Default competitor depth = **Track A only** (no live probing for competitors).

**Live track is authoritative; dataset is a directional cross-check.** When the two
disagree by more than ~20 percentage points on the same metric, trust the live
(Track B) figure for the headline and note the gap in the narrative.

---

## Interaction Rules (apply to every question -- STRICT)

**One question per turn. No batching. No exceptions.** The numbered items inside
each step are asked SEQUENTIALLY, one per turn, never together. This is the single
most common failure mode of this skill -- do not collapse multiple questions into
one turn to "save time". Even though a step lists several items, you surface them
one at a time.

Hard rules:

- **Ask exactly ONE question, then STOP and wait for the user's reply.** Do not ask
  the next question, do not pre-fetch data, do not proceed to the next step until
  the answer is in hand.
- **`AskUserQuestion` must contain exactly ONE question object per call.** The tool
  technically accepts up to four; you must never pass more than one. One call = one
  question = one screen for the user.
- **Never ask two questions in the same message**, whether via `AskUserQuestion`,
  plain text, or a mix of both. Never print a consolidated list like "1)... 2)...
  3)..." asking the user to answer several at once.
- For any question with a fixed option set: use `AskUserQuestion` (interactive UI).
  Do NOT print a numbered text list for these.
- Optional text fields: ask in plain text, note "(optional -- press Enter or type
  '-' to skip)". Store null if skipped.
- Open-ended lists (keywords, competitors): ask in plain text. Never pre-fill.
- Multi-part items (e.g. "Location + language", or a custom TTF that needs a family
  name) are still asked one sub-question per turn -- ask location, wait; then ask
  language, wait.

Correct rhythm: ask Q1 → wait for answer → ask Q2 → wait for answer → ... Only after
the last question of a step is answered do you move to the next step.

---

## Prerequisites

- **A DataForSEO MCP connector, OR the bundled REST helper `scripts/dfs.py`** with
  `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` loaded (see "Running it in your environment").
  If any call returns a 401 or credential error, stop immediately and tell the user:
  "Please check the DataForSEO credentials (or connect the DataForSEO MCP), then retry."
- **Detect the connector at the start** and pick one (see Connectors below). If both a V1 and
  a V3 connector are present, **use V3**.

---

## Connectors — V1 and V3 (choose V3 if both present)

The skill runs on either DataForSEO MCP connector. **This is a transport swap only — the
logic, request parameters, and response parsing are identical on both.** Detect which is
available; if both, use V3.

- **V1** — exposes one **named tool per endpoint** (`ai_optimization_llm_response`,
  `ai_opt_llm_ment_agg_metrics`, `ai_opt_llm_ment_cross_agg_metrics`,
  `ai_opt_llm_ment_top_domains`/`_top_pages`/`_search`, `ai_optimization_llm_models`,
  `ai_optimization_keyword_data_search_volume`, the `*_loc_and_lang` / `*_filters` helpers,
  `ai_optimization_chat_gpt_scraper`). Call the tool with its structured params. Responses
  are the standard envelope — read `tasks[0].result`.
- **V3** — exposes a single generic **`api_request`** (`method`, `path`, `data`) plus
  `docs_*` tools. Call the REST path directly.

**V3 calling convention — default (AI) mode, do NOT set `noAiMode`:**
```
api_request({ method: "POST", path: "<v3 path>", data: [ { ...task params... } ] })
```
- In default AI mode V3 drops the `tasks` envelope and exposes the result array at top level
  as **`items`**. So **read `items` on V3 wherever you read `tasks[0].result` on V1**;
  everything nested below is identical (same field names). Verified on real calls.
  - i.e. V1 `tasks[0].result[0].X` ≡ V3 `items[0].X`; V1 `tasks[0].result[]` ≡ V3 `items[]`.
- **Do not force `noAiMode: true` by default.** Only if one specific call's AI subset is
  missing a field you actually need (e.g. the full message text or `annotations` on a live
  LLM response), retry *that one call* with `noAiMode: true` to get the full schema.
- `data` is an **array with exactly one task object** (DataForSEO POST convention).
- Task params use the **same field names as V1** (`user_prompt`, `model_name`, `web_search`,
  `target`, `platform`, `location_name`/`location_code`, `language_code`, `keywords`,
  `search_filter`, `search_scope`, `aggregation_key`, `links_scope`, `items_list_limit`,
  `internal_list_limit`, `limit`, `order_by`), with two differences:
  1. **The LLM type and the endpoint are in the PATH, not the body** (no `llm_type` field).
  2. **The mentions filter field is `initial_dataset_filters`** (V1 sometimes calls it `filters`).
- GET endpoints (models, loc/lang, filters, scraper locations) take no `data`.

**Endpoint map (V1 tool → V3 path · method):**

| Purpose | V1 tool | V3 path | Method |
|---|---|---|---|
| Model list (per LLM) | `ai_optimization_llm_models` | `/v3/ai_optimization/{llm}/llm_responses/models` | GET |
| Live LLM response | `ai_optimization_llm_response` | `/v3/ai_optimization/{llm}/llm_responses/live` | POST |
| ChatGPT scraper | `ai_optimization_chat_gpt_scraper` | `/v3/ai_optimization/chat_gpt/llm_scraper/live/advanced` | POST |
| Scraper locations | `ai_optimization_chat_gpt_scraper_locations` | `/v3/ai_optimization/chat_gpt/llm_scraper/locations` | GET |
| AI search volume | `ai_optimization_keyword_data_search_volume` | `/v3/ai_optimization/ai_keyword_data/keywords_search_volume/live` | POST |
| Mentions filters | `ai_optimization_llm_mentions_filters` | `/v3/ai_optimization/llm_mentions/filters` | GET |
| Target metrics (agg) | `ai_opt_llm_ment_agg_metrics` | `/v3/ai_optimization/llm_mentions/target_metrics/live` | POST |
| Multi-target (cross) | `ai_opt_llm_ment_cross_agg_metrics` | `/v3/ai_optimization/llm_mentions/multi_target_metrics/live` | POST |
| Search mentions | `ai_opt_llm_ment_search` | `/v3/ai_optimization/llm_mentions/search_mentions/live` | POST |
| Top mentioned domains | `ai_opt_llm_ment_top_domains` | `/v3/ai_optimization/llm_mentions/top_mentioned_domains/live` | POST |
| Top mentioned pages | `ai_opt_llm_ment_top_pages` | `/v3/ai_optimization/llm_mentions/top_mentioned_pages/live` | POST |
| Mentions loc/lang | `ai_opt_llm_ment_loc_and_lang` | `/v3/ai_optimization/llm_mentions/locations_and_languages` | GET |
| KW-data loc/lang | `ai_opt_kw_data_loc_and_lang` | `/v3/ai_optimization/ai_keyword_data/locations_and_languages` | GET |

`{llm}` is one of `chat_gpt` / `gemini` / `claude` / `perplexity`.

**Response field paths.** Below, `R` = `tasks[0].result` on **V1**, or `items` on **V3**
(AI mode). The nested fields are identical on both:
- **Live LLM response** — `R[0].items[]`; the element with `type == "message"` holds the
  answer as `sections[]` (join `section.text` where `type == "text"`) and the sources as
  `annotations[]` (each `{ title, url, start_index, end_index, text }`). So: mention = brand
  name in the joined text; citation = brand domain in an `annotations[].url` (redirect-resolve
  first, per 6.1); `cited_sources` = domains/pages from `annotations[].url`. `reasoning`
  elements are ignored. `R[0].web_search` shows whether search ran. (On V3 this is
  `items[0].items[]` — the result object's own `items` array.)
- **Target / multi-target metrics** — `R[0].aggregated_metrics.total.mentions` per entity;
  cited domains = `R[0].aggregated_metrics.sources_domain[]` (`{ key: domain, mentions }`).
  Multi-target returns one `R` element per `aggregation_key`.
- **AI search volume** — `R[0].items[]` → `{ keyword, ai_search_volume }`.
- **Models** — `R[]` → `{ model_name, web_search_supported, reasoning }` (a flag is present
  only when true).

Everywhere below, endpoints are named by their V1 tool; call them on V3 via the path above.
The `chat_gpt` mentions dataset remains **US / English only** on both connectors.

---

## Step 1 -- White-Label Config

Check for `_agency_whitelabel.json` in the project folder. If present, load it and
show a one-line summary ("Using saved white-label: [agency_name]."). Otherwise
collect it (these are agency-level, reusable across clients).

**Ask the items below ONE AT A TIME, one per turn, waiting for each answer before
the next** (see Interaction Rules -- no batching):

1. Plain text: "Agency name (appears in header/footer):"
2. Plain text: "Report title (default 'AI Visibility Report'):" -- default if skipped.
3. Plain text: "Footer text (default '[agency_name]  •  Confidential'):"
4. Plain text: "Path to agency logo PNG (optional -- '-' to skip):"
5. Plain text: "Primary (dark) brand color as hex, e.g. #0F2A43 (optional):"
6. Plain text: "Accent color as hex, e.g. #E4572E (optional):"
7. Plain text: "Path to a custom TTF font (optional -- '-' to skip):"
   If provided, also ask: "Font family name to register it under:"

Save as `_agency_whitelabel.json` (schema in Appendix A, `white_label` block). Any
skipped value falls back to a neutral default inside the script. **The subject
brand and competitor names are NOT white-label config -- they are client inputs
collected in Step 2.**

---

## Step 2 -- Brand & Scope

**Ask ONE AT A TIME, one question per turn, waiting for each answer before the next**
(see Interaction Rules -- no batching, exactly one question per `AskUserQuestion` call):

1. Plain text: "Brand name (e.g. 'SerpFox'):"
2. Plain text: "Brand domain -- root only, no www/https (e.g. 'serpfox.com'):"
3. Plain text: "Competitor domains for side-by-side comparison, comma-separated
   (optional -- '-' to skip; recommended up to 5):"
   For each, capture a display name (default = domain).
   **Only if one or more competitors were provided**, ask a follow-up on a separate
   turn -- Use AskUserQuestion, single-select, header "Competitor basis":
   - Question: "How should competitors be measured?"
   - Option 1: "Live prompt set -- like-for-like (recommended)" -- description:
     "Read every entity from the brand's own unbranded live answers (0 extra API
     calls). Same sample as the headline, per model, and works even when the dataset
     is empty. Scoped to your exact topics."
   - Option 2: "Aggregated dataset -- broader population" -- description: "Competitor
     share from the aggregated AI-mentions dataset (Track A, ~4-7 calls). Covers a
     wider population than your prompts, but is ChatGPT-only and often empty for niche
     brands. Directional."
   Save the boolean `competitor_live_probing` (Option 1/default = true, Option 2 = false).
   **Live probing adds NO extra live calls** — competitors are read from the 6.1
   checkpoint and aggregated in 6.3, so there is nothing to warn about on cost.
   Default to Option 1 unless the user wants the broader dataset population.
   If no competitors were provided, set `competitor_live_probing = false` and skip this.
4. Plain text: "Target keywords / topics, comma-separated (e.g. 'serp api, rank
   tracker'). Recommended 3-8 -- each is expanded into several prompts:"
5. **Location + language** (each sub-question on its own turn):

   a. Plain text: "Location (e.g. 'United States', 'United Kingdom'):"
      Look the input up in BOTH `ai_opt_llm_ment_loc_and_lang` (Track A) and
      `ai_opt_kw_data_loc_and_lang` (search volume) -- they are different lists.
      Present the best 2-3 matches via AskUserQuestion (single-select) + "None of these".
      - **If "None of these":** re-ask the location in plain text and re-present
        candidates. Cap at **2 retries**; if still unmatched, stop with a clear
        message ("I couldn't match that location in DataForSEO's lists — please give a
        country/city that appears there, e.g. 'United States'.") Do not improvise a code.
      - Save `location_name`.
      - **Platform detection (#5):** from the matched locale record, set
        `track_a_platform = "chat_gpt"` if the location+language is United States /
        English (the only locale with a chat_gpt dataset), else `"google"`.
      - **Coverage heads-up:** if the location is present in one list but not the other,
        tell the user which section will be unavailable (e.g. "AI Search Demand needs the
        keyword-data locale; it will be omitted for this market").

   b. Plain text: "Language (e.g. 'English'):"
      Do NOT free-hand the code. Match the input against the language names in the
      loc/lang lists and present the best 2-3 candidates via AskUserQuestion +
      "None of these" (re-ask on None, cap 2 retries). Derive `language_code` and
      `language_name` from the confirmed match.

   If `track_a_platform = "google"` (non-US/en), warn now: "Dataset sections
   (Citation Landscape, Competitor Comparison) will reflect the Google AI surface;
   the ChatGPT dataset cross-check isn't available for this market. Live results
   (Sections 1-3) are unaffected." Save `track_a_platform` to config.
6. **Prompt depth:** Use AskUserQuestion, single-select, header "Prompts per topic":
   - Question: "How many prompts per keyword? (drives cost: prompts x models live calls)"
   - Option 1: "3 -- lean"
   - Option 2: "4 -- standard (recommended)"
   - Option 3: "2 -- minimal / cheapest"
   The tool also shows a built-in "Other" option: if the user picks it, they can
   type a custom number. Accept it, but validate: it must be an integer >= 1.
   Round/coerce non-integers, and reject 0 or negatives (re-ask). If the custom
   value is large (> 6), note that it multiplies live calls (prompts x models) and
   confirm before saving. Save the final integer as `prompts_per_keyword`.
7. **Reporting period:** First check whether a prior `[brand-domain]_ai_visibility_*.json`
   exists in the project folder.
   - **If none exists:** do NOT offer the compare option. Skip the question, set the
     period to the current month, and tell the user: "No prior run found — this run
     becomes the baseline; the next run will show the trend."
   - **If one or more exist:** Use AskUserQuestion, single-select, header "Period":
     - Option 1: "Current snapshot (recommended)" -- label period as the current month.
     - Option 2: "Compare to previous run" -- load the most recent prior file's
       `summary` block into `previous` for trend.
   Save `period_current` (e.g. "July 2026") and, if comparing, `period_prev`.
   **Note -- the period is a label, not a query filter.** It is NEVER sent to any
   DataForSEO endpoint. The live endpoints (Track B: `ai_optimization_llm_response`,
   `ai_optimization_chat_gpt_scraper`) always answer "as of now" and take no dates,
   so all data reflects the moment of the run. "Compare to previous run" is a
   file-based, snapshot-over-snapshot trend: it reads the `summary` block of the
   brand's previously saved JSON into `previous`. Do NOT ask for arbitrary date
   ranges and do NOT apply `first_response_at`/`last_response_at` filters (doing so
   would scope Track A to a window while Track B stays "now", making the two
   inconsistent).

Save merged config to `[brand-domain]_config.json` (Appendix A).

---

## Step 2b -- Determine the Model Set (no user input, deterministic)

The model choice must be **reproducible** — two runs on the same day must pick the
same models, or the trend table shows fake movement. There is no tier/recency field
in the API, so selection is a fixed rule over the returned `model_name` strings.

For each llm_type -- `chat_gpt`, `gemini`, `claude`, `perplexity` (plus any new
llm_type the tool returns) -- call `ai_optimization_llm_models`, then:

1. **Explicit pin wins.** If `_agency_whitelabel.json` (or the client config) has
   `llm_model_overrides` mapping the llm_type to a `model_name` that exists in the
   returned list, use it verbatim. This is the maintainer-controlled, fully
   reproducible path and is preferred when models change often.
2. **Otherwise, deterministic rule** over models with `web_search_supported: true`:
   a. rank by tier class from the name: `pro` / `opus` / `ultra` / `sonar-pro`
      (top tier) rank above `flash` / `mini` / `nano` / `lite` / `haiku`;
   b. then by parsed version number descending (e.g. 5.2 > 5.1 > 5);
   c. then `reasoning: true` before false;
   d. then `model_name` ascending as a final, total tiebreak.
   Pick the top of that ordering.
3. **Fallback if no web-search model exists** for a provider: apply the same rule
   over all models regardless of web-search support, pick the top, and note in the
   run narrative that this provider has reduced citation fidelity (no web search).
   Never drop below the "at least 1 model" requirement in Step 5.

Build `llms_covered` as `[{llm_type, model_name, label}]`, label human-readable,
e.g. "ChatGPT (GPT-5.2)". Save it into the config.

**Trend integrity:** on "Compare to previous run", compare `llms_covered` to the
prior run's. If the model set differs, add a caveat to the narrative ("model lineup
changed since last run; some trend movement may reflect that, not real visibility").

---

## Step 3 -- Generate the Prompt Set (skill does this, no API)

**Count is exact.** For EACH keyword, generate **exactly `prompts_per_keyword`**
prompts -- no more, no fewer. The total prompt set therefore has
`len(keywords) x prompts_per_keyword` entries. State this count back to yourself
before generating and confirm it matches Step 4's "Total prompts = N x k".

**Language & region (#10):** write every prompt in the selected `language_name`, and
where it reads naturally, geo-qualify the wording ("…in the United Kingdom") to nudge
the model toward the target market — without breaking the "reads like a real user
question" rule. Do not force geo-qualification where it sounds unnatural.

Prompts are natural user questions, mixing branded and unbranded, using these fixed
types (from `PROMPT_TYPES` in the script -- use these exact labels):

- **Informational**: "What is [keyword] and how does it work?" / "How do I choose a [keyword]?"
- **Comparative**: "What is the best [keyword]?" / "Compare the top [keyword] providers"
- **Recommendation**: "Recommend a [keyword] for developers" / "Which [keyword] should I use for [use case]?"
- **Branded**: "Is [brand] a good [keyword]?" / "How does [brand] compare for [keyword]?"

Type allocation per keyword (`k` = `prompts_per_keyword`) -- deterministic for any `k >= 1`:
- `k = 1`: Comparative.
- `k = 2`: Comparative + Recommendation.
- `k = 3`: Comparative + Recommendation + Informational (drop Branded unless the
  keyword itself is brand-related).
- `k = 4`: one of each type (Informational, Comparative, Recommendation, Branded).
- `k > 4`: start with one of each of the 4 types, then fill the remainder by cycling
  through the unbranded types in this fixed order -- Comparative, Recommendation,
  Informational -- writing distinct question wordings each time.

Invariants (hold for every `k`):
- Exactly `k` prompts per keyword.
- At least one unbranded prompt per keyword (so unbranded discovery visibility can
  be isolated).
- At most one Branded prompt per keyword.
- Prompts read like real user questions, not keyword stuffing; no duplicate wordings
  within a keyword.

Store each as `{id, keyword, text, type, branded}` in `config.prompts`. The full
prompt set is printed verbatim in the report's Scope page for transparency.

---

## Step 4 -- Confirm Before Running

Display a summary and the **expected live-call count** = number of prompts x number
of models (Track B), plus ~6 dataset calls (Track A). Then confirm.

```
------------------------------------------------------
AI VISIBILITY REPORT -- RUN CONFIG
------------------------------------------------------
Brand:       [brand_name] ([brand_domain])
Competitors: [list or none]   Competitor basis: [live (reuse) | dataset]
Market:      [location_name] / [language_name]
Models:      [llms_covered labels]
Keywords:    [N]     Prompts/keyword: [k]     Total prompts: [N*k]
Period:      [period_current]  (compare: [period_prev or none])

ESTIMATED API CALLS
  Setup/util (models, loc/lang, filters): ~5
  Dataset (Track A): ~6  (+~[models] if competitor basis = dataset, for by_model)
  Live prompts -- brand (Track B): [N*k] x [models] = [N*k*models]
  Live prompts -- competitors: 0  (live basis reuses the brand answers above)
  ------------------------------------------------
  Total: ~[sum]  (brand live calls dominate cost)

  Live prompts run sequentially (one prompt x one model per call; no batch endpoint).
  Expect roughly [ceil(total_live / 20)]-[ceil(total_live / 10)] minutes.

OUTPUT
  PDF:  [brand-domain]_ai_visibility_[YYYY-MM].pdf
  Data: [brand-domain]_ai_visibility_[YYYY-MM].json
------------------------------------------------------
```

Use AskUserQuestion, single-select, header "Confirm":
- Option 1: "Yes -- start now"
- Option 2: "No -- edit config"

Make NO API calls until Option 1. The live-call count has **three real levers** —
name them if the count is large (roughly > 100 live calls): fewer keywords, fewer
prompts-per-keyword, and leaving competitor live probing off. (Model count is fixed;
there is no configurator screen.) Treat this as an informational cost note, not a
hard block — the recommended range (6-8 keywords x 4 prompts x 4 models = 96-128) is
normal and expected.

---

## Step 5 -- Validate

| Check | Rule |
|-------|------|
| Domain format | No https://, no www, no trailing slash. |
| Keywords | At least 1. |
| Locale | Confirmed against both loc/lang lists; `track_a_platform` set. |
| Language | Derived from a confirmed match, not free-typed. |
| Models | At least 1 in `llms_covered`, each with a valid `model_name`. |
| White-label colors | Any provided `primary_color`/`accent_color` matches `^#?[0-9A-Fa-f]{6}$`. |
| White-label logo | If `logo_path` set, the file exists and is readable. |
| White-label font | If `font_path` set, the file exists, loads, and covers `•—–…`. |
| reportlab | Run `python -c "import reportlab"`. If it fails, `pip install reportlab` once. |

For any failing white-label check, warn the user with the **specific bad value** and
let them fix it or knowingly accept the neutral fallback — do not let branding fail
silently. (The script also warns to stderr as a backstop.) Stop and state exactly
what needs fixing if a non-white-label check fails.

---

## Step 6 -- Fetch Data

Read `references/endpoints.md` for exact requests. Work section by section. If a
dataset call errors or is empty, set that section's data to null/empty and continue
-- never abort the whole run. Print a short status line after each section.

**Token-efficient workflow — you do NOT compute the numbers by hand.**
`scripts/aggregate.py` deterministically builds the entire `sections` block (all
shares, rates, matrices, citation landscape) from a compact checkpoint. Your job in
Step 6 is only to: (a) call the live API, (b) classify each answer into one small
checkpoint record and **discard the full text**, (c) fetch the few Track A values the
script can't derive, (d) write the prose. This keeps long model answers out of your
generated output and removes all in-context arithmetic.

**Classification rules for live responses (Track B) -- apply identically to brand
and competitors:**
- `mention` = brand name (or obvious variant) appears in the answer text (word-boundary, case-insensitive). String match.
- `citation` = brand domain appears in the answer body or its returned source links.
  **Resolve redirect/grounding links first (esp. Gemini):** Gemini returns
  `vertexaisearch…/grounding-api-redirect/…` URLs, not the target domain, so a naive
  match under-counts its citations. Follow/parse the redirect to the real destination
  domain before matching (or, if you cannot resolve it, note in `insight` that
  Gemini's citation rate is under-measured — do not silently score it 0).
- `prominence` (one of `Named first` / `Shortlist` / `Passing mention` / `Absent`):
  sole lead recommendation = Named first; one of several named options = Shortlist;
  named but not recommended = Passing mention; not present = Absent. **This is the only
  judgment call** (brand only) — mention and citation are pure string matches.

### 6.1 Live matrix + compact checkpoint (do this first)
For each prompt x each model in `llms_covered`, call `ai_optimization_llm_response`
(`web_search: true`). Classify the answer immediately and **append ONE compact record**
to the checkpoint `[brand-domain]_ai_visibility_[YYYY-MM]_cells.json`, then move on —
do not carry the full answer forward. A single record per (prompt, model) captures the
brand AND every competitor (one answer names them all — this is the free like-for-like
competitor data, no extra calls):
```json
{ "prompt_id":"p2", "model":"ChatGPT (GPT-5.2)", "status":"measured",
  "brand_mention":true, "brand_citation":true, "prominence":"Named first",
  "competitor_mentions":["semrush.com"], "competitor_citations":["semrush.com"],
  "cited_sources":[{"domain":"dataforseo.com","page":"/apis/serp-api"},
                   {"domain":"g2.com","page":"/best-serp-api"}] }
```
- `model` must equal a `llms_covered[].label` exactly.
- `competitor_mentions` / `competitor_citations` = competitor DOMAINS named / cited in
  this answer.
- `cited_sources` = every source link (redirect-resolved) — feeds Section 4.
- **Failed call (#2):** retry with backoff up to 3x; if still failing, append
  `{ "prompt_id":..., "model":..., "status":"not_measured" }` and move on — the
  aggregator excludes it from denominators; NEVER record it as a measured "Absent".

**Resume (#14):** at Step 6 start, if the checkpoint exists, load it and skip
(prompt_id, model) pairs already present. Delete it once the final PDF succeeds.

### 6.2 Fetch the few Track A values the aggregator can't derive
The checkpoint has everything for Sections 1-5 in LIVE mode. Two things still need a
dataset call, and go into `prose.json` (Step 7):
1. **AI search volume (Section 6):** `ai_optimization_keyword_data_search_volume`
   (keyword-data locale) -> `prose.search_volume.rows = [{keyword, ai_search_volume}]`.
   Omit the section if the locale is unavailable (Step 2.5 heads-up).
2. **Dataset-mode competitors (only if `competitor_live_probing = false`):**
   `ai_opt_llm_ment_cross_agg_metrics` (+ per-model, ChatGPT-only) with
   `platform = track_a_platform`; compute SoV rows/by_model and put them in
   `prose.competitors` with `live_basis: false`. In the default LIVE mode, do NOT do
   this — `aggregate.py` builds competitors from the checkpoint.
Optional cross-check: `ai_opt_llm_ment_agg_metrics` (Track A) for the brand; if live
vs dataset mention share differ by >~20 pts, keep live and note it in the narrative.

### 6.3 What `aggregate.py` computes from the checkpoint (do NOT compute by hand)
Reference only — the script owns this math (so it is reproducible and off your token
budget). Invariants it enforces:
- **summary:** headline over UNBRANDED, measured cells only; `score_denominator` = that
  count; `0.6/0.4` score; `cells_total/measured/failed` = full grid (reliability note).
- **by_llm:** per model over ALL prompts; mention/citation rate; modal prominence.
- **by_prompt:** all prompts; `invisible_prompts` = zero mentions AND zero citations (#16).
- **citation_landscape:** from `cited_sources`; `share = domain / total`; brand rows flagged.
- **competitors (live):** SHARE OF VOICE over unbranded cells (sums ~100%; a different
  metric from Section 1 by design), brand first, `by_model` looked up by domain.

### 6.4 Opportunities (generated, GEO-specific) -> `prose.opportunities.actions`
Write 3-6 actions grounded in the findings. Each MUST tie to a specific result:
invisible prompts to target, most-cited third-party sources to earn/pitch,
competitor citation gaps, weak models. Fields: `title, why, actions, effort,
impact, priority` (priority = High/Medium/Low). Must read like GEO strategy
(earning citations, entity coverage, source placement) -- NOT recycled SEO advice.

**Near-zero visibility is a valid, common result.** If mention_share and
citation_share are both ~0, do NOT produce a thin report: the summary auto-renders
an "effectively invisible" call-out, and the opportunities section must convert the
invisible prompts and competitor-owned citations into concrete targets. The story
is "here is exactly where you're invisible and how to fix it," never a blank page.

---

## Step 7 -- Aggregate → Data JSON

Write two small files, then let the script assemble the full data JSON:

1. **`[brand-domain]_config.json`** — the merged config (Step 1 white-label + Step 2
   scope + Step 2b models + Step 3 prompts + `score_weights` + `track_a_platform` +
   `output_path`). Appendix A.
2. **`[brand-domain]_prose.json`** — only the LLM-authored text: `summary.narrative`
   & `.insight` (+ optional `.previous`), one `insight` per section, `search_volume`,
   dataset-mode `competitors`, and `opportunities.actions`. Appendix B (prose schema).

Then run the aggregator (checkpoint from 6.1 + config + prose -> full data JSON):
```bash
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ai-visibility-report/scripts/aggregate.py \
  "[project_folder]/[brand-domain]_config.json" \
  "[project_folder]/[brand-domain]_ai_visibility_[YYYY-MM]_cells.json" \
  "[project_folder]/[brand-domain]_prose.json" \
  -o "[project_folder]/[brand-domain]_ai_visibility_[YYYY-MM].json"
```
It prints the headline numbers and writes the data JSON (Appendix C). Do NOT hand-write
the `sections` block — the aggregator owns every number.

---

## Step 8 -- Generate PDF

```bash
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ai-visibility-report/scripts/build_report.py "[project_folder]/[brand-domain]_ai_visibility_[YYYY-MM].json"
```
On success: `Report saved: [path]`. Delete the `_cells.json` checkpoint now. **Do not
edit build_report.py or aggregate.py at runtime** (this prohibition is for the
operator; the maintainer may edit them — see Core Principle). Watch stderr for
`[build_report] WARNING:` lines (bad hex color, missing logo/font, flattened font
weights) and relay any to the user.

Common errors:
- `ModuleNotFoundError: reportlab` -> `pip install reportlab`
- `UnicodeEncodeError` -> ensure JSON saved with utf-8.

---

## Step 9 -- Deliver

```
AI Visibility report complete.

PDF:  [output_path]
Data: [data_json_path]

Headline:
  - AI Visibility Score: [score]/100  (unbranded prompts, [D] measured responses)
  - Mention share: [x]%   Citation share: [y]%   (kept separate)
  - [n]/[N] prompts mention the brand across [m] models
  - [k] invisible prompts flagged (no mention AND no citation)
  - Top competitor: [domain] at [x]% mention share

Note: figures are a point-in-time snapshot; LLM answers vary run to run, so small
differences may be noise, not real change.
```

---

## Error Handling

| Situation | Action |
|-----------|--------|
| A live model call errors | Retry w/ backoff (3x). If still failing, mark the cell `not_measured` and EXCLUDE it from denominators — never count it as `Absent`/"not mentioned" (see 6.1). |
| >20% of live cells failed | Flag the run low-confidence in the narrative; advise re-running. |
| Dataset call empty | Citation Landscape is built from live `cited_sources` by the aggregator (6.1/6.3), so it survives an empty dataset. PDF renders a neutral "no data" note only if nothing was cited anywhere. |
| Brand invisible everywhere | Expected -- render the invisibility story + targeted opportunities. |
| DataForSEO 401 | Stop. "Please check DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD (API password) or re-authenticate the DataForSEO MCP." |
| No competitors provided | Skip Section 5 entirely (PDF omits it and renumbers automatically). |
| Non-US/en market | `track_a_platform = google`; warn dataset sections use the Google surface; live unaffected. |
| User says no at Step 4 | Ask what to change, update config, re-display summary. |

---

## Appendix A -- Config Schema

`_agency_whitelabel.json` (reusable) provides the `white_label` block (and may carry
an optional `llm_model_overrides` map used by Step 2b):
```json
{
  "white_label": {
    "agency_name":     "North Star Digital",
    "report_title":    "AI Visibility Report",
    "footer_text":     "North Star Digital  •  Confidential",
    "logo_path":       null,
    "primary_color":   "#0F2A43",
    "accent_color":    "#E4572E",
    "font_path":       null,
    "font_name":       null,
    "font_path_bold":  null,
    "font_path_italic":null
  },
  "llm_model_overrides": {
    "chat_gpt": "gpt-5.2", "gemini": "gemini-3.1-pro-preview",
    "claude": "claude-opus-4-8", "perplexity": "sonar-pro"
  }
}
```
`font_path_bold` / `font_path_italic` are optional; without them a custom font's
bold/italic collapse to one weight (the script warns). `llm_model_overrides` is
optional; when present it pins the model per llm_type for fully reproducible runs.

`[brand-domain]_config.json` (per client), merged into the data JSON `config`:
```json
{
  "brand_name":   "SerpFox",
  "brand_domain": "serpfox.com",
  "competitors":  [{ "name": "DataForSEO", "domain": "dataforseo.com" }],
  "competitor_live_probing": true,
  "location_name":"United States",
  "language_code":"en",
  "language_name":"English",
  "track_a_platform":"chat_gpt",
  "period_current":"July 2026",
  "period_prev":  null,
  "date_generated":"2026-07-02",
  "llms_covered": [
    { "llm_type": "chat_gpt",   "model_name": "gpt-5.2",              "label": "ChatGPT (GPT-5.2)" },
    { "llm_type": "gemini",     "model_name": "gemini-3.1-pro-preview","label": "Gemini (3.1 Pro)" },
    { "llm_type": "claude",     "model_name": "claude-opus-4-8",       "label": "Claude (Opus 4.8)" },
    { "llm_type": "perplexity", "model_name": "sonar-pro",             "label": "Perplexity (Sonar Pro)" }
  ],
  "keywords": ["serp api", "rank tracker"],
  "prompts_per_keyword": 4,
  "prompts": [
    { "id": "p1", "keyword": "serp api", "text": "What is the best SERP API for developers?", "type": "Comparative", "branded": false }
  ],
  "score_weights": { "mention": 0.6, "citation": 0.4 },
  "white_label": { "...": "from _agency_whitelabel.json" },
  "output_path": "serpfox.com_ai_visibility_2026-07.pdf"
}
```

---

## Appendix B -- Checkpoint & Prose Schemas (operator writes these)

**Checkpoint `[brand-domain]_ai_visibility_[YYYY-MM]_cells.json`** — a JSON list; one
record per (prompt, model), appended live in 6.1 (`model` = exact `llms_covered[].label`):
```json
[
  { "prompt_id": "p2", "model": "ChatGPT (GPT-5.2)", "status": "measured",
    "brand_mention": true, "brand_citation": true, "prominence": "Named first",
    "competitor_mentions": ["semrush.com"], "competitor_citations": ["semrush.com"],
    "cited_sources": [ { "domain": "dataforseo.com", "page": "/apis/serp-api" },
                       { "domain": "g2.com", "page": "/best-serp-api" } ] },
  { "prompt_id": "p3", "model": "Gemini (3.1 Pro)", "status": "not_measured" }
]
```

**Prose `[brand-domain]_prose.json`** — ONLY the LLM-authored text; every number is
computed by `aggregate.py`. All fields optional except where the section needs text:
```json
{
  "summary": { "narrative": "...", "insight": "...",
               "previous": { "mention_share": 15, "citation_share": 5, "ai_visibility_score": 11 } },
  "by_llm": { "insight": "..." },
  "by_prompt": { "insight": "..." },
  "citation_landscape": { "insight": "..." },
  "competitors": { "insight": "..." },
  "search_volume": { "rows": [ { "keyword": "serp api", "ai_search_volume": 4200 } ], "insight": "..." },
  "opportunities": { "actions": [
    { "title": "...", "why": "...", "actions": "1) ...  2) ...",
      "effort": "Medium (1-2 weeks)", "impact": "High -- targets most-cited domains",
      "priority": "High" } ] }
}
```
In **dataset** competitor mode only, also supply `competitors.rows` / `.by_model` /
`live_basis: false` here (the aggregator does not build dataset competitors).

---

## Appendix C -- Data JSON Schema (aggregate.py output, build_report.py input)

`aggregate.py` writes `{config, sections}`; `build_report.py` reads it. Section titles
and table headers are NOT here — they are fixed constants in the script. This is
generated, not hand-written; shown for reference:
```json
{
  "config": { "...": "Appendix A, fully merged" },
  "sections": {
    "summary": { "mention_share": 22, "citation_share": 8, "ai_visibility_score": 16,
      "prompts_total": 15, "prompts_with_mention": 4, "prompts_with_citation": 2,
      "models_total": 4, "cells_total": 80, "cells_measured": 78, "cells_failed": 2,
      "score_denominator": 58, "previous": null, "narrative": "...", "insight": "..." },
    "by_llm": { "rows": [ { "model_label": "ChatGPT (GPT-5.2)", "prompts_tested": 20,
      "mentions": 5, "mention_rate": 25, "citations": 1, "citation_rate": 5,
      "avg_prominence": "Shortlist" } ], "insight": "..." },
    "by_prompt": { "rows": [ { "prompt": "...", "type": "Comparative",
      "models_mentioning": ["Gemini (3.1 Pro)"], "models_total": 4,
      "prominence": "Shortlist", "cited": true, "visible": true } ],
      "invisible_prompts": ["..."], "insight": "..." },
    "citation_landscape": { "top_domains": [ { "domain": "g2.com", "citations": 5,
      "share": 17, "is_brand": false } ], "top_pages": [ { "page": "/best", "domain":
      "g2.com", "citations": 4, "is_brand": false } ], "brand_cited_pages": [], "insight": "..." },
    "competitors": { "live_basis": true, "rows": [ { "name": "SerpFox", "domain":
      "serpfox.com", "mention_share": 22, "citation_share": 8, "ai_visibility_score": 16,
      "is_brand": true } ], "by_model": [ { "model_label": "ChatGPT (GPT-5.2)",
      "brand_mention_share": 25, "competitors": [ { "domain": "dataforseo.com",
      "mention_share": 75 } ] } ], "insight": "..." },
    "search_volume": { "rows": [ { "keyword": "serp api", "ai_search_volume": 4200 } ], "insight": "..." },
    "opportunities": { "actions": [ { "title": "...", "why": "...", "actions": "...",
      "effort": "...", "impact": "...", "priority": "High" } ] }
  }
}
```

---

## Reference Files

- `references/endpoints.md` -- DataForSEO AI Optimization endpoint reference, per
  section, with the Track A / Track B split. Read before fetching.
- `scripts/aggregate.py` -- deterministic aggregator: compact checkpoint + config +
  prose -> full data JSON. Owns every number; call via subprocess, do not modify at
  runtime (maintainer may).
- `scripts/dfs.py` -- DataForSEO REST helper (mirrors the MCP V3 `api_request`), prints the
  cost of every call and keeps a local per-run cost ledger.
- `scripts/build_report.py` -- deterministic PDF generator. Call via subprocess; the
  operator does not modify it at runtime (the maintainer may — see Core Principle).
  Section titles and table columns are fixed constants inside it.
