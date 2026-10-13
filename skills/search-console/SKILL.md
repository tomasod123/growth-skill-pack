---
name: search-console
description: Read-only Google Search Console data through Google's official Python libraries (scope webmasters.readonly). Property list, performance vs the previous period, raw exports, striking-distance queries, CTR gaps, cannibalisation, zero-click pages, URL inspection, sitemap audit, per-URL query history, and a redirect-map checker that flags 301s pointing old pages at the wrong topic. Use when the user says "search console data", "GSC data", "real clicks and impressions", "striking distance", "ctr gaps", "cannibalisation", "which old URLs ranked for what", "is the redirect map right", "what did this page rank for before the migration", or "is this page indexed".
---

# search-console: read-only Search Console

`scripts/gsc.py` calls Google's Search Console API through Google's own libraries (`google-api-python-client`, `google-auth-oauthlib`) and nothing else. Google has no official Search Console MCP; prefer this over community connectors. Search Console shows what Google actually served, so it wins over third-party SEO tool estimates on any conflict.

## Security

- Read-only twice over: the token carries only `webmasters.readonly` (Google refuses any write), and the script refuses to save a token with any other scope. Never request another scope.
- Files: `$GSC_CONFIG_DIR/client_secrets.json` (OAuth desktop client) and `$GSC_CONFIG_DIR/token.json`. Default `GSC_CONFIG_DIR` is `~/.config/gsc-reader`. Folder 700, files 600; the script writes everything owner-only. Never print, paste or commit the token.
- Revoke: myaccount.google.com/permissions > remove the app.

## Setup and login

See `SETUP.md` (about 15 minutes, once). Then:
```
python3 scripts/gsc.py login        # opens Google, click Allow
python3 scripts/gsc.py properties   # proves it works: lists every property the account can read
```
**7-day caveat:** while the OAuth app is in Google's "Testing" mode, a sign-in expires 7 days after login and commands exit with `invalid_grant`. Run `login` again, or publish the app (Branding needs a home page and privacy policy URL first).

Environment variables (all optional): `GSC_CONFIG_DIR` (key and token folder), `GSC_REPORTS_DIR` (where `audit` saves, default `./gsc-reports`), `GSC_LOGIN_HINT` (pre-selects the Google account at login), `GSC_IGNORE_WORDS` (comma list of town or area words for `redirect-check`).

## Commands

SITE is exactly as `properties` prints it (`sc-domain:example.com` or `https://www.example.com/`). Every command prints JSON. `--out FILE` saves the full JSON and prints only `{saved, summary}`; use it for anything bigger than a few rows.

| Command | What you get |
|---|---|
| `properties` | every property + permission level |
| `performance SITE [--days 28]` | totals vs previous period, top 10 queries and pages (final data, ends 3 days ago) |
| `sitemaps SITE` | submitted sitemaps, errors, warnings |
| `inspect SITE URL` | Google's index verdict, coverage, last crawl, Google vs declared canonical |
| `audit SITE [--max-urls 200]` | every sitemap URL: live HTTP status + index verdict; saves to `$GSC_REPORTS_DIR` |
| `export SITE --start D --end D --dims query,page [--device [MOBILE\|DESKTOP\|TABLET]] [--row-limit 25000]` | raw rows, paged until empty, dataState all. Bare `--device` adds device as a dimension; a value filters |
| `opportunities SITE [--days 28] [--min-impr 15] [--top 50]` | striking_distance, ctr_gaps, cannibalisation, host_duplicates, zero_click_pages |
| `url-history SITE --urls-file FILE [--days 480]` | per URL: totals, host variants seen, top 15 queries (clicks, impressions, position) |
| `redirect-check SITE --redirects FILE [--days 480] [--base URL] [--ignore-words a,b] [--min-impr 20]` | per 301 source: history, target, topic_match, flags, suggested better target |

Examples:
```
G=scripts/gsc.py; S=sc-domain:example.com
python3 $G performance $S --days 28
python3 $G export $S --start 2026-09-01 --end 2026-09-28 --dims date --device --out daily-device.json
python3 $G opportunities $S --days 28 --out opps.json
printf '/old-page-1\n/old-page-2\n' > old.txt && python3 $G url-history $S --urls-file old.txt
python3 $G redirect-check $S --redirects _redirects --base https://www.example.com --ignore-words springfield --out rc.json
```

### opportunities, exactly

- **striking_distance**: queries at average position 4-20 with impressions >= `--min-impr`, plus the page with most impressions.
- **ctr_gaps**: query+page rows at position <= 10 whose CTR is under the curve pos1 .28, 2 .15, 3 .10, 4 .07, 5 .05, 6 .04, 7 .03, 8 .025, 9 .02, 10 .018; `expected_extra_clicks` = impressions x (expected - actual).
- **cannibalisation** (always last 90 days): queries served by 2+ pages each with >= 10 impressions, after collapsing http/https/www/trailing slash. **host_duplicates** lists the same page seen under 2+ host variants.
- **zero_click_pages**: pages with >= 50 impressions and 0 clicks in the window.

### url-history and redirect-check, exactly

- URLs may be absolute or path-only (resolved against the property's host). Matching ignores http/https, www and trailing slash; `/*` splats and `:placeholder` segments work. Paths are batched into regex page filters, so a few API calls cover dozens of URLs.
- redirect-check reads a `_redirects` file (one `from to [status]` rule per line; comments, `301!` and inline `# notes` are fine; whole-domain host rules and 200 rewrites are skipped and listed) or a 2-column CSV `old,new`.
- **topic_match** (0-1): impression-weighted token overlap between the source's top queries and the target slug words. Ignored: stopwords, town words you pass (`--ignore-words` or `GSC_IGNORE_WORDS`), brand words taken from the domain, `site:` and brand-only queries. Queries that sit on many old pages (site-wide noise) are down-weighted, as are positions worse than 20.
- Candidate targets come from the live `/sitemap.xml` (`--base`, else https://www.host then https://host).
- Flags: **MANY_TO_ONE** 3+ sources with search history point at one target. **TOPIC_MISMATCH** the source's queries share no words with the target slug and a sitemap URL matches. **BETTER_TARGET** the target matches a little, another URL matches 1.5x better. **NO_HISTORY** zero impressions in the window. Suggestions need >= `--min-impr` impressions on the source.
- `summary.clean` = no suggested fixes. `summary.suggested_fixes` is the worklist; `targets_not_in_sitemap` carries each one's live HTTP status.
- It proposes; a human confirms each re-point against the query list before anything is deployed.

## Gotchas

- **Lag**: data is 2-3 days behind. `performance` uses final data ending 3 days ago; the other commands use dataState "all" ending 2 days ago, so recent days can still move.
- **Retention**: 16 months. `--days 480` is about the maximum.
- **URL Inspection quota**: 2,000 calls a day and 600 a minute per property. `audit` spends one per sitemap URL.
- **Domain vs URL-prefix property**: `sc-domain:` covers every host and protocol; a URL-prefix property sees only its prefix. `sitemaps SITE` is often empty on a domain property because the sitemap was submitted under a URL-prefix property; use the live sitemap.xml.
- **www vs non-www during a migration**: both hosts report separately until Google consolidates, so the same page shows twice (host_duplicates) and old and new URLs show as "cannibalisation" for weeks after a cutover. Read that list with the redirect map beside it.
- **Position is an impression-weighted average** and hides device splits; desktop and mobile can differ by 10 places. Export with `--device` before quoting a rank.
- Query rows drop anonymised queries, so query totals are lower than page totals. Brand queries dominate ctr_gaps on small sites; skip them when writing actions.
- `invalid_grant`: see the 7-day caveat. `Not signed in`: run `login`.

## How other skills call it

Shell (preferred): `python3 ~/.claude/skills/search-console/scripts/gsc.py <command> SITE ... --out <work-dir>/gsc-<cmd>.json`, then read the JSON. Save outputs in a work folder for that site, never inside the skill folder.

Python:
```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.claude/skills/search-console/scripts"))
import gsc
svc = gsc.service()
rows = gsc.query_all(svc, "sc-domain:example.com", "2026-09-01", "2026-09-15", ["query", "page"])
```
Also exposed: `opportunities`, `url_history`, `redirect_check`, `inspect`, `sitemaps`, `performance`.

Run `properties` first for a new site: if it is missing, the signed-in account has not been added as a user on that property (see the analytics-access-setup skill). Client-facing numbers need a date range and "Google Search Console" as the source, and need the account owner's approval before they are shared.
