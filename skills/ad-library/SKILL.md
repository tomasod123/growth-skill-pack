---
name: ad-library
description: A local, compounding library of video ads (competitor and own-client) in one JSONL file, default ./ad-library-data/ or $AD_LIBRARY_DIR. One row per ad - competitor or own-client, market, niche (clinical niches plus healthcare-software, b2b-software, agency-to-smb, trades), offer, format class, hook, days running, fit and quality scores, offer-tied, transcript and media paths, source scrape - plus first/last seen, is_active, survival days, variant count, platforms, relaunches, advertiser type, country and a 0-100 survival-based performance proxy refreshed weekly from the Meta Ads Library via Apify. Ingest from any video-ad-swipe-page work dir or any Ads Library scrape JSON without re-downloading; query by niche, offer, offer type, country, advertiser type, platform, survival or performance; export CSV. Use when the user says "ad library", "what ads do we already have for X", "swipe examples for", "add these to the library", "own-client winners", "competitor ad tracker", "track competitor ads weekly", or before any competitor video research.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./ad-library-output/`.

# Ad library

## Goal
Stop paying for the same research twice and stop losing what a client's own winners taught you.
One index at `<library>/index.jsonl`; media and transcripts stay where the research left them
(the index points at them). The library starts EMPTY and grows with every swipe page, every
scrape and every weekly refresh.

Library location: `$AD_LIBRARY_DIR`, else `./ad-library-data/` under the current directory.
Pick one folder and keep it (set `AD_LIBRARY_DIR` in `~/.claude/skills/.env`), or every project
grows its own library. The scripts create the folder and an empty `index.jsonl` on first use.

```
set -a; source ~/.claude/skills/.env; set +a; S=~/.claude/skills/ad-library/scripts
```
Each Bash call is a fresh shell: start EVERY Bash call that runs a command below with that line
(it loads AD_LIBRARY_DIR, AD_LIBRARY_MARKETS, APIFY_TOKEN for refresh only, and sets `$S`).
A new library is EMPTY: queries return nothing until you ingest. Fill it from a
`video-ad-swipe-page` work dir (run that skill first) or any Ads Library scrape JSON.

## The rules
1. **Query the library first.** Before `video-ad-swipe-page` fires a single Apify run:
   `query.py --niche <x> --country <y>`. If eight or more usable rows exist for the offer, the
   scrape is a top-up, not a discovery.
2. **Select by fit, quality and offer-tied. Run length is evidence, not the rule.** A 900-day ad
   that sells a different offer loses to a 90-day ad that sells the client's exact offer with a
   person on camera.
3. **Personal and brand-specific beats slides.** A named clinician or founder to camera, the
   client's own rooms or product, the client's real offer. Text slides are the fallback when
   nobody will film.
4. **Own-client winners are examples where consent allows.** A client's ad on another client's
   page appears unnamed (blur the name, strip the logo) unless written consent is on file;
   `client_or_competitor: client` rows carry a `notes` line on consent. A client's own ad never
   appears on their own page as a "winner", only as "where the current video sits".
5. Nothing enters the index that names a prescription-only medicine in a market where that is
   restricted, or breaks another market rule, unless flagged `compliance_flag: true` with
   `notes: compliance-flagged, do not model`.

## Row schema (summary; full detail in `references/SCHEMA.md`)
Core: `id` · `ad_id` · `client_or_competitor` · `client` · `advertiser` · `market` · `niche` ·
`niche_basis` · `offer` · `format_class` · `format_basis` · `hook` · `days_running` · `fit_score`
(1-5) · `quality_score` (1-5 or null) · `quality_basis` · `offer_tied` · `personal_vs_slides` ·
`width`/`height`/`low_res`/`duration_s`/`has_audio` · `transcript_path` · `media_path` ·
`poster_path` · `lib_url` · `cta` · `body_excerpt` · `source_scrape` · `date` · `notes`.

**`niche` is a controlled vocabulary of twelve values** (`niche_rules.NICHES`): eight clinical
(`skin`, `injectables`, `body-contouring`, `hair-and-tattoo-removal`, `hair-restoration`, `dental`,
`cosmetic-surgery`, `medical-wellness`), two software (`healthcare-software`, `b2b-software`), and
`agency-to-smb`, `trades-home-services`. **The niche is read from the ad, not from the batch:**
`--niche` is only the fallback for a row whose own copy names nothing. Stamping one label per
scrape is how a library ends up with "skin concerns", "skin, aesthetics" and "aesthetic clinic,
general" all meaning the same thing.

**Who the ad SELLS TO beats what it names.** Software is detected first (two distinct software
signals: "book a demo", "free trial", "integrates with", "AI scribe", "EHR", "SOC 2"...), then
`sells_to_a_business()`: the ad addresses a business owner AND sells them leads, marketing, a
website, ads or coaching. Without the audience test, raw keyword counting files an agency ad
that says "plumber" forty times as a plumber. Keep every token in those tests to words an
ADVERTISER writes, never words a reviewer writes: a reviewer phrase like "practice owner" in the
list once convicted a dental clinic whose own format note said "a talking-head video of the
practice owner".

**Off-scope advertisers are refused at ingest, by name.** `ingest.py` and `refresh.py` both run
`niche_rules.scope_check()` and refuse anything outside the niches before a row is written,
printing the row and why (override: `--allow-off-scope`, after judging each one). A row that trips
an off-scope signal but survives prints a `CHECK:` line. The gate scores the ad, never the
advertiser's name: a name-only keyword scan flags a doctor whose surname is Law. Ads Library
keyword searches return anything that uses your words ("free consultation" pulls in injury
lawyers, tax firms and window installers), which is why the gate exists. Edit `OFF_SCOPE` to
change your library's scope.

**`format_class`** (controlled): `talking_head` · `testimonial` · `organic_reel_cta` ·
`voiceover_broll` · `screen_demo` · `silent_broll_text` · `text_slides` · `carousel_static` ·
`unclassified`. `unclassified` is a legitimate answer and **must** carry a reason in `notes`;
`ingest.py` REFUSES to write an unclassified or unscored row with empty `notes`. Never invent a
class from ad copy alone: copy tells you the offer, not who is on camera.

**Scores.** `offer_tied` is read from **the ad's own words only** (hook + body + title +
transcript). The `--offer` / `--niche` arguments are per-batch labels; feeding them into the match
marks every row in a batch offer_tied. `fit_score` 1-5 at ingest = home market (set
`AD_LIBRARY_MARKETS`, e.g. `GB,IE,US` or `US,CA,GB`) + an authority on camera + the right category
+ a concrete offer + a person speaking; clinic and software rows use their own patterns
(`ingest.FIT_PROFILES`, edit freely). **Scores at ingest are a sort order, not a verdict.** The
swipe page's watched top-12 overwrites `fit_score`, `quality_score`, `hook` and `format_class` with
`--scores-json --update`.

**Weak ads are hidden by default.** A row with `quality_score` 2 or below never appears in a
`query.py` result unless asked (`--include-weak`, or `--min-quality` at or below 2). They are never
deleted: a weak ad that ran 700 days is evidence about what the market tolerates, and it still
counts in `--stats`.

## SCHEMA v2: delivery, advertiser, geography, performance proxy
Filled by `enrich_row` from the raw scrapes on disk (`raw_scan.py`): `first_seen` · `last_seen` ·
`is_active` · `start_date` · `end_date` (null while live: the scraper reports today as the end
date for every running ad) · `days_running` (recomputed on every read, never stale) ·
`survival_days_at_last_check` (the conservative one, use it client-facing) · `variant_count` ·
`platforms` · `advertiser_ads_live` (a floor, not a census) · `relaunch_of` / `relaunch_count` ·
`status_history` · `page_id` / `page_name` / `page_categories` · `advertiser_type` (`single_site`,
`multi_site`, `chain`, `training_provider`, `product_brand`, `software_vendor`, `unknown`) ·
`locations_named` · `city` · `country_iso` + `country_basis` · `performance_score` 0-100.

**`performance_score` is NEVER spend and NEVER impressions.** Meta publishes neither for commercial
ads; across thousands of raw rows `spend` and `reach_estimate` come back null. It weighs survival
40, still-live 15, variants 15, platform breadth 10, relaunches 10, advertiser ads live 10. Say
what it is (how long the ad survived and how widely the advertiser spread it) or do not use it.

**`country_iso` order:** the ad's own country field, then the country of the SEARCH that returned
it, then the ad's own copy (`.com.au` link, `+44` dial code, `City, ST ZIP`, a UK postcode), then
that advertiser's other ads, then the per-batch `--market` label. `country_basis` records which.
This catches ads stamped with the wrong market by a batch label.

### Creative attributes (`creative_tags.jsonl` sidecar)
Produced by WATCHING the ad and folded in by `merge_tags.py`: `tag_basis` · `person_on_camera` ·
`setting` · `captions` · `voice` · `music` · `offer_type` · `price_shown` · `callout_type` ·
`claim_type` · `urgency` · `social_proof` · `landing_type` · `device_shown` / `device_is_hero` ·
**`replicable_by_small_team`** · **`compliance_flag`** + `compliance_market` · notes fields. The two
in bold decide a swipe page. A `copy_only` row has null on-screen fields because nobody could see
the creative (its CDN URL expired before anyone downloaded it); filter `--tagged` and
`tag_basis: watched` when the on-screen fields must be real. Vocabulary: `references/SCHEMA.md`.

## Commands
```
set -a; source ~/.claude/skills/.env; set +a; S=~/.claude/skills/ad-library/scripts
python3 $S/query.py --stats
python3 $S/query.py --niche skin --country GB --offer consult --min-fit 3 --with-media
python3 $S/query.py --niche healthcare-software --offer-type demo_booking,free_trial --country US --sort performance
python3 $S/query.py --advertiser-type single_site --country GB --active --sort performance
python3 $S/query.py --min-survival 180 --min-performance 60 --platform instagram
python3 $S/query.py --city Manchester --json
python3 $S/query.py --kind client                                       # own winners; check notes for consent
python3 $S/query.py --q "free consultation" --csv > picks.csv          # open in any spreadsheet
python3 $S/ingest.py --from-swipe <video-swipe workdir> --client <slug> --niche <niche> --offer "<offer>" --market GB --source "<slug> swipe <date>" [--dry-run]
python3 $S/ingest.py --from-json picks.json --client <slug> --kind competitor --market GB --niche skin --offer "..." --media-dir media --media-pattern "{base}.mp4" --poster-pattern "{base}.jpg" --tx-dir tx --tx-pattern "{base}.txt" --source "..."
python3 $S/ingest.py --from-json own-ads.json --client <slug> --kind client --niche skin --offer "..." --source "<slug> own ads <date>"   # rows carry media_path/transcript_path/notes/quality_score directly
python3 $S/ingest.py ... --scores-json scores.json --update             # after watching: per-ad format_class/fit/quality/hook
```
Ingest never downloads. Dedupe is on `id`; `--update` overwrites. `--dry-run` prints the first five
rows and the media/transcript/unclassified counts. `--no-poster` skips ffmpeg poster generation.
`--scores-json` values may set `format_class`; an off-vocabulary value is a hard error.

Rebuild the v2 fields after new scrapes land:
```
set -a; source ~/.claude/skills/.env; set +a; S=~/.claude/skills/ad-library/scripts
python3 $S/raw_scan.py          # rescan the scrapes on disk -> work/v2/raw_index.json
python3 $S/backfill_v2.py       # derive the v2 fields onto index.jsonl + completeness table
python3 $S/merge_tags.py        # fold creative_tags.jsonl in
```
`raw_scan.py` reads `<library>/scrapes/` plus any globs in `AD_LIBRARY_EXTRA_SCRAPES`
(colon-separated, e.g. `./video-ad-swipe-page-output/*/*/raw_ads.json`), or `--add <file>`.

## After every swipe page (two minutes)
1. `ingest.py --from-swipe <workdir>` for the competitors, with `--scores-json` from the watched top-12.
2. `ingest.py --from-json own-ads.json --kind client` for the client's own ads that ran (CPL and consent status in `notes`).
3. `query.py --stats` and paste the counts into the handover.

## The weekly refresh (optional; Apify, about $0.20 to $2 a run)
```
set -a; source ~/.claude/skills/.env; set +a; S=~/.claude/skills/ad-library/scripts
cp ~/.claude/skills/ad-library/templates/tracked.example.json "$AD_LIBRARY_DIR/tracked.json"   # then edit
#   or build it from the advertisers already in the index:  python3 $S/refresh.py --seed-tracked
python3 $S/refresh.py --dry-run     # plan + cost, spends nothing
python3 $S/refresh.py               # aborts over --budget (default $2.00, hard cap $10)
```
`tracked.json` = advertiser page ids to re-check (from the Ads Library URL `view_all_page_id=`)
plus standing search terms, rotated a slice per ISO week so the cost stays flat. Each run:
downloads media for new ads in the SAME session (HD url first), upserts new ads on tracked pages
(keyword hits are discovery only, never auto-added), marks ads that disappeared from a fully
scraped page as ended, recomputes `performance_score`, writes `refresh-log/<date>.md`, prunes
scrape folders older than 12 weeks, then **runs `audit.py` against the index it just wrote**.
`--post-cmd "<your sync>"` (or `AD_LIBRARY_POST_CMD`) runs only when the audit passes. `--slack`
posts one line if `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID` are set. Re-running on the same day
reuses that day's scrape files instead of paying again (`--force` re-fires).

To schedule it, any scheduler works; example cron line (Mondays 07:00 local time):
```
set -a; source ~/.claude/skills/.env; set +a; S=~/.claude/skills/ad-library/scripts
0 7 * * 1  cd /path/to/workspace && set -a && . ~/.claude/skills/.env && set +a && python3 ~/.claude/skills/ad-library/scripts/refresh.py >> "$AD_LIBRARY_DIR/refresh-log/cron.log" 2>&1
```
If your laptop changes timezone, gate inside the job on `TZ=<your zone> date` rather than trusting
the scheduler's hour.

## The audit (run it any time, and before trusting a count)
```
set -a; source ~/.claude/skills/.env; set +a; S=~/.claude/skills/ad-library/scripts
python3 $S/audit.py               # every check, no network
python3 $S/audit.py --http 40     # also fetch 40 media/poster urls (ranged GET, not HEAD)
python3 $S/audit.py --video-only  # still-image ads become a failure instead of a warning
```
Read-only, exits non-zero on a failure. It checks: every controlled field holds a value from its
vocabulary · `personal_vs_slides` matches `format_class` · no row claims `watched` without a frame
artefact or transcript · a `copy_only` row carries no on-screen field · `country_iso` is real,
matches `market` and is not contradicted by the ad's own copy · `days_running` and
`survival_days_at_last_check` agree with `start_date`, `end_date` and `last_seen` ·
`performance_score` recomputes from its own inputs · scores are in range and have a basis · no
duplicate ad ids and no advertiser running one creative under two ad ids · still-image ads
(warning) · `aspect_ratio` matches the real dimensions · no tokens, credentials or PII in any
field · every `compliance_flag` row says `compliance-flagged` in `notes` · recorded paths exist.

## Hard-won gotchas
- **Media has a five-day shelf life.** Facebook CDN video URLs in a scrape JSON expire in about
  five days. Download the mp4 in the same session as the scrape or the creative is gone for good
  (and the row can only ever be `copy_only`).
- **fbcdn 302s a browser User-Agent.** `curl -A "<Chrome UA>"` without `-L` writes a 0-byte file
  and **exits 0**. Always `-L`, and check the file size, never the exit code. (Python's urllib
  follows redirects, so the scripts are not affected.)
- **One scrape file can hold the same ad many times.** The same ad comes back from several keyword
  searches. Collapse per ad id and keep the keywords on the row, or you trip the duplicate check
  and inflate every count.
- **A batch's own `niche` / `offer` fields must not vote.** If a scrape stamped every row with a
  label, blank it before classifying; feeding it back into the classifier is circular.
- **Do not judge an ad dead from a truncated page run.** A page scrape capped at
  `ads_per_page_run` may simply have cut off; `refresh.py` only marks deaths on complete runs.
- **Never write a file for a failed or empty Apify run.** An empty file is reused as "today's
  scrape" on a re-run and reads as "every ad died".
- **The right analysis is case-control, and country is the confound.** If you pick ads across
  run-length bands, "median survival by attribute" is biased; compare the composition of the
  longest third against the shortest, inside each country (long runners skew to the US in most
  clinic samples, so an uncontrolled contrast is really a US-vs-UK contrast).
- **Every write goes through `write_index` + `index_lock`.** The weekly refresh and a hand-run
  ingest can overlap; a bare `open()` lets whichever finishes last discard the other's work.
- Apify `usageTotalUsd` right after a run often reads $0. Measure spend as the delta of
  `/v2/users/me/limits` before and after if you need the real number.
- Take rows out by moving them to `<library>/removed.jsonl` with a reason, never by deleting, so
  a wrong call is reversible.

## Related
`video-ad-swipe-page` (step 0 reads this library, step 9 writes to it) · `static-ad-factory` ·
`meta-ads-analyst`.
