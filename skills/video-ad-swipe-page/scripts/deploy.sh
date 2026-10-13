#!/usr/bin/env bash
# OPTIONAL step 8: deploy a rendered swipe page to Netlify (unlisted, noindex) and verify it live.
# Any static host works; this is just the Netlify CLI path. Skip it and send the folder instead.
#
# Usage: deploy.sh <abs site dir> <site-name> [grep-phrase]
#   deploy.sh "$PWD/video-ad-swipe-page-output/clinic-a/video-swipe-20260903/site" clinic-a-swipe "Filming kit"
#
# Needs: npm i -g netlify-cli, and NETLIFY_AUTH_TOKEN in the environment
#        (set -a; source ~/.claude/skills/.env; set +a). NETLIFY_ACCOUNT_SLUG is optional.
# Gotchas baked in:
#  - never a bare `netlify deploy` inside a folder that is already linked to another site:
#    it deploys over that site. Always pass --site <id>.
#  - sites:create can crash yet still create the site; always re-list before giving up
#  - --no-build (a build step can die on "Failed retrieving extensions" for a static folder)
#  - verify from the LIVE url, never from the CLI's own success line
#  - Netlify accounts have a site cap; reuse one site with sub-folders if you publish many pages
set -euo pipefail
DIR="${1:?abs site dir}"; NAME="${2:?netlify site name}"; PHRASE="${3:-Filming kit}"
[[ "$DIR" = /* ]] || { echo "site dir must be absolute"; exit 1; }
[[ -f "$DIR/index.html" ]] || { echo "no index.html in $DIR"; exit 1; }
[[ -n "${NETLIFY_AUTH_TOKEN:-}" ]] || { echo "NETLIFY_AUTH_TOKEN not set; skipping deploy (the page is at $DIR/index.html)"; exit 0; }
grep -qi 'name="robots" content="noindex' "$DIR/index.html" || { echo "ABORT: page lost its noindex meta"; exit 1; }
grep -q '{{[A-Z_]*}}' "$DIR/index.html" && { echo "ABORT: unfilled {{TOKENS}} in page"; exit 1; }

find_site() { netlify api listSites 2>/dev/null | python3 -c "import sys,json;print(next((s['id'] for s in json.load(sys.stdin) if s['name']=='$NAME'),''))"; }
SITE_ID=$(find_site)
if [[ -z "$SITE_ID" ]]; then
  echo "creating site $NAME"
  if [[ -n "${NETLIFY_ACCOUNT_SLUG:-}" ]]; then
    netlify sites:create --name "$NAME" --account-slug "$NETLIFY_ACCOUNT_SLUG" >/dev/null 2>&1 || true
  else
    netlify sites:create --name "$NAME" >/dev/null 2>&1 || true
  fi
  SITE_ID=$(find_site)
  [[ -n "$SITE_ID" ]] || { echo "site create failed"; exit 1; }
fi
echo "site $NAME -> $SITE_ID"
mkdir -p "$DIR/.netlify"; printf '{"siteId":"%s"}\n' "$SITE_ID" > "$DIR/.netlify/state.json"
netlify deploy --no-build --prod --dir "$DIR" --site "$SITE_ID" >/dev/null
URL="https://$NAME.netlify.app"
sleep 3
if curl -sL "$URL" | grep -qi "$PHRASE"; then echo "LIVE  $URL  (found: $PHRASE)"; else echo "DEPLOYED BUT PHRASE NOT FOUND: $URL"; exit 2; fi
