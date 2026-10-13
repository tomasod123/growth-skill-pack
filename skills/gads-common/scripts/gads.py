#!/usr/bin/env python3
"""Google Ads reader (READ-ONLY). Python stdlib only (certifi used if installed).

Credentials come from environment variables (load them first:
`set -a; source ~/.claude/skills/.env; set +a`):

  GOOGLE_ADS_DEVELOPER_TOKEN     from the manager account: Tools > API Center
  GOOGLE_ADS_CLIENT_ID           OAuth client (Desktop app) from Google Cloud Console
  GOOGLE_ADS_CLIENT_SECRET       same OAuth client
  GOOGLE_ADS_REFRESH_TOKEN       made once with: gads.py login
  GOOGLE_ADS_LOGIN_CUSTOMER_ID   manager account id, 10 digits, no dashes (optional if you
                                 sign in with a user who has direct access to the account)
  GOOGLE_ADS_CUSTOMER_ID         default account to read (optional; any command takes one)
  GOOGLE_ADS_API_VERSION         optional override, default below

Commands
  gads.py login [--save] [--port N]  one-time browser sign-in; prints GOOGLE_ADS_REFRESH_TOKEN.
                                     --save appends it to ~/.claude/skills/.env (owner-only file)
  gads.py doctor                     what works and what is missing, in order, with the fix per line
  gads.py accounts                   every client account under the manager (login customer id)
  gads.py query [CUSTOMER] "GAQL"    any read query, prints JSON rows
  gads.py snapshot [CUSTOMER] [--days N]
                                     campaigns (status, serving, why, budget, spend, clicks,
                                     conversions), live ads' final URLs + approval, conversion
                                     actions (primary? counted ONE or MANY? origin)

CUSTOMER = 10 digits, dashes optional. Defaults to GOOGLE_ADS_CUSTOMER_ID.
The adwords scope can technically write, but this script only ever calls googleAds:search and
customers:listAccessibleCustomers. Never add a mutate call. Revoke access any time at
https://myaccount.google.com/permissions
"""
import datetime as dt
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = ssl.create_default_context()

# Google sunsets each API version about a year after release. If calls 404 on the version path,
# bump this (or set GOOGLE_ADS_API_VERSION) to the newest one listed at
# https://developers.google.com/google-ads/api/docs/sunset-dates
API = os.environ.get("GOOGLE_ADS_API_VERSION", "v25")
BASE = f"https://googleads.googleapis.com/{API}"
SHARED_ENV = os.path.expanduser("~/.claude/skills/.env")
SCOPES = " ".join([
    "https://www.googleapis.com/auth/adwords",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
])
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def env(name):
    return (os.environ.get(name) or "").strip().strip('"').strip("'")


def cid(x):
    x = (x or "").replace("-", "").strip()
    if not (x.isdigit() and len(x) == 10):
        die(f"customer id must be 10 digits (dashes optional), got {x!r}")
    return x


def manager():
    m = env("GOOGLE_ADS_LOGIN_CUSTOMER_ID").replace("-", "")
    return cid(m) if m else ""


def default_customer():
    c = env("GOOGLE_ADS_CUSTOMER_ID")
    if not c:
        die("No customer id given and GOOGLE_ADS_CUSTOMER_ID is not set.")
    return cid(c)


def http(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, {"raw": body[:400].decode("utf-8", "replace")}


def access_token():
    missing = [n for n in ("GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN")
               if not env(n)]
    if missing:
        die("Missing " + ", ".join(missing) + ". Load ~/.claude/skills/.env "
            "(set -a; source ~/.claude/skills/.env; set +a). No refresh token yet? Run: gads.py login")
    data = urllib.parse.urlencode({"client_id": env("GOOGLE_ADS_CLIENT_ID"),
                                   "client_secret": env("GOOGLE_ADS_CLIENT_SECRET"),
                                   "refresh_token": env("GOOGLE_ADS_REFRESH_TOKEN"),
                                   "grant_type": "refresh_token"}).encode()
    st, t = http(TOKEN_URI, data)
    if st != 200:
        die(f"Refresh token rejected ({st}: {t.get('error_description') or t.get('error') or t}).\n"
            "  -> If the OAuth consent screen is in Testing mode, refresh tokens expire after 7 days: "
            "run gads.py login again, or publish the app (In production) to stop the expiry.\n"
            "  -> invalid_client means GOOGLE_ADS_CLIENT_ID / _SECRET do not match the client that "
            "made the refresh token.")
    return t["access_token"]


def headers(tok, login=True):
    h = {"Authorization": "Bearer " + tok, "Content-Type": "application/json"}
    if env("GOOGLE_ADS_DEVELOPER_TOKEN"):
        h["developer-token"] = env("GOOGLE_ADS_DEVELOPER_TOKEN")
    if login and manager():
        h["login-customer-id"] = manager()
    return h


def explain(st, body):
    err = body.get("error", body) if isinstance(body, dict) else body
    msg = json.dumps(err)[:900]
    hints = []
    if "SERVICE_DISABLED" in msg or "has not been used in project" in msg:
        hints.append("Google Ads API is not enabled on the Cloud project that owns your OAuth client: "
                     "Cloud Console > APIs & Services > Library > Google Ads API > Enable")
    if "DEVELOPER_TOKEN_NOT_APPROVED" in msg or "only approved for use with test accounts" in msg:
        hints.append("Developer token is Test-account-only: apply for Explorer or Basic access in the "
                     "manager account under Tools > API Center")
    elif "DEVELOPER_TOKEN" in msg:
        hints.append("Developer token missing or invalid: set GOOGLE_ADS_DEVELOPER_TOKEN "
                     "(manager account > Tools > API Center)")
    if "USER_PERMISSION_DENIED" in msg:
        hints.append("The signed-in user cannot reach this account through the login customer id. "
                     "Check GOOGLE_ADS_LOGIN_CUSTOMER_ID is the manager the account is linked under "
                     "(10 digits, no dashes), and that the account is linked")
    if "CUSTOMER_NOT_ENABLED" in msg:
        hints.append("The account is cancelled, suspended or not yet set up")
    if "insufficient" in msg.lower() and "scope" in msg.lower():
        hints.append("The refresh token lacks the adwords scope: run gads.py login again")
    if st == 404:
        hints.append(f"API version {API} may be sunset: set GOOGLE_ADS_API_VERSION to the newest version")
    return f"HTTP {st}: {msg}" + "".join("\n  -> " + h for h in hints)


def search(customer, q, tok=None):
    """Paginated GAQL read. Returns a list of row dicts (camelCase keys, as REST returns them)."""
    tok = tok or access_token()
    rows, page = [], None
    while True:
        body = {"query": q}
        if page:
            body["pageToken"] = page
        st, r = http(f"{BASE}/customers/{cid(customer)}/googleAds:search", json.dumps(body).encode(), headers(tok))
        if st != 200:
            die(explain(st, r))
        rows += r.get("results", [])
        page = r.get("nextPageToken")
        if not page:
            return rows


def g(row, path):
    for k in path.split("."):
        row = (row or {}).get(k)
    return row


def whoami(tok):
    st, r = http("https://www.googleapis.com/oauth2/v3/userinfo", headers={"Authorization": "Bearer " + tok})
    return r.get("email", "") if st == 200 else ""


def cmd_login(a):
    """Loopback OAuth flow with PKCE for a Desktop app client. Prints the refresh token."""
    import base64
    import hashlib
    import secrets
    import threading
    import webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer

    client_id, secret = env("GOOGLE_ADS_CLIENT_ID"), env("GOOGLE_ADS_CLIENT_SECRET")
    if not client_id or not secret:
        die("Set GOOGLE_ADS_CLIENT_ID and GOOGLE_ADS_CLIENT_SECRET first (Desktop app OAuth client).")
    port = 0
    if "--port" in a:
        i = a.index("--port") + 1
        port = int(a[i]) if i < len(a) and a[i].isdigit() else 0
    got = {}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h2>Signed in. You can close this tab.</h2>")

        def log_message(self, *x):
            pass

    srv = HTTPServer(("127.0.0.1", port), H)
    redirect = "http://localhost:%d" % srv.server_port
    verifier = base64.urlsafe_b64encode(os.urandom(40)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(16)
    url = AUTH_URI + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": redirect,
        "scope": SCOPES, "access_type": "offline", "prompt": "consent",
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})
    print("Open this URL, sign in as a Google user with access to the Google Ads manager account, "
          "and allow access.\n(On a remote server: run with --port 8085 and first "
          "`ssh -L 8085:localhost:8085 <server>` from your laptop, then open the URL locally.)\n")
    print(url + "\n")
    threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    for _ in range(10):
        srv.handle_request()
        if "code" in got or "error" in got:
            break
    srv.server_close()
    if got.get("error"):
        die("Sign-in refused: %s" % got["error"])
    if "code" not in got or got.get("state") != state:
        die("Sign-in did not complete.")
    data = urllib.parse.urlencode({
        "code": got["code"], "client_id": client_id, "client_secret": secret,
        "redirect_uri": redirect, "grant_type": "authorization_code",
        "code_verifier": verifier}).encode()
    st, t = http(TOKEN_URI, data)
    if st != 200 or "refresh_token" not in t:
        die("Token exchange failed (%s: %s)" % (st, t))
    who = whoami(t["access_token"])
    line = "GOOGLE_ADS_REFRESH_TOKEN=" + t["refresh_token"]
    if "--save" in a:
        lines = []
        if os.path.exists(SHARED_ENV):
            lines = [x for x in open(SHARED_ENV).read().splitlines()
                     if not x.startswith("GOOGLE_ADS_REFRESH_TOKEN=")]
        lines.append(line)
        os.makedirs(os.path.dirname(SHARED_ENV), exist_ok=True)
        fd = os.open(SHARED_ENV, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Signed in as {who or 'unknown'}. Refresh token saved to {SHARED_ENV} "
              f"(ends ...{t['refresh_token'][-4:]}). Reload the env file before the next command.")
    else:
        print(f"Signed in as {who or 'unknown'}. Add this line to {SHARED_ENV} "
              "(do not paste it into chat):\n")
        print(line)


def cmd_doctor():
    ok = True

    def line(good, text):
        nonlocal ok
        ok = ok and good
        print(("OK   " if good else "TODO ") + text)

    for n, why in [("GOOGLE_ADS_DEVELOPER_TOKEN", "manager account > Tools > API Center"),
                   ("GOOGLE_ADS_CLIENT_ID", "Cloud Console > APIs & Services > Credentials"),
                   ("GOOGLE_ADS_CLIENT_SECRET", "same OAuth client"),
                   ("GOOGLE_ADS_REFRESH_TOKEN", "run: gads.py login")]:
        line(bool(env(n)), f"{n} set" + ("" if env(n) else f" ({why})"))
    print(("OK   " if manager() else "NOTE ") + "GOOGLE_ADS_LOGIN_CUSTOMER_ID "
          + (f"= {manager()}" if manager() else "not set (fine only if the user has direct access to each account)"))
    if not all(env(n) for n in ("GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN")):
        print("\nStop here: fill the TODO lines first.")
        return 1
    tok = access_token()
    who = whoami(tok)
    line(True, f"Refresh token works, signed in as {who or 'unknown'}")
    st, r = http(f"{BASE}/customers:listAccessibleCustomers", headers=headers(tok, login=False))
    if st != 200:
        line(False, "List accessible accounts: " + explain(st, r))
        return 1
    names = [x.split("/")[-1] for x in r.get("resourceNames", [])]
    line(True, f"API {API} reachable; this user reaches {len(names)} account(s) directly")
    m = manager()
    if m:
        line(m in names, f"Manager {m} " + ("is directly accessible" if m in names else
                                             "is NOT directly accessible to this user (add the user to the manager account)"))
        st, r = http(f"{BASE}/customers/{m}/googleAds:search",
                     json.dumps({"query": "SELECT customer_client.id FROM customer_client "
                                          "WHERE customer_client.level = 1"}).encode(), headers(tok))
        line(st == 200, "Read client accounts under the manager" + ("" if st == 200 else ": " + explain(st, r)))
        if st == 200:
            ids = [str(g(x, "customerClient.id")) for x in search(
                m, "SELECT customer_client.id FROM customer_client WHERE customer_client.level = 1", tok)]
            print(f"     {len(ids)} client account(s) linked under the manager")
            c = env("GOOGLE_ADS_CUSTOMER_ID").replace("-", "")
            if c:
                line(c in ids or c in names, f"Default customer {c} reachable")
    print("\nAll good." if ok else "\nFix the TODO lines top to bottom.")
    return 0 if ok else 1


def cmd_accounts():
    m = manager()
    if not m:
        tok = access_token()
        st, r = http(f"{BASE}/customers:listAccessibleCustomers", headers=headers(tok, login=False))
        if st != 200:
            die(explain(st, r))
        for x in r.get("resourceNames", []):
            i = x.split("/")[-1]
            print(f"{i[:3]}-{i[3:6]}-{i[6:]}  (direct access; set GOOGLE_ADS_LOGIN_CUSTOMER_ID to list a manager's clients)")
        return
    q = ("SELECT customer_client.id, customer_client.descriptive_name, customer_client.currency_code, "
         "customer_client.status, customer_client.manager FROM customer_client WHERE customer_client.level = 1")
    for r in sorted(search(m, q), key=lambda r: g(r, "customerClient.descriptiveName") or ""):
        i = str(g(r, "customerClient.id"))
        print(f"{i[:3]}-{i[3:6]}-{i[6:]}  {(g(r, 'customerClient.status') or ''):<10} {g(r, 'customerClient.currencyCode')}  "
              f"{'MANAGER ' if g(r, 'customerClient.manager') else ''}{g(r, 'customerClient.descriptiveName')}")


def money(micros):
    return round(int(micros or 0) / 1e6, 2)


def cmd_snapshot(customer, days):
    tok = access_token()
    end = dt.date.today()
    start = end - dt.timedelta(days=days - 1)
    during = f"segments.date BETWEEN '{start}' AND '{end}'"
    out = {"customer": customer, "window": f"{start}..{end} (account time zone)"}
    acct = search(customer, "SELECT customer.descriptive_name, customer.currency_code, customer.time_zone, "
                            "customer.auto_tagging_enabled, customer.status FROM customer", tok)
    c0 = acct[0].get("customer", {}) if acct else {}
    out["account"] = {**c0, "autoTaggingEnabled": bool(c0.get("autoTaggingEnabled"))} if acct else None
    camps = search(customer, "SELECT campaign.id, campaign.name, campaign.status, campaign.serving_status, "
                             "campaign.primary_status, campaign.primary_status_reasons, "
                             "campaign.advertising_channel_type, campaign_budget.amount_micros FROM campaign "
                             "WHERE campaign.status != 'REMOVED'", tok)
    perf = {g(r, "campaign.id"): r.get("metrics", {}) for r in search(customer,
            "SELECT campaign.id, metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions, "
            f"metrics.all_conversions FROM campaign WHERE {during}", tok)}
    out["campaigns"] = [{
        "name": g(c, "campaign.name"), "status": g(c, "campaign.status"),
        "serving": g(c, "campaign.servingStatus"), "primary_status": g(c, "campaign.primaryStatus"),
        "why": g(c, "campaign.primaryStatusReasons"), "type": g(c, "campaign.advertisingChannelType"),
        "daily_budget": money(g(c, "campaignBudget.amountMicros")),
        "spend": money(perf.get(g(c, "campaign.id"), {}).get("costMicros")),
        "impressions": int(perf.get(g(c, "campaign.id"), {}).get("impressions", 0)),
        "clicks": int(perf.get(g(c, "campaign.id"), {}).get("clicks", 0)),
        "conversions": perf.get(g(c, "campaign.id"), {}).get("conversions", 0),
    } for c in camps]
    ads = search(customer, "SELECT campaign.name, ad_group.name, ad_group_ad.status, ad_group_ad.ad.final_urls, "
                           "ad_group_ad.policy_summary.approval_status FROM ad_group_ad "
                           "WHERE ad_group_ad.status != 'REMOVED' AND campaign.status != 'REMOVED'", tok)
    out["ads"] = [{"campaign": g(a, "campaign.name"), "ad_group": g(a, "adGroup.name"),
                   "status": g(a, "adGroupAd.status"), "approval": g(a, "adGroupAd.policySummary.approvalStatus"),
                   "final_urls": g(a, "adGroupAd.ad.finalUrls")} for a in ads]
    conv = search(customer, "SELECT conversion_action.name, conversion_action.status, conversion_action.type, "
                            "conversion_action.origin, conversion_action.primary_for_goal, "
                            "conversion_action.counting_type, conversion_action.category, "
                            "conversion_action.include_in_conversions_metric FROM conversion_action "
                            "WHERE conversion_action.status != 'REMOVED'", tok)
    # REST omits false/0/default fields, so spell every one out: absent primaryForGoal means NOT primary.
    out["conversion_actions"] = [{
        "name": g(c, "conversionAction.name"), "status": g(c, "conversionAction.status") or "",
        "type": g(c, "conversionAction.type") or "", "origin": g(c, "conversionAction.origin") or "",
        "category": g(c, "conversionAction.category") or "",
        "primary_for_goal": bool(g(c, "conversionAction.primaryForGoal")),
        "include_in_conversions_metric": bool(g(c, "conversionAction.includeInConversionsMetric")),
        "counting_type": g(c, "conversionAction.countingType") or "",
    } for c in conv]
    print(json.dumps(out, indent=1))


def _is_cid(x):
    return x.replace("-", "").isdigit() and len(x.replace("-", "")) == 10


def main(a):
    if not a or a[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    c = a[0]
    if c == "login":
        cmd_login(a[1:])
    elif c == "doctor":
        return cmd_doctor()
    elif c == "accounts":
        cmd_accounts()
    elif c == "query" and len(a) >= 2:
        customer, q = (a[1], a[2]) if len(a) >= 3 and _is_cid(a[1]) else (default_customer(), a[1])
        print(json.dumps(search(customer, q), indent=1))
    elif c == "snapshot":
        rest = a[1:]
        customer = rest[0] if rest and _is_cid(rest[0]) else default_customer()
        days = 1
        if "--days" in rest:
            i = rest.index("--days") + 1
            if i >= len(rest) or not rest[i].isdigit() or int(rest[i]) < 1:
                die("--days needs a whole number, e.g. --days 7")
            days = int(rest[i])
        cmd_snapshot(cid(customer), days)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
