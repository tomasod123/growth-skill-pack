#!/usr/bin/env python3
"""
meta_pull.py - Consolidated Meta pull for the meta-ads-analyst skill (live data mode).

Self-contained. Read-only (GET only). NEVER prints the token value (redacts it from every logged URL).
Graph API version from META_GRAPH_VERSION (default v21.0). Account from --account or META_AD_ACCOUNT_ID; token from META_ACCESS_TOKEN.
Load both first:  set -a; source ~/.claude/skills/.env; set +a

Outputs ONE JSON object to stdout (and to --out <path> if given), covering the active
campaign for last_7d + last_3d:
  - totals: spend, impressions, reach, frequency, clicks, link clicks, ctr, link-ctr, cpm,
    cost/link-click, leads (`lead`) + leads (`onsite_conversion.lead_grouped`), CPL (both)
  - per_ad: name, spend, leads, CPL, CTR (sorted by leads desc)
  - breakdowns: placement (publisher_platform + platform_position), age, gender
  - campaigns_spending: any OTHER campaign with >0 spend in last_7d (contamination flag)
  - quality: per-ad quality / engagement / conversion rate rankings (last_7d)
  - device: impression_device breakdown; daily: impressions per unit of spend by day
  - activities: account change log for the last 14 days (did the edits actually publish?)

Usage:
  python3 meta_pull.py                         # biggest-spending campaign, prints JSON
  python3 meta_pull.py --out ./meta-ads-analyst-output/meta.json
  python3 meta_pull.py --campaign <id>         # pin a campaign
  python3 meta_pull.py --account act_XXXXXXXXXX
"""
import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "").strip() or "v21.0"  # override when Meta retires v21.0
BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
ACCT = os.environ.get("META_AD_ACCOUNT_ID", "")  # digits or act_XXXXXXXXXX; --account overrides
DEFAULT_CAMPAIGN = os.environ.get("META_CAMPAIGN_ID", "")  # empty = biggest spender in the last 30 days
WINDOWS = {"last_7d": {"date_preset": "last_7d"}, "last_3d": {"date_preset": "last_3d"}}

INSIGHT_FIELDS = (
    "spend,impressions,reach,frequency,clicks,inline_link_clicks,"
    "ctr,inline_link_click_ctr,cpm,cost_per_inline_link_click,"
    "actions,cost_per_action_type"
)

# ---------------------------------------------------------------------------
# Token (never echoed)
# ---------------------------------------------------------------------------
TOKEN = os.environ.get("META_ACCESS_TOKEN", "").strip()

try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    CTX = ssl.create_default_context()


def _redact(url):
    return url.replace(TOKEN, "<TOKEN>") if TOKEN else url


LOG = []


def gget(path, params):
    params = dict(params)
    params["access_token"] = TOKEN
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    safe = _redact(url)
    try:
        with urllib.request.urlopen(urllib.request.Request(url), context=CTX, timeout=90) as r:
            return json.loads(r.read().decode()), safe
    except urllib.error.HTTPError as e:
        return {"__error__": True, "status": e.code, "body": _redact(e.read().decode())}, safe
    except Exception as e:
        return {"__error__": True, "status": "EXC", "body": _redact(str(e))}, safe


def paged(path, params, cap=5000):
    rows = []
    data, safe = gget(path, params)
    LOG.append(safe)
    if isinstance(data, dict) and data.get("__error__"):
        return data
    rows.extend(data.get("data", []))
    nxt = data.get("paging", {}).get("next")
    while nxt and len(rows) < cap:
        try:
            with urllib.request.urlopen(urllib.request.Request(nxt), context=CTX, timeout=90) as r:
                d = json.loads(r.read().decode())
            rows.extend(d.get("data", []))
            nxt = d.get("paging", {}).get("next")
        except Exception:
            break
    return {"data": rows}


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------
def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def leads_from(row):
    """Return dict of lead / lead_grouped counts + CPLs from an insights row."""
    lead = grouped = cpl_lead = cpl_grouped = None
    for a in row.get("actions", []) or []:
        if a.get("action_type") == "lead":
            lead = f(a.get("value"))
        elif a.get("action_type") == "onsite_conversion.lead_grouped":
            grouped = f(a.get("value"))
    for a in row.get("cost_per_action_type", []) or []:
        if a.get("action_type") == "lead":
            cpl_lead = f(a.get("value"))
        elif a.get("action_type") == "onsite_conversion.lead_grouped":
            cpl_grouped = f(a.get("value"))
    return {
        "leads": lead,
        "leads_grouped": grouped,
        "cpl": cpl_lead,
        "cpl_grouped": cpl_grouped,
    }


def totals_from(row):
    t = {
        "campaign_name": row.get("campaign_name"),
        "spend": f(row.get("spend")),
        "impressions": f(row.get("impressions")),
        "reach": f(row.get("reach")),
        "frequency": f(row.get("frequency")),
        "clicks": f(row.get("clicks")),
        "link_clicks": f(row.get("inline_link_clicks")),
        "ctr": f(row.get("ctr")),
        "link_ctr": f(row.get("inline_link_click_ctr")),
        "cpm": f(row.get("cpm")),
        "cost_per_link_click": f(row.get("cost_per_inline_link_click")),
    }
    t.update(leads_from(row))
    return t


def clean_breakdown(rows, keys):
    out = []
    for r in rows:
        entry = {k: r.get(k) for k in keys}
        entry["spend"] = f(r.get("spend"))
        entry["impressions"] = f(r.get("impressions"))
        entry["ctr"] = f(r.get("ctr"))
        entry.update(leads_from(r))
        out.append(entry)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    global ACCT
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--campaign", default=DEFAULT_CAMPAIGN)
    ap.add_argument("--account", default=ACCT, help="ad account id (digits or act_...); default META_AD_ACCOUNT_ID")
    ap.add_argument("--no-extras", action="store_true", help="skip quality rankings, device, daily and activity log")
    args = ap.parse_args()
    if not TOKEN:
        print(json.dumps({"FATAL": "META_ACCESS_TOKEN not set. Run: set -a; source ~/.claude/skills/.env; set +a"}))
        sys.exit(1)
    if not args.account:
        print(json.dumps({"FATAL": "No ad account. Pass --account or set META_AD_ACCOUNT_ID."}))
        sys.exit(1)
    ACCT = "act_" + args.account.replace("act_", "")
    CAMP = args.campaign
    if not CAMP:
        # No campaign pinned: take the account's biggest spender over the last 30 days,
        # falling back to the newest campaign. Keeps the audit working as campaigns are
        # created and retired.
        camps, safe = gget(f"{ACCT}/campaigns", {"fields": "name,status,created_time", "limit": "100"})
        rows = (camps or {}).get("data", []) if isinstance(camps, dict) else []
        spend = {}
        ins, _ = gget(f"{ACCT}/insights", {"level": "campaign", "fields": "campaign_id,spend",
                                           "date_preset": "last_30d", "limit": "100"})
        for r in ((ins or {}).get("data", []) if isinstance(ins, dict) else []):
            try:
                spend[r.get("campaign_id")] = float(r.get("spend") or 0)
            except Exception:
                pass
        if rows:
            rows.sort(key=lambda c: (spend.get(c.get("id"), 0.0), c.get("created_time", "")), reverse=True)
            CAMP = rows[0].get("id", "")
    CAMP_FILTER = json.dumps([{"field": "campaign.id", "operator": "IN", "value": [CAMP]}])

    OUT = {
        "meta": {"account": ACCT, "campaign_id": CAMP, "graph": GRAPH_VERSION, "currency": None},
        "windows": {},
    }

    # account currency (verify, don't assume)
    acct, safe = gget(ACCT, {"fields": "currency,name,timezone_name"})
    LOG.append(safe)
    if isinstance(acct, dict) and not acct.get("__error__"):
        OUT["meta"]["currency"] = acct.get("currency")
        OUT["meta"]["account_name"] = acct.get("name")
        OUT["meta"]["timezone"] = acct.get("timezone_name")

    # contamination check: any OTHER campaign spending in last_7d?
    camp_rows = paged(
        f"{ACCT}/insights",
        {"fields": "campaign_name,campaign_id,spend", "level": "campaign", "date_preset": "last_7d"},
    )
    spending = []
    if isinstance(camp_rows, dict) and not camp_rows.get("__error__"):
        for r in camp_rows.get("data", []):
            sp = f(r.get("spend")) or 0
            if sp > 0:
                spending.append(
                    {
                        "campaign_id": r.get("campaign_id"),
                        "campaign_name": r.get("campaign_name"),
                        "spend": sp,
                        "is_target": r.get("campaign_id") == CAMP,
                    }
                )
    OUT["campaigns_spending_last_7d"] = spending
    others = [c for c in spending if not c["is_target"]]
    OUT["contamination_flag"] = (
        f"WARNING: {len(others)} other campaign(s) also spending in last_7d "
        f"(account totals will exceed the target campaign): "
        + ", ".join(f"{c['campaign_name']} ({c['spend']:.2f})" for c in others)
        if others
        else None
    )

    for wname, wparam in WINDOWS.items():
        w = {}

        # totals (campaign node insights, no breakdown)
        p = {"fields": "campaign_name,campaign_id," + INSIGHT_FIELDS}
        p.update(wparam)
        tot = paged(f"{CAMP}/insights", p)
        if isinstance(tot, dict) and not tot.get("__error__") and tot.get("data"):
            w["totals"] = totals_from(tot["data"][0])
        else:
            w["totals"] = {"__error__": tot}

        # per-ad (campaign-scoped via account insights + filter)
        p = {"fields": "ad_name,ad_id," + INSIGHT_FIELDS, "level": "ad", "filtering": CAMP_FILTER}
        p.update(wparam)
        ads = paged(f"{ACCT}/insights", p)
        per_ad = []
        if isinstance(ads, dict) and not ads.get("__error__"):
            for r in ads.get("data", []):
                lf = leads_from(r)
                per_ad.append(
                    {
                        "ad_name": r.get("ad_name"),
                        "ad_id": r.get("ad_id"),
                        "spend": f(r.get("spend")),
                        "ctr": f(r.get("ctr")),
                        "leads": lf["leads"],
                        "leads_grouped": lf["leads_grouped"],
                        "cpl": lf["cpl"],
                    }
                )
            per_ad.sort(key=lambda x: (x["leads"] or 0), reverse=True)
        w["per_ad"] = per_ad

        # breakdowns (campaign-scoped)
        for bname, bval, keys in (
            ("placement", "publisher_platform,platform_position", ["publisher_platform", "platform_position"]),
            ("age", "age", ["age"]),
            ("gender", "gender", ["gender"]),
        ):
            p = {"fields": INSIGHT_FIELDS, "level": "campaign", "breakdowns": bval, "filtering": CAMP_FILTER}
            p.update(wparam)
            bd = paged(f"{ACCT}/insights", p)
            w[bname] = clean_breakdown(bd.get("data", []), keys) if isinstance(bd, dict) and not bd.get("__error__") else {"__error__": bd}

        OUT["windows"][wname] = w

    if not args.no_extras:
        # quality rankings: BELOW_AVERAGE_35 = bottom 35% of the auction -> higher CPM, less delivery
        p = {"fields": "ad_name,ad_id,spend,impressions,quality_ranking,engagement_rate_ranking,conversion_rate_ranking",
             "level": "ad", "filtering": CAMP_FILTER, "date_preset": "last_7d"}
        qr = paged(f"{ACCT}/insights", p)
        OUT["quality"] = qr.get("data", []) if isinstance(qr, dict) and not qr.get("__error__") else {"__error__": qr}
        # device split
        p = {"fields": INSIGHT_FIELDS, "level": "campaign", "breakdowns": "impression_device",
             "filtering": CAMP_FILTER, "date_preset": "last_14d"}
        dv = paged(f"{ACCT}/insights", p)
        OUT["device_last_14d"] = clean_breakdown(dv.get("data", []), ["impression_device"]) if isinstance(dv, dict) and not dv.get("__error__") else {"__error__": dv}
        # daily impressions per unit of spend (a falling line = delivery suppression or rising auction cost)
        p = {"fields": "spend,impressions,actions,cost_per_action_type", "time_increment": "1", "date_preset": "last_14d"}
        dd = paged(f"{CAMP}/insights", p)
        daily = []
        if isinstance(dd, dict) and not dd.get("__error__"):
            for r in dd.get("data", []):
                sp, im = f(r.get("spend")), f(r.get("impressions"))
                row = {"date": r.get("date_start"), "spend": sp, "impressions": im,
                       "impressions_per_unit_spend": round(im / sp, 1) if sp and im else None}
                row.update(leads_from(r))
                daily.append(row)
        OUT["daily_last_14d"] = daily
        # activity log: did the edits you think you made actually publish?
        import datetime as _dt
        since = (_dt.date.today() - _dt.timedelta(days=14)).isoformat()
        ac = paged(f"{ACCT}/activities", {"fields": "event_type,event_time,object_name,extra_data,actor_name",
                                          "since": since, "limit": "300"}, cap=1000)
        OUT["activities_last_14d"] = ac.get("data", []) if isinstance(ac, dict) and not ac.get("__error__") else {"__error__": ac}

    OUT["__log__"] = LOG  # token-redacted URLs for verification

    payload = json.dumps(OUT, indent=2, default=str)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w") as fh:
            fh.write(payload)
    print(payload)


if __name__ == "__main__":
    main()
