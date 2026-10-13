---
name: gads-audit
description: End-to-end, read-only Google Ads setup-and-audit agent for any account (your own business or a client's). Account audit (serving status, impression share lost to rank vs budget, bids vs market, negatives in all three layers, conversion counting, ad schedule, geo, quality score), keyword research and market sizing via DataForSEO, landing page audit (mobile fold, overflow, speed, message match against the live ad copy), a multi-pass competitor SERP check, then an action spreadsheet, a draft email to whoever runs the account and an internal summary page. Never changes an account. Use on "google ads audit", "audit the ads", "ppc audit", "keyword research for <account>", "why isn't the campaign spending", "why no impressions", "is the landing page the problem", "who else is bidding on this", "what should the PPC manager change", "plan a new Google Ads campaign".
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./gads-audit-output/`.

# gads-audit

**Read-only.** Every script only searches. Nothing here mutates a Google Ads account, and nothing
is sent to anyone: the email is a draft and the summary page is internal. Changes go in the
spreadsheet and the email for a human to make.

Depends on the **gads-common** skill (installed beside this one: `../gads-common/scripts/gads.py`)
for Google Ads access, and on DataForSEO for modules 2 and 4. If a Google Ads pull fails, run
`set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/gads-common/scripts/gads.py doctor` first.

## Before anything

```bash
set -a; source ~/.claude/skills/.env; set +a
```
Each Bash call is a fresh shell: this line goes at the top of EVERY Bash call that runs a
script, together with the `S=` / `W=` lines below.

Ask the user for (or read from their notes): the customer id, the landing page the ads are
supposed to point at, the places the business says matter, what the live page sells (core
terms), any other service lines (adjacent terms), the country, and the account currency.

## The answer first, every time

**Read `search_rank_lost_impression_share` against `search_budget_lost_impression_share` before
anything else.** Those two numbers decide whether the problem is bids or money, and they need
opposite fixes. Get this backwards and you spend a month raising a budget that was never the
constraint. A typical young campaign: almost nothing lost to budget, most impressions lost to
rank, and a generous daily budget that has barely spent. More budget fixes none of that.

## Run order (about 25 minutes of wall clock, most of it waiting)

```bash
set -a; source ~/.claude/skills/.env; set +a
S=~/.claude/skills/gads-audit/scripts
W=./gads-audit-output/<account-slug>-$(date +%Y%m%d)
mkdir -p "$W"
export DFS_LEDGER="$W/dfs-cost-ledger.jsonl" DFS_RUN_ID=<account-slug>-audit

# 1. account audit, about 20 seconds, free
python3 $S/audit_account.py <CUSTOMER_ID> --days 30 --out "$W" \
  --expect-url "<the agreed landing page>" \
  --priority-geo "<places the business has SAID matter>"

# 2. keyword research and market size, about 1 minute, roughly US$0.10-0.60
python3 $S/keyword_research.py --out "$W" \
  --seeds "<8-12 real anchors, not synonyms>" --location US --limit 1000 \
  --geo "<the business's towns>" --core "<what the live page sells>" \
  --adjacent "<other service lines>" --controls "<two terms you KNOW have volume>" --fx 1.0

# 3. re-run the audit so the market bid feeds the bid findings
python3 $S/audit_account.py <CUSTOMER_ID> --days 30 --out "$W" \
  --expect-url "<page>" --priority-geo "<places>" --keywords-json "$W/keywords.json"

# 4. landing page, about 1 minute, free (needs Chrome + Node 22+)
python3 $S/landing_page.py --audit-json "$W/account-audit.json" --out "$W" \
  --widths 320,360,390,430,1280 --thankyou "<thank-you page>"

# 5. competitors: 2-3 passes at DIFFERENT hours inside the business's hours, then merge
python3 $S/competitors.py --out "$W" --location US \
  --keywords "<5 core terms>" --device mobile --label "10:00 Thu local"
#   ... later the same day ...
python3 $S/competitors.py --out "$W" --location US \
  --keywords "<same 5>" --device mobile --label "16:00 Thu local"
python3 $S/competitors.py --merge "$W" --client-domain <the business's domain>

# 6. outputs
python3 $S/build_outputs.py --dir "$W" --client <slug> --client-name "<Name>" \
  --contractor "<who runs the account>" --sender "<your name>" [--supabase]
```

`--fx` is USD per 1 unit of the account currency (1.0 for USD accounts; about 0.66 for AUD in
2026). Set `GADS_AUDIT_OWNER` (default "PPC manager") to the name that should appear in the
"who" column, or pass `--contractor`.

### Planning a NEW account or campaign (no live data yet)

Skip modules 1 and 3. Run module 2 to size the market, pick core terms and build the negative
list before launch; module 4 to see the organic picture; module 4 on the page you plan to use.
Then build the campaign by hand against the "Do not" list below, and run the full audit after a
couple of weeks of serving.

## Diagnostic decision tree

1. **Is it serving?** `campaign.primary_status` plus `primary_status_reasons`. Anything other than
   ELIGIBLE / LIMITED / LEARNING, stop and clear those reasons. Nothing else matters.
2. **Has it ever spent?** Life-of-campaign spend, not the window. A serving campaign with zero
   lifetime spend is a bid problem, an approval problem or a conversion-tracking illusion, never a
   budget problem.
3. **Lost to rank or lost to budget?**
   - rank high, budget ~0: **bids and quality.** Raise bids toward the market top-of-page bid, or
     move to a conversion-led strategy, and fix ad-to-keyword relevance. Raising budget does nothing.
   - budget high: **money.** Raise the daily budget, or cut the terms eating it.
   - both null: no auction history yet. Say "no data", never "0%".
4. **Can it even be reached?** Module 2's core monthly searches. If (searches/30) x CTR x CPC is
   well under the daily budget, the budget was never the constraint and never will be.
5. **Are negatives in place?** All three layers (below). Zero intent negatives is critical, and it
   must be fixed BEFORE any bid or budget rise, or the extra money buys job-seeker clicks.
6. **Is a conversion being counted correctly?** A primary action must exist, and lead actions count
   ONE_PER_CLICK, not MANY.
7. **Does the page carry the ad's promise, on a phone?** Module 3.
8. **What does Google itself think of the page?** `post_click_quality_score`. That is the
   authoritative verdict because Ad Rank uses it, but it is NULL until the keyword has impressions,
   which is exactly why the measured numbers matter on a young campaign.

### Negatives have three layers, and checking one is how you get this wrong

A first pass that reads only campaign-level negatives will happily report "0 negative keywords"
while a shared list of well-chosen intent negatives is attached to the campaign. That wrong finding
then lands in an email accusing someone of not doing their job. Check all three:

| Layer | GAQL |
|---|---|
| Campaign level | `campaign_criterion` where `negative = true` |
| Ad group level | `ad_group_criterion` where `negative = true` |
| Shared lists | `campaign_shared_set` for what is ATTACHED, then `shared_criterion` for the members |

And distinguish Google's **auto-created brand-safety lists** (Adult, Terrorism, Download, Covid
and similar) from real intent lists. An attached brand-safety list is not an intent negative, and
the script counts them separately (`--brandsafety` adds more names).

## Mandatory QC before anything leaves the building

A first draft contractor email from this kind of audit can easily carry a dozen factual errors,
some stating the opposite of what the account shows, none of which the audit itself catches. Run
all four lenses in parallel (subagents work well), on the DRAFT, before a human sees it. They
disagree with each other, which is the point. If you have the **persona-qc** skill, use it for
the persona lens.

| Lens | Brief | What it catches that nothing else does |
|---|---|---|
| Claim-by-claim fact-check | Re-query EVERY number in the draft against the API. Report the figure you measured, never "approximately" | Counts out by several times, reversed conclusions |
| Kill-our-own-theory | Give it the conclusion and tell it to destroy it | A plausible theory that does not survive the data |
| Contractor persona | Read the draft as the person who runs the account, on a phone, tired, reputation in mind. Ask for a drift log and a relationship-risk score | A 30-day figure compared against a 7-day one; arguments that contradict each other two items apart |
| Page/Sheet consistency | Check every figure matches across all artefacts, and hunt nulls reported as zeros | Impression-share sentinels printed as hard percentages |

**The two reversals to fear**, because they survive a spelling check and a tone check:
1. "Conversions are inflated by repeat-counting actions." Often false. `primary_for_goal` and
   `include_in_conversions_metric` are **legacy account-level** fields. A Performance Max campaign
   can carry its own campaign-level conversion goals, so those flags do NOT describe what the
   campaign counts or bids to. **Always segment by `segments.conversion_action_name` to see which
   actions actually produced the conversions.**
2. "The ad copy is clean." Checking `ad_group_ad` only covers Search ads. **Performance Max copy
   lives in `asset_group_asset`.** Check there too before saying a regulated or banned term is absent.

## Traps this skill has already fallen into. Do not repeat them.

- **Bid-vs-market only means something on MANUAL_CPC, non-brand, not budget-capped.** Under smart
  bidding the keyword bid is ignored (a leftover 0.01 bid is meaningless). Brand terms are cheap by
  nature, so never compare them with the price of generic terms. And on a campaign losing lots of
  impressions to BUDGET, bidding up buys fewer clicks with the same money. All three gates are in
  `judge()`. Capped impression share prints as ">90%" / "<10%" via `isp()`.
- **Count records, not lines.** Counting non-empty lines of JSON output inflates a negatives count
  several times over. Parse with `json.loads` and `len()` the list.
- **Impression share has sentinels.** Google returns `0.0999` for "less than 10%" and `0.9001` for
  "more than 90%". Printing them as 10% and 90% overstates the figure and makes the three columns
  sum past 100%, which is the tell.
- **`DURING LAST_30_DAYS` silently returns nothing on `change_event`.** Use `LAST_14_DAYS`.
  Selecting `change_event.campaign` throws a 400. Change history does not expose ad text, so it
  cannot tell you when a typo arrived.
- **Negative location criteria look like targets.** Filter on `campaign_criterion.negative`, or an
  excluded region gets reported as targeted.
- **"Still shows N targets in the old geo" proves nothing.** New locations sit ALONGSIDE existing
  ones. State the total count and the absence of the specific new ones.
- **Check the campaign status before describing anything as live.** Disapproved ads, bad negatives
  and whole keyword classes often sit inside PAUSED campaigns. An enabled ad in a paused campaign
  serves nothing.
- **Compare like with like.** A campaign launched 7 days ago against one running 30 days is not a
  result. Use complete days only; today's row is still moving.
- **Do not use a blind metric as evidence.** If the account records no conversions at all, you
  cannot cite zero conversions as proof a page does not convert. Go to the CRM and say that is
  where the number came from.
- **Read a shared negative list before recommending it.** A list named after a service can hold a
  thousand members, none of them that word, plus a bare broad `free` that blocks "free consultation".
- **Landing page experience is scored PER KEYWORD.** If the same page scores AVERAGE on some
  keywords and BELOW_AVERAGE on others, no page-level property (speed, schema, word count) can be
  the explanation.
- **Measure speed from the customer's country.** A test from another continent can rank hosting
  options backwards. Use a probe service such as Globalping with its location set to the
  business's city.
- **`metrics.speed_score` is absent for most accounts.** Never present your own stopwatch as
  Google's judgement.
- **Quality score components are not equal.** Expected CTR usually moves the score more than the
  landing page component. Check which component is actually capping the score before blaming the page.
- **Check whether the ads were changed in the last fortnight** before reading any quality score.
  Scores lag.

## Deliverable rules

- The actions spreadsheet carries a **"Done when"** acceptance test per row and a **Status
  dropdown** when you build a shared tracker, so completion is not a matter of opinion. openpyxl
  `DataValidation(type="list")` survives an xlsx to Google Sheets import. **Options must not
  contain commas**: the list formula is comma separated.
- An xlsx sitting in Google Drive is not a Google Sheet. Import it (File > Import, or upload with
  "Convert uploads" on) if anyone needs to edit it as a Sheet.
- **Number the actions sequentially after sorting.** A list that jumps 8, 7.5, 9, 3.5 is not a
  ranked list.
- The contractor email is **action-first**: every item opens with the imperative. Aim for about
  1,400 words, not 2,000+, because it will be read on a phone.
- **Say what you got wrong.** Corrections stated plainly at the top buy more credibility than the
  correct findings underneath.
- **Give the hours.** Eight to ten hours of work with a two-day deadline reads as urgent however
  the opening sentence is worded. Ask for their date instead.
- **Own what is yours.** Separate the items that are yours (web team, tracking) from the PPC
  manager's, explicitly.

## Findings catalogue

Severity drives the order. `critical` means stop and fix before spending more.

| Code | Sev | What it means | Do this |
|---|---|---|---|
| NO_LIVE_CAMPAIGN | critical | No ENABLED campaign | Confirm with the business it is deliberate |
| CAMPAIGN_NOT_SERVING | critical | primary_status is not eligible | Clear every primary_status_reason in order |
| SERVING_NO_SPEND | critical | Eligible and serving but has never spent a cent | Read rank vs budget. Nearly always bids, never budget |
| NO_DELIVERY_IN_WINDOW | critical | Zero impressions in the window | Serving status, bids, and whether the ad schedule excluded the window |
| LOST_IS_RANK | critical | 50%+ of impressions lost to Ad Rank | Bids toward the market top-of-page bid, fix relevance. Do NOT raise budget |
| LOST_IS_RANK_MODERATE | warning | 25-50% lost to rank | Bid up on the converting terms only |
| LOST_IS_BUDGET | warning | 20%+ lost to budget | This one IS money: raise the budget or cut the terms eating it |
| NO_IMPRESSION_SHARE_DATA | info | Google has no auction history yet | Re-run after a few serving days. Report "no data", not 0% |
| MANUAL_CPC | warning (info over 15 conversions) | Manual CPC with little conversion history | Manual only while calibrating, at or above market bid. Then Maximise clicks capped, then Maximise conversions once conversion volume is steady (Google suggests roughly 15-30 conversions in 30 days) |
| BID_BELOW_MARKET | critical under 60% of market, else warning | Median keyword bid below the market top-of-page bid | Take bids to the market figure, or let smart bidding price them |
| BID_BELOW_MARKET_BUDGET_CAPPED | warning | Bid below market BUT 20%+ of impressions already lost to budget | Do not bid up: same money, fewer clicks. Fix landing page/tracking, then budget, then bids |
| ZERO_NEGATIVES | critical | No intent negatives in ANY of the three layers | Add module 2's negative set BEFORE any bid or budget rise |
| NEGATIVES_THIN | warning | Fewer than 15 intent negatives | Extend from this run's candidates |
| NEGATIVES_PRESENT | info | Intent negatives found, counted per layer | Re-check against this run's candidates for gaps |
| NEGATIVE_BLOCKS_PRIORITY_GEO | critical | A negative keyword blocks a place the business named a priority | Remove it, or get written confirmation it is deliberate |
| AD_DISAPPROVED | critical | Ad not approved | Read the policy reason and rewrite; it serves nothing |
| AD_APPROVED_LIMITED | warning | Approved with limits | Find which policy limited it; limited ads lose most eligible traffic |
| NO_ENABLED_ADS | critical | No enabled ads | Nothing can serve |
| AD_FINAL_URL_DRIFT | critical | Live ads point somewhere other than the agreed page | Repoint, or agree the new page and re-audit it |
| MULTIPLE_FINAL_URLS | info | Live ads span several pages | Fine if deliberate, one page per ad group |
| NO_CONVERSION_ACTIONS | critical | Nothing is measured | Build the lead and call conversions before spending more |
| CONV_NO_PRIMARY | critical | No primary_for_goal action | Smart bidding has nothing to aim at |
| CONV_COUNTING_MANY | warning | A lead action counts MANY_PER_CLICK | Set it to One. Three submissions by one person read as three leads and misprice every bid built on them |
| CONV_ORIGIN_GA4_IMPORT | info | Action imported from Analytics | GA4 imports lag and can double-count beside a website tag. One source per action |
| CONV_DUPLICATE_NAMES | warning | Two counted actions with one name | Pause the duplicate |
| CLICKS_NO_CONVERSIONS | critical | 50+ clicks, zero conversions | Test the form end to end before touching bids |
| AD_SCHEDULE_THIN | warning | Under 42 of 168 hours (25% of the week) | Widen to evenings and weekends unless the business has said those enquiries are worthless |
| AD_SCHEDULE_PARTIAL | info | 42-120 hours | Check the excluded hours against when enquiries actually arrive |
| NO_LOCATION_TARGET | critical | No geo targeting | Add the real service areas |
| MANY_SMALL_GEOS | info | 5+ location targets | Keep the geo targets. Suburb-level KEYWORDS are the problem, not suburb-level targets |
| DEVICE_NO_MODIFIERS / NO_DEVICE_CRITERIA | info | No device bid modifiers | Leave until there is device-level conversion data |
| BUDGET_SHARED | info | Shared budget | Another campaign can eat this one's money |
| AUTOTAGGING_OFF | warning | No gclid appended | The CRM (e.g. GoHighLevel) cannot attribute a lead to a click |
| QS_NO_DATA | info | No quality score on any keyword | NULL until impressions exist. Say "no data yet", never a score of 0 |
| QS_AVERAGE | info at 6+, else warning | Average quality score | Under 6: fix relevance and the page before bidding up, since Ad Rank multiplies bid by quality |
| QS_LANDING_PAGE_BELOW_AVERAGE | critical | Google rates the landing page below average | This is Google's own verdict. Fix message match and speed, then re-check |
| QS_PREDICTED_CTR_BELOW_AVERAGE | warning | Expected CTR below average | Rewrite headlines to carry the keyword and the offer |
| KEYWORDS_NO_IMPRESSIONS | warning | Half or more keywords got nothing | Either bids under the floor or no search volume. Module 2 says which |
| BROAD_MATCH_IN_USE | warning | Broad match keywords present | Needs a full negative list and weekly search-term review. Confirm the business wants it |
| SEARCH_TERM_WASTE | warning | Terms that spent with no conversion | Negative the irrelevant ones only |

The thresholds above live in `audit_account.py` (`judge()`); change them there if your accounts
need different lines.

## Module 2: market sizing and the budget ceiling

Max absorbable daily spend is roughly **(monthly searches / 30) x CTR x CPC**. Past that, money has
nowhere to go. A niche local service with a few hundred core searches a month and a mid-single-digit
CPC can only absorb single digits a day, so a three-figure daily budget was never the constraint
and "spend more" was never the answer.

Report CORE and ADJACENT separately. Adjacent demand is real but belongs to a different service
line, and spending into it without a page for it reproduces the same intent-to-page mismatch.

Gotchas the script encodes:
- `dataforseo_labs/google/keyword_suggestions/live` is phrase-locked. `keyword_ideas` is not, and
  its semantic expansion drifts off-niche badly.
- The Labs path matters: `keywords_data/google_ads/keyword_suggestions/live` returns **40400 Not
  Found at $0 cost**, which reads exactly like an empty market.
- **Every CPC and bid is USD** whatever the location_code. Pass `--fx` (USD per 1 unit of the
  account currency) and label the converted column as indicative.
- Always pass `--controls` with two terms you know have volume. They go out in the same
  `search_volume` call, so a null is provable rather than assumed: if the controls return volume
  and your niche terms return nothing, that is a real finding about the channel, not an API fault.
- Location codes: AU 2036, UK/GB 2826, CA 2124, US 2840, IE 2372, NZ 2554.
- Classification is word-boundary matched. End a token with `*` for a prefix match
  (`transplant*`). Without boundaries "land" fires inside "queensland" and "sil" inside "silence",
  which is how a clean negative list ends up with nonsense in it. Add niche-specific job-board or
  marketplace names with `--negatives-extra`.

### Caveat: the absorbable-spend ceiling does not bound a Performance Max campaign

The ceiling is a **Search** calculation. A live Performance Max campaign can be losing most of its
impressions to budget while the keyword ceiling says a few dollars a day: both are true, because
PMax buys Search, Discover, YouTube and more. **Only quote the ceiling against Search campaigns.**

## Module 3: landing page

Local Chrome rules, all enforced in the script and none of them optional:
`--mute-audio` and gated autoplay (an unmuted render plays every page video through the real
speakers), its **own** `--user-data-dir` in a temp folder (a default-profile launch signs you out
of every Google account), poll `/json/version` instead of sleeping, a **fresh tab per width**
(`Emulation.setDeviceMetricsOverride` leaks between runs and a leaked override turns a real
overflow into a clean pass), cache disabled and localStorage cleared per run, and kill Chrome by
pid, never a `pkill` pattern that would match its own shell.

It renders 320/360/390/430/1280 and reports: whether `innerWidth` really equals the device width,
horizontal overflow, whether the first form field AND the submit button clear the fold, embedded
GoHighLevel form iframes that run past the fold, the redirect chain, HTTP status, page weight, lab
timings, and **message match against the live ad headlines pulled from module 1**. With
`--psi-key` (or `PSI_API_KEY`) it adds PageSpeed field and lab data.

Never hand anyone a single PageSpeed score: identical pages swing by tens of points between runs.
Quote page weight and field timings. Google's `post_click_quality_score` outranks every number
this module measures, when it exists.

Module 3 traps, all the same shape (reporting what it could not see as a defect on the site):
- **A 403 is a bot challenge, not an outage.** Sites behind Cloudflare and similar return 401/403/429
  to headless browsers. The script reports these as a bot block, sets `page["blocked"]`, and warns
  that every other measurement on that page is unreliable.
- **Never score message match against a page that did not render.** Message match is skipped when
  the page is blocked or returns under 40 words, and says so.
- **The URL and promise lists come from ALL ads, including paused ones.** Check a bad URL is in an
  enabled campaign AND an enabled ad group or asset group before calling it urgent. PMax URLs live
  in `asset_group`, not `ad_group_ad`.
- **A page can lay out WIDER than the viewport with zero overflow** (e.g. 372px inside a 320px
  viewport). Overflow alone does not catch this; the script compares the laid-out width against the
  emulated width. It is usually a missing or wrong viewport meta or a min-width element, and phones
  respond by zooming out to unreadable text.

What it gets genuinely right, and is worth running for: pages that show **no visible form at all**
on a phone (the real reason hundreds of paid clicks produce zero enquiries), forms that begin far
below an 844px fold, and ads that promise a phrase ("Free Consultation", the full service name)
that the page never says, only an abbreviation of.

## Module 4: competitors. Read this before running it.

**The paid side is unreliable.** DataForSEO's organic SERP endpoint has been seen returning ZERO
paid listings for whole country/device combinations, even on control terms that certainly carry ads
("car insurance", "hotels <city>").

So: **never tell anyone who is or is not bidding on the strength of this module.** Fifty queries of
"nobody is advertising against you" is an instrument failure, not a market finding, and it is the
kind of claim that gets repeated to a client and then falls over.

Before ever reporting a paid finding from this module, run a **control query** on a term you know
carries ads in that country and device. If the control returns zero paid listings, the paid half of
the module is dead for that configuration and only the organic half is usable.

What the module IS good for: the organic picture. If the business already ranks #1 organically for
a term, that is worth knowing before paying for those clicks. `rank_group` is the organic position;
`rank_absolute` counts ads and SERP features and differs by 5-8 places. Never mix them.

To actually answer "who is bidding", use the Auction Insights report in the Google Ads UI, or the
account's own `auction_insight` data.

A single SERP pull is **not evidence** of anything. Advertisers daypart, budgets exhaust, and the
auction is stochastic. `--merge` refuses to drop the warning until there are 2+ passes, and reports
each advertiser as "seen in N of M passes". Labs `ranked_keywords` is an organic dataset: an empty
paid result from it means nothing.

## Impression share figures MATURE. Timestamp them, and re-pull before quoting.

The same `LAST_7_DAYS` window can return a very different lost-to-rank figure a few hours apart:
Google recalculates impression share as the day's data settles, and a tiny denominator makes it
swing hard.

- Always print the pull time next to any impression share number.
- **Re-pull immediately before the figure goes into an email, a sheet or a client page.** Someone
  who opens the account and sees 79% when the email said 90% will doubt the whole audit.
- Below roughly 100 impressions, quote the DIRECTION ("almost all of it lost to rank, none to
  budget") rather than the decimal. The direction is stable; the decimal is not.
- Check several windows (TODAY, YESTERDAY, LAST_7/14/30_DAYS). Pick one, name it in the output, and
  stick to it.

## API gotchas

- **API v25 renamed `campaign.start_date` and `campaign.end_date` to `campaign.start_date_time` /
  `campaign.end_date_time`** (value like `2026-09-15 23:47:06`). The old names return
  UNRECOGNIZED_FIELD and kill the whole query. Check the field reference for your version;
  `google_ads_field` is not queryable through `googleAds:search`.
- Location targets come back as `geoTargetConstants/<id>`. Resolve them with
  `SELECT geo_target_constant.name, geo_target_constant.canonical_name FROM geo_target_constant
  WHERE geo_target_constant.id IN (...)`, or a geo-coverage check compares a town name against an
  integer and fires a false "not targeted".
- The REST API **omits false, zero and default fields**, so a missing `primaryForGoal` means NOT
  primary and a missing `qualityInfo` means no data yet. Spell every boolean out with `bool(...)`.
- **Quality Score is null until a keyword has impressions.** Report "no data yet" and say why. Do
  not tell anyone their landing page experience is bad when Google has not scored it.
- **A JS template literal eats `\s`.** The CDP page-measuring expression lives inside a backtick
  string, where `\s` collapses to a bare `s`, so `/\s+/g` silently becomes `/s+/g` and strips every
  letter s out of the page text, breaking every message-match score. Write `\\s`.
- Collect positional URLs by checking that the previous argv item is not a flag, or
  `--thankyou <url>` gets audited as if it were the landing page.
- PostgREST (Supabase) rejects a batch whose objects have different keys with PGRST102 "All object
  keys must match": the optional upsert normalises every row to the union of keys first.

## Do not

- Do not raise a budget on a campaign losing impressions to rank. It buys nothing.
- Do not recommend broad match without the business's agreement, and never without a full negative
  list plus a weekly search-term review.
- Do not add keywords for demand nobody has measured. Check volume first, and say "no volume
  returned" rather than "no demand": the keyword tool is not the whole of Google.
- Do not pause a keyword on "no volume" alone when it has never had a bid high enough to serve.
  Mark it "check first".
- Do not quote a competitor as bidding, or not bidding, on a term from one SERP pull.
- Do not report a null impression share, quality score or landing-page score as a zero.
- Do not state any figure in client copy that was not computed in this session, and never round money.
- Do not treat an attached shared negative list as intent negatives until you have read its members.
- Do not send the contractor email, the spreadsheet or the summary to anyone without the user's
  explicit approval. This skill only ever stages.
- Do not mutate anything in Google Ads. If a change is needed it goes in the spreadsheet and the
  email for a human to make.
- Healthcare accounts: Google restricts some medical terms and claims (prescription drugs,
  unproven treatments, before/after claims) and some regions regulate health advertising (e.g. the
  UK CAP Code). Flag regulated wording in ads and pages for a human to check; do not rule on it.

## Outputs (all in the work folder, default `./gads-audit-output/<slug>-<date>/`)

| File | What it is |
|---|---|
| `account-audit.json`, `ACCOUNT-AUDIT.md` | Module 1: campaigns, three-layer negatives, findings table |
| `keywords.json`, `KEYWORDS.md` | Module 2: kept terms, core/adjacent split, by-place demand, negative candidates, budget ceiling, control check |
| `landing-page.json`, `LANDING-PAGE.md` | Module 3: per-width fold table, issues, message match |
| `competitors-pass-N.json`, `COMPETITORS.md` | Module 4: passes and the merged view |
| `actions.json`, `actions-<tab>.csv`, `actions.xlsx` | Six action tabs: keywords to add, negatives to add, keywords to pause, targeting, bid and budget, landing page fixes. Each row: item, why, evidence, who, status |
| `CONTRACTOR-EMAIL.md` | Draft, action-first email to whoever runs the account |
| `SUMMARY.html` | Internal one-page view. Uses `~/.claude/brand/tokens.css` if you have one (CSS variables `--color-primary`, `--color-bg`, `--font-body`); optionally deploy it to any static host |
| `dfs-cost-ledger.jsonl` | DataForSEO cost per call for this run |

Optional: `--supabase` writes `gads_accounts`, `gads_daily` and `gads_audit_findings` to your own
Supabase project for tracking over time (schema: `references/supabase-schema.sql`).

## Cost per run

| Module | Cost | Time |
|---|---|---|
| 1 account audit | free (Google Ads API), ~15 GAQL reads | 20-40 s |
| 2 keyword research | about US$0.015-0.035 per seed (suggestions) + about US$0.09 per `search_volume` call | 1-2 min |
| 3 landing page | free locally; PSI is free within quota | 20 s per page per width set |
| 4 competitors | about US$0.0035 per query per pass | 7-20 s per query |
| 5 outputs | free | seconds |

A full audit with 10 seeds and 3 competitor passes of 5 terms runs about **US$0.55-1.00** of
DataForSEO credit. Check DataForSEO's current pricing; the ledger prints the real cost per call.

## Files

| File | What it does |
|---|---|
| `scripts/gadslib.py` | Loads gads-common and the DataForSEO client, findings model, markdown tables, location codes |
| `scripts/dfs_client.py` | Minimal DataForSEO REST client with a per-run cost ledger (`--balance`, `--ledger`) |
| `scripts/audit_account.py` | Module 1. ~15 GAQL reads, shapes them, runs the findings catalogue |
| `scripts/keyword_research.py` | Module 2. Phrase-locked expansion, exact volumes with controls, intent classification, market size and budget ceiling |
| `scripts/landing_page.py` | Module 3. CDP renders at 5 widths, fold and overflow, redirect chain, lab timings, PSI, message match |
| `scripts/competitors.py` | Module 4. One pass per call; `--merge` combines and enforces the multi-pass rule |
| `scripts/build_outputs.py` | Module 5. Actions, CSVs, xlsx, contractor email, summary page, optional Supabase |
