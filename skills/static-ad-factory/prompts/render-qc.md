# Subagent prompts: QC every render (three agents in parallel)

Rules for all three: read images ONE AT A TIME, every image under 2000 px. Output `{variant, verdict: PASS|FIX, why, fix}` per image to `work/qc_<lens>.json`.

**(a) Text accuracy.** Compare every word on the image to the concept's `headline_on_image` and `other_text_on_image`. FIX on any misspelling, extra word, invented number, missing element, garbled logo, or text crowding an edge.

**(b) Claims and brand compliance.** Against `data/BRIEF.md`: only whitelisted claims; no phone numbers, signage or third-party brands; people only if cleared; a "client story" ad actually shows the client (not invented people); the founder never shown as a clinician; locale and currency right; no banned look; nothing that breaks Meta health / personal-attributes / unrealistic-outcome policies.

**(c) Scroll stop.** Would the target audience stop on this at phone size in one second? Is the reason to buy obvious? Does it look like an AI ad (plastic skin, warped hands, generic gradients)? FIX with one concrete change.

Re-render FIXes with an edited `image_plan` (assert the edit changed the concept), or route them to a human if the issue is a real asset.
