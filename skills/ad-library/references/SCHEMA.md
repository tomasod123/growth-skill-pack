# Ad library schema

One JSON object per line in `<library>/index.jsonl`. The library folder is `$AD_LIBRARY_DIR`, or
`./ad-library-data/` under the current directory. Every script reads and writes the same file
through `adlib_common.py`, under a file lock, via temp file + rename (one `.bak` kept).

## 0. Niches (controlled, `niche_rules.NICHES`)

| family | value | what it is |
|---|---|---|
| clinical | `skin` | skin concerns, facials, peels, lasers, general aesthetic clinic (the clinical fallback) |
| clinical | `injectables` | toxin, fillers, skin boosters, PRP and similar |
| clinical | `body-contouring` | fat reduction, muscle stimulation, cellulite, body sculpting devices |
| clinical | `hair-and-tattoo-removal` | laser hair removal, electrolysis, tattoo removal |
| clinical | `hair-restoration` | hair loss, transplants, scalp treatments |
| clinical | `dental` | dentistry, aligners, veneers, implants |
| clinical | `cosmetic-surgery` | surgical procedures |
| clinical | `medical-wellness` | weight loss, IV therapy, hormones, men's and women's health |
| software | `healthcare-software` | SaaS / AI / platforms sold to clinics, practices, hospitals, clinicians |
| software | `b2b-software` | any other SaaS sold to a business |
| services | `agency-to-smb` | agencies, lead marketplaces, web shops, coaching sold to business owners |
| trades | `trades-home-services` | a trade advertising its own work to a homeowner |

The niche is read from the ad's own words (`niche_basis: ad_content`); `--niche` at ingest is only
the fallback (`source_batch`). Tie-break order: clinical first, then software, agency, trades.
Software is decided by `sells_software()` (two distinct software signals) before anything else;
agency by `sells_to_a_business()` (addresses a business owner AND sells them growth).

Off-scope advertisers are refused at ingest by name (`niche_rules.OFF_SCOPE`): legal, finance and
insurance, consumer apps, recruitment, ecommerce product brands, musculoskeletal pain, other
non-aesthetic medicine, non-clinical beauty. Edit the list to change your library's scope.

## 1. Core row fields (written by ingest.py)

`id` (`<source-id>:<ad id>`) · `row_key` · `ad_id` · `client_or_competitor` (`client` | `competitor`) ·
`client` (whose research, or who owns the ad) · `advertiser` · `market` · `niche` · `niche_basis` ·
`offer` (batch label) · `format_class` · `format_note` (human prose) · `format_basis` · `format`
(mirror of `format_class`) · `hook` · `days_running` · `start` · `fit_score` (1-5) · `quality_score`
(1-5 or null) · `quality_basis` · `offer_tied` (bool, from the ad's own words only) ·
`personal_vs_slides` · `width` · `height` · `low_res` (width < 600) · `duration_s` · `has_audio` ·
`audio_speech` · `transcript_path` · `media_path` · `poster_path` · `lib_url` · `cta` ·
`body_excerpt` · `source_scrape` · `date` · `ingested_at` · `notes`.

### format_class (controlled)

| value | what it is | personal_vs_slides |
|---|---|---|
| `talking_head` | a person addresses the camera and speaks | personal |
| `testimonial` | a client, patient or customer tells their own story | personal |
| `organic_reel_cta` | an organic reel with a ten-second CTA close added | personal |
| `voiceover_broll` | b-roll under a voiceover; the speaker is never filmed talking | voiceover |
| `screen_demo` | a screen recording / product walkthrough, usually narrated | voiceover |
| `silent_broll_text` | b-roll with no speech; the message is on-screen text | silent |
| `text_slides` | static text cards, no motion b-roll | silent |
| `carousel_static` | a still image or carousel of stills | silent |
| `unclassified` | the evidence supports none of the above; `notes` must say why | unknown |

`format_basis`: `watched` · `transcript` · `prose` · `copy` · `probe` (no audio stream) ·
`scores-json` · `none`. `quality_basis`: `watched` · `text_only` · null.

### fit_score (1-5, a sort order at ingest, overwritten by watched scores)
1 base + home-market weight (`AD_LIBRARY_MARKETS`, first 1.5 / second 0.5 / others 0.25) +
authority on camera 1 + primary category 1 (secondary 0.25) + `offer_tied` 1.5 + a person on
camera 0.5, rounded and clamped. Clinic rows and software rows use their own authority/category
patterns (`ingest.FIT_PROFILES`).

## 2. SCHEMA v2: delivery, advertiser, geography, performance (enrich_row from raw_scan.py)

- **Delivery and survival:** `first_seen` · `last_seen` · `is_active` · `start_date` · `end_date`
  (null while live: the scraper reports today's date as the end date for every running ad) ·
  `days_running` (recomputed on every read) · `survival_days_at_last_check` (the conservative
  one; use it client-facing) · `variant_count` (collation count) · `platforms` ·
  `advertiser_ads_live` (a floor, not a census) · `relaunch_of` · `relaunch_count` (same body,
  same page, different ad id) · `status_history` (append-only, one entry per date).
- **Advertiser and geography:** `page_id` · `page_name` · `page_categories` · `page_like_count` ·
  `advertiser_type` (`single_site` | `multi_site` | `chain` | `training_provider` |
  `product_brand` | `software_vendor` | `unknown`) + `advertiser_type_basis` · `locations_named` ·
  `city` · `region` · `country_iso` + `country_basis` + `country_why` · `currency` ·
  `market_label_at_ingest`.
- **country_iso order:** the ad's own country field (`ad_field`) > the country of the Ads Library
  SEARCH that returned it (`search`) > the ad's own copy: TLD, `+dial` code, `City, ST ZIP`, UK
  postcode (`ad_copy`) > the same advertiser's other ads (`advertiser_copy`) > the per-batch
  `--market` label (`batch_label`).
- **performance_score 0-100** + `performance_basis`: survival 40 (log scale, capped at 730 days),
  still live 15, variants 15, platform breadth 10, relaunches 10, advertiser ads live 10.

**`performance_score` is NEVER spend and NEVER impressions.** Meta publishes neither for commercial
ads in the Ads Library (spend and reach are null on essentially every commercial row; they exist
only for political/issue ads and some EU-delivered ads). Say what the number is, how long the ad
survived and how widely the advertiser spread it, or do not use it.

## 3. Creative attributes (`creative_tags.jsonl` sidecar, folded in by merge_tags.py)

Produced by WATCHING the ad. Keyed on `id` (or `row_key` / `ad_id`). Identity fields and
scrape-derived fields are never overwritten.

| field | values |
|---|---|
| `tag_basis` | `watched` · `transcript` · `copy_only` · `none` |
| `person_on_camera` | `named_practitioner` · `unnamed_staff` · `patient` · `founder_or_exec` · `customer` · `model_or_actor` · `none` |
| `setting` | `clinic_treatment_room` · `clinic_reception` · `office_or_workspace` · `plain_wall_or_studio` · `home_or_car` · `outdoor` · `screen_recording` · `graphic_only` |
| `captions` | `burned_in_full` · `burned_in_keywords` · `none` |
| `voice` | `on_camera_speech` · `voiceover` · `silent` |
| `music` | `none` · `bed` · `trending_track` |
| `offer_type` | `free_consultation` · `price_led` · `discount_percent` · `discount_amount` · `free_treatment_or_taster` · `bundle` · `membership_or_plan` · `finance_payment_plan` · `competition_giveaway` · `demo_booking` · `free_trial` · `lead_magnet` · `free_audit_or_assessment` · `none` |
| `callout_type` | `demographic` · `problem` · `objection` · `location` · `none` |
| `claim_type` | `results_promise` · `credential_authority` · `technology_novelty` · `social_proof` · `education_only` · `none` |
| `urgency` | `deadline_date` · `limited_places` · `seasonal` · `none` |
| `social_proof` | `before_after` · `patient_testimonial` · `customer_testimonial` · `review_count` · `customer_logos` · `case_study_numbers` · `celebrity_or_influencer` · `none` |
| `landing_type` | `booking_page` · `lead_form` · `messenger_or_whatsapp` · `homepage` · `demo_booking` · `trial_signup` · `content_download` · `unknown` |
| booleans | `device_shown` / `device_is_hero` · `credentials_shown` · `guarantee` · `compliance_flag` · `replicable_by_small_team` |
| free text | `aspect_ratio` · `price_shown` / `price_currency` / `price_context` · `callout` · `claim_text` · `guarantee_text` · `hook_seconds_to_offer` · `cta_button` · `compliance_market` · `compliance_note` · `replication_note` · `tag_notes` |

A `copy_only` row has null `person_on_camera`, `setting`, `captions`, `voice`, `music` and
`aspect_ratio`, because nobody could see the creative. The audit enforces that.

The two fields that decide a swipe page: `replicable_by_small_team` (an ad needing a second
operator, a studio crew or a device the client does not own is a reference, not a brief) and
`compliance_flag` (true = must not be modelled in `compliance_market`; `notes` must then say
`compliance-flagged, do not model`).

Example sidecar line:
```json
{"id": "clinic-a-swipe-2026-09-03:AD_ID", "tag_basis": "watched", "person_on_camera": "named_practitioner", "setting": "clinic_treatment_room", "captions": "burned_in_full", "voice": "on_camera_speech", "offer_type": "free_consultation", "replicable_by_small_team": true, "compliance_flag": false, "format_class": "talking_head", "quality_score": 4, "quality_basis": "watched"}
```

## 4. Other files in the library folder

| file | written by | what |
|---|---|---|
| `index.jsonl` | ingest, refresh, backfill, merge_tags | the library |
| `creative_tags.jsonl` | you (after watching) | creative attributes sidecar |
| `tracked.json` | you, or `refresh.py --seed-tracked` | pages + searches for the weekly refresh |
| `scrapes/<date>/*.json` | refresh.py | raw scrape payloads (last 12 weeks kept) |
| `work/v2/raw_index.json` | raw_scan.py | observation index the v2 fields derive from |
| `media/<client>/<ad id>.mp4/.jpg` | refresh.py | creative downloaded in the same session |
| `posters/<ad id>.jpg` | ingest.py | poster frame at 12% of runtime |
| `refresh-log/<date>.md` | refresh.py | new ads, ads that died, biggest movers |
| `removed.jsonl` | you | rows taken out, with a reason, so a wrong call is reversible |
