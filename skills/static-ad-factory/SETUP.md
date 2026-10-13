# static-ad-factory setup

## What it does
Researches competitor static ads in the Meta Ads Library, turns the long-running structures into concepts built on distinct reasons to buy, and renders them with OpenAI gpt-image.
QCs every image (text, claims, phone numbers, safe zones, crop proof) and ships a launch-ordered folder per Meta size plus an approval spreadsheet.

## What you need
- `OPENAI_API_KEY`: platform.openai.com > API keys > Create new secret key. gpt-image models need organisation verification: platform.openai.com > Settings > Organization > General > Verify organization (ID check). Add credit first (Settings > Billing); auto top-up does not start from a zero balance.
- `APIFY_TOKEN` (only for fresh scrapes): console.apify.com > Settings > API & Integrations > Personal API token. The actor used is `curious_coder/facebook-ads-library-scraper` (pay per result; check its price on the actor page).
- Python 3.9+: `pip install openai pillow numpy openpyxl`
- tesseract for phone and Stories checks: `sudo apt install tesseract-ocr` or `brew install tesseract`.
- Optional: `pip install "rembg[cpu]"` (background removal for real-person composites), `ffmpeg` (pull frames from video), `rclone` configured with a Google Drive remote (only if you share via Drive and use fetch_feedback.py or --patch-sheet-id: `rclone config` > new remote > drive).
- Claude Code with subagents (classification, vision tagging, concept writing and QC run as parallel agents).
- No MCP servers required.

## Install
1. Copy this folder to `~/.claude/skills/static-ad-factory/`.
2. Add the vars from `.env.example` to `~/.claude/skills/.env`.
3. `cp ~/.claude/skills/static-ad-factory/config/ranking.example.json ~/.claude/skills/static-ad-factory/config/ranking.json` (adjust caps and launch count later).
4. Test without spending anything (each line is one self-contained command):
```bash
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/scrape_ads_library.py --query "hair transplant" --country GB --count 200 --dry-run
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/render.py --help
tesseract --version
```
Free key checks (no image generated, no actor run):
```bash
# OpenAI: a JSON list of models = key works; look for "gpt-image" in it. 401 = bad key.
set -a; source ~/.claude/skills/.env; set +a; curl -s https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY" | grep -o '"gpt-image[^"]*"' | sort -u
# Apify (only if you scrape): your username and plan = token works. 401 = bad token.
set -a; source ~/.claude/skills/.env; set +a; curl -s https://api.apify.com/v2/users/me -H "Authorization: Bearer $APIFY_TOKEN" | head -c 300; echo
```
The OpenAI check proves the key, not organisation verification or credit; the first one-image render probe proves those (about US$0.07).

## First run (2 minutes)
Type: `Use static-ad-factory: research what static ads are working for <niche> in <country>, then write 30 concepts for <offer> aimed at <audience>. Stop before rendering so I can approve the brief.`
You get the scrape cost estimate (it asks before spending), then a ranked competitor set, structure families, a brief to approve and a concept list with distinct reasons to buy. After you approve, it renders, QCs and stages everything under `./static-ad-factory-output/<project>/` (renders/, work/stage_review/ with contact sheets, data/review_sheet.xlsx; after approval work/ratios/<size>/ and data/run_sheet.xlsx).

## Common errors and fixes
- OpenAI key check prints nothing: the key is wrong or the gpt-image models are not listed for your organisation. Run the curl without the `grep` to see the error.
- OpenAI 403 "organization must be verified" on gpt-image: verify the organisation (see above); it can take a few minutes to apply.
- Renders fail with `insufficient_quota` mid-batch: out of credit. The renderer stops instead of retrying; top up, then re-run (existing files are skipped).
- A fixed concept still shows the old image: the renderer skips existing files. Delete that render or pass `--force --ids-file`.
- Text in the Stories top or bottom band: expected from the model; `make_story.py` detects it and rebuilds into the safe area.
- 4:5 version cut through a CTA bar: you used a blind centre crop. Use `make_ratios.py`, which only removes rows measured flat.
- `rclone copy --ignore-existing` left a broken image live: drop the flag for re-renders, delete the old file by name if the headline changed.
- Image reads stop working in the Claude session: an image over 2000 px was read in a batch. Downscale, start a new session, read one image at a time.
- Ads Library image downloads fail: the URLs expired. Recover from the original payload's `snapshot.images` / `cards` before paying for a re-scrape.

## Setup time
20 minutes (most of it OpenAI organisation verification).

## Cost per run
About US$0.07 per medium 1024x1024 image (gpt-image-2 at the time of writing): 30 concepts x 3 sizes is roughly US$6-8. A fresh Ads Library scrape is roughly US$0.75 per 1,000 ads. Reusing an old scrape is free.
