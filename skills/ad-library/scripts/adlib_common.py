#!/usr/bin/env python3
"""Shared derivations for SCHEMA v2 of the ad library. Stdlib only.

Everything in here is DETERMINISTIC: same raw scrape in, same value out. Nothing is guessed.
A field that cannot be derived is left None and the reason is appended to `notes`.

Read references/SCHEMA.md (in this skill) for what each field means and how performance_score is
weighted. This module is the single implementation of those rules; ingest.py, backfill_v2.py,
refresh.py and query.py all call it so the numbers can never drift apart.
"""
import contextlib
import datetime
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import tempfile

# The library lives in $AD_LIBRARY_DIR, else ./ad-library-data/ under the current directory.
LIB_DEFAULT = os.path.abspath(os.path.expanduser(os.environ.get("AD_LIBRARY_DIR") or "./ad-library-data"))


def ensure_library(lib=LIB_DEFAULT):
    """Create an empty library on first use: the folder plus an empty index.jsonl."""
    os.makedirs(lib, exist_ok=True)
    p = os.path.join(lib, "index.jsonl")
    if not os.path.exists(p):
        open(p, "a", encoding="utf-8").close()
    return lib

# ---------------------------------------------------------------- controlled vocabularies
ADVERTISER_TYPES = ["single_site", "multi_site", "chain", "training_provider",
                    "product_brand", "software_vendor", "unknown"]
COUNTRY_BASES = ["ad_field", "search", "ad_copy", "advertiser_copy", "batch_label", "none"]
PLATFORMS = ["facebook", "instagram", "audience_network", "messenger", "threads", "whatsapp", "oculus"]

# ---------------------------------------------------------------- country detection
US_STATES = ("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV "
             "NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC").split()
AU_STATES = ["VIC", "NSW", "QLD", "WA", "SA", "TAS", "ACT", "NT"]

RE_US_ADDR = re.compile(r"([A-Z][A-Za-z.'\-]{1,18}(?:\s+[A-Z][A-Za-z.'\-]{1,18}){0,2}),\s*(" +
                        "|".join(US_STATES) + r")\.?\s+(\d{5})(?:-\d{4})?\b")
RE_UK_POST = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b")
RE_AU_ADDR = re.compile(r"([A-Z][A-Za-z.'\-]{1,18}(?:\s+[A-Z][A-Za-z.'\-]{1,18}){0,2}),?\s+(" +
                        "|".join(AU_STATES) + r")\.?\s+(\d{4})\b")
RE_TLD = re.compile(r"https?://[^\s\"'<>]*?\.(co\.uk|org\.uk|com\.au|net\.au|\.ie|\.ca|\.nz|com\.mx|"
                    r"\.mx|\.co\.nz|\.ae|\.za)\b|\b[\w.-]+\.(co\.uk|com\.au|net\.au|com\.mx)\b", re.I)
TLD_COUNTRY = {"co.uk": "GB", "org.uk": "GB", "com.au": "AU", "net.au": "AU", "co.nz": "NZ",
               ".nz": "NZ", ".ie": "IE", ".ca": "CA", "com.mx": "MX", ".mx": "MX", ".ae": "AE",
               ".za": "ZA"}
# international dial codes seen with a leading + (unambiguous)
RE_DIAL = re.compile(r"\+(52|61|64|44|353|1|971|27|91)[\s\-()0-9]{6,}")
DIAL_COUNTRY = {"52": "MX", "61": "AU", "64": "NZ", "44": "GB", "353": "IE", "1": "US",
                "971": "AE", "27": "ZA", "91": "IN"}
RE_NANP = re.compile(r"\(\d{3}\)\s?\d{3}[\s\-]\d{4}|\b\d{3}-\d{3}-\d{4}\b")
RE_UK_PHONE = re.compile(r"\b0(1\d{2,3}|2\d|7\d{3})[\s\-]?\d{3,4}[\s\-]?\d{3,4}\b")

# ---------------------------------------------------------------- gazetteer (cue-gated)
GAZ = {
 "GB": ["London", "Manchester", "Birmingham", "Leeds", "Glasgow", "Edinburgh", "Liverpool",
        "Bristol", "Sheffield", "Cardiff", "Belfast", "Nottingham", "Newcastle", "Leicester",
        "Southampton", "Portsmouth", "Brighton", "Reading", "Oxford", "Cambridge", "York",
        "Cheltenham", "Bath", "Exeter", "Plymouth", "Norwich", "Ipswich", "Derby", "Coventry",
        "Wolverhampton", "Stoke", "Sunderland", "Middlesbrough", "Hull", "Preston", "Blackpool",
        "Bolton", "Warrington", "Chester", "Lancaster", "Carlisle", "Durham", "Harrogate",
        "Wakefield", "Huddersfield", "Bradford", "Halifax", "Rotherham", "Doncaster", "Lincoln",
        "Peterborough", "Northampton", "Milton Keynes", "Luton", "Watford", "St Albans",
        "Chelmsford", "Colchester", "Southend", "Basildon", "Maidstone", "Canterbury", "Ashford",
        "Guildford", "Woking", "Croydon", "Kingston", "Richmond", "Wimbledon", "Chiswick",
        "Islington", "Camden", "Hackney", "Greenwich", "Harrow", "Enfield", "Barnet", "Bromley",
        "Sutton", "Ealing", "Fulham", "Chelsea", "Mayfair", "Marylebone", "Knightsbridge",
        "Harley Street", "Wilmslow", "Altrincham", "Stockport", "Solihull", "Sutton Coldfield",
        "Swansea", "Newport", "Wrexham", "Aberdeen", "Dundee", "Inverness", "Stirling", "Paisley",
        "Falkirk", "Ayr", "Perth", "Bournemouth", "Poole", "Swindon", "Gloucester",
        "Worcester", "Shrewsbury", "Telford", "Stafford", "Crewe", "Macclesfield", "Bury",
        "Rochdale", "Oldham", "Salford", "Wigan", "St Helens", "Birkenhead", "Southport",
        "Brixton", "Clapham", "Wandsworth", "Battersea", "Shoreditch", "Hampstead",
        "Notting Hill", "Wembley", "Ilford", "Romford", "Stratford", "Lewisham", "Peckham",
        "Dulwich", "Balham", "Tooting", "Streatham", "Putney", "Barnes", "Twickenham",
        "Hounslow", "Slough", "Windsor", "Wellington", "Taunton", "Lymm", "Knutsford", "Sale",
        "Didsbury", "Chorlton", "Leamington Spa", "Rugby", "Banbury", "Bicester", "Aylesbury",
        "High Wycombe", "Reigate", "Redhill", "Epsom", "Esher", "Weybridge", "Farnham",
        "Basingstoke", "Winchester", "Salisbury", "Yeovil", "Truro", "Torquay", "Newquay",
        "Somerset", "Cheshire", "Surrey", "Essex", "Kent", "Hampshire", "Yorkshire",
        "Lancashire", "Devon", "Cornwall", "Dorset", "Berkshire", "Buckinghamshire",
        "Hertfordshire", "Warwickshire", "Staffordshire", "Nottinghamshire", "Merseyside"],
 "IE": ["Dublin", "Cork", "Galway", "Limerick", "Waterford", "Kilkenny", "Drogheda", "Dundalk",
        "Sligo", "Wexford", "Athlone", "Ennis", "Tralee", "Navan", "Bray", "Swords", "Maynooth"],
 "AU": ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Canberra", "Hobart", "Darwin",
        "Gold Coast", "Newcastle", "Wollongong", "Geelong", "Townsville", "Cairns", "Toowoomba",
        "Ballarat", "Bendigo", "Launceston", "Mackay", "Rockhampton", "Bunbury", "Prahran",
        "South Yarra", "Toorak", "Richmond", "Fitzroy", "St Kilda", "Bondi", "Paddington",
        "Chatswood", "Parramatta", "Manly", "Surry Hills", "Double Bay", "Mosman", "Subiaco",
        "Fremantle", "Noosa", "Byron Bay", "Sunshine Coast", "Ipswich", "Logan", "Frankston", "Blakehurst", "Victoria", "Queensland", "Tasmania",
        "Dandenong", "Box Hill", "Camberwell", "Hawthorn", "Brighton", "Malvern", "Armadale"],
 "US": ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia", "San Antonio",
        "San Diego", "Dallas", "Austin", "Jacksonville", "Fort Worth", "Columbus", "Charlotte",
        "Indianapolis", "Seattle", "Denver", "Boston", "Nashville", "Detroit", "Portland",
        "Memphis", "Louisville", "Milwaukee", "Baltimore", "Albuquerque", "Tucson", "Fresno",
        "Sacramento", "Atlanta", "Kansas City", "Miami", "Raleigh", "Omaha", "Minneapolis",
        "Tampa", "Tulsa", "Arlington", "New Orleans", "Wichita", "Cleveland", "Bakersfield",
        "Honolulu", "Anaheim", "Santa Ana", "Riverside", "Corpus Christi", "Lexington",
        "Henderson", "Stockton", "Saint Paul", "Cincinnati", "Pittsburgh", "Greensboro",
        "Anchorage", "Plano", "Orlando", "Irvine", "Newark", "Durham", "Chula Vista", "Toledo",
        "Fort Wayne", "St Petersburg", "Laredo", "Jersey City", "Chandler", "Madison", "Lubbock",
        "Scottsdale", "Reno", "Buffalo", "Gilbert", "Glendale", "North Las Vegas", "Winston Salem",
        "Chesapeake", "Norfolk", "Fremont", "Garland", "Irving", "Hialeah", "Richmond", "Boise",
        "Spokane", "Baton Rouge", "Tacoma", "San Bernardino", "Modesto", "Fontana", "Des Moines",
        "Moreno Valley", "Santa Clarita", "Fayetteville", "Birmingham", "Oxnard", "Rochester",
        "Port St Lucie", "Grand Rapids", "Huntsville", "Salt Lake City", "Frisco", "Yonkers",
        "Amarillo", "Glendale", "Huntington Beach", "McKinney", "Montgomery", "Augusta",
        "Aurora", "Akron", "Little Rock", "Tempe", "Columbus", "Overland Park", "Grand Prairie",
        "Tallahassee", "Cape Coral", "Mobile", "Knoxville", "Shreveport", "Worcester",
        "Ontario", "Vancouver", "Sioux Falls", "Chattanooga", "Brownsville", "Fort Lauderdale",
        "Providence", "Newport News", "Rancho Cucamonga", "Santa Rosa", "Peoria", "Oceanside",
        "Elk Grove", "Salem", "Pembroke Pines", "Eugene", "Garden Grove", "Cary", "Fort Collins",
        "Corona", "Springfield", "Jackson", "Alexandria", "Hayward", "Clarksville", "Lakewood",
        "Lancaster", "Salinas", "Palmdale", "Hollywood", "Macon", "Kansas City", "Sunnyvale",
        "Pomona", "Killeen", "Escondido", "Pasadena", "Naperville", "Bellevue", "Joliet",
        "Murfreesboro", "Midland", "Rockford", "Paterson", "Savannah", "Bridgeport", "Torrance",
        "McAllen", "Syracuse", "Surprise", "Denton", "Roseville", "Thornton", "Miramar",
        "Fullerton", "Charleston", "Visalia", "Warren", "Hampton", "Boca Raton", "Highland Park",
        "Beverly Hills", "Santa Monica", "Scarsdale", "White Plains", "Larchmont", "Brooklyn",
        "SoHo", "Midtown", "Long Island", "Manhattan", "Queens", "Bronx", "Hackensack", "Boone",
        "Mendham", "Darien", "Glen Mills", "Mansfield", "Naples", "Sarasota", "Bradenton",
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
        "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
        "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
        "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire",
        "New Jersey", "New Mexico", "New York State", "North Carolina", "North Dakota", "Ohio",
        "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
        "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia",
        "Wisconsin", "Wyoming"],
}
UK_COUNTIES = ["SOMERSET", "CHESHIRE", "SURREY", "ESSEX", "KENT", "HAMPSHIRE", "YORKSHIRE",
               "LANCASHIRE", "DEVON", "CORNWALL", "DORSET", "BERKSHIRE", "BUCKINGHAMSHIRE",
               "HERTFORDSHIRE", "WARWICKSHIRE", "STAFFORDSHIRE", "NOTTINGHAMSHIRE", "MERSEYSIDE",
               "MIDDLESEX", "SUSSEX", "NORFOLK", "SUFFOLK", "WILTSHIRE", "GLOUCESTERSHIRE"]
REGION_NAMES = set(US_STATES) | set(AU_STATES) | set(UK_COUNTIES) | {
    s.upper() for s in ("Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware "
                        "Florida Georgia Hawaii Idaho Illinois Indiana Iowa Kansas Kentucky "
                        "Louisiana Maine Maryland Massachusetts Michigan Minnesota Mississippi "
                        "Missouri Montana Nebraska Nevada Ohio Oklahoma Oregon Pennsylvania "
                        "Tennessee Texas Utah Vermont Virginia Washington Wisconsin Wyoming "
                        "Victoria Queensland Tasmania").split()}

GAZ_LOOKUP = {}
for _cc, _names in GAZ.items():
    for _n in _names:
        GAZ_LOOKUP.setdefault(_n.lower(), []).append(_cc)
# a location word only counts when one of these cues sits on the same line
RE_CUE = re.compile(r"\U0001F4CD|\bloc(?:ated|ation|ations)\b|\bbased in\b|\bserving\b|\bnear\b|"
                    r"\battention\b|\bproviders? in\b|\btop provider\b|\bhere at\b|"
                    r"\bvisit us\b|\bclinic in\b|\bstudio in\b|\bhey\b|\bladies\b|\bwomen of\b|"
                    r"\bmen of\b|\barea\b|\bsurrounding\b|\bresidents\b|\bwelcome to\b|\bour\s+\w*\s*(?:clinic|practice|salon|spa)\b",
                    re.I)

# ---------------------------------------------------------------- advertiser_type cues
RE_TRAINING = re.compile(r"\b(academy|training (?:course|academy|provider|day)|masterclass|"
                         r"cpd|accredited course|foundation course|advanced course|become an? "
                         r"(?:injector|aesthetic)|train with (?:us|me)|student clinic|"
                         r"course dates|enrol|enroll now|our students|teach(?:ing)? clinicians)\b", re.I)
RE_PRODUCT = re.compile(r"\b(shop now|free (?:shipping|delivery)|add to (?:cart|bag)|our (?:products|range)|"
                        r"stockist|wholesale|buy (?:now|online)|use code|discount code|"
                        r"subscribe (?:and|&) save|bundle)\b", re.I)
# software / SaaS vendor: a platform, app or AI tool sold to a business (location is irrelevant)
RE_SOFTWARE = re.compile(r"\b(saas|software|platform|book a demo|request a demo|free demo|free trial|"
                         r"start (?:your )?free|integrat(?:es|ion) with|\bapi\b|ehr|emr|ai (?:scribe|"
                         r"assistant|agent|receptionist)|dashboard|hipaa[- ]compliant|soc ?2)\b", re.I)
# The CUE is case-insensitive; the PLACE NAME is not (re.I on the whole pattern makes [A-Z]
# match lowercase, which captured "Thame offers" as a town on the first pass).
RE_BASED_IN = re.compile(r"(?i:\b(?:based in|based at|located in|located at|situated in|clinic in|"
                         r"studio in|salon in|spa in|medspa in|med spa in|centre in|center in|"
                         r"lounge in|clinics? based|practice in|here in|serving|we are in|"
                         r"provider in|providers in|top providers? in))\s+"
                         r"([A-Z][A-Za-z'\-]{2,20}(?:\s+[A-Z][A-Za-z'\-]{2,20}){0,2})"
                         r"(?:\s*,\s*([A-Z][A-Za-z'\-]{2,20}))?")
RE_PIN_LINE = re.compile(r"\U0001F4CD\s*([^\n]{3,70})")
RE_SINGULAR = re.compile(r"\b(our clinic|the clinic|our studio|our salon|our practice|our spa|"
                         r"our med ?spa|our doors|our facility|our rooms|our team here|"
                         r"at our clinic|in[- ]clinic|book your appointment|visit us|"
                         r"come (?:and )?see us|our patients|our clients)\b", re.I)
RE_MULTISITE = re.compile(r"\b(all (?:our )?(?:clinics|locations|branches)|nearest clinic|"
                          r"clinics? (?:across|nationwide|throughout)|both (?:our )?clinics|"
                          r"our (?:other|second|new) (?:clinic|location|branch))\b", re.I)
RE_CHAINWORD = re.compile(r"\b(\d{1,3})\s+(?:clinics|locations|sites|centres|centers|studios|branches)\b", re.I)


# ---------------------------------------------------------------- small helpers
def today():
    return datetime.date.today()


def as_date(v):
    """Accept 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM:SS', an epoch int, or None."""
    if v in (None, "", 0):
        return None
    if isinstance(v, (int, float)):
        try:
            return datetime.datetime.utcfromtimestamp(int(v)).date()
        except (ValueError, OSError, OverflowError):
            return None
    s = str(v)[:10]
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def iso(d):
    return d.isoformat() if isinstance(d, datetime.date) else (d or None)


def body_text(snapshot):
    """The actor stores body either as a plain string or as {'text': ...}."""
    b = (snapshot or {}).get("body")
    if isinstance(b, dict):
        b = b.get("text")
    return b or ""


def all_text(snapshot):
    """Every human-visible string on the ad: body, title, link description, caption, cards."""
    s = snapshot or {}
    parts = [body_text(s), s.get("title"), s.get("link_description"), s.get("caption"),
             s.get("link_url"), s.get("byline")]
    for c in (s.get("cards") or []):
        parts += [c.get("body"), c.get("title"), c.get("link_description"), c.get("caption"),
                  c.get("link_url")]
    for t in (s.get("extra_texts") or []):
        parts.append(t.get("text") if isinstance(t, dict) else t)
    for lnk in (s.get("extra_links") or []):
        parts.append(lnk if isinstance(lnk, str) else json.dumps(lnk))
    return "\n".join(str(p) for p in parts if p)


def body_hash(snapshot):
    """Creative identity: the normalised body text. Two ad ids with the same hash on the same
    page are the same creative relaunched."""
    t = re.sub(r"\s+", " ", body_text(snapshot)).strip().lower()
    t = re.sub(r"\{\{[^}]*\}\}", "", t)          # dynamic-creative placeholders
    return hashlib.sha1(t.encode("utf-8")).hexdigest()[:16] if len(t) >= 25 else None


# ---------------------------------------------------------------- country
def country_from_copy(text):
    """(iso2, why) from the ad's own words. Highest-precision signal first. None if silent."""
    if not text:
        return None, None
    m = RE_TLD.search(text)
    if m:
        tld = (m.group(1) or m.group(2) or "").lower().lstrip(".")
        for k, v in TLD_COUNTRY.items():
            if k.lstrip(".") == tld:
                return v, "tld:" + tld
    m = RE_DIAL.search(text)
    if m and m.group(1) != "1":
        return DIAL_COUNTRY[m.group(1)], "dial:+" + m.group(1)
    if RE_US_ADDR.search(text):
        return "US", "us_address"
    if RE_AU_ADDR.search(text):
        return "AU", "au_address"
    if RE_UK_POST.search(text) and ("£" in text or RE_UK_PHONE.search(text) or " UK" in text):
        return "GB", "uk_postcode"
    if m and m.group(1) == "1":
        return "US", "dial:+1"
    if RE_NANP.search(text):
        return "US", "nanp_phone"
    if "£" in text and RE_UK_POST.search(text):
        return "GB", "gbp+postcode"
    return None, None


def country_of(text, country_field=None, search_cc=None, batch_market=None, advertiser_text=None):
    """(country_iso, country_basis, why). Order: the ad's own country field > the country of the
    SEARCH that returned it > the ad's own copy > the per-batch label typed at ingest.
    `text` is everything human-visible on the ad (see all_text)."""
    if country_field:
        return str(country_field).upper(), "ad_field", "snapshot.country_iso_code"
    if search_cc:
        return str(search_cc).upper(), "search", "country of the Ads Library search"
    cc, why = country_from_copy(text)
    if cc:
        return cc, "ad_copy", why
    cc, why = country_from_copy(advertiser_text or "")
    if cc:
        return cc, "advertiser_copy", why + " (in another ad by the same advertiser)"
    if batch_market:
        return {"UK": "GB"}.get(batch_market.upper(), batch_market.upper()), "batch_label", "the --market label typed at ingest"
    return None, "none", None


# ---------------------------------------------------------------- locations
def locations_from_text(text):
    """Towns and cities named in an advertiser's own ads. Address patterns first (exact), then a
    gazetteer name that shares a line with a location cue. Returns [(name, region, cc, how)]."""
    out, seen = [], set()

    def add(name, region, cc, how):
        name = re.sub(r"\s+", " ", (name or "").strip(" .,-"))
        if not name or len(name) < 3 or name.lower() in seen:
            return
        seen.add(name.lower())
        out.append({"name": name, "region": region, "country_iso": cc, "basis": how})

    for m in RE_US_ADDR.finditer(text or ""):
        add(m.group(1), m.group(2), "US", "us_address")
    for m in RE_AU_ADDR.finditer(text or ""):
        add(m.group(1), m.group(2), "AU", "au_address")
    # "NY: SoHo - Brooklyn - Midtown" location lists
    for m in re.finditer(r"\b(" + "|".join(US_STATES) + r"):\s*([A-Z][A-Za-z .'\-]+(?:\s*[-–]\s*[A-Z][A-Za-z .'\-]+)*)",
                         text or ""):
        for piece in re.split(r"\s*[-–]\s*", m.group(2)):
            add(piece, m.group(1), "US", "location_list")
    for m in RE_BASED_IN.finditer(text or ""):
        second = (m.group(2) or "").strip()
        region = second if second.upper() in REGION_NAMES else None
        add(m.group(1), region, None, "based_in_phrase")
        if second and (region or second.lower() in GAZ_LOOKUP):
            add(second, None, None, "based_in_phrase")
    for line in (text or "").splitlines():
        if not RE_CUE.search(line):
            continue
        low = line.lower()
        for name, ccs in GAZ_LOOKUP.items():
            if len(name) < 4:
                continue
            if re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", low):
                add(name.title(), None, ccs[0] if len(ccs) == 1 else None, "gazetteer+cue")
    for m in RE_PIN_LINE.finditer(text or ""):
        line = m.group(1)
        for name, ccs in GAZ_LOOKUP.items():
            if len(name) >= 4 and re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", line.lower()):
                add(name.title(), None, ccs[0] if len(ccs) == 1 else None, "pin_line")
    # a UK town sitting on the line before a postcode
    for m in RE_UK_POST.finditer(text or ""):
        pre = (text or "")[max(0, m.start() - 90):m.start()]
        seg = re.split(r"[\n,]", pre)
        cand = [s.strip() for s in seg if s.strip()]
        if cand and re.match(r"^[A-Z][A-Za-z .'\-]{2,28}$", cand[-1]):
            add(cand[-1], m.group(1), "GB", "uk_postcode_line")
    return out


def classify_advertiser(page_name, page_categories, texts):
    """(advertiser_type, why). Evidence = the advertiser's page name, page categories and the
    text of EVERY ad of theirs in the corpus. Order matters: a training academy also sells
    treatments, and a product brand also names a city."""
    blob = "\n".join(t for t in texts if t)
    name = page_name or ""
    cats = " ".join(page_categories or [])
    locs = locations_from_text(blob)
    names = sorted({l["name"] for l in locs})
    for gname, _ccs in GAZ_LOOKUP.items():
        if len(gname) >= 5 and re.search(r"(?<![a-z])" + re.escape(gname) + r"(?![a-z])", name.lower()):
            t = gname.title()
            if t not in names:
                names = sorted(names + [t])
    if len(set(m.group(0).lower() for m in RE_SOFTWARE.finditer(blob))) >= 2:
        return "software_vendor", "two or more software/SaaS signals in their ads", names
    if RE_TRAINING.search(blob) or RE_TRAINING.search(name):
        return "training_provider", f"training language in copy/name ({len(names)} locations)", names
    if RE_PRODUCT.search(blob) and not names:
        return "product_brand", "ecommerce language, no address in any ad", names
    m = RE_CHAINWORD.search(blob)
    if m and int(m.group(1)) >= 5:
        return "chain", f"copy states {m.group(1)} locations", names
    if len(names) >= 5:
        return "chain", f"{len(names)} distinct locations named across their ads", names
    if len(names) >= 2:
        return "multi_site", f"{len(names)} locations named across their ads", names
    if len(names) == 1:
        return "single_site", f"one location named ({names[0]})", names
    if re.search(r"\b(clinics|group|centres|centers)\b", name, re.I) or RE_MULTISITE.search(blob):
        return "chain", "plural page name or multi-location language, but no address found", names
    if RE_SINGULAR.search(blob):
        return "single_site", "singular clinic language and no second location named anywhere in their ads", names
    return "unknown", "no address, location list, singular-clinic or ecommerce signal in any of their ads", names


# ---------------------------------------------------------------- performance proxy
W_SURVIVAL, W_ACTIVE, W_VARIANT, W_PLATFORM, W_RELAUNCH, W_ADVERTISER = 40, 15, 15, 10, 10, 10
SURVIVAL_CAP_DAYS = 730
VARIANT_CAP = 16
PLATFORM_CAP = 5
RELAUNCH_CAP = 3
ADS_LIVE_CAP = 8


def performance(survival_days, is_active, variant_count, platforms, relaunch_count, ads_live):
    """0-100 proxy built ONLY from what Meta publishes for a commercial ad. It is NOT spend and
    NOT impressions: Meta publishes neither for commercial ads (see references/SCHEMA.md)."""
    if survival_days is None:
        return None, "no Ad Library record (start_date unknown), so no survival evidence"
    s = min(1.0, math.log10(1 + max(0, survival_days)) / math.log10(1 + SURVIVAL_CAP_DAYS)) * W_SURVIVAL
    a = W_ACTIVE if is_active else 0.0
    v = min(1.0, math.log2(1 + max(0, (variant_count or 1) - 1)) / math.log2(VARIANT_CAP)) * W_VARIANT
    p = min(1.0, len(platforms or []) / PLATFORM_CAP) * W_PLATFORM
    r = min(1.0, (relaunch_count or 0) / RELAUNCH_CAP) * W_RELAUNCH
    d = min(1.0, math.log2(1 + max(0, (ads_live or 1) - 1)) / math.log2(ADS_LIVE_CAP)) * W_ADVERTISER
    total = round(s + a + v + p + r + d)
    basis = (f"survival {s:.0f}/{W_SURVIVAL} ({survival_days}d) · "
             f"active {a:.0f}/{W_ACTIVE} · variants {v:.0f}/{W_VARIANT} ({variant_count or 1}) · "
             f"platforms {p:.0f}/{W_PLATFORM} ({len(platforms or [])}) · "
             f"relaunch {r:.0f}/{W_RELAUNCH} ({relaunch_count or 0}) · "
             f"advertiser {d:.0f}/{W_ADVERTISER} ({ads_live or 1} live ads seen)")
    return total, basis


def recompute_days(row, ref=None):
    """days_running is NEVER stored stale: start_date -> (end_date if ended, else today)."""
    ref = ref or today()
    s = as_date(row.get("start_date") or row.get("start"))
    if not s:
        return None
    e = as_date(row.get("end_date")) if not row.get("is_active") else None
    return max(0, ((e or ref) - s).days)


def note_append(row, msg):
    if not msg:
        return
    cur = row.get("notes") or ""
    if msg in cur:
        return
    row["notes"] = (cur + "; " if cur else "") + msg


# ---------------------------------------------------------------- SCHEMA v2 field list
V2_FIELDS = [
    # delivery and survival
    "first_seen", "last_seen", "is_active", "end_date", "days_running",
    "survival_days_at_last_check", "variant_count", "platforms", "advertiser_ads_live",
    "relaunch_of", "relaunch_count", "status_history",
    # advertiser and geography
    "page_id", "page_name", "page_categories", "advertiser_type", "advertiser_type_basis",
    "locations_named", "city", "region", "country_iso", "country_basis", "country_why", "currency",
    # extra Ads Library signals that are actually populated
    "start_date", "ad_library_url", "display_format", "page_like_count",
    "market_label_at_ingest",
    "contains_digital_created_media", "gated_type", "ad_categories",
    # computed performance proxy
    "performance_score", "performance_basis",
]
NO_LIBRARY_NOTE = ("no Meta Ad Library record for this ad id (own-client creative supplied "
                   "direct), so delivery, geography and performance signals cannot be derived")


def _dedupe_observations(obs):
    """One status_history entry per DATE. Several scrape files can see the same ad on the same
    day (a per-query file and the merged unique file); that is one observation, not two."""
    by = {}
    for o in obs:
        d = o["date"]
        if d not in by:
            by[d] = {"date": d, "is_active": bool(o.get("is_active"))}
        else:
            by[d]["is_active"] = by[d]["is_active"] or bool(o.get("is_active"))
    return [by[d] for d in sorted(by)]


def enrich_row(row, idx, ref=None):
    """Fill every SCHEMA v2 field on one index row from the raw observation index (raw_scan.py).
    Deterministic. Returns the row. Fields it cannot derive stay None and say why in `notes`."""
    ref = ref or today()
    raw = (idx.get("ads") or {}).get(str(row.get("ad_id") or ""))
    pages = idx.get("pages") or {}
    creatives = idx.get("creatives") or {}

    if not raw:
        for f in V2_FIELDS:
            row.setdefault(f, None)
        row["platforms"] = row.get("platforms") or []
        row["page_categories"] = row.get("page_categories") or []
        row["locations_named"] = row.get("locations_named") or []
        row["ad_categories"] = row.get("ad_categories") or []
        row["status_history"] = row.get("status_history") or []
        row["advertiser_type"] = row.get("advertiser_type") or "unknown"
        row["advertiser_type_basis"] = row.get("advertiser_type_basis") or NO_LIBRARY_NOTE
        row["first_seen"] = row.get("first_seen") or row.get("date")
        row["last_seen"] = row.get("last_seen") or row.get("date")
        row["country_iso"], row["country_basis"], row["country_why"] = country_of(
            (row.get("body_excerpt") or "") + "\n" + (row.get("hook") or ""),
            None, None, row.get("market"))
        row["performance_score"], row["performance_basis"] = None, NO_LIBRARY_NOTE
        if row.get("market_label_at_ingest") is None:
            row["market_label_at_ingest"] = row.get("market")
        if row.get("country_iso"):
            row["market"] = row["country_iso"]
        note_append(row, NO_LIBRARY_NOTE)
        return row

    obs = _dedupe_observations(raw.get("observations") or [])
    dates = [o["date"] for o in obs] or ([row.get("date")] if row.get("date") else [])
    # first_seen only ever moves EARLIER, last_seen only ever moves LATER, and both keep the
    # value already stored on the row: the scan reaches back only as far as the scrape files
    # still on disk. A status_history entry written by the death path means the ad was NOT seen,
    # so history dates never feed last_seen.
    hist = [e.get("date") for e in (row.get("status_history") or []) if e.get("date")]
    first_seen = min([d for d in dates + hist + [row.get("first_seen"), row.get("date")] if d] or [None])
    last_seen = max([d for d in dates + [row.get("last_seen")] if d]
                    or [row.get("date")] or [None])
    is_active = obs[-1]["is_active"] if obs else bool(raw.get("is_active"))

    start = as_date(raw.get("start_date"))
    end = as_date(raw.get("end_date_raw"))
    # For a LIVE ad this actor reports end_date = the day of the scrape, not a real end date.
    end_date = iso(end) if (not is_active and end) else None

    row["start_date"] = iso(start)
    row["start"] = row.get("start") or iso(start)
    row["is_active"] = is_active
    row["end_date"] = end_date
    row["first_seen"] = first_seen
    row["last_seen"] = last_seen
    # APPEND, never replace: pruned scrape files fall out of the scan, the row must not forget
    row["status_history"] = merge_status_history(row.get("status_history"), obs)
    row["days_running"] = recompute_days(row, ref)
    ls = as_date(last_seen)
    row["survival_days_at_last_check"] = (max(0, ((as_date(end_date) or ls) - start).days)
                                          if start and (ls or end_date) else None)
    row["variant_count"] = raw.get("collation_count") or 1
    row["platforms"] = raw.get("platforms") or []
    row["currency"] = (raw.get("currency") or None)
    row["gated_type"] = raw.get("gated_type")
    row["ad_categories"] = [c for c in (raw.get("categories") or []) if c and c != "UNKNOWN"]
    row["contains_digital_created_media"] = raw.get("contains_digital_created_media")
    row["display_format"] = raw.get("display_format")
    row["ad_library_url"] = raw.get("ad_library_url") or row.get("lib_url")
    row["lib_url"] = row.get("lib_url") or row["ad_library_url"]
    row["page_like_count"] = raw.get("page_like_count")

    pid = raw.get("page_id")
    pg = pages.get(pid or "", {})
    row["page_id"] = pid
    row["page_name"] = raw.get("page_name") or pg.get("page_name")
    row["page_categories"] = raw.get("page_categories") or pg.get("page_categories") or []
    row["advertiser"] = row.get("advertiser") or row["page_name"]
    row["advertiser_type"] = pg.get("advertiser_type") or "unknown"
    row["advertiser_type_basis"] = pg.get("advertiser_type_basis")
    row["locations_named"] = list(pg.get("locations_named") or [])   # plain town/city strings
    row["advertiser_ads_live"] = max(int(raw.get("ads_count") or 0), int(pg.get("ads_live_seen") or 0)) or None

    # relaunch: the same creative body on the same page under a different ad id
    bh = raw.get("body_hash")
    sibs = creatives.get(f"{pid}|{bh}", []) if (pid and bh) else []
    others = [s for s in sibs if s[0] != str(row.get("ad_id"))]
    row["relaunch_count"] = len(others)
    earlier = [s for s in others if (s[1] or "9999") < (iso(start) or "0000")]
    row["relaunch_of"] = earlier[0][0] if earlier else None

    # geography, per ad
    text = raw.get("text") or raw.get("body") or ""
    row["country_iso"], row["country_basis"], row["country_why"] = country_of(
        text, raw.get("country_iso_code"), raw.get("search_cc"), row.get("market"),
        advertiser_text=pg.get("text_blob"))
    own = locations_from_text(text)
    adv = row["locations_named"]
    if own:
        row["city"], row["region"] = own[0]["name"], own[0].get("region")
    elif len(adv) == 1:
        row["city"], row["region"] = adv[0], None
    else:
        row["city"], row["region"] = None, None

    row["performance_score"], row["performance_basis"] = performance(
        row["survival_days_at_last_check"], is_active, row["variant_count"],
        row["platforms"], row["relaunch_count"], row["advertiser_ads_live"])

    if row.get("market_label_at_ingest") is None:
        row["market_label_at_ingest"] = row.get("market")
    if row.get("country_iso"):
        row["market"] = row["country_iso"]

    if row["country_basis"] == "batch_label":
        note_append(row, "country_iso falls back to the per-batch --market label: this scrape "
                         "carried no search country and the ad copy names no country")
    if not row["city"]:
        note_append(row, "city null: no address, postcode or cue-anchored place name in this "
                         "advertiser's ad copy")
    return row



# ---------------------------------------------------------------- safe writes and locking
@contextlib.contextmanager
def index_lock(lib=LIB_DEFAULT, timeout=300):  # POSIX only (fcntl): macOS, Linux, WSL
    """Exclusive lock around any read-modify-write of index.jsonl. refresh.py, backfill_v2.py and
    merge_tags.py all rewrite the whole file; without this, whichever finishes last silently
    discards the other's work (the weekly cron and a hand-run merge can absolutely overlap)."""
    ensure_library(lib)
    path = os.path.join(lib, ".index.lock")
    f = open(path, "w")
    t0 = datetime.datetime.now()
    while True:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if (datetime.datetime.now() - t0).total_seconds() > timeout:
                f.close()
                raise SystemExit(f"another ad-library job holds {path}; try again when it finishes")
            import time as _t
            _t.sleep(1)
    try:
        yield
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()


def write_atomic(path, text_or_bytes, keep_bak=True):
    """Write via a temp file in the same directory + os.replace, so an interruption can never
    leave a truncated source-of-truth file. Keeps one .bak of the previous version."""
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    if keep_bak and os.path.exists(path):
        shutil.copy2(path, path + ".bak")
    mode = "wb" if isinstance(text_or_bytes, bytes) else "w"
    kw = {} if mode == "wb" else {"encoding": "utf-8"}
    fd, tmp = tempfile.mkstemp(dir=d, prefix=os.path.basename(path) + ".", suffix=".tmp")
    os.close(fd)
    try:
        with open(tmp, mode, **kw) as f:
            f.write(text_or_bytes)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_index(rows, lib=LIB_DEFAULT):
    """The ONLY way index.jsonl should ever be written."""
    path = os.path.join(lib, "index.jsonl")
    write_atomic(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return path


def merge_status_history(old, new):
    """Union two status histories, one entry per date, newest evidence winning. The raw
    observation index only reaches back as far as the scrape files still on disk (the refresh
    keeps 12 weeks), so the ROW is the durable record of an ad's status over time, not the scan."""
    by = {}
    for e in list(old or []) + list(new or []):
        d = (e or {}).get("date")
        if d:
            by[d] = {"date": d, "is_active": bool(e.get("is_active"))}
    return [by[d] for d in sorted(by)]
