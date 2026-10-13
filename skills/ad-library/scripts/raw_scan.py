#!/usr/bin/env python3
"""Scan every Meta Ads Library scrape held on disk and build the observation index the
SCHEMA v2 backfill and the weekly refresh both read.

  python3 raw_scan.py                      # rescan the standing sources, write work/v2/raw_index.json
  python3 raw_scan.py --add <file.json> --date 2026-09-10 --label "refresh 2026-09-10"

Output (work/v2/raw_index.json):
  sources   [{file, date, label, n}]
  ads       ad_archive_id -> {page_id, page_name, page_categories, page_like_count, start_date,
                              end_date, is_active, collation_count, ads_count, platforms,
                              currency, gated_type, categories, cdm, display_format,
                              ad_library_url, cta, title, body, body_hash, search_cc, all_text_len,
                              observations:[{date,is_active,file,search}]}
  pages     page_id -> {page_name, page_categories, ad_ids, advertiser_type, why,
                        locations_named, ads_live_seen}
  creatives "<page_id>|<body_hash>" -> [[ad_id, start_date], ...] sorted oldest first

Every scrape file is treated as ONE observation of every ad in it, dated by the file's own
timestamp (or --date). That is what makes last_seen, status_history and relaunch detection real
rather than assumed.
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adlib_common import (LIB_DEFAULT, all_text, as_date, body_hash, body_text,  # noqa: E402
                          classify_advertiser, iso, write_atomic)

# The standing scrapes. Each entry: glob, label. The weekly refresh writes scrapes/<date>/<run>.json;
# every past week has to stay in the scan or status_history and last_seen would forget it. Add your
# own research folders (e.g. video-ad-swipe-page work dirs) with AD_LIBRARY_EXTRA_SCRAPES, a list of
# globs separated by ":" (e.g. "./video-ad-swipe-page-output/*/*/raw_ads.json").
SOURCE_GLOBS = [
    (LIB_DEFAULT + "/scrapes/*/*.json", "ad-library refresh"),
    (LIB_DEFAULT + "/scrapes/*.json", "ad-library scrape"),
] + [(g.strip(), "extra research scrape")
     for g in (os.environ.get("AD_LIBRARY_EXTRA_SCRAPES") or "").split(":") if g.strip()]
RE_FILE_CC = re.compile(r"raw_([A-Z]{2})_")


RE_DATE_DIR = re.compile(r"/scrapes/(\d{4}-\d{2}-\d{2})/")


def file_date(path):
    """A refresh scrape is dated by its <date> directory, not the mtime, so a file touched later
    does not silently move the observation."""
    m = RE_DATE_DIR.search(path)
    if m:
        return m.group(1)
    return datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()


def ids_of(rec):
    """(ad_archive_id, page_id) exactly as the scan records them. refresh.py imports this so its
    "which ads did we just see" set can never drift from what the index was built with — a thinner
    copy there produced empty-string ids and false death marks."""
    snap = rec.get("snapshot") or {}
    aid = str(rec.get("ad_archive_id") or rec.get("ad_id") or "")
    pid = str(rec.get("page_id") or snap.get("page_id") or "") or None
    return aid, pid


def search_cc_of(rec, path):
    """The country of the SEARCH that returned this ad. _q is 'GB::skin clinic'; otherwise the
    filename carries it (raw_GB_*.json). Absent on some older scrapes, which is why those rows
    fall through to the ad's own copy."""
    q = rec.get("_q")
    if q and isinstance(q, str) and "::" in q:
        cc = q.split("::", 1)[0].strip().upper()
        if len(cc) == 2:
            return cc, q
        return None, q
    m = RE_FILE_CC.search(os.path.basename(path))
    if m:
        return m.group(1).upper(), None
    return None, q if isinstance(q, str) else None


def scan(paths_dates):
    ads, pages, creatives, sources = {}, {}, {}, []
    for path, date, label in paths_dates:
        try:
            d = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"  SKIP {path}: {e}")
            continue
        if not isinstance(d, list):
            d = d.get("ads") or list(d.values())
        n = 0
        for rec in d:
            if not isinstance(rec, dict):
                continue
            aid, pid_of_rec = ids_of(rec)
            if not aid:
                continue
            n += 1
            snap = rec.get("snapshot") or {}
            cc, q = search_cc_of(rec, path)
            obs = {"date": date, "is_active": bool(rec.get("is_active")), "file": os.path.basename(path),
                   "search": q, "search_cc": cc}
            cur = ads.get(aid)
            if cur is None:
                cur = ads[aid] = {
                    "ad_archive_id": aid,
                    "page_id": pid_of_rec,
                    "page_name": rec.get("page_name") or snap.get("page_name"),
                    "page_categories": snap.get("page_categories") or [],
                    "page_like_count": snap.get("page_like_count"),
                    "start_date": iso(as_date(rec.get("start_date_formatted") or rec.get("start_date"))),
                    "end_date_raw": iso(as_date(rec.get("end_date_formatted") or rec.get("end_date"))),
                    "is_active": bool(rec.get("is_active")),
                    "collation_count": rec.get("collation_count"),
                    "ads_count": rec.get("ads_count"),
                    "platforms": [str(p).lower() for p in (rec.get("publisher_platform") or [])],
                    "currency": (rec.get("currency") or None),
                    "gated_type": rec.get("gated_type"),
                    "categories": rec.get("categories") or [],
                    "contains_digital_created_media": rec.get("contains_digital_created_media"),
                    "display_format": snap.get("display_format"),
                    "ad_library_url": rec.get("ad_library_url") or rec.get("url"),
                    "cta": snap.get("cta_text"),
                    "title": snap.get("title"),
                    "body": body_text(snap)[:1500],
                    "body_hash": body_hash(snap),
                    "search_cc": cc,
                    "observations": [],
                }
                cur["text"] = all_text(snap)[:3000]
                cur["country_iso_code"] = snap.get("country_iso_code")
            else:
                cur["is_active"] = bool(rec.get("is_active"))
                cur["search_cc"] = cur["search_cc"] or cc
                if not cur["collation_count"]:
                    cur["collation_count"] = rec.get("collation_count")
                cur["ads_count"] = max(cur.get("ads_count") or 0, rec.get("ads_count") or 0) or None
                for p in (rec.get("publisher_platform") or []):
                    if str(p).lower() not in cur["platforms"]:
                        cur["platforms"].append(str(p).lower())
            if not any(o["date"] == date and o["file"] == obs["file"] for o in cur["observations"]):
                cur["observations"].append(obs)
            pid = cur["page_id"]
            if pid:
                pg = pages.setdefault(pid, {"page_id": pid, "page_name": cur["page_name"],
                                            "page_categories": cur["page_categories"],
                                            "ad_ids": [], "texts": [], "ads_live_seen_by_date": {}})
                if aid not in pg["ad_ids"]:
                    pg["ad_ids"].append(aid)
                    pg["texts"].append(cur["text"])
                if rec.get("is_active"):
                    key = date
                    s = pg["ads_live_seen_by_date"].setdefault(key, [])
                    if aid not in s:
                        s.append(aid)
                bh = cur["body_hash"]
                if bh:
                    creatives.setdefault(f"{pid}|{bh}", [])
                    if not any(x[0] == aid for x in creatives[f"{pid}|{bh}"]):
                        creatives[f"{pid}|{bh}"].append([aid, cur["start_date"]])
        sources.append({"file": path, "date": date, "label": label, "n": n})
        print(f"  {os.path.basename(path):42s} {date}  {n:5d} ads")

    for a in ads.values():
        a["observations"].sort(key=lambda o: o["date"])
    for k in creatives:
        creatives[k].sort(key=lambda x: (x[1] or "9999-99-99"))
    for pid, pg in pages.items():
        t, why, locs = classify_advertiser(pg["page_name"], pg["page_categories"], pg["texts"])
        pg["advertiser_type"] = t
        pg["advertiser_type_basis"] = why
        pg["locations_named"] = locs
        pg["ads_live_seen"] = max([len(v) for v in pg["ads_live_seen_by_date"].values()] or [0])
        pg["text_blob"] = "\n".join(t for t in pg["texts"] if t)[:6000]
        pg.pop("texts", None)
    return {"built_at": datetime.datetime.now().astimezone().replace(microsecond=0).isoformat(),
            "sources": sources, "ads": ads, "pages": pages, "creatives": creatives}


def standing_sources(extra=()):
    """Every scrape file on disk, each exactly once. The globs overlap with whatever the caller
    passes in `extra` (the refresh hands us the files it just wrote, which its own scrapes/<date>/
    glob also finds), so dedupe on the real path or the same file is scanned twice."""
    out, seen = [], set()
    for p, d, label in [(p, file_date(p), label) for pat, label in SOURCE_GLOBS
                        for p in sorted(glob.glob(pat))] + list(extra):
        real = os.path.realpath(p)
        if real in seen:
            continue
        seen.add(real)
        out.append((p, d, label))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", default=LIB_DEFAULT)
    ap.add_argument("--add", action="append", default=[], help="extra scrape JSON to fold in")
    ap.add_argument("--date", help="observation date for --add files (default: file mtime)")
    ap.add_argument("--label", default="ad-hoc")
    ap.add_argument("--out")
    a = ap.parse_args()
    extra = [(p, a.date or file_date(p), a.label) for p in a.add]
    print("scanning scrapes:")
    idx = scan(standing_sources(extra))
    out = a.out or os.path.join(a.library, "work", "v2", "raw_index.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_atomic(out, json.dumps(idx, ensure_ascii=False), keep_bak=False)
    print(f"  -> {out}: {len(idx['ads'])} distinct ads · {len(idx['pages'])} advertisers · "
          f"{len(idx['creatives'])} creatives · {len(idx['sources'])} source files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
