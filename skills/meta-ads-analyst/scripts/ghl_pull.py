#!/usr/bin/env python3
"""
ghl_pull.py - Consolidated GoHighLevel pull for the meta-ads-analyst skill (live data mode).

Self-contained. Read-only (GET only). NEVER prints the token value.
LeadConnector v2, Version 2021-07-28. Env: GHL_API_KEY (Private Integration token), GHL_LOCATION_ID,
optional GHL_PIPELINE_ID. Load first:  set -a; source ~/.claude/skills/.env; set +a
REQUIRES a browser User-Agent (Cloudflare error 1010 on python-urllib otherwise) + certifi SSL.

Outputs ONE JSON object to stdout (and --out <path>):
  - pipeline: name + stages + stage_distribution (opp counts per stage)
  - bookings: last-7d appointments (via /contacts/{id}/appointments across pipeline contacts),
    booking count, booking rate vs recent (7d) opps
  - recent_leads: per recent (7d) lead {contact, utmContent ad name, adId, qualified / unqualified tag}
  - speed_to_lead: first outbound touch + first TYPE_CALL for booked/recent contacts (minutes)
  - conversation_samples: 3-5 message threads (channel, direction, is_call, body)

Usage:
  python3 ghl_pull.py                        # prints JSON
  python3 ghl_pull.py --out ./meta-ads-analyst-output/ghl.json
  python3 ghl_pull.py --days 7               # recency window (default 7)
  python3 ghl_pull.py --list-pipelines       # print pipeline ids/names and exit
  python3 ghl_pull.py --qualified-tag "qualified" --unqualified-tag "disqualified" \
      --exclude-names "test,demo"            # how YOUR CRM marks lead quality, and test contacts to skip
"""
import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE = "https://services.leadconnectorhq.com"
LOC = os.environ.get("GHL_LOCATION_ID", "").strip()
PIPE = os.environ.get("GHL_PIPELINE_ID", "").strip()  # optional; --pipeline overrides; empty = first pipeline
VERSION = "2021-07-28"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
NOW = datetime.now(timezone.utc)

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()


TOKEN = os.environ.get("GHL_API_KEY", "").strip()

H = {
    "Authorization": f"Bearer {TOKEN}",
    "Version": VERSION,
    "Accept": "application/json",
    "User-Agent": _UA,
}
EP = []  # (endpoint, http) for verification


def get(path, params=None, version=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    h = dict(H)
    if version:
        h["Version"] = version
    req = urllib.request.Request(url, headers=h, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=45, context=_SSL_CTX) as r:
            EP.append((path.split("?")[0], 200))
            return 200, json.loads(r.read().decode(), strict=False)  # conversations search can return raw control chars
    except urllib.error.HTTPError as e:
        hint = None
        try:
            hint = e.read().decode()[:200]
        except Exception:
            pass
        EP.append((path.split("?")[0], e.code))
        return e.code, {"_hint": hint}
    except Exception as e:
        EP.append((path.split("?")[0], -1))
        return -1, {"_err": str(e)}


def iso(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        try:
            return datetime.fromtimestamp(int(s) / 1000, tz=timezone.utc)
        except Exception:
            return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        try:
            return datetime.fromtimestamp(int(s) / 1000, tz=timezone.utc)
        except Exception:
            return None


# TYPE_CALL detection: top-level `type` looks like SMS; the CALL marker is messageType/meta.
def is_call_msg(m):
    mt = str(m.get("messageType") or "")
    t = m.get("type")
    if mt == "TYPE_CALL":
        return True
    if t == 29:
        return True
    if "call" in mt.lower():
        return True
    meta = m.get("meta") or {}
    if isinstance(meta, dict) and meta.get("call"):
        return True
    return m.get("callDuration") is not None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    global PIPE
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--sample", type=int, default=4, help="conversation threads to include (3-5)")
    ap.add_argument("--pipeline", default=PIPE, help="pipeline id (default GHL_PIPELINE_ID, else the first pipeline)")
    ap.add_argument("--list-pipelines", action="store_true")
    ap.add_argument("--qualified-tag", default="qualified",
                    help="substring of the contact tag that marks a qualified lead (case-insensitive)")
    ap.add_argument("--unqualified-tag", default="unqualified",
                    help="substring of the tag that marks an unqualified lead (checked first)")
    ap.add_argument("--exclude-names", default="test",
                    help="comma list of name substrings to skip (test contacts, your own team)")
    args = ap.parse_args()
    if not TOKEN or not LOC:
        print(json.dumps({"FATAL": "GHL_API_KEY and GHL_LOCATION_ID must be set. Run: set -a; source ~/.claude/skills/.env; set +a"}))
        sys.exit(1)
    PIPE = args.pipeline
    EXCL = [x.strip().lower() for x in args.exclude_names.split(",") if x.strip()]
    SINCE = NOW - timedelta(days=args.days)
    OUT = {"meta": {"location": LOC, "pipeline": PIPE, "now_utc": NOW.isoformat(), "window_days": args.days}}

    # ---- 1) Pipeline stages + stage distribution ----
    STAGE_MAP = {}
    PIPE_NAME = None
    code, data = get("/opportunities/pipelines/", {"locationId": LOC})
    if code == 200:
        pls = data.get("pipelines", [])
        if args.list_pipelines:
            print(json.dumps([{"id": p.get("id"), "name": p.get("name")} for p in pls], indent=2))
            return
        if not PIPE and pls:
            PIPE = pls[0].get("id")
            OUT["meta"]["pipeline"] = PIPE
            OUT["meta"]["pipeline_note"] = "no pipeline given: used the first one; pass --pipeline to choose"
        for p in pls:
            if p.get("id") == PIPE:
                PIPE_NAME = p.get("name")
                STAGE_MAP = {s["id"]: s["name"] for s in p.get("stages", [])}
    OUT["pipeline"] = {"name": PIPE_NAME, "stages": list(STAGE_MAP.values())}

    # pull ALL opps in the pipeline (paged)
    opps = []
    page = 1
    while page < 60:
        code, data = get("/opportunities/search/", {"location_id": LOC, "pipeline_id": PIPE, "limit": 100, "page": page})
        if code != 200:
            break
        batch = data.get("opportunities", [])
        if not batch:
            break
        opps.extend(batch)
        m = data.get("meta", {}) or {}
        if m.get("nextPage"):
            page = m["nextPage"]
        else:
            break

    def opp_norm(o):
        sid = o.get("pipelineStageId") or o.get("stageId")
        cid = o.get("contactId") or (o.get("contact") or {}).get("id")
        return {
            "name": o.get("name"),
            "contactId": cid,
            "stage": STAGE_MAP.get(sid, sid),
            "createdDt": iso(o.get("createdAt") or o.get("dateAdded")),
            "status": o.get("status"),
        }

    nopps = [opp_norm(o) for o in opps]
    dist = {}
    for o in nopps:
        dist[o["stage"]] = dist.get(o["stage"], 0) + 1
    OUT["pipeline"]["total_opps"] = len(nopps)
    OUT["pipeline"]["stage_distribution"] = dict(sorted(dist.items(), key=lambda x: -x[1]))

    recent_opps = [o for o in nopps if o["createdDt"] and o["createdDt"] >= SINCE]
    OUT["recent_opps_count"] = len(recent_opps)

    # all contactIds in pipeline (for appt sweep) + recent ones (for lead detail)
    all_cids = []
    for o in nopps:
        if o["contactId"] and o["contactId"] not in all_cids:
            all_cids.append(o["contactId"])
    recent_cids = [o["contactId"] for o in recent_opps if o["contactId"]]

    # ---- 2) Bookings via /contacts/{id}/appointments across ALL pipeline contacts ----
    appts = []
    for cid in all_cids:
        code, data = get(f"/contacts/{cid}/appointments")
        if code != 200 or not isinstance(data, dict):
            continue
        events = data.get("events", data.get("appointments", [])) or []
        for e in events:
            appts.append(
                {
                    "contactId": cid,
                    "apptId": e.get("id"),
                    "title": e.get("title"),
                    "calendarId": e.get("calendarId"),
                    "status": e.get("appointmentStatus") or e.get("status") or e.get("appoinmentStatus"),
                    "startDt": iso(e.get("startTime")),
                    "bookedDt": iso(e.get("dateAdded") or e.get("createdAt")),
                    "source": e.get("source"),
                    "createdBy": e.get("createdBy"),
                }
            )
        time.sleep(0.02)

    booked_7d = [a for a in appts if a["bookedDt"] and a["bookedDt"] >= SINCE]
    status_dist = {}
    for a in appts:
        s = a["status"] or "(none)"
        status_dist[s] = status_dist.get(s, 0) + 1
    OUT["bookings"] = {
        "total_appointments_found": len(appts),
        "booked_last_7d": len(booked_7d),
        "recent_opps_last_7d": len(recent_opps),
        "booking_rate_pct": round(100 * len(booked_7d) / len(recent_opps), 1) if recent_opps else None,
        "status_distribution": status_dist,
        "booked_7d_detail": [
            {
                "contactId": a["contactId"],
                "title": a["title"],
                "status": a["status"],
                "scheduled": a["startDt"].isoformat() if a["startDt"] else None,
                "booked_on": a["bookedDt"].isoformat() if a["bookedDt"] else None,
                "createdBy": a["createdBy"],
            }
            for a in sorted(booked_7d, key=lambda x: (x["bookedDt"] or NOW))
        ],
    }

    # ---- 3) Per-recent-lead qualification: utmContent (ad name) + adId + qualified/unqualified tag ----
    def contact(cid):
        code, data = get(f"/contacts/{cid}")
        if code != 200:
            return {}
        return data.get("contact", data)

    recent_leads = []
    for cid in recent_cids:
        c = contact(cid)
        if not c:
            continue
        # attributionSource = FIRST touch (correct); lastAttributionSource is overwritten by booking page
        attr = c.get("attributionSource") or {}
        tags = c.get("tags") or []
        full = ((c.get("firstName") or "") + " " + (c.get("lastName") or "")).strip().lower()
        if any(x in full for x in EXCL):
            continue
        qtag = None
        for t in tags:
            tl = str(t).lower()
            if args.unqualified_tag.lower() in tl:
                qtag = "unqualified"
                break
            if args.qualified_tag.lower() in tl:
                qtag = "qualified"
        recent_leads.append(
            {
                "contactId": cid,
                "name": (c.get("firstName", "") + " " + c.get("lastName", "")).strip() or c.get("name"),
                "ad_name": attr.get("utmContent"),
                "adId": attr.get("adId"),
                "utmCampaign": attr.get("utmCampaign"),
                "quality_tag": qtag,
                "created": c.get("dateAdded"),
                "tags": tags,
            }
        )
        time.sleep(0.02)
    # qualified summary
    q = {"qualified": 0, "unqualified": 0, "untagged": 0}
    for l in recent_leads:
        q[l["quality_tag"] or "untagged"] += 1
    OUT["recent_leads"] = recent_leads
    OUT["qualification_summary_7d"] = q

    # ---- 4) Speed-to-lead + conversation samples ----
    def messages(cid, cap_convs=6):
        out = []
        code, cdata = get("/conversations/search/", {"locationId": LOC, "contactId": cid})
        if code != 200 or not cdata:
            return out
        for cv in (cdata.get("conversations", []) or [])[:cap_convs]:
            conv_id = cv.get("id")
            if not conv_id:
                continue
            code2, mdata = get(f"/conversations/{conv_id}/messages", {"limit": 100})
            if code2 != 200 or not mdata:
                continue
            mm = mdata.get("messages", {})
            msg_list = mm.get("messages", []) if isinstance(mm, dict) else mm
            for m in msg_list or []:
                out.append(
                    {
                        "dt": iso(m.get("dateAdded")),
                        "messageType": m.get("messageType"),
                        "type_num": m.get("type"),
                        "direction": (m.get("direction") or "").lower(),
                        "status": m.get("status"),
                        "is_call": is_call_msg(m),
                        "body": str(m.get("body") or "")[:500],
                        "meta": m.get("meta"),
                    }
                )
            time.sleep(0.02)
        out.sort(key=lambda x: x["dt"] or NOW)
        return out

    def stl_for(cid, created_raw):
        msgs = messages(cid)
        created = iso(created_raw)
        first_out = None
        first_call = None
        for m in msgs:
            if m["direction"] == "outbound" and first_out is None and not m["is_call"]:
                # only real comms channels (skip activity/opportunity system events)
                if m["type_num"] in (1, 2, 3, 4, 5, 6, 7, 8, 19, 29) or "TYPE_" in str(m["messageType"]):
                    first_out = m["dt"]
            if m["is_call"] and first_call is None:
                first_call = m["dt"]

        def mins(a, b):
            return round((b - a).total_seconds() / 60, 1) if a and b else None

        return {
            "contactId": cid,
            "created": created_raw,
            "first_outbound": first_out.isoformat() if first_out else None,
            "stl_to_first_touch_min": mins(created, first_out),
            "first_call": first_call.isoformat() if first_call else None,
            "stl_to_first_call_min": mins(created, first_call),
            "msg_count": len(msgs),
        }, msgs

    # speed-to-lead over the recent leads (cap to keep runtime sane)
    stl_rows = []
    sample_threads = []
    stl_targets = recent_leads[: max(args.sample, 8)]
    for l in stl_targets:
        row, msgs = stl_for(l["contactId"], l["created"])
        row["name"] = l["name"]
        stl_rows.append(row)
        if len(sample_threads) < args.sample and msgs:
            sample_threads.append(
                {
                    "contactId": l["contactId"],
                    "name": l["name"],
                    "ad_name": l["ad_name"],
                    "quality_tag": l["quality_tag"],
                    "messages": [
                        {
                            "dt": m["dt"].isoformat() if m["dt"] else None,
                            "channel": m["messageType"] or m["type_num"],
                            "direction": m["direction"],
                            "is_call": m["is_call"],
                            "status": m["status"],
                            "body": m["body"],
                        }
                        for m in msgs
                    ],
                }
            )
    # STL aggregate (only rows with a real first-touch)
    touched = [r["stl_to_first_touch_min"] for r in stl_rows if r["stl_to_first_touch_min"] is not None]
    OUT["speed_to_lead"] = {
        "rows": stl_rows,
        "median_first_touch_min": sorted(touched)[len(touched) // 2] if touched else None,
        "leads_with_no_outbound": sum(1 for r in stl_rows if r["stl_to_first_touch_min"] is None),
        "leads_sampled": len(stl_rows),
    }
    OUT["conversation_samples"] = sample_threads

    OUT["endpoints_called"] = sorted(set(EP))

    payload = json.dumps(OUT, indent=2, default=str)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w") as fh:
            fh.write(payload)
    print(payload)


if __name__ == "__main__":
    main()
