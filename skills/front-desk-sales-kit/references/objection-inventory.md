# Objection inventory: method and starter checklists

The checklists below are unranked categories to code against. The order and counts come only
from your own calls: `scripts/mine_calls.py` pulls the recordings, `scripts/transcribe_calls.py`
transcribes them, and you tally each category from the transcripts.

## Method (mine before you write)
1. Pull every recorded call over 30 s from the location (`scripts/mine_calls.py`).
2. Transcribe locally (`scripts/transcribe_calls.py`).
3. Exclude voicemails and no-answers from the counts (they still matter for speed to lead).
4. Read every live call. Write down each pushback in the lead's words.
5. Merge variants into one canonical objection (different wordings of "what is this?" are
   one item).
6. Count each one. Machine transcripts are rough, so report bands (common / occasional /
   rare) rather than exact tallies.
7. Tag each with a bucket: **Clarity** (doesn't understand the offer), **Timing**, **Money**,
   **Trust** (is this genuine, send me info), **Fit** (do you do X, am I eligible, already a
   customer).
8. Write one handler per objection in the business's voice, plus one coaching note.
9. De-identify everything: no names, numbers, health details or quotes that identify a person.
10. If a location has very few recordings (calls made on personal phones), say so and fall
    back to the team's notes. Routing every call through the CRM fixes this.

## Checklist A: clinic front desk (offer-led or ad leads)
Code calls against these; add anything new you hear. Example wording for each lives in
`configs/example-clinic.json` (OBJECTIONS).

| Bucket | Category to look for |
|---|---|
| Clarity | What is the offer / what's included? |
| Clarity | Quick "not interested" |
| Timing | Not now / call me back |
| Timing | How long does the offer last? |
| Timing | Health or life reason, can't come now |
| Money | Price of the treatment |
| Money | The condition (deposit, minimum, eligibility) |
| Money | Can't afford it right now |
| Trust | Send me info / I'll check the website |
| Trust | I'll have a think |
| Trust | Who is this / I didn't enquire |
| Trust | Tried things before, didn't work |
| Fit | Already a client |
| Fit | Do you do [treatment]? |

High-ticket procedures (hair restoration and similar) often add: "Am I a candidate?" (Fit:
route to the assessment, never diagnose on the phone), "Will it look natural?" (Trust: results
are discussed with the clinician, no guarantees), "Can I pay monthly?" (Money: confirm finance
exists, details at consultation), "I'm comparing clinics / going abroad" (Trust: acknowledge,
never criticise competitors).

## Checklist B: inbound SaaS (demo request, free trial, content lead)
Use these as the OBJECTIONS list when the kit is for an SDR or inbound sales team. Replace
BOOKED_CALL with "demo" and SPECIALIST with "solutions specialist" in the config.

| Bucket | Category | Handler shape |
|---|---|---|
| Clarity | "I was just researching / downloaded a guide" | Acknowledge, ask what prompted the research, offer a short tailored walkthrough |
| Trust | "Send me a deck / pricing first" | Send it, then offer a time: a deck can't show it on their workflow, a short demo can |
| Money | "How much is it?" | Give the pricing model and a range if public; exact pricing depends on seats or volume |
| Timing | "Not now, maybe next quarter" | Ask what happens next quarter (budget, project, renewal), book a date tied to that event |
| Fit | "We already use [competitor] / have something in-house" | Ask what works and what doesn't; offer a side-by-side on the gap they named |
| Fit | "I'm not the decision maker" | Ask who else is involved and invite them; offer a one-page summary for them |
| Trust | "Is it secure / HIPAA / SOC 2?" | Confirm only the certifications you actually hold, offer the security pack and a call with your security lead |
| Fit | "Does it integrate with our EHR / CRM?" | Confirm known integrations, book a technical demo for anything else, don't promise roadmap |
| Trust | "We tried AI tools and they didn't work" | Ask what failed; position the demo as a test on their own scenario |
| Timing | "Just email me" | Agree, send a two-line email, suggest a 15-minute slot |

## Living inventory
After each mining pass, append a short dated section here: dataset size (live vs voicemail),
the categories you found most often, and any NEW objection with its handler. No client names.
