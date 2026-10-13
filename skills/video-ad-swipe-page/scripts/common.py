"""Shared helpers for the video-ad-swipe-page scripts.

No tokens live in code. The Apify token is read from the environment only:
  $APIFY_TOKEN (or $APIFY_API_TOKEN). Load it first with
  set -a; source ~/.claude/skills/.env; set +a
"""
import json
import os
import re
import ssl
import sys
import urllib.request
import urllib.parse

HOME = os.path.expanduser("~")

# Public Apify actor for the Meta (Facebook) Ads Library. Pay per ad returned.
ACTOR = "curious_coder~facebook-ads-library-scraper"
ACTOR_ID = "XtaWFhbtfxyzqrFmd"
FALLBACK_PRICE_PER_AD = 0.00075  # USD, PAY_PER_EVENT "ad" (live price is fetched from /v2/acts at run time)
BUDGET_DEFAULT = 10.0
HARD_CAP = 25.0  # never exceed without the budget owner's explicit yes

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


def ssl_ctx():
    """macOS python often lacks CA certs. export SSL_CERT_FILE=$(python3 -m certifi)
    before ANY urllib job, or the run fires 0 of N and still looks like success."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        cf = os.environ.get("SSL_CERT_FILE")
        if cf and os.path.exists(cf):
            return ssl.create_default_context(cafile=cf)
        return ssl.create_default_context()


CTX = ssl_ctx()


def apify_token(required=True):
    tok = os.environ.get("APIFY_TOKEN") or os.environ.get("APIFY_API_TOKEN")
    if not tok and required:
        sys.exit("No Apify token found. Add APIFY_TOKEN to ~/.claude/skills/.env, then run: "
                 "set -a; source ~/.claude/skills/.env; set +a")
    return tok


def api(path, token=None, data=None, method=None, timeout=120):
    """Small JSON client for api.apify.com. Never logs the token."""
    token = token or apify_token()
    sep = "&" if "?" in path else "?"
    url = f"https://api.apify.com/v2/{path}{sep}token={token}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"Content-Type": "application/json", **UA})
    with urllib.request.urlopen(req, context=CTX, timeout=timeout) as r:
        return json.load(r)


def actor_price(token=None):
    """Live per-ad price from the actor's pricingInfos (last PAY_PER_EVENT or PRICE_PER_DATASET_ITEM)."""
    try:
        d = api(f"acts/{ACTOR}", token=token)["data"]
    except Exception as e:  # noqa: BLE001
        print(f"  (could not fetch live price: {e}; using fallback ${FALLBACK_PRICE_PER_AD})", file=sys.stderr)
        return FALLBACK_PRICE_PER_AD, "fallback"
    price = None
    for p in d.get("pricingInfos") or []:
        if p.get("pricingModel") == "PAY_PER_EVENT":
            ev = (p.get("pricingPerEvent") or {}).get("actorChargeEvents") or {}
            for _, v in ev.items():
                if v.get("isPrimaryEvent") or price is None:
                    price = v.get("eventPriceUsd")
        elif p.get("pricingModel") == "PRICE_PER_DATASET_ITEM" and price is None:
            price = p.get("pricePerUnitUsd")
    return (price or FALLBACK_PRICE_PER_AD), ("live" if price else "fallback")


def ads_library_url(term, country, active_only=True, media="video"):
    """Exact-phrase Ads Library search URL. media: video | all | image."""
    status = "active" if active_only else "all"
    return ("https://www.facebook.com/ads/library/?active_status=%s&ad_type=all&country=%s&q=%s"
            "&search_type=keyword_exact_phrase&media_type=%s"
            % (status, country, urllib.parse.quote(term), media))


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj, indent=1):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=indent, ensure_ascii=False)


def workdir(client, sub=None):
    """Per-client work dir: $SWIPE_OUTPUT_DIR or ./video-ad-swipe-page-output/<slug>/video-swipe-<YYYYmmdd>/
    (under the current directory; never a temp dir that the OS may wipe mid-session)."""
    import datetime
    base = os.environ.get("SWIPE_OUTPUT_DIR") or os.path.join(os.getcwd(), "video-ad-swipe-page-output")
    d = os.path.join(base, client, sub or f"video-swipe-{datetime.date.today():%Y%m%d}")
    os.makedirs(d, exist_ok=True)
    return d


def which(cmd):
    from shutil import which as _w
    p = _w(cmd)
    if p:
        return p
    for cand in (os.path.join(HOME, "Library/Python/3.11/bin", cmd),
                 os.path.join(HOME, "Library/Python/3.12/bin", cmd),
                 "/usr/local/bin/" + cmd, "/opt/homebrew/bin/" + cmd):
        if os.path.exists(cand):
            return cand
    return None
