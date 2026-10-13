# Live data mode: Meta + GoHighLevel join

Optional. Use it when you have API access and want the full funnel (bookings, qualified rate, speed to lead, conversations), not just what Ads Manager shows. Works for a recurring audit (for example Mon/Wed/Fri) via `scripts/run.sh`.

Run this as ONE Bash call (the env load only lasts for that call):
```bash
set -a; source ~/.claude/skills/.env; set +a; D=./meta-ads-analyst-output/$(date +%F); mkdir -p $D
python3 ~/.claude/skills/meta-ads-analyst/scripts/meta_pull.py --out $D/meta.json [--campaign <id>]
python3 ~/.claude/skills/meta-ads-analyst/scripts/ghl_pull.py --days 7 --out $D/ghl.json \
  --qualified-tag "<your qualified tag>" --unqualified-tag "<your unqualified tag>" --exclude-names "test,<team names>"
python3 ~/.claude/skills/meta-ads-analyst/scripts/funnel_math.py --meta $D/meta.json --ghl $D/ghl.json \
  --config ~/.claude/skills/meta-ads-analyst/config/analyst.json [--closes N --cash X]
```
Both pulls are GET only and never print tokens.

## What each pull gives you
**meta_pull.py** (Graph API, version from `META_GRAPH_VERSION`, default v21.0): the biggest-spending campaign of the last 30 days unless `--campaign` is given; last 7 and last 3 days of totals, per ad, placement, age, gender; `lead` and `onsite_conversion.lead_grouped` counted separately; any other campaign spending at the same time (contamination flag); per-ad quality / engagement / conversion rankings; device split; daily impressions per unit of spend for 14 days; the account activity log for 14 days.

**ghl_pull.py** (LeadConnector v2): pipeline stages and counts; appointments for every pipeline contact (bookings in the window, booking rate vs new opportunities); each recent lead's first-touch ad (`attributionSource.utmContent` = ad name, `adId`) and quality tag; speed to first outbound touch and first call; a few conversation threads to read.

## The join
Meta spend per ad joined to CRM leads by **utm_content = ad name**. That only works if every ad carries URL parameters like:
```
utm_source=facebook&utm_medium=paid&utm_campaign={{campaign.name}}&utm_content={{ad.name}}&utm_term={{adset.name}}
```
Instant-form leads synced into GHL also carry the ad id. If neither is present, the per-ad qualified table is empty: fix tracking first and say so in the report.

## Deep checks, every run
0. **Publish state first.** Read `activities_last_14d`. If the edits the team believes were made are not in the log, they never published (they can sit behind "Review and publish"). Say so at the top and stop treating that period as a test of those changes. `update_ad_set_target_spec` and `update_ad_set_budget` entries carry old and new values; count `update_ad_creative` events, since each can reset learning.
1. **Quality rankings.** `BELOW_AVERAGE_35` / `_20` / `_10` means the ad is in the bottom part of the auction, which raises CPM and cuts delivery. Cross-check with daily impressions per unit of spend: a steady fall against the first days confirms suppression.
2. **Placements: enabled vs delivering.** Report both. Enabled placements that never serve cost nothing; do not untick them to "save money".
3. **Device split.** iOS vs Android often differ a lot in B2B. Note it; act only after cleaner fixes (age floor, form qualifier) are in place, because device often proxies for something else.
4. **Targeting history.** For every campaign with real spend, list its age floor and other targeting next to its CPL and cost per customer. One table often settles an argument.
5. **Front-end cash vs contracted ROAS.** Contracted ROAS can look excellent while front-end cash ROAS is far below 1 because only a small deposit is collected. The cheapest money-layer fix is often the deposit or payment terms, not the ads.
6. **Decompose the working KPI.** cost per qualified booking ~ cost per qualified lead / booking rate, so you can see which lever to pull.
7. **Judge format on cost per customer**, not CPL.
8. **Throughput ladder** for the next budget levels (qualified leads/week, bookings/week, customers/month, concepts needed).
9. **Volatility is partly structural.** At low daily lead counts, zero days are expected; say so.

## GoHighLevel API gotchas
- Send a browser `User-Agent` header. The API sits behind Cloudflare and returns error 1010 to the default python-urllib agent. The script does this.
- On some Python installs SSL fails: `pip install certifi` and `export SSL_CERT_FILE=$(python3 -m certifi)`.
- Header `Version: 2021-07-28` is required.
- **Bookings live on the calendar, not the pipeline stage.** A booking often does not move the opportunity to a "Booked" stage unless a workflow does it. Read appointments per contact (`GET /contacts/{id}/appointments`); the location-wide events endpoint needs a calendar id per call. If stage counts and calendar counts disagree, report it as a workflow gap.
- Won/lost often lives in the stage name, with the `status` field left "open". Check both.
- Use `attributionSource` (first touch), not `lastAttributionSource`, which a booking page visit can overwrite for self-bookers.
- Calls are messages with `messageType == "TYPE_CALL"` and a nested `meta.call {duration, status}`; the top-level `type` can look like SMS, so a naive filter misses them. Automated workflow messages fire at lead creation and are not speed to lead: count human outbound touches and calls.
- Messages come back newest first; the script sorts them.
- The conversations search response can contain raw control characters; the script parses with `strict=False`.
- `monetaryValue` on opportunities is often a flat placeholder. Do not compute ROAS from it; ask for real deal values or first-payment cash.
- Exclude test contacts and your own team by name (`--exclude-names`).

## Meta API gotchas
- Count leads by `action_type == "lead"` exactly. `onsite_conversion.lead_grouped` is reported separately; summing substring matches double counts.
- Lead form answers need `leads_retrieval` and Page access; without them, get qualification from the CRM.
- Never report lifetime numbers for a campaign that had old bursts and long dark gaps; use the current window.
- If a second campaign is spending, account totals will not equal the target campaign; the pull flags this.
- Check the account currency in the pull; do not assume it.
- Signed image URLs from the API expire after some days; re-pull rather than reuse old thumbnails.
