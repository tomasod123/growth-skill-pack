#!/usr/bin/env bash
# Read-only probe: confirm the GHL Private Integration token can read contacts,
# conversations and (critically) conversation MESSAGES, the scope call recordings need.
# Prints pass/fail. NEVER prints the token.
# Env: GHL_API_KEY, GHL_LOCATION_ID  (load: set -a; source ~/.claude/skills/.env; set +a)
# Needs: curl, jq
set -uo pipefail
: "${GHL_API_KEY:?missing GHL_API_KEY - run: set -a; source ~/.claude/skills/.env; set +a}"
: "${GHL_LOCATION_ID:?missing GHL_LOCATION_ID}"
BASE="https://services.leadconnectorhq.com"
V="Version: 2021-07-28"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

C_CODE=$(curl -s -o "$TMP/c.json" -w '%{http_code}' -H "Authorization: Bearer $GHL_API_KEY" -H "$V" \
  "$BASE/contacts/?locationId=$GHL_LOCATION_ID&limit=5")
echo "contacts:              HTTP=$C_CODE (returned $(jq -r '.contacts | length' "$TMP/c.json" 2>/dev/null || echo '?'))"

S_CODE=$(curl -s -o "$TMP/s.json" -w '%{http_code}' -H "Authorization: Bearer $GHL_API_KEY" -H "$V" \
  "$BASE/conversations/search?locationId=$GHL_LOCATION_ID&limit=5")
CONV=$(jq -r '.conversations[0].id // empty' "$TMP/s.json" 2>/dev/null)
echo "conversations:         HTTP=$S_CODE (total ~$(jq -r '.total // (.conversations|length) // "?"' "$TMP/s.json" 2>/dev/null))"

if [ -n "${CONV:-}" ]; then
  M_CODE=$(curl -s -o "$TMP/m.json" -w '%{http_code}' -H "Authorization: Bearer $GHL_API_KEY" -H "$V" \
    "$BASE/conversations/$CONV/messages?limit=40")
  NCALL=$(jq -r '[.messages.messages[]? | select(.type==1)] | length' "$TMP/m.json" 2>/dev/null || echo '?')
  echo "messages (recordings): HTTP=$M_CODE (calls in sample=$NCALL)"
  if [ "$M_CODE" = "401" ] || [ "$M_CODE" = "403" ]; then
    echo ">> SCOPE MISSING: add 'View Conversation Messages' to the Private Integration and use the new token"
  fi
else
  echo "messages (recordings): SKIPPED (no conversation to test)"
fi
