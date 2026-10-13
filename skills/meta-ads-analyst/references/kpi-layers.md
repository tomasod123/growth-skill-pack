# The scorecard and the maths behind it

Every target lives in `config/analyst.json`. This file ships no benchmarks: they swing too much by market, price point and sales motion. Your own last 90 days are the baseline to beat.

## A three-layer scorecard

| Layer | What it tells you | Typical metrics |
|---|---|---|
| Money | Is spend turning into customers and cash at a price you can live with? | CAC (spend / new customers), first-payment cash / spend, total contract value / spend, lifetime gross profit / CAC |
| Pipeline | At which step are people leaking out? | CPL, cost per qualified lead, lead-to-booking %, cost per booking, show %, cost per show, close %, speed to lead, share paid upfront |
| Diagnostics | What is causing a pipeline number to be off? | Link CTR, CPM, 3-second view rate, hold rate, page or form conversion, Meta's quality / engagement / conversion rankings, frequency, disqualification rate |

Reading it:
- The money layer is what you report and decide on. The pipeline layer points to the step that needs work. Diagnostics suggest the specific change.
- When the money layer is in target, a weak pipeline or diagnostic number is a watch item, not an emergency. Write it down and recheck next run; the case for changing a profitable campaign has to be strong.
- When the money layer is out of target, trace it down: which pipeline step has drifted furthest from its target, and which diagnostic explains it.
- Low CPL with high CAC is a problem. High CPL with low CAC is fine.

## The cost chain
```
cost per booking   = CPL / lead-to-booking rate
cost per show      = cost per booking / show rate
CAC                = cost per show / close rate
cost per qualified booking ~ cost per qualified lead / booking rate
first-payment cash / spend = cash collected on first payment / spend
```
Writing the chain out shows which rate moves CAC most. If CPL is on target but lead-to-booking is half its target, the work is in follow-up (response time, the booking step, the person calling), not in the ads.

`scripts/funnel_math.py` computes the chain from screenshot numbers or live pulls.

## Affordable costs for a new offer (no history yet)
Start from what a customer is worth to you and divide back through each step. Made-up numbers:
```
First payment collected        4,000
Gross margin                   60%   -> break-even CAC          = 2,400
Assumed close rate             25%   -> max cost per show       = 600
Assumed show rate              70%   -> max cost per booking    = 420
Assumed lead-to-booking rate   40%   -> max CPL                 = 168
```
These are ceilings, not goals. Put your assumptions in the config and swap in measured rates once you have a few weeks of data.

## Spend needed for a goal
```
new customers needed  = revenue goal / average customer value
shows needed          = customers / close rate
bookings needed       = shows / show rate
leads needed          = bookings / lead-to-booking rate
spend needed          = leads x CPL
```
Add a capacity table next to it: for each budget level, the qualified leads and bookings per week it implies, the customers per month, and how many distinct creative concepts it would need. A budget increase is pointless if follow-up or creative is the real limit.

## Business-to-business vs local consumer
Say which one each campaign is before grading; the patterns differ.
- **B2B / SaaS (demos, sales calls, contracts):** longer cycles, higher CPL, qualification matters more than volume, and the close may be a pilot weeks later. Cost per qualified booking and pipeline value per booking are the useful working numbers. Put one hard qualifier on the form (company size, role or budget band) and make the CRM record it.
- **Local consumer (patients, one or a few locations):** short cycles, response time and lead volume matter most, the offer moves results the most, frequency climbs quickly in a small radius, and deposits change show rates. Track consult bookings, shows and first-visit cash.
- **Healthcare in either case:** compliance limits what you can say and which events you may send to Meta. Check what the pixel and Conversions API actually pass; Meta restricts some health-related data.

## Finding the bottleneck
The four steps are: get leads, get them booked, get them to show, get them to buy. The bottleneck is the step furthest behind its target. When several are behind, estimate for each fix how much it would move CAC and how much work it is, and lead with the best ratio. Reminder messages and a confirmation call often fix a show-rate gap faster than new creative.

When the ads "don't work", look at what is being sold and to whom, how the ad communicates it, and how the account is set up and tracked, before concluding the channel is wrong.
