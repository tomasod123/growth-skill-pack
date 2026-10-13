"""GA4 Data API: sessions, engaged sessions and key events by session source/medium and landing page.

Auth: a Google Cloud service account JSON key (GA4_SERVICE_ACCOUNT_JSON = path to the file). Add the
service account's email as a Viewer on the GA4 property. Scope: analytics.readonly.
'keyEvents' is what GA4 used to call 'conversions'.
"""
import os

from .common import SourceError, dig, http, num

NAME = "ga4"
SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
PAGE = 10000


def _prop(cfg):
    return str(dig(cfg, "ga4", "property_id", default="") or "").replace("properties/", "").strip()


def missing(cfg, env):
    out = []
    path = env.get("GA4_SERVICE_ACCOUNT_JSON")
    if not path:
        out.append("GA4_SERVICE_ACCOUNT_JSON in .env")
    elif not os.path.exists(os.path.expanduser(path)):
        out.append(f"the service account key file GA4_SERVICE_ACCOUNT_JSON points at ({path})")
    if not _prop(cfg).isdigit():
        out.append("ga4.property_id in config.yaml (the number, not the G- measurement id)")
    return out


def access_token(env):
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    creds = service_account.Credentials.from_service_account_file(
        os.path.expanduser(env["GA4_SERVICE_ACCOUNT_JSON"]), scopes=[SCOPE])
    creds.refresh(Request())
    return creds.token


def run_report(cfg, token, body):
    url = f"https://analyticsdata.googleapis.com/v1beta/properties/{_prop(cfg)}:runReport"
    rows, offset = [], 0
    while True:
        d = http("POST", url, headers={"Authorization": f"Bearer {token}"},
                 json_body={**body, "limit": PAGE, "offset": offset})
        rows += d.get("rows", [])
        total = int(d.get("rowCount") or 0)
        offset += PAGE
        if offset >= total or not d.get("rows"):
            d["rows"] = rows
            return d


def fetch(cfg, env, start, end):
    try:
        tok = access_token(env)
    except Exception as e:  # bad key file, wrong JSON
        raise SourceError(f"GA4 service account key could not be used: {e}")
    body = {"dateRanges": [{"startDate": start, "endDate": end}],
            "dimensions": [{"name": "sessionSourceMedium"}, {"name": "landingPage"}],
            "metrics": [{"name": "sessions"}, {"name": "engagedSessions"}, {"name": "keyEvents"}]}
    return {"report": run_report(cfg, tok, body)}


def parse(raw, cfg, start, end):
    rep = raw.get("report", {})
    dims = [h["name"] for h in rep.get("dimensionHeaders", [])]
    mets = [h["name"] for h in rep.get("metricHeaders", [])]
    rows = []
    for r in rep.get("rows", []):
        d = dict(zip(dims, [v.get("value", "") for v in r.get("dimensionValues", [])]))
        m = dict(zip(mets, [num(v.get("value")) for v in r.get("metricValues", [])]))
        rows.append({"source_medium": d.get("sessionSourceMedium", "(not set)").lower(),
                     "landing_page": d.get("landingPage", "(not set)"),
                     "sessions": int(m.get("sessions", 0)), "engaged": int(m.get("engagedSessions", 0)),
                     "key_events": m.get("keyEvents", 0.0)})
    by_sm, by_lp = {}, {}
    for r in rows:
        for key, bucket in ((r["source_medium"], by_sm), (r["landing_page"], by_lp)):
            b = bucket.setdefault(key, {"sessions": 0, "engaged": 0, "key_events": 0.0})
            for k in ("sessions", "engaged", "key_events"):
                b[k] += r[k]
    agg = lambda b, name: sorted(({name: k, **v, "engagement_rate": v["engaged"] / v["sessions"] if v["sessions"] else None}
                                   for k, v in b.items()), key=lambda x: -x["sessions"])
    tot = {k: sum(r[k] for r in rows) for k in ("sessions", "engaged", "key_events")}
    return {"totals": tot, "rows": rows, "by_source_medium": agg(by_sm, "source_medium"),
            "by_landing_page": agg(by_lp, "landing_page")}
