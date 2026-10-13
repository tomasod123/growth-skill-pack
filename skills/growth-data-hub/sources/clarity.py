"""Microsoft Clarity Data Export API (project-live-insights): sessions, scroll depth, dead clicks,
rage clicks and quick backs, by URL.

Limits that shape this module:
  * only the last 1, 2 or 3 days (numOfDays), whatever --days says
  * about 10 calls per project per day, 1,000 rows max, no pagination
So hub.py makes ONE call (dimension1=URL) and caches the answer for the day in cache/.
Auth: a project API token (Settings > Data Export > Generate new API token), sent as a Bearer token.
"""
import datetime as dt
import json
import os

from .common import SourceError, dig, http, num

NAME = "clarity"
URL = "https://www.clarity.ms/export-data/api/v1/project-live-insights"


def missing(cfg, env):
    return [] if env.get("CLARITY_API_TOKEN") else ["CLARITY_API_TOKEN in .env"]


def fetch(cfg, env, start, end, cache_dir=None, refresh=False):
    days = int(dig(cfg, "clarity", "num_days", default=3))
    days = min(max(days, 1), 3)
    cache = os.path.join(cache_dir, f"clarity-{dt.date.today().isoformat()}-{days}d.json") if cache_dir else None
    if cache and os.path.exists(cache) and not refresh:
        with open(cache) as f:
            return json.load(f)
    try:
        d = http("GET", URL, params={"numOfDays": days, "dimension1": "URL"}, retries=0,  # every retry spends one of ~10 daily calls
                 headers={"Authorization": f"Bearer {env['CLARITY_API_TOKEN']}", "Content-Type": "application/json"})
    except SourceError as e:
        if "429" in str(e):
            raise SourceError("Clarity daily limit reached (about 10 calls per project per day). "
                              "Try again tomorrow; today's cached answer is reused automatically when it exists.")
        raise
    raw = {"num_days": days, "metrics": d}
    if cache:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache, "w") as f:
            json.dump(raw, f)
    return raw


def _key(name):
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def _url(info):
    for k, v in info.items():
        if k.lower() == "url":
            return v
    return None


def _path(u):
    """https://www.example.com/book?x=1 -> /book  (GA4 landing pages are paths)."""
    if not u:
        return ""
    s = u.split("://", 1)[-1]
    s = "/" + s.split("/", 1)[1] if "/" in s else "/"
    s = s.split("?", 1)[0].split("#", 1)[0]
    return s.rstrip("/") or "/"


# metricName (normalised) -> which field holds the per-URL value
PCT_METRICS = {"deadclickcount": "dead_click_pct", "rageclickcount": "rage_click_pct",
               "quickbackclick": "quickback_pct", "excessivescroll": "excessive_scroll_pct",
               "errorclickcount": "error_click_pct", "scripterrorcount": "script_error_pct"}


def parse(raw, cfg, start, end):
    pages = {}
    for block in raw.get("metrics") or []:
        mname = _key(block.get("metricName"))
        for info in block.get("information") or []:
            u = _url(info)
            if not u:
                continue
            p = pages.setdefault(_path(u), {"path": _path(u), "url": u, "sessions": 0, "bot_sessions": 0})
            if mname == "traffic":
                p["sessions"] += int(num(info.get("totalSessionCount")))
                p["bot_sessions"] += int(num(info.get("totalBotSessionCount")))
            elif mname == "scrolldepth":
                p["scroll_depth"] = num(info.get("averageScrollDepth"), None)
            elif mname == "engagementtime":
                p["active_time_s"] = num(info.get("activeTime"), None)
            elif mname in PCT_METRICS:
                # percentage of sessions on that URL with at least one such event
                p[PCT_METRICS[mname]] = num(info.get("sessionsWithMetricPercentage"), None)
    rows = sorted(pages.values(), key=lambda r: -r["sessions"])
    return {"num_days": raw.get("num_days", 3), "pages": rows,
            "totals": {"sessions": sum(r["sessions"] for r in rows)}}
