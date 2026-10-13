# Setter call rubric (8 dimensions)

Written from widely published sales practice (speed-to-lead research, upfront agendas,
problem-centred discovery, objection loops, specific-time booking, no-show prevention).
Targets that vary by business live in `audit-config.json`, not here. Score every dimension
PASS / PARTIAL / MISS / N/A, and back every score with a quote and a `[mm:ss]` timestamp.

A setter call here means any first-contact or follow-up call whose job is to book the next
step: a consultation (clinic), a demo or discovery call (SaaS), or a strategy call (agency).

---

## 1. Speed to lead and persistence
How fast the first human contact happened, and whether the setter kept trying.

| Score | Criteria |
|---|---|
| PASS | First outbound call within `speed_pass_minutes`, AND a follow-up plan across channels (call, text, email) if unreached |
| PARTIAL | First call within `speed_partial_minutes`, or fast but only one attempt |
| MISS | Slower than `speed_partial_minutes`, or one attempt then nothing |

Use `first_call_min` from the manifest (automated texts make `speed_to_lead_min` look instant).
Count `outbound_call_attempts` for persistence. Public research (Harvard Business Review,
"The Short Life of Online Sales Leads", 2011) found that firms contacting web leads within an
hour were far more likely to qualify them than those waiting longer; quote it as background,
not as a promise.

## 2. Opening and agenda
In the first minute: who is calling and why, a reminder of what the lead asked for, a short
agenda (what this call is for and what happens at the end), and a check the lead is OK with it.

| Score | Criteria |
|---|---|
| PASS | Names self and business, reminds the lead of their enquiry, states the purpose of the call, and asks permission or confirms time |
| PARTIAL | Two or three of those four |
| MISS | Launches straight into questions or a pitch; the lead is unsure why they are being called |

Good sign: the setter frames the call up front, saying what the call covers and what will
happen at the end of it (for example, "if it looks like we can help, we'll pick a time for the
consultation; if not, I'll point you somewhere useful").

## 3. Discovery (the problem, the goal and the cost of waiting)
Did the setter get the lead to describe, in their own words:
- **Where they are now** (the problem, ideally with a number: e.g. "losing 30% of my hair at the crown", "our nurses spend 2 hours a day on notes", "we get 40 leads a month and book 8").
- **Where they want to be** (the goal, ideally with a number or date).
- **Why now** and **what it costs to stay put** (money, time, confidence, risk).

| Score | Criteria |
|---|---|
| PASS | All three, at least one quantified, lead did most of the talking |
| PARTIAL | One or two, or all three but only surface level ("I just want it better") |
| MISS | No discovery, or the setter answered their own questions |

Coach on follow-up questions: "What does that look like day to day?", "What have you tried?",
"What happens if nothing changes in six months?".

## 4. Qualification
Did the setter confirm the lead meets the fit criteria in `audit-config.json`
(`qualification_criteria`, e.g. need, decision maker, timing, budget or ability to pay,
location or eligibility, tech stack or team size)?

| Score | Criteria |
|---|---|
| PASS | Every required criterion confirmed or explicitly ruled out, unqualified leads are not booked (or are routed elsewhere) |
| PARTIAL | Some criteria checked; at least one required one skipped |
| MISS | Booked without checking fit, or disqualified on a guess |

Also check: is the person on the call the decision maker, and will any other decision maker
attend the booked call (partner, practice owner, CFO, IT/security)?

## 5. Objection handling
For each pushback ("send me an email", "how much is it?", "I need to think", "not now",
"I'm talking to others"), did the setter run a full loop?
1. **Acknowledge** (no arguing, no steamrolling).
2. **Clarify** the real concern with a question (for example, "what's making you unsure?") before answering it.
3. **Respond** to that concern briefly, tied to what the lead said in discovery.
4. **Confirm** it is resolved, then return to booking.

| Score | Criteria |
|---|---|
| PASS | Loop completed on every objection, call moves forward |
| PARTIAL | Acknowledged but answered the surface objection without clarifying, or dropped the booking afterwards |
| MISS | Accepted the brush-off and ended the call, argued, or discounted to save it |

"Send me some info" is rarely the real objection: agree, send it, and still book or pin a time.

## 6. Booking commitment
| Score | Criteria |
|---|---|
| PASS | Offers two specific times (a choice, not "when suits?"), within `booking_window_days`, books it live, confirms date, time, timezone, channel (in person, phone, video) and who attends |
| PARTIAL | Booked, but with an open-ended time ask, outside the window, or details not confirmed aloud |
| MISS | No booking attempt, or "call us back when you're ready" |

## 7. Show-up setup
What the setter did to make the booked call actually happen.

| Score | Criteria |
|---|---|
| PASS | Gets a commitment ("if anything changes, will you let me know so I can give the slot to someone else?"), confirms they will get the invite and reminders, sets an expectation of what happens on the call, and gives a reason to show (a pre-call video, case study, checklist or form) |
| PARTIAL | One or two of those |
| MISS | Hangs up straight after the time is agreed |

Cross-check in GHL: did the confirmation and reminder automations actually fire for this booking?

## 8. Delivery and accuracy
| Score | Criteria |
|---|---|
| PASS | Lead talks most of the time (aim roughly 60/40 or more in the lead's favour in discovery), calm pace, uses the lead's words back, correct business name, offer, price rules and compliance lines |
| PARTIAL | Talks over the lead in places, rushed, or one factual slip |
| MISS | Monologue, wrong offer terms or price, or a compliance breach (outcome promises, medical claims, sharing data with the wrong person) |

Estimate talk ratio from transcript segment lengths per speaker; say it is an estimate.

---

## Scoring roll-up
- PASS = 2, PARTIAL = 1, MISS = 0, N/A excluded. Call score = points / (2 x scored dimensions), shown as a percentage.
- Report the dimension pattern across calls (e.g. "Discovery MISS on 6 of 9 calls"); patterns matter more than any single call.
- Sample-size note: below `min_calls_for_judgement` calls, label the audit DIRECTIONAL in the header.

## Coaching rules
- Behaviour only. Quote what was said and what the rubric expected. Never comment on character, attitude, effort or trustworthiness.
- Frame each miss as a drill ("practise this line"), not a verdict.
- New setter (inside `ramp_days` of their start date): say so in the header and weight accordingly.
- Never attribute a call to a person until the user id to name map is confirmed by the user.

## Living rubric
After each audit, if a pattern showed up that no dimension covers, add one bullet under the
right dimension here (generic wording, no lead names, no quotes that identify anyone).
