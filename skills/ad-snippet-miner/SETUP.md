# ad-snippet-miner: setup

## What it does
Reads the last week of Fathom call transcripts and pulls out verbatim customer quotes worth using in ads (praise, results, before-pain), rated 1-5 with clip times and consent status.
Writes a weekly Markdown + HTML digest locally; optionally posts it to Slack.

## What you need
- A Fathom account that records your customer calls (any plan with API access).
- `FATHOM_API_KEY`: in Fathom go to Settings > API Access (under Integrations) > Generate API key. Copy it once; it is shown only at creation.
- Claude Code CLI on PATH (`claude -p` must work in your terminal; it does the mining). Install: `npm install -g @anthropic-ai/claude-code`, then run `claude` once to log in.
- Python 3.8+ (stdlib only). Optional: `pip install certifi` if your Python has no CA bundle (macOS python.org builds).
- Optional Slack: `SLACK_BOT_TOKEN` from api.slack.com/apps > your app > OAuth & Permissions > Bot User OAuth Token (scopes `chat:write`, plus `im:write` for DMs). `SLACK_CHANNEL_ID`: your member id (Slack profile > three dots > Copy member ID) for a DM, or a private channel id (channel name > About > bottom). Invite the bot to the channel.

## Install
1. Copy this folder to `~/.claude/skills/ad-snippet-miner/`.
2. Add the vars from `.env.example` to `~/.claude/skills/.env` (only `FATHOM_API_KEY` is required).
3. Pick ONE home for the ledger and digests, outside the skill folder (so reinstalling the skill never wipes the ledger), and point both interactive and cron runs at it by adding to `~/.claude/skills/.env`:
   ```
   MINER_WORKDIR=$HOME/ad-snippet-miner-output
   MINER_CONFIG=$HOME/ad-snippet-miner-output/ad-snippet-miner-config.json
   MINER_TZ=Europe/London
   ```
   (`MINER_TZ` = your IANA timezone, e.g. `America/New_York`; add `MINER_SLACK=1` only if the weekly run should post to Slack.) Then: `mkdir -p ~/ad-snippet-miner-output && cp ~/.claude/skills/ad-snippet-miner/config.example.json ~/ad-snippet-miner-output/ad-snippet-miner-config.json` and fill in your business line, your own team names and known customers.
4. Test (read-only): `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ad-snippet-miner/scripts/miner.py --check-fathom`
5. Optional weekly run (macOS or Linux cron). Cron has a minimal PATH, so find the folder that holds `claude` with `dirname "$(command -v claude)"` (often `$HOME/.npm-global/bin`, `/usr/local/bin`, or `$(npm prefix -g)/bin`; under nvm it is `$HOME/.nvm/versions/node/<version>/bin`). Then `crontab -e` and add this one line, with that folder first on PATH:
   ```
   7 * * * * PATH="$HOME/.npm-global/bin:/usr/local/bin:/usr/bin:/bin" MINER_WORKDIR="$HOME/ad-snippet-miner-output" MINER_CONFIG="$HOME/ad-snippet-miner-output/ad-snippet-miner-config.json" /bin/bash "$HOME/.claude/skills/ad-snippet-miner/scripts/run_weekly.sh"
   ```
   It fires hourly and only runs Monday 08:00-10:59 in `MINER_TZ`, once per week. The `MINER_*` values in the line are optional if they are already in `~/.claude/skills/.env` (the wrapper loads that file first). The log is `$HOME/ad-snippet-miner-output/miner.log`.

## First run (2 minutes)
Type: `Run ad snippet miner on the last 7 days as a dry run.`
Claude loads the env, checks the config, and prints the digest it would write: up to 10 quotes, each with category, rating, a Fathom link to the exact second, clip bounds and consent status. Say "write it" and it lands in `$MINER_WORKDIR/digest-<week>.md` and `.html` (or `./ad-snippet-miner-output/` if `MINER_WORKDIR` is not set).

## Common errors and fixes
- **`BLOCKER: Fathom API returned 401`.** The key is wrong or revoked. Generate a new one in Fathom settings and update `~/.claude/skills/.env`.
- **`claude -p failed rc=...`.** The Claude CLI is not logged in or not on PATH for this shell (cron has a minimal PATH). Run `claude` once interactively; in the crontab line put the folder from `dirname "$(command -v claude)"` first on `PATH=`, or set `MINER_CLAUDE_CMD=/full/path/to/claude`. The wrapper logs "claude CLI not on PATH" to `miner.log` when this is the cause. If you add `--permission-mode bypassPermissions`, note it refuses to run as root.
- **Your own team's lines appear as customer quotes.** ASR speaker labels are guesses. Add every team name (and common misspellings) to `team_names` in the config.
- **Nothing in the digest.** Zero candidates means no file and no message by design. Check `--days`, and that calls have at least 8 transcript segments (short calls are skipped).
- **A quote you already used came back.** It won't with the same ledger: quotes are hash-deduped. If you changed `--out`, or ran from another folder without `MINER_WORKDIR` set, you started a fresh ledger; set `MINER_WORKDIR` to the folder holding the old `ledger.db` (interactive and cron then share it).
- **Slack `not_in_channel` or `channel_not_found`.** Invite the bot to the private channel, or use your member id (U...) for a DM.

## Setup time
10 minutes.

## Cost per run
Fathom API: free with your plan. Mining: one Sonnet pass per new call through your Claude Code plan (roughly 20-60k input tokens per hour of call). Slack: free.
