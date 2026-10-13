#!/usr/bin/env python3
"""tech-health-check: one daily check for the tech that silently loses leads.

Read-only on every platform. The only writes are optional: ClickUp fix tasks (--create-tasks)
and a Slack summary (--send).

  python3 scripts/health_check.py --demo                 # fixture data, no API calls
  python3 scripts/health_check.py                        # all active clients, print + write report
  python3 scripts/health_check.py --client "Example Clinic"
  python3 scripts/health_check.py --create-tasks         # one ClickUp task per problem, with the fix
  python3 scripts/health_check.py --send                 # Slack summary if anything is WARNING or worse

Checks per client: CRM key missing (new client with no Private Integration Token), CRM key
rejected, Meta ad account status (grace period, payment needed, disabled), Meta leads not
reaching the CRM (and since when), partial sync, ads not spending, pipeline frozen, landing
page down or SSL wrong, cold email inboxes disconnected. Agency level: sub-accounts in
GoHighLevel that have no entry in config.yaml (a new client nobody wired up).
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OUT = Path.cwd() / "tech-health-check-output"
STATE = HERE / "state"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"
GHL = "https://services.leadconnectorhq.com"
GRAPH = "https://graph.facebook.com/v21.0"
CRIT, WARN, INFO = "CRITICAL", "WARNING", "INFO"
META_STATUS = {1: None, 2: "disabled", 3: "unsettled (a payment failed)", 7: "pending risk review",
               8: "pending settlement", 9: "in grace period (the card failed, ads stop soon)",
               100: "pending closure", 101: "closed"}

# The fix for every problem. This text goes straight into the ClickUp task.
PLAYBOOK = {
    "pit-missing": ("This client has no CRM key (GoHighLevel Private Integration Token), so nothing about it is being checked. "
                    "Usually a new client that was onboarded without one.", [
        "Open the client's sub-account (not the agency view) > Settings > Private Integrations > Create new integration. Name it 'Health check (read-only)'.",
        "Tick only read scopes: contacts.readonly, opportunities.readonly, locations.readonly, workflows.readonly, forms.readonly.",
        "Copy the token (shown once) into ~/.claude/skills/.env under the name in config.yaml (token_env). Never paste it in chat or a task.",
        "Add the client to config.yaml with its location id (in the browser URL after /location/). Re-run the check.",
        "Make this step 1 of every new client onboarding."]),
    "pit-invalid": ("The CRM key for this client was rejected (401/403). It was deleted, expired, or the sub-account was paused, so this client is not being watched.", [
        "Check the sub-account still exists and is active (an inactive location also returns 401).",
        "Create a new Private Integration with the same read scopes (see pit-missing) and replace the token in .env.",
        "Re-run the check to confirm it reads again."]),
    "meta-account-status": ("The Meta ad account is not in normal status. Usually the card failed: the account goes into a grace period, then ads stop.", [
        "Ads Manager > Billing and payments: pay any balance owed and fix or replace the card.",
        "Ask the client to add a second (backup) payment method so one bounced card can't stop the ads.",
        "If it says disabled or risk review: Account Quality (business.facebook.com/accountquality) shows the reason and the request-review button.",
        "Once it's active, check the lead forms still reach the CRM (the sync check below) because a pause is when integrations most often drop."]),
    "sync-break": ("Meta is collecting leads but they are not reaching the CRM. Those people get no text, call or reminder.", [
        "Sub-account > Settings > Integrations > Facebook: check it says Connected and which Page it is on. Screenshot.",
        "In the Facebook integration settings choose 'select all Facebook pages', save, press Sync leads.",
        "Settings > Integrations > Facebook > Form Field Mapping: every live lead form must be listed and enabled. A new or duplicated form that isn't mapped is the most common cause.",
        "Still broken: Disconnect and Reconnect the Facebook integration (sometimes it takes two goes). Use a Facebook login that is admin on the client's Page.",
        "Recover what was missed: Integrations > Facebook > Troubleshooting > 'Leads are not syncing automatically' > Last 15 days > Sync Leads. Older than 15 days: download the CSV from the Meta form (kept 90 days) and import it.",
        "Recovered contacts DO NOT start any workflow (no tags, no texts, unassigned). Tag them (for example recovered-<date>), put them in a Smart List, and run a separate short reactivation (3 texts over 5 days, business hours, drip 25 every 30 minutes) after the client approves the wording. Never drop them into the normal new-lead workflow: it would say 'thanks for your enquiry' two weeks late.",
        "Also check: the business's Meta Business Settings > Integrations > Leads access must include LeadConnector for that Page."]),
    "sync-partial": ("Only some Meta leads are reaching the CRM. Usually one form out of several is not mapped.", [
        "Settings > Integrations > Facebook > Form Field Mapping: compare the list of forms with the live forms in Ads Manager. Map and enable the missing one.",
        "Check the lead workflow's trigger includes every live form, not just the old ones.",
        "Run Troubleshooting > Sync Leads for the last 15 days to recover the missing ones (see sync-break for how to treat recovered contacts)."]),
    "no-delivery": ("The ads spent nothing in the last day although they normally do.", [
        "Ads Manager: Delivery column for every campaign. Look for 'Not delivering', rejected ads, or ended schedules.",
        "Billing and payments: a failed card pauses everything (see meta-account-status).",
        "Account Quality: restrictions on the ad account, Page or person.",
        "If nothing is wrong, check the daily budgets and campaign end dates."]),
    "pipeline-frozen": ("New leads keep arriving but the pipeline has not changed for a day. The workflow that creates opportunities has probably stopped.", [
        "Automation > Workflows: open the new-lead workflow. Is it Published? Open Execution Logs for the last 24h and look for errors.",
        "Check the 'Create/Update Opportunity' step still points at a pipeline and stage that exist.",
        "Fix and re-publish, then add the missed contacts to the pipeline by hand."]),
    "site-down": ("A landing page or booking page is not loading, or its SSL certificate is wrong. Ad clicks are landing on an error.", [
        "Open the URL in a private window on your phone. Screenshot what you see.",
        "SSL error or 'not secure': the custom domain is pointing at the host but not attached to the site, or the certificate has not been issued. Attach the domain in the host (Netlify, GoHighLevel funnel domains) and wait for the certificate.",
        "404 or 5xx: the page or funnel step was renamed, unpublished or deleted. Restore it or point the ads at the right URL.",
        "Pause the ads that point at it if it can't be fixed within the hour."]),
    "cold-email-inbox": ("One or more cold email inboxes are disconnected or erroring, so sequences on them have stopped.", [
        "Instantly > Email accounts: filter by status. Reconnect any with an error (usually an expired app password or OAuth).",
        "Check warm-up is still on for reconnected inboxes.",
        "If many failed at once, check the domain's DNS (SPF, DKIM, DMARC) has not changed."]),
    "unmanaged-subaccount": ("This GoHighLevel sub-account exists in the agency but is not in config.yaml, so nobody is watching it. Usually a new client.", [
        "If it's a live client: create its read-only Private Integration (see pit-missing) and add it to config.yaml.",
        "If it's internal, a demo or a former client: add its location id to ghl_agency.ignore_locations."]),
}

CTX = ssl.create_default_context()
try:
    import certifi  # noqa
    CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    pass


class Api:
    """All network calls go through here so --demo can swap in fixtures."""
    def request(self, method, url, headers=None, body=None, timeout=30):
        data = json.dumps(body).encode() if body is not None else None
        h = {"User-Agent": UA, "Accept": "application/json", **(headers or {})}
        if data is not None:
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                txt = r.read().decode("utf-8", "ignore")
                return r.status, (json.loads(txt) if txt.strip().startswith(("{", "[")) else txt)
        except urllib.error.HTTPError as e:
            return e.code, None
        except ssl.SSLError as e:
            return "ssl", str(e)[:120]
        except Exception as e:
            return "error", str(e)[:120]


class DemoApi(Api):
    """Fixture rows: {"url": part of the URL, "body": part of the JSON body, "status", "data"}. First match wins."""
    def __init__(self, rows):
        self.rows = rows

    def request(self, method, url, headers=None, body=None, timeout=30):
        b = json.dumps(body or {})
        for r in self.rows:
            if r["url"] in url and r.get("body", "") in b:
                return r["status"], r.get("data")
        return 404, None


def load_yaml(p):
    import yaml  # pip install pyyaml
    return yaml.safe_load(Path(p).read_text())


def ms(dt):
    return int(dt.timestamp() * 1000)


def ghl_headers(tok):
    return {"Authorization": f"Bearer {tok}", "Version": "2021-07-28"}


def finding(client, check, sev, headline, lines):
    return {"client": client, "check": check, "severity": sev, "headline": headline, "lines": lines}


def check_client(api, c, now, state):
    name = c["name"]
    out = []
    g = c.get("ghl") or {}
    tok = os.environ.get(g.get("token_env") or "", "")
    loc = g.get("location_id")
    crm_ok = False
    if not tok or not loc:
        out.append(finding(name, "pit-missing", CRIT, f"{name}: no CRM key set up",
                           [f"token_env {g.get('token_env') or '(none)'} is {'empty' if g.get('token_env') else 'not set'}; location_id {'missing' if not loc else 'set'}"]))
    else:
        s, d = api.request("POST", f"{GHL}/contacts/search", ghl_headers(tok),
                           {"locationId": loc, "pageLimit": 1})
        if s in (401, 403):
            out.append(finding(name, "pit-invalid", CRIT, f"{name}: CRM key rejected ({s})", [f"POST /contacts/search returned {s}"]))
        elif s != 200:
            out.append(finding(name, "pit-invalid", WARN, f"{name}: CRM did not answer ({s})", [f"POST /contacts/search returned {s}"]))
        else:
            crm_ok = True

    m = c.get("meta") or {}
    meta_tok = os.environ.get(m.get("token_env") or "META_ACCESS_TOKEN", "")
    act = m.get("ad_account_id")
    meta_leads_24h = meta_leads_since = None
    if act and meta_tok:
        s, d = api.request("GET", f"{GRAPH}/{act}?" + urllib.parse.urlencode({"fields": "account_status,disable_reason,name", "access_token": meta_tok}))
        if s == 200 and isinstance(d, dict):
            st = d.get("account_status")
            if META_STATUS.get(st):
                out.append(finding(name, "meta-account-status", CRIT, f"{name}: Meta ad account {META_STATUS[st]}",
                                   [f"account_status={st} disable_reason={d.get('disable_reason')}"]))
        elif s in (400, 401, 403):
            out.append(finding(name, "meta-account-status", WARN, f"{name}: can't read the Meta ad account ({s})",
                               ["The system user token lost access to this ad account, or the token was revoked."]))
        since_day = (now - timedelta(days=14)).date().isoformat()
        q = {"fields": "spend,actions", "time_increment": 1, "access_token": meta_tok,
             "time_range": json.dumps({"since": since_day, "until": now.date().isoformat()})}
        s, d = api.request("GET", f"{GRAPH}/{act}/insights?" + urllib.parse.urlencode(q))
        if s == 200 and isinstance(d, dict):
            days = []
            for r in d.get("data", []):
                leads = sum(int(a.get("value", 0)) for a in r.get("actions", []) if a.get("action_type") == "lead")
                days.append((r["date_start"], float(r.get("spend", 0) or 0), leads))
            days.sort()
            meta_leads_24h = sum(l for day, _, l in days if day >= (now - timedelta(days=1)).date().isoformat())
            meta_leads_since = days
            spend_last = sum(sp for day, sp, _ in days if day == (now - timedelta(days=1)).date().isoformat())
            prior = [sp for day, sp, _ in days if day < (now - timedelta(days=1)).date().isoformat()][-7:]
            if prior and sum(prior) / len(prior) > 5 and spend_last == 0:
                out.append(finding(name, "no-delivery", WARN, f"{name}: ads spent nothing yesterday",
                                   [f"7-day average spend before that: {sum(prior)/len(prior):.2f}"]))

    if crm_ok and meta_leads_since is not None:
        match = [x.lower() for x in (m.get("lead_source_match") or ["facebook", "instagram"])]
        s, d = api.request("POST", f"{GHL}/contacts/search", ghl_headers(tok),
                           {"locationId": loc, "pageLimit": 100, "sort": [{"field": "dateAdded", "direction": "desc"}]})
        contacts = (d or {}).get("contacts", []) if s == 200 else []
        meta_contacts = [x for x in contacts if any(k in (x.get("source") or "").lower() for k in match)
                         or "meta" in [t.lower() for t in x.get("tags", [])]]
        cutoff = datetime.combine((now - timedelta(days=1)).date(), datetime.min.time(), tzinfo=timezone.utc)
        crm_24h = sum(1 for x in meta_contacts if x.get("dateAdded", "") >= cutoff.isoformat()[:19])
        last = meta_contacts[0]["dateAdded"][:16].replace("T", " ") + " UTC" if meta_contacts else "none in the last 100 contacts"
        if (meta_leads_24h or 0) >= 3 and crm_24h == 0:
            last_day = meta_contacts[0]["dateAdded"][:10] if meta_contacts else "0000-00-00"
            missed = sum(l for day, _, l in meta_leads_since if day >= last_day)
            out.append(finding(name, "sync-break", CRIT, f"{name}: Meta leads not reaching the CRM",
                               [f"Meta leads since yesterday 00:00 UTC: {meta_leads_24h}", "CRM Meta contacts since then: 0",
                                f"Last Meta lead that reached the CRM: {last}",
                                f"Meta leads since then (approx): {missed}"]))
        elif (meta_leads_24h or 0) >= 5 and crm_24h < 0.5 * meta_leads_24h:
            out.append(finding(name, "sync-partial", WARN, f"{name}: only some Meta leads reaching the CRM",
                               [f"Meta leads since yesterday 00:00 UTC: {meta_leads_24h}", f"CRM Meta contacts since then: {crm_24h}"]))
        s, d = api.request("GET", f"{GHL}/opportunities/search?" + urllib.parse.urlencode({"location_id": loc, "limit": 1}), ghl_headers(tok))
        if s == 200 and isinstance(d, dict):
            total = (d.get("meta") or {}).get("total")
            key = f"pipeline:{name}"
            prev = state.get(key)
            if prev and total == prev.get("total") and crm_24h >= 3 and \
                    now - datetime.fromisoformat(prev["at"]) >= timedelta(hours=22):
                out.append(finding(name, "pipeline-frozen", WARN, f"{name}: pipeline hasn't moved in a day",
                                   [f"Opportunities: {total} (same as {prev['at'][:16]})", f"New Meta contacts in the CRM: {crm_24h}"]))
            if not prev or prev.get("total") != total:
                state[key] = {"total": total, "at": now.isoformat()}

    for url in c.get("sites") or []:
        s, d = api.request("GET", url, headers={"Accept": "text/html"}, timeout=20)
        if s == "ssl":
            out.append(finding(name, "site-down", CRIT, f"{name}: SSL problem on {url}", [str(d)]))
        elif s == "error" or (isinstance(s, int) and s >= 400):
            out.append(finding(name, "site-down", CRIT, f"{name}: {url} returns {s}", [str(d)[:120] if d else ""]))
    return out


def check_agency(api, cfg):
    a = cfg.get("ghl_agency") or {}
    tok = os.environ.get(a.get("token_env") or "", "")
    if not tok or not a.get("company_id"):
        return []
    known = {(c.get("ghl") or {}).get("location_id") for c in cfg.get("clients", [])}
    ignore = set(a.get("ignore_locations") or [])
    s, d = api.request("GET", f"{GHL}/locations/search?" + urllib.parse.urlencode({"companyId": a["company_id"], "limit": 500}), ghl_headers(tok))
    if s != 200:
        return [finding("Agency", "pit-invalid", WARN, f"Agency key could not list sub-accounts ({s})", [])]
    out = []
    for l in (d or {}).get("locations", []):
        if l.get("id") not in known and l.get("id") not in ignore:
            out.append(finding(l.get("name") or l.get("id"), "unmanaged-subaccount", WARN,
                               f"{l.get('name')}: sub-account with no health check (new client without a CRM key?)",
                               [f"location id {l.get('id')}"]))
    return out


def check_instantly(api, cfg):
    key = os.environ.get("INSTANTLY_API_KEY", "")
    if not key or not cfg.get("instantly"):
        return []
    s, d = api.request("GET", "https://api.instantly.ai/api/v2/accounts?limit=100", {"Authorization": f"Bearer {key}"})
    if s != 200:
        return [finding("Cold email", "cold-email-inbox", WARN, f"Instantly did not answer ({s})", ["Check INSTANTLY_API_KEY."])]
    bad = [x.get("email") for x in (d or {}).get("items", []) if isinstance(x.get("status"), int) and x["status"] < 0]
    if bad:
        return [finding("Cold email", "cold-email-inbox", WARN, f"{len(bad)} cold email inbox(es) disconnected", bad[:20])]
    return []


def clickup(api, method, path, body=None):
    tok = os.environ.get("CLICKUP_API_TOKEN", "")
    return api.request(method, "https://api.clickup.com/api/v2" + path, {"Authorization": tok}, body)


def route_tasks(api, cfg, findings, now, state):
    """One task per client+check, daily comment while open, 'looks fixed' when it clears."""
    r = cfg.get("routing") or {}
    lst, who = r.get("clickup_list_id"), r.get("clickup_assignee_id")
    if not (lst and os.environ.get("CLICKUP_API_TOKEN")):
        return ["routing: no clickup_list_id or CLICKUP_API_TOKEN, no tasks created"]
    log, today = [], now.date().isoformat()
    tasks = state.setdefault("tasks", {})
    firing = {}
    for f in findings:
        if f["severity"] in (CRIT, WARN):
            firing[f"{f['client']}|{f['check']}"] = f
    for key, f in firing.items():
        rec = tasks.get(key)
        if rec:
            s, t = clickup(api, "GET", f"/task/{rec['id']}")
            done = s == 200 and ((t or {}).get("status") or {}).get("type") in ("done", "closed")
            if not done:
                if rec.get("last") != today:
                    clickup(api, "POST", f"/task/{rec['id']}/comment",
                            {"comment_text": "Health check: still happening today.\n" + "\n".join(f["lines"]), "notify_all": True})
                    rec["last"] = today
                    log.append(f"comment {rec['id']} {key}")
                continue
        what, steps = PLAYBOOK[f["check"]]
        desc = "\n".join([f"**{f['headline']}**", "", "## What's wrong", what, "", "## The numbers",
                          *[f"* {l}" for l in f["lines"] if l], "", "## How to fix it",
                          *[f"{i}. {s}" for i, s in enumerate(steps, 1)], "", "## Done when",
                          "Post what you found and changed as a comment. If it's still happening tomorrow the check comments here instead of opening a new task.",
                          "", "_Created by tech-health-check._"])
        body = {"name": ("URGENT: " if f["severity"] == CRIT else "") + f["headline"], "markdown_description": desc,
                "priority": 1 if f["severity"] == CRIT else 2, "tags": ["tech-health"],
                "due_date": ms(now + timedelta(hours=4 if f["severity"] == CRIT else 24)), "due_date_time": True}
        if who:
            body["assignees"] = [int(who)]
        s, t = clickup(api, "POST", f"/list/{lst}/task", body)
        if s == 200:
            tasks[key] = {"id": t.get("id"), "opened": today, "last": today}
            log.append(f"created {t.get('id')} {key}")
        else:
            log.append(f"create failed {s} {key}")
    checked = {f"{c['name']}" for c in cfg.get("clients", []) if c.get("active", True)}
    for key in [k for k in tasks if k not in firing and k.split("|")[0] in checked]:
        rec = tasks.pop(key)
        clickup(api, "POST", f"/task/{rec['id']}/comment",
                {"comment_text": "Health check: this looks fixed today. Close the task once you've checked.", "notify_all": True})
        log.append(f"resolved {key}")
    return log


def write_report(findings, now):
    OUT.mkdir(exist_ok=True)
    (OUT / "findings.json").write_text(json.dumps(findings, indent=1))
    lines = [f"# Tech health check, {now:%Y-%m-%d %H:%M} UTC", ""]
    if not findings:
        lines.append("All clear: every check passed.")
    for sev in (CRIT, WARN, INFO):
        group = [f for f in findings if f["severity"] == sev]
        if group:
            lines.append(f"## {sev} ({len(group)})")
            for f in group:
                lines.append(f"- **{f['headline']}** ({f['check']})")
                lines += [f"  - {l}" for l in f["lines"] if l]
                lines.append(f"  - Fix: {PLAYBOOK[f['check']][1][0]}")
            lines.append("")
    (OUT / "REPORT.md").write_text("\n".join(lines))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--client")
    ap.add_argument("--create-tasks", action="store_true")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--config", default=str(HERE / "config.yaml"))
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    if a.demo:
        cfg = load_yaml(HERE / "fixtures" / "demo_config.yaml")
        api = DemoApi(json.loads((HERE / "fixtures" / "demo_api.json").read_text()))
        for k, v in (cfg.get("demo_env") or {}).items():
            os.environ.setdefault(k, v)
    else:
        if not Path(a.config).exists():
            sys.exit("No config.yaml. Copy config.example.yaml to config.yaml and follow SETUP.md.")
        cfg, api = load_yaml(a.config), Api()
    STATE.mkdir(exist_ok=True)
    sp = STATE / ("demo_state.json" if a.demo else "state.json")
    state = json.loads(sp.read_text()) if sp.exists() else {}
    findings = []
    for c in cfg.get("clients", []):
        if not c.get("active", True) or (a.client and c["name"] != a.client):
            continue
        findings += check_client(api, c, now, state)
    if not a.client:
        findings += check_agency(api, cfg) + check_instantly(api, cfg)
    print(write_report(findings, now))
    if a.create_tasks and not a.demo:
        for line in route_tasks(api, cfg, findings, now, state):
            print(line)
    if a.send and not a.demo and any(f["severity"] in (CRIT, WARN) for f in findings):
        hook = os.environ.get((cfg.get("routing") or {}).get("slack_webhook_env") or "SLACK_WEBHOOK_URL", "")
        if hook:
            txt = "\n".join(f"{'🔴' if f['severity'] == CRIT else '🟡'} {f['headline']}" for f in findings if f["severity"] != INFO)
            api.request("POST", hook, body={"text": "Tech health check\n" + txt})
    tmp = sp.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    os.replace(tmp, sp)
    return 1 if any(f["severity"] == CRIT for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
