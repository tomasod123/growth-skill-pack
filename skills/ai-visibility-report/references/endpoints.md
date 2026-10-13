# DataForSEO AI Optimization -- Endpoint Reference for the AI Visibility Report

All data is fetched via the DataForSEO MCP. This file documents the exact tools,
request parameters, and response fields used by the skill, and **which report
section each one feeds**.

There are two complementary data tracks. Understanding the split is essential:

| Track | Tools | What it gives | Hard limits |
|-------|-------|---------------|-------------|
| **A -- Dataset (broad, cheap)** | `ai_opt_llm_ment_*` family | Pre-aggregated mention & citation metrics for the brand and competitors, most-cited domains/pages, cross-brand comparison | `platform: "chat_gpt"` or `"google"`. **`chat_gpt` is US/English only**; other locales must use `"google"`. Pass `track_a_platform` (set in Step 2.5), never a hard-coded `chat_gpt`. Query the existing mentions dataset, NOT your prompts. Filter by model with `model_name` (only meaningful for `chat_gpt`). |
| **B -- Live probing (targeted, costs 1 call each)** | `ai_optimization_llm_response`, `ai_optimization_chat_gpt_scraper` | The **actual answer** a specific model gives to **your generated prompt**, parseable for the brand name and domain. Covers all four LLM types incl. Claude & Perplexity. | 1 request = 1 prompt x 1 model. Cost/time scale with prompts x models. |

Track B is what makes the by-prompt and by-model views possible and lets us show
the generated prompts transparently. Track A is what makes competitor comparison
and citation-landscape breadth affordable.

**On the reporting period / dates.** The report's `period` is a label only; it is
never sent to any endpoint. The live endpoints (Track B) take no date parameters
and always answer "as of now". The dataset endpoints (Track A) *do* expose
`first_response_at` / `last_response_at` time filters, but the skill deliberately
does NOT use them: scoping Track A to a past window while Track B stays "now" would
make the two tracks' mention/citation numbers inconsistent. Trend ("with trend if
run before") is therefore file-based -- the current run is compared against the
brand's previously saved report JSON, not against a historical query.

---

## Connectors — V1 and V3 (transport only; parsing is identical)

Every endpoint below is named by its **V1 tool**. It works the same on the **V3**
connector — call the REST path with `api_request` in **default (AI) mode** (do NOT set
`noAiMode`). See SKILL.md → "Connectors" for the full map and response field paths. Detect
the connector; if both are present, use V3.

- **V1:** call the named tool with the JSON shown in each section as its params. Read
  responses at `tasks[0].result`.
- **V3:** `api_request({ method, path, data: [ <that same JSON as one task> ] })`. The
  `llm_type`/endpoint is in the PATH (not the body); the mentions filter field is
  `initial_dataset_filters`. AI mode drops the `tasks` envelope and exposes the result array
  as top-level **`items`** — read `items` where V1 reads `tasks[0].result`; nested fields are
  identical. Force `noAiMode: true` only for a single call whose AI subset is missing a field
  you need (e.g. `annotations` on a live LLM response).

| V1 tool | V3 path · method |
|---|---|
| `ai_optimization_llm_models` | `/v3/ai_optimization/{llm}/llm_responses/models` · GET |
| `ai_optimization_llm_response` | `/v3/ai_optimization/{llm}/llm_responses/live` · POST |
| `ai_optimization_chat_gpt_scraper` | `/v3/ai_optimization/chat_gpt/llm_scraper/live/advanced` · POST |
| `ai_optimization_chat_gpt_scraper_locations` | `/v3/ai_optimization/chat_gpt/llm_scraper/locations` · GET |
| `ai_optimization_keyword_data_search_volume` | `/v3/ai_optimization/ai_keyword_data/keywords_search_volume/live` · POST |
| `ai_optimization_llm_mentions_filters` | `/v3/ai_optimization/llm_mentions/filters` · GET |
| `ai_opt_llm_ment_agg_metrics` | `/v3/ai_optimization/llm_mentions/target_metrics/live` · POST |
| `ai_opt_llm_ment_cross_agg_metrics` | `/v3/ai_optimization/llm_mentions/multi_target_metrics/live` · POST |
| `ai_opt_llm_ment_search` | `/v3/ai_optimization/llm_mentions/search_mentions/live` · POST |
| `ai_opt_llm_ment_top_domains` | `/v3/ai_optimization/llm_mentions/top_mentioned_domains/live` · POST |
| `ai_opt_llm_ment_top_pages` | `/v3/ai_optimization/llm_mentions/top_mentioned_pages/live` · POST |
| `ai_opt_llm_ment_loc_and_lang` | `/v3/ai_optimization/llm_mentions/locations_and_languages` · GET |
| `ai_opt_kw_data_loc_and_lang` | `/v3/ai_optimization/ai_keyword_data/locations_and_languages` · GET |

`{llm}` is one of `chat_gpt` / `gemini` / `claude` / `perplexity`. Response root `R` = `tasks[0].result`
(V1) or `items` (V3). Key paths, identical below the root: live answer text = `R[0].items[]`
(`type=="message"` → join `sections[].text`), cited sources = that message's `annotations[].url`;
metrics = `R[0].aggregated_metrics.total.mentions` + `R[0].aggregated_metrics.sources_domain[]`;
volume = `R[0].items[].ai_search_volume`.

---

## Utility / setup tools (call these first, cost 0)

### `ai_optimization_llm_models`
Lists available models per `llm_type` (`chat_gpt`, `gemini`, `claude`, `perplexity`).
Call once per selected llm_type to pick the flagship model. Prefer a model with
`"web_search_supported": true` so answers reflect current web knowledge.

Request: `{ "llm_type": "chat_gpt" }`
Response: array of `{ model_name, reasoning, web_search_supported, task_post_supported }`.

### `ai_opt_llm_ment_loc_and_lang`
Valid locations/languages for the **mentions dataset** (Track A). No args. Use the
matched record to set `track_a_platform`: `chat_gpt` only for United States / English,
otherwise `google`. Every `ai_opt_llm_ment_*` call below passes this
`<track_a_platform>`, never a hard-coded `chat_gpt`.

### `ai_opt_kw_data_loc_and_lang`
Valid locations/languages for **AI search-volume** (`ai_optimization_keyword_data_search_volume`).
Note: this is a **different list** from the mentions one -- validate the chosen
locale against both before running.

### `ai_optimization_llm_mentions_filters`
Returns the filterable fields for the `ai_opt_llm_ment_*` family. As of writing:
`platform`, `location_code`, `language_code`, `ai_search_volume`,
`first_response_at`, `last_response_at`, `model_name`. Use `model_name` to build
the per-model rows of the by-LLM cross-check.

### `ai_optimization_chat_gpt_scraper_locations`
Valid locations for the live ChatGPT scraper (Track B citation source).

---

## Section: Scope & Prompt Set

No endpoint. The prompt set is **generated by the skill** from the user's keywords
(see SKILL.md, Step 3) and written verbatim into `config.prompts`. Model list comes
from `ai_optimization_llm_models`.

---

## Section 1: AI Visibility Summary

### `ai_opt_llm_ment_agg_metrics`  (Track A -- headline shares)
Aggregated mention metrics for the brand.

Request:
```json
{
  "target": [{ "domain": "serpfox.com" }],
  "platform": "<track_a_platform>",
  "location_name": "United States",
  "language_code": "en"
}
```
Use the returned counts as a dataset-side estimate and **reconcile with the Track B
prompt-level rates** (which cover all models). The live figures are the authoritative
headline; if they differ from this dataset estimate by more than ~20 points, keep the
live numbers and note the gap. Pass `<track_a_platform>` for the market.

### `ai_optimization_llm_response`  (Track B -- prompt-level truth)
For every generated prompt x every selected model, send the prompt and parse the
answer. This is the primary source for the summary counters.

Request:
```json
{
  "llm_type": "chat_gpt",
  "model_name": "gpt-5.2",
  "user_prompt": "What is the best SERP API for developers?",
  "web_search": true
}
```
From each response, determine per (prompt, model):
- **mention** = brand name appears in the answer text (case-insensitive, word match).
- **citation** = brand domain appears in the answer / its cited sources/links.
- **cited_sources** = the third-party domains/pages the answer links (retain them —
  Section 4 reuses these when the dataset is empty).

Aggregate the headline over **unbranded prompts only** and over **successfully
measured cells only** (retry failures; exclude the ones that still fail — do not
count them as "not mentioned"):
- `D` = (unbranded prompts x models) − not_measured cells
- `mention_share = unbranded_mentions / D * 100`
- `citation_share = unbranded_citations / D * 100`
- `ai_visibility_score = 0.6 * mention_share + 0.4 * citation_share`
Record `cells_total`, `cells_measured`, `cells_failed` in `sections.summary`.

---

## Section 2: By-LLM Breakdown

### `ai_optimization_llm_models` (model list) + `ai_optimization_llm_response` (Track B)
Group the Track B results by model to fill each row: `prompts_tested`, `mentions`,
`mention_rate`, `citations`, `citation_rate`, `avg_prominence`.

### `ai_opt_llm_ment_agg_metrics` with `model_name` filter (Track A cross-check, optional)
For chat_gpt models only, add a dataset-side rate as corroboration.
```json
{
  "target": [{ "domain": "serpfox.com" }],
  "platform": "<track_a_platform>",
  "filters": [["model_name", "=", "gpt-5.2"]]
}
```

### `ai_optimization_chat_gpt_scraper` (Track B, ChatGPT live search)
Optional: real ChatGPT-search answer + citation links for a keyword, to enrich the
ChatGPT row and the citation landscape.
```json
{ "keyword": "best serp api", "language_code": "en", "location_name": "United States" }
```

---

## Section 3: By Prompt & Topic

### `ai_optimization_llm_response` (Track B)
The per-prompt rows come straight from the Track B matrix: which models mentioned
the brand, the prominence (Named first / Shortlist / Passing mention / Absent --
judged from answer text), and whether cited. Any prompt with zero mentions across
all models goes into `invisible_prompts`.

### `ai_opt_llm_ment_search` (Track A -- topic context, optional)
Broader dataset view of how a **keyword** surfaces the brand.
```json
{
  "target": [{ "keyword": "serp api", "match_type": "word_match" }],
  "platform": "<track_a_platform>",
  "limit": 20
}
```

---

## Section 4: Citation Landscape

### `ai_opt_llm_ment_top_domains` (Track A)
Domains models cite most for the target.
```json
{
  "target": [{ "keyword": "serp api" }],
  "platform": "<track_a_platform>",
  "links_scope": "sources",
  "items_list_limit": 10,
  "internal_list_limit": 5
}
```
Mark `is_brand = true` for the brand's own domain.

Run **one call with the full keyword set** (not looped per keyword) so counts
aggregate in a single pass. `share = domain_citations / sum(all domain_citations) * 100`.

### `ai_opt_llm_ment_top_pages` (Track A)
Same, grouped by page URL. Highlight brand-owned pages in `brand_cited_pages`.

### Live source links (Track B) -- fallback / merge, no extra calls (#6)
The dataset legitimately returns **empty** for niche B2B brands. In that case build
the landscape from the `cited_sources` already captured per live answer in Step 6.1
(the third-party domains/pages the models linked) — no additional API calls. If the
dataset is non-empty, keep it primary and optionally merge the live sources in
(dedupe by domain/page, sum counts). Discarding those links was the old bug.

### `ai_optimization_chat_gpt_scraper` (Track B, optional)
Live ChatGPT-search citation links to further complement the domains/pages.

---

## Section 5: Competitor Comparison (only if competitors provided)

### `ai_opt_llm_ment_cross_agg_metrics` (Track A -- primary)
Built exactly for brand-vs-competitor. Pass each entity with its own
`aggregation_key`; the response is grouped so you can read one row per brand.
```json
{
  "targets": [
    { "aggregation_key": "serpfox.com",   "target": [{ "domain": "serpfox.com" }] },
    { "aggregation_key": "dataforseo.com","target": [{ "domain": "dataforseo.com" }] },
    { "aggregation_key": "serpapi.com",   "target": [{ "domain": "serpapi.com" }] }
  ],
  "platform": "<track_a_platform>",
  "location_name": "United States",
  "language_code": "en"
}
```
Always run this for the overall view. The competitor metric is **share of voice** —
each entity's share of all brand+competitor mentions/citations (values sum to ~100%),
which is a DIFFERENT metric from the Section 1 response rate, so the brand's row here
will not equal its page-1 headline (by design). The PDF labels these columns "… SoV".
**The response returns raw COUNTS, not percentages.** Define the shares yourself with
a shared denominator across the brand and all competitors, so a value is always 0-100:
- `mention_share = entity_mentions / sum(mentions across brand + all competitors) * 100`
- `citation_share = entity_citations / sum(citations across all entities) * 100`
  (if the endpoint gives no citation count, derive from each entity's own domain in
  sources, or set `citation_share = null` -> the PDF prints "n/a"). Never emit a raw
  count as a share.
- `ai_visibility_score = 0.6*mention_share + 0.4*citation_share`.
Compute the **brand's own row on this same dataset basis** (not the live headline) so
the table is internally consistent; the PDF labels these columns "Dataset …".

When `competitor_live_probing = false`, `by_model` is built by repeating this call
with the `model_name` filter — but only `chat_gpt` has a dataset, so **the dataset
`by_model` matrix covers ChatGPT only.** Do not fabricate Gemini/Claude/Perplexity
rows.

### Competitor live basis -- REUSE 6.1, no extra calls (`competitor_live_probing = true`, default)
Controlled by the config toggle set in Step 2. Live is the recommended default:
- **true (live, recommended):** do NOT call `ai_optimization_llm_response` again for
  competitors. Every competitor's mentions and citations are already in the brand's
  unbranded 6.1 answers — one answer to "best rank tracker?" names every vendor. Tally
  all entities from that single shared sample (same classification rules), so the
  brand's competitor row rests on the identical sample as its Section 1 headline. Set
  `live_basis = true`. **Cost: 0 extra live calls.**
- **false (dataset):** use Track A `cross_agg_metrics` only (above). Set
  `live_basis = false`. Broader population than your prompts, but ChatGPT-only and
  often empty for niche brands.

Never re-ask prompts per competitor: it wastes calls and measures the brand on a
different draw than its headline.

---

## Section 6: AI Search Demand

### `ai_optimization_keyword_data_search_volume` (Track A)
Estimated LLM query usage per keyword.
```json
{ "keywords": ["serp api", "rank tracker"], "language_code": "en", "location_name": "United States" }
```
Put the returned volume in `ai_search_volume`. The report table is AI-demand only —
there is no web-search-volume column (it was always empty, so it was removed). Uses
the keyword-data locale; if unavailable for the market, omit this section.

---

## Section 7: Opportunities & Next Actions

No endpoint. Generated by the skill from the findings above (invisible prompts,
weak models, competitor citation gaps). Must be GEO-specific, not generic SEO.

---

## Endpoint Summary

| # | Section | Tool | Track | Calls |
|---|---------|------|-------|-------|
| 0 | Setup | `ai_optimization_llm_models` | util | 1 per llm_type |
| 0 | Setup | `ai_opt_llm_ment_loc_and_lang`, `ai_opt_kw_data_loc_and_lang` | util | 1 each |
| 0 | Setup | `ai_optimization_llm_mentions_filters` | util | 1 |
| 1 | Summary | `ai_opt_llm_ment_agg_metrics` | A | 1 |
| 1 | Summary | `ai_optimization_llm_response` | B | prompts x models |
| 2 | By-LLM | `ai_optimization_llm_response` (regrouped) | B | (reuses S1) |
| 2 | By-LLM | `ai_opt_llm_ment_agg_metrics` + model_name filter | A | 0-N (optional) |
| 2 | By-LLM | `ai_optimization_chat_gpt_scraper` | B | 0-1 (optional) |
| 3 | By prompt | `ai_optimization_llm_response` (regrouped) | B | (reuses S1) |
| 3 | By prompt | `ai_opt_llm_ment_search` | A | 0-1 per kw (optional) |
| 4 | Citations | `ai_opt_llm_ment_top_domains` | A | 1 (full keyword set) |
| 4 | Citations | `ai_opt_llm_ment_top_pages` | A | 1 (full keyword set) |
| 4 | Citations | live `cited_sources` reuse | B | 0 (fallback when dataset empty) |
| 5 | Competitors (live, default) | reuse 6.1 unbranded answers | B | **0 extra** |
| 5 | Competitors (dataset) | `ai_opt_llm_ment_cross_agg_metrics` | A | 1 (+1 per model, ChatGPT-only by_model) |
| 6 | AI demand | `ai_optimization_keyword_data_search_volume` | A | 1 |

**Typical total (brand + 2 competitors, 5 keywords x 4 prompts, 4 models):**
~5 setup/util + ~6 dataset + (20 prompts x 4 models = 80 brand live) ≈ **~91 calls**.
Live competitor probing (default) adds **0** — it reuses the brand answers. The
dataset basis adds only ~4-7 dataset calls. There is no configuration under which
competitors multiply the live-call count.

**Cost levers (there is no configurator screen, and the model set is fixed):** reduce
by (1) fewer keywords, (2) fewer prompts-per-keyword. Competitor basis does not
materially change cost. Live calls run sequentially, one prompt x one model per call — no batch
endpoint — so a large matrix or competitor live probing can take many minutes.

---

## Notes on parsing live responses (Track B)

`ai_optimization_llm_response` returns the model's answer text (and, when
`web_search: true`, cited sources). To classify a response:
- **mention**: regex/word-boundary match of the brand name (and obvious variants —
  spacing, legal suffix, common misspellings). Keep the variant rule consistent
  across brand and competitors.
- **citation**: brand domain appears in the answer body or in the returned source
  links (match the registrable domain, ignoring `www.`/subdomain and path). **Resolve
  redirect/grounding URLs first** — Gemini returns `vertexaisearch…/grounding-api-redirect/…`
  links rather than the target domain, so an unresolved match under-counts Gemini
  citations. Follow/parse the redirect to the real host; if unresolvable, flag Gemini's
  citation rate as under-measured rather than scoring it 0.
- **cited_sources**: capture every third-party domain/page the answer links, for the
  citation landscape.
- **prominence** (judgment call from the answer): the brand is the single lead
  recommendation = `Named first`; one of several named options = `Shortlist`;
  mentioned but not recommended = `Passing mention`; not present = `Absent`.

Keep the classification rules identical across brand and competitors so the
comparison is fair. Retry transient failures; a cell that still fails is
`not_measured` and is excluded from denominators — never scored as `Absent`.

**Where the results go.** Write each classified answer as ONE compact record to the
checkpoint `[brand-domain]_..._cells.json` (SKILL.md 6.1 / Appendix B) and discard the
full text. `scripts/aggregate.py` then computes every `sections` number from that
checkpoint — you never tally shares/rates/SoV/citation counts by hand. This keeps the
long answers off the token budget and makes the numbers reproducible.
