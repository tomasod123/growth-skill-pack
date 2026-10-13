#!/usr/bin/env python3
"""Query the ad library. Every new swipe page runs this FIRST.

  python3 query.py --niche skin --market GB --min-fit 3                 # table
  python3 query.py --offer "consult" --offer-tied --personal            # only ads tied to an offer with a person speaking
  python3 query.py --format-class talking_head --market GB --watched    # UK talking heads someone actually watched
  python3 query.py --classified --no-low-res --min-quality 4            # usable, classified, HD only
  python3 query.py --kind client                                        # own-client winners (consent check before use)
  python3 query.py --niche healthcare-software --offer-type demo_booking,free_trial --country US
  python3 query.py --niche skin --json > picks.json                     # rows as JSON for a page build
  python3 query.py --niche skin --paths                                 # media + transcript paths only (for embedding)
  python3 query.py --advertiser-type single_site --country GB --active  # live ads from one-site UK clinics
  python3 query.py --min-survival 180 --min-performance 60 --platform instagram
  python3 query.py --city Manchester --json
  python3 query.py --replicable --no-compliance-flag --offer-type free_consultation --country GB
  python3 query.py --stats                                              # counts by client / market / niche / kind
  python3 query.py --include-weak --min-quality 1                       # the quality<=2 ads, deliberately asked for
  python3 query.py --q "free consultation" --csv > picks.csv            # spreadsheet-friendly export

Filters are case-insensitive substring matches on niche, offer, advertiser, hook and body (--q searches all of them).
Sort: --sort fit (default: fit desc, then days), days, quality, performance, survival.

WEAK ADS ARE HIDDEN BY DEFAULT. A row with quality_score <= 2 is a production standard you would
never brief a client to copy, so it never surfaces in a selection result unless the operator
asks. It is NOT deleted: a bad ad that ran 700 days is evidence about what the market
tolerates, and it still counts in --stats and in every survival number. Pass --include-weak to
see them (or --min-quality <= 2, which is an explicit ask for them and lifts the filter on its
own). Rows with no quality_score at all are unscored, not weak, and are never hidden by this.
"""
import argparse
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adlib_common import LIB_DEFAULT, recompute_days  # noqa: E402

# A quality_score at or below this is a production standard we would never brief a client to copy.
# Hidden from results by default; never removed from the index.
WEAK_MAX = 2


def load(lib):
    p = os.path.join(lib, "index.jsonl")
    if not os.path.exists(p):
        return []
    rows = [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
    for r in rows:
        d = recompute_days(r)                 # days_running is never served stale
        if d is not None:
            r["days_running"] = d
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", default=LIB_DEFAULT)
    ap.add_argument("--niche"); ap.add_argument("--offer"); ap.add_argument("--market"); ap.add_argument("--client"); ap.add_argument("--q")
    ap.add_argument("--kind", choices=["competitor", "client"])
    ap.add_argument("--min-fit", type=float, default=None); ap.add_argument("--min-quality", type=float, default=None); ap.add_argument("--min-days", type=int, default=None)
    ap.add_argument("--include-weak", action="store_true",
                    help="show ads with quality_score <= 2, which are hidden from results by default")
    ap.add_argument("--offer-tied", action="store_true"); ap.add_argument("--personal", action="store_true", help="personal or voiceover, not silent")
    ap.add_argument("--format-class", help="controlled vocabulary: talking_head, silent_broll_text, voiceover_broll, testimonial, text_slides, organic_reel_cta, carousel_static, screen_demo, unclassified (comma-separate for several)")
    ap.add_argument("--classified", action="store_true", help="drop rows whose format_class is unclassified")
    ap.add_argument("--watched", action="store_true", help="only rows whose quality_score came from watching the media")
    ap.add_argument("--no-low-res", action="store_true", help="drop rows whose media is under 600px wide")
    ap.add_argument("--with-media", action="store_true")
    ap.add_argument("--sort", choices=["fit", "days", "quality", "performance", "survival"], default="fit")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--json", action="store_true"); ap.add_argument("--paths", action="store_true"); ap.add_argument("--stats", action="store_true")
    ap.add_argument("--csv", action="store_true", help="CSV of the main fields (open in any spreadsheet)")
    ap.add_argument("--advertiser-type", help="single_site, multi_site, chain, training_provider, product_brand, software_vendor, unknown (comma-separate for several)")
    ap.add_argument("--platform", help="facebook, instagram, audience_network, messenger, threads (comma-separate: matches ANY)")
    ap.add_argument("--active", action="store_true", help="only ads live at the last check")
    ap.add_argument("--ended", action="store_true", help="only ads that have stopped")
    ap.add_argument("--min-survival", type=int, default=None, help="minimum survival_days_at_last_check")
    ap.add_argument("--min-performance", type=int, default=None, help="minimum performance_score (0-100)")
    ap.add_argument("--city")
    ap.add_argument("--tagged", action="store_true", help="only rows with creative attributes merged in")
    ap.add_argument("--replicable", action="store_true", help="only ads a small team could reproduce on a phone (replicable_by_small_team)")
    ap.add_argument("--offer-type", help="none, free_consultation, discount_percent, discount_amount, price_led, free_treatment_or_taster, "
                                         "demo_booking, free_trial, lead_magnet, free_audit_or_assessment, ... (comma-separate)")
    ap.add_argument("--no-compliance-flag", action="store_true", help="drop rows flagged as a compliance risk in their market (compliance_flag)")
    ap.add_argument("--country", help="country_iso, the per-ad country (--market is the batch label)")
    a = ap.parse_args()
    rows = load(a.library)
    if a.stats:
        print(f"  rows {len(rows)}")
        for k in ("client_or_competitor", "client", "country_iso", "country_basis", "niche", "format_class", "format_basis", "personal_vs_slides", "quality_basis", "advertiser_type", "tag_basis", "source_scrape"):
            print(f"  {k}: " + ", ".join(f"{v} {n}" for v, n in Counter(str(r.get(k)) for r in rows).most_common()))
        act = sum(1 for r in rows if r.get("is_active"))
        ps = [r["performance_score"] for r in rows if r.get("performance_score") is not None]
        sv = [r["survival_days_at_last_check"] for r in rows if r.get("survival_days_at_last_check") is not None]
        print(f"  live at last check {act} · ended {sum(1 for r in rows if r.get('is_active') is False)} · "
              f"performance_score scored {len(ps)}"
              + (f" (median {sorted(ps)[len(ps)//2]}, max {max(ps)})" if ps else "")
              + (f" · median survival {sorted(sv)[len(sv)//2]}d" if sv else ""))
        tg = [r for r in rows if r.get("tag_basis")]
        print(f"  creative-tagged {len(tg)} of {len(rows)}"
              + (" · " + " · ".join(
                  f"{k}: " + ", ".join(f"{v} {n}" for v, n in Counter(r.get(k) for r in tg).most_common(6))
                  for k in ("offer_type", "person_on_camera", "landing_type")) if tg else ""))
        if tg:
            print(f"  replicable by a small team {sum(1 for r in tg if r.get('replicable_by_small_team'))}"
                  f" · compliance flagged {sum(1 for r in tg if r.get('compliance_flag'))}")
        print(f"  platforms: " + ", ".join(f"{v} {n}" for v, n in Counter(p for r in rows for p in (r.get("platforms") or [])).most_common()))
        print(f"  cities: " + ", ".join(f"{v} {n}" for v, n in Counter(r.get("city") for r in rows if r.get("city")).most_common(12)))
        weak = [r for r in rows if r.get("quality_score") is not None and r["quality_score"] <= WEAK_MAX]
        print(f"  weak (quality_score <= {WEAK_MAX}, hidden from results unless --include-weak): {len(weak)}"
              + (" · longest of them " + str(max((r.get('survival_days_at_last_check') or 0) for r in weak)) + "d survival" if weak else ""))
        print(f"  with media {sum(1 for r in rows if r.get('media_path') or r.get('media_url'))} (local {sum(1 for r in rows if r.get('media_path'))}, url-only {sum(1 for r in rows if r.get('media_url') and not r.get('media_path'))}) · with poster {sum(1 for r in rows if r.get('poster_path'))} · with transcript {sum(1 for r in rows if r.get('transcript_path'))} · offer_tied {sum(1 for r in rows if r.get('offer_tied'))} · quality scored {sum(1 for r in rows if r.get('quality_score') is not None)} · low res {sum(1 for r in rows if r.get('low_res'))}")
        return
    sub = lambda v, s: (s or "").lower() in str(v or "").lower()  # noqa: E731
    # Weak ads are hidden by default and only by default: they stay in index.jsonl, in --stats and
    # in every survival number. An explicit --min-quality at or below the weak line is itself an
    # ask for them, so it lifts the filter without needing --include-weak as well.
    hide_weak = not (a.include_weak or (a.min_quality is not None and a.min_quality <= WEAK_MAX))
    hidden_weak = 0
    out = []
    for r in rows:
        if hide_weak and r.get("quality_score") is not None and r["quality_score"] <= WEAK_MAX:
            hidden_weak += 1
            continue
        if a.niche and not sub(r.get("niche"), a.niche): continue
        if a.offer and not (sub(r.get("offer"), a.offer) or sub(r.get("body_excerpt"), a.offer) or sub(r.get("hook"), a.offer)): continue
        if a.market and str(r.get("market") or "").upper() != a.market.upper(): continue
        if a.client and not sub(r.get("client"), a.client): continue
        if a.kind and r.get("client_or_competitor") != a.kind: continue
        if a.q and not any(sub(r.get(k), a.q) for k in ("niche", "offer", "advertiser", "hook", "body_excerpt", "notes", "transcript_text")): continue
        if a.min_fit is not None and (r.get("fit_score") or 0) < a.min_fit: continue
        if a.min_quality is not None and (r.get("quality_score") is None or r["quality_score"] < a.min_quality): continue
        if a.min_days is not None and (r.get("days_running") or 0) < a.min_days: continue
        if a.offer_tied and not r.get("offer_tied"): continue
        if a.format_class and (r.get("format_class") or "") not in [x.strip() for x in a.format_class.split(",")]: continue
        if a.classified and r.get("format_class") in (None, "", "unclassified"): continue
        if a.watched and r.get("quality_basis") != "watched": continue
        if a.no_low_res and r.get("low_res"): continue
        if a.personal and r.get("personal_vs_slides") not in ("personal", "voiceover"): continue
        if a.with_media and not (r.get("media_path") or r.get("media_url")): continue
        if a.advertiser_type and (r.get("advertiser_type") or "") not in [x.strip() for x in a.advertiser_type.split(",")]: continue
        if a.platform and not (set(x.strip().lower() for x in a.platform.split(",")) & set(r.get("platforms") or [])): continue
        if a.active and not r.get("is_active"): continue
        if a.ended and r.get("is_active") is not False: continue
        if a.min_survival is not None and (r.get("survival_days_at_last_check") or 0) < a.min_survival: continue
        if a.min_performance is not None and (r.get("performance_score") or 0) < a.min_performance: continue
        if a.city and not sub(r.get("city"), a.city) and not any(sub(x, a.city) for x in (r.get("locations_named") or [])): continue
        if a.tagged and not r.get("tag_basis"): continue
        if a.replicable and not r.get("replicable_by_small_team"): continue
        if a.offer_type and (r.get("offer_type") or "") not in [x.strip() for x in a.offer_type.split(",")]: continue
        if a.no_compliance_flag and r.get("compliance_flag"): continue
        if a.country and str(r.get("country_iso") or r.get("market") or "").upper() != a.country.upper(): continue
        out.append(r)
    key = {"fit": lambda r: (-(r.get("fit_score") or 0), -(r.get("days_running") or 0)),
           "days": lambda r: -(r.get("days_running") or 0),
           "quality": lambda r: (-(r.get("quality_score") or 0), -(r.get("fit_score") or 0)),
           "performance": lambda r: (-(r.get("performance_score") or 0), -(r.get("days_running") or 0)),
           "survival": lambda r: -(r.get("survival_days_at_last_check") or 0)}[a.sort]
    out.sort(key=key); out = out[:a.limit]
    if hidden_weak and (a.json or a.paths or a.csv):
        print(f"# {hidden_weak} weak row(s) hidden (quality_score <= {WEAK_MAX}); --include-weak to show", file=sys.stderr)
    if a.json:
        print(json.dumps(out, indent=1, ensure_ascii=False)); return
    if a.csv:
        import csv
        cols = ["id", "advertiser", "client_or_competitor", "client", "country_iso", "niche", "offer", "offer_type",
                "format_class", "hook", "days_running", "survival_days_at_last_check", "is_active", "fit_score",
                "quality_score", "performance_score", "advertiser_type", "city", "lib_url", "media_path", "notes"]
        w = csv.DictWriter(sys.stdout, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in out:
            w.writerow({k: r.get(k) for k in cols})
        return
    if a.paths:
        for r in out:
            m = r.get("media_path") or r.get("media_url")
            t = r.get("transcript_path")
            print(f"{r['id']}\t{m or '-'}\t{t or '-'}")
        return
    print(f"  {len(out)} rows (of {len(rows)})"
          + (f" · {hidden_weak} weak row(s) hidden (quality_score <= {WEAK_MAX}); --include-weak to show" if hidden_weak else ""))
    print(f"  {'id':28s} {'advertiser':22s} cc  live days fit q perf {'advertiser_type':14s} {'city':14s} format_class       hook")
    for r in out:
        print(f"  {r['id'][:28]:28s} {str(r.get('advertiser'))[:22]:22s} "
              f"{str(r.get('country_iso') or r.get('market') or '-'):3s} "
              f"{('yes' if r.get('is_active') else ('no' if r.get('is_active') is False else '-')):4s}"
              f"{str(r.get('days_running') or '-'):>4s}  {str(r.get('fit_score')):>2s} "
              f"{str(r.get('quality_score') or '-'):>2s} {str(r.get('performance_score') if r.get('performance_score') is not None else '-'):>4s} "
              f"{str(r.get('advertiser_type') or '-')[:14]:14s} {str(r.get('city') or '-')[:14]:14s} "
              f"{str(r.get('format_class') or '-')[:18]:18s} {str(r.get('hook') or '')[:40]}")


if __name__ == "__main__":
    main()
