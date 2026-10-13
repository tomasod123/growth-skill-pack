# client-performance-report: setup

**What it does:** turns a growth-data-hub `report.json` into two one-page HTML reports: a candid internal review and a client-branded draft that leads with wins and nudges speed to lead.
No API calls of its own: it only reads files, so the only setup is Python and a brand file per client.

## What you need

| Item | Where to get it |
|---|---|
| Python 3.9+ with PyYAML | `pip install -r requirements.txt` |
| A `report.json` | Run the `growth-data-hub` skill (`.venv/bin/python hub.py --days 28` in its folder); it writes `out/report.json`. For a test, use `fixtures/report.json`. |
| A `brand.yaml` per client | Copy `brand.example.yaml`. Fill in client name, logo, two hex colours, a font name. |
| The client's logo | Their website (right-click the header logo, save) or ask them for a PNG/SVG. Save it next to `brand.yaml` so it is inlined into the page. |
| Brand colours | The client's brand guide, or pick two from their website with a colour picker (hex, like `#0F5257`). |
| Optional: `benchmarks.yaml` | The same file growth-data-hub uses, so wins and nudges use your tuned floors. |

No environment variables, no keys.

## Install

```bash
cp -r client-performance-report ~/.claude/skills/
cd ~/.claude/skills/client-performance-report
python3 -m pip install -r requirements.txt     # on Ubuntu/Debian system Python: python3 -m venv .venv && . .venv/bin/activate first
mkdir -p clients/demo-clinic && cp brand.example.yaml clients/demo-clinic/brand.yaml   # then edit it
```

## First run (2 minutes)

```bash
python3 scripts/build_report.py --help
python3 scripts/build_report.py --report fixtures/report.json --brand fixtures/brand.yaml --out /tmp/demo-report
python3 -m pytest -q tests                     # optional: 18 tests, all should pass
```

Open `/tmp/demo-report/client.html` and `internal.html` in a browser (both work on a phone). Then the real one:

```bash
python3 scripts/build_report.py --report ~/.claude/skills/growth-data-hub/out/report.json \
  --brand clients/demo-clinic/brand.yaml --out clients/demo-clinic/2026-10 \
  --benchmarks ~/.claude/skills/growth-data-hub/benchmarks.yaml
```

Or ask Claude: "build the client report for Demo Clinic from the latest growth report".

`client.html` is a draft. Nothing is sent anywhere. Share it yourself once you have approved it (rebuild with `--approved` to drop the draft banner).

## Common errors and fixes

| You see | Fix |
|---|---|
| `is not a growth-data-hub report.json (missing 'funnel')` | Point `--report` at the hub's `out/report.json`, not `ACTIONS.md` or `report.html`. |
| `brand.yaml needs client_name` | Add `client_name:` to the brand file. |
| `colors.primary must be a hex colour` | Use `#RRGGBB` (or `#RGB`) in quotes, e.g. `"#0F5257"`. Colour names are rejected on purpose. |
| `warning: logo not found` | The logo path is relative to `brand.yaml`. Fix the path; until then a text wordmark is used. |
| Logo missing when the page is opened offline | You used an `https://` logo URL. Save the file locally instead so it is inlined. |
| Font looks different from the brand | Only installed fonts render. The page falls back to the system font, which is fine for sharing. |
| No speed-to-lead section | Every channel with enough leads books at or above its floor. That is good news. |
| A win you expected is missing | It needs enough data (`minimums` in benchmarks) and must clear its floor by 20%. |
| Numbers differ from the ad platform | The client page uses CRM leads (the hub's join). The internal page shows both and flags the gap. |

## Setup time

5 minutes for the install and demo. About 5 minutes per new client to make the brand file.

## API cost

None. It reads local files only. All free except your time.
