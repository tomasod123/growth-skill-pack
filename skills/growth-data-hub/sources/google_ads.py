"""Google Ads API (REST): cost, clicks, impressions, conversions by campaign, plus search impression
share lost to budget and to rank. Optional: the last N days of account changes (change_event).

Auth: OAuth refresh token for a Google user with access to the account, an OAuth client id/secret,
a developer token, and (when access comes through a manager account) the manager's id as
login-customer-id. Read-only: this module only calls googleAds:search.
"""
from .common import SourceError, dig, http, num

NAME = "google_ads"


def _cid(x):
    return str(x or "").replace("-", "").strip()


def missing(cfg, env):
    out = [f"{k} in .env" for k in ("GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID",
                                     "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN") if not env.get(k)]
    cid = _cid(dig(cfg, "google_ads", "customer_id"))
    if not cid.isdigit():
        out.append("google_ads.customer_id in config.yaml")
    return out


def access_token(env):
    d = http("POST", "https://oauth2.googleapis.com/token", retries=1, retry_on=(500, 502, 503), data={
        "client_id": env["GOOGLE_ADS_CLIENT_ID"], "client_secret": env["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": env["GOOGLE_ADS_REFRESH_TOKEN"], "grant_type": "refresh_token"})
    if "access_token" not in d:
        raise SourceError("Google OAuth refresh failed; re-run tools/google_oauth.py to get a new refresh token")
    return d["access_token"]


def search(cfg, env, query, token):
    version = dig(cfg, "google_ads", "api_version", default="v25")
    url = f"https://googleads.googleapis.com/{version}/customers/{_cid(dig(cfg, 'google_ads', 'customer_id'))}/googleAds:search"
    headers = {"Authorization": f"Bearer {token}", "developer-token": env["GOOGLE_ADS_DEVELOPER_TOKEN"],
               "Content-Type": "application/json"}
    if env.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID"):
        headers["login-customer-id"] = _cid(env["GOOGLE_ADS_LOGIN_CUSTOMER_ID"])
    rows, page = [], None
    while True:
        body = {"query": query}
        if page:
            body["pageToken"] = page
        d = http("POST", url, headers=headers, json_body=body)
        rows += d.get("results", [])
        page = d.get("nextPageToken")
        if not page:
            return rows


CAMPAIGN_GAQL = """
SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type,
       metrics.cost_micros, metrics.clicks, metrics.impressions, metrics.conversions,
       metrics.search_impression_share, metrics.search_budget_lost_impression_share,
       metrics.search_rank_lost_impression_share
FROM campaign
WHERE segments.date BETWEEN '{start}' AND '{end}' AND metrics.impressions > 0
"""

# change_event REJECTS queries without an explicit change_date_time range (and only keeps ~30 days),
# and it requires a LIMIT. Always pass both.
CHANGES_GAQL = """
SELECT change_event.change_date_time, change_event.change_resource_type, change_event.resource_change_operation,
       change_event.changed_fields, campaign.name
FROM change_event
WHERE change_event.change_date_time >= '{start}' AND change_event.change_date_time <= '{end}'
ORDER BY change_event.change_date_time DESC
LIMIT 200
"""


def fetch(cfg, env, start, end):
    import datetime as dt
    tok = access_token(env)
    raw = {"campaigns": search(cfg, env, CAMPAIGN_GAQL.format(start=start, end=end), tok), "changes": []}
    # change_event only covers the last 30 days; clamp so a --days 90 run still works.
    today = dt.date.today()
    c_start = max(dt.date.fromisoformat(start), today - dt.timedelta(days=29))
    try:
        raw["changes"] = search(cfg, env, CHANGES_GAQL.format(start=c_start.isoformat(), end=end + " 23:59:59"), tok)
    except SourceError:
        raw["changes"] = []  # change history is a nice-to-have; never fail the run over it
    return raw


def parse(raw, cfg, start, end):
    camps = []
    for r in raw.get("campaigns", []):
        cost = num(dig(r, "metrics", "costMicros")) / 1e6
        clicks, impr = num(dig(r, "metrics", "clicks")), num(dig(r, "metrics", "impressions"))
        conv = num(dig(r, "metrics", "conversions"))
        is_ = dig(r, "metrics", "searchImpressionShare")
        camps.append({
            "id": str(dig(r, "campaign", "id", default="")), "name": dig(r, "campaign", "name", default=""),
            "status": dig(r, "campaign", "status", default=""),
            "type": dig(r, "campaign", "advertisingChannelType", default=""),
            "spend": round(cost, 2), "clicks": int(clicks), "impressions": int(impr),
            "conversions": round(conv, 2), "ctr": clicks / impr if impr else None,
            "cpa": cost / conv if conv else None,
            # impression share metrics only exist for Search campaigns; None elsewhere
            "impression_share": None if is_ is None else num(is_),
            "lost_is_budget": _opt(dig(r, "metrics", "searchBudgetLostImpressionShare")),
            "lost_is_rank": _opt(dig(r, "metrics", "searchRankLostImpressionShare")),
        })
    camps.sort(key=lambda c: -c["spend"])
    tot = {"spend": round(sum(c["spend"] for c in camps), 2), "clicks": sum(c["clicks"] for c in camps),
           "impressions": sum(c["impressions"] for c in camps),
           "leads": round(sum(c["conversions"] for c in camps), 2)}
    # CTR benchmarks are for Search; Performance Max / Display impressions would drag a blended CTR down.
    s_rows = [c for c in camps if c["type"] == "SEARCH"]
    s_imp = sum(c["impressions"] for c in s_rows)
    tot["ctr"] = sum(c["clicks"] for c in s_rows) / s_imp if s_imp else None
    search_c = [c for c in camps if c["lost_is_budget"] is not None and c["spend"] > 0]
    sp = sum(c["spend"] for c in search_c)
    tot["lost_is_budget"] = sum(c["lost_is_budget"] * c["spend"] for c in search_c) / sp if sp else None
    tot["lost_is_rank"] = sum((c["lost_is_rank"] or 0) * c["spend"] for c in search_c) / sp if sp else None
    changes = [{"when": dig(r, "changeEvent", "changeDateTime", default=""),
                "what": dig(r, "changeEvent", "changeResourceType", default=""),
                "op": dig(r, "changeEvent", "resourceChangeOperation", default=""),
                "campaign": dig(r, "campaign", "name", default="")} for r in raw.get("changes", [])]
    return {"totals": tot, "campaigns": camps, "changes": changes}


def _opt(v):
    return None if v is None else num(v)
