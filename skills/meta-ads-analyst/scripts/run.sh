#!/bin/bash
# Example wrapper for a recurring live-data audit (meta-ads-analyst live data mode).
# Pulls Meta + GHL into a dated folder, then (optionally) asks headless Claude to write the report.
#
#   bash run.sh                 # pulls + report
#   SKIP_CLAUDE=1 bash run.sh   # pulls only
#
# Schedule it with your own scheduler, e.g. crontab (Mon/Wed/Fri 08:15 local time):
#   see SETUP.md "Recurring audit" for the full crontab (PATH line, OUT_ROOT, log file).
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_ROOT="${OUT_ROOT:-$PWD/meta-ads-analyst-output}"
DAY="$(date +%F)"
DIR="$OUT_ROOT/$DAY"
mkdir -p "$DIR"

# shared env file (META_ACCESS_TOKEN, META_AD_ACCOUNT_ID, GHL_API_KEY, GHL_LOCATION_ID, ...)
if [ -f "$HOME/.claude/skills/.env" ]; then set -a; . "$HOME/.claude/skills/.env"; set +a; fi
export SSL_CERT_FILE="${SSL_CERT_FILE:-$(python3 -m certifi 2>/dev/null || true)}"

python3 "$SKILL_DIR/scripts/meta_pull.py" --out "$DIR/meta.json" >/dev/null
echo "meta pull OK -> $DIR/meta.json"

if [ -n "${GHL_API_KEY:-}" ] && [ -n "${GHL_LOCATION_ID:-}" ]; then
  python3 "$SKILL_DIR/scripts/ghl_pull.py" --days 7 --out "$DIR/ghl.json" ${GHL_PULL_ARGS:-} >/dev/null
  echo "ghl pull OK -> $DIR/ghl.json"
else
  echo "GHL vars not set: Meta-only run"
fi

[ "${SKIP_CLAUDE:-0}" = "1" ] && exit 0

PROMPT="Use the meta-ads-analyst skill in live data mode. The pulls are in ${DIR} (meta.json, ghl.json if present). \
Do not re-pull. funnel_math.py needs no env file: run it directly with python3 and the absolute skill path. \
Write the report to ${DIR}/report.md and ${DIR}/report.html. \
If SLACK_BOT_TOKEN and SLACK_CHANNEL_ID are set, post the DO THIS WEEK list and the file path as ONE message. \
Internal audit only: never send anything to a client."
# Headless runs cannot answer permission prompts. CLAUDE_ALLOWED_TOOLS is passed as ONE --allowedTools value
# (default below lets Claude read/write files and run python3 only; add ,Bash(curl:*) for the Slack post).
# CLAUDE_ARGS adds any other flags, space-separated, no quoted values (e.g. "--model sonnet").
CLAUDE_ALLOWED_TOOLS="${CLAUDE_ALLOWED_TOOLS:-Read,Write,Edit,Glob,Grep,Bash(python3:*)}"
command -v claude >/dev/null || { echo "claude not on PATH (cron: add its folder to the crontab PATH line)"; exit 1; }
# shellcheck disable=SC2086
claude -p "$PROMPT" --allowedTools "$CLAUDE_ALLOWED_TOOLS" ${CLAUDE_ARGS:-}
