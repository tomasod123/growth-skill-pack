"""GoHighLevel (LeadConnector) API v2: contacts created, opportunities by pipeline stage, appointments
booked / showed / no-show, by source and tag, for the window.

Auth: a Private Integration Token for the sub-account (GHL_PRIVATE_TOKEN) plus its location id.
Gotchas kept from production use:
  * POST /contacts/search needs a NUMERIC pageLimit; without it the call can 422 or come back empty.
  * Some endpoints sit behind a CDN that rejects library user agents, so we send a browser one.
  * GHL merges contacts on email and phone: a repeat enquiry updates the old contact and keeps its
    original dateAdded, so CRM 'new contacts' can be lower than the ad platform's lead count.
  * Burst limit is 100 requests per 10 seconds per location; we pace at ~8 a second.
"""
import sys
import time
import urllib.parse

from .common import BROWSER_UA, SourceError, dig, http

NAME = "ghl"
BASE = "https://services.leadconnectorhq.com"
MAX_PAGES = 100


class Client:
    def __init__(self, token, location):
        self.loc = location
        self.h = {"Authorization": f"Bearer {token}", "Version": "2021-07-28", "Accept": "application/json",
                  "Content-Type": "application/json", "User-Agent": BROWSER_UA}
        self._last = 0.0
        self.warnings = []

    def req(self, method, path, body=None, version=None):
        wait = self._last + 0.125 - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        h = dict(self.h, Version=version) if version else self.h
        return http(method, BASE + path, headers=h, json_body=body)


def missing(cfg, env):
    out = [] if env.get("GHL_PRIVATE_TOKEN") else ["GHL_PRIVATE_TOKEN in .env"]
    loc = str(dig(cfg, "ghl", "location_id", default="") or "")
    if not loc or "YOUR" in loc:
        out.append("ghl.location_id in config.yaml")
    return out


def _contacts(g, start, end):
    out, page = [], 1
    while page <= MAX_PAGES:
        d = g.req("POST", "/contacts/search", {
            "locationId": g.loc, "pageLimit": 100, "page": page,  # pageLimit must be a number
            "filters": [{"field": "dateAdded", "operator": "range",
                         "value": {"gte": f"{start}T00:00:00Z", "lte": f"{end}T23:59:59Z"}}],
            "sort": [{"field": "dateAdded", "direction": "desc"}]})
        cs = d.get("contacts") or []
        out += cs
        total = d.get("total") or d.get("count") or 0
        # GHL can keep returning full pages past the end, so also stop at the reported total
        if len(cs) < 100 or (total and len(out) >= total):
            break
        page += 1
    else:
        g.warnings.append(f"stopped at {MAX_PAGES * 100} contacts (page search limit); use a shorter --days")
    return list({c.get("id"): c for c in out}.values())


def _opportunities(g, pipeline_id):
    out, page = [], 1
    while page <= MAX_PAGES:
        q = urllib.parse.urlencode({"location_id": g.loc, "pipeline_id": pipeline_id, "limit": 100, "page": page})
        d = g.req("GET", "/opportunities/search?" + q)
        ops = d.get("opportunities") or []
        out += ops
        total = dig(d, "meta", "total", default=0)
        if len(ops) < 100 or (total and len(out) >= total):
            break
        page += 1
    return out


def _ms(day, end_of_day=False):
    import datetime as dt
    d = dt.datetime.fromisoformat(day + ("T23:59:59" if end_of_day else "T00:00:00")).replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp() * 1000)


def fetch(cfg, env, start, end):
    import datetime as dt
    g = Client(env["GHL_PRIVATE_TOKEN"], dig(cfg, "ghl", "location_id"))
    raw = {"contacts": _contacts(g, start, end), "pipelines": [], "opportunities": [], "calendars": [], "events": []}
    pipes = g.req("GET", "/opportunities/pipelines?locationId=" + g.loc).get("pipelines") or []
    wanted = [p.lower() for p in (dig(cfg, "ghl", "pipelines", default=[]) or [])]
    raw["pipelines"] = [p for p in pipes if not wanted or (p.get("name") or "").lower() in wanted]
    print(f"    ghl: {len(raw['contacts'])} contacts; reading {len(raw['pipelines'])} pipeline(s) and calendars ...",
          file=sys.stderr, flush=True)
    for p in raw["pipelines"]:
        raw["opportunities"] += _opportunities(g, p["id"])
    # Appointments: from the window start to N days after it ends, so calls booked late in the window count.
    ahead = int(dig(cfg, "ghl", "appointments_days_ahead", default=21))
    ev_end = (dt.date.fromisoformat(end) + dt.timedelta(days=ahead)).isoformat()
    try:
        cals = g.req("GET", "/calendars/?locationId=" + g.loc, version="2021-04-15").get("calendars") or []
        wanted_c = [c.lower() for c in (dig(cfg, "ghl", "calendars", default=[]) or [])]
        raw["calendars"] = [c for c in cals if not wanted_c or (c.get("name") or "").lower() in wanted_c]
        for c in raw["calendars"]:
            q = urllib.parse.urlencode({"locationId": g.loc, "calendarId": c["id"],
                                        "startTime": _ms(start), "endTime": _ms(ev_end, True)})
            evs = g.req("GET", "/calendars/events?" + q, version="2021-04-15").get("events") or []
            raw["events"] += [dict(e, calendarName=c.get("name")) for e in evs]
    except SourceError as e:
        raw["events"] = []
        g.warnings.append("appointments skipped (token needs calendars.readonly and calendars/events.readonly): "
                          + str(e).split(" -> FIX")[0][:120])
    raw["warnings"] = g.warnings
    return raw


def _stage_kind(stage_name, status, stages_cfg):
    """Map a pipeline stage name (and opportunity status) to booked / showed / no_show / won / lost / None."""
    n = (stage_name or "").strip().lower()
    if (status or "").lower() == "won":
        return "won"
    for kind in ("won", "showed", "no_show", "booked", "lost"):
        if n in [s.lower() for s in (stages_cfg.get(kind) or [])]:
            return kind
    if (status or "").lower() == "lost":
        return "lost"
    return None


def _attribution(c):
    """First-touch attribution. Contacts carry either attributionSource (a dict) or attributions (a list,
    one per touch, first touch flagged isFirst), depending on endpoint and account age; accept both."""
    if c.get("attributionSource"):
        return c["attributionSource"]
    touches = [t for t in (c.get("attributions") or []) if isinstance(t, dict)]
    return next((t for t in touches if t.get("isFirst")), touches[0] if touches else {}) or {}


def parse(raw, cfg, start, end):
    stages_cfg = dig(cfg, "ghl", "stages", default={}) or {}
    stage_names = {}
    for p in raw.get("pipelines", []):
        for s in p.get("stages") or []:
            stage_names[s.get("id")] = (p.get("name"), s.get("name"))

    contacts, dropped = [], 0
    for c in raw.get("contacts", []):
        added = (c.get("dateAdded") or "")[:10]
        if added and not (start <= added <= end):
            dropped += 1
            continue
        a = _attribution(c)
        contacts.append({
            "id": c.get("id"), "date": added, "source": c.get("source") or "",
            "tags": [t.lower() for t in (c.get("tags") or [])],
            "utm_source": (a.get("utmSource") or "").lower(), "utm_medium": (a.get("utmMedium") or "").lower(),
            "utm_campaign": a.get("utmCampaign") or a.get("campaign") or "",
            "session_source": (a.get("sessionSource") or a.get("utmSessionSource") or "").lower(), "medium": (a.get("medium") or "").lower(),
            "url": a.get("url") or "", "fbclid": bool(a.get("fbclid")), "gclid": bool(a.get("gclid")),
        })

    opps = []
    for o in raw.get("opportunities", []):
        pipe, stage = stage_names.get(o.get("pipelineStageId"), (None, None))
        opps.append({"contact_id": o.get("contactId") or dig(o, "contact", "id"), "pipeline": pipe, "stage": stage,
                     "status": o.get("status"), "kind": _stage_kind(stage, o.get("status"), stages_cfg),
                     "value": o.get("monetaryValue") or 0})

    appts = []
    for e in raw.get("events", []):
        st = (e.get("appointmentStatus") or e.get("status") or "").lower()
        if st in ("cancelled", "invalid"):
            continue
        appts.append({"contact_id": e.get("contactId"), "start": str(e.get("startTime") or "")[:16],
                      "status": st, "calendar": e.get("calendarName") or ""})

    stage_counts = {}
    ids = {c["id"] for c in contacts}
    for o in opps:
        if o["contact_id"] in ids:
            key = f"{o['pipeline']} / {o['stage']}"
            stage_counts[key] = stage_counts.get(key, 0) + 1
    appt_counts = {}
    for a in appts:
        if start <= a["start"][:10] <= end:
            appt_counts[a["status"] or "unknown"] = appt_counts.get(a["status"] or "unknown", 0) + 1
    by_source, by_tag = {}, {}
    for c in contacts:
        by_source[c["source"] or "(none)"] = by_source.get(c["source"] or "(none)", 0) + 1
        for t in c["tags"]:
            by_tag[t] = by_tag.get(t, 0) + 1
    warnings = list(raw.get("warnings", []))
    if dropped > max(len(contacts), 50):
        warnings.append(f"the CRM returned {dropped} contacts outside the window (kept {len(contacts)}); "
                        "the date filter may not have applied, which only costs extra calls")
    if opps and not any(o["kind"] for o in opps):
        seen = sorted({o["stage"] for o in opps if o["stage"]})
        warnings.append("no pipeline stage matched ghl.stages in config.yaml, so booked/showed/won only come from "
                        "calendar appointments. Your stage names: " + ", ".join(seen[:15]))
    return {"contacts": contacts, "opportunities": opps, "appointments": appts,
            "totals": {"contacts": len(contacts), "opportunities": sum(stage_counts.values()),
                       "appointments_in_window": sum(appt_counts.values())},
            "by_stage": dict(sorted(stage_counts.items(), key=lambda kv: -kv[1])),
            "appointments_by_status": appt_counts,
            "by_source": dict(sorted(by_source.items(), key=lambda kv: -kv[1])[:20]),
            "by_tag": dict(sorted(by_tag.items(), key=lambda kv: -kv[1])[:20]),
            "warnings": warnings}
