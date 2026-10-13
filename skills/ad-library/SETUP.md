# ad-library: setup

## What it does
Keeps every competitor and own-client video ad you research in one local JSONL file, with format, offer, fit and quality scores, transcripts, media paths and a survival-based performance proxy.
Query it before any new research (so you never pay for the same scrape twice), feed it from every swipe page, and optionally re-check tracked advertisers weekly from the Meta Ads Library.

## What you need
- **Python 3.9+** on macOS, Linux or WSL (stdlib only; the file lock uses `fcntl`, so native Windows is not supported). `pip install certifi` recommended on macOS for the weekly refresh's TLS.
- **ffmpeg / ffprobe** (dimensions, duration, poster frames at ingest): `brew install ffmpeg` or `sudo apt install ffmpeg`. Without them ingest still works; those fields stay null.
- For the optional weekly refresh only: an **Apify account** (https://console.apify.com).
  - `APIFY_TOKEN`: Apify Console > Settings > API & Integrations > Personal API tokens > copy a token. Uses the public actor `curious_coder/facebook-ads-library-scraper` (about $0.00075 per ad).
- Optional: **Slack** summaries. `SLACK_BOT_TOKEN`: api.slack.com/apps > Create New App > OAuth & Permissions > Bot Token Scopes `chat:write` > Install to Workspace > copy the `xoxb-` token. `SLACK_CHANNEL_ID`: open the channel in Slack > channel name > About > Channel ID (invite the bot to the channel).
- Pairs with the **video-ad-swipe-page** skill (its work dirs ingest straight in).
- Optional extra vars (leave blank unless you need them):
  - `AD_LIBRARY_EXTRA_SCRAPES`: extra scrape files for `raw_scan.py` to read besides `<library>/scrapes/`, as globs separated by `:`, e.g. `$HOME/work/video-ad-swipe-page-output/*/*/raw_ads.json`. Set it if you keep swipe-page work dirs and want their raw scrapes folded into the v2 fields.
  - `AD_LIBRARY_MEDIA_BASE`: base URL if you publish the library's `media/` folder on a static host (e.g. `https://files.example.com/ad-library`). Used to build shareable media links and by `audit.py --http`. Blank = local file paths only.
  - `AD_LIBRARY_POST_CMD`: a shell command `refresh.py` runs only after a passing audit, e.g. your own export or sync step (`rsync -a "$AD_LIBRARY_DIR/" backup:/ad-library/`). Blank = nothing runs.

## Install
1. Copy this folder to `~/.claude/skills/ad-library/`.
2. Add the vars from `.env.example` to `~/.claude/skills/.env`. Set `AD_LIBRARY_DIR` to one fixed folder (e.g. `~/ad-library-data`) so every project shares the same library, and `AD_LIBRARY_MARKETS` to your markets (e.g. `GB,IE,US`).
3. Test (creates the empty library, prints zero counts, touches no network):
   ```
   set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ad-library/scripts/query.py --stats && python3 ~/.claude/skills/ad-library/scripts/audit.py
   ```
   For the refresh: copy `templates/tracked.example.json` to `$AD_LIBRARY_DIR/tracked.json`, put in real page ids, then `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ad-library/scripts/refresh.py --dry-run` prints the plan and cost without spending.

## First run (2 minutes)
The library starts EMPTY: a query on a fresh install returns nothing until you ingest something. Run the **video-ad-swipe-page** skill once first (it writes a work dir with ads, media and scores), or have an Ads Library scrape JSON to hand. Then type: `Add the ads from my last swipe page to the ad library: ./video-ad-swipe-page-output/clinic-a/video-swipe-20261013, niche skin, offer free consultation, market GB.`
Claude runs `ingest.py --dry-run` first, shows you the rows (and any it refused as off-scope), then writes them and prints `query.py --stats`. Once rows exist, try: `What ads do we already have for healthcare software demo offers in the US?` The library lives in `$AD_LIBRARY_DIR/index.jsonl` (default `./ad-library-data/`).

## Common errors and fixes
- **Every query returns 0 rows.** The library is new and empty. Ingest a swipe-page work dir (`ingest.py --from-swipe <workdir>`) or a scrape JSON first; `query.py --stats` shows the counts.
- **`REFUSED: N row(s) are outside the library's scope`.** The off-scope gate caught lawyers, finance, consumer apps and similar from a keyword search. Drop them from the input, or pass `--allow-off-scope` after judging each one. To change what is in scope, edit `OFF_SCOPE` / `NICHES` in `scripts/niche_rules.py`.
- **`REFUSED: ... unclassified or unscored with no reason in notes`.** Add a `notes` reason per row, or pass watched scores with `--scores-json`. Do not use `--allow-unexplained`; it is how a library fills with rows nobody can retrieve.
- **Media paths point at nothing / videos 403.** Facebook CDN links expire in about five days. Download in the same session as the scrape (refresh.py does). With curl, always use `-L` and check the file size: without `-L` you get a 0-byte file and exit code 0.
- **`another ad-library job holds .index.lock`.** A refresh or merge is still running. Wait, or check for a stuck process; never delete the lock while a job runs.
- **Audit fails "country_iso ... contradicted by the ad copy".** The batch `--market` label was wrong for that ad. Re-run `raw_scan.py` then `backfill_v2.py` so the country comes from the search or the copy.
- **Everything ingested lands in your current folder instead of your library.** `AD_LIBRARY_DIR` is not set in this shell. Put `set -a; source ~/.claude/skills/.env; set +a;` in the same Bash call as the script.

## Setup time
5 minutes (10 with the weekly refresh).

## Cost per run
Free for query, ingest, audit and backfill (local only). The weekly refresh costs about $0.00075 per ad returned: roughly $0.20 to $2 a week depending on how many pages and searches you track (aborts over `--budget`, default $2, hard cap $10).
