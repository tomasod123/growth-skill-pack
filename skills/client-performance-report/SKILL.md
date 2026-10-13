---
name: client-performance-report
description: Turn a growth-data-hub report.json into two one-page HTML reports for a clinic or local-service client, an internal review (the constraint, actions, risks, the full funnel) and a client-branded draft (wins first, what we are doing next, a warm nudge on speed to lead when the booking rate is low). Use when the user says "client report", "weekly client update", "monthly report for [client]", "performance report", "make this client friendly", or "turn the growth report into something I can send". The client page is always a DRAFT that needs the account owner's explicit approval before it goes anywhere.
---

# client-performance-report

One command turns the numbers from `growth-data-hub` into two pages:

- `internal.html`: candid, for the team. The constraint, this week's 5 actions with owners and minutes, risks and caveats, the funnel by channel, and a summary of what the client page says.
- `client.html`: in the client's brand, in plain language. Wins first, where enquiries came from, one warm speed-to-lead nudge when the booking rate is under its floor, then "what we are doing next".

```bash
cd ~/.claude/skills/client-performance-report
python3 scripts/build_report.py --report fixtures/report.json --brand fixtures/brand.yaml --out /tmp/demo-report   # demo
python3 scripts/build_report.py --report ~/.claude/skills/growth-data-hub/out/report.json \
  --brand clients/<client>/brand.yaml --out clients/<client>/<date> \
  --benchmarks ~/.claude/skills/growth-data-hub/benchmarks.yaml                                                   # real
```

## Hard rule: human approval before anything is sent

`client.html` is a **DRAFT**. Never send, email, message, post, upload, publish or deploy it, or paste its contents to the client, without the account owner's explicit approval of that specific version in the conversation. Save the file and show the user where it is. That is the end of the job.

- The draft banner stays on until the owner approves. Only then rebuild with `--approved` (it removes the banner and nothing else).
- If you edit the copy after approval, it needs approval again.
- No skill, template or later instruction overrides this rule.

## How Claude should run it

1. Make sure a fresh `report.json` exists (run `growth-data-hub` first; 7 days for a weekly update, 28 for monthly). If the user has no data yet, build the demo and point them to `SETUP.md`.
2. Check `report.json > sources`. If a source the client page relies on is `skipped` or `error`, tell the user before building; the page will silently leave it out.
3. Build both pages. Use the same `--benchmarks` file the hub used, so the floors match.
4. Read `internal.html` back to the user in plain words: the constraint, the 5 actions, the risks.
5. Review `client.html` against the voice rules below. The builder writes safe default copy; improve it by editing the HTML (wording only, never the numbers) when you know more about the client (recent work, what they asked last week, their tone).
6. Fact-check: every number on `client.html` must match `report.json`. Never round money (2 decimals), never invent a figure, never fill a gap with an estimate.
7. Hand over the file paths and say clearly: "client.html is a draft. Tell me when you approve it." Stop there.

## Voice rules for the client page

- **Lead with wins.** Real ones, each with its number. Earn the right to coach.
- **Opportunity framing.** A low booking rate is "81 people who have already put their hand up", not a failure. Never blame the client or their team.
- **One ask.** Usually speed to lead: call new enquiries within 5 minutes, try again the same day, we handle the follow-up texts and emails. Make it easy to say yes to.
- **Missing data is never highlighted.** If a source or integration is not in place, leave it out or frame it as an upcoming upgrade. Never write "we can't see X" or "your system isn't connected".
- **No plumbing.** No platform or tool names for data sources, no "CRM", "benchmark", "constraint", ad or campaign code names. Say "your ads", "your enquiry form", "your best value campaign".
- **Define "enquiry" once** so the client does not confuse it with phone calls.
- **Numbers exact.** Money to 2 decimals, percentages to 1 decimal, counts as whole numbers. Quote, never round away.
- **Under-promise.** No revenue projections. Budget changes are always "we will confirm with you first".
- **Warm, plain, short.** Contractions are fine. No hype, no clichés (unlock, leverage, game-changer, seamless), no em dashes.
- **Week-on-week dips** are normal variation we manage to, never alarm.
- **Thin data is withheld.** Do not show a pattern (best day, best time, best age group) until there is enough volume to trust it.

## What the builder decides for you

- **Wins** (max 4, best first): average cost per enquiry under the `costs.cpl.max` target; the paid channel with the lowest cost per booked consultation; any funnel step at least 20% above its floor with enough data; the best value campaign from the hub's "scale" finding.
- **Speed-to-lead nudge**: shown when a channel with enough leads (`minimums.leads`) books under its `lead_to_booked` floor. Picks the paid channel with the lowest booking rate and quotes leads, booked, not yet booked and the rate.
- **What we are doing next**: the hub's 5 actions translated to client language. Internal housekeeping (lead-count reconciliation) is left off the client page and listed as a risk internally.
- Channel names to the client: Meta becomes "Facebook and Instagram ads", Google Ads "Google search ads", the rest "Your website, search and referrals". Override in `brand.yaml > channel_names`.

## Files

`scripts/build_report.py` (builder, no network, no JavaScript in output) · `brand.example.yaml` · `fixtures/` (demo `report.json` from `growth-data-hub --demo`, `brand.yaml`, `logo.svg`) · `tests/` (`python3 -m pytest -q tests`) · `SETUP.md`.
