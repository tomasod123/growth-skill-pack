---
name: video-ad-swipe-page
description: Build a client-facing "swipe page" of competitor video ads plus ready-to-film scripts. Reads the local ad library FIRST, tops it up from the Meta (Facebook) Ads Library via Apify only when it must, selects examples by FIT to the client's own offer and buyer (never by how long an ad has run), downloads and transcribes them, extracts the pattern table, writes scripts in the client's voice through the market's compliance filter, embeds each competitor example beside its script with click-to-enlarge, QCs through persona lenses, and optionally deploys unlisted. Works for clinics and healthcare providers (patient-facing offers) and for B2B SaaS / software companies (demo, trial or content offers). Use when the user says "swipe page", "competitor video ads", "what video ads are working for X", "scripts to replicate", "filming kit", "direct-offer video ads", "video ad research", or "what are competitors running on Meta".
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./video-ad-swipe-page-output/`.

# Video Ad Swipe Page

## The one rule that decides the page

> **An example earns its place by being something this client could run next week, not by having run for a long time somewhere else.**

Fit to the client's own offer and their own buyer comes first. Quality second. Run length is
evidence and a tiebreak, never the ranking. **Six to eight excellent examples beat twelve
mediocre ones.** Everything in step 0 and step 2 exists to enforce that.

## Goal
One self-contained HTML page the client (or their presenter) can film from: the competitor ads
that fit the client's offer best, what they have in common, and 4 to 6 scripts in two groups
(A: the client's own organic content plus recommended new videos, each with a ten-second CTA
close; B: competitor-modelled direct-offer videos) written in the client's voice, each Group B
script with its competitor example embedded beside it.

## The bar
Satisfies the brief, plenty of contrast, examples for every group, so simple a ten-year-old
could follow it, no more words than needed.

## What goes wrong (the failure mode this skill is built against)

A hypothetical bad set: a dozen or more examples for a person-led clinic whose offer is a free
consultation, ranked purely by how long each ad had been running. Read against the library
fields, the picks tend to break down like this:

| What was wrong | Typical share |
|---|---|
| Nobody speaking on camera (silent b-roll, text slides, carousels) for a **person-led** business | often the majority |
| Ads from another country on a page for a home-market client | a sizeable share |
| Not reproducible: a device, studio or second operator the client does not have | a sizeable share |
| Sold the client's own offer shape | a small minority |
| `talking_head`, the one format the client can actually shoot | a small minority |

In a set like that, the top pick is often the longest-running ad with no offer at all, ranked
first purely on longevity. Every one of those failures is a hard exclusion in step 2, and every
one is a field the ad library already holds, which is why step 0 is a library query and not a
scrape.

**The failure mode in one line:** run length measures the advertiser's patience, not fit to this
client. Ranking on it produces a set that is technically "proven" and useless to the person who
has to hold the phone.

**B2B SaaS version of the same trap:** a long-running brand video from a category leader with a studio
crew and no offer ranks first, while a newer founder-to-camera "book a demo" ad that your
team could shoot tomorrow sits at #14. Fit first fixes it.

## Inputs (ask once, then run)
| Input | Clinic example | B2B SaaS example | Default |
|---|---|---|---|
| client slug | `clinic-a` | `my-saas` | required |
| profile | `clinic` | `b2b` | `clinic` |
| offer | "free skin consultation" | "book a 20-minute demo" / "14-day free trial" | required |
| treatment / category | skin concerns, hair restoration | AI scribe, patient intake, RCM software | required |
| target countries in order | `GB,IE,US` | `US,GB,CA` | `US,GB,AU` (first = home market, worth the most fit) |
| Apify budget | `--budget 10` | `--budget 10` | **$10 default, $25 hard cap**, never above without the budget owner's yes |
| presenter + city | the lead clinician, their city | the founder / a clinician customer | ask |
| lands on | instant form / booking page | demo booking page / trial signup | instant form |
| your own pages | file of page names to exclude | same | none |

Client facts (presenter, city, prices, what they have already filmed) come from the client's own
notes or brief, and the logo and primary colour from your brand folder (optional:
`~/.claude/brand/clients/<slug>/`). Never state a client's price from memory; confirm it or mark
it "to confirm together".

Working dir: `./video-ad-swipe-page-output/<slug>/video-swipe-<YYYYMMDD>/` under the current
directory (override with `--workdir` or `$SWIPE_OUTPUT_DIR`). Never a temp dir the OS may wipe.

## Scripts
`~/.claude/skills/video-ad-swipe-page/scripts/` (all have `--help`; steps 1 to 4 have
`--dry-run`; no tokens in code, the Apify token comes from `$APIFY_TOKEN`).

```
set -a; source ~/.claude/skills/.env; set +a; export SSL_CERT_FILE=${SSL_CERT_FILE:-$(python3 -m certifi 2>/dev/null)}; S=~/.claude/skills/video-ad-swipe-page/scripts; L=~/.claude/skills/ad-library/scripts
```
**Each Bash call is a fresh shell: start EVERY Bash call that runs a command below with that
exact line** (it loads APIFY_TOKEN and NETLIFY_AUTH_TOKEN, sets the CA bundle so Apify calls do
not fail silently on macOS, and sets `$S` and `$L`; `$L` only works if the ad-library skill is
installed). Needs `pip install certifi` once (see SETUP.md).

## Step 0 · THE AD LIBRARY IS STEP ZERO

**If the `ad-library` skill is installed, the first action is a query against it, not a scrape.**
Rows that were tagged by someone watching the video can answer "does a person speak on camera",
"could a small team reproduce this", "is it safe in this market", which a fresh scrape cannot.
Only scrape when the library cannot supply enough genuine fits. (No library yet? Skip to step 1,
then ingest at step 9 so the next page starts here.)

```
set -a; source ~/.claude/skills/.env; set +a; export SSL_CERT_FILE=${SSL_CERT_FILE:-$(python3 -m certifi 2>/dev/null)}; S=~/.claude/skills/video-ad-swipe-page/scripts; L=~/.claude/skills/ad-library/scripts
# 1. what exists at all
python3 $L/query.py --stats
# 2. THE SELECTION QUERY: fit filters first, sort by fit, never by days
python3 $L/query.py --replicable --no-compliance-flag --country GB \
        --offer-type free_consultation --tagged --format-class talking_head
#    B2B SaaS:
python3 $L/query.py --replicable --country US --niche b2b-software \
        --offer-type demo_booking,free_trial --tagged --format-class talking_head,testimonial
# 3. widen one filter at a time until you have 10 to 14 candidates to watch
python3 $L/query.py --replicable --no-compliance-flag --country GB \
        --offer-type free_consultation --tagged --format-class talking_head,testimonial,voiceover_broll
python3 $L/query.py --replicable --no-compliance-flag --niche skin --min-fit 4 --with-media --paths
# 4. own-client winners (read the consent note in `notes` before any go on another client's page)
python3 $L/query.py --kind client --niche <niche>
# 5. hand the JSON to the build
python3 $L/query.py --replicable --no-compliance-flag --country GB --offer-type free_consultation --json > picks.json
```

Filter meanings (full vocabulary in the ad-library skill's `references/SCHEMA.md`):
`--replicable` = `replicable_by_small_team` (no second operator, no studio crew, no device or
platform the client does not have) · `--no-compliance-flag` = drops rows with `compliance_flag`
set for their market · `--tagged` = a human watched it, so `person_on_camera`, `setting`,
`captions`, `voice` are real and not guessed · `--offer-type` = the shape of the offer the ad
actually sells (`free_consultation`, `price_led`, `discount_percent`, `discount_amount`,
`free_treatment_or_taster`, `bundle`, `membership_or_plan`, `finance_payment_plan`,
`competition_giveaway`, `demo_booking`, `free_trial`, `lead_magnet`, `free_audit_or_assessment`,
`none`) · `--format-class` = who is on camera (`talking_head`, `testimonial`, `voiceover_broll`,
`organic_reel_cta`, `screen_demo`, `silent_broll_text`, `text_slides`, `carousel_static`) ·
`--country` = the ad's resolved `country_iso`, not the batch label.

**Decision:** eight or more genuine fits in the library → step 1 is skipped or is a small
top-up. Fewer than eight → scrape, with terms aimed at the gap the query exposed (the missing
market, the missing offer shape), not at the whole niche again. Library rows carry their media,
posters and transcripts, so steps 3 and 4 skip them.

**Every scrape ingests back (step 9), so the library compounds and the next page is cheaper.**
A page that scrapes and does not ingest has paid for the same research twice.

## Step 1 · Competitor discovery (Apify, Meta Ads Library) — only if step 0 came up short
Actor: `curious_coder~facebook-ads-library-scraper` (public actor on the Apify Store), roughly
**$0.00075 per ad** (pay per result; the live price is fetched at run time). A typical research
pull of 3 countries x 10 terms x 120 ads = 3,600 ads worst case, about $2.70.

1. Write 6 to 12 exact-phrase terms per the offer: concern words + offer words. Clinic:
   `skin consultation, acne scarring, pigmentation, melasma, rosacea, skin needling`. B2B SaaS:
   `ai scribe, clinical documentation, patient intake, no shows, book a demo, practice management`.
   Fewer, tighter terms beat many loose ones. Also search competitor brand names directly.
2. Cost preview (fires nothing). The formula is printed BEFORE anything is charged:
   **runs x count x price**, runs = countries x terms.
   ```
   set -a; source ~/.claude/skills/.env; set +a; export SSL_CERT_FILE=${SSL_CERT_FILE:-$(python3 -m certifi 2>/dev/null)}; S=~/.claude/skills/video-ad-swipe-page/scripts; L=~/.claude/skills/ad-library/scripts
   python3 $S/01_discover.py --client <slug> --terms "t1,t2,..." --countries US,GB --count 120 --dry-run
   ```
   It aborts over `--budget` (default $10) and always over the $25 hard cap.
3. Fire, poll, pull:
   ```
   set -a; source ~/.claude/skills/.env; set +a; export SSL_CERT_FILE=${SSL_CERT_FILE:-$(python3 -m certifi 2>/dev/null)}; S=~/.claude/skills/video-ad-swipe-page/scripts; L=~/.claude/skills/ad-library/scripts
   python3 $S/01_discover.py --client <slug> --terms "..." --countries US,GB --count 120 fire
   python3 $S/01_discover.py --client <slug> poll --wait 30   # loops until every run finishes, prints ACTUAL usd
   python3 $S/01_discover.py --client <slug> pull             # paginates until an EMPTY chunk, writes raw_ads.json
   ```
   Default `--media video` (Ads Library filter) so you do not pay for image ads you will drop
   anyway; `--media all` if the offer is rare.
4. **Keep `raw_ads.json`.** `snapshot.videos[].video_hd_url` / `video_preview_image_url` expire
   within days; the raw payload is the only way back to them without paying again.

## Step 2 · SELECTION IS ON FIT, NOT LONGEVITY

Order of decision, every time:
1. **Fit** — a comparable offer, a comparable treatment or product category, a comparable kind of
   business, and the client's own market. Does this ad speak to the buyer this client actually
   sells to?
2. **Quality** — production standard: framing, light, captions, audio, and whether it looks like
   a real business rather than stock.
3. **Run length** — evidence that the market kept paying for it, and the tiebreak between two ads
   of equal fit. Never the ranking.

**Target: six to eight excellent examples.**

### Hard exclusions (drop, do not rank)
- **No person on camera, for a person-led business.** Text slides, stock b-roll with a caption,
  logo openers, `format_class` in `silent_broll_text` / `text_slides` / `carousel_static`. A
  person-led business cannot learn anything from an ad with nobody in it. (B2B: a
  `screen_demo` is fine when a person narrates it.)
- **Equipment or product the client does not have.** Anything whose hero is a device or feature
  they cannot show (`device_shown` / `device_is_hero`, and `--exclude-device` on the scrape path).
- **A different category.** Not "aesthetics" or "health tech" broadly: the treatment or product
  this client sells.
- **Not reproducible.** `replicable_by_small_team: false`: a second operator, a studio crew, an
  agency-grade shoot. A reference at best, never a brief.
- **A compliance flag for the client's market.** `compliance_flag: true`, or any ad naming a
  prescription-only medicine for a UK or AU page. See the compliance filter in step 5.
- Aggregators, franchises running 40 identical creatives, wrong language, your own clients.
- **B2B extra:** ads selling to the end consumer instead of the business buyer, recruitment ads,
  investor or award announcements.

### The script
```
set -a; source ~/.claude/skills/.env; set +a; export SSL_CERT_FILE=${SSL_CERT_FILE:-$(python3 -m certifi 2>/dev/null)}; S=~/.claude/skills/video-ad-swipe-page/scripts; L=~/.claude/skills/ad-library/scripts
python3 $S/02_rank.py --client <slug> --countries GB,US --top 40 --dry-run   # look first
python3 $S/02_rank.py --client <slug> --countries GB,US --top 40 \
   --offer-exact 'free consultation|complimentary consultation' \
   --exclude-device 'emsculpt|coolsculpt|hydrafacial|cryolipolysis|morpheus|co2 laser|picosure' \
   --concern 'acne|pigment|melasma|rosacea|texture|scarring' --exclude-pages own-pages.txt
# B2B SaaS
python3 $S/02_rank.py --client <slug> --profile b2b --countries US,GB --top 40 \
   --offer-exact 'book a demo|free trial' --concern 'documentation|charting|no.show|admin|burnout|denials'
```
Keeps video only, active only, run >= 14 days, an offer match, a named concern or pain point;
drops shops/products, the wrong audience for the profile (clinic: training and B2B pitches; b2b:
consumer-facing ads), job ads, bad CTAs, pages in `--exclude-pages`, ads naming a prescription
medicine on the clinic profile (`--allow-pom` keeps them; you will not want to model on one), and
anything matching `--exclude-device`.

Ranking is `--rank-by fit` by default: **fit 0-5 first, run length only breaks ties inside a fit
band** (capped at 400 days so a far older ad cannot climb past a better-fitting one). Fit is `+2`
the client's own offer shape (`--offer-exact`) or `+1` any offer, `+1` a concern the client
solves, `+0.5` a second concern, `+1 / +0.5 / 0` by market position, `+0.5` a copy signal that a
human is in the ad. `--rank-by days` exists only to read the evidence order.

**Fit from a scrape is computed from copy, which cannot see who is on camera.** The script prints
the hand-drop checklist for that reason. Watch the first three seconds of every candidate, apply
the hard exclusions above, then record `fit_score` (0-5: exact offer 2, same kind of business 1,
concern named 1, a real person or the business's own premises/product 1) and `quality_score`
(0-5, after watching) per ad in `scores.json`. They go to the library at step 9, which is what
makes the next client's step 0 sharper.

## Step 3 · Download + transcribe + thumbnails
```
set -a; source ~/.claude/skills/.env; set +a; export SSL_CERT_FILE=${SSL_CERT_FILE:-$(python3 -m certifi 2>/dev/null)}; S=~/.claude/skills/video-ad-swipe-page/scripts; L=~/.claude/skills/ad-library/scripts
python3 $S/03_media.py --client <slug> --dry-run
python3 $S/03_media.py --client <slug>          # media/<id>.mp4 + .jpg, frames/<id>.jpg, hooks/<id>.wav+.txt, media_meta.json
python3 $S/03_media.py --client <slug> --full   # adds tx/<id>.txt full transcripts (small.en, slow: ~1 min per 30 s clip)
```
- Downloads the snapshot video URLs **while fresh** with a browser User-Agent. If one 403s and
  you have a public page video link (`facebook.com/<page>/videos/<id>`), put it in a JSON map and
  pass `--ytdlp-map map.json`; yt-dlp works on public page videos with no cookies, using plain
  `-f best` (height selectors fail). `ads/library/?id=` pages are JS-gated and do not work with yt-dlp.
- Hook = **first 8 s**, cut by ffmpeg to 16 kHz mono wav, transcribed with `whisper tiny.en`
  (small.en on the full clip can take 15+ minutes for two clips). Sequential, not parallel.
- First frame at 0.5 s for every ad, so a thumbnail exists even when the video later goes.
- Never `ls | xargs` over media paths (curly quotes in names drop files); the script walks the dir in Python.
- More than 60 clips or `--full` on a laptop: consider a bigger machine and ask first.

## Step 4 · Pattern table
```
set -a; source ~/.claude/skills/.env; set +a; export SSL_CERT_FILE=${SSL_CERT_FILE:-$(python3 -m certifi 2>/dev/null)}; S=~/.claude/skills/video-ad-swipe-page/scripts; L=~/.claude/skills/ad-library/scripts
python3 $S/04_patterns.py --client <slug> --top 12 --dry-run
python3 $S/04_patterns.py --client <slug> --top 12    # patterns.md (paste-ready) + patterns.json (counts for the page)
```
Columns: **hook type · offer · on-screen text · length · CTA · format · run days**. Hook types:
CALLOUT (city / person / role), PROBLEM (concern or business pain named), NUMBER, INVITATION ("I'm
X from Y and I want to invite you"), BLAME-OFF ("it's not your fault"), SHOW (the scan or the
product on screen), QUESTION, TEXT-ONLY (no voice; hook written on screen). The regex is a first
pass: **watch the first 3 s of every top-12 ad yourself** and correct hook type and on-screen text
(tesseract OCR fills it when installed, else `[read frame]`). Then write the "Key things" counts as
"X of N" lines ("11 of 11 a person speaking or the hook on screen before one second is up").
Count what NEVER survives too (silent product footage, logo openers, feature menus). Compute
every number in-session from this table; never carry a count from an older page.

## Step 5 · Scripts the client can film
Per script: **title · hook job · length · source ("from the 180-day example") · Hook (said first,
also on screen) · Body (short spoken lines, one per breath) · Close (lead form / demo line) ·
On-screen text · Length · Offer · Lands on · What good looks like · Setting up the shot ·
reference (embedded) · callout (only if something must be confirmed first)**

Rules
- Two groups. **Group A = ALL of the client's existing organic content plus recommended new
  videos**, each with a ten-second CTA close the presenter records once (one row per video, link
  to the file, the CTA script, a check-off). **Group B = competitor-modelled direct-offer videos**,
  home market first, the competitor example embedded beside each script (right column, larger,
  enlarges on click) with its days live. **Examples for every group**, at least one script per group.
- **Personal and brand-specific beats slides.** A named clinician or founder to camera, the
  client's own rooms or product, the client's real offer. Text-slide versions are the fallback
  for when nobody will film, never the lead.
- **Own-client winners are examples where consent allows.** Pull them from the library
  (`query.py --kind client`); on another client's page they appear unnamed (name blurred, logo
  off) unless written consent is on file. A client's own ad never appears on their own page as a
  winner, only as "where the current video sits", and their own spend or revenue never appears.
- 20 to 45 s, one take, phone, presenter's own rhythm. "It does not have to be word perfect."
  One script needs nobody to speak (text cards over real footage or a screen recording).
- Client voice: presenter's name and business in the first 5 s, a city or role callout where the
  example used one, contractions, no AI-isms, no em-dashes, never quote the client's own words
  back at them, no big prose blocks.
- Hook does exactly one job from the pattern table; say it AND put it on screen; nothing opens on a logo.
- Mark manufacturer or vendor figures ("20,000 contractions", "saves 2 hours a day") as
  *manufacturer's figure, to confirm together first*.
- Compliance filter by market (write the "A note on claims" callout from it). General guidance,
  not legal advice:
  - **UK**: Human Medicines Regulations 2012 reg 284 and the CAP Code. Do not name, describe,
    price or make bookable any prescription-only medicine (POM), and not by euphemism
    ("anti-wrinkle injections", "wrinkle relaxing" are caught too). Sell the consultation. No
    before/afters implying POM results.
  - **AU**: AHPRA advertising guidelines (cosmetic and "higher-risk" procedures: no testimonials,
    no discounts or time-limited offers), TGA (no prescription medicines named, even by
    euphemism), National Law s133 (no clinical-outcome testimonials, no "cure / guaranteed /
    permanent"). Consult-led and education-led, exact all-in prices only.
  - **US**: FTC (substantiated claims, clear material terms on any price, "results vary"), HIPAA
    on any real patient on camera (written authorisation), state rules on who may be shown
    treating.
  - **B2B healthcare software**: claims about time saved, accuracy or revenue need a source you
    can show; "HIPAA compliant" / "SOC 2" only if the certification or BAA position is real and
    current; no implied clinical outcomes; customer logos and quotes only with permission.
  - All markets: no income or guarantee language; Meta's advertising standards (health and
    personal attributes) still apply on top.
- Money: state the offer price only if the client confirmed it; otherwise "[price, to confirm]".

## Step 6 · Page build
```
set -a; source ~/.claude/skills/.env; set +a; export SSL_CERT_FILE=${SSL_CERT_FILE:-$(python3 -m certifi 2>/dev/null)}; S=~/.claude/skills/video-ad-swipe-page/scripts; L=~/.claude/skills/ad-library/scripts
python3 $S/05_render.py --example > page.json      # edit: client, agency, page, key_things, winners, patterns, groups/scripts, transcripts
python3 $S/05_render.py --spec page.json --out <workdir>/site --media-src <workdir>/media
```
Template: `templates/page.html` (recipe, winners grid, pattern table, transcripts, scripts, next
step; filming-kit chrome: sticky tabs, progress bar, mark-as-filmed, upload button, file names).

**Layout, and the intent behind it. This survives any rebuild of the HTML:**
- **The script the client films is the LEFT column. The competitor example is the RIGHT column,
  and it is the larger of the two media wells** (`--ref-col`, 420px desktop, 340px at 1040px
  down). Left is the work they do, right is the thing they are copying, and the example has to be
  big enough to actually watch.
- **On a phone the columns stack with the example ABOVE the script** (`.ad-ref{order:-1}`), so
  they see what they are copying before they read the words. Deliberate, not a bug.
- Every grid child carries `min-width:0` so a wide child scrolls inside itself instead of pushing
  the page sideways. Verify at 1440x789 AND 390x844: `scrollWidth <= innerWidth`.

**HARD RULE · never let this page make noise.** Headless Chrome on a desktop plays page audio
through the real speakers, and this page is a wall of competitor videos. An unguarded check can
start every video at once with no window to close. So every Chrome this skill launches, for a
screenshot, a measurement or QC:
```
"$CHROME_PATH" --headless=new --remote-debugging-port=<port> --user-data-dir=<tmp profile> \
  --mute-audio --autoplay-policy=user-gesture-required \
  --no-first-run --no-default-browser-check --disable-gpu about:blank &
CHPID=$!    # ... run the check ... then, always:
kill $CHPID
```
- `--mute-audio` and `--autoplay-policy=user-gesture-required` are not optional. **Never**
  `--autoplay-policy=no-user-gesture-required`.
- Kill the browser by the PID you captured. Never `pkill -f` a pattern from inside the same Bash
  call that launched it (it matches and kills your own shell).
- To check whether a video plays or pauses, read the element's `paused` and `currentTime` over
  CDP. If `play()` really is needed, set `muted = true` on the element first.
- `scripts/qc_page.mjs` does all of the above (safe flags, own temp profile, kill by PID in a
  `finally`, muted before any play):
  `cd <site> && python3 -m http.server 8791` then, in one Bash call, the preamble line followed by `node $S/qc_page.mjs http://127.0.0.1:8791/index.html`.

**Click to enlarge, on every competitor example.**
- The overlay carries the ad's detail (advertiser, country, days running, their offer, format)
  plus **two or three lines on why it works and what the client takes from it**.
- Closes on the X, on Escape, and on an outside click. **The video pauses on close.** Keyboard
  accessible: focus moves to the close button on open, is trapped in the card while open and
  returns to the button that opened it. Body scroll locks while open.
- Plain HTML, CSS and vanilla JS. No library.
- Built into `templates/page.html`: one `#zoom` overlay per page plus a `.zoom-btn` inside any
  `position:relative` media well, carrying `data-zoom`, `data-kind` (`video`|`thumb`),
  `data-media` (path with no extension), `data-advertiser`, `data-country`, `data-days`,
  `data-offer`, `data-format`, `data-insights` (a JSON array of the 2 to 3 lines). Filled by
  `05_render.py` from the spec: `ref_country`, `ref_offer`, `ref_format`, `ref_insights[]` on a
  script; `country`, `offer`, `format`, `insights[]` on a winner.
- **Write the insight lines yourself, per ad.** They are the reason the example is on the page.
  Generic lines ("great hook") are worse than none.
- `[hidden]{display:none!important}` is declared once at the top of the stylesheet: a class that
  sets `display` beats the UA `[hidden]` rule, and the overlay would never hide without it.

Other rules:
- Self-contained: fonts from Google only, all media local under `site/media/`, no external JS.
- **Branding**: client logo top-left, `--brand` = client primary colour (spec `client.primary`)
  for the progress bar and card rules; the neutral tokens at the top of the template for
  everything else (swap in your own brand tokens if you keep them in `~/.claude/brand/`).
  Footer from `agency.footer`, or `© <year> · <agency.name> · <version>`.
- Competitor example **embedded in the right column beside each script**: the mp4 with poster, or
  the first-frame thumbnail when no video survived (`REF_KIND thumb`), each with a "N days live"
  badge and an Enlarge button.
- Contrast: every text/background pair >= 4.5:1 (check numerically if you add colour).
- `noindex,nofollow` stays on.

## Step 7 · QC loop (run until every lens passes)
Spawn three parallel review subagents on the rendered `index.html` + `patterns.md`, each with ONE
lens, each returning a drift log (quote the exact line where they stopped following, and why).
If you have the `persona-qc` skill, use it for this step.
1. **The client owner** (use their own tools as the frame): would they film this tomorrow? Is
   anything about their business wrong? Any price or claim they can falsify?
2. **The person who films** (presenter): can each script be said in one take at that length
   (count words: ~2.5 words/s)? Is the shot setup doable with a phone and a window? Is it clear
   which file name goes where?
3. **A ten-year-old-could-follow-it read**: reading level (aim <= grade 7 on prose), one next
   action visible at every scroll position, no jargon, no clause with two ideas.

Also run:
- **The fit lens.** For EVERY example on the page, in the owner's voice: is this my offer, my
  treatment or product, my kind of business, my market, and could I shoot it on my phone next
  week? One no is a hard fail on that example. Then count: how many examples have a person
  speaking on camera, and how many sell the client's own offer shape? If either count is under
  half, the selection failed and step 2 runs again.
- Compliance (market rules above), and contradictions vs `patterns.json` (every "X of N" on the
  page must match).
- **Does-it-physically-work**: preamble line + `node $S/qc_page.mjs http://127.0.0.1:8791/index.html` against a
  `python3 -m http.server` in the site dir. It runs 1440x789 and 390x844, fresh tab each, muted,
  and kills the browser by PID. It asserts: no horizontal scroll, the script is the left column
  and the example the right and larger at desktop, the example is above the script on the phone,
  and the enlarge overlay opens, closes by all three routes, pauses its video on close, traps
  focus and returns it. Check by eye as well: videos load, tabs scroll, ticks persist.

Fix, re-render, re-run the failing lens. Ship only when all pass.

## Step 8 · Deliver (optional deploy)
The page is a static folder: `<workdir>/site/`. Zip it, or drop it on any static host (Netlify
Drop, Cloudflare Pages, S3). With the Netlify CLI and `NETLIFY_AUTH_TOKEN` set:
```
set -a; source ~/.claude/skills/.env; set +a; export SSL_CERT_FILE=${SSL_CERT_FILE:-$(python3 -m certifi 2>/dev/null)}; S=~/.claude/skills/video-ad-swipe-page/scripts; L=~/.claude/skills/ad-library/scripts
bash $S/deploy.sh "$(cd <workdir>/site && pwd)" <slug>-<treatment>-swipe "Filming kit"
```
It creates the site once, deploys with `--site <id>` (never a bare `netlify deploy` inside a
folder linked to another site), and **verifies by `curl -sL <url> | grep <phrase>`** rather than
trusting the CLI. Sending the link to the client is a human's call: stage it, do not send it.

## Step 9 · Ingest into the ad library, then hand over (if ad-library is installed)
```
set -a; source ~/.claude/skills/.env; set +a; export SSL_CERT_FILE=${SSL_CERT_FILE:-$(python3 -m certifi 2>/dev/null)}; S=~/.claude/skills/video-ad-swipe-page/scripts; L=~/.claude/skills/ad-library/scripts
python3 $L/ingest.py --from-swipe <workdir> --client <slug> --niche <niche> --offer "<offer>" --market <home> --source "<slug> swipe <date>" --scores-json <workdir>/scores.json
python3 $L/ingest.py --from-json <workdir>/own-ads.json --client <slug> --kind client --niche <niche> --offer "<offer>" --source "<slug> own ads <date>"
```
`scores.json` = the watched top-12's fit / quality / hook / format_class; `own-ads.json` = the
client's own ads that ran, with CPL and consent status in `notes`. Two minutes; it is what makes
the next page cheaper.

## Step 9b · Handover notes
Write `<workdir>/HANDOVER-<date>.md` (short version first): page location or live URL, what was
filmed / approved, the shortlist ids used and which fell out, terms + countries + actual Apify
spend (from `runs.json` usd), compliance decisions taken, open "to confirm" items (prices,
manufacturer figures, product claims), and the one next action. Do not paste the raw payload or
transcripts into notes.

## Gotchas (do not repeat)
- **Selection ranked on run length.** See "What goes wrong" above. The most expensive mistake this
  skill can make, because the whole page is built on top of it.
- SSL on macOS: an Apify wave can fire 0 of 40 on CERTIFICATE_VERIFY_FAILED and still exit 0.
  The preamble line sets `SSL_CERT_FILE` (needs `pip install certifi`); check `poll` shows items.
- Pagination: `clean=true` pages can come back short mid-dataset; only an empty chunk ends the loop.
- Media URLs expire between research day and page day (about five days); keep `raw_ads.json` and
  download on the same day as `pull`.
- `small.en` on full clips for a hook check is very slow. `tiny.en` on the 8 s wav is seconds.
- If you pull the client's OWN ad videos from the Marketing API (`act_<id>/advideos?fields=source`
  with `META_ACCESS_TOKEN`), `curl` needs `-g` or the field-expansion braces break the URL.
- Headless Chrome QC: fresh tab per run, real device metrics (1440x789), muted, killed by PID.
  On Linux add `--no-sandbox` (qc_page.mjs does) or Chrome aborts.
- The Ads Library publishes **no spend and no impressions** for commercial ads. "Days live" and
  variant counts are survival evidence, never a performance number. Say so on the page.
- The client's own current ad belongs on the page ONLY as "where the current video sits", never
  as a winner, and their own takings never appear.
