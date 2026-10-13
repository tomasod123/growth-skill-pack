#!/usr/bin/env python3
"""MODULE 4 - who is actually bidding on the client's terms (READ-ONLY).

  python3 competitors.py --keywords "a,b" --location AU [options]      one pass
  python3 competitors.py --merge DIR                                   combine the passes

Options
  --keywords "a,b"          terms to check (use the CORE buyer terms from module 2)
  --location US|2840        location_code for the SERP
  --location-name "Chicago,Illinois,United States"   town-level SERP instead of country-level
  --device desktop|mobile
  --language en
  --label "CST 10:00 Thu"  what this pass is: time of day and day, in the CLIENT's timezone
  --out DIR
  --merge DIR               read every pass-*.json in DIR and write COMPETITORS.md
  --client-domain x.com     flags the client's own ads and organic positions

HARD RULE, and the script enforces it on merge: a single SERP pull is NOT evidence that anyone
is or is not bidding. Advertisers daypart, budgets exhaust, and Google's auction is stochastic,
so a cookie-less scrape at one moment reproduces only part of the real picture. Run this 2-3
times at different hours INSIDE the client's local business hours before concluding anything.
In practice, one overnight pass can find zero ads on most terms and contradict the client's own
report that a named competitor is bidding; the client is not wrong, the single pass is.

Also encoded
  - rank_group is the organic position. rank_absolute counts ads and SERP features too, and they
    differ by 5-8 places. Never mix them in one table.
  - serp/google/organic/live/advanced returns paid items too (item_type "paid"), which is the
    cheapest way to see live ad copy and landing URLs at about US$0.002 a query.
  - Labs ranked_keywords is an ORGANIC dataset. It will never show you an ad, so an empty paid
    result from it means nothing.
"""
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gadslib import dfs_api, dfs_run_cost, location_code, md_table, now_stamp, read_json, write_json


def arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag) + 1
        if i < len(sys.argv):
            return sys.argv[i]
    return default


def host(u):
    u = (u or "").replace("https://", "").replace("http://", "")
    return u.split("/")[0].lower()


def serp(keyword, loc_code, loc_name, lang, device):
    task = {"keyword": keyword, "language_code": lang, "device": device,
            "depth": 20, "calculate_rectangles": False}
    if loc_name:
        task["location_name"] = loc_name
    else:
        task["location_code"] = loc_code
    r = dfs_api("POST", "/v3/serp/google/organic/live/advanced", [task])
    try:
        res = r["tasks"][0]["result"][0]
    except (KeyError, IndexError, TypeError):
        return {"keyword": keyword, "error": r.get("status_message"), "paid": [], "organic": []}
    items = res.get("items") or []
    paid, organic = [], []
    for it in items:
        t = it.get("type")
        if t == "paid":
            paid.append({"position": it.get("rank_absolute"), "title": it.get("title"),
                         "description": it.get("description"),
                         "url": it.get("url") or (it.get("links") or [{}])[0].get("url"),
                         "domain": host(it.get("domain") or it.get("url")),
                         "breadcrumb": it.get("breadcrumb")})
        elif t == "organic":
            organic.append({"rank_group": it.get("rank_group"), "rank_absolute": it.get("rank_absolute"),
                            "domain": (it.get("domain") or "").lower(), "url": it.get("url"),
                            "title": it.get("title")})
    return {"keyword": keyword, "se_results_count": res.get("se_results_count"),
            "paid_count": len(paid), "paid": paid, "organic": organic[:10],
            "check_url": res.get("check_url")}


def run_pass():
    kws = [k.strip() for k in (arg("--keywords") or "").split(",") if k.strip()]
    if not kws:
        print(__doc__)
        return 2
    loc = location_code(arg("--location", "US"))
    loc_name = arg("--location-name")
    lang = arg("--language", "en")
    device = arg("--device", "desktop")
    label = arg("--label") or now_stamp()
    out = os.path.abspath(arg("--out", "gads-audit-output"))
    os.makedirs(out, exist_ok=True)
    before = dfs_run_cost()
    rows = []
    for k in kws:
        rows.append(serp(k, loc, loc_name, lang, device))
        time.sleep(0.2)
    data = {"label": label, "pulled_at": now_stamp(), "location_code": loc,
            "location_name": loc_name, "language": lang, "device": device,
            "keywords": kws, "results": rows,
            "run_cost_usd": round(dfs_run_cost() - before, 4)}
    n = len(glob.glob(os.path.join(out, "competitors-pass-*.json"))) + 1
    path = write_json(os.path.join(out, f"competitors-pass-{n}.json"), data)
    ads = sum(r.get("paid_count", 0) for r in rows)
    print(f"[comp] pass {n} ({label}, {device}, "
          f"{loc_name or loc}): {len(kws)} queries, {ads} paid listing(s) seen. "
          f"Cost US${data['run_cost_usd']:.4f}. Wrote {path}", file=sys.stderr)
    print(f"[comp] NOT EVIDENCE YET. Run at least one more pass at a different hour inside the "
          f"client's business hours, then: competitors.py --merge {out}", file=sys.stderr)
    return 0


def merge():
    d = os.path.abspath(arg("--merge"))
    passes = [read_json(p) for p in sorted(glob.glob(os.path.join(d, "competitors-pass-*.json")))]
    passes = [p for p in passes if p]
    if not passes:
        sys.exit(f"[comp] no competitors-pass-*.json in {d}")
    client = (arg("--client-domain") or "").lower()
    kws = sorted({k for p in passes for k in p["keywords"]})
    # advertiser -> keyword -> set of pass labels where it was seen
    seen = {}
    for p in passes:
        for r in p["results"]:
            for a in r.get("paid", []):
                seen.setdefault(a["domain"], {}).setdefault(r["keyword"], []).append(
                    {"label": p["label"], "position": a["position"], "title": a["title"],
                     "description": a["description"], "url": a["url"]})
    npass = len(passes)
    L = ["# Who is actually bidding on these terms", "",
         f"{npass} pass(es): " + "; ".join(f"{p['label']} ({p['device']}, "
                                           f"{p.get('location_name') or p['location_code']})" for p in passes),
         "", f"Queries: {len(kws)}. Source: DataForSEO `serp/google/organic/live/advanced`, "
         "which returns paid listings alongside organic. `rank_group` below is the ORGANIC position; "
         "paid positions are absolute and counted separately.", ""]
    if npass < 2:
        L += ["> **This is one pass, so it is not evidence.** Advertisers daypart, budgets run out "
              "and the auction is stochastic. Do not tell anyone a competitor is or is not bidding "
              "off a single snapshot. Run 2-3 passes at different hours inside the client's local "
              "business hours and merge again.", ""]
    else:
        L += [f"Advertisers are reported with the number of passes they appeared in, out of {npass}. "
              "Appearing in one pass of three means they bid some of the time, not that they do not "
              "bid; absent from all passes still is not proof of absence, only of low coverage "
              "at those hours.", ""]
    rows = []
    for dom, per_kw in sorted(seen.items(), key=lambda kv: -sum(len(v) for v in kv[1].values())):
        for kw, hits in sorted(per_kw.items()):
            labels = sorted({h["label"] for h in hits})
            rows.append([dom + (" (CLIENT)" if client and client in dom else ""), kw,
                         f"{len(labels)}/{npass}", min(h["position"] or 99 for h in hits),
                         hits[0]["title"], hits[0]["url"]])
    L += ["## Paid listings seen", "",
          md_table(["Advertiser", "Query", "Passes seen in", "Best paid position", "Ad headline",
                    "Landing URL"], rows) if rows else
          "No paid listings were returned on any query in any pass. That is a coverage result, not "
          "a conclusion: a cookie-less scrape does not see every eligible advertiser on every "
          "impression. Check the client's own Auction Insights report before saying the term is "
          "uncontested.", ""]
    L += ["## Organic leaders (rank_group, organic only)", ""]
    org = {}
    for p in passes:
        for r in p["results"]:
            for o in r.get("organic", [])[:5]:
                org.setdefault(r["keyword"], {}).setdefault(o["domain"], []).append(o["rank_group"])
    for kw in kws:
        if kw in org:
            best = sorted(((dom, min(v)) for dom, v in org[kw].items()), key=lambda x: x[1])[:5]
            L.append(f"- **{kw}**: " + ", ".join(f"{dom} (#{pos})" for dom, pos in best))
    total = sum(p.get("run_cost_usd", 0) for p in passes)
    L += ["", f"DataForSEO cost across the passes: US${total:.4f} "
          f"(about US$0.0035 a query, {sum(len(p['keywords']) for p in passes)} queries).", "",
          "Read-only: SERPs were read, nothing was clicked or changed.", ""]
    md = "\n".join(L)
    with open(os.path.join(d, "COMPETITORS.md"), "w") as fh:
        fh.write(md)
    print(md)
    print(f"\n[comp] merged {npass} pass(es), {len(seen)} advertiser(s). Wrote {d}/COMPETITORS.md",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(merge() if "--merge" in sys.argv else run_pass())
