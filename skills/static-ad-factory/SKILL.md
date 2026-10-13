---
name: static-ad-factory
description: "End-to-end static ad pipeline: scrape competitor ads from the Meta Ads Library, reverse-engineer the structures that last, write concepts around distinct reasons to buy (post-Andromeda diversity), render them with OpenAI gpt-image, QC them (text, claims, phone numbers, safe zones, crop proof), and ship a ranked, launch-ordered folder per Meta size (1:1, 4:5, 9:16) plus an approval spreadsheet. Use when the user says 'static ads', 'new creatives', 'make me N ads', 'what's working in the niche', 'competitor ad research', 'image ads for Meta', or wants a data-backed creative batch for their own business or a client."
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, Agent, WebFetch, WebSearch]
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./static-ad-factory-output/`.

# Static ad factory

Turns "we need new statics" into a reviewed, organised batch built on evidence rather than taste.

Every Bash call that runs a script starts with `set -a; source ~/.claude/skills/.env; set +a; ` in the same command (each Bash call is a fresh shell) and uses the absolute path `~/.claude/skills/static-ad-factory/scripts/...` (needs `OPENAI_API_KEY`; `APIFY_TOKEN` only if you scrape). Run them from the project folder, default `./static-ad-factory-output/<project>/`. File shapes: `references/schemas.md`.

## The principles this encodes
1. **Text load on the image is the biggest lever.** In one past study of a few hundred competitor statics, ads with 3 or fewer text elements ran far longer (median roughly 2-3x) than ads with 7 or more, and the pattern held inside every layout. Default every concept to 3 or fewer; some should carry none. Re-derive the table for each niche (`merge_rank.py` prints it).
2. **Diversity means a different REASON TO BUY, not a different layout.** Meta's public guidance on its Andromeda retrieval system is to supply creatively diverse ads; in practice, look-alike ads compete for the same people, so count them as one concept. Keep a list of reasons to buy and cover as many distinct ones as the budget can feed. Never clone a winning hook into more ads.
3. **Longevity is the public performance proxy.** The Ads Library shows no impressions for most ads, so days running is the honest signal. It also rewards ads nobody switched off; trust the 91-200 day band most.
4. **Rank your own ads by lead QUALITY, not CPL,** when CRM data exists. With small lead counts, CPL differences between ads are usually noise; tagging every lead real or junk the day it lands separates ads far sooner.
5. **Every number passes the claims whitelist** in the brief before it touches an image.

## Phases

### 1. Reuse before you scrape (always)
Check for an existing scrape first (a previous project's `data/raw.json`, or the `ad-library` skill if you have it). Reuse is free.
If a fresh scrape is needed: `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/scrape_ads_library.py --query "<niche words>" --country GB --count 500 --cap-usd 5 --dry-run`, then without `--dry-run`. Apify actor `curious_coder/facebook-ads-library-scraper`, roughly US$0.75 per 1,000 ads (check the actor page). Estimate before firing; keep a hard cap per job. Pair any "no ads found" result with a control query you know has ads, so a broken scrape is not read as "nobody advertises".
Ads Library image URLs expire within days: run `dedupe.py` straight after, which downloads every image. If URLs have expired, recover them from the ORIGINAL payload (`snapshot.images`, `cards`, `extra_images` carry original and resized URLs) before paying to re-scrape.

### 2. Dedupe and qualify
`set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/dedupe.py` collapses to unique statics on (page, normalised body[:120], normalised title[:60]) and computes days running, variants and advertiser scale. Then classify each as a target advertiser or not with parallel subagents in chunks of ~120 (`prompts/classify.md`).

### 3. Vision-tag the structure
Parallel subagents, ~20 images each, one Read per image (`prompts/vision-tag.md`): layout, hook type, audience callout, headline, **text_lines**, density, style, colours, person, proof, CTA, transferable structure. Then `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/merge_rank.py [--prefer-country GB]` merges (complete tags beat null ones), scores, writes the text-load table and a top-40 contact sheet.

### 4. Cluster into structure families
One strong model (`prompts/cluster-families.md`). **60-80 families, not a dozen.** Two ads share a family only if a designer would build them the same way. Each family: recipe, hook pattern, n ads, median and max days, best example, fit, risks.

### 5. Write concepts
One brief (`data/BRIEF.md` from `templates/BRIEF.example.md`): offer, audience, claim whitelist AND blacklist, text-load rule, locale, no em dashes, banned AI-look aesthetics, who may appear, output schema. Put banned claims as regexes in `data/claims_blacklist.txt`. Then parallel agents, one per lane of families (`prompts/write-concepts.md`). Every concept names the reference ad it copies.

### 6. Reason-to-buy dedup (do not skip)
One agent (`prompts/reason-dedup.md`) assigns a reason to buy and trigger to every concept, lists redundancy and missing reasons, then repoints the redundant ones. This routinely more than doubles the number of distinct reasons. Then:
```bash
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/qc_concepts.py --blacklist data/claims_blacklist.txt --locale uk|us
```
It catches banned claims, dashes, wrong-locale words, **sourcing instructions** that must go to a human, banned garments named in an image plan, missing keys, text-line caps, headline length and duplicates.

### 7. Render
```bash
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/render.py --dry-run                         # prints the first prompt and the job count
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/render.py --aspect square --out renders [--ids-file ids.txt] [--variants a]
```
gpt-image-2, medium quality, 5 workers (rate limits bite above about 6). Roughly US$0.07 per medium 1024x1024 image at the time of writing (check current pricing); 250 images is about US$18. Retries 3x with backoff, never returns None, and stops on out-of-credit errors instead of retrying them. Do a cheap one-image probe before a big batch.
**People:** for `needs_asset: "person_photo"`, pass `--ref` with 4-6 crops of the same person from different angles and `--person-brief` (from `templates/person-brief.example.txt`). The renderer adds a "several photos, ONE person, never a second person or reflection" block; without it multi-reference edits sometimes render two people.
Default to one variant per concept to halve time and cost; render both (`--variants ab`) when the owner wants choice. Either way the prompt carries a margin law: large type AND clear margins, never shrink type to fit a long headline.

### 8. QC
Three parallel agents over every render (`prompts/render-qc.md`): (a) spelling and text accuracy vs the concept, (b) claims and brand compliance, (c) would it stop the audience scrolling. Agents read images ONE AT A TIME and every image must be under 2000 px. Re-render failures. Then:
```bash
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/phone_sweep.py renders [--known "<the client's phone digits>"]
```

### 9. Review round
```bash
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/stage_review.py                # flat folder '<ID> - headline.png' + labelled contact sheets
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/build_review_xlsx.py review    # data/review_sheet.xlsx with an Approve / Reject / Maybe dropdown
```
Share the folder and sheet any way you like (optionally Google Drive: `rclone copy`, and `build_review_xlsx.py --patch-sheet-id <id>` to publish over an existing Sheet keeping its URL). Contact sheets with IDs stamped under each image let a reviewer point at a specific ad (folder links are identical for every file inside).

### 10. Read the feedback
The reviewer works in two places: the sheet carries verdicts, file comments carry art direction. With Drive: `set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/fetch_feedback.py --folder-id <id> --sheet-id <id>`.
- Read the dropdowns before looking for prose: "there are 60 of them" usually means 60 rows marked Approve.
- Join every comment to the same reviewer's own verdict before doing work; comments often sit on ads they then rejected.
- Diff against the previous pull and act only on new comments.
- Bucket before editing: deletes, global prompt changes, per-ad copy, per-ad CTA, layout, asset problems. Thirteen "more photorealistic" notes are ONE change to the shared person block.
- Every edit asserts it changed something (`if json.dumps(c, sort_keys=True) == before: sys.exit(...)`).
- Check a requested change against the project's own findings before honouring it (adding a CTA to an ad already at 3 text elements pushes it into the heavy band). Say which you applied and why.

### 11. Rank, fan out to sizes, prove, ship
```bash
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/rank_approved.py --review data/review_sheet.xlsx --config ~/.claude/skills/static-ad-factory/config/ranking.json
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/render.py --aspect vertical --out renders_vert --ids-file approved_ids.txt
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/render.py --aspect story    --out renders_story --ids-file approved_ids.txt
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/make_ratios.py      # 1:1 1080x1080 + 4:5 1080x1350
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/make_story.py       # 9:16 1080x1920, interface bands OCR-verified or rebuilt
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/crop_proof.py       # geometric proof that no copy was cropped
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/stage_approved.py   # flat, launch-ordered folder
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/static-ad-factory/scripts/build_review_xlsx.py run   # READY TO RUN sheet with a column per size + upload tracker
```
Ranking re-ranks within the approved subset only, with caps per painpoint and per style so one angle cannot fill the launch tier. Ship **one flat folder per size with identical filenames** (`NN TIER PAINPOINT IDv - headline.png`) so the media buyer matches sizes by name and loads top to bottom.

## Sizes and safe zones
- Meta sizes: 1:1 1080x1080 (feed, explore), 4:5 1080x1350 (feed, largest footprint), 9:16 1080x1920 (stories, reels).
- gpt-image-2 accepts any size with both sides divisible by 16 (the 1024x1024 / 1024x1536 menu was gpt-image-1's limit). 1024x1280 is exactly 4:5; 1152x2048 is exactly 9:16; 1080x1920 itself is not valid, so render 1152x2048 and downscale. A rejected size fails before generation, so testing it is free.
- **4:5** comes from a 2:3 render whose prompt reserves flat top and bottom bands. `make_ratios.py` crops only rows it measured flat (per-row channel std under 9), then extends any remaining difference with a SOLID colour sampled from the outer ~10 rows. Never centre-crop blind (it slices CTA bars and logos); never extend by replicating the edge row (it ghosts the CTA into the band).
- **9:16 is not automatically a Stories asset.** The app draws its interface over the top ~14% and bottom ~20%. Models do not respect percentage instructions reliably (in one batch only about 1 in 6 native renders kept both bands clear), so `make_story.py` OCRs both bands, keeps a native render only when both are provably empty, and otherwise rebuilds by scaling the 4:5 composition into the safe area. It costs a little type size and buys a guarantee.
- A variance check on extension bands gives false alarms on photographic edges; look before re-rendering.
- Anything you composite must respect the safe area too: `person_panel.py` uses a foot line / height cap of about 0.955 / 0.92 on squares, 0.86 / 0.70 on 2:3, 0.76 / 0.56 on true stories frames. A side column that works on a square (about 42%) is too narrow at 9:16; give the concept `person_panel_vert` / `image_plan_vert` with a wider column (about 55%).
- Prove no copy is cropped geometrically (`crop_proof.py`). Cross-ratio OCR comparison is invalid: the sizes are separate renders, so OCR differences are rendering differences, and OCR on display type is unreliable anyway.

## Real people, logos and photos
- **Composite real logos, never render them** (`logo_stamp.py`). Reserve an empty corner the CTA cannot reach (top corners; the CTA usually sits low). It auto-tints to ivory on dark grounds.
- **Real person, exact likeness:** cut them out with `rembg` using the `u2net_human_seg` session (clean hair, fingers, raised arms) and composite with `person_panel.py`, which adds a soft contact shadow so the figure does not hover. A cut-out also removes background signage, phone numbers, stray objects that read as extra limbs, and awkward crops in one step.
- **AI likeness from references:** build a multi-angle reference SET, not one crop. Mine a short video at `ffmpeg -vf fps=4` for many head angles. Crop true squares centred on the head; never pad to square (the subject renders small). Grade a washed-out reference instead of replacing it (`ImageOps.autocontrast(cutoff=1)`, contrast about 1.14, colour about 1.2) so the expression the client likes survives. Name the one feature to preserve in the brief (for example "[FEATURE] is the most important thing to carry across").
- **A named garment in `image_plan` beats the renderer's global ban.** Grep plans for banned garments before rendering (qc_concepts.py does).
- **Crop from the retouched master in ONE step**, centred on measured subject coordinates (overlay a normalised grid and read head top, face centre, hands, feet). Chained intermediate crops upscale twice and read as "stretched". "Stretched" from a non-designer usually is not stretch: check the aspect maths, then look for a crop cutting the head or hands, or a clipped subtitle.
- **Consent triage** on client-supplied photos: usable as an ad, usable only as a likeness reference (crop other people out first or the model renders them), unusable. Background strangers are never cleared. Anything that raises a question about who owns or appears in a photo goes to the owner as a question; record the answer in the brief so it is settled once.
- **Check that a client-proof ad actually contains the client.** Read the render: models invent people.
- Verify anything that decides whether an image can be published yourself, at magnification (crop the region from several frames into one strip). Do not adjudicate between two agents' opinions.

## Hard rules
- Never invent a number. If a concept needs one you cannot source, write it without one.
- Check currency: a figure written with a bare "$" may be AUD, CAD or USD. Convert honestly or state the country; never relabel.
- Only people cleared in the brief may appear or be named.
- No phone number, client signage or third-party branding in any ad. Retouch the master, then prove it with `phone_sweep.py`.
- A concept whose plan says "find the real screenshot" is NOT a render brief: the model will invent client messages, dashboards and testimonials. Route those to a human. Re-rendering does not fix it.
- Locale: UK ads use UK words (clinic, diary, pounds); US ads use US words.
- No em dashes. A founder or marketer appears as an adviser, never as a clinician.
- Banned look: warm cream + serif + terracotta, pastel pill tags, floating rounded shadow cards, three-column icon grids, emoji markers, everything centred.
- Health ads: no prescription-only medicine names in consumer ads (UK/IE/AU), no before/after in AU cosmetic ads, no personal-attribute callouts ("your wrinkles"), no unrealistic outcomes. For a full pre-launch check use `meta-launch-audit`.
- Nothing goes to a client or goes live without the owner's approval.

## Loading and budget (how many to launch)
- Load the ad set up rather than thinning it: in a consolidated ad set a few ads take most of the spend and the rest getting little is expected. Meta will not spend on ads it does not distribute, so the tail costs little; the real cost is that most stay untested. Handle that with painpoint caps in the launch tier, not by cutting the count.
- A silent ad is untested, not bad. Never kill on zero reach.
- Raising budget mid-learning can push spend into the cheapest, worst placement and spike CPL. If that happens, revert and wait.
- For the scale / kill reading once live, use `meta-ads-analyst`.

## Gotchas
- Files in `~/Downloads` can be blocked from the terminal by macOS privacy controls; ask the user to move them.
- zsh does not word-split unquoted vars: pass id lists with `--ids-file`, never `--ids $VAR`.
- One image over 2000 px in a multi-image read can break image reading for the rest of a Claude session. Downscale first, read one at a time, delegate visual QC to subagents, and assert contact sheets are under 1980 px.
- Renderer skips existing files, so a concept edited AFTER its first render keeps a stale image. Track concept edits with git (diff `concepts_final.json` across commits and compare changed ids with render times), then `--force` or delete those files.
- `rclone copy --ignore-existing` will not replace a re-rendered image. Drop the flag for re-renders, and delete the old file by name first if the headline changed (the filename embeds it, so you get a duplicate).
- rclone lists a native Google Sheet with an `.xlsx` extension: `rclone delete "<folder>/Review.xlsx"` trashes the live Sheet silently (it still accepts writes and exports). Delete by file id after checking `mimeType`; restore with a Drive PATCH `{"trashed": false}`.
- Purging a Drive folder's contents leaves an empty folder the client will report as a bug; delete the folder too.
- In OOXML `showDropDown=True` HIDES the in-cell arrow. Set it False (the script does).
- Baking dropdowns into an xlsx and PATCHing it over a Google Sheet as media keeps the URL and the validation without the Sheets API.
- OpenAI image models need organisation verification on the platform; auto top-up does not fire from a zero balance, top up manually first.
- `SSL_CERT_FILE=$(python3 -m certifi)` before urllib / OpenAI calls if you see certificate errors on macOS.
- Convert HEIC before any image API sees it (`sips -s format jpeg` on macOS, `heif-convert` on Linux).
- `pathlib.glob` treats `[` `]` in filenames as a character class; filter `os.listdir` instead (the scripts do).
- Back up: git-init the project with images and renders gitignored; commit before and after rendering.
