#!/bin/bash
# ad-snippet-miner weekly wrapper (optional). Schedule it HOURLY with cron; it gates itself
# on your timezone so the digest lands Monday morning year-round regardless of server tz.
# The 3-hour window gives two retries if a run fails; the per-ISO-week stamp guarantees
# at most ONE digest per week (noise budget).
#
# Example crontab line (see SETUP.md; put the folder that holds `claude` on PATH):
#   7 * * * * PATH="$HOME/.npm-global/bin:/usr/local/bin:/usr/bin:/bin" "$HOME/.claude/skills/ad-snippet-miner/scripts/run_weekly.sh"
#
# Settings (in ~/.claude/skills/.env, in the crontab line, or in the environment):
#   MINER_TZ       timezone for the Monday gate (default Europe/London)
#   MINER_WORKDIR  where digests + ledger.db live (default: $HOME/ad-snippet-miner-output,
#                  OUTSIDE the skill folder so reinstalling the skill never wipes the ledger)
#   MINER_CONFIG   path to your config.json (optional)
#   MINER_SLACK=1  also post to Slack (needs SLACK_BOT_TOKEN + SLACK_CHANNEL_ID)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"

# Shared env file for the skill pack (cron does not load your shell profile).
# Loaded FIRST so MINER_* values set there take effect.
set -a
. "$HOME/.claude/skills/.env" 2>/dev/null
set +a

TZN="${MINER_TZ:-Europe/London}"
OUT="${MINER_WORKDIR:-$HOME/ad-snippet-miner-output}"
OUT="${OUT/#\~/$HOME}"
export MINER_WORKDIR="$OUT"
mkdir -p "$OUT"
STAMP="$OUT/.last_sent_week"
DOW=$(TZ="$TZN" date +%u)    # 1 = Monday
HOUR=$(TZ="$TZN" date +%H)
WEEK=$(TZ="$TZN" date +%G-W%V)

[ "$DOW" = "1" ] || exit 0
case "$HOUR" in 08|09|10) ;; *) exit 0 ;; esac
[ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$WEEK" ] && exit 0

CCMD="${MINER_CLAUDE_CMD:-claude}"
if ! command -v "${CCMD%% *}" >/dev/null 2>&1; then
  echo "$(date -u +%FT%TZ) claude CLI not on PATH ($PATH): add its folder to PATH in the crontab line or set MINER_CLAUDE_CMD" >> "$OUT/miner.log"
  exit 1
fi

ARGS=(--days 7 --write --out "$OUT")
[ -n "${MINER_CONFIG:-}" ] && ARGS+=(--config "$MINER_CONFIG")
[ "${MINER_SLACK:-0}" = "1" ] && ARGS+=(--slack)

echo "=== $(date -u +%FT%TZ) ad-snippet-miner run (week $WEEK) ===" >> "$OUT/miner.log"
if python3 "$HERE/miner.py" "${ARGS[@]}" >> "$OUT/miner.log" 2>&1; then
  echo "$WEEK" > "$STAMP"
else
  echo "$(date -u +%FT%TZ) run FAILED - will retry next gated hour" >> "$OUT/miner.log"
fi
