#!/usr/bin/env python3
"""lp-webhook-tracking / webhook_check.py

Three subcommands:

  payload  Print the full sample payload (every field the landing-page form sends) and a curl line.
           No network. Use it so GHL's webhook mapping screen has seen every field.
  send     POST the sample payload to the GHL inbound webhook. Creates ONE real contact, so it refuses
           to run without --yes and without an email containing --test-marker.
  verify   Read-only. POST /contacts/search (a read) + GET /contacts/{id} with the Private Integration
           token, then report the tag lp-<slug> and every mapped custom field, filled or empty.

  set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/lp-webhook-tracking/scripts/webhook_check.py payload --slug example-service
  set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/lp-webhook-tracking/scripts/webhook_check.py send --webhook "$GHL_WEBHOOK_URL" --email you+lptest-1@example.com --phone <unique> --slug example-service --yes
  set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/lp-webhook-tracking/scripts/webhook_check.py verify --email you+lptest-1@example.com --slug example-service

Env: GHL_API_KEY, GHL_LOCATION_ID (verify), GHL_WEBHOOK_URL (send, optional if --webhook given),
     LP_TEST_MARKER (optional default for --test-marker). Never prints the token. Stdlib only.
"""
import argparse, json, os, ssl, sys, time, urllib.error, urllib.request

BASE = "https://services.leadconnectorhq.com"
API_VERSION = "2021-07-28"
# Cloudflare 1010-blocks the default urllib user agent on leadconnectorhq.com.
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

AD_FIELDS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "gclid", "fbclid",
             "wbraid", "gbraid", "campaign_id", "adgroup_id", "matchtype", "device", "network", "loc"]


def ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def default_email():
    """Default test email always carries the test marker, so the Real-enquiry branch filters it out."""
    marker = os.environ.get("LP_TEST_MARKER", "+lptest") or "+lptest"
    return "test%s@example.com" % marker if marker.startswith("+") else "test+%s@example.com" % marker


def sample(a):
    full = a.name.strip()
    parts = full.split(" ")
    p = {
        "first_name": parts[0], "last_name": " ".join(parts[1:]), "full_name": full,
        "phone": a.phone or "", "email": a.email or default_email(),
        "message": "Test enquiry, please ignore", "service": a.slug,
        "service_label": a.label or a.slug.replace("-", " ").title(),
        "page_url": "https://example.com/%s/" % a.slug, "consent": "yes",
        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    for k in AD_FIELDS:
        p[k] = "test-" + k.replace("_", "-")
    return p


def req(method, url, body=None, token=None):
    h = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": UA}
    if token:
        h["Authorization"] = "Bearer " + token
        h["Version"] = API_VERSION
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, context=ctx(), timeout=45) as resp:
            txt = resp.read().decode() or "{}"
            try:
                return resp.status, json.loads(txt)
            except Exception:
                return resp.status, {"_text": txt[:300]}
    except urllib.error.HTTPError as e:
        return e.code, {"_error": e.read().decode()[:400]}
    except Exception as e:
        return 0, {"_error": str(e)[:300]}


def cmd_payload(a):
    p = sample(a)
    print(json.dumps(p, indent=2))
    print("\ncurl -X POST '<webhook url>' -H 'Content-Type: application/json' -d '%s'" % json.dumps(p))


def cmd_send(a):
    url = a.webhook or os.environ.get("GHL_WEBHOOK_URL", "")
    if not url:
        sys.exit("ERROR: pass --webhook or set GHL_WEBHOOK_URL")
    if not a.email or a.test_marker.lower() not in a.email.lower():
        sys.exit("ERROR: --email must contain the test marker %r so the workflow's Real-enquiry branch "
                 "sends it to END and nobody is alerted." % a.test_marker)
    if not a.yes:
        sys.exit("Refusing to send: this creates a real contact. Re-run with --yes once the Real-enquiry "
                 "branch is confirmed.")
    st, body = req("POST", url, sample(a))
    print("HTTP %s  %s" % (st, json.dumps(body)[:300]))
    print("A published workflow replies with an execution message; a draft replies 'test request received'.")
    print("Wait ~45 s, then run: verify --email %s --slug %s" % (a.email, a.slug))


def cmd_verify(a):
    token, loc = os.environ.get("GHL_API_KEY"), a.location or os.environ.get("GHL_LOCATION_ID", "")
    if not token or not loc:
        sys.exit("ERROR: GHL_API_KEY and GHL_LOCATION_ID must be set "
                 "(set -a; source ~/.claude/skills/.env; set +a)")
    st, res = req("POST", BASE + "/contacts/search", {"locationId": loc, "query": a.email, "pageLimit": 5}, token)
    if st != 200:
        sys.exit("contacts/search HTTP %s %s" % (st, json.dumps(res)[:300]))
    hits = [c for c in res.get("contacts", []) if (c.get("email") or "").lower() == a.email.lower()]
    if not hits:
        print("NOT FOUND: no contact with email %s. Wait longer, check the workflow is published, or the "
              "email/phone matched an older contact (GHL merges on both)." % a.email)
        return 1
    cid = hits[0]["id"]
    st, full = req("GET", BASE + "/contacts/" + cid, None, token)
    c = full.get("contact", {}) if st == 200 else hits[0]
    tags = c.get("tags") or []
    want = "lp-" + a.slug if a.slug else None
    print("contact   %s %s | email %s | phone %s" % (c.get("firstName"), c.get("lastName"), c.get("email"), c.get("phone")))
    print("tags      %s" % ", ".join(tags))
    ok = True
    if want:
        print("tag %-22s %s" % (want, "OK" if want in tags else "MISSING"))
        ok &= want in tags
    if not c.get("lastName"):
        print("last name EMPTY  (map last_name in the Create/Update Contact action)")
        ok = False
    # custom field names need the field list to be readable
    names = {}
    st, cf = req("GET", BASE + "/locations/%s/customFields" % loc, None, token)
    if st == 200:
        names = {f.get("id"): f.get("name") for f in cf.get("customFields", [])}
    vals = {x.get("id"): x.get("value") for x in (c.get("customFields") or [])}
    print("\ncustom fields on the contact:")
    for fid, name in sorted(names.items(), key=lambda x: str(x[1])):
        if fid in vals or any(k.replace("_", " ") in str(name).lower() for k in AD_FIELDS + ["landing page", "click id"]):
            v = vals.get(fid)
            print("  %-28s %s" % (name, v if v not in (None, "") else "EMPTY"))
            if v in (None, ""):
                ok = False
    if not names:
        print("  (customFields not readable, HTTP %s; raw values: %s)" % (st, json.dumps(vals)[:300]))
    print("\nRESULT: %s" % ("PASS" if ok else "CHECK THE EMPTY / MISSING ITEMS"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="Landing page -> GHL webhook test helper.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("payload", "send", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--slug", default="example-service", help="SERVICE_SLUG of the page")
        p.add_argument("--email", default="")
        if name != "verify":
            p.add_argument("--label", default="", help="SERVICE_LABEL")
            p.add_argument("--name", default="Test Lead", help="full name to send")
            p.add_argument("--phone", default="", help="a unique phone per test")
        if name == "send":
            p.add_argument("--webhook", default="")
            p.add_argument("--test-marker", default=os.environ.get("LP_TEST_MARKER", "+lptest"),
                           help="string the test email must contain (default $LP_TEST_MARKER or +lptest)")
            p.add_argument("--yes", action="store_true", help="really send (creates one contact)")
        if name == "verify":
            p.add_argument("--location", default="")
    a = ap.parse_args()
    rc = {"payload": cmd_payload, "send": cmd_send, "verify": cmd_verify}[a.cmd](a)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
