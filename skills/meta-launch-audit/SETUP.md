# meta-launch-audit setup

## What it does
Read-only pre-launch and live audit of a Meta ad account: targeting map, structure, tracking, lead form, copy compliance, creative QC, lead path and payback.
Writes one AUDIT.md with a verdict (DO NOT LAUNCH / LAUNCH + fix / READY) and a ranked fix list with click paths, owner and minutes.

## What you need
- A Meta Business account with access to the ad account you want to audit.
- `META_ACCESS_TOKEN`: Meta Business Settings > Users > System users > Add (role Employee is enough) > Assign assets > the ad account (View performance) > Generate new token, pick your app, token expiration **Never**, scopes `ads_read` (add `pages_read_engagement` and `leads_retrieval` if you want lead forms to be readable). If you have no app yet: developers.facebook.com > My Apps > Create app > Business, then add the Marketing API product. Keep it read-only; the audit never writes.
- `META_AD_ACCOUNT_ID`: Ads Manager > account dropdown (top left) > the number under the account name, or Business Settings > Accounts > Ad accounts. Digits only or `act_XXXXXXXXXX`.
- `META_GRAPH_VERSION` (optional): Graph API version, default `v21.0`. When Meta retires it (errors mention an unsupported or deprecated version), set the current one from developers.facebook.com/docs/graph-api/changelog, for example `v22.0`.
- `OPENAI_API_KEY` (optional, video transcripts in step 4): platform.openai.com > API keys > Create new secret key.
- Python 3.9+ with `pip install pillow certifi` (contact sheet, SSL).
- For `creative_qc.py`: `pip install "opencv-python-headless<5" numpy pillow` and tesseract (`sudo apt install tesseract-ocr` or `brew install tesseract`). Optional: `ffmpeg` for video frame grabs.
- No MCP servers required.

## Install
1. Copy this folder to `~/.claude/skills/meta-launch-audit/`.
2. Add the vars from `.env.example` to `~/.claude/skills/.env`.
3. `cp ~/.claude/skills/meta-launch-audit/config/thresholds.example.json ~/.claude/skills/meta-launch-audit/config/thresholds.json` and fill the numbers from your own last 90 days (the file's `_how_to_set` explains each). Anything left null is skipped and listed in AUDIT.md as "threshold not set, skipped".
4. Test:
```bash
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/meta-launch-audit/scripts/meta_audit.py --help
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/meta-launch-audit/scripts/meta_audit.py --act "$META_AD_ACCOUNT_ID" --mode b2b --config ~/.claude/skills/meta-launch-audit/config/thresholds.json --out ./meta-launch-audit-output/test
```
The second call is read-only; if the token works, `AUDIT.md` lists the account's campaigns.

## First run (2 minutes)
Type: `Run the meta launch audit on our ad account before we switch on. Business location is <address or postcode>, town <town>, market UK, local mode.` (for B2B: `...mode b2b, national targeting`).
You get back the verdict, the P0 list with click paths, and a contact sheet of every creative scored on the seven visual checks. Files land in `./meta-launch-audit-output/<date>/` (AUDIT.md, raw.json, creatives/, contact-sheet.jpg).

## Common errors and fixes
- `META_ACCESS_TOKEN is not set`: run `set -a; source ~/.claude/skills/.env; set +a` in the same shell first.
- "Account status not readable by this token" or forms "not readable by API": the system user lacks that asset or scope. Assign the ad account / Page in Business Settings, or check that item by eye (normal for lead forms).
- Business shows as OUTSIDE its own targeted circle: the ad set uses a region "place" with a radius, which centres on the region's middle. Replace it with a pin or address on the business.
- Lead counts look double: only `action_type == 'lead'` is counted on purpose; other tools that substring-match "lead" add grouped lead actions twice.
- `creative_qc.py` crashes on `CascadeClassifier`: you have OpenCV 5. `pip install "opencv-python-headless<5"`.
- Postcode lookup returns nothing outside the UK: use `--latlon "lat,lon"` instead of `--postcode`.
- AUDIT.md has a "Checks skipped (threshold not set)" section: those thresholds are null in your thresholds.json, or you forgot `--config`. Fill them in to switch the checks on.
- Meta error about an unsupported or deprecated API version: set `META_GRAPH_VERSION` in `~/.claude/skills/.env`.
- Downloaded video is 576 px wide: Meta returned the low-res upload; use the original master file for review.

## Setup time
15 minutes (most of it creating the Meta system user token).

## Cost per run
Free (Meta Graph API and postcodes.io are free). Optional Whisper transcription is about US$0.006 per minute of video.
