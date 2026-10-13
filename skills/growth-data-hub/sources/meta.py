"""Meta Marketing API: spend, impressions, link clicks, CTR, CPM and leads, by campaign and by ad.

Auth: a system user access token with ads_read (META_ACCESS_TOKEN).
Leads are counted ONLY where action_type == 'lead'. Never match the substring 'lead': Meta also
returns onsite_conversion.lead_grouped, offsite_conversion.fb_pixel_lead and others for the SAME
submission, so a substring match double or triple counts.
"""
import json

from .common import SourceError, dig, http, num

NAME = "meta"
FIELDS = ("campaign_id,campaign_name,ad_id,ad_name,spend,impressions,clicks,inline_link_clicks,"
          "frequency,actions")


def _account(cfg):
    acct = str(dig(cfg, "meta", "ad_account_id", default="") or "").strip()
    if acct and not acct.startswith("act_"):
        acct = "act_" + acct
    return acct


def missing(cfg, env):
    out = []
    if not env.get("META_ACCESS_TOKEN"):
        out.append("META_ACCESS_TOKEN in .env")
    if not _account(cfg) or "YOUR" in _account(cfg):
        out.append("meta.ad_account_id in config.yaml")
    return out


def _insights(cfg, env, level, start, end):
    version = dig(cfg, "meta", "api_version", default="v26.0")
    url = f"https://graph.facebook.com/{version}/{_account(cfg)}/insights"
    params = {
        "level": level,
        "fields": FIELDS,
        "time_range": json.dumps({"since": start, "until": end}),
        "use_unified_attribution_setting": "true",  # same numbers as Ads Manager
        "limit": 500,
    }
    # Token in the Authorization header, not the URL, so it can never end up in an error message or log.
    headers = {"Authorization": f"Bearer {env['META_ACCESS_TOKEN']}"}
    rows = []
    while url:
        try:
            d = http("GET", url, params=params, headers=headers)
        except SourceError as e:
            # error code 1 = "reduce the amount of data": retry the same page with smaller pages
            if '"code":1,' in str(e).replace(" ", "") and params and params.get("limit") != 100:
                params["limit"] = 100
                continue
            raise
        if "error" in d:
            raise SourceError(f"Meta: {d['error'].get('message')}")
        rows += d.get("data", [])
        url = dig(d, "paging", "next")
        params = None  # the next link already carries every parameter
    return rows


def fetch(cfg, env, start, end):
    return {"campaigns": _insights(cfg, env, "campaign", start, end),
            "ads": _insights(cfg, env, "ad", start, end)}


def lead_count(actions, action_type="lead"):
    """Exact match on action_type. Substring matching ('lead' in t) double counts."""
    return sum(num(a.get("value")) for a in (actions or []) if a.get("action_type") == action_type)


def _row(r, key_id, key_name, lead_type):
    spend, impr, link = num(r.get("spend")), num(r.get("impressions")), num(r.get("inline_link_clicks"))
    leads = lead_count(r.get("actions"), lead_type)
    return {
        "id": str(r.get(key_id) or ""), "name": r.get(key_name) or "(no name)",
        "campaign": r.get("campaign_name") or "",
        "spend": round(spend, 2), "impressions": int(impr), "clicks": int(link),
        "all_clicks": int(num(r.get("clicks"))), "frequency": round(num(r.get("frequency")), 2),
        "ctr": link / impr if impr else None,
        "cpm": spend / impr * 1000 if impr else None,
        "leads": leads, "cpl": spend / leads if leads else None,
    }


def parse(raw, cfg, start, end):
    lead_type = dig(cfg, "meta", "lead_action_type", default="lead")
    campaigns = [_row(r, "campaign_id", "campaign_name", lead_type) for r in raw.get("campaigns", [])]
    ads = [_row(r, "ad_id", "ad_name", lead_type) for r in raw.get("ads", [])]
    tot = {k: sum(c[k] for c in campaigns) for k in ("spend", "impressions", "clicks", "leads")}
    tot["spend"] = round(tot["spend"], 2)
    return {"totals": tot,
            "campaigns": sorted(campaigns, key=lambda c: -c["spend"]),
            "ads": sorted(ads, key=lambda a: -a["spend"])}
