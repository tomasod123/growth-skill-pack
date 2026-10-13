#!/usr/bin/env python3
"""Read-only Meta ad account audit: pre-launch gate + live performance + payback.

Usage:
  set -a; source ~/.claude/skills/.env; set +a
  python3 meta_audit.py --act $META_AD_ACCOUNT_ID --postcode "AB1 2CD" --market UK --mode local \
      --out ./meta-launch-audit-output/<date> [--days 14] [--customer-value 180 \
      --lead-to-customer 0.25] [--creatives] [--config ../config/thresholds.json]

GET only. Never edits, never switches anything on. Token: META_ACCESS_TOKEN from the environment
(use a read-only system user, so "can we fix it from here" is always no: hand the fix to a human).
Modes: local = a local business (clinic, practice) with a geo radius; b2b = B2B / SaaS / national.
Writes AUDIT.md (ranked P0/P1/P2), raw.json, and with --creatives a creatives/ folder plus
contact-sheet.jpg to LOOK at (the visual check is done by the model/human, not this script).
"""
import argparse, json, math, os, re, ssl, sys, urllib.error, urllib.parse, urllib.request
from collections import Counter

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = ssl.create_default_context()

GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "").strip() or "v21.0"  # override when Meta retires v21.0
G = f"https://graph.facebook.com/{GRAPH_VERSION}/"
UA = {"User-Agent": "Mozilla/5.0"}


def env(key):
    v = os.environ.get(key, "").strip()
    if not v:
        sys.exit(f"{key} is not set. Run: set -a; source ~/.claude/skills/.env; set +a")
    return v


# Thresholds are YOUR numbers and ship unset (None). Set them in config/thresholds.json (copy
# thresholds.example.json; its _readme says how to derive each one from your last 90 days).
# Any check whose threshold is None is skipped and listed as "threshold not set, skipped".
DEFAULTS = {
    "target_cpl": None,                 # your target cost per lead, account currency
    "kill_cpl_multiple": None,          # zero-lead ad is a kill candidate after this many x target CPL
    "min_spend_no_target": None,        # spend line used instead when target_cpl is not set
    "kill_ctr_below_pct": None,         # ...and link CTR (%) is below this
    "hook_rate_floor_pct": None,        # 3-second views / impressions, %
    "frequency_ceiling_local": None,    # local mode only
    "max_radius_miles_local": None,     # local mode only
    "min_ads_per_adset": None,          # below this = P1
    "target_ads_per_adset": None,       # below this = P2
    "min_daily_budget_per_ad": None,    # account currency per day
}
CFG = dict(DEFAULTS)
SKIPPED = {}  # threshold key -> check that was skipped because it is not set


def th(key, check):
    """Return threshold `key` as a float, or None (and record the skip) if it is unset or not a number."""
    v = CFG.get(key)
    if v is None or v == "":
        if key not in SKIPPED:
            SKIPPED[key] = check
            print(f"{key}: threshold not set, skipped ({check})", file=sys.stderr)
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        if key not in SKIPPED:
            SKIPPED[key] = f"{check} (value {v!r} is not a number)"
            print(f"{key}: threshold not a number, skipped ({check})", file=sys.stderr)
        return None


def fmt(v):
    return f"{v:g}"


TOKEN = None


def g(path, **p):
    p["access_token"] = TOKEN
    url = G + path + "?" + urllib.parse.urlencode(p)
    try:
        return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), context=CTX))
    except urllib.error.HTTPError as e:
        try:
            return {"ERR": json.loads(e.read().decode()).get("error", {}).get("message", "")[:200]}
        except Exception:
            return {"ERR": f"HTTP {e.code}"}


def allpages(path, **p):
    out, r = [], g(path, **p)
    if "ERR" in r:
        return r
    out += r.get("data", [])
    while r.get("paging", {}).get("next"):
        r = json.load(urllib.request.urlopen(urllib.request.Request(r["paging"]["next"], headers=UA), context=CTX))
        out += r.get("data", [])
    return {"data": out}


def miles(a, b):
    R, p = 3958.8, math.radians
    h = math.sin(p(b[0] - a[0]) / 2) ** 2 + math.cos(p(a[0])) * math.cos(p(b[0])) * math.sin(p(b[1] - a[1]) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def geocode(pc):
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(
            "https://api.postcodes.io/postcodes/" + urllib.parse.quote(pc.replace(" ", "")), headers=UA), context=CTX))
        return r["result"]["latitude"], r["result"]["longitude"]
    except Exception:
        return None


# ---------- copy rules (local health / aesthetics business) ----------
POM = r"\b(botox|dysport|bocouture|xeomin|azzalure|alluzience|letybo|botulinum|toxin|anti[- ]?wrinkle|wrinkle[- ]relax\w*|muscle[- ]relax\w*|baby botox|line[- ]softening|aqualyx|kybella|lemon bottle|mounjaro|wegovy|ozempic|saxenda|semaglutide|tirzepatide|liraglutide|weight[- ]loss injection\w*|fat[- ]dissolv\w*)\b"
SCARCITY = r"\b(only \d+|limited (spaces|spots|places|time)|spots? left|places? left|hurry|last chance|ends (tonight|today|soon)|while stocks|book now before)\b"
GUARANTEE = r"\b(guarantee\w*|money[- ]back|risk[- ]free|100% (results|safe))\b"
OUTCOME = r"\b(look \d+ years younger|instant results|permanent(ly)?|pain[- ]free|no downtime|cure\w*|miracle|flawless|perfect skin)\b"
PERSONAL = r"\b(are you (over ?weight|fat|ugly|old|insecure)|your (wrinkles|fat|belly|double chin|acne scars|saggy)|you have (wrinkles|acne|cellulite))\b"
VALUE_STACK = r"\b(worth £?\$?\d|value of £?\$?\d|rrp)\b"
BEFORE_AFTER = r"\b(before (and|&) after|before/after|b&a)\b"


def scan_copy(text, market, mode, required=True):
    t = (text or "").lower()
    f = []
    if mode == "local":
        for rx, sev, why in [
            (POM, "P0", "names or implies a prescription-only medicine (UK Human Medicines Regs / ASA guidance; IE similar; AU TGA; US: check FDA/FTC and state rules)"),
            (GUARANTEE, "P0", "guarantee / risk-free claim (Meta unrealistic outcomes + ASA)"),
            (OUTCOME, "P1", "absolute outcome claim needs substantiation (CAP 3.1, Meta unrealistic outcomes)"),
            (PERSONAL, "P0", "asserts a personal attribute (Meta Personal Attributes policy)"),
            (SCARCITY, "P1", "scarcity / urgency pressure (reads as a scam pattern to Meta review)"),
            (VALUE_STACK, "P1", "'worth £X' value stack (hard to substantiate; house rule)"),
        ]:
            m = re.findall(rx, t)
            if m:
                f.append((sev, why, sorted({x if isinstance(x, str) else x[0] for x in m})))
        if market == "AU" and re.search(BEFORE_AFTER, t):
            f.append(("P0", "before/after in AU cosmetic ad (Ahpra 2023 guidelines)", ["before/after"]))
        if t.count("free") > 1:
            f.append(("P1", "'free' used more than once", [f"{t.count('free')}x"]))
        if required and not re.search(r"\b18s?\b|over.?18|adults", t):
            f.append(("P1", "no 18+ line in primary text", []))
        if required and not re.search(r"t&c|terms", t):
            f.append(("P2", "no 'T&Cs apply' in primary text (needed when an offer is priced)", []))
    else:  # b2b
        if re.search(r"£\s?\d{2,3},?\d{3}|\$\s?\d{2,3},?\d{3}|\d+k (a|per) month|revenue|income", t):
            f.append(("P0", "money / income figure in B2B copy (income claims are a common cause of account restrictions)", []))
        if re.search(GUARANTEE, t):
            f.append(("P0", "guarantee in B2B copy", []))
        if re.search(SCARCITY, t):
            f.append(("P1", "scarcity counter in B2B copy", []))
    return f


def creative_texts(cr):
    """All primary texts + headlines from object_story_spec or asset_feed_spec."""
    bodies, titles, cta = [], [], None
    oss = cr.get("object_story_spec") or {}
    ld = oss.get("link_data") or oss.get("video_data") or {}
    if ld:
        bodies.append(ld.get("message", ""))
        titles.append(ld.get("name") or ld.get("title") or "")
        cta = ld.get("call_to_action")
    afs = cr.get("asset_feed_spec") or {}
    bodies += [b.get("text", "") for b in afs.get("bodies", [])]
    titles += [b.get("text", "") for b in afs.get("titles", [])]
    if afs.get("call_to_actions"):
        cta = afs["call_to_actions"][0]
    return [b for b in bodies if b], [x for x in titles if x], cta


def main():
    global TOKEN
    ap = argparse.ArgumentParser()
    ap.add_argument("--act", required=True)
    ap.add_argument("--postcode", help="business postcode (UK, via postcodes.io) for the geo check")
    ap.add_argument("--latlon", help="business 'lat,lon' (any country) if no UK postcode")
    ap.add_argument("--town", help="town name, should appear in local ad copy")
    ap.add_argument("--market", default="UK", choices=["UK", "IE", "AU", "US", "CA"])
    ap.add_argument("--mode", default="local", choices=["local", "b2c", "b2b"], help="local/b2c = local business with health-ad copy rules; b2b = B2B or national")
    ap.add_argument("--campaign", help="limit to campaign ids (comma)")
    ap.add_argument("--days", type=int, default=0, help="live mode: insights window")
    ap.add_argument("--customer-value", type=float, help="first-purchase cash per new customer (first visit, first invoice)")
    ap.add_argument("--ltv", type=float, help="12-month gross profit per customer (optional)")
    ap.add_argument("--lead-to-customer", type=float, help="leads -> paying customer rate, e.g. 0.2")
    ap.add_argument("--creatives", action="store_true", help="download images/thumbnails + contact sheet")
    ap.add_argument("--out", required=True)
    ap.add_argument("--config", help="thresholds JSON (see config/thresholds.example.json)")
    a = ap.parse_args()
    if a.mode == "local":
        a.mode = "local"
    if a.config:
        CFG.update({k: v for k, v in json.load(open(os.path.expanduser(a.config))).items() if not k.startswith("_")})
    TOKEN = env("META_ACCESS_TOKEN")
    out = os.path.expanduser(a.out)
    os.makedirs(out, exist_ok=True)
    A = "act_" + a.act.replace("act_", "")
    F = []  # (sev, area, finding, evidence, fix, owner, minutes)

    def add(sev, area, finding, evidence="", fix="", owner="Media buyer", mins=5):
        F.append((sev, area, finding, evidence, fix, owner, mins))

    raw = {}
    raw["account"] = g(A, fields="name,account_status,disable_reason,currency,timezone_name,amount_spent,spend_cap,funding_source_details")
    if "ERR" in raw["account"]:
        add("P2", "Account", "Account status not readable by this token", raw["account"]["ERR"],
            "Check Billing + Account quality in Business Manager by eye (card valid, no restriction).", "Media buyer", 2)
    else:
        st = raw["account"].get("account_status")
        if st != 1:
            add("P0", "Account", f"account_status {st} (1 = active; 2 disabled, 3 unsettled, 9 grace period)",
                "", "Fix billing / restriction before launch. Read act/activities for ad_account_update_status.", "Account owner", 15)
    raw["campaigns"] = allpages(A + "/campaigns", fields="id,name,status,effective_status,objective,special_ad_categories,daily_budget,lifetime_budget,bid_strategy,issues_info", limit=100)
    raw["adsets"] = allpages(A + "/adsets", fields="id,name,campaign_id,status,effective_status,daily_budget,lifetime_budget,optimization_goal,billing_event,promoted_object,targeting,destination_type,start_time,end_time,issues_info", limit=100)
    raw["ads"] = allpages(A + "/ads", fields="id,name,adset_id,campaign_id,status,effective_status,issues_info,ad_review_feedback,creative{id,name,object_story_spec,asset_feed_spec,thumbnail_url,image_url,instagram_user_id,url_tags,video_id}", limit=200)
    raw["pixels"] = g(A + "/adspixels", fields="id,name,last_fired_time")
    camps = raw["campaigns"].get("data", [])
    if a.campaign:
        keep = set(a.campaign.split(","))
        camps = [c for c in camps if c["id"] in keep]
    cids = {c["id"] for c in camps}
    sets = [s for s in raw["adsets"].get("data", []) if s.get("campaign_id") in cids or not a.campaign]
    ads = [x for x in raw["ads"].get("data", []) if x.get("campaign_id") in cids or not a.campaign]
    # skip archived/deleted noise
    sets = [s for s in sets if s.get("effective_status") not in ("ARCHIVED", "DELETED")]
    ads = [x for x in ads if x.get("effective_status") not in ("ARCHIVED", "DELETED")]
    camps = [c for c in camps if c.get("effective_status") not in ("ARCHIVED", "DELETED")]

    loc = None
    if a.postcode:
        loc = geocode(a.postcode)
    elif a.latlon:
        loc = tuple(float(x) for x in a.latlon.split(","))
    if not camps:
        add("P0", "Campaign", "No campaign found in the account", "", "Build the campaign.", "Media buyer", 30)

    # ---- campaign checks
    for c in camps:
        if c.get("special_ad_categories"):
            add("P1", "Campaign", f"{c['name']}: special ad category {c['special_ad_categories']}",
                "", "Health and B2B offers are rarely housing/credit/employment/politics; remove unless it really is one (it restricts targeting).", "Media buyer", 3)
        if c.get("objective") not in ("OUTCOME_LEADS", "OUTCOME_SALES", "LEAD_GENERATION", "CONVERSIONS"):
            add("P1", "Campaign", f"{c['name']}: objective {c.get('objective')}", "", "Lead campaigns use the Leads (or Sales with a lead event) objective.", "Media buyer", 5)
        for i in c.get("issues_info") or []:
            add("P0", "Campaign", f"{c['name']}: Meta issue", str(i)[:200], "Resolve in Ads Manager.", "Media buyer", 10)

    # ---- ad set checks
    for s in sets:
        t = s.get("targeting", {})
        geo = t.get("geo_locations", {})
        pts = []
        for p in geo.get("places", []) + geo.get("custom_locations", []):
            if "latitude" in p:
                pts.append((p.get("name") or p.get("address_string") or "pin", p["latitude"], p["longitude"], p.get("radius"), p.get("distance_unit", "mile")))
        for cty in geo.get("cities", []):
            pts.append((cty.get("name"), None, None, cty.get("radius"), cty.get("distance_unit", "mile")))
        geo_txt = "; ".join(f"{n} r={r}{u[:2] if u else ''}" for n, _, _, r, u in pts) or json.dumps(geo)[:200]
        if a.mode == "local":
            if geo.get("countries") and not pts:
                add("P0", "Targeting", f"{s['name']}: whole-country targeting for a local business", geo_txt,
                    "Set a radius around the business postcode or pin.", "Media buyer", 3)
            if loc and pts:
                inside = []
                for n, la, lo, r, u in pts:
                    if la is None:
                        continue
                    d = miles(loc, (la, lo))
                    rad = (r or 0) * (0.621 if (u or "").startswith("kilo") else 1)
                    inside.append(d <= rad)
                    max_rad = th("max_radius_miles_local", "wide local radius check")
                    if max_rad is not None and rad > max_rad:
                        add("P1", "Targeting", f"{s['name']}: radius {rad:.0f} mi is wide for one location", n,
                            "Most local customers come from a short drive. Check where existing customers live and set the radius from that.", "Account owner", 2)
                    if d > rad:
                        add("P0", "Targeting", f"{s['name']}: the BUSINESS IS OUTSIDE the targeted circle",
                            f"circle '{n}' centre is {d:.1f} mi from {a.postcode or a.latlon}, radius {rad:.0f} mi",
                            f"Ads Manager > ad set > Locations: remove '{n}', drop a pin or type the business address, set the radius. "
                            "A 'place' (region) with a radius is centred on that region's middle, not the business.", "Media buyer", 3)
                if not inside:
                    add("P1", "Targeting", f"{s['name']}: could not measure geo against the business location", geo_txt, "Check by eye on the map.", "Media buyer", 2)
        if (t.get("age_min") or 18) < 18:
            add("P0", "Targeting", f"{s['name']}: age_min {t.get('age_min')}", "", "Set 18+ (health and aesthetics offers are adult only).", "Media buyer", 1)
        lt = geo.get("location_types")
        if a.mode == "local" and lt and "home" not in lt:
            add("P1", "Targeting", f"{s['name']}: location types {lt}", "", "Use people living in / recently in.", "Media buyer", 1)
        po = s.get("promoted_object") or {}
        dest = s.get("destination_type")
        if s.get("optimization_goal") == "OFFSITE_CONVERSIONS" and not raw["pixels"].get("data"):
            add("P0", "Tracking", f"{s['name']}: optimises for website conversions but the account has no pixel", "", "Install pixel + Conversions API or switch to an instant form.", "Media buyer", 20)
        if dest == "ON_AD" and s.get("optimization_goal") not in ("LEAD_GENERATION", "QUALITY_LEAD"):
            add("P1", "Delivery", f"{s['name']}: instant form but optimisation {s.get('optimization_goal')}", "", "Optimise for leads.", "Media buyer", 2)
        if s.get("end_time"):
            add("P2", "Delivery", f"{s['name']}: has an end date {s['end_time'][:10]}", "", "Remove unless the offer really ends then.", "Media buyer", 1)
        b = s.get("daily_budget") or next((c.get("daily_budget") for c in camps if c["id"] == s.get("campaign_id")), None)
        if b:
            add("INFO", "Budget", f"{s['name']}: daily budget {int(b)/100:.2f} {raw['account'].get('currency','')}", "", "", "", 0)
        add("INFO", "Targeting", f"{s['name']}: geo {geo_txt}; ages {t.get('age_min')}-{t.get('age_max')}; "
            f"advantage audience {'on' if (t.get('targeting_automation') or {}).get('advantage_audience') else 'off'}; "
            f"placements {'Advantage+ (all)' if not t.get('publisher_platforms') else t.get('publisher_platforms')}", "", "", "", 0)
        for i in s.get("issues_info") or []:
            add("P0", "Delivery", f"{s['name']}: Meta issue", str(i)[:200], "Resolve in Ads Manager.", "Media buyer", 10)
        n_ads = sum(1 for x in ads if x.get("adset_id") == s["id"])
        if n_ads == 0:
            add("P0", "Creative", f"{s['name']}: no ads", "", "Load the approved creatives.", "Media buyer", 20)
        elif (mn := th("min_ads_per_adset", "too few ads per ad set (P1)")) is not None and n_ads < mn:
            add("P1", "Creative", f"{s['name']}: only {n_ads} ads", "", f"Launch with at least {fmt(mn)} genuinely different concepts; Meta recommends creative diversity for its retrieval system.", "Media buyer", 15)
        elif (tg := th("target_ads_per_adset", "ads per ad set below your target (P2)")) is not None and n_ads < tg:
            add("P2", "Creative", f"{s['name']}: {n_ads} ads (target {fmt(tg)}+ distinct concepts)", "", "Fine to launch; add the rest in week 1.", "Media buyer", 15)

    # ---- tracking: URL parameters (a launch with none set cannot attribute leads to ads)
    no_tags = [x.get("name", "?") for x in ads
               if not ((x.get("creative") or {}).get("url_tags") or "").strip()]
    if no_tags and len(no_tags) == len(ads):
        add("P1", "Tracking", f"NO ad has URL parameters set ({len(ads)} ads)",
            "creative.url_tags is empty on every ad, so nothing downstream can tell which ad produced a lead. "
            "Instant-form leads carry the form id but not the ad, so CPL per creative cannot be worked out.",
            "Ads Manager > ad > Tracking > URL parameters. Paste: "
            "utm_source=facebook&utm_medium=paid&utm_campaign={{campaign.name}}&utm_content={{ad.name}}&utm_term={{adset.name}} "
            "Do it on every ad. If the brief did not ask for it, fix the brief too.", "Media buyer", 15)
    elif no_tags:
        add("P2", "Tracking", f"{len(no_tags)} of {len(ads)} ads have no URL parameters",
            ", ".join(no_tags[:8]), "Add the same utm string used on the other ads.", "Media buyer", 10)

    # ---- budget spread across creatives
    try:
        daily = sum(float(c.get("daily_budget") or 0) for c in camps) / 100.0
        daily += sum(float(st.get("daily_budget") or 0) for st in sets) / 100.0
        if daily > 0 and len(ads) > 0:
            per = daily / len(ads)
            min_per = th("min_daily_budget_per_ad", "daily budget per ad check")
            if min_per is not None and per < min_per:
                add("P1", "Delivery", f"{len(ads)} ads sharing {daily:.2f} a day = {per:.2f} per ad",
                    f"Under about {fmt(min_per)} a day per ad, most never gather enough data to judge and the ad set "
                    "struggles to leave learning.",
                    "Pause the weakest, or raise the budget.", "Media buyer", 10)
    except Exception:
        pass

    # ---- ad checks
    forms, ig_missing, ctas = set(), [], Counter()
    for x in ads:
        cr = x.get("creative") or {}
        bodies, titles, cta = creative_texts(cr)
        if cta:
            ctas[cta.get("type")] += 1
            fid = (cta.get("value") or {}).get("lead_gen_form_id")
            if fid:
                forms.add(fid)
        oss = cr.get("object_story_spec") or {}
        if not (oss.get("instagram_user_id") or cr.get("instagram_user_id")):
            ig_missing.append(x["name"])
        texts = [(b, False) for b in bodies + titles] + [(" ".join(bodies), True)]
        for b, req in texts:
            for sev, why, ev in [z for z in scan_copy(b, a.market, a.mode, required=req) if req == ("no " in z[1][:3])]:
                add(sev, "Compliance", f"{x['name']}: {why}", ", ".join(ev), "Rewrite the line; re-run.", "Account owner" if sev == "P0" else "Media buyer", 5)
        if a.town and not any(a.town.lower() in (b or "").lower() for b in bodies + titles):
            add("P2", "Creative", f"{x['name']}: town '{a.town}' not in copy", "", "A local place name in the headline or line 1 usually lifts local CTR.", "Media buyer", 3)
        if a.mode == "local" and bodies and not re.search(r"£|€|\$\s?\d|free", " ".join(bodies).lower()):
            add("P2", "Creative", f"{x['name']}: no concrete offer/price in copy", "", "Local lead ads without a concrete priced or free offer tend to underperform; add one.", "Account owner", 5)
        if x.get("ad_review_feedback"):
            add("P0", "Review", f"{x['name']}: Meta review feedback", json.dumps(x["ad_review_feedback"])[:250], "Fix and resubmit.", "Media buyer", 15)
        for i in x.get("issues_info") or []:
            add("P0", "Delivery", f"{x['name']}: Meta issue", str(i)[:200], "Resolve in Ads Manager.", "Media buyer", 10)
        if x.get("effective_status") == "DISAPPROVED":
            add("P0", "Review", f"{x['name']}: DISAPPROVED", "", "Read the reason in Account Quality; fix copy/creative.", "Account owner", 15)
    if ig_missing and len(ig_missing) == len(ads) and ads:
        add("P1", "Identity", "No ad has an Instagram account attached", ", ".join(ig_missing[:5]), "Attach the business Instagram account so IG placements run as the brand.", "Media buyer", 5)
    if len(forms) > 1:
        add("P1", "Lead form", f"{len(forms)} different lead forms in use", ", ".join(forms), "One form per offer, or the GHL mapping must cover all of them.", "Media buyer", 5)
    for fid in forms:
        r = g(fid, fields="id,name,status,questions,privacy_policy_url,thank_you_page,leads_count")
        raw.setdefault("forms", {})[fid] = r
        if "ERR" in r:
            add("P1", "Lead form", f"Form {fid} not readable by API: check by eye", r["ERR"][:120],
                "Open the form: privacy URL works, questions = full name + phone + email (+1 qualifier), "
                "thank-you screen says what happens next and who calls, 'Higher intent' review screen ON.", "Media buyer", 5)
        else:
            if not r.get("privacy_policy_url"):
                add("P0", "Lead form", f"Form {r.get('name')}: no privacy policy URL", "", "Add the business privacy policy page.", "Media buyer", 5)
            if r.get("status") != "ACTIVE":
                add("P0", "Lead form", f"Form {r.get('name')}: status {r.get('status')}", "", "Use an active form.", "Media buyer", 5)
    add("INFO", "Creative", f"{len(ads)} ads; CTA types {dict(ctas)}; forms {sorted(forms)}", "", "", "", 0)

    # ---- live mode
    perf = []
    if a.days:
        ins = allpages(A + "/insights", level="ad", date_preset=None or "maximum" if a.days > 89 else None,
                       time_range=json.dumps({"since": __import__("datetime").date.fromordinal(__import__("datetime").date.today().toordinal() - a.days).isoformat(),
                                              "until": __import__("datetime").date.today().isoformat()}),
                       fields="ad_id,ad_name,spend,impressions,reach,frequency,cpm,inline_link_click_ctr,actions,video_thruplay_watched_actions,video_p25_watched_actions",
                       limit=500)
        raw["insights"] = ins
        tot_spend = tot_leads = 0
        for r in ins.get("data", []):
            acts = {z["action_type"]: float(z["value"]) for z in r.get("actions", [])}
            leads = acts.get("lead", 0)  # ONLY 'lead'; substring matching (e.g. onsite_conversion.lead_grouped) double counts
            v3 = acts.get("video_view", 0)
            imp = float(r.get("impressions", 0) or 0)
            thru = sum(float(z["value"]) for z in r.get("video_thruplay_watched_actions", []) or [])
            spend = float(r.get("spend", 0))
            tot_spend += spend; tot_leads += leads
            perf.append(dict(ad=r["ad_name"], spend=spend, leads=leads, cpl=spend / leads if leads else None,
                             ctr=float(r.get("inline_link_click_ctr") or 0), cpm=float(r.get("cpm") or 0),
                             freq=float(r.get("frequency") or 0),
                             hook=(v3 / imp * 100) if imp and v3 else None, hold=(thru / v3 * 100) if v3 and thru else None))
        perf.sort(key=lambda z: (z["cpl"] is None, z["cpl"] or 0))
        for p in perf:
            if a.mode == "local":
                fc = th("frequency_ceiling_local", "local frequency check")
                if fc is not None and p["freq"] > fc:
                    add("P1", "Live", f"{p['ad']}: frequency {p['freq']:.1f}", "", "Local audience is saturating: new concepts or widen radius a little.", "Account owner", 10)
            tcpl = th("target_cpl", "zero-lead kill line from target CPL") if CFG.get("target_cpl") not in (None, "") else None
            mult = th("kill_cpl_multiple", "zero-lead kill line from target CPL") if tcpl is not None else None
            if tcpl is not None and mult is not None:
                kill_spend = tcpl * mult
            else:
                kill_spend = th("min_spend_no_target", "zero-lead kill check (needs target_cpl + kill_cpl_multiple, or min_spend_no_target)")
            ctr_floor = th("kill_ctr_below_pct", "zero-lead kill check (CTR floor)")
            if kill_spend is not None and ctr_floor is not None and p["spend"] > 0 and p["leads"] == 0 and p["ctr"] < ctr_floor and p["spend"] >= kill_spend:
                add("P1", "Live", f"{p['ad']}: {p['spend']:.0f} spent, 0 leads, CTR {p['ctr']:.2f}%", "", f"Kill candidate: spend passed your kill line ({kill_spend:.0f}) and leading indicators are weak.", "Account owner", 2)
            hf = th("hook_rate_floor_pct", "hook rate check") if p["hook"] is not None else None
            if hf is not None and p["hook"] < hf:
                add("P2", "Live", f"{p['ad']}: hook rate {p['hook']:.0f}% (<{fmt(hf)}%)", "", "Replace the first 3 seconds; keep the body.", "Account owner", 10)
        cpl = tot_spend / tot_leads if tot_leads else None
        raw["live_totals"] = dict(spend=tot_spend, leads=tot_leads, cpl=cpl)
        if a.customer_value and a.lead_to_customer and tot_leads:
            patients = tot_leads * a.lead_to_customer
            cac = tot_spend / patients if patients else None
            fe_roas = (patients * a.customer_value) / tot_spend if tot_spend else None
            raw["payback"] = dict(customers_est=patients, cac=cac, fe_roas=fe_roas,
                                  payback_purchases=(cac / a.customer_value) if cac else None,
                                  ltv_to_cac=(a.ltv / cac) if (a.ltv and cac) else None)
            if fe_roas is not None and fe_roas < 1:
                add("P1", "Payback", f"Front-end cash ROAS {fe_roas:.2f}x: the first purchase does not pay the ads back",
                    f"CAC {cac:.0f}, first purchase {a.customer_value:.0f}", "Fine only if LTV:CAC is healthy (pass --ltv) and the business can float the cash; else lift the offer price or the lead-to-customer rate.", "Account owner", 10)

    # ---- creatives download + contact sheet
    if a.creatives:
        cdir = os.path.join(out, "creatives"); os.makedirs(cdir, exist_ok=True)
        hashes = set()
        for x in ads:
            cr = x.get("creative") or {}
            for im in (cr.get("asset_feed_spec") or {}).get("images", []):
                hashes.add(im["hash"])
            ld = (cr.get("object_story_spec") or {}).get("link_data") or {}
            if ld.get("image_hash"):
                hashes.add(ld["image_hash"])
        imgs = []
        if hashes:
            r = g(A + "/adimages", hashes=json.dumps(sorted(hashes)), fields="hash,url,width,height,name")
            for im in r.get("data", []):
                p = os.path.join(cdir, f"img_{im['hash'][:10]}_{im.get('width')}x{im.get('height')}.jpg")
                try:
                    open(p, "wb").write(urllib.request.urlopen(im["url"], context=CTX).read()); imgs.append(p)
                except Exception as e:
                    print("img fail", e, file=sys.stderr)
        for x in ads:
            cr = x.get("creative") or {}
            vd = (cr.get("object_story_spec") or {}).get("video_data") or {}
            vid = vd.get("video_id") or cr.get("video_id")
            if vid:
                v = g(vid, fields="source,picture,length,title")
                raw.setdefault("videos", {})[vid] = {k: v.get(k) for k in ("length", "title")}
                pic = vd.get("image_url") or v.get("picture") or cr.get("thumbnail_url")
                if pic:
                    p = os.path.join(cdir, f"vidthumb_{vid}.jpg")
                    try:
                        open(p, "wb").write(urllib.request.urlopen(pic, context=CTX).read()); imgs.append(p)
                    except Exception:
                        pass
                if v.get("source"):
                    p = os.path.join(cdir, f"video_{vid}.mp4")
                    try:
                        open(p, "wb").write(urllib.request.urlopen(v["source"], context=CTX).read())
                    except Exception:
                        pass
                else:
                    add("INFO", "Creative", f"{x['name']}: video file not downloadable via API (normal); use the original master file for the hook-body-CTA review", "", "", "", 0)
        try:
            from PIL import Image
            thumbs = []
            for p in imgs:
                im = Image.open(p).convert("RGB"); im.thumbnail((360, 640)); thumbs.append(im)
            if thumbs:
                cols = min(4, len(thumbs)); rows = math.ceil(len(thumbs) / cols)
                sheet = Image.new("RGB", (cols * 370, rows * 650), (248, 248, 247))
                for i, im in enumerate(thumbs):
                    sheet.paste(im, ((i % cols) * 370 + 5, (i // cols) * 650 + 5))
                sheet.save(os.path.join(out, "contact-sheet.jpg"), quality=85)
        except ImportError:
            pass

    raw["skipped_checks"] = SKIPPED
    json.dump(raw, open(os.path.join(out, "raw.json"), "w"), indent=1, default=str)
    order = {"P0": 0, "P1": 1, "P2": 2, "INFO": 3}
    F.sort(key=lambda z: order[z[0]])
    n = Counter(z[0] for z in F)
    verdict = "DO NOT LAUNCH" if n["P0"] else ("LAUNCH, fix P1s this week" if n["P1"] else "READY TO LAUNCH")
    L = [f"# Meta audit {A} ({raw['account'].get('name', '')})", "",
         f"**Verdict: {verdict}** (P0 {n['P0']} · P1 {n['P1']} · P2 {n['P2']})", "",
         "| Sev | Area | Finding | Evidence | Fix | Owner | Min |", "|---|---|---|---|---|---|---|"]
    for sev, area, fi, ev, fx, ow, mi in F:
        L.append("| " + " | ".join(str(v).replace("|", "/").replace("\n", " ") for v in (sev, area, fi, ev, fx, ow, mi or "")) + " |")
    if perf:
        L += ["", "## Live performance (ad level, best CPL first)", "", "| Ad | Spend | Leads | CPL | CTR % | CPM | Freq | Hook % | Hold % |", "|---|---|---|---|---|---|---|---|---|"]
        for p in perf:
            f2 = lambda v: "" if v is None else f"{v:.2f}"
            L.append(f"| {p['ad']} | {p['spend']:.2f} | {p['leads']:.0f} | {f2(p['cpl'])} | {p['ctr']:.2f} | {p['cpm']:.2f} | {p['freq']:.2f} | {f2(p['hook'])} | {f2(p['hold'])} |")
        L += ["", f"Totals: {json.dumps(raw.get('live_totals'))}"]
        if raw.get("payback"):
            L += ["", f"Payback: {json.dumps(raw['payback'], default=lambda v: round(v, 2))}"]
    if SKIPPED:
        L += ["", "## Checks skipped (threshold not set)", "",
              "Set these in config/thresholds.json (see its _readme) to turn the checks on.", ""]
        L += [f"- `{k}`: threshold not set, skipped ({v})" for k, v in SKIPPED.items()]
    L += ["", "## Not checkable by API (do by eye, see SKILL.md step 3-5)",
          "- Lead form preview + thank-you screen + privacy URL loads",
          "- Test lead via Lead Ads Testing Tool reaches the CRM and alerts the right person",
          "- Visual + on-brand + not-AI-looking review of every creative (contact-sheet.jpg)",
          "- Video hook / body / CTA review against your own past results"]
    open(os.path.join(out, "AUDIT.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L[:4 + len(F) + 2]))
    print(f"\nWrote {out}/AUDIT.md")


if __name__ == "__main__":
    main()
