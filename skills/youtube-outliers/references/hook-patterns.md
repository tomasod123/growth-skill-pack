# Hook and title patterns: how to read an outlier

Use this after `find_outliers.py` has written `report.md` and `transcripts/`.

## The score
- **raw_ratio** = this video's views / the channel's median views over its recent uploads (the video itself excluded). Median, not mean, so one old viral hit doesn't hide every new outlier.
- **outlier_score** = raw_ratio x recency boost (1 day old x2.0, 3 days x1.5, 7 days x1.2). New videos haven't had time to collect views.
- **score** (adjacent mode only) = outlier_score x format penalty (x0.3 for formats that rarely transfer: setups, vlogs, reactions, news) x hook bonuses (money x1.4, curiosity x1.3, transformation x1.25, contrarian x1.25, speed x1.2, urgency x1.15, a number x1.1). These weights are starting points; tune them in the script for your market.
- A channel needs at least 3 other recent uploads to get a baseline; otherwise the video is skipped.

## Own niche vs adjacent niche
| | Own niche (`--mode own`) | Adjacent niche (`--mode adjacent`) |
|---|---|---|
| Question | What is my market watching right now? | Which packaging works on any audience? |
| Keywords | your topics, your buyers' words | broad business, sales, marketing, money, productivity |
| Channels | direct competitors, creators your buyers follow | big general channels |
| Filter | none beyond noise | titles with your own niche terms are dropped |
| Use it for | topics, angles, objections to answer | hooks, title structures, thumbnail ideas |
| Cadence | weekly | monthly |

## What to pull from each top outlier
1. **Title formula.** Rewrite the title with the topic blanked out: "Why most [group] waste [money] on [thing]". Note the number, the enemy, the promise.
2. **Hook (first 30 seconds of the transcript).** What is promised, what tension is opened, how fast the topic lands.
3. **Structure.** List the sections in order. Note where the payoff lands and where a second open loop starts.
4. **Why it beat the channel's normal.** One sentence. Topic timing, a named enemy, a specific number, a contrarian claim, a format shift.
5. **Adaptation.** One title and one hook for your niche that keep the trigger and change the topic. Only claims you can back up.

## Pattern table to hand back
| # | Original title | Formula | Hook type | Why it worked | Our title | Our first line |
|---|---|---|---|---|---|---|

## Keyword tiers for adjacent mode
- Tier 1, close to your buyers: "grow a clinic", "practice management tips", "healthcare marketing", "SaaS sales", "B2B demand generation".
- Tier 2, broad business: "how to scale a business", "founder productivity", "hiring your first salesperson".
- Tier 3, money hooks: "increase revenue", "pricing strategy", "high ticket sales".

## Health and medical claims
Titles that overperform often promise outcomes. In health, outcome claims, before/afters and testimonials are restricted (Meta health policies, UK ASA/CAP, Australian AHPRA, US FTC). Keep the structure, drop the claim you can't substantiate.
