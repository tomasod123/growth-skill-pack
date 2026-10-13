#!/usr/bin/env python3
"""The weekly job. Re-check every tracked advertiser in the Meta Ad Library, fold what changed
into index.jsonl, and download any new creative in the SAME session.

  python3 refresh.py --seed-tracked      # (once) write tracked.json from the index + past searches
  python3 refresh.py --dry-run           # print the plan and the cost, spend nothing
  python3 refresh.py                     # the real run (default budget $2.00, hard cap $10)
  python3 refresh.py --budget 5 --no-media

What it does, in order
  1. prints the cost estimate and ABORTS if it is over --budget (default $2.00, hard cap $10.00)
  2. fires the Ads Library scrape: every tracked page_id, plus a rotating slice of the standing
     search terms (the slice moves with the ISO week, so every term is re-checked in turn)
  3. DOWNLOADS the mp4 and the poster for every new ad in the same session, HD url first.
     Facebook CDN urls die in about five days; a scrape without a download is a lost creative.
  4. upserts new ads, and on every existing row updates last_seen, is_active, days_running,
     variant_count, platforms, advertiser_ads_live, appends to status_history, and marks ads that
     have DISAPPEARED from a page we did scrape as ended (end_date = the last day we saw them)
  5. recomputes performance_score for every row
  6. runs audit.py against the index it just wrote (and runs --post-cmd, if given, only when the
     audit passes: use it for any sync of your own, e.g. a database or sheet upload)
  7. writes refresh-log/<date>.md: new ads, ads that died, biggest movers

Idempotent: re-running on the same day reuses that day's scrape files instead of paying again
(--force re-fires them), and every write is an upsert keyed on the row id.

Credentials: APIFY_TOKEN from the environment (set -a; source ~/.claude/skills/.env; set +a).
Optional: SLACK_BOT_TOKEN + SLACK_CHANNEL_ID for a one-line summary with --slack.
No token is ever written to a file or a log.
"""
import argparse
import datetime
import io
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adlib_common import (LIB_DEFAULT, enrich_row, ensure_library, index_lock,  # noqa: E402
                          note_append, performance, recompute_days, today, write_atomic,
                          write_index)
from raw_scan import ids_of  # noqa: E402
from niche_rules import scope_check, classify_niche, NICHES  # noqa: E402
from ingest import fit as fit_score_for, OFFER as OFFER_RE  # noqa: E402


def _vocab_niche(label):
    """A tracked.json per-page label is free text typed by a human and predates the controlled
    vocabulary ("emsculpt, body contouring", "skin concerns", "ai scribe vendor"). Writing it
    straight into `niche` puts off-vocabulary values into the index and the audit hard-fails
    every one. Map it through the classifier; if it names nothing, use nothing."""
    if not label:
        return None
    if label in NICHES:
        return label
    return classify_niche(str(label))[0]
import audit  # noqa: E402
import raw_scan  # noqa: E402

ACTOR = "curious_coder~facebook-ads-library-scraper"
PRICE_PER_AD = 0.00075          # $ per ad returned (actor pay-per-result; check the actor page for today's price)
PRICE_PER_START = 0.00005
HARD_CAP = 10.00
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:                                     # stdlib fallback
    CTX = ssl.create_default_context()


# ---------------------------------------------------------------- creds
def apify_token():
    tok = os.environ.get("APIFY_TOKEN") or os.environ.get("APIFY_API_TOKEN")
    if not tok:
        raise SystemExit("APIFY_TOKEN not set. Add it to ~/.claude/skills/.env, then run: "
                         "set -a; source ~/.claude/skills/.env; set +a")
    return tok


# ---------------------------------------------------------------- tracked list
def seed_tracked(lib, force=False):
    """Seed tracked.json from every distinct page_id in the index plus the search terms already
    used in the scrapes we hold."""
    ensure_library(lib)
    rows = [json.loads(l) for l in io.open(os.path.join(lib, "index.jsonl"), encoding="utf-8") if l.strip()]
    idx_path = os.path.join(lib, "work", "v2", "raw_index.json")
    idx = json.load(open(idx_path, encoding="utf-8")) if os.path.exists(idx_path) else {"ads": {}}
    pages, terms = {}, {}
    for r in rows:
        pid = r.get("page_id")
        if not pid:
            continue
        p = pages.setdefault(pid, {"page_id": pid, "page_name": r.get("page_name") or r.get("advertiser"),
                                   "country": r.get("country_iso") or r.get("market") or "GB",
                                   "client": r.get("client"), "niche": r.get("niche"),
                                   "offer": r.get("offer"), "rows": 0})
        p["rows"] += 1
    for a in idx["ads"].values():
        for o in a.get("observations", []):
            q = o.get("search") or ""
            for piece in q.split("|"):
                piece = piece.strip()
                if "::" in piece:
                    cc, term = piece.split("::", 1)
                    if len(cc) == 2 and term.strip():
                        terms[f"{cc.upper()}::{term.strip()}"] = {"country": cc.upper(), "term": term.strip()}
    out = {
        "_readme": "The weekly refresh list. pages = every advertiser we hold an ad for; searches "
                   "= the standing keyword sweeps, rotated a slice at a time so the cost stays flat. "
                   "Edit freely; refresh.py reads this file and nothing else.",
        "actor": ACTOR,
        "price_per_ad_usd": PRICE_PER_AD,
        "budget_usd": 2.00,
        "hard_cap_usd": HARD_CAP,
        "ads_per_page_run": 25,
        "ads_per_search_run": 60,
        "searches_per_week": 8,
        "pages": sorted(pages.values(), key=lambda p: (p["client"] or "", p["page_name"] or "")),
        "searches": sorted(terms.values(), key=lambda t: (t["country"], t["term"])),
    }
    path = os.path.join(lib, "tracked.json")
    if os.path.exists(path) and not force:
        raise SystemExit(f"{path} already exists and holds hand edits (budget knobs, "
                         f"per-page niche/offer, pages you deliberately removed). "
                         f"Re-seed with --force only if you mean to discard them.")
    write_atomic(path, json.dumps(out, indent=1, ensure_ascii=False))
    print(f"  -> {path}: {len(out['pages'])} pages · {len(out['searches'])} search terms")
    return out


def load_tracked(lib):
    p = os.path.join(lib, "tracked.json")
    if not os.path.exists(p):
        raise SystemExit(f"no {p} — copy templates/tracked.example.json there and edit it, "
                         f"or run: python3 refresh.py --seed-tracked (builds it from the index)")
    return json.load(open(p, encoding="utf-8"))


# ---------------------------------------------------------------- plan + cost
def build_plan(t, week):
    """(runs, estimated_dollars). A run = {key, url, count}."""
    runs = []
    n_page = int(t.get("ads_per_page_run") or 25)
    for p in t["pages"]:
        url = ("https://www.facebook.com/ads/library/?active_status=all&ad_type=all"
               f"&country={p.get('country') or 'GB'}&view_all_page_id={p['page_id']}"
               "&search_type=page&media_type=all")
        runs.append({"key": f"page::{p['page_id']}", "url": url, "count": n_page,
                     "page_id": p["page_id"], "country": p.get("country"), "client": p.get("client"),
                     "niche": p.get("niche"), "offer": p.get("offer"), "page_name": p.get("page_name")})
    searches = t.get("searches") or []
    k = int(t.get("searches_per_week") or 8)
    n_search = int(t.get("ads_per_search_run") or 60)
    if searches and k:
        start = (week * k) % len(searches)
        slice_ = [searches[(start + i) % len(searches)] for i in range(min(k, len(searches)))]
        for s in slice_:
            url = ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
                   f"&country={s['country']}&q={urllib.parse.quote(s['term'])}"
                   "&search_type=keyword_exact_phrase&media_type=all")
            runs.append({"key": f"{s['country']}::{s['term']}", "url": url, "count": n_search,
                         "country": s["country"], "search": True})
    est = sum(r["count"] for r in runs) * PRICE_PER_AD + len(runs) * PRICE_PER_START
    return runs, est


# ---------------------------------------------------------------- apify
def fire(token, run):
    inp = {"urls": [{"url": run["url"]}], "count": run["count"]}
    if run.get("country"):
        inp["scrapePageAds.countryCode"] = run["country"]
    req = urllib.request.Request(f"https://api.apify.com/v2/acts/{ACTOR}/runs?token={token}",
                                 data=json.dumps(inp).encode(),
                                 headers={"Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, context=CTX))["data"]
    return d["id"], d["defaultDatasetId"]


def _get(url, tries=4):
    """One GET with a socket timeout and a few retries. A transient blip here would otherwise
    crash the whole cycle AFTER every run has already been fired and billed."""
    last = None
    for i in range(tries):
        try:
            return json.load(urllib.request.urlopen(url, context=CTX, timeout=60))
        except Exception as e:                               # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise last


def abort(token, run_id):
    try:
        req = urllib.request.Request(
            f"https://api.apify.com/v2/actor-runs/{run_id}/abort?token={token}", data=b"")
        urllib.request.urlopen(req, context=CTX, timeout=30).read()
        print(f"    aborted run {run_id} (it outran our wait)")
    except Exception as e:                                   # noqa: BLE001
        print(f"    abort failed for {run_id}: {str(e)[:80]}")


def wait(token, run_id, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = _get(f"https://api.apify.com/v2/actor-runs/{run_id}?token={token}")["data"]["status"]
        if st in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            return st
        time.sleep(6)
    abort(token, run_id)        # stop it billing server-side rather than just walking away
    return "TIMEOUT"


def pull(token, ds):
    items, off = [], 0
    while True:
        ch = _get(f"https://api.apify.com/v2/datasets/{ds}/items?token={token}&clean=true"
                  f"&limit=1000&offset={off}")
        if not ch:
            break
        items += ch
        off += len(ch)
    return items


# ---------------------------------------------------------------- media
def best_video(snap):
    """HD first, then SD, per the standing rule. Cards, then the top-level videos list."""
    for c in (snap.get("cards") or []) + (snap.get("videos") or []) + (snap.get("extra_videos") or []):
        if not isinstance(c, dict):
            continue
        for k in ("video_hd_url", "video_sd_url"):
            if c.get(k):
                return c[k], c.get("video_preview_image_url")
    return None, None


def fetch(url, dest):
    if not url or (os.path.exists(dest) and os.path.getsize(dest) > 1000):
        return os.path.exists(dest) and os.path.getsize(dest) > 1000
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}),
                                    context=CTX, timeout=180) as f, open(dest, "wb") as o:
            o.write(f.read())
    except Exception as e:                                   # noqa: BLE001
        print(f"    media ERR {os.path.basename(dest)}: {str(e)[:90]}")
        return False
    return os.path.getsize(dest) > 1000


def download_media(rec, lib, client):
    snap = rec.get("snapshot") or {}
    vid, poster = best_video(snap)
    aid = str(rec.get("ad_archive_id"))
    d = os.path.join(lib, "media", client or "unknown")
    mp4, jpg = os.path.join(d, aid + ".mp4"), os.path.join(d, aid + ".jpg")
    ok = fetch(vid, mp4)
    if poster:
        fetch(poster, jpg)
    if ok and not (os.path.exists(jpg) and os.path.getsize(jpg) > 1000):
        subprocess.run(["ffmpeg", "-y", "-v", "quiet", "-ss", "0.8", "-i", mp4,
                        "-frames:v", "1", "-q:v", "3", jpg], check=False)
    return (mp4 if ok else None), (jpg if os.path.exists(jpg) and os.path.getsize(jpg) > 1000 else None)


# ---------------------------------------------------------------- row building
def scope_and_niche(rec, run):
    """(ok, refuse_why, niche, niche_basis, warn) for an ad the refresh found on a tracked page.
    The weekly job upserts straight from the scrape without going through ingest.py, so the
    off-scope gate has to live here too or an injury lawyer walks in with the weekly run."""
    snap = rec.get("snapshot") or {}
    body = snap.get("body")
    body = body.get("text") if isinstance(body, dict) else (body or "")
    text = " ".join(str(x or "") for x in [rec.get("page_name"), snap.get("page_name"),
                                           snap.get("title"), body, snap.get("caption"),
                                           snap.get("link_url"), snap.get("cta_text"),
                                           rec.get("page_categories")])
    cats = rec.get("page_categories") or snap.get("page_categories") or []
    ok, why, niche, warn = scope_check({"page_categories": cats}, text)
    fallback = _vocab_niche(run.get("niche"))
    return ok, why, (niche or fallback or None), ("ad_content" if niche else "source_batch"), warn


def _blob(snap, body):
    """The ad's OWN words only - never the per-batch --niche/--offer labels (feeding those in
    once marked every row in a batch offer_tied)."""
    return " ".join(str(x or "") for x in (snap.get("title"), body, snap.get("caption"),
                                           snap.get("cta_text")))


def new_row(rec, run, lib, date, media, poster, niche=None, niche_basis=None):
    snap = rec.get("snapshot") or {}
    body = snap.get("body")
    body = body.get("text") if isinstance(body, dict) else (body or "")
    aid = str(rec.get("ad_archive_id"))
    src = f"ad-library refresh {date}"
    return {
        "id": f"refresh-{date}:{aid}", "row_key": f"refresh-{date}:{aid}", "ad_id": aid,
        "client_or_competitor": "competitor", "client": run.get("client") or "cross-client",
        "advertiser": rec.get("page_name") or snap.get("page_name"),
        "market": run.get("country"), "niche": niche or _vocab_niche(run.get("niche")) or None,
        "niche_basis": niche_basis, "offer": run.get("offer") or "",
        "format_class": "unclassified", "format_note": None, "format_basis": "none",
        "format": "unclassified", "personal_vs_slides": "unknown",
        "hook": (snap.get("title") or body.split("\n")[0])[:140],
        "days_running": None, "start": None,
        "fit_score": fit_score_for(run.get("country"), "unclassified",
                                   bool(OFFER_RE.search(_blob(snap, body))),
                                   _blob(snap, body) + " " + str(rec.get("page_name") or ""),
                                   niche or _vocab_niche(run.get("niche"))),
        "quality_score": None, "quality_basis": None,
        "offer_tied": bool(OFFER_RE.search(_blob(snap, body))),
        "width": None, "height": None, "low_res": None, "duration_s": None,
        "has_audio": None, "audio_speech": None,
        "transcript_path": None, "media_path": media, "poster_path": poster,
        "lib_url": rec.get("ad_library_url") or rec.get("url"),
        "cta": snap.get("cta_text"), "body_excerpt": (body or "")[:200],
        "source_scrape": src, "date": date,
        "ingested_at": datetime.datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "notes": ("added by the weekly refresh; format_class unclassified because nobody has "
                  "watched it yet, and fit/quality are unscored for the same reason"),
    }


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", default=LIB_DEFAULT)
    ap.add_argument("--budget", type=float, default=2.00, help="abort if the estimate exceeds this (hard cap $10)")
    ap.add_argument("--seed-tracked", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-fire runs even if today's scrape files exist")
    ap.add_argument("--post-cmd", default=os.environ.get("AD_LIBRARY_POST_CMD", ""),
                    help="optional shell command to run after a PASSING audit (your own sync/export step)")
    ap.add_argument("--ignore-audit", action="store_true",
                    help="run --post-cmd even when audit.py fails (do not use; it is how the index rots)")
    ap.add_argument("--audit-http", type=int, default=40,
                    help="how many media/poster urls the audit fetches (0 to skip the network check)")
    ap.add_argument("--no-media", action="store_true")
    ap.add_argument("--slack", action="store_true", help="post a one-line summary (needs SLACK_BOT_TOKEN and SLACK_CHANNEL_ID)")
    a = ap.parse_args()
    lib = a.library
    date = today().isoformat()
    if a.seed_tracked:
        seed_tracked(lib, force=a.force)
        return 0
    if a.budget > HARD_CAP:
        raise SystemExit(f"--budget {a.budget} is over the hard cap ${HARD_CAP:.2f}")

    t = load_tracked(lib)
    week = today().isocalendar()[1]
    runs, est = build_plan(t, week)
    n_ads = sum(r["count"] for r in runs)
    print(f"  plan: {len(runs)} runs ({sum(1 for r in runs if not r.get('search'))} pages + "
          f"{sum(1 for r in runs if r.get('search'))} searches) x up to {n_ads} ads")
    print(f"  cost estimate: {n_ads} ads x ${PRICE_PER_AD} + {len(runs)} starts = "
          f"${est:.2f}  (budget ${a.budget:.2f}, hard cap ${HARD_CAP:.2f})")
    if est > a.budget:
        print(f"  ABORT: ${est:.2f} exceeds the budget of ${a.budget:.2f}. Lower ads_per_page_run / "
              f"searches_per_week in tracked.json, or pass --budget.")
        return 2
    if a.dry_run:
        for r in runs[:6]:
            print(f"    {r['key'][:40]:40s} {r['count']:4d} ads")
        print(f"    ... {len(runs)} runs total")
        print("  [dry-run] nothing fired, nothing downloaded, nothing written")
        return 0

    scrape_dir = os.path.join(lib, "scrapes", date)
    os.makedirs(scrape_dir, exist_ok=True)
    token = apify_token()
    fired, files, complete = {}, [], {}
    for r in runs:
        safe = re.sub(r"[^A-Za-z0-9]+", "-", r["key"]).strip("-")[:60]
        out = os.path.join(scrape_dir, safe + ".json")
        if os.path.exists(out) and not a.force:
            files.append((out, r))
            try:
                complete[r["key"]] = len(json.load(open(out, encoding="utf-8"))) < r["count"]
            except (OSError, ValueError):
                complete[r["key"]] = False
            continue
        try:
            rid, ds = fire(token, r)
            fired[rid] = (ds, out, r)
        except Exception as e:                               # noqa: BLE001
            print(f"    fire FAILED {r['key']}: {str(e)[:120]}")
    print(f"  fired {len(fired)} runs · reused {len(files)} of today's existing scrape files")
    for rid, (ds, out, r) in fired.items():
        try:
            st = wait(token, rid)
        except Exception as e:                               # noqa: BLE001
            print(f"    {r['key'][:44]:44s} WAIT ERROR {str(e)[:70]}")
            continue
        if st != "SUCCEEDED":
            # do NOT write a file for a failed run: an empty file would be reused as "today's
            # scrape" on a re-run, and an empty page result would read as "every ad died"
            print(f"    {r['key'][:44]:44s} {st:10s}    - ads (not written)")
            continue
        try:
            items = pull(token, ds)
        except Exception as e:                               # noqa: BLE001
            print(f"    {r['key'][:44]:44s} PULL ERROR {str(e)[:70]} (file not written)")
            continue
        if not items:
            print(f"    {r['key'][:44]:44s} SUCCEEDED     0 ads (not written)")
            continue
        for it in items:
            it["_q"] = r["key"] if r.get("search") else None
        json.dump(items, open(out, "w", encoding="utf-8"), ensure_ascii=False)
        files.append((out, r))
        complete[r["key"]] = len(items) < r["count"]      # not truncated = we saw the whole page
        print(f"    {r['key'][:44]:44s} {st:10s} {len(items):4d} ads"
              f"{'' if complete[r['key']] else '  (TRUNCATED at the cap: deaths not judged)'}")

    # fold the new scrape files into the observation index
    extra = [(p, date, f"ad-library refresh {date}") for p, _ in files]
    idx = raw_scan.scan(raw_scan.standing_sources(extra))
    raw_out = os.path.join(lib, "work", "v2", "raw_index.json")
    write_atomic(raw_out, json.dumps(idx, ensure_ascii=False), keep_bak=False)

    ensure_library(lib)
    idx_path = os.path.join(lib, "index.jsonl")
    lock = index_lock(lib)
    lock.__enter__()                       # held until the index is safely rewritten
    rows = [json.loads(l) for l in io.open(idx_path, encoding="utf-8") if l.strip()]
    before = {r["id"]: dict(r) for r in rows}
    by_ad = {str(r["ad_id"]): r for r in rows}

    # 1. new ads on tracked pages
    seen_by_page, new_rows, judged_pages = {}, [], set()
    refused_new, warned_new = [], []
    for path, run in files:
        try:
            recs = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for rec in recs:
            aid, pid = ids_of(rec)
            if pid:
                seen_by_page.setdefault(pid, set()).add(aid)
                if run.get("page_id") == pid and complete.get(run["key"]):
                    judged_pages.add(pid)
            if not aid or aid in by_ad:
                continue
            if not run.get("page_id"):
                continue                     # keyword hits are discovery, not auto-added
            ok, why, niche, nbasis, warn = scope_and_niche(rec, run)
            if not ok:
                refused_new.append((aid, rec.get("page_name") or "", why))
                continue                     # REFUSED: never enters the index, and is named below
            if warn:
                warned_new.append((aid, rec.get("page_name") or "", warn))
            media = poster = None
            if not a.no_media:
                media, poster = download_media(rec, lib, run.get("client"))
            row = new_row(rec, run, lib, date, media, poster, niche, nbasis)
            by_ad[aid] = row
            new_rows.append(row)
    rows += new_rows

    # 2. re-enrich everything against the fresh observations
    for r in rows:
        enrich_row(r, idx)

    # 3. ads that have DISAPPEARED from a page we actually scraped this run
    died = []
    for r in rows:
        pid = r.get("page_id")
        # A page run capped at ads_per_page_run may have been truncated; an ad missing from a
        # truncated result is not dead, it just fell off the end. Only judge complete runs.
        if not pid or pid not in judged_pages:
            continue
        if str(r["ad_id"]) in seen_by_page[pid]:
            continue
        if r.get("is_active") is False:
            continue
        # Mutate directly: enrich_row rebuilds is_active/status_history/end_date FROM the
        # observations, and this ad has none for today (that is precisely why it is dead), so
        # re-running it here would resurrect it.
        r["is_active"] = False
        r["end_date"] = r.get("last_seen") or date
        r["status_history"] = (r.get("status_history") or []) + [{"date": date, "is_active": False}]
        r["days_running"] = recompute_days(r)
        r["performance_score"], r["performance_basis"] = performance(
            r.get("survival_days_at_last_check"), False, r.get("variant_count"),
            r.get("platforms"), r.get("relaunch_count"), r.get("advertiser_ads_live"))
        note_append(r, f"stopped: absent from the {date} refresh of its page, last seen {r.get('last_seen')}")
        died.append(r)

    write_index(rows, lib)                 # temp file + os.replace + one .bak, never truncatable
    lock.__exit__(None, None, None)
    print(f"  index: {len(rows)} rows · {len(new_rows)} new · {len(died)} ended")
    if refused_new:
        print(f"  REFUSED {len(refused_new)} off-scope ad(s), not added to the library:")
        for aid, name, why in refused_new[:20]:
            print(f"    {aid}  {str(name)[:40]}")
            print(f"      {why}")
    for aid, name, why in warned_new[:20]:
        print(f"  CHECK: {aid}  {str(name)[:40]} — {why}")

    # 3b. AUDIT. Every check in audit.py, run against the index we just wrote. A failure here
    # blocks --post-cmd: a broken index must not be pushed anywhere else.
    audit_rows = audit.load(lib)
    audit_res = audit.run(audit_rows, http_sample=a.audit_http)
    audit_fail = sum(x["count"] for x in audit_res if x["severity"] == "fail")
    audit_warn = sum(x["count"] for x in audit_res if x["severity"] == "warn")
    print(f"  audit: {len(audit_res)} checks · {audit_fail} failure(s) · {audit_warn} warning(s)")
    for x in audit_res:
        if x["count"] and x["severity"] == "fail":
            print(f"    FAIL {x['check']} ({x['count']})")
            for line in x["failures"][:6]:
                print(f"         {line}")
    if audit_fail and not a.ignore_audit:
        print("  POST-CMD SKIPPED: the index did not pass audit.py. Fix the rows above, then run "
              "your sync by hand, or re-run with --ignore-audit if you have judged every failure.")

    # 4. movers
    movers = []
    for r in rows:
        b = before.get(r["id"])
        if not b or r.get("performance_score") is None:
            continue
        d = (r["performance_score"] or 0) - (b.get("performance_score") or 0)
        if d:
            movers.append((d, r))
    movers.sort(key=lambda x: -abs(x[0]))

    # 5. log
    logdir = os.path.join(lib, "refresh-log")
    os.makedirs(logdir, exist_ok=True)
    L = [f"# Ad library refresh {date}", "",
         f"- runs fired: {len(fired)} · scrape files used: {len(files)} · estimated cost "
         f"${est:.2f} (budget ${a.budget:.2f})",
         f"- audit: {audit_fail} failure(s), {audit_warn} warning(s)"
         + (f" · REFUSED {len(refused_new)} off-scope ad(s)" if refused_new else ""),
         f"- index: {len(rows)} rows · {len(new_rows)} new · {len(died)} ended · "
         f"{sum(1 for r in rows if r.get('is_active'))} still live", ""]
    L.append("## New ads")
    L += ([f"- `{r['id']}` {r.get('advertiser')} ({r.get('country_iso')}) — "
           f"{'mp4 downloaded' if r.get('media_path') else 'NO MEDIA'} — {(r.get('hook') or '')[:80]}"
           for r in new_rows] or ["- none"])
    L += ["", "## Ads that died"]
    L += ([f"- `{r['id']}` {r.get('advertiser')} — ran {r.get('survival_days_at_last_check')} days, "
           f"last seen {r.get('last_seen')}" for r in died] or ["- none"])
    L += ["", "## Biggest movers (performance_score)"]
    L += ([f"- {d:+d} → {r['performance_score']} · {r.get('advertiser')} · {r.get('performance_basis')}"
           for d, r in movers[:10]] or ["- none"])
    if new_rows:
        L += ["", "## What to do with the new rows",
              f"They land `format_class: unclassified` with `fit_score` and `quality_score` null, "
              f"because nobody has watched them. They will NOT appear in a `--min-fit` or "
              f"fit-sorted query until someone does. To score them:",
              "```",
              "python3 ~/.claude/skills/ad-library/scripts/query.py --q '' --sort performance --with-media --limit 20",
              "# watch the first three seconds of each, then write creative_tags.jsonl or scores and:",
              "python3 ~/.claude/skills/ad-library/scripts/merge_tags.py",
              "```"]
    L += ["", "_performance_score is a survival-and-spread proxy, never spend or impressions: "
          "Meta publishes neither for commercial ads._", ""]
    logp = os.path.join(logdir, f"{date}.md")
    write_atomic(logp, "\n".join(L), keep_bak=False)
    print(f"  -> {logp}")

    # 5b. prune old scrape dirs. Dozens of files a week add up on a laptop disk; keep the last
    # 12 weeks, which is more than status_history needs to stay meaningful.
    try:
        dirs = sorted(d for d in os.listdir(os.path.join(lib, "scrapes"))
                      if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d))
        for old_dir in dirs[:-12]:
            shutil.rmtree(os.path.join(lib, "scrapes", old_dir), ignore_errors=True)
            print(f"  pruned scrapes/{old_dir}")
    except OSError:
        pass

    # 6. optional post-command (your own sync / export), only on a passing audit
    if a.post_cmd and (not audit_fail or a.ignore_audit):
        print(f"  $ {a.post_cmd}")
        subprocess.run(a.post_cmd, shell=True, check=False)

    # 7. one line to Slack, at most
    chan = (os.environ.get("SLACK_CHANNEL_ID") or "").strip()
    if a.slack and chan:
        try:
            slack(chan, f"Ad library {date}: {len(rows)} ads tracked, {len(new_rows)} new, "
                        f"{len(died)} stopped, ${est:.2f} spent.")
        except Exception as e:                               # noqa: BLE001
            print(f"  slack skipped: {str(e)[:100]}")
    return 0


def slack(channel, text):
    tok = os.environ.get("SLACK_BOT_TOKEN")
    if not tok:
        return
    body = json.dumps({"channel": channel, "text": text}).encode()
    req = urllib.request.Request("https://slack.com/api/chat.postMessage", data=body,
                                 headers={"Content-Type": "application/json; charset=utf-8",
                                          "Authorization": "Bearer " + tok})
    urllib.request.urlopen(req, context=CTX, timeout=20).read()


if __name__ == "__main__":
    sys.exit(main())
