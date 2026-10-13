# Static ad brief: [business / offer] ([month year])

## Offer
What is being sold, price or price anchor, risk reversal, what the click leads to (lead form, booking page, demo request).

## Audience (ICP)
Who, in their own words. Role or situation, market (country), what they already tried. What they must NOT be (to keep lead quality up).

## Claim whitelist (the only numbers and claims allowed on an image)
| Claim | Exact wording allowed | Source (file, page, date) |
|---|---|---|

## Claim blacklist (never, in any form)
- Anything not in the whitelist.
- Guarantees, income or revenue promises, "permanent", "pain-free", clinical outcomes you cannot substantiate.
- Regulatory claims you cannot back with paperwork (clearances, "HIPAA compliant", "SOC 2") unless the attestation exists.
- Prescription-only medicine names in consumer ads (UK/IE/AU rules), before/after in AU cosmetic ads.
Also write each banned phrase as a regex in `data/claims_blacklist.txt` so qc_concepts.py enforces it.

## People who may appear
Named people cleared to appear or be named, with written consent on file. Nobody else. Background strangers are never cleared.

## Rules
- Text load: 3 or fewer text elements per image by default; some concepts carry none.
- Locale: [UK English | US English]; currency [£ | $ | €], never relabel another country's figure.
- No em dashes.
- No phone numbers, client signage or third-party branding in any image.
- Real logos are composited (logo_stamp.py), never rendered: reserve an empty corner the CTA cannot reach.
- Banned look: warm cream + serif + terracotta, pastel pill tags, floating rounded shadow cards, three-column icon grids, emoji, everything centred.
- Brand: [your colours and fonts, or "see ~/.claude/brand/tokens.css"].

## Output schema
See references/schemas.md (concept fields). One JSON list per lane: `work/concepts_<lane>.json`.
