# Token registry

Every business-specific value is a `{{TOKEN}}` in `templates/*.html`, filled from the config.
Scalar tokens can be used inside other values and inside list text.

## Scalar tokens
| Token | Meaning | Clinic example | Inbound SaaS example |
|---|---|---|---|
| `BUSINESS_NAME` | Trading name | Example Clinic | Example Health AI |
| `TEAM` | Who the doc is for | the front desk team | the inbound SDR team |
| `CALLER_ROLE` | What the caller is | the front desk | your SDR |
| `SPECIALIST` | Who runs the booked call | clinician | solutions specialist |
| `LEAD_EXPERT` | Named lead (optional, shown on the cover) | Dr A. Example, lead clinician | Head of Clinical Solutions |
| `BOOKED_CALL` | What gets booked | consultation | demo |
| `OFFER_NAME` | The ONE offer term, used everywhere | free consultation and written estimate | free 14-day pilot |
| `OFFER_AMOUNT` | Headline figure or word | free | 14 days |
| `MINIMUM_SPEND` | Minimum, deposit or key condition (say it early) | $25 refundable deposit | up to 3 clinicians |
| `OFFER_ONE_LINER` | The exact sentence that explains the offer | see example config | "The pilot gives three clinicians full access for 14 days, set up on a 20-minute call, no card needed." |
| `LOCATION` | City or region (match reality) | Example City | US and Canada |
| `CREDENTIALS` | Trust line (credibility, not outcomes) | registered clinicians, assessment first | SOC 2 Type II, HIPAA-ready, BAA available |
| `PRICE_GUIDE` | Rough guide for the price question | every cost is set out in the written estimate | per-seat pricing, from $X per clinician per month |
| `OFFER_EXPIRY` | When the offer ends | end of next month | end of the quarter |
| `CALENDAR_URL` | Booking link (a GHL custom value is fine) | `{{custom_values.booking_link}}` | your scheduling link |
| `COMPLIANCE_NOTES` | Region and niche rules | no outcome promises, no prescription brand names, deposit described exactly as the terms say | no unapproved clinical claims, no roadmap promises |
| `SPEED_TARGET`, `SPEED_LINE`, `SPEED_EVIDENCE` | Speed-to-lead box | 5 min | 5 min |
| `SHEET_TITLE`, `SHEET_HEADLINE`, `SHEET_INTRO` | Cheat sheet header | | |
| `PLAYBOOK_TITLE`, `PLAYBOOK_INTRO`, `FOOTER_CREDIT` | Playbook cover and footer | | |
| `VERSION`, `DATE` | Footer and cover | v1.0 | v1.0 |

## Brand tokens
`BRAND_PRIMARY`, `BRAND_INK`, `BRAND_MUTED`, `BRAND_ACCENT`, `BRAND_PAPER`, `BRAND_RULE`
(hex colours), `BRAND_FONT` (a Google Fonts family name), `LOGO_FILE` (path relative to the
config, or a URL). Take these from the client's website or brand guide. For your own
material, use your brand tokens (optional: `~/.claude/brand/tokens.css`).

## List blocks
`PRINCIPLES`, `KEEP_BY_THE_PHONE` (word + what; 3 short phone habits), `KEEP_TIPS` (1-2 one-line tips; your own team's habits go here), `OPENERS` (label, lines, note;
the first is the cheat-sheet opener, the rest become branch notes), `CALL_STEPS` (title, goal,
say, cue, compliance), `FAQS` (q, a), `TEXTS` (label, when, body), `OBJECTIONS` (q, freq,
bucket, variants, short, handle, note; `short` is used on the cheat sheet), `DRILLS` (title,
situation, target, principle, aim), `SPEED_HABITS`, `OFFER_TERMS` (chips; `<b>` allowed). `freq` on an objection is a free-text label: use `Starter` until you have mined calls, then a band such as common / occasional.
`CHEATSHEET_TOP_N` sets how many objections fit on the one-pager (default 11).

## Voice switch
`TEAM` + `CALLER_ROLE` + `SPECIALIST` set the tone. A front-desk caller is friendly and clear and
hands clinical or technical detail to the specialist. Confirm who actually makes the calls
before rendering.

## Merge fields
Lowercase dotted tokens such as `{{contact.first_name}}` and `{{custom_values.booking_link}}`
are GHL merge fields and are left in place on purpose (texts get pasted into GHL workflows).
