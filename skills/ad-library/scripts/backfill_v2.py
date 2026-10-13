#!/usr/bin/env python3
"""Backfill SCHEMA v2 onto every row of index.jsonl from the raw scrapes on disk.

  python3 raw_scan.py            # first: build work/v2/raw_index.json
  python3 backfill_v2.py --dry-run
  python3 backfill_v2.py

Deterministic and idempotent: it derives, it never guesses, and re-running it produces the same
file. Prints the completeness table BEFORE and AFTER, every country correction, and the
advertiser_type distribution. A `.bak-<date>` copy of index.jsonl is written first.
"""
import argparse
import datetime
import io
import json
import os
import shutil
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adlib_common import LIB_DEFAULT, V2_FIELDS, enrich_row, ensure_library, index_lock, write_index  # noqa: E402

CORE = ["id", "ad_id", "client_or_competitor", "client", "advertiser", "market", "niche", "offer",
        "format_class", "hook", "days_running", "start", "fit_score", "quality_score",
        "offer_tied", "media_path", "transcript_path", "lib_url", "cta", "body_excerpt"]


def completeness(rows, fields):
    n = len(rows)
    out = []
    for f in fields:
        filled = sum(1 for r in rows if r.get(f) not in (None, "", [], {}))
        out.append((f, filled, n, 100.0 * filled / n if n else 0.0))
    return out


def print_table(title, tbl):
    print(f"\n  {title}")
    print(f"  {'field':34s} {'filled':>7s} {'of':>4s} {'%':>7s}")
    for f, k, n, p in tbl:
        print(f"  {f:34s} {k:7d} {n:4d} {p:6.1f}%")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", default=LIB_DEFAULT)
    ap.add_argument("--raw-index")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    ensure_library(a.library)
    idx_path = os.path.join(a.library, "index.jsonl")
    raw_path = a.raw_index or os.path.join(a.library, "work", "v2", "raw_index.json")
    if not os.path.exists(raw_path):
        raise SystemExit(f"no raw index at {raw_path} — run raw_scan.py first")
    lock = index_lock(a.library)
    lock.__enter__()
    rows = [json.loads(l) for l in io.open(idx_path, encoding="utf-8") if l.strip()]
    idx = json.load(open(raw_path, encoding="utf-8"))
    print(f"  index {len(rows)} rows · raw index {len(idx['ads'])} ads / {len(idx['pages'])} advertisers")

    before = completeness(rows, CORE + V2_FIELDS)
    print_table("BEFORE", before)

    corrections, matched = [], 0
    for r in rows:
        old_market = r.get("market")
        if str(r.get("ad_id")) in idx["ads"]:
            matched += 1
        enrich_row(r, idx)
        if r.get("country_iso") and old_market and r["country_iso"] != str(old_market).upper():
            corrections.append((r["id"], r.get("advertiser"), old_market, r["country_iso"],
                                r["country_basis"], r["country_why"]))

    after = completeness(rows, CORE + V2_FIELDS)
    print_table("AFTER", after)

    print(f"\n  matched to a raw Ads Library record: {matched} of {len(rows)}")
    print(f"\n  country_basis: " + ", ".join(f"{k} {v}" for k, v in
                                             Counter(r.get("country_basis") for r in rows).most_common()))
    print(f"  country corrections vs the per-batch market label: {len(corrections)}")
    for c in corrections:
        print(f"    {c[0][:34]:34s} {str(c[1])[:26]:26s} {c[2]} -> {c[3]}  ({c[4]}: {c[5]})")
    print("\n  advertiser_type: " + ", ".join(f"{k} {v}" for k, v in
                                              Counter(r.get("advertiser_type") for r in rows).most_common()))
    top = sorted([r for r in rows if r.get("performance_score") is not None],
                 key=lambda r: -r["performance_score"])[:10]
    print("\n  performance_score top 10")
    for r in top:
        print(f"    {r['performance_score']:3d}  {str(r.get('advertiser'))[:30]:30s} "
              f"{str(r.get('country_iso') or '-'):3s}  {r['performance_basis']}")
    if a.dry_run:
        lock.__exit__(None, None, None)
        print("\n  [dry-run] nothing written")
        return 0
    shutil.copy2(idx_path, idx_path + ".bak-" + datetime.date.today().strftime("%Y%m%d"))
    write_index(rows, a.library)          # temp file + os.replace, never a truncated index
    lock.__exit__(None, None, None)
    print(f"\n  -> {idx_path}: {len(rows)} rows written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
