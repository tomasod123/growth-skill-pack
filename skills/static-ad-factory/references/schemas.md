# Data files and schemas

All paths are relative to the project folder (default `./static-ad-factory-output/<project>/`).

| File | Written by | Shape |
|---|---|---|
| `data/raw.json` | scrape_ads_library.py | list of Ads Library ads as the Apify actor returns them, plus `_country`, `_query` |
| `data/statics_unique.json` | dedupe.py | `[{ids[], page, title, body, days, variants, page_ads, cc[], active, lib, img}]` |
| `work/classify/labels_NN.json` | classify subagents (prompts/classify.md) | `[{id, is_target: bool, fit: 0..1, segment, why}]` |
| `work/tags_NN.json` | vision-tag subagents (prompts/vision-tag.md) | `[{id, layout, hook_type, icp_callout_text, headline_on_image, text_lines, text_density, style, colours, person, proof_element, cta_on_image, transferable_structure}]` |
| `data/ranked.json`, `data/textload.json` | merge_rank.py | scored rows; text elements vs days-running table |
| `data/families.json` | cluster agent (prompts/cluster-families.md) | `[{family_id: "F01", name, recipe, hook_pattern, n_ads, median_days, max_days, best_example_id, fit: high/medium/low, risks}]` |
| `data/BRIEF.md` | you + the owner (templates/BRIEF.example.md) | offer, audience, claim whitelist and blacklist, rules |
| `data/claims_blacklist.txt` | you | one regex per line of claims that must never appear |
| `data/concepts_final.json` | concept agents (prompts/write-concepts.md) + reason dedup (prompts/reason-dedup.md) | see below |
| `renders*/` | render.py | `<concept_id><variant>_<family_id>.png`, e.g. `A01a_F07.png` |
| `data/review_sheet.xlsx` | build_review_xlsx.py review | rows per variant with an Approve dropdown |
| `data/launch_order.json` | rank_approved.py | `[{rank, tier, variant, cid, score, painpoint, style, family, text_lines, headline, fb_headline, primary, why}]` |
| `work/ratios/<size>/` | make_ratios.py, make_story.py | `NN TIER PAINPOINT IDv - headline.png`, identical names across sizes |

## Concept fields
```json
{
  "concept_id": "A01",
  "family_id": "F07",
  "reference_ad_id": "<Ads Library id it is built from>",
  "reason_to_buy": "one short phrase, unique across the set",
  "painpoint": "short bucket used for diversity caps, e.g. TIME, COST, PROOF, RISK",
  "style": "photo | type-only | screenshot | person | diagram ...",
  "headline_on_image": "the main line, or null for a no-text ad",
  "other_text_on_image": ["at most a couple of extra elements"],
  "text_lines": 2,
  "image_plan": "art direction for the renderer, no sourcing instructions",
  "image_plan_vert": "optional, for tall frames (wider side column etc.)",
  "needs_asset": null,
  "person_panel": {"side": "right", "frac": 0.42},
  "primary_text": "Meta primary text",
  "fb_headline": "Meta headline, 40 characters or less",
  "why_this_should_work": "evidence from the scrape",
  "risk": "what could go wrong (compliance, claims, fit)"
}
```
`needs_asset`: `null` (fully generated), `"person_photo"` (AI likeness from reference photos via render.py --ref), `"real_photo"` / `"screenshot"` (a human supplies the real asset; do not render).
