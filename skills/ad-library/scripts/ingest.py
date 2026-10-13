#!/usr/bin/env python3
"""Ingest ads into the ad library ($AD_LIBRARY_DIR/index.jsonl, default ./ad-library-data/), one row per ad,
pointing at media and transcripts where they already are (never re-downloads).

Sources:
  --from-swipe <workdir>      a video-ad-swipe-page work dir (shortlist.json + media_meta.json + media/ + hooks/ + tx/)
  --from-json <file>          any scrape/pick list (a picks.json, finalists.json or top40.json from earlier research, or a hand-written
                              own-ads.json). Keys are read tolerantly: id|ad_archive_id|base, page|page_name|advertiser,
                              days|days_running, lib|lib_url|url, cta, title, body, start, country|geo|market, video, poster.
Per-source metadata (inputs, never guessed): --client <slug who researched it> --kind competitor|client --market GB|US|AU
  --niche "skin" --offer "free consultation + £50 off" --source "label of the scrape"
  (B2B example: --niche healthcare-software --offer "book a demo")
Media/transcripts by pattern from row fields: --media-dir DIR --media-pattern "{id}.mp4" --poster-pattern "{id}.jpg"
  --tx-dir DIR --tx-pattern "{id}.txt" (fields: id, base, rank, page_slug, n)

WHAT IS CAPTURED AT INGEST (all of it, every time):
  format_class  one of the CONTROLLED VOCABULARY below. Never free text. A row that cannot be
                classified from evidence is written as "unclassified" AND MUST carry a reason in
                notes - ingest refuses to write an unexplained unclassified/unknown row.
  format_note   the original human prose about the creative ("Doctor talking head, plain wall...").
  format_basis  watched | transcript | prose | copy | scores-json | none - how format_class was decided.
  quality_score 1-5 production standard, plus quality_basis (watched | text_only | None).
  fit_score     1-5 from the rubric in fit() - closeness to YOUR target: a home market (set
                AD_LIBRARY_MARKETS, e.g. "GB,IE,US"), an authority figure on camera, the right
                category, a concrete offer, a person speaking. Clinic and software rows use
                their own category/authority patterns (FIT_PROFILES).
  offer_tied    from the AD'S OWN WORDS only (hook + body + transcript + title). The --offer and
                --niche labels are per-batch inputs and are deliberately excluded: including them
                once marked every row in a batch offer_tied.
  width/height/low_res/duration_s/has_audio  ffprobe of media_path. low_res = width < 600.
  poster_path   generated with ffmpeg at 12% of duration when media exists and no poster was given.
  row_key       the index id, kept alongside for any external copy you sync to.
  ingested_at   ISO timestamp, set once and never overwritten.

  python3 ingest.py --from-json picks.json --client acme --kind competitor --market GB --niche skin --offer "..." \
      --media-dir research/media --media-pattern "{base}.mp4" --poster-pattern "{base}.jpg" --tx-dir research/tx --tx-pattern "{base}.txt" --source "acme research 2026-09-03" [--dry-run]
"""
import argparse
import datetime
import io
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adlib_common import (LIB_DEFAULT, enrich_row, ensure_library, index_lock,  # noqa: E402
                          write_index, note_append)

from niche_rules import NICHES, SOFTWARE_NICHES, classify_niche, scope_check  # noqa: E402

# ---------------------------------------------------------------- controlled vocabulary
FORMAT_CLASSES = [
    "talking_head",       # a person addresses the camera and speaks
    "silent_broll_text",  # b-roll with no speech; the message is on-screen text (or nothing)
    "voiceover_broll",    # b-roll under a spoken voiceover; the speaker is not filmed talking
    "testimonial",        # a client/patient tells their own story, on camera or in voiceover
    "text_slides",        # static text cards, headshot cards, no motion b-roll
    "organic_reel_cta",   # an organic reel with the ten-second CTA close bolted on
    "carousel_static",    # a still image (or carousel of stills) with animated text
    "screen_demo",        # a screen recording / product walkthrough, usually narrated (software ads)
    "unclassified",       # evidence does not support any of the above - notes must say why
]
PVS = {"talking_head": "personal", "testimonial": "personal", "organic_reel_cta": "personal",
       "voiceover_broll": "voiceover", "silent_broll_text": "silent", "text_slides": "silent",
       "carousel_static": "silent", "screen_demo": "voiceover", "unclassified": "unknown"}

# free-text prose written by whoever watched the ad -> the controlled value
PROSE_TO_CLASS = [
    (r"talking head|person to camera|one smiling woman to camera", "talking_head"),
    (r"testimonial", "testimonial"),
    (r"text slides|slides with", "text_slides"),
    (r"organic reel \+ ten[- ]second cta", "organic_reel_cta"),
    (r"carousel|static image|still image", "carousel_static"),
    (r"screen ?(recording|demo|share)|product (demo|walkthrough)|screencast", "screen_demo"),
    (r"voice ?over", "voiceover_broll"),
    (r"silent b-roll|b-roll", "silent_broll_text"),
    (r"organic reel", "talking_head"),
]

# offer_tied: a specific offer, price or free item, named in the ad's own words
OFFER = re.compile(
    r"free (consult\w*|skin (analysis|consult\w*|assessment|scan)|session|treatment|facial|scan|"
    r"analysis|voucher|trial|gift|ai skin scan\w*)"
    r"|complimentary [a-z ]{0,20}(consult\w*|analysis|scan|facial|treatment|session)"
    r"|(only|just|for|from|now)\s?[£$]\s?\d"
    r"|[£$]\s?\d[\d,.]*\s?(off\b|voucher|special|facial|consult|session|package)"
    r"|save\s(up to\s)?[£$]\s?\d|\d{1,3}\s?%\s?off"
    r"|new (client|patient)s?'?s? ?(special|pricing|offer|only|receive|discount)"
    r"|off your (very )?first|off (a|your) first (treatment|visit|session)"
    r"|intro(ductory)? offer|introductory|welcome (offer|package)|limited time offer|special offer"
    r"|new patient special|model prices|discounted model|trial today|book your trial"
    r"|always complimentary|[£$]\s?\d[\d,.]*\s?(secures|holds|deposit)|fully redeemable"
    # B2B offers: a demo, a trial, a free audit, or a named content asset
    r"|book a (free )?demo|request a demo|free demo|get a demo|free trial|\d+[- ]day (free )?trial"
    r"|start (for |your )?free|free (audit|assessment|roi (report|analysis)|consultation call|strategy call)"
    r"|(free|download|get) (the |our )?(guide|ebook|e-book|report|checklist|template|playbook|whitepaper|calculator)"
    r"|(join|register for) (our|the) (free )?(webinar|workshop|masterclass)",
    re.I)
DOCTOR = re.compile(r"\bdr\.?\b|\bdoctor|gmc|gdc|medical lead|nurse prescriber|physician|md\b|dermatolog", re.I)
SKINAES = re.compile(r"skin|aesthetic|facial|inject|filler|peel|laser|derm|microneedl|pigment|acne|anti-?wrinkle|hydrafacial|botox", re.I)
BODYCON = re.compile(r"emsculpt|emsella|coolsculpt|body contour|fat reduc|muscle|vanquish|sculpt", re.I)
# fit profiles: which words count as an AUTHORITY on camera and as the PRIMARY / SECONDARY category.
# Clinic rows use "clinic"; software rows (niche in SOFTWARE_NICHES) use "software". Edit freely.
FIT_PROFILES = {
    "clinic": {"authority": DOCTOR, "primary": SKINAES, "secondary": BODYCON},
    "software": {
        "authority": re.compile(r"\b(founder|co-?founder|ceo|cmo|cto|chief|clinician|physician|doctor|dr\.?|"
                                r"nurse|practice (owner|manager)|customer|i'?m [A-Z][a-z]+)\b", re.I),
        "primary": re.compile(r"clinic|practice|patient|clinical|healthcare|hospital|provider|charting|"
                              r"documentation|intake|scheduling|billing|ehr|emr", re.I),
        "secondary": re.compile(r"\bsaas\b|software|platform|automation|\bai\b", re.I),
    },
}


def market_weights():
    """Home market first. AD_LIBRARY_MARKETS="GB,IE,US" -> GB 1.5, IE 0.5, US 0.25."""
    order = [c.strip().upper() for c in (os.environ.get("AD_LIBRARY_MARKETS") or "US,GB,AU").split(",") if c.strip()]
    return {cc: w for cc, w in zip(order, [1.5, 0.5, 0.25, 0.25, 0.25])}


PERSON = re.compile(r"\b(i|i'm|we|my|me|our|you|your)\b", re.I)


def g(row, *keys, default=None):
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return default


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")[:60]


def read_tx(path):
    if not path or not os.path.exists(path):
        return None
    return io.open(path, encoding="utf-8", errors="replace").read().strip()


# ---------------------------------------------------------------- media probing
def probe(path):
    """ffprobe a local file -> width/height/duration/audio. Never downloads."""
    if not path or not os.path.exists(path):
        return {}
    out = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                          "-show_streams", "-show_format", path], capture_output=True, text=True).stdout
    try:
        d = json.loads(out)
    except ValueError:
        return {}
    v = [s for s in d.get("streams", []) if s.get("codec_type") == "video"]
    a = [s for s in d.get("streams", []) if s.get("codec_type") == "audio"]
    dur = d.get("format", {}).get("duration")
    return {"width": v[0]["width"] if v else None, "height": v[0]["height"] if v else None,
            "duration_s": round(float(dur), 1) if dur else None, "has_audio": bool(a)}


def make_poster(media, lib, ad_id, dur):
    """One frame at 12% of the runtime, written to <lib>/posters/<ad_id>.jpg."""
    dest = os.path.join(lib, "posters", f"{ad_id}.jpg")
    if os.path.exists(dest):
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "quiet", "-ss", str(round((dur or 1) * 0.12, 2)),
                    "-i", media, "-frames:v", "1", "-q:v", "3", dest], check=False)
    return dest if os.path.exists(dest) else None


# ---------------------------------------------------------------- scoring
def ad_blob(row, hook, tx):
    """ONLY the ad's own words. The --offer and --niche labels are batch inputs, not ad copy,
    and including them flips every row in a batch to offer_tied."""
    return " ".join(str(x or "") for x in (hook, g(row, "title", default=""), g(row, "body", default=""), tx))


def fit(market, cls, offer_tied, blob, niche=None):
    """1-5: closeness to your target profile. A sort order at ingest, never a verdict: the watched
    score from --scores-json overwrites it."""
    prof = FIT_PROFILES["software" if niche in SOFTWARE_NICHES else "clinic"]
    pts = 1.0
    pts += market_weights().get((market or "").upper(), 0.0)
    if prof["authority"].search(blob):
        pts += 1.0
    if prof["primary"].search(blob):
        pts += 1.0
    elif prof["secondary"].search(blob):
        pts += 0.25
    if offer_tied:
        pts += 1.5
    if cls in ("talking_head", "testimonial", "organic_reel_cta"):
        pts += 0.5
    return max(1, min(5, int(round(pts))))


def classify(row, prose, tx, media, has_audio):
    """(format_class, format_basis). Evidence order: explicit field > prose > transcript > none."""
    explicit = g(row, "format_class")
    if explicit:
        if explicit not in FORMAT_CLASSES:
            raise SystemExit(f"format_class {explicit!r} is not in the controlled vocabulary: {FORMAT_CLASSES}")
        return explicit, g(row, "format_basis", default="scores-json")
    if prose:
        low = str(prose).lower()
        for pat, c in PROSE_TO_CLASS:
            if re.search(pat, low):
                return c, "prose"
    if tx and len(tx.split()) >= 8:
        # speech exists; without frames we cannot tell a talking head from a voiceover
        return ("voiceover_broll", "transcript") if not PERSON.search(tx) else ("talking_head", "transcript")
    if media and has_audio is False:
        return "silent_broll_text", "probe"
    return "unclassified", "none"


def build_row(row, a, idx):
    adid = str(g(row, "id", "ad_archive_id", "ad_id", default=""))
    if not adid and g(row, "lib", "lib_url", "url"):
        m = re.search(r"id=(\d+)", g(row, "lib", "lib_url", "url")); adid = m.group(1) if m else ""
    if not adid:
        adid = g(row, "base", default=f"row{idx}")
    fields = {"id": adid, "base": g(row, "base", default=adid), "rank": g(row, "rank", default=idx),
              "n": idx, "page_slug": slugify(g(row, "page", "page_name", "advertiser", default=""))}

    def pat(p, d):
        if not p:
            return None
        try:
            name = p.format(**fields)
        except KeyError:
            return None
        return os.path.join(d, name) if d else name

    media = g(row, "media_path") or pat(a.media_pattern, a.media_dir)
    media = media if media and os.path.exists(media) else None
    poster = g(row, "poster_path") or pat(a.poster_pattern, a.media_dir)
    poster = poster if poster and os.path.exists(poster) else None
    txp = g(row, "transcript_path") or pat(a.tx_pattern, a.tx_dir)
    tx = read_tx(txp)

    pr = probe(media)
    if media and not poster and not a.no_poster:
        poster = make_poster(media, a.library, adid, pr.get("duration_s"))

    hook = (g(row, "hook") or (tx.split(". ")[0][:140] if tx else None)
            or (g(row, "title") or "")[:140] or (g(row, "body") or "").split("\n")[0][:140])
    prose = g(row, "format")
    if prose and str(prose).strip().lower() in ("unknown", "none", "-"):
        prose = None

    cls, basis = classify(row, prose, tx, media, pr.get("has_audio"))
    ab = ad_blob(row, hook, tx)
    offer_tied = bool(g(row, "offer_tied")) if g(row, "offer_tied") is not None else bool(OFFER.search(ab))
    fit_blob = " ".join(str(x) for x in (ab, g(row, "page", "page_name", "advertiser", default=""), a.niche, a.offer))

    days = g(row, "days", "days_running")
    try:
        days = int(days) if days is not None else None
    except (TypeError, ValueError):
        days = None
    country = g(row, "country", "geo", "market", default=a.market)
    country = {"UK": "GB"}.get(country, country)
    quality = g(row, "quality_score", default=a.quality)
    qbasis = g(row, "quality_basis") or ("watched" if quality is not None and media else
                                         ("text_only" if quality is not None else None))
    # NICHE IS READ FROM THE AD, NOT FROM --niche. Stamping one label per scrape batch is exactly
    # what leaves "skin, doctor-led clinic", "skin concerns" and "aesthetic clinic, general"
    # overlapping. --niche is only the fallback when the ad's own words name nothing.
    scope_text = " ".join(str(x) for x in (ab, g(row, "page", "page_name", "advertiser", default=""),
                                           prose, g(row, "notes", default="") or "", tx or ""))
    row_for_scope = {"page_categories": g(row, "page_categories", "categories", default=[]) or []}
    ok, refuse_why, guessed, warn_why = scope_check(row_for_scope, scope_text)
    if guessed:
        niche, niche_basis = guessed, "ad_content"
    else:
        niche, niche_basis = a.niche, "source_batch"
    row_scope = (ok, refuse_why, warn_why)
    fit_score = g(row, "fit_score")
    if fit_score is None:
        fit_score = fit(country, cls, offer_tied, fit_blob, niche)

    return {
        "_scope": row_scope,
        "id": f"{a.source_id}:{adid}", "row_key": f"{a.source_id}:{adid}", "ad_id": adid,
        "client_or_competitor": a.kind, "client": a.client,
        "advertiser": g(row, "page", "page_name", "advertiser", default=""), "market": country,
        "niche": niche, "niche_basis": niche_basis, "offer": g(row, "offer") or a.offer,
        "format_class": cls, "format_note": prose, "format_basis": basis, "format": cls,
        "hook": hook, "days_running": days, "start": g(row, "start", default=None),
        "fit_score": fit_score, "quality_score": quality, "quality_basis": qbasis,
        "offer_tied": offer_tied, "personal_vs_slides": PVS[cls],
        "width": pr.get("width"), "height": pr.get("height"),
        "low_res": (pr["width"] < 600) if pr.get("width") else None,
        "duration_s": pr.get("duration_s"), "has_audio": pr.get("has_audio"),
        "audio_speech": (bool(tx and tx.strip()) if media else None),
        "transcript_path": txp if tx is not None else None, "media_path": media, "poster_path": poster,
        "lib_url": g(row, "lib", "lib_url", "url", default=None), "cta": g(row, "cta", "cta_text", default=None),
        "body_excerpt": (g(row, "body", default="") or "")[:200], "source_scrape": a.source, "date": a.date,
        "ingested_at": datetime.datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "notes": g(row, "notes", default=None),
    }


def load_swipe(workdir):
    sl = json.load(open(os.path.join(workdir, "shortlist.json"), encoding="utf-8"))
    meta = {}
    mp = os.path.join(workdir, "media_meta.json")
    if os.path.exists(mp):
        m = json.load(open(mp, encoding="utf-8"))
        meta = {str(k): v for k, v in (m.items() if isinstance(m, dict) else ((x.get("id"), x) for x in m))}
    rows = []
    for r in sl:
        r = dict(r); mm = meta.get(str(r.get("id")), {})
        if mm.get("hook"):
            r["hook"] = mm["hook"]
        for sub, key, ext in (("media", "media_path", ".mp4"), ("media", "poster_path", ".jpg"),
                              ("tx", "transcript_path", ".txt"), ("hooks", "transcript_path", ".txt")):
            p = os.path.join(workdir, sub, f"{r.get('id')}{ext}")
            if os.path.exists(p) and not r.get(key):
                r[key] = p
        rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", default=LIB_DEFAULT)
    ap.add_argument("--from-swipe"); ap.add_argument("--from-json")
    ap.add_argument("--client", required=True, help="slug of the client this research was done for (or who owns the ad)")
    ap.add_argument("--kind", choices=["competitor", "client"], default="competitor")
    ap.add_argument("--market", default=None)
    ap.add_argument("--niche", required=True, choices=NICHES,
                    help="fallback niche for rows whose own words name no treatment. Every other "
                         "row is classified from the ad itself. One of: " + " ".join(NICHES))
    ap.add_argument("--offer", default="")
    ap.add_argument("--source", required=True, help="label of the scrape, e.g. 'clinic-a research 2026-09-03'")
    ap.add_argument("--source-id", help="short id prefix for rows (default: slug of --source)")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--media-dir"); ap.add_argument("--media-pattern"); ap.add_argument("--poster-pattern"); ap.add_argument("--tx-dir"); ap.add_argument("--tx-pattern")
    ap.add_argument("--quality", type=float, default=None, help="quality_score for the whole batch (only if someone watched them)")
    ap.add_argument("--scores-json", help='{"<ad_id>": {"format_class": "talking_head", "fit_score": 5, "quality_score": 4, "notes": "..."}} per-ad overrides')
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--update", action="store_true", help="overwrite rows with the same id")
    ap.add_argument("--no-poster", action="store_true", help="do not generate posters with ffmpeg")
    ap.add_argument("--allow-off-scope", action="store_true",
                    help="admit rows the scope gate refuses (it names each one first). Use only "
                         "after judging every refusal by hand")
    ap.add_argument("--allow-unexplained", action="store_true",
                    help="permit unclassified rows with no reason in notes (do not use; it is how the index rotted)")
    ap.add_argument("--no-enrich", action="store_true",
                    help="skip the SCHEMA v2 backfill from the raw scrapes (do not use)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    a.source_id = a.source_id or slugify(a.source)
    if a.from_swipe:
        rows = load_swipe(a.from_swipe)
    elif a.from_json:
        d = json.load(open(a.from_json, encoding="utf-8")); rows = d if isinstance(d, list) else (d.get("ads") or d.get("picks") or list(d.values()))
    else:
        ap.error("--from-swipe or --from-json")
    if a.limit:
        rows = rows[:a.limit]
    overrides = json.load(open(a.scores_json, encoding="utf-8")) if a.scores_json else {}
    ensure_library(a.library)
    idx_path = os.path.join(a.library, "index.jsonl")
    existing = {}
    if os.path.exists(idx_path):
        for line in io.open(idx_path, encoding="utf-8"):
            if line.strip():
                r = json.loads(line); existing[r["id"]] = r
    new, upd, skip = 0, 0, 0
    out = []
    for i, r in enumerate(rows, 1):
        row = build_row(r, a, i)
        ov = overrides.get(row["ad_id"], {})
        if ov.get("format_class") and ov["format_class"] not in FORMAT_CLASSES:
            raise SystemExit(f"scores-json format_class {ov['format_class']!r} is not in {FORMAT_CLASSES}")
        row.update(ov)
        if ov.get("format_class"):
            row["format"] = ov["format_class"]
            row["personal_vs_slides"] = PVS[ov["format_class"]]
            row["format_basis"] = ov.get("format_basis", "scores-json")
        if row["id"] in existing:
            row["ingested_at"] = existing[row["id"]].get("ingested_at") or row["ingested_at"]
        if row["id"] in existing and not a.update:
            skip += 1; continue
        upd += row["id"] in existing
        new += row["id"] not in existing
        out.append(row)

    # SCHEMA v2: fill delivery, survival, advertiser, geography and the performance proxy from the
    # raw scrapes on disk (raw_scan.py). Nothing here is guessed; a field with no evidence stays
    # None and says why in notes. See references/SCHEMA.md.
    if not a.no_enrich:
        raw_path = os.path.join(a.library, "work", "v2", "raw_index.json")
        if os.path.exists(raw_path):
            idx = json.load(open(raw_path, encoding="utf-8"))
            for r in out:
                enrich_row(r, idx)
        else:
            print(f"  note: no {raw_path} — run raw_scan.py to fill the SCHEMA v2 fields")

    # THE OFF-SCOPE GATE. Ads Library keyword searches return anything that uses your words:
    # "free consultation" pulls in personal-injury lawyers, window installers, tax-relief firms,
    # pest control and ride-hailing apps; in one batch over a fifth of the picks were off-scope.
    # Only the niches in niche_rules.NICHES get in, and a refusal always names the row.
    refused = [(r, r["_scope"][1]) for r in out if not r["_scope"][0]]
    warned = [(r, r["_scope"][2]) for r in out if r["_scope"][0] and r["_scope"][2]]
    for r in out:
        r.pop("_scope", None)
    if refused and not a.allow_off_scope:
        print(f"  REFUSED: {len(refused)} row(s) are outside the library's scope (niche_rules.OFF_SCOPE). "
              f"Nothing was written.")
        for r, why in refused:
            print(f"    {r['id']}  {str(r.get('advertiser'))[:40]}")
            print(f"      {why}")
        print("  Drop them from the input, or pass --allow-off-scope if you have judged each one "
              "and disagree. Rows already in the library go to removed.jsonl, never deleted.")
        return 1
    if refused:
        print(f"  --allow-off-scope: {len(refused)} off-scope row(s) admitted anyway:")
        for r, why in refused:
            note_append(r, "admitted with --allow-off-scope despite: " + why)
            print(f"    {r['id']}  {str(r.get('advertiser'))[:40]}")
    for r, why in warned:
        print(f"  CHECK: {r['id']}  {str(r.get('advertiser'))[:40]}")
        print(f"    {why}")

    # A row nobody can filter on must at least say why. Without this rule a library fills with
    # "unknown" rows that no query can retrieve.
    bad = [r for r in out if (r["format_class"] == "unclassified" or r["quality_score"] is None) and not r.get("notes")]
    if bad and not a.allow_unexplained:
        print(f"  REFUSED: {len(bad)} row(s) are unclassified or unscored with no reason in notes:")
        for r in bad[:10]:
            print(f"    {r['id']}  format_class={r['format_class']}  quality_score={r['quality_score']}")
        print("  Add a `notes` reason per row (or --scores-json), or pass --allow-unexplained.")
        return 1

    media_ok = sum(1 for r in out if r["media_path"]); tx_ok = sum(1 for r in out if r["transcript_path"])
    unc = sum(1 for r in out if r["format_class"] == "unclassified")
    print(f"  source {a.source!r}: rows {len(rows)} · new {new} · updated {upd} · skipped (exists) {skip} · "
          f"media on disk {media_ok} · transcripts {tx_ok} · unclassified {unc}")
    for r in out[:5]:
        print(f"    {r['id']}  {str(r['advertiser'])[:26]:26s} {r['market'] or '-':3s} "
              f"{(str(r['days_running'])+'d') if r['days_running'] is not None else '-':>6s} "
              f"{r['niche']:>22s} fit {r['fit_score']} q {r['quality_score'] if r['quality_score'] is not None else '-'} "
              f"{'offer' if r['offer_tied'] else '     '} {r['format_class']:18s} "
              f"{str(r['width'] or '-')}x{str(r['height'] or '-'):5s} {'mp4' if r['media_path'] else '   '} {'tx' if r['transcript_path'] else '  '}")
    if a.dry_run:
        print("  [dry-run] nothing written"); return 0
    for r in out:
        existing[r["id"]] = r
    # write_index + index_lock, never a bare open(): the weekly refresh and a hand-run ingest can
    # overlap, and whichever finishes last would silently discard the other's work.
    with index_lock(a.library):
        write_index(list(existing.values()), a.library)
    print(f"  -> {idx_path}: {len(existing)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
