#!/usr/bin/env python3
"""Search Console reader (read-only).

Google's official Search Console API, called through Google's official Python libraries
(google-api-python-client, google-auth-oauthlib: github.com/googleapis). No third-party code.
READ-ONLY: the token only carries webmasters.readonly, so Google itself refuses any change.

Sign in once with the Google account that has access to your properties (`gsc.py login`).
Key and token live in $GSC_CONFIG_DIR (default ~/.config/gsc-reader, owner-only).
Reports from `audit` go to $GSC_REPORTS_DIR (default ./gsc-reports). Optional: GSC_LOGIN_HINT=<your Google email>
pre-selects the Google account at login. Revoke: https://myaccount.google.com/permissions

Usage (every command prints JSON; --out FILE saves the full JSON and prints only a short summary):
  gsc.py login                                   sign in (opens Google in the browser)
  gsc.py properties                              every property the account can see, with permission level
  gsc.py performance SITE [--days 28]            clicks/impressions vs the previous period, top queries and pages
  gsc.py sitemaps SITE                           submitted sitemaps, errors, warnings
  gsc.py inspect SITE URL                        Google's index verdict for one URL
  gsc.py audit SITE [--max-urls 200]             sitemap URLs: live HTTP status + Google's index verdict, plus performance
  gsc.py export SITE --start D --end D --dims query,page [--device [MOBILE|DESKTOP|TABLET]] [--row-limit 25000]
  gsc.py opportunities SITE [--days 28] [--min-impr 15] [--top 50]
  gsc.py url-history SITE --urls-file FILE [--days 480]
  gsc.py redirect-check SITE --redirects FILE [--days 480] [--base https://www.example.com] [--ignore-words a,b]
SITE is exactly as listed by `properties`, e.g. sc-domain:example.com or https://www.example.com/
"""
import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict

os.umask(0o077)  # anything this script writes is owner-only
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass

try:  # Google's official libraries. Imported softly so --help works before they are installed.
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    MISSING_LIBS = None
except ImportError as _exc:
    MISSING_LIBS = _exc

    class RefreshError(Exception):
        pass

    class HttpError(Exception):
        pass

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
LOGIN_HINT = os.environ.get("GSC_LOGIN_HINT") or None  # optional: pre-selects the Google account at login
CFG = os.path.expanduser(os.environ.get("GSC_CONFIG_DIR") or "~/.config/gsc-reader")
CLIENT = os.path.join(CFG, "client_secrets.json")
TOKEN = os.path.join(CFG, "token.json")
REPORTS = os.path.expanduser(os.environ.get("GSC_REPORTS_DIR") or "./gsc-reports")  # keep site data out of the skill folder
LOGIN_CMD = f"python3 {sys.argv[0] if sys.argv and sys.argv[0].endswith('gsc.py') else 'scripts/gsc.py'} login"
UA = "search-console-reader"
EXPIRED_MSG = ("Search Console sign-in has expired or been revoked (invalid_grant). If the OAuth app is in Google "
               "'Testing' mode, a sign-in lasts 7 days. Fix: run `" + LOGIN_CMD + "` and click Allow.")


def _save(c):
    os.makedirs(CFG, mode=0o700, exist_ok=True)
    with open(TOKEN, "w") as f:
        f.write(c.to_json())
    os.chmod(TOKEN, 0o600)


def credentials(interactive=False):
    c = Credentials.from_authorized_user_file(TOKEN, SCOPES) if os.path.exists(TOKEN) else None
    if c and c.valid and not interactive:
        return c
    if c and c.expired and c.refresh_token and not interactive:
        try:
            c.refresh(Request())
        except RefreshError:
            sys.exit(EXPIRED_MSG)
        _save(c)
        return c
    if not interactive:
        sys.exit("Not signed in. Run: " + LOGIN_CMD)
    if not os.path.exists(CLIENT):
        sys.exit(f"Missing OAuth key at {CLIENT}")
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT, SCOPES)
    hint = {"login_hint": LOGIN_HINT} if LOGIN_HINT else {}
    c = flow.run_local_server(port=0, prompt="consent", **hint,
                              authorization_prompt_message="",
                              success_message="Signed in. You can close this tab and go back to Claude.")
    granted = set(c.scopes or [])
    if granted - set(SCOPES):
        sys.exit(f"Refusing token with extra scopes: {sorted(granted)}")
    _save(c)
    return c


def service(interactive=False):
    if MISSING_LIBS:
        sys.exit(f"Google libraries missing ({MISSING_LIBS}). Run: pip install -r requirements.txt")
    return build("searchconsole", "v1", credentials=credentials(interactive), cache_discovery=False)


def _dates(days, offset=0):
    end = dt.date.today() - dt.timedelta(days=3 + offset)  # Search Console data lags ~2-3 days
    start = end - dt.timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def _window(days):
    """Window for the dataState=all commands: ends 2 days ago (fresh, partly unfinalised data)."""
    end = dt.date.today() - dt.timedelta(days=2)
    return (end - dt.timedelta(days=days - 1)).isoformat(), end.isoformat()


# ---------------------------------------------------------------- original commands

def properties(svc):
    rows = svc.sites().list().execute().get("siteEntry", [])
    return sorted(({"site": r["siteUrl"], "permission": r["permissionLevel"]} for r in rows), key=lambda r: r["site"])


def performance(svc, site, days=28, top=10):
    def q(start, end, dims=None, limit=top):
        body = {"startDate": start, "endDate": end, "rowLimit": limit}
        if dims:
            body["dimensions"] = dims
        return svc.searchanalytics().query(siteUrl=site, body=body).execute().get("rows", [])

    cur, prev = _dates(days), _dates(days, offset=days)
    def tot(rows):
        r = rows[0] if rows else {}
        return {k: round(r.get(k, 0), 4) for k in ("clicks", "impressions", "ctr", "position")}
    return {
        "period": cur, "previous_period": prev,
        "current": tot(q(*cur)), "previous": tot(q(*prev)),
        "top_queries": [{"query": r["keys"][0], "clicks": r["clicks"], "impressions": r["impressions"], "position": round(r["position"], 1)} for r in q(*cur, ["query"])],
        "top_pages": [{"page": r["keys"][0], "clicks": r["clicks"], "impressions": r["impressions"], "position": round(r["position"], 1)} for r in q(*cur, ["page"])],
    }


def sitemaps(svc, site):
    out = []
    for s in svc.sitemaps().list(siteUrl=site).execute().get("sitemap", []):
        out.append({"path": s.get("path"), "lastDownloaded": s.get("lastDownloaded"), "isPending": s.get("isPending"),
                    "errors": int(s.get("errors", 0)), "warnings": int(s.get("warnings", 0)),
                    "submitted": sum(int(c.get("submitted", 0)) for c in s.get("contents", []))})
    return out


def inspect(svc, site, url):
    r = svc.urlInspection().index().inspect(body={"inspectionUrl": url, "siteUrl": site}).execute()
    ix = r.get("inspectionResult", {}).get("indexStatusResult", {})
    return {"url": url, "verdict": ix.get("verdict"), "coverage": ix.get("coverageState"),
            "fetch": ix.get("pageFetchState"), "robots": ix.get("robotsTxtState"), "indexing": ix.get("indexingState"),
            "lastCrawl": ix.get("lastCrawlTime"), "googleCanonical": ix.get("googleCanonical"), "userCanonical": ix.get("userCanonical")}


def _http_status(url):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    op = urllib.request.build_opener(NoRedirect)
    try:
        return op.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20).status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return type(e).__name__


def _sitemap_urls(sitemap_url, depth=0):
    try:
        xml = urllib.request.urlopen(urllib.request.Request(sitemap_url, headers={"User-Agent": UA}), timeout=30).read()
        root = ET.fromstring(xml)
    except Exception:
        return []
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    if root.tag.endswith("sitemapindex") and depth < 2:
        return [u for loc in root.findall("s:sitemap/s:loc", ns) for u in _sitemap_urls(loc.text.strip(), depth + 1)]
    return [loc.text.strip() for loc in root.findall("s:url/s:loc", ns)]


def audit(svc, site, max_urls=200, days=28):
    maps = sitemaps(svc, site)
    urls = []
    for m in maps:
        urls += _sitemap_urls(m["path"])
    urls = list(dict.fromkeys(urls))[:max_urls]
    pages, issues = [], []
    for u in urls:
        status = _http_status(u)
        try:
            row = inspect(svc, site, u)
        except HttpError as e:
            row = {"url": u, "verdict": f"inspect error {e.resp.status}"}
        row["http"] = status
        pages.append(row)
        if status != 200:
            issues.append(f"{u} returns {status} but is in the sitemap")
        if row.get("verdict") not in ("PASS",):
            issues.append(f"{u}: Google says {row.get('verdict')} / {row.get('coverage')}")
        if row.get("googleCanonical") and row.get("userCanonical") and row["googleCanonical"] != row["userCanonical"]:
            issues.append(f"{u}: Google picked a different canonical ({row['googleCanonical']})")
    for m in maps:
        if m["errors"] or m["warnings"]:
            issues.append(f"sitemap {m['path']}: {m['errors']} errors, {m['warnings']} warnings")
    perf = performance(svc, site, days)
    report = {"site": site, "run": dt.datetime.now().isoformat(timespec="seconds"), "sitemaps": maps,
              "urls_checked": len(pages), "issues": issues, "pages": pages, "performance": perf}
    os.makedirs(REPORTS, exist_ok=True)
    path = os.path.join(REPORTS, f"{site.replace('sc-domain:', '').replace('https://', '').replace('http://', '').strip('/').replace('/', '_')}-{dt.date.today()}.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=1)
    report["saved"] = path
    return report


# ---------------------------------------------------------------- shared helpers for the new commands

def query_all(svc, site, start, end, dims, filters=None, page_size=25000):
    """Raw searchanalytics rows, paginated with startRow until an empty page. dataState=all, web search."""
    rows, start_row = [], 0
    while True:
        body = {"startDate": start, "endDate": end, "dimensions": dims, "rowLimit": page_size,
                "startRow": start_row, "dataState": "all", "type": "web"}
        if filters:
            body["dimensionFilterGroups"] = [{"groupType": "and", "filters": filters}]
        chunk = svc.searchanalytics().query(siteUrl=site, body=body).execute().get("rows", [])
        if not chunk:
            return rows
        for r in chunk:
            d = dict(zip(dims, r.get("keys", [])))
            d.update(clicks=r["clicks"], impressions=r["impressions"], ctr=round(r["ctr"], 4), position=round(r["position"], 2))
            rows.append(d)
        start_row += len(chunk)


def site_host(site):
    if site.startswith("sc-domain:"):
        return site[len("sc-domain:"):].lower()
    return urllib.parse.urlsplit(site).netloc.lower().removeprefix("www.")


def norm_url(u):
    """Collapse http/https, www/non-www, trailing slash and #fragment: 'host/path?query'."""
    p = urllib.parse.urlsplit(u.strip())
    host = p.netloc.lower().removeprefix("www.")
    return host + (p.path.rstrip("/") or "/") + (("?" + p.query) if p.query else "")


def norm_path(p):
    p = urllib.parse.urlsplit(p).path if p.startswith("http") else p.split("#")[0].split("?")[0]
    return p.rstrip("/") or "/"


def _agg(rows, key):
    acc = {}
    for r in rows:
        a = acc.setdefault(key(r), {"clicks": 0, "impressions": 0, "_pw": 0.0})
        a["clicks"] += r["clicks"]
        a["impressions"] += r["impressions"]
        a["_pw"] += r["position"] * r["impressions"]
    for a in acc.values():
        pw = a.pop("_pw")
        a["position"] = round(pw / a["impressions"], 1) if a["impressions"] else None
        a["ctr"] = round(a["clicks"] / a["impressions"], 4) if a["impressions"] else 0
    return acc


def _path_regex(path):
    """_redirects-style source path -> RE2 fragment. '/x/*' also matches '/x'; ':name' matches one segment."""
    if path.endswith("/*"):
        return _path_regex(path[:-2] or "/").removesuffix("/?") + "(?:/.*)?"
    out = ""
    for part in re.split(r"(\*|:[A-Za-z_]\w*)", path.rstrip("/")):
        if part == "*":
            out += ".*"
        elif part.startswith(":") and len(part) > 1:
            out += "[^/]+"
        else:
            out += re.escape(part)
    return out + "/?"


def _full_regex(host, fragments):
    return r"^https?://(?:www\.)?" + re.escape(host) + "(?:" + "|".join(fragments) + r")(?:[?#].*)?$"


def _resolve(site, u):
    u = u.strip()
    if u.startswith("http"):
        p = urllib.parse.urlsplit(u)
        return p.netloc.lower().removeprefix("www."), (p.path or "/")
    return site_host(site), (u if u.startswith("/") else "/" + u)


def _filtered_rows(svc, site, start, end, dims, host, paths):
    """Rows for a set of paths on one host, via includingRegex page filters. Splits the regex if Google rejects it."""
    frags = [_path_regex(p) for p in paths]
    chunks, cur = [], []
    for f in frags:
        if cur and len("|".join(cur + [f])) > 1500:
            chunks.append(cur)
            cur = []
        cur.append(f)
    if cur:
        chunks.append(cur)
    rows = []
    while chunks:
        ch = chunks.pop(0)
        flt = [{"dimension": "page", "operator": "includingRegex", "expression": _full_regex(host, ch)}]
        try:
            rows += query_all(svc, site, start, end, dims, flt)
        except HttpError as e:
            if e.resp.status == 400 and len(ch) > 1:
                chunks[:0] = [ch[:len(ch) // 2], ch[len(ch) // 2:]]
            else:
                raise
    return rows


# ---------------------------------------------------------------- export

def export(svc, site, start, end, dims, device=None, row_limit=25000):
    dims = [d.strip() for d in dims.split(",") if d.strip()]
    filters = None
    if device == "__dim__":
        dims = dims + ["device"] if "device" not in dims else dims
    elif device:
        filters = [{"dimension": "device", "operator": "equals", "expression": device.upper()}]
    rows = query_all(svc, site, start, end, dims, filters, page_size=min(max(1, row_limit), 25000))
    tot_c, tot_i = sum(r["clicks"] for r in rows), sum(r["impressions"] for r in rows)
    return {"site": site, "start": start, "end": end, "dimensions": dims, "device_filter": filters and device.upper(),
            "dataState": "all", "summary": {"rows": len(rows), "clicks": tot_c, "impressions": tot_i}, "rows": rows}


# ---------------------------------------------------------------- opportunities

EXPECTED_CTR = {1: .28, 2: .15, 3: .10, 4: .07, 5: .05, 6: .04, 7: .03, 8: .025, 9: .02, 10: .018}


def opportunities(svc, site, days=28, min_impr=15, top=50):
    start, end = _window(days)
    q_rows = query_all(svc, site, start, end, ["query"])
    qp_rows = query_all(svc, site, start, end, ["query", "page"])
    p_rows = query_all(svc, site, start, end, ["page"])
    s90, e90 = _window(90)
    qp90 = qp_rows if days == 90 else query_all(svc, site, s90, e90, ["query", "page"])
    p90 = p_rows if days == 90 else query_all(svc, site, s90, e90, ["page"])

    best_page = {}
    for r in qp_rows:
        if r["query"] not in best_page or r["impressions"] > best_page[r["query"]]["impressions"]:
            best_page[r["query"]] = r
    striking = [{"query": r["query"], "impressions": r["impressions"], "clicks": r["clicks"], "position": round(r["position"], 1),
                 "page": best_page.get(r["query"], {}).get("page")}
                for r in q_rows if 4 <= r["position"] <= 20 and r["impressions"] >= min_impr]
    striking.sort(key=lambda r: -r["impressions"])

    gaps = []
    for r in qp_rows:
        if r["position"] > 10 or r["impressions"] < min_impr:
            continue
        exp = EXPECTED_CTR[max(1, min(10, int(r["position"] + 0.5)))]
        if r["ctr"] < exp:
            gaps.append({"query": r["query"], "page": r["page"], "impressions": r["impressions"], "clicks": r["clicks"],
                         "position": round(r["position"], 1), "ctr": r["ctr"], "expected_ctr": exp,
                         "expected_extra_clicks": round(r["impressions"] * (exp - r["ctr"]), 1)})
    gaps.sort(key=lambda r: -r["expected_extra_clicks"])

    by_query = defaultdict(list)
    for r in qp90:
        by_query[r["query"]].append(r)
    cannibal = []
    for q, rs in by_query.items():
        groups = _agg(rs, lambda r: norm_url(r["page"]))
        pages = []
        for k, a in groups.items():
            if a["impressions"] < 10:
                continue
            variants = sorted((r for r in rs if norm_url(r["page"]) == k), key=lambda r: -r["impressions"])
            pages.append({"page": variants[0]["page"], "impressions": a["impressions"], "clicks": a["clicks"], "position": a["position"],
                          **({"host_variants": [v["page"] for v in variants]} if len(variants) > 1 else {})})
        if len(pages) >= 2:
            pages.sort(key=lambda p: -p["impressions"])
            cannibal.append({"query": q, "impressions": sum(p["impressions"] for p in pages), "pages": pages})
    cannibal.sort(key=lambda c: -c["impressions"])

    host_dups = []
    shared = defaultdict(lambda: defaultdict(set))
    for r in qp90:
        shared[norm_url(r["page"])][r["page"]].add(r["query"])
    by_key = defaultdict(list)
    for r in p90:
        by_key[norm_url(r["page"])].append(r)
    for k, rs in by_key.items():
        rs = [r for r in rs if r["impressions"] >= 10]
        if len(rs) < 2:
            continue
        qsets = [shared[k][r["page"]] for r in rs]
        host_dups.append({"page": k, "impressions": sum(r["impressions"] for r in rs),
                          "shared_queries": len(set.intersection(*qsets)) if all(qsets) else 0,
                          "variants": sorted(({"page": r["page"], "impressions": r["impressions"], "clicks": r["clicks"],
                                               "position": round(r["position"], 1)} for r in rs), key=lambda v: -v["impressions"])})
    host_dups.sort(key=lambda h: -h["impressions"])

    zero = sorted(({"page": r["page"], "impressions": r["impressions"], "position": round(r["position"], 1)}
                   for r in p_rows if r["impressions"] >= 50 and r["clicks"] == 0), key=lambda r: -r["impressions"])

    lists = {"striking_distance": striking, "ctr_gaps": gaps, "cannibalisation": cannibal,
             "host_duplicates": host_dups, "zero_click_pages": zero}
    return {"site": site, "window": [start, end], "cannibalisation_window": [s90, e90], "min_impr": min_impr,
            "expected_ctr_curve": EXPECTED_CTR,
            "summary": {k: len(v) for k, v in lists.items()} | {
                "ctr_gap_expected_extra_clicks": round(sum(g["expected_extra_clicks"] for g in gaps), 1)},
            **{k: v[:top] for k, v in lists.items()}}


# ---------------------------------------------------------------- url-history

def url_history(svc, site, urls, days=480, top=15):
    start, end = _window(days)
    items = []
    for u in urls:
        u = u.strip()
        if not u or u.startswith("#"):
            continue
        host, path = _resolve(site, u)
        items.append({"url": u, "host": host, "path": path,
                      "rx": re.compile(_full_regex(host, [_path_regex(path)]))})
    page_rows, qp_rows = [], []
    by_host = defaultdict(list)
    for it in items:
        by_host[it["host"]].append(it["path"])
    for host, paths in by_host.items():
        paths = list(dict.fromkeys(paths))
        page_rows += _filtered_rows(svc, site, start, end, ["page"], host, paths)
        qp_rows += _filtered_rows(svc, site, start, end, ["query", "page"], host, paths)
    out = []
    for it in items:
        prs = [r for r in page_rows if it["rx"].match(r["page"])]
        qrs = [r for r in qp_rows if it["rx"].match(r["page"])]
        tot = _agg(prs, lambda r: "all").get("all", {"clicks": 0, "impressions": 0, "position": None})
        queries = _agg(qrs, lambda r: r["query"])
        tq = sorted(({"query": q, **a} for q, a in queries.items()), key=lambda r: (-r["impressions"], -r["clicks"]))[:top]
        out.append({"url": it["url"], "path": it["path"], "clicks": tot["clicks"], "impressions": tot["impressions"],
                    "position": tot["position"],
                    "variants": [r["page"] for r in sorted(prs, key=lambda r: -r["impressions"])][:10],
                    "top_queries": [{k: r[k] for k in ("query", "clicks", "impressions", "position")} for r in tq]})
    return {"site": site, "window": [start, end],
            "summary": {"urls": len(out), "with_history": sum(1 for o in out if o["impressions"])}, "urls": out}


# ---------------------------------------------------------------- redirect-check

STOPWORDS = set("""a an and are as at be best by can cheap cost costs do does for from get good how i in is it me my
near nearby of on or price prices pricing the to top vs what whats where which who why will with you your much long
last before after site http https www com co uk org net html htm php index page pages blog category tag clinic clinics
salon salons spa practice treatment treatments service services non review reviews book booking appointment online
offer offers deal deals local private""".split())
# Town and area words never decide a topic (the old and new pages both carry the town). Pass yours with
# --ignore-words (e.g. --ignore-words springfield,riverside) or set GSC_IGNORE_WORDS=springfield,riverside.
TOWN_WORDS = {w.strip().lower() for w in os.environ.get("GSC_IGNORE_WORDS", "").split(",") if w.strip()}
# Niche synonyms: a query word on the left counts as a hit on a slug containing the word on the right.
SYNONYMS = {"botox": "wrinkle", "tox": "wrinkle", "bocouture": "wrinkle", "azzalure": "wrinkle", "dysport": "wrinkle",
            "profhilo": "booster", "polynucleotide": "booster", "vampire": "prp"}


def _stem(t):
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def _tokens(text, brand, ignore):
    out = []
    for t in re.split(r"[^a-z0-9]+", text.lower()):
        if len(t) < 2 or t.isdigit() or t in STOPWORDS or t in ignore or (len(t) >= 4 and t in brand):
            continue
        s = _stem(t)
        if s not in out and s not in STOPWORDS and s not in ignore:
            out.append(s)
    return out


def _hit(t, slug, joined):
    for x in (t, SYNONYMS.get(t)):
        if x and (x in slug or (len(x) >= 5 and x in joined)
                  or (len(x) >= 6 and any(len(s) >= 6 and s[:6] == x[:6] for s in slug))):
            return True
    return False


def _score(weighted, path, brand, ignore):
    """Weighted token overlap (Jaccard per query) between a source's queries and a target path's slug words. 0..1."""
    slug = _tokens(" ".join(path.strip("/").split("/")), brand, ignore)
    joined = "".join(slug)
    num = den = 0.0
    hits = []
    for q, qt, w in weighted:
        den += w
        if not slug:
            continue
        shared = sum(1 for t in qt if _hit(t, slug, joined))
        if shared:
            num += w * min(1.0, shared / (len(qt) + len(slug) - shared))
            hits.append(q)
    return (round(num / den, 3) if den else None), hits


def parse_redirects(path):
    rules, skipped = [], []
    text = open(path, encoding="utf-8").read()
    if path.lower().endswith(".csv"):
        for n, row in enumerate(csv.reader(text.splitlines()), 1):
            if len(row) >= 2 and row[0].strip().startswith(("/", "http")):
                rules.append({"line": n, "from": row[0].strip(), "to": row[1].strip(), "status": "301"})
    else:
        for n, raw in enumerate(text.splitlines(), 1):
            toks = raw.split()
            if not toks or toks[0].startswith("#"):
                continue
            cut = next((i for i, t in enumerate(toks) if t.startswith("#")), len(toks))
            toks = toks[:cut]
            src, rest = toks[0], [t for t in toks[1:] if "=" not in t]  # drop query-param matchers
            if not rest:
                continue
            status = rest[1] if len(rest) > 1 and re.fullmatch(r"\d{3}!?", rest[1]) else "301"
            rules.append({"line": n, "from": src, "to": rest[0], "status": status})
    out = []
    for r in rules:
        code = int(r["status"].rstrip("!"))
        if code not in (301, 302, 303, 307, 308):
            skipped.append({**r, "reason": f"status {code} is not a redirect"})
        else:
            out.append(r)
    return out, skipped


def redirect_check(svc, site, redirects_file, days=480, base=None, extra_ignore=(), min_impr=20):
    rules, skipped = parse_redirects(redirects_file)
    host = site_host(site)
    kept = []
    for r in rules:
        if r["from"].startswith("http"):
            u = urllib.parse.urlsplit(r["from"])
            if u.netloc.lower().removeprefix("www.") != host or u.path in ("", "/", "/*"):
                skipped.append({**r, "reason": "host rule (whole-domain redirect)"})
                continue
            r = {**r, "from": u.path}
        kept.append(r)
    rules = kept
    brand = re.sub(r"\.(com|co|uk|au|ie|net|org|ca|io)\b", "", host).replace(".", "").replace("-", "")
    ignore = TOWN_WORDS | {w.strip().lower() for w in extra_ignore if w.strip()}

    sources = {}  # normalised source path -> rule info (deduped: /x and /x/ are one source)
    for r in rules:
        key = r["from"] if "*" in r["from"] else norm_path(r["from"])
        tgt = r["to"]
        tkey = norm_path(tgt) if (not tgt.startswith("http") or site_host(tgt) == host) else tgt.rstrip("/")
        s = sources.setdefault(key, {"source": key, "target": tgt, "target_key": tkey, "status": r["status"], "lines": []})
        s["lines"].append(r["line"])
    hist = url_history(svc, site, list(sources), days)
    for s, h in zip(sources.values(), hist["urls"]):
        s["history"] = h

    base = (base or "").rstrip("/")
    sm_urls = []
    for b in ([base] if base else [f"https://www.{host}", f"https://{host}"]):
        sm_urls = _sitemap_urls(b + "/sitemap.xml")
        if sm_urls:
            base = base or b
            break
    if not sm_urls:
        for m in sitemaps(svc, site):
            sm_urls += _sitemap_urls(m["path"])
    live = list(dict.fromkeys(norm_path(u) for u in sm_urls))

    # many-to-one only costs rankings when the merged pages carried search demand, so count sources with history
    fan_in, fan_in_quiet = defaultdict(list), defaultdict(int)
    for s in sources.values():
        if s["history"]["impressions"]:
            fan_in[s["target_key"]].append(s["source"])
        else:
            fan_in_quiet[s["target_key"]] += 1

    # document frequency: a query that shows up on many old pages (site-wide noise) counts for less
    qsets = {k: {q["query"] for q in s["history"]["top_queries"]} for k, s in sources.items()}
    n_hist = max(1, sum(1 for v in qsets.values() if v))
    df = defaultdict(int)
    for v in qsets.values():
        for q in v:
            df[q] += 1

    rows = []
    for s in sources.values():
        h = s["history"]
        weighted = []
        for q in h["top_queries"]:
            qt = _tokens(q["query"], brand, ignore)
            if not qt:
                continue  # brand-only or site: queries say nothing about topic
            idf = math.log(1 + n_hist / df[q["query"]]) / math.log(1 + n_hist)
            pos = q["position"] or 100
            weighted.append((q["query"], qt, q["impressions"] * idf * min(1.0, 20 / pos)))
        flags = []
        if not h["impressions"]:
            flags.append("NO_HISTORY")
        if len(fan_in[s["target_key"]]) >= 3:
            flags.append("MANY_TO_ONE")
        row = {"source": s["source"], "target": s["target"], "status": s["status"], "lines": s["lines"],
               "clicks": h["clicks"], "impressions": h["impressions"],
               "top_queries": [f"{q['query']} ({q['impressions']} impr, pos {q['position']})" for q in h["top_queries"][:5]],
               "target_in_sitemap": s["target_key"] in live if s["target_key"].startswith("/") else None,
               "topic_match": None, "flags": flags, "suggested_target": None}
        if weighted:
            tscore, _ = _score(weighted, s["target_key"], brand, ignore)
            row["topic_match"] = tscore
            cands = []
            for p in live:
                if p in (s["target_key"], norm_path(s["source"])):
                    continue
                sc, hits = _score(weighted, p, brand, ignore)
                if sc:
                    cands.append((sc, -p.count("/"), p, hits))
            cands.sort(key=lambda c: (-c[0], -c[1], c[2]))
            if cands:
                sc, _, p, hits = cands[0]
                better = sc > (tscore or 0) * 1.5 and sc - (tscore or 0) >= 0.05
                if better and h["impressions"] >= min_impr:
                    row["suggested_target"] = (p if p == "/" else p + "/")
                    row["suggested_score"] = sc
                    row["suggested_because"] = hits[:3]
                    flags.append("TOPIC_MISMATCH" if not tscore else "BETTER_TARGET")
        rows.append(row)

    rows.sort(key=lambda r: (r["suggested_target"] is None, "MANY_TO_ONE" not in r["flags"], -r["impressions"]))
    many = [{"target": t, "sources_with_history": v, "sources_without_history": fan_in_quiet[t]}
            for t, v in fan_in.items() if len(v) >= 3]
    fixes = [f"{r['source']} -> {r['suggested_target']} (now {r['target']}; {', '.join(r['flags'])})"
             for r in rows if r["suggested_target"]]
    count = defaultdict(int)
    for r in rows:
        for f in r["flags"]:
            count[f] += 1
    return {"site": site, "file": os.path.abspath(redirects_file), "window": hist["window"], "base": base,
            "sitemap_urls": len(live),
            "summary": {"sources_checked": len(rows), "with_history": sum(1 for r in rows if r["impressions"]),
                        "flags": dict(count), "many_to_one_targets": many, "suggested_fixes": fixes,
                        "clean": not fixes,
                        "targets_not_in_sitemap": {t: _http_status(urllib.parse.urljoin(base + "/", t)) if base else None
                                                   for t in sorted({r["target"] for r in rows if r["target_in_sitemap"] is False})}},
            "skipped_rules": skipped, "rows": rows}


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description="Search Console reader (read-only, scope webmasters.readonly). "
                                 "Config: $GSC_CONFIG_DIR (default ~/.config/gsc-reader). Reports: $GSC_REPORTS_DIR (default ./gsc-reports).")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--out", help="save the full JSON here; stdout then gets only a short summary")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", parents=[common])
    sub.add_parser("properties", parents=[common])
    p = sub.add_parser("performance", parents=[common]); p.add_argument("site"); p.add_argument("--days", type=int, default=28)
    p = sub.add_parser("sitemaps", parents=[common]); p.add_argument("site")
    p = sub.add_parser("inspect", parents=[common]); p.add_argument("site"); p.add_argument("url")
    p = sub.add_parser("audit", parents=[common]); p.add_argument("site"); p.add_argument("--max-urls", type=int, default=200); p.add_argument("--days", type=int, default=28)
    p = sub.add_parser("export", parents=[common]); p.add_argument("site")
    p.add_argument("--start", required=True); p.add_argument("--end", required=True)
    p.add_argument("--dims", default="query,page", help="comma list: query,page,date,country,device,searchAppearance")
    p.add_argument("--device", nargs="?", const="__dim__", help="bare: add device as a dimension; MOBILE/DESKTOP/TABLET: filter")
    p.add_argument("--row-limit", type=int, default=25000, help="page size per request (max 25000); pages until empty")
    p = sub.add_parser("opportunities", parents=[common]); p.add_argument("site")
    p.add_argument("--days", type=int, default=28); p.add_argument("--min-impr", type=int, default=15); p.add_argument("--top", type=int, default=50)
    p = sub.add_parser("url-history", parents=[common]); p.add_argument("site")
    p.add_argument("--urls-file", required=True); p.add_argument("--days", type=int, default=480)
    p = sub.add_parser("redirect-check", parents=[common]); p.add_argument("site")
    p.add_argument("--redirects", required=True, help="_redirects file (one 'from to [status]' rule per line) or 2-column CSV old,new")
    p.add_argument("--days", type=int, default=480); p.add_argument("--base", help="live site base for sitemap.xml, e.g. https://www.example.com")
    p.add_argument("--ignore-words", default="", help="town/area/brand words to ignore when matching topics, comma separated")
    p.add_argument("--min-impr", type=int, default=20, help="only suggest a new target when the source had at least this many impressions")
    a = ap.parse_args()

    try:
        svc = service(interactive=(a.cmd == "login"))
        if a.cmd in ("login", "properties"):
            out = properties(svc)
        elif a.cmd == "performance":
            out = performance(svc, a.site, a.days)
        elif a.cmd == "sitemaps":
            out = sitemaps(svc, a.site)
        elif a.cmd == "inspect":
            out = inspect(svc, a.site, a.url)
        elif a.cmd == "audit":
            out = audit(svc, a.site, a.max_urls, a.days)
        elif a.cmd == "export":
            out = export(svc, a.site, a.start, a.end, a.dims, a.device, a.row_limit)
        elif a.cmd == "opportunities":
            out = opportunities(svc, a.site, a.days, a.min_impr, a.top)
        elif a.cmd == "url-history":
            with open(a.urls_file, encoding="utf-8") as f:
                out = url_history(svc, a.site, f.read().splitlines(), a.days)
        else:
            out = redirect_check(svc, a.site, a.redirects, a.days, a.base, a.ignore_words.split(","), a.min_impr)
    except RefreshError:
        sys.exit(EXPIRED_MSG)
    except HttpError as e:
        sys.exit(f"Search Console API error {e.resp.status}: {getattr(e, 'reason', '') or str(e)[:300]}")

    if a.out:
        with open(a.out, "w") as f:
            json.dump(out, f, indent=1)
        summary = out.get("summary") if isinstance(out, dict) else None
        print(json.dumps({"saved": os.path.abspath(a.out), "summary": summary}, indent=1))
    else:
        print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
