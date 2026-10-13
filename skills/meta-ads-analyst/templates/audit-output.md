# Audit output template

Plain language first, numbers after. Write for the business owner, not another media buyer. No jargon without a one-line explanation. Currency as in the account.

```markdown
# Meta ads read: [account / campaign], [window]

## Do this week
1. [Action in plain words]. Why: [one line tied to money or customers]. Who: [media buyer / setter / owner]. Time: [minutes].
2. ...
(Mark items already done as done.)

## Verdict
[One line: Profitable / Break-even / Losing, and the bottleneck step.]

## Campaign: [NAME]
**Type:** B2B / local B2C   **Objective / optimisation event:** [...]   **Window:** [dates, why this window]
**Data caveats:** [publish-state check result, contamination, tracking gaps]

### Money layer
| Metric | Value | Target | Status |
|---|---|---|---|

### Pipeline layer
| Metric | Value | Target | Status |
|---|---|---|---|

### Diagnostics (only where the pipeline needs explaining)
| Metric | Value | Target | Status |
|---|---|---|---|

### Bottleneck: [Leads / Booking / Show / Close]
[Where the biggest gap is, with the cost-chain line that proves it.]

### Per ad / per concept
| Ad or concept | Spend | Leads | Qualified | Cost per qualified | Call (GROW/KEEP/ADJUST/TOO EARLY/STOP) | Why |
|---|---|---|---|---|---|---|

### Creative diversity
Distinct concepts live: [n] (floor [config]). Duplicates grouped: [...]. Missing angles: [...].

### Follow-up and CRM (live data mode)
Bookings from the calendar, booking rate, speed-to-lead buckets, stage-sync gaps, what the conversations show (short quotes, no personal data).

### Actions, best effect for the effort first
1. [Action] - [expected effect on which metric]
2. ...

### Traps check
[Any trap from references/decision-rules.md being triggered, or "none".]

### Budget read
[More budget safe now? Step size and timing from config, or why not yet.]

### Third-party recommendations cross-check (if any)
| Their recommendation | Agree / disagree | Why |
|---|---|---|

## Data appendix
Sources, pull timestamps, windows, anything excluded and why.
```

Optional HTML: render the same content with your brand tokens (colours, fonts) from `~/.claude/brand/tokens.css` if you keep one; otherwise a plain readable page. Footer with your company name and the date only.
