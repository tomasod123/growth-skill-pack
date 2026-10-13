# Subagent prompt: write concepts (one agent per lane of families)

Read `data/BRIEF.md` (offer, audience, claim whitelist and blacklist, rules) and these families from `data/families.json`: [F..].
Write [N] concepts per family. Every concept:
- names the reference ad it copies (`reference_ad_id`) and the family,
- is built around ONE reason to buy, with hook, image and CTA all agreeing,
- keeps `text_lines` at 3 or fewer unless the family needs more (say why), and some concepts carry no text at all,
- uses only whitelisted claims and numbers; if a number cannot be sourced, write the line without one,
- never contains a sourcing instruction ("find the real screenshot") in `image_plan`: set `needs_asset` to "real_photo" or "screenshot" instead,
- for a real logo, reserves an empty corner the CTA cannot reach and says which,
- follows the locale, no em dashes, no banned look.
Output schema: references/schemas.md. Write `work/concepts_[lane].json`.
