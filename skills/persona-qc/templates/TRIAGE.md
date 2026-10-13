# Triage, <artefact> v<N>, <date time> (<who>)
One row per FIX BEFORE SEND and drift item from every lens, plus the coordinator's additions. Allowed verdicts, exactly these words in bold: **implement** · **already fixed** · **team** (a named person, becomes a task in your task tool) · **client** (a question for the client, becomes a one-line question on the page) · **owner decision** (only where no DEFAULT in DECISIONS.md covers it) · **rejected** (with the rule or the brief line). Source of truth for every number: `FACTS.md`.

## Counts
implement <n> · already fixed <n> · team <n> · client <n> · owner decision <n> · rejected <n>

## <Lens 1 name>
| # | Item | Verdict | Where / why |
|---|---|---|---|
| L1-fix1 | <one line> | **implement** | <file, what the replacement is, DECISIONS item if any> |
| L1-fix2 | <one line> | **already fixed** | <where: file/section, or which earlier round> |
| L1-drift3 | <one line> | **team** | <who, what they check, by when> |
| L1-drift4 | <one line> | **client** | <the one-line question it becomes, and where on the page> |
| L1-fix5 | <one line> | **owner decision** | <what it changes: offer / price / commitment / fault admission; recommended DEFAULT> |
| L1-drift6 | <one line> | **rejected** | <the rule or brief line: e.g. "brief F6 asks for this block", "figure is sourced (call, timestamp)", "house rule: no money talk over email"> |

## <Lens 2 name>
...

## Coordinator additions
Items no lens raised but the coordinator saw while reading all four (contradictions between lenses, a fix that would break another lens's pass).
