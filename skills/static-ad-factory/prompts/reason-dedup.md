# Agent prompt: reason-to-buy dedup (do not skip)

Read every `work/concepts_*.json`. Meta's public Andromeda guidance is to supply creatively diverse ads, and near-identical ads compete for the same people, so diversity here means a different REASON TO BUY, not a different layout.
1. Assign each concept `reason_to_buy` (short phrase) and `painpoint` (bucket) and a psychological trigger.
2. Produce the reason inventory: reason -> concept ids.
3. Flag redundancy: concepts that share a reason and differ only in wording or layout.
4. List reasons to buy that are MISSING (from the brief, customer language, competitor ads).
5. For each redundant concept, propose a repoint to a missing reason (new hook + image plan), keeping the family.
Write `data/reason_audit.json` and then the merged, repointed set to `data/concepts_final.json`. Target: as many distinct reasons as the budget can feed.
