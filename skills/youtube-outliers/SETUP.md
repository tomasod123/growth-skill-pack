# youtube-outliers: setup

## What it does
Finds YouTube videos that beat their channel's normal views by a wide margin, in your own niche (what your market wants now) or adjacent niches (hooks and titles that work on any audience).
Pulls transcripts and writes a ranked report with hook tags, then Claude turns the top ones into titles, hooks and angles for your niche.

## What you need
- Python 3.8+. The script itself is stdlib only.
- `YOUTUBE_API_KEY` (recommended, free): Google Cloud Console (console.cloud.google.com) > create or pick a project > APIs & Services > Library > search "YouTube Data API v3" > Enable > APIs & Services > Credentials > Create credentials > API key. Restrict it to the YouTube Data API v3.
- Transcripts: `pip install youtube-transcript-api` (free).
- Optional, no API key route: `pip install -U yt-dlp` (laptop only; blocked on most servers).
- Optional `APIFY_TOKEN` (transcript fallback): Apify Console (console.apify.com) > Settings > API & Integrations > Personal API tokens.
- Optional `TUBELAB_API_KEY` (`--source tubelab`, paid credits): tubelab.net > your account > API.
- Optional `ANTHROPIC_API_KEY` (`--summarize`, `--variants`): console.anthropic.com > Settings > API keys. Not needed if you let Claude Code do the analysis in-session.
- Optional `OUTLIERS_MODEL`: the Anthropic model id used by `--summarize` / `--variants` (default `claude-sonnet-4-5`). Set it to any current model id from docs.anthropic.com > Models if the default is retired or you want a cheaper one. Leave blank otherwise.
- Optional `APIFY_TRANSCRIPT_ACTOR`: the Apify actor used for the transcript fallback (default `karamelo/youtube-transcripts`). Only change it if that actor stops working or changes its output: pick another YouTube transcript actor in Apify Store (apify.com/store, search "youtube transcript") and paste its id as `owner/actor-name`.

## Install
1. Copy this folder to `~/.claude/skills/youtube-outliers/`.
2. Add the vars you use from `.env.example` to `~/.claude/skills/.env`.
3. `pip install youtube-transcript-api` (and `yt-dlp` if you want the no-key route).
4. In your working folder: `cp ~/.claude/skills/youtube-outliers/config.example.json outliers-config.json` and edit the keywords and channels.
5. Test from that folder (no calls): `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/youtube-outliers/scripts/find_outliers.py --config outliers-config.json --mode own --dry-run`

## First run (2 minutes)
Type: `Find YouTube outliers in my niche from the last 14 days and tell me which hooks to steal.`
Claude loads the env, runs a dry run to show the cost, runs the own-niche search, then reads the top transcripts and returns a pattern table (original title, formula, hook type, why it worked, your adapted title and first line). Files land in `./youtube-outliers-output/<date>-own/` (`report.md`, `outliers.csv`, `outliers.json`, `transcripts/`).

## Common errors and fixes
- **"YouTube API quota exhausted".** A search costs 100 of 10,000 daily units. Cut keywords or `per_keyword`, wait for the midnight Pacific reset, or use `--source ytdlp` on a laptop.
- **yt-dlp returns nothing / "confirm you're not a bot".** YouTube blocks it from cloud IPs. Use `--source youtube-api`.
- **"transcript: none" on every video.** youtube-transcript-api is IP-blocked or the video has no captions. Set `APIFY_TOKEN` for the fallback, or `--no-transcripts` and work from titles.
- **"nothing to score" or zero outliers.** Widen `--days`, lower `--min-score`, add keywords, or lower `min_views`. Channels need at least 3 other recent uploads for a baseline.
- **Report full of tiny channels.** Raise `min_views` in the config (e.g. 10000).
- **Adjacent mode still shows competitors.** Add their topic words to `own_niche_terms`.

## Setup time
10 minutes (5 of them creating the Google Cloud API key).

## Cost per run
Free with the YouTube Data API free quota (about 1,000-1,500 of 10,000 daily units for 10 keywords). Optional: Apify transcript fallback about US$0.01-0.05 per video; TubeLab about 5 credits per keyword; `--summarize`/`--variants` a few cents per video on the Anthropic API.
