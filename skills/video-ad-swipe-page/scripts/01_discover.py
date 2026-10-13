#!/usr/bin/env python3
"""Step 1: competitor discovery on the Facebook Ads Library via Apify.

Three phases, one script:
  fire   -> prints runs x count x price BEFORE anything is charged, then starts the runs
  poll   -> status of every run
  pull   -> paginate every dataset until an EMPTY chunk, keep the RAW payload (video/image
            URLs in it expire in days; the raw file is the only way back), dedupe by ad_archive_id

Examples
  # cost preview only (no charge)
  python3 01_discover.py --client acme --terms "skin consultation,acne scarring" --countries AU,GB,US --dry-run
  # fire, then poll until done, then pull
  python3 01_discover.py --client acme --terms-file terms.txt --countries AU,GB,US --count 120 fire
  python3 01_discover.py --client acme poll
  python3 01_discover.py --client acme pull
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402


def parse_terms(args):
    terms = []
    if args.terms:
        terms += [t.strip() for t in args.terms.split(",") if t.strip()]
    if args.terms_file:
        terms += [l.strip() for l in open(args.terms_file) if l.strip() and not l.startswith("#")]
    seen, out = set(), []
    for t in terms:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def plan_runs(terms, countries):
    return [(cc, t) for cc in countries for t in terms]


def cmd_fire(args, wd):
    terms = parse_terms(args)
    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    if not terms or not countries:
        sys.exit("Need --terms/--terms-file and --countries")
    runs = plan_runs(terms, countries)
    price, src = C.actor_price(token=None if not args.dry_run else C.apify_token(required=False))
    est = len(runs) * args.count * price
    print(f"ACTOR   {C.ACTOR}  (id {C.ACTOR_ID})")
    print(f"PRICE   ${price:.5f} per ad ({src})")
    print(f"RUNS    {len(runs)} = {len(countries)} countries x {len(terms)} terms")
    print(f"COUNT   {args.count} ads max per run   media={args.media}   active_only={not args.include_inactive}")
    print(f"WORST-CASE COST  {len(runs)} x {args.count} x ${price:.5f} = ${est:.2f}   "
          f"(budget ${args.budget:.2f}, hard cap ${C.HARD_CAP:.2f})")
    for cc, t in runs:
        print(f"   {cc}  {t!r}")
    if est > C.HARD_CAP:
        sys.exit(f"ABORT: ${est:.2f} exceeds the ${C.HARD_CAP:.2f} hard cap. Cut terms/countries/count.")
    if est > args.budget:
        sys.exit(f"ABORT: ${est:.2f} exceeds --budget ${args.budget:.2f}. Raise --budget (max {C.HARD_CAP}) "
                 f"only with the budget owner's yes, or trim the plan.")
    if args.dry_run:
        print("DRY RUN: nothing fired.")
        return
    token = C.apify_token()
    out = C.load_json(os.path.join(wd, "runs.json"), {}) or {}
    for cc, t in runs:
        key = f"{cc}::{t}"
        if key in out and out[key].get("run"):
            print("skip (already fired)", key)
            continue
        inp = {
            "urls": [{"url": C.ads_library_url(t, cc, active_only=not args.include_inactive, media=args.media)}],
            "count": args.count,
            "scrapePageAds.activeStatus": "all" if args.include_inactive else "active",
            "scrapePageAds.countryCode": cc,
        }
        try:
            d = C.api(f"acts/{C.ACTOR}/runs", token=token, data=inp)["data"]
        except Exception as e:  # noqa: BLE001
            print("ERR firing", key, e)
            continue
        out[key] = {"run": d["id"], "ds": d["defaultDatasetId"], "country": cc, "term": t}
        print("fired", key, d["id"], flush=True)
        C.save_json(os.path.join(wd, "runs.json"), out)
    print(f"TOTAL RUNS {len(out)}  -> {os.path.join(wd, 'runs.json')}")


def cmd_poll(args, wd):
    runs = C.load_json(os.path.join(wd, "runs.json"), {}) or {}
    if not runs:
        sys.exit("no runs.json yet; run fire first")
    token = C.apify_token()
    while True:
        done = tot = 0
        usd = 0.0
        for k, v in runs.items():
            d = C.api(f"actor-runs/{v['run']}", token=token)["data"]
            v["status"] = d["status"]
            n = (d.get("stats") or {}).get("outputItemCount")
            v["n"] = n
            v["usd"] = (d.get("usageTotalUsd") or 0)
            usd += v["usd"]
            tot += n or 0
            if d["status"] in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                done += 1
            print(f"{k:40s} {d['status']:10s} items={n} usd={v['usd']:.4f}")
        C.save_json(os.path.join(wd, "runs.json"), runs)
        print(f"DONE {done}/{len(runs)}  ITEMS {tot}  ACTUAL USD so far ${usd:.2f}")
        if done == len(runs) or not args.wait:
            break
        time.sleep(args.wait)


def cmd_pull(args, wd):
    runs = C.load_json(os.path.join(wd, "runs.json"), {}) or {}
    if not runs:
        sys.exit("no runs.json yet; run fire first")
    token = C.apify_token()
    allads, seen = [], set()
    for k, v in runs.items():
        items, off = [], 0
        while True:
            # Gotcha: with clean=true a page can return fewer than `limit` mid-dataset.
            # Only an EMPTY chunk means the end.
            try:
                ch = C.api(f"datasets/{v['ds']}/items?clean=true&limit=1000&offset={off}", token=token)
            except Exception as e:  # noqa: BLE001
                print("ERR", k, e)
                break
            if not ch:
                break
            items += ch
            off += len(ch)
            if off > args.max_per_run:
                break
        print(f"{k:40s} {len(items)}")
        for it in items:
            aid = it.get("ad_archive_id")
            if aid and aid not in seen:
                seen.add(aid)
                it["_q"] = k
                allads.append(it)
    raw = os.path.join(wd, "raw_ads.json")
    C.save_json(raw, allads, indent=0)
    print(f"UNIQUE ADS {len(allads)} -> {raw}   (KEEP THIS FILE: media URLs inside expire)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("phase", nargs="?", default="fire", choices=["fire", "poll", "pull"])
    ap.add_argument("--client", required=True, help="client or project slug, e.g. clinic-a or my-saas")
    ap.add_argument("--workdir", help="override work dir (default ./video-ad-swipe-page-output/<slug>/video-swipe-<date>)")
    ap.add_argument("--terms", help="comma-separated exact-phrase search terms")
    ap.add_argument("--terms-file", help="one term per line")
    ap.add_argument("--countries", default="AU,GB,US", help="ISO codes in priority order (first = home market)")
    ap.add_argument("--count", type=int, default=120, help="max ads per run (120 is a good default)")
    ap.add_argument("--media", default="video", choices=["video", "all", "image"],
                    help="Ads Library media filter. video = cheaper, we only keep video anyway")
    ap.add_argument("--include-inactive", action="store_true", help="also pull paused ads (default: active only)")
    ap.add_argument("--budget", type=float, default=C.BUDGET_DEFAULT, help="USD soft budget (default 10)")
    ap.add_argument("--max-per-run", type=int, default=3000)
    ap.add_argument("--wait", type=int, default=0, help="poll: seconds between polls until all runs finish")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and the cost, fire nothing")
    args = ap.parse_args()
    wd = args.workdir or C.workdir(args.client)
    {"fire": cmd_fire, "poll": cmd_poll, "pull": cmd_pull}[args.phase](args, wd)


if __name__ == "__main__":
    main()
