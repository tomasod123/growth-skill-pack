# Creative diversification after Andromeda

What Meta says publicly (Meta Engineering, "Meta Andromeda: Supercharging Advantage+ automation with the next-gen personalized ads retrieval engine", engineering.fb.com, December 2024; Meta Business Help Center pages on Advantage+ creative and the learning phase): Andromeda is the retrieval stage that narrows every eligible ad down to a short list for ranking, it can now consider far more ads per person and personalise better, and Meta recommends giving the system a broad range of creatively diverse ads. Everything after this paragraph is a working method, not Meta's wording.

## What it means in practice
- Different messages tend to reach different people, so the creative does much of the targeting.
- Ads that look and say nearly the same thing compete for the same people. Count them as one concept.
- A spread of genuinely different concepts gives retrieval more to work with than many variants of one.
- In a consolidated ad set a few ads taking most of the spend is normal.

## How to count concepts
Count distinct **ideas**, not files. An ad is a new concept when it gives a different reason to buy, speaks to a different problem or audience, or tells it in a clearly different way (for example a different format or a different person on camera).

Not new concepts: new crops or ratios (9:16, 4:5, 1:1), a new colour, a reworded hook on the same body, the same video with a different thumbnail. Hooks are still worth testing; just count a hook batch on one body as one concept unless the message changes.

Set your floor for distinct concepts live per ad set in `config/analyst.json` (`min_distinct_concepts_live`). The right number scales with budget: more budget can feed more concepts with enough data each.

## Building the concept list
1. Write down every reason someone would buy (outcome, fear, status, speed, cost, risk removal, identity, convenience, compliance, "my competitor already has it").
2. Group the near-duplicates. Each group is one concept.
3. For each concept, write hook, body and CTA around that one reason so the whole ad agrees with itself. Do not bolt one generic body onto many hooks.
4. Choose a format and a person for each, and vary them across the list.
5. Write a small shared set of headlines and primary texts if you use dynamic / multiple text options; the differentiation lives in the creative.

Example reasons for a clinical software product: saves clinician time per patient, cuts no-shows, passes the security review, fits the existing EHR, a peer clinic's result, avoids a compliance fine, staff stop hating the old tool. For a local clinic: a priced first consult, a specific worry addressed, the clinician's credibility, the before-the-visit experience, finance options, a nearby location, a seasonal reason.

## Testing and refresh
- New concepts can be tested in a separate testing campaign so the proven campaign is not disturbed; graduate winners into the main campaign. Alternatively add a few new concepts at a time to the main ad set. Pick one method and be consistent.
- Refresh when frequency rises and cost per result climbs together, or quality ranking drops. Replace the ads that get no spend with new concepts; keep the winners running.
- Do not clone a winning hook into many more ads: it crowds the same audience pocket. Find new reasons instead.
- Make the landing page or form match whichever ad is taking most of the spend.
- Feed server-side signal (Conversions API, good event match quality) so learning finishes faster.

## Hook / body / CTA review
- Hook (first 1-3 s): the problem or the offer lands before second 2; a person on camera with one clear on-screen line is a reliable shape.
- Body: one concrete promise the viewer can picture; captions on.
- CTA: what they get, what to tap, why now (without fake scarcity).
- Hook rate and hold rate are signals, not goals. A strong hook that brings the wrong people is a worse ad.

## A prompt you can use to generate concept ideas
```
You are a direct response copywriter for [BUSINESS / CATEGORY].
Audience: [WHO, including role or situation]. Offer: [OFFER, PRICE, RISK REVERSAL].
List as many distinct reasons as you can for this audience to act now. Group near-duplicates.
For the most different groups, write one ad concept each: hook (spoken + on-screen line),
body (3-5 sentences, one promise), CTA, suggested format and person.
No guarantees, no income claims, no fake scarcity, no claims we cannot substantiate.
```
