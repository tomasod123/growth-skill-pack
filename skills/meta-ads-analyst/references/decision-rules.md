# Per-ad calls and when to make them

All numbers come from `config/analyst.json`. If a value is null, say "no target set" and ask the user for it once.

## Before judging anything
- **Enough spend to know.** Judge an ad or campaign only after it has spent `judge_after_spend_multiple_of_target` x the target cost for the result you are judging (CPL, cost per booking) over at least `judge_after_min_days` days. Before that, call it TOO EARLY.
- **Clearly broken is the exception.** Very low CTR and no results after real spend can be called early. Name the leading indicator behind the call.
- **Small budgets need longer windows.** At about one result a day, empty days are normal (a Poisson process with a mean of 1 gives a zero day about 37% of the time). Use 7-14 day windows.
- **Meta's learning phase** needs about 50 optimisation events per ad set per week to stabilise (Meta Business Help Center). A low-budget campaign far below that stays in "Learning limited"; that is structural, not a creative failure. Significant edits (budget, targeting, new creative, bid) can restart learning.
- **Confirm edits were published.** Ads Manager edits can sit unpublished behind "Review and publish". Compare the account activity log (`meta_pull.py` pulls 14 days) with what the team thinks is live before reading any trend.

## The five calls (one per ad, ad set and campaign)
| Call | Use it when |
|---|---|
| GROW | Money layer in target, enough data, frequency has headroom: add budget in place |
| KEEP | Doing its job; leave it running untouched |
| ADJUST | Close to target; name one change and the metric it should move |
| TOO EARLY | Not enough spend or days to judge yet; say what data would settle it |
| STOP | Enough data and clearly off target, or past `kill_zero_result_spend_multiple` x target with no result |

Losers that get almost no spend inside a consolidated ad set cost little; Meta has already throttled them. Focus STOP calls on losers still taking a real share of budget.

## Adding budget
- Grow a winner where it is: raise budget by about `budget_step_pct` every `budget_step_every_days` days while the money layer holds. Big single jumps tend to push cost per result up.
- Copying a proven ad into a new ad set restarts learning, so do not treat duplication as a way to grow.
- Before a budget increase, check the capacity table in kpi-layers.md: enough concepts live and enough follow-up capacity for the extra leads.

## Lead quality
- If the money layer is profitable despite a high disqualification rate, keep funding what works and test quality fixes on a small slice of budget.
- Ways to lift quality: address a more advanced version of the problem in the copy, add one hard qualifier to the form, switch the form to "Higher intent", send qualified-lead events back to Meta with Conversions API for CRM.

## Targeting and structure
- Broad (Advantage+ audience) is a sensible default unless your own tests say otherwise; the creative carries most of the targeting.
- Fewer, consolidated ad sets learn faster than many small ones.
- Cutting placements because CPM is high often backfires; adapt the creative to the placement instead (for example 4:5 feed statics). Some B2B accounts do better without Audience Network or Messenger: test it, do not assume.
- Exclude existing customers and open pipeline contacts with a customer list.
- Leave age and gender to the algorithm unless your history (CPL and cost per customer by age floor) shows a repeatable difference.

## Format
Compare video and static on cost per customer or cost per qualified booking, not CPL. Run formats side by side; do not switch off the one that wins further down the funnel.

## Traps worth calling out
- Changes driven by a bad day or a hunch rather than enough data.
- Working on a pipeline or diagnostic number while the money layer is fine.
- Frequent small edits that keep restarting learning.
- Reading lifetime totals across old bursts and dark weeks instead of the window the current setup has been live.
- Reading account totals while another campaign is also spending (the pull flags it).
- Counting leads by substring match on action type, which double counts.
- Blaming "lead quality" with no CRM tags to show it.
- Calling a re-cut of the same message "new creative".
