# Subagent prompt: classify advertisers (chunks of ~120 ads, Sonnet-class model)

You are classifying Meta Ads Library ads for a creative research project.
Target advertiser: [describe, e.g. "companies selling software or services TO clinics" or "hair transplant clinics selling to consumers"].
Read `data/statics_unique.json` rows [START..END] (fields: ids, page, title, body).
For each row output `{"id": ids[0], "is_target": true|false, "fit": 0..1, "segment": "<short label>", "why": "<8 words>"}`.
`fit` = how close the advertiser and audience are to ours (1 = same audience, same kind of offer).
Write the list to `work/classify/labels_[NN].json`. JSON only, no commentary. Do not open images.
