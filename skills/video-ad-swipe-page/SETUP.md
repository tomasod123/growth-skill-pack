# video-ad-swipe-page: setup

## What it does
Finds competitor video ads in the Meta Ads Library (via Apify), picks the 6 to 8 that best fit your client's offer and buyer, downloads and transcribes them, and builds a pattern table.
Writes ready-to-film scripts and renders one self-contained "filming kit" HTML page with each competitor example beside its script. Works for clinics and for B2B SaaS.

## What you need
- **Apify account** (pay as you go is fine): https://console.apify.com
  - `APIFY_TOKEN`: Apify Console > Settings > API & Integrations > Personal API tokens > copy (or create) a token.
  - The actor `curious_coder/facebook-ads-library-scraper` is public; no extra setup. Roughly $0.00075 per ad returned.
- **Python 3.9+**: install certifi FIRST: `pip install certifi` (the scripts and the SKILL.md preamble use it for TLS on macOS; harmless elsewhere). Optional: `pip install openai-whisper` for transcripts (pulls in PyTorch, a large download).
- **ffmpeg + ffprobe** (frames, hook clips, durations): `brew install ffmpeg` or `sudo apt install ffmpeg`.
- Optional: **yt-dlp** for videos whose CDN link expired: `pip install yt-dlp`.
- Optional: **tesseract** for on-screen text OCR: `brew install tesseract` or `sudo apt install tesseract-ocr`.
- Optional: **Node 22+ and Google Chrome or Chromium** for the silent layout/overlay QC (`qc_page.mjs` uses Node's built-in WebSocket). Set `CHROME_PATH` (or `CHROME_BIN`, or pass `--chrome <path>`) if Chrome is not in a standard location.
- Optional: **Netlify CLI** to publish: `npm i -g netlify-cli`; `NETLIFY_AUTH_TOKEN` from Netlify > User settings > Applications > Personal access tokens > New access token.
- Optional but recommended: the **ad-library** skill from this pack (step 0 queries it, step 9 feeds it).

## Install
1. Copy this folder to `~/.claude/skills/video-ad-swipe-page/`.
2. Add the vars from `.env.example` to `~/.claude/skills/.env` (only `APIFY_TOKEN` is required).
3. Test (prints the cost plan, charges nothing):
   ```
   pip install certifi
   set -a; source ~/.claude/skills/.env; set +a; export SSL_CERT_FILE=${SSL_CERT_FILE:-$(python3 -m certifi 2>/dev/null)}; python3 ~/.claude/skills/video-ad-swipe-page/scripts/01_discover.py --client test --terms "free consultation" --countries GB --count 20 --dry-run
   ```
   You should see `PRICE ... (live)`; `(fallback)` means the token or network is not working.

## First run (2 minutes)
Type: `Build a video ad swipe page for Clinic A: offer is a free skin consultation, market GB then IE, budget $5.`
(B2B: `Build a video ad swipe page for my-saas: offer is "book a demo" of our AI scribe, profile b2b, markets US then GB.`)
Claude queries the ad library first, shows you the Apify cost plan before spending anything, then shortlists, downloads, builds the pattern table and drafts scripts. Output lands in `./video-ad-swipe-page-output/<slug>/video-swipe-<date>/` (`shortlist.json`, `patterns.md`, `site/index.html`, `HANDOVER-<date>.md`). Nothing is published unless you ask.

## Common errors and fixes
- **`fire` reports runs but `poll` shows 0 items, or CERTIFICATE_VERIFY_FAILED.** macOS Python has no CA bundle. Run `pip install certifi`, then `export SSL_CERT_FILE=${SSL_CERT_FILE:-$(python3 -m certifi 2>/dev/null)}` in the same Bash call as the script, and fire again (already-fired runs are skipped).
- **Videos 403 or 0-byte files a few days after the scrape.** Facebook CDN links expire in about five days. Download (step 3) the same day as `pull`; for public page videos pass `--ytdlp-map`. Keep `raw_ads.json`.
- **`ABORT: ... exceeds --budget`.** The worst-case cost is runs x count x price. Cut terms, countries or `--count`, or raise `--budget` (max $25 hard cap).
- **Shortlist is full of long-running ads that do not fit.** You ranked with `--rank-by days` or skipped `--offer-exact`. Re-run with the default `--rank-by fit` and the client's own offer regex; for SaaS add `--profile b2b`.
- **B2B ads all dropped as "training/B2B".** You are on the default clinic profile. Pass `--profile b2b`.
- **Chrome aborts with "No usable sandbox" or QC hangs.** On Linux `qc_page.mjs` adds `--no-sandbox`; set `CHROME_PATH` (or `CHROME_BIN`) if Chrome is elsewhere. Never launch Chrome for this page without `--mute-audio`.
- **Pagination stops early.** Only an empty chunk ends a dataset; the script handles it, do not "fix" it to stop on a short page.

## Setup time
10 minutes (15 with whisper).

## Cost per run
Apify only: about $0.00075 per ad returned. A typical pull (2 to 3 countries x 8 to 12 terms x 120 ads) is $2 to $5 worst case, often less. Free when the ad library already has enough fits.
