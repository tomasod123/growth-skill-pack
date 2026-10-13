#!/usr/bin/env python3
"""Step 2: filter + rank the raw Ads Library payload into a shortlist.

SELECTION IS ON FIT, NOT LONGEVITY.
An example earns its place by being something this business could run next week, not by having
run for a long time somewhere else. So the sort is FIT first, quality second, and run length is
evidence and a tiebreak only. A 900-day ad selling a different offer loses to a 90-day ad
selling the client's exact offer with a person on camera.

Fit here is computed from the ad's COPY, which is all a scrape can see. It is a sort order for
the hand review, never the verdict. The exclusions that decide a page (a person actually on
camera, equipment or product the client has, replicable by a small team on a phone, no
compliance flag) need eyes on the video: see the checklist this prints, and step 2 of SKILL.md.

Two profiles set sensible defaults (every regex can still be overridden by its flag):
  --profile clinic  a clinic / med spa / healthcare provider selling a consultation or treatment
                    to a patient. Drops product shops, training providers, B2B pitches, and ads
                    naming a prescription-only medicine.
  --profile b2b     a B2B SaaS / software / services company selling a demo, trial, audit or
                    content offer to a business buyer (e.g. healthcare software sold to clinics).
                    Keeps "for clinics" / "practitioners" language (that IS the audience), keeps
                    Download / Apply now / Sign up CTAs, and drops consumer shops and job ads.

Keeps: video ads only, active, a similar OFFER, a named CONCERN (pain point), not excluded by the
profile, not your own or your clients' pages (--exclude-pages), not an ad selling equipment the
client does not have (--exclude-device). Dedupes by (page, first 120 chars of body) keeping the
longest runner.

  python3 02_rank.py --client clinic-a --countries GB,US --top 40
  python3 02_rank.py --raw path/to/raw_ads.json --out shortlist.json \
      --concern 'acne|pigment|rosacea' --offer 'consult|book|assessment' \
      --offer-exact 'free consultation|complimentary consultation' \
      --exclude-device 'emsculpt|coolsculpt|hydrafacial|cryolipolysis|morpheus|co2 laser' \
      --exclude-pages my-own-pages.txt --ban 'shop now|academy'
  python3 02_rank.py --client my-saas --profile b2b --countries US,GB \
      --offer-exact 'book a demo|free trial' --concern 'no.show|admin|documentation|burnout|denial'
  python3 02_rank.py --client clinic-a --rank-by days      # evidence order only, not selection order
"""
import argparse
import ast
import datetime
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

# Your own brand and your own clients: never put a client's own ad, or another client's, on a
# swipe page. Pass them with --exclude-pages <file> (one page name per line, substring match).
EXCLUDE_PAGES_DEFAULT = []

PRODUCT_RX = r"\{\{product|shopify|/products/|/collections/|free shipping|add to cart|money.back|buy now|order now|subscription box|wholesale|device for sale"
JOBS_RX = r"we'?re hiring|now hiring|job vacanc|apply for this role|join our team as"

PROFILES = {
    "clinic": {
        "bad_cta": {"Shop now", "Visit Instagram profile", "Visit Instagram", "Order now", "Download", "Play game",
                    "Install now", "Subscribe", "Watch more", "Listen now", "Buy tickets", "Donate now", "Apply now",
                    "Get quote"},
        # B2B / training language means the ad is selling TO clinics, not to patients
        "audience_drop_rx": r"\bacademy\b|\btraining\b|certif|salon owners|practitioners|for clinics\b|\bcourse\b",
        "audience_drop_label": "training/B2B",
        "offer_rx": (r"consultation|consult\b|book(ing)? (a|your|an|now|online)|appointment|assessment|analysis|"
                     r"free scan|clinic|treatment plan|trial session|first session|discovery call|complimentary"),
        "concern_rx": (r"acne|scar|pigment|melasma|rosacea|pore|texture|fine line|wrinkl|sun damage|"
                       r"under.eye|dark circle|redness|uneven|laxity|stubborn fat|belly|tone|"
                       r"muscle|hair loss|thinning|receding|bald"),
        "drop_pom": True,
    },
    "b2b": {
        "bad_cta": {"Shop now", "Order now", "Play game", "Buy tickets", "Donate now", "Listen now", "Install now"},
        # consumer / patient-facing language means the ad is selling to the END customer, not the business
        "audience_drop_rx": r"\bbook your (facial|treatment|appointment)\b|\bour patients love\b|\bnew patient special\b|\bmodel prices\b",
        "audience_drop_label": "consumer-facing, not B2B",
        "offer_rx": (r"demo|free trial|trial\b|start (for )?free|get started|sign up|book a (call|meeting)|"
                     r"consultation|assessment|audit|webinar|guide|ebook|e-book|report|checklist|template|"
                     r"calculator|case study|whitepaper|playbook|pricing|see how|learn how"),
        "concern_rx": (r"no.shows?|admin|paperwork|documentation|charting|notes|burnout|staffing|front desk|"
                       r"missed calls|scheduling|billing|claims?|denials?|revenue|compliance|hipaa|soc ?2|"
                       r"patient (intake|experience|retention)|reviews|referrals|wait times|manual|"
                       r"spreadsheets?|churn|pipeline|leads?|conversion|roi|cost|time back|hours"),
        "drop_pom": False,
    },
}
# Named prescription-only medicines (UK reg 284 / AU S4 and similar rules): kept OUT of a clinic
# shortlist so no script is ever modelled on an ad that names one.
POM_RX = (r"\bbotox\b|dysport|xeomin|bocouture|azzalure|juvederm|restylane|\bfiller|anti.wrinkle inject|"
          r"wrinkle relax|tox\b|roaccutane|isotretinoin|tretinoin|hydroquinone|ozempic|semaglutide|mounjaro|"
          r"minoxidil|finasteride|dutasteride")


def norm_snapshot(a):
    sn = a.get("snapshot")
    if isinstance(sn, str):
        try:
            sn = ast.literal_eval(sn)
        except Exception:  # noqa: BLE001
            sn = {}
    return sn or {}


def first_video(sn):
    for v in sn.get("videos") or []:
        u = v.get("video_hd_url") or v.get("video_sd_url")
        if u:
            return u, v.get("video_preview_image_url")
    for c in sn.get("cards") or []:
        u = c.get("video_hd_url") or c.get("video_sd_url")
        if u:
            return u, c.get("video_preview_image_url")
    for v in sn.get("extra_videos") or []:
        u = v.get("video_hd_url") or v.get("video_sd_url")
        if u:
            return u, v.get("video_preview_image_url")
    return None, None


def normalise(ads, now):
    rows = []
    for a in ads:
        sn = norm_snapshot(a)
        body = sn.get("body")
        body = body.get("text") if isinstance(body, dict) else (body or "")
        if not body:
            for c in sn.get("cards") or []:
                if c.get("body"):
                    body = c["body"]
                    break
        sd = a.get("start_date_formatted") or ""
        d0 = None
        if sd:
            try:
                d0 = datetime.datetime.strptime(sd[:10], "%Y-%m-%d")
            except ValueError:
                d0 = None
        if d0 is None and a.get("start_date"):
            try:
                d0 = datetime.datetime.utcfromtimestamp(int(a["start_date"]))
            except Exception:  # noqa: BLE001
                d0 = None
        if d0 is None:
            continue
        video, poster = first_video(sn)
        q = a.get("_q") or ""
        country = q.split("::")[0] if "::" in q else ""
        if not country:  # fallback: the search URL the actor was given carries country=XX
            m = re.search(r"[?&]country=([A-Z]{2})", a.get("url") or "")
            country = m.group(1) if m else ((a.get("targeted_or_reached_countries") or [""])[0] or "")
        rows.append({
            "id": str(a.get("ad_archive_id")),
            "page": (a.get("page_name") or sn.get("page_name") or "").strip(),
            "page_id": a.get("page_id"),
            "q": q,
            "country": country,
            "countries": a.get("targeted_or_reached_countries") or [],
            "platforms": a.get("publisher_platform") or [],
            "start": d0.strftime("%Y-%m-%d"),
            "days": (now - d0).days,
            "active": str(a.get("is_active")) == "True",
            "cta": sn.get("cta_text") or "",
            "cta_type": sn.get("cta_type") or "",
            "title": sn.get("title") or "",
            "body": body or "",
            "link": sn.get("link_url") or "",
            "display_format": sn.get("display_format") or "",
            "video": video,
            "poster": poster,
            "collation": a.get("collation_count") or a.get("total") or 1,
            "lib_url": a.get("ad_library_url") or f"https://www.facebook.com/ads/library/?id={a.get('ad_archive_id')}",
        })
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", help="client or project slug (locates <output>/<slug>/video-swipe-<date>/raw_ads.json)")
    ap.add_argument("--profile", choices=sorted(PROFILES), default="clinic",
                    help="clinic (patient-facing provider) or b2b (software/services sold to a business). Sets the defaults below")
    ap.add_argument("--workdir")
    ap.add_argument("--raw", help="explicit raw_ads.json path")
    ap.add_argument("--out", help="shortlist path (default <workdir>/shortlist.json)")
    ap.add_argument("--countries", default="US,GB,AU", help="priority order, first = home market (market fit 1 / 0.5 / 0)")
    ap.add_argument("--offer", default=None, help="regex the body/title MUST match (the offer). Default from --profile")
    ap.add_argument("--concern", default=None,
                    help="regex of concerns / pain points the client solves. Default from --profile")
    ap.add_argument("--offer-exact", default="", help="regex for the CLIENT'S OWN offer shape "
                                                      "(e.g. 'free consultation|complimentary consult'); +2 fit when the ad's own words match it")
    ap.add_argument("--exclude-device", default="", help="regex of equipment the client does NOT have; an ad selling it is dropped "
                                                         "(e.g. 'emsculpt|coolsculpt|hydrafacial|cryolipolysis|morpheus|co2 laser|picosure')")
    ap.add_argument("--rank-by", choices=["fit", "days"], default="fit",
                    help="fit (default, correct): fit first, run length only breaks ties. days: evidence order only")
    ap.add_argument("--ban", default="", help="extra regex to exclude on body/title/page")
    ap.add_argument("--allow-pom", action="store_true", help="keep ads naming prescription medicines (clinic profile drops them)")
    ap.add_argument("--exclude-pages", help="file of page names to exclude (your brand, your clients), one per line")
    ap.add_argument("--min-days", type=int, default=14)
    ap.add_argument("--min-body", type=int, default=40)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--now", help="YYYY-MM-DD for run-length maths (default today)")
    ap.add_argument("--dry-run", action="store_true", help="print counts and the top rows, write nothing")
    args = ap.parse_args()

    wd = args.workdir or (C.workdir(args.client) if args.client else None)
    raw = args.raw or (os.path.join(wd, "raw_ads.json") if wd else None)
    if not raw or not os.path.exists(raw):
        sys.exit("raw_ads.json not found; pass --raw or run 01_discover.py pull first")
    now = datetime.datetime.strptime(args.now, "%Y-%m-%d") if args.now else datetime.datetime.now()
    ads = C.load_json(raw)
    rows = normalise(ads, now)
    print(f"raw ads {len(ads)}  normalised {len(rows)}")

    prof = PROFILES[args.profile]
    args.offer = args.offer or prof["offer_rx"]
    args.concern = args.concern or prof["concern_rx"]
    bad_cta = prof["bad_cta"]
    excl = [x.lower() for x in EXCLUDE_PAGES_DEFAULT]
    if args.exclude_pages:
        excl += [l.strip().lower() for l in open(args.exclude_pages) if l.strip()]
    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    # market fit, not a longevity bonus: home market 1.0, second 0.5, everything else 0
    market_fit = {cc: b for cc, b in zip(countries, [1.0, 0.5, 0.0, 0.0, 0.0, 0.0])}
    offer_rx = re.compile(args.offer, re.I)
    offer_exact_rx = re.compile(args.offer_exact, re.I) if args.offer_exact else None
    device_rx = re.compile(args.exclude_device, re.I) if args.exclude_device else None
    concern_rx = re.compile(args.concern, re.I)
    ban_rx = re.compile(args.ban, re.I) if args.ban else None
    # weak copy-level signal that a human is in the ad. NOT proof: it must be confirmed by watching.
    person_rx = re.compile(r"\bI'm\b|\bI am\b|\bmy name is\b|\bDr\.? [A-Z]|\bour (doctor|nurse|clinician|founder|ceo|team)\b|"
                           r"\bmeet (our|the) team\b|\bhi,? I\b", re.I)
    prod_rx, aud_rx, pom_rx = re.compile(PRODUCT_RX, re.I), re.compile(prof["audience_drop_rx"], re.I), re.compile(POM_RX, re.I)
    jobs_rx = re.compile(JOBS_RX, re.I)
    drop_pom = prof["drop_pom"] and not args.allow_pom

    drop = Counter()
    kept = []
    for r in rows:
        blob = f"{r['body']} {r['title']}"
        pl = r["page"].lower()
        if not r["video"]:
            drop["no video"] += 1; continue
        if not r["active"]:
            drop["inactive"] += 1; continue
        if any(x in pl for x in excl):
            drop["own/client page (--exclude-pages)"] += 1; continue
        if r["days"] < args.min_days:
            drop[f"< {args.min_days} days"] += 1; continue
        if len(r["body"]) < args.min_body:
            drop["body too short"] += 1; continue
        if r["cta"] in bad_cta:
            drop["bad CTA"] += 1; continue
        if prod_rx.search(blob) or prod_rx.search(r["link"]):
            drop["product/shop"] += 1; continue
        if aud_rx.search(blob) or aud_rx.search(pl):
            drop[prof["audience_drop_label"]] += 1; continue
        if jobs_rx.search(blob):
            drop["recruitment"] += 1; continue
        if ban_rx and (ban_rx.search(blob) or ban_rx.search(pl)):
            drop["--ban"] += 1; continue
        if drop_pom and pom_rx.search(blob):
            drop["names a POM"] += 1; continue
        if device_rx and device_rx.search(blob):
            drop["sells equipment the client does not have"] += 1; continue
        if not offer_rx.search(blob):
            drop["no offer match"] += 1; continue
        concerns = sorted({m.group(0).lower() for m in concern_rx.finditer(blob)})
        if not concerns:
            drop["no concern"] += 1; continue
        r["concerns"] = concerns
        # FIT 0-5 from the ad's own copy. Sort order for the hand review, never the verdict.
        fit = 0.0
        fit += 2.0 if (offer_exact_rx and offer_exact_rx.search(blob)) else 1.0   # same offer shape
        fit += 1.0 if concerns else 0.0                                          # names a concern the client solves
        fit += 0.5 if len(concerns) > 1 else 0.0
        fit += market_fit.get(r["country"], 0.0)                                 # same market as the client
        r["person_signal"] = bool(person_rx.search(blob))                        # unverified, watch it
        fit += 0.5 if r["person_signal"] else 0.0
        r["fit"] = round(min(fit, 5.0), 1)
        # run length is a TIEBREAK inside a fit band, never the ranking (capped so a 900-day ad
        # cannot climb past a better-fitting one)
        r["score"] = r["fit"] * 1000 + min(r["days"], 400) if args.rank_by == "fit" else r["days"]
        kept.append(r)

    # dedupe by page + opening body, keep longest running
    kept.sort(key=lambda x: -x["days"])
    seen, ded = set(), []
    for r in kept:
        k = (r["page"].lower(), re.sub(r"\s+", " ", r["body"])[:120].lower())
        if k in seen:
            drop["duplicate creative"] += 1
            continue
        seen.add(k)
        ded.append(r)
    ded.sort(key=lambda x: -x["score"])
    top = ded[:args.top]

    print("dropped:", dict(drop))
    print(f"candidates {len(ded)}  shortlist {len(top)}  by country {dict(Counter(r['country'] for r in top))}"
          f"  ranked by {'FIT (run length breaks ties only)' if args.rank_by == 'fit' else 'DAYS (evidence order)'}")
    print(f"{'#':>2} {'fit':>3} {'days':>5} cc | {'page':34s} | {'cta':14s} | person? | concerns")
    for i, r in enumerate(top, 1):
        print(f"{i:2d} {r.get('fit', 0):3.1f} {r['days']:5d}d {r['country']:2s} | {r['page'][:34]:34s} | {r['cta'][:14]:14s} | "
              f"{'person?' if r.get('person_signal') else '   -   '} | "
              f"{','.join(r['concerns'][:4])[:34]:34s} | {re.sub(chr(10), ' ', r['body'])[:70]}")
    print("\nBEFORE ANY OF THESE GO ON A PAGE, watch the first 3 seconds and hand-drop:")
    print("  - no person on camera, for a person-led business (text slides, stock b-roll, logo openers)")
    print("  - equipment/product the client does not have, or a category the client does not sell")
    print("  - anything the client could not physically reproduce on a phone next week")
    print("  - anything carrying a compliance flag for the client's market")
    print("  Then take SIX to EIGHT excellent fits. Six to eight excellent beats twelve mediocre.")
    print("  Record fit_score and quality_score per ad in scores.json for the library (step 9).")
    if args.dry_run:
        print("DRY RUN: nothing written")
        return
    out = args.out or os.path.join(wd or os.path.dirname(raw), "shortlist.json")
    C.save_json(out, top)
    print("->", out)


if __name__ == "__main__":
    main()
