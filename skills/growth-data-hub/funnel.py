"""Join every source into one funnel per channel:
spend > impressions > clicks > sessions > leads > booked > showed > won.

Channel rules come from config.yaml (channels:). GA4 sessions are matched on session source/medium
(regex), CRM contacts on UTM source/medium, GHL's session source, click ids, tags or the contact source.
Anything that matches no paid channel lands in 'other' (organic, direct, referral...).
"""
import re

OTHER = {"key": "other", "label": "Organic and other", "platform": None}


def channels(cfg):
    return list(cfg.get("channels") or []) + [OTHER]


def match_source_medium(sm, cfg):
    for ch in cfg.get("channels") or []:
        for pat in ch.get("ga4_source_medium") or []:
            if re.search(pat, sm or "", re.I):
                return ch["key"]
    return "other"


def match_contact(c, cfg):
    """First channel whose GHL rules match. Rules are OR'ed; utm_source + utm_medium are AND'ed when both set."""
    for ch in cfg.get("channels") or []:
        r = ch.get("ghl") or {}
        lower = lambda key: [str(x).lower() for x in (r.get(key) or [])]
        if r.get("click_id") and c.get(r["click_id"]):
            return ch["key"]
        if c.get("session_source") and c["session_source"] in lower("session_source"):
            return ch["key"]
        us, um = lower("utm_source"), lower("utm_medium")
        if us and c.get("utm_source") in us and (not um or c.get("utm_medium") in um):
            return ch["key"]
        if set(lower("tags")) & set(c.get("tags") or []):
            return ch["key"]
        src = (c.get("source") or "").lower()
        if src and any(s in src for s in lower("source_contains")):
            return ch["key"]
    return "other"


def contact_outcomes(ghl):
    """Per contact id: booked / showed / no_show / won, from appointments and opportunity stages together."""
    out = {}
    for c in ghl.get("contacts", []):
        out[c["id"]] = {"booked": False, "showed": False, "no_show": False, "won": False}
    for a in ghl.get("appointments", []):
        o = out.get(a["contact_id"])
        if o is None:
            continue
        o["booked"] = True
        if a["status"] == "showed":
            o["showed"] = True
        elif a["status"] in ("noshow", "no_show", "no-show"):
            o["no_show"] = True
    for op in ghl.get("opportunities", []):
        o = out.get(op["contact_id"])
        if o is None or not op["kind"]:
            continue
        k = op["kind"]
        if k in ("booked", "showed", "no_show", "won"):
            o["booked"] = True
        if k in ("showed", "won"):
            o["showed"] = True
        if k == "no_show":
            o["no_show"] = True
        if k == "won":
            o["won"] = True
    for o in out.values():
        if o["showed"]:
            o["no_show"] = False  # a rebooked no-show that later showed counts as showed
    return out


def _div(a, b):
    return a / b if b else None


def rates(f):
    f["ctr"] = _div(f["clicks"], f["impressions"])
    f["click_to_session"] = _div(f["sessions"], f["clicks"]) if f["clicks"] and f["sessions"] is not None else None
    f["session_to_lead"] = _div(f["leads"], f["sessions"]) if f["sessions"] and f["leads"] is not None else None
    f["lead_to_booked"] = _div(f["booked"], f["leads"]) if f["booked"] is not None and f["leads"] else None
    # Show rate counts only calls that have happened (showed or no-show), so future bookings don't drag it down.
    done = (f["showed"] or 0) + (f["no_show"] or 0)
    f["show_rate"] = _div(f["showed"], done) if f["showed"] is not None else None
    f["showed_to_won"] = _div(f["won"], f["showed"]) if f["won"] is not None else None
    sp = f["spend"] or 0
    f["cpl"] = _div(sp, f["leads"]) if sp else None
    f["cost_per_booked"] = _div(sp, f["booked"]) if sp and f["booked"] else None
    f["cost_per_showed"] = _div(sp, f["showed"]) if sp and f["showed"] else None
    f["cost_per_won"] = _div(sp, f["won"]) if sp and f["won"] else None
    return f


def build(data, cfg):
    """data: {source_name: parsed or None}. Returns {'channels': [...], 'total': {...}}."""
    ga4, ghl = data.get("ga4"), data.get("ghl")
    sessions = {}
    if ga4:
        for r in ga4["by_source_medium"]:
            k = match_source_medium(r["source_medium"], cfg)
            sessions[k] = sessions.get(k, 0) + r["sessions"]
    crm_leads, outcomes, per = {}, {}, {}
    if ghl:
        outcomes = contact_outcomes(ghl)
        for c in ghl["contacts"]:
            k = match_contact(c, cfg)
            crm_leads[k] = crm_leads.get(k, 0) + 1
            p = per.setdefault(k, {"booked": 0, "showed": 0, "no_show": 0, "won": 0})
            for s in p:
                p[s] += outcomes[c["id"]][s]

    rows = []
    for ch in channels(cfg):
        k, plat = ch["key"], ch.get("platform")
        src = data.get(plat) if plat else None
        if src is None and not ga4 and not ghl:
            continue
        t = (src or {}).get("totals", {})
        f = {"key": k, "label": ch.get("label", k), "platform": plat,
             "spend": t.get("spend", 0.0) if src else 0.0,
             "impressions": t.get("impressions", 0) if src else 0,
             "clicks": t.get("clicks", 0) if src else 0,
             "sessions": sessions.get(k, 0) if ga4 else None,
             "platform_leads": t.get("leads") if src else None,
             "lead_source": "crm" if ghl else "platform"}
        # No CRM and no ad platform for this channel = leads unknown (not zero), so no step is judged on it.
        f["leads"] = crm_leads.get(k, 0) if ghl else f["platform_leads"]
        o = per.get(k, {}) if ghl else {}
        for s in ("booked", "showed", "no_show", "won"):
            f[s] = o.get(s, 0) if ghl else None
        f["has_platform_data"] = bool(src)
        f = rates(f)
        if src and t.get("ctr") is not None:
            f["ctr"] = t["ctr"]  # the source knows better (Google Ads: Search campaigns only)
        rows.append(f)

    tot = {"key": "total", "label": "All channels", "platform": None, "lead_source": "crm" if ghl else "platform"}
    for k in ("spend", "impressions", "clicks", "leads"):
        tot[k] = sum(r[k] or 0 for r in rows)
    tot["sessions"] = sum(sessions.values()) if ga4 else None
    pl = [r["platform_leads"] for r in rows if r["platform_leads"] is not None]
    tot["platform_leads"] = sum(pl) if pl else None
    for s in ("booked", "showed", "no_show", "won"):
        tot[s] = sum(r[s] for r in rows) if ghl else None
    # clicks only exist for paid channels, so the click_to_session ratio uses paid sessions only
    paid_sessions = sum(r["sessions"] or 0 for r in rows if r["platform"]) if ga4 else None
    tot = rates(tot)
    tot["click_to_session"] = _div(paid_sessions, tot["clicks"]) if ga4 and tot["clicks"] else None
    return {"channels": rows, "total": tot}
