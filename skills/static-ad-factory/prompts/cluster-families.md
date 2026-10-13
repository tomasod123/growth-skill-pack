# Agent prompt: cluster into structure families (one strong model)

Read `data/ranked.json` (scores, days running, tags). Group the ads into 60-80 STRUCTURE FAMILIES, not a dozen.
Two ads share a family only if a designer would build them the same way (layout, hierarchy, type treatment, image role).
For each family output {family_id "F01"..., name, recipe (a build instruction a designer or image model can follow),
hook_pattern, n_ads, median_days, max_days, best_example_id, fit (high/medium/low for our audience and offer), risks}.
Write `data/families.json`. Note families that only work with assets we do not have (real screenshots, client photos).
