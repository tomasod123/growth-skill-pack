#!/usr/bin/env bash
# Adds this skill's env vars to the shared pack env file and prints where to get each key.
# Usage: bash ~/.claude/skills/cold-email-starter-kit/scripts/setup-env.sh

set -e
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$HOME/.claude/skills/.env"
mkdir -p "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"

added=0
while IFS= read -r line; do
  case "$line" in
    ''|'#'*) continue ;;
  esac
  key="${line%%=*}"
  if ! grep -q "^${key}=" "$ENV_FILE"; then
    echo "$line" >> "$ENV_FILE"
    added=$((added + 1))
  fi
done < "$SKILL_DIR/.env.example"

echo "Added $added new vars to $ENV_FILE (existing vars left untouched)."
echo ""
echo "Now open $ENV_FILE and fill in your API keys:"
echo "  Dynadot:    dynadot.com > My Info > API (Tools > API) > generate key + whitelist your IP"
echo "  Zapmail:    zapmail.ai > Settings > API > copy token"
echo "  Prospeo:    app.prospeo.io > Settings > API (prospeo.io/app/settings/api) > copy key"
echo "  Smartlead:  app.smartlead.ai > Settings > API Keys > Create"
echo "  Instantly:  app.instantly.ai > Settings > Integrations > API Keys (API v2 key)"
echo ""
echo "Then run:  set -a; source $ENV_FILE; set +a"
echo "           npx tsx $SKILL_DIR/scripts/verify-credentials.ts"
