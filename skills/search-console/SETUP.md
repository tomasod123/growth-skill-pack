# search-console: setup

**What it does:** reads your real Google Search Console data (clicks, impressions, CTR, position, index status) through Google's official libraries, read-only.
It also finds quick wins (striking distance, CTR gaps, cannibalisation) and checks a redirect map against what old pages used to rank for.

## What you need

| Item | Where to get it |
|---|---|
| A Google account that is a user on each Search Console property | search.google.com/search-console > property > Settings > **Users and permissions** > Add user. Restricted is enough for performance data; Full for sitemaps and URL inspection on every property. |
| A Google Cloud project | console.cloud.google.com > project picker > New project (free). |
| Search Console API enabled | Cloud Console > APIs & Services > Library > **Google Search Console API** > Enable. |
| OAuth consent screen | Cloud Console > **Google Auth Platform**: any app name, audience External (or Internal on Workspace), add your Google account as a **test user**, leave scopes empty, no logo (a logo triggers Google verification). |
| OAuth desktop client file | Google Auth Platform > Clients > Create client > **Desktop app** > Download JSON. Save as `~/.config/gsc-reader/client_secrets.json`. |
| Optional env vars | `GSC_CONFIG_DIR` (default `~/.config/gsc-reader`), `GSC_REPORTS_DIR` (default `./gsc-reports`), `GSC_LOGIN_HINT` (your Google email, pre-selects it at login), `GSC_IGNORE_WORDS` (town words for redirect-check). |

The full click-by-click walk-through is in the `analytics-access-setup` skill, section 5.

## Install

```bash
cp -r search-console ~/.claude/skills/
cd ~/.claude/skills/search-console
python3 -m pip install -r requirements.txt     # on Ubuntu/Debian system Python: python3 -m venv .venv && . .venv/bin/activate first
mkdir -p ~/.config/gsc-reader && chmod 700 ~/.config/gsc-reader
mv ~/Downloads/<downloaded-client-file>.json ~/.config/gsc-reader/client_secrets.json && chmod 600 ~/.config/gsc-reader/client_secrets.json
```

## First run (2 minutes)

```bash
python3 scripts/gsc.py --help                    # no network, no login needed
python3 scripts/gsc.py login                     # browser opens; sign in; "Google hasn't verified this app" is expected: Continue, Allow
python3 scripts/gsc.py properties                # your sites
python3 scripts/gsc.py performance sc-domain:example.com --days 28
```

On a machine without a browser, run `login` on your laptop and copy `token.json` into the same folder on the server (`chmod 600`).

Or ask Claude: "pull Search Console for example.com: what are my striking distance queries?"

## Common errors and fixes

| You see | Fix |
|---|---|
| `Google libraries missing` | `pip install -r requirements.txt` in the same Python you run the script with. |
| `Missing OAuth key at .../client_secrets.json` | Download the Desktop app client JSON and save it under that exact name, or set `GSC_CONFIG_DIR`. |
| `Not signed in` | Run `gsc.py login`. |
| `invalid_grant` / expired | Testing-mode logins last 7 days. Run `login` again, or publish the app (needs home page and privacy policy URLs). |
| "Access blocked: app has not completed verification" | The account is not a test user. Add it under Audience > Test users. |
| `Refusing token with extra scopes` | The client asked for more than read-only. Delete `token.json` and log in again; do not add scopes. |
| `Search Console API error 403` | API not enabled in this project, or your account has no access to that property. |
| Site missing from `properties` | Add your Google account as a user on the property; check `sc-domain:` vs `https://` form. |
| `sitemaps` empty on a domain property | The sitemap was submitted under a URL-prefix property. Use `--base` with the live site. |
| SSL certificate errors on macOS | `pip install certifi` (the script uses it automatically). |

## Setup time

About 15 minutes once (Cloud project, consent screen, client file, login). Later logins take 1 minute.

## API cost

Free. Search Console API quotas are generous; URL Inspection allows about 2,000 calls per property per day. All free except your time.
