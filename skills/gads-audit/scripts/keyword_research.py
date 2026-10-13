#!/usr/bin/env python3
"""MODULE 2 - keyword research and market sizing via DataForSEO (READ-ONLY).

  python3 keyword_research.py --seeds "a,b,c" [options]

Options
  --seeds "a,b"         seed phrases for phrase-locked expansion (required)
  --location US|2840    country for volume data (AU 2036, UK/GB 2826, CA 2124, US 2840, IE 2372, NZ 2554)
  --language en
  --limit N             suggestions per seed, default 1000
  --min-volume N        drop terms under this monthly volume, default 10
  --extra "a,b"         extra exact keywords to price with search_volume/live
  --controls "a,b"      known-high-volume control terms, run in the SAME call so a null
                        result can be proved real instead of an API fault. Default: a
                        generic pair; override with two terms from the client's own market.
  --geo "chicago,evanston"     place names to split the market by (read off the keyword text)
  --core "hair transplant,fue" tokens that mean CORE demand (what the live page sells).
                        Tokens match on word boundaries; end one with * for a prefix
                        match (transplant* catches transplant and transplants).
  --adjacent "prp,hair loss treatment"   tokens that mean a DIFFERENT service line
  --negatives-extra "a,b"      niche-specific negative tokens on top of the built-in list
  --investor-extra "a,b"       niche-specific investor-intent tokens
  --ctr 0.05            assumed click-through rate for budget sizing
  --fx 1.0              USD per 1 unit of the ACCOUNT currency (e.g. about 0.66 for AUD in 2026; 1.0 for a USD account).
                        DataForSEO returns CPC and bids in USD whatever the location_code.
  --out DIR             writes keywords.json + KEYWORDS.md

Classification (precedence: NEGATIVE > INVESTOR > CORE > ADJACENT > UNCLASSIFIED)
  NEGATIVE  job seeker, salary, course/training, volunteer, student, government housing,
            job boards and marketplaces (Seek, Indeed, Gumtree), logins/portals, complaints
  INVESTOR  for sale, buy, investment, rental yield, developer, finance - property investors,
            not service buyers. A trap in care-home, clinic-property and franchise niches.
  CORE      matches a --core token: the demand the live landing page actually serves
  ADJACENT  matches an --adjacent token: real demand, different service line and page

Budget sizing: max absorbable daily spend is roughly (monthly searches / 30) x CTR x CPC.
Beyond that the money has nowhere to go: the ceiling is how many people type the terms,
not the daily cap. That is why a rank-lost campaign is never fixed by more budget.

Gotchas encoded here
  - keyword_suggestions (dataforseo_labs) is phrase-locked. keyword_ideas is NOT: its semantic
    expansion drifts off-niche (clinic ops seeds came back with urinary retention and lazy spas).
  - the Labs path is /v3/dataforseo_labs/google/keyword_suggestions/live, NOT keywords_data/...
    (the keywords_data path returns 40400 Not Found at $0 cost, which reads like an empty market).
  - every CPC / top-of-page bid is USD regardless of location_code. Convert with --fx and say so.
  - a control term runs in the same search_volume call as the terms under test, so "no volume"
    is provable rather than assumed.
  - cost of every call is printed by dfs_client.py and totalled at the end.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gadslib import dfs_api, dfs_items, dfs_run_cost, location_code, md_table, now_stamp, write_json

NEGATIVE_TOKENS = [
    "job", "jobs", "career", "careers", "vacancy rate", "salar*", "wage", "wages",
    "pay rate", "pay rates", "hourly rate", "hiring", "recruit", "recruitment", "resume", "cv ",
    "employment", "employer", "seek", "indeed", "gumtree", "linkedin", "apprentice", "traineeship",
    "course", "courses", "training", "certificate", "certification", "diploma", "tafe", "degree",
    "qualification", "how to become", "how do i become", "requirements to become", "licence to",
    "volunteer", "volunteering", "student", "internship", "work experience", "placement agency",
    "public housing", "housing commission", "social housing", "department of housing", "centrelink",
    "government housing", "council housing", "free", "cheap", "diy", "login", "log in", "portal",
    "sign in", "complaint", "complaints", "scam", "review of",
    "award rate", "enterprise agreement", "union", "payslip", "superannuation", "abn",
]
INVESTOR_TOKENS = [
    "for sale", "buy", "buying", "purchase", "invest*",
    "rental yield", "yield", "roi", "return on investment", "developer", "development site",
    "finance", "loan", "mortgage", "property", "build", "builder", "capital growth",
    "lease back", "leaseback", "franchise", "business for sale",
]
DEFAULT_CONTROLS = ["insurance", "hotel"]


def arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag) + 1
        if i < len(sys.argv):
            return sys.argv[i]
    return default


def csv_arg(flag, default=()):
    v = arg(flag)
    return [x.strip().lower() for x in v.split(",") if x.strip()] if v else [x.lower() for x in default]


_TOKRE = {}


def _hit(tok, text):
    """Word-boundary match, so 'land' does not fire inside 'queensland' and 'job' does not fire
    inside 'jobbing'. A token ending in '*' matches as a prefix ('vacanc*' -> vacancy, vacancies)."""
    if tok not in _TOKRE:
        if tok.endswith("*"):
            _TOKRE[tok] = re.compile(r"(?<![a-z0-9])" + re.escape(tok[:-1]) + r"[a-z]*", re.I)
        else:
            _TOKRE[tok] = re.compile(r"(?<![a-z0-9])" + re.escape(tok) + r"(?![a-z0-9])", re.I)
    return bool(_TOKRE[tok].search(text))


def classify(term, core, adjacent, negatives, investors):
    t = term.lower()
    for label, toks in (("NEGATIVE", negatives), ("INVESTOR", investors),
                        ("CORE", core), ("ADJACENT", adjacent)):
        for tok in toks:
            if _hit(tok, t):
                return label, tok
    return "UNCLASSIFIED", ""


def geo_of(term, geos):
    t = term.lower()
    for gname in geos:
        if gname in t:
            return gname
    return ""


def bid_fields(k):
    """keyword_info or the flat shape, whichever the endpoint used."""
    info = k.get("keyword_info") or k
    return (info.get("search_volume"), (info.get("competition_level") or info.get("competition")),
            info.get("cpc"), info.get("low_top_of_page_bid"), info.get("high_top_of_page_bid"))


def suggestions(seed, loc, lang, limit):
    body = [{"keyword": seed, "location_code": loc, "language_code": lang,
             "limit": int(limit), "include_seed_keyword": True,
             "include_serp_info": False, "ignore_synonyms": True,
             "order_by": ["keyword_info.search_volume,desc"]}]
    # the Labs path, not keywords_data: the wrong path 40400s at zero cost and looks like an empty market
    r = dfs_api("POST", "/v3/dataforseo_labs/google/keyword_suggestions/live", body)
    rows = []
    for it in dfs_items(r):
        kw = it.get("keyword") or it.get("keyword_data", {}).get("keyword")
        src = it if "keyword_info" in it else it.get("keyword_data", it)
        vol, comp, cpc, lo, hi = bid_fields(src)
        if kw:
            rows.append({"keyword": kw, "volume": vol or 0, "competition": comp, "cpc_usd": cpc,
                         "low_top_of_page_bid_usd": lo, "high_top_of_page_bid_usd": hi, "seed": seed})
    return rows


def search_volume(keywords, loc, lang):
    out, batch = [], [k for k in keywords if k]
    for i in range(0, len(batch), 700):  # endpoint caps at 1000 keywords per task
        chunk = batch[i:i + 700]
        r = dfs_api("POST", "/v3/keywords_data/google_ads/search_volume/live",
                    [{"keywords": chunk, "location_code": loc, "language_code": lang,
                      "search_partners": False}])
        for it in dfs_items(r):
            out.append({"keyword": it.get("keyword"), "volume": it.get("search_volume"),
                        "competition": it.get("competition"), "cpc_usd": it.get("cpc"),
                        "low_top_of_page_bid_usd": it.get("low_top_of_page_bid"),
                        "high_top_of_page_bid_usd": it.get("high_top_of_page_bid")})
    return out


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2
    return round(m, 2)


def main():
    seeds = [s.strip() for s in (arg("--seeds") or "").split(",") if s.strip()]
    if not seeds:
        print(__doc__)
        return 2
    loc = location_code(arg("--location", "US"))
    lang = arg("--language", "en")
    limit = int(arg("--limit", "1000"))
    min_vol = int(arg("--min-volume", "10"))
    ctr = float(arg("--ctr", "0.05"))
    fx = float(arg("--fx", "1.0"))
    out = os.path.abspath(arg("--out", "gads-audit-output"))
    os.makedirs(out, exist_ok=True)
    core = csv_arg("--core")
    adjacent = csv_arg("--adjacent")
    geos = csv_arg("--geo")
    negatives = NEGATIVE_TOKENS + csv_arg("--negatives-extra")
    investors = INVESTOR_TOKENS + csv_arg("--investor-extra")
    controls = csv_arg("--controls", DEFAULT_CONTROLS)
    extra = [x.strip() for x in (arg("--extra") or "").split(",") if x.strip()]

    print(f"[kw] {len(seeds)} seed(s), location_code {loc}, phrase-locked suggestions, "
          f"limit {limit}/seed", file=sys.stderr)
    rows, seen = [], set()
    for s in seeds:
        got = suggestions(s, loc, lang, limit)
        print(f"[kw] seed {s!r}: {len(got)} terms", file=sys.stderr)
        for r in got:
            k = r["keyword"].lower()
            if k not in seen:
                seen.add(k)
                rows.append(r)

    # exact volumes for the explicit list plus the controls, in ONE call so a null is provable
    control_rows = []
    if extra or controls:
        sv = search_volume(list(dict.fromkeys(extra + controls)), loc, lang)
        for r in sv:
            k = (r["keyword"] or "").lower()
            if k in [c.lower() for c in controls]:
                control_rows.append(r)
            elif k and k not in seen:
                seen.add(k)
                r["seed"] = "(explicit)"
                rows.append(r)
            elif k:
                for ex in rows:
                    if ex["keyword"].lower() == k and not ex.get("volume"):
                        ex.update({kk: vv for kk, vv in r.items() if vv is not None})
    controls_ok = any((c.get("volume") or 0) > 0 for c in control_rows) if control_rows else None

    kept = [r for r in rows if (r.get("volume") or 0) >= min_vol]
    for r in kept:
        cls, why = classify(r["keyword"], core, adjacent, negatives, investors)
        r["intent"] = cls
        r["intent_token"] = why
        r["geo"] = geo_of(r["keyword"], geos)
        hi = r.get("high_top_of_page_bid_usd")
        r["high_top_of_page_bid_account_currency"] = round(hi / fx, 2) if (hi and fx) else None
    kept.sort(key=lambda r: -(r.get("volume") or 0))

    def total(cls, geo=None):
        return sum(r["volume"] for r in kept if r["intent"] == cls and (geo is None or r["geo"] == geo))

    core_terms = [r for r in kept if r["intent"] == "CORE"]
    adj_terms = [r for r in kept if r["intent"] == "ADJACENT"]
    neg_terms = [r for r in kept if r["intent"] == "NEGATIVE"]
    inv_terms = [r for r in kept if r["intent"] == "INVESTOR"]
    # geo-bounded figures: only terms whose TEXT names one of the client's places
    core_geo = [r for r in core_terms if r["geo"]] if geos else core_terms
    adj_geo = [r for r in adj_terms if r["geo"]] if geos else adj_terms
    core_vol = sum(r["volume"] for r in core_geo)
    adj_vol = sum(r["volume"] for r in adj_geo)
    med_hi_usd = median([r.get("high_top_of_page_bid_usd") for r in core_geo])
    med_cpc_usd = median([r.get("cpc_usd") for r in core_geo])
    med_hi_acct = round(med_hi_usd / fx, 2) if (med_hi_usd and fx) else None
    med_cpc_acct = round(med_cpc_usd / fx, 2) if (med_cpc_usd and fx) else None
    absorb_core = round((core_vol / 30.0) * ctr * (med_cpc_acct or 0), 2)
    absorb_both = round(((core_vol + adj_vol) / 30.0) * ctr * (med_cpc_acct or 0), 2)

    data = {"pulled_at": now_stamp(), "location_code": loc, "language": lang, "seeds": seeds,
            "min_volume": min_vol, "fx_usd_per_account_unit": fx, "assumed_ctr": ctr,
            "controls": control_rows, "controls_prove_api_live": controls_ok,
            "counts": {"terms_returned": len(rows), "terms_kept": len(kept),
                       "core": len(core_terms), "adjacent": len(adj_terms),
                       "negative": len(neg_terms), "investor": len(inv_terms),
                       "unclassified": len([r for r in kept if r["intent"] == "UNCLASSIFIED"])},
            "market": {"core_monthly_searches": core_vol, "adjacent_monthly_searches": adj_vol,
                       "core_median_top_of_page_bid_usd": med_hi_usd,
                       "core_median_top_of_page_bid_account_currency": med_hi_acct,
                       "core_median_cpc_usd": med_cpc_usd,
                       "core_median_cpc_account_currency": med_cpc_acct,
                       "max_absorbable_daily_spend_core": absorb_core,
                       "max_absorbable_daily_spend_core_plus_adjacent": absorb_both},
            "by_geo": {gname: {"core": total("CORE", gname), "adjacent": total("ADJACENT", gname)}
                       for gname in geos},
            "terms": kept, "run_cost_usd": round(dfs_run_cost(), 4)}
    write_json(os.path.join(out, "keywords.json"), data)

    cur = "account currency"
    L = [f"# Keyword research and market size", "",
         f"Pulled {data['pulled_at']}. DataForSEO `dataforseo_labs/google/keyword_suggestions/live` "
         f"(phrase-locked) for expansion, `keywords_data/google_ads/search_volume/live` for exact "
         f"volumes. location_code {loc}, language {lang}. Seeds: " + ", ".join(seeds) + ".", "",
         f"**Every CPC and bid below is USD**, whatever the location code. The {cur} column divides "
         f"by {fx} (USD per 1 unit of the account currency). Google bills in the account currency at "
         "the live rate on the day, so treat the converted figure as indicative.", ""]
    if control_rows:
        L += ["**Control check.** " + "; ".join(f"{c['keyword']} = {c.get('volume')}/mo"
                                                for c in control_rows)
              + (". Controls returned volume, so any null below is a real null, not an API fault."
                 if controls_ok else ". Controls returned NOTHING: treat every null below as "
                                     "unproven and re-run before concluding a market is empty."), ""]
    L += ["## Market size", "",
          md_table(["Layer", "Monthly searches", "Median top-of-page bid (USD)",
                    f"Median top-of-page bid ({cur})", "Median CPC (USD)", f"Max absorbable spend/day ({cur})"],
                   [["CORE (what the live page sells)", core_vol, med_hi_usd, med_hi_acct, med_cpc_usd, absorb_core],
                    ["CORE + ADJACENT service lines", core_vol + adj_vol, med_hi_usd, med_hi_acct,
                     med_cpc_usd, absorb_both]]),
          "",
          f"Max absorbable spend is (monthly searches / 30) x CTR {ctr:g} x median CPC. Past that the "
          "money has nowhere to go: the ceiling is how many people type these terms. Spending into the "
          "ADJACENT layer only makes sense once there is a page and an offer built for that service "
          "line, otherwise the intent and the page do not match.", ""]
    if geos:
        L += ["### By place (read off the keyword text, since volume data is country level)", "",
              md_table(["Place", "CORE searches/mo", "ADJACENT searches/mo"],
                       [[gname, total("CORE", gname), total("ADJACENT", gname)] for gname in geos]), ""]
    for label, bucket, note in [
        ("CORE buyer terms", core_terms, "Bid on these. Match type is a client decision. The total here is "
                                        "ALL of the country; the geo-bounded figure in Market size above is "
                                        "what this client can actually reach."),
        ("ADJACENT service lines", adj_terms, "Real demand for a different service. Do not bid until "
                                             "there is a page for it."),
        ("INVESTOR intent", inv_terms, "Property investors, not service buyers. Add as negatives."),
        ("NEGATIVE signals", neg_terms, "Add as negatives before any bid or budget rise."),
    ]:
        L += ["", f"## {label} ({len(bucket)} terms, {sum(r['volume'] for r in bucket)}/mo)", "", note, "",
              md_table(["Keyword", "Vol/mo", "Competition", "Top-of-page bid (USD)",
                        f"Top-of-page bid ({cur})", "Place", "Matched on"],
                       [[r["keyword"], r["volume"], r.get("competition"),
                         f"{r.get('low_top_of_page_bid_usd')}-{r.get('high_top_of_page_bid_usd')}"
                         if r.get("high_top_of_page_bid_usd") else "no data",
                         r.get("high_top_of_page_bid_account_currency") or "no data",
                         r.get("geo") or "", r.get("intent_token") or ""] for r in bucket[:400]])]
    unc = [r for r in kept if r["intent"] == "UNCLASSIFIED"]
    if unc:
        L += ["", f"## Unclassified ({len(unc)} terms) - read these by hand", "",
              md_table(["Keyword", "Vol/mo"], [[r["keyword"], r["volume"]] for r in unc[:200]])]
    L += ["", f"## Run cost", "", f"DataForSEO this run: **US${data['run_cost_usd']:.4f}**. "
          "Read-only; no account was changed.", ""]
    with open(os.path.join(out, "KEYWORDS.md"), "w") as fh:
        fh.write("\n".join(L))
    print(f"\n[kw] {len(kept)} terms kept of {len(rows)} returned. CORE {core_vol}/mo, "
          f"ADJACENT {adj_vol}/mo, {len(neg_terms)} negative candidates, {len(inv_terms)} investor traps. "
          f"Max absorbable {absorb_core}/day on core. Cost US${data['run_cost_usd']:.4f}. "
          f"Wrote {out}/keywords.json and KEYWORDS.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
