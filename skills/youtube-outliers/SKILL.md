---
name: youtube-outliers
description: Find YouTube outlier videos (far above the channel's normal views) in your own niche (competitor and market intel) or in adjacent niches (transferable hooks, title structures and formats), pull their transcripts, tag hook patterns, and turn them into titles, hooks and video or ad angles for your niche. Writes a local report, CSV and transcripts folder. Use when the user says "YouTube outliers", "what's going viral in my niche", "find viral videos", "competitor YouTube", "cross-niche outliers", "content inspiration", "hook ideas from YouTube", "title ideas", or "what video topics should we make".
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./youtube-outliers-output/`.

# YouTube outliers (own niche + adjacent niche)

## Goal
Find the videos that beat their own channel's normal by a wide margin, then work out why
and what to borrow. Own-niche outliers tell you which topics and angles your market wants
right now. Adjacent-niche outliers tell you which packaging (title, hook, structure) works
on any audience, without copying a competitor.

## Before running
1. Work from the user's working folder (not the skill folder): config and outputs live there,
   so reinstalling the skill never touches them. Each Bash call is a fresh shell, so every
   script command starts with `set -a; source ~/.claude/skills/.env; set +a;` in the same call
   and calls the script by its absolute path. Recommended: `YOUTUBE_API_KEY`.
   Optional: `APIFY_TOKEN` (transcript fallback), `TUBELAB_API_KEY`, `ANTHROPIC_API_KEY`.
2. Config: if `./outliers-config.json` (or a path the user gives) doesn't exist, copy
   `~/.claude/skills/youtube-outliers/config.example.json` there and fill it with the user: one line on the niche, 5-10 own-niche
   keywords (in the buyer's words), 3-10 competitor channels, 5-10 adjacent keywords,
   and `own_niche_terms` (words that mark a title as your niche, dropped in adjacent mode).
3. Run `--dry-run` first (`set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/youtube-outliers/scripts/find_outliers.py --config outliers-config.json --mode own --dry-run`): it prints the keyword list, channels and estimated quota/credits.

## Steps
1. **Own niche** (weekly):
   `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/youtube-outliers/scripts/find_outliers.py --config outliers-config.json --mode own --days 14`
2. **Adjacent niche** (monthly):
   `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/youtube-outliers/scripts/find_outliers.py --config outliers-config.json --mode adjacent --days 30`
3. **Read the output** in `./youtube-outliers-output/<date>-<mode>/`: `report.md` (top
   outliers with score, channel median, views, age, hook tags), `transcripts/<id>.txt`,
   `outliers.csv` (import into Google Sheets or Excel if you want a sheet), `outliers.json`.
4. **Analyse the top 5-10 yourself** in-session using `references/hook-patterns.md`: title
   formula, hook in the first 30 seconds of the transcript, structure, why it beat the
   channel, and one adapted title + first line for the user's niche. Hand back the pattern
   table from that file. (Or pass `--summarize --variants 3` to have the script do a first
   pass through the Anthropic API.)
5. **Hand off** (optional): adapted hooks feed ad scripts and statics (`static-ad-factory`,
   `video-ad-swipe-page`, `ad-library` if installed); check any health or outcome claim
   with `persona-qc`'s compliance lens before it goes in an ad.

## Flags
| Flag | Default | Notes |
|---|---|---|
| `--mode own/adjacent` | own | adjacent drops own-niche titles and applies hook/format weights |
| `--source auto/youtube-api/ytdlp/tubelab` | auto | auto = youtube-api if `YOUTUBE_API_KEY` set, else yt-dlp |
| `--keywords "a,b"` / `--channels "@x,UC..."` | from config | one-off override |
| `--days N` | 14 own / 30 adjacent | max video age |
| `--min-score X` | 2.0 own / 1.5 adjacent | lower it if nothing comes back |
| `--top N` | 20 | how many get transcripts and report entries |
| `--no-transcripts` | off | faster |
| `--summarize`, `--variants N` | off | need `ANTHROPIC_API_KEY` |
| `--out DIR` | `./youtube-outliers-output/<date>-<mode>` | |
| `--dry-run` | off | plan + cost estimate, no calls |

## How the score works
Views divided by the channel's median over its recent uploads (excluding the video),
times a recency boost (newer videos have had less time). Adjacent mode then penalises
formats that rarely transfer (setups, vlogs, reactions, news) and rewards proven hook
types (money, curiosity, transformation, contrarian, speed, urgency, a number). Details
and tuning notes: `references/hook-patterns.md`.

## Gotchas
- **yt-dlp on cloud servers** gets "Sign in to confirm you're not a bot" and returns
  nothing. Use `--source youtube-api` there; yt-dlp is fine on a laptop for small runs.
- **YouTube API quota:** a search costs 100 units of the free 10,000/day; video and
  playlist lookups cost 1. Ten keywords at 30 results is about 1,000-1,500 units. Quota
  resets at midnight Pacific.
- **Transcripts:** `youtube-transcript-api` changed its API at v1.0 (instance `.fetch()`
  instead of `get_transcript`); the script handles both. It gets IP-blocked quickly from
  servers; then the Apify fallback runs if `APIFY_TOKEN` is set. If the default actor's
  output changes, set `APIFY_TRANSCRIPT_ACTOR` to another YouTube transcript actor.
- **Short-heavy niches:** videos of 60 s or less are dropped; Shorts follow different
  view dynamics.
- **Small channels** can show 50x ratios on tiny view counts. Raise `min_views` in the
  config if the top of the report is full of 2,000-view videos.
- **TubeLab** allows about 10 requests a minute and each search costs credits; the
  script waits between calls.
