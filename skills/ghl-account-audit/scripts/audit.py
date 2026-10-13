#!/usr/bin/env python3
"""
ghl-account-audit / audit.py

READ-ONLY sweep of a GoHighLevel (GHL) sub-account.
GET requests only. Never writes, never messages, never changes a setting.

Usage:
  set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ghl-account-audit/scripts/audit.py \
      --client    "Clinic A" \
      --expect-address "1 Example Street, Exampletown AB1 2CD" \
      --expect-phone   "<the business's real main line>" \
      --country   ANY        # or UK, IE, AU, US

Reads the token from the env var named by --token-env (default GHL_API_KEY) and the
location id from --location or GHL_LOCATION_ID. Never prints the token.
Output goes to --out (default ./ghl-account-audit-output/).
Stdlib only (certifi used if installed). Exits 0 always (an audit is not a test);
prints the P0 count. Exits 2 if the token or location id is missing.
"""
import argparse, json, os, re, ssl, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = "https://services.leadconnectorhq.com"
API_VERSION = "2021-07-28"
# Cloudflare 1010-blocks default urllib/curl user agents on leadconnectorhq.com.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# name -> (path template, key that holds the list, note)
ENDPOINTS = [
    ("location",         "/locations/{loc}",                                              None),
    ("users",            "/users/?locationId={loc}",                                      "users"),
    ("phone_numbers",    "/phone-system/numbers/location/{loc}",                          "numbers"),
    ("custom_values",    "/locations/{loc}/customValues",                                 "customValues"),
    ("custom_fields",    "/locations/{loc}/customFields",                                 "customFields"),
    ("tags",             "/locations/{loc}/tags",                                         "tags"),
    ("sms_templates",    "/locations/{loc}/templates?originId={loc}&deleted=false&limit=100", "templates"),
    ("email_templates",  "/emails/builder?locationId={loc}&limit=100",                    "builders"),
    ("workflows",        "/workflows/?locationId={loc}",                                  "workflows"),
    ("calendars",        "/calendars/?locationId={loc}",                                  "calendars"),
    ("calendar_groups",  "/calendars/groups?locationId={loc}",                            "groups"),
    ("forms",            "/forms/?locationId={loc}&limit=100",                            "forms"),
    ("form_submissions", "/forms/submissions?locationId={loc}&limit=100",                 "submissions"),
    ("surveys",          "/surveys/?locationId={loc}&limit=50",                          "surveys"),
    ("survey_submissions","/surveys/submissions?locationId={loc}&limit=20",              "submissions"),
    ("funnels",          "/funnels/funnel/list?locationId={loc}",                         "funnels"),
    ("pipelines",        "/opportunities/pipelines?locationId={loc}",                     "pipelines"),
    ("opportunities",    "/opportunities/search?location_id={loc}&limit=100",             "opportunities"),
    ("conversations",    "/conversations/search?locationId={loc}&limit=100",              "conversations"),
    ("social_accounts",  "/social-media-posting/{loc}/accounts",                          None),
    ("payment_providers","/payments/integrations/provider/whitelabel?altId={loc}&altType=location", "providers"),
    ("payment_orders",   "/payments/orders?altId={loc}&altType=location&limit=20",        "data"),
    ("products",         "/products/?locationId={loc}&limit=100",                         "products"),
    ("links",            "/links/?locationId={loc}",                                      "links"),
    ("businesses",       "/businesses/?locationId={loc}",                                 "businesses"),
    ("campaigns",        "/campaigns/?locationId={loc}",                                  "campaigns"),
    ("objects",          "/objects/?locationId={loc}",                                    "objects"),
    ("voice_ai_agents",  "/voice-ai/agents?locationId={loc}",                             "agents"),
    ("blogs",            "/blogs/site/all?locationId={loc}&limit=20",                     "data"),
    ("media",            "/medias/files?altId={loc}&altType=location&limit=20&type=file", "files"),
    ("email_schedules",  "/emails/schedule?locationId={loc}",                             "schedules"),
    ("recurring_tasks",  "/locations/{loc}/recurring-tasks",                              "recurringTasks"),
    ("store_setting",    "/store/store-setting?altId={loc}&altType=location",             None),
]

# Mobile-number shapes per market (spaces, brackets and dashes are stripped first).
MOBILE = {
    "UK": r"^\+?(44|0)7\d{9}$",
    "IE": r"^\+?(353|0)8[35-9]\d{7}$",
    "AU": r"^\+?(61|0)4\d{8}$",
    "US": r"^\+?1?[2-9]\d{9}$",   # US/CA numbers do not separate mobile from landline
    "ANY": r"^\+?\d{8,15}$",
}
# Who fixes what. Overridden from --owner-ops / --owner-lead / --owner-client.
OWNERS = {"ops": "VA / account admin", "lead": "Account lead", "client": "The client"}

CONSENT_LAW = {"UK": "PECR / UK GDPR", "IE": "the ePrivacy rules / GDPR", "AU": "the Spam Act",
               "US": "the TCPA and carrier A2P 10DLC rules", "ANY": "your local marketing-consent law"}


class Client:
    def __init__(self, token, loc):
        self._t, self.loc = token, loc
        try:
            import certifi
            self.ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            self.ctx = ssl.create_default_context()

    def get(self, path):
        url = BASE + path.replace("{loc}", self.loc)
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + self._t,
            "Version": API_VERSION,
            "Accept": "application/json",
            "User-Agent": UA,
        })
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=45) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:500]
            try:
                body = json.loads(body)
            except Exception:
                pass
            return e.code, {"_error": body}
        except Exception as e:
            return 0, {"_error": str(e)[:300]}


def paged_contacts(cl, cap=20000):
    """GET /contacts/ with startAfterId paging. Read-only (POST /contacts/search is a
    read too, but this skill is GET-only by rule)."""
    out, start_after_id, start_after, total = [], None, None, None
    while len(out) < cap:
        q = "/contacts/?locationId={loc}&limit=100"
        if start_after_id:
            q += "&startAfterId=" + urllib.parse.quote(str(start_after_id))
        if start_after:
            q += "&startAfter=" + urllib.parse.quote(str(start_after))
        st, body = cl.get(q)
        if st != 200:
            return out, total, st, body
        batch = body.get("contacts", [])
        meta = body.get("meta", {}) or {}
        if total is None:
            total = meta.get("total")
        out.extend(batch)
        start_after_id, start_after = meta.get("startAfterId"), meta.get("startAfter")
        if not batch or not start_after_id:
            break
    return out, total, 200, None


def sweep(cl, outdir):
    raw, statuses = {}, {}
    os.makedirs(os.path.join(outdir, "raw"), exist_ok=True)
    for name, path, _k in ENDPOINTS:
        st, body = cl.get(path)
        statuses[name] = (st, path)
        raw[name] = body
        with open(os.path.join(outdir, "raw", name + ".json"), "w") as f:
            json.dump(body, f, indent=1)
    contacts, ctotal, cst, cerr = paged_contacts(cl)
    statuses["contacts"] = (cst, "/contacts/?locationId={loc}&limit=100")
    raw["contacts"] = {"contacts": contacts, "total": ctotal, "_error": cerr}
    with open(os.path.join(outdir, "raw", "contacts.json"), "w") as f:
        json.dump(raw["contacts"], f, indent=1)
    return raw, statuses


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def lst(raw, name, key):
    b = raw.get(name) or {}
    if not isinstance(b, dict):
        return []
    v = b.get(key)
    return v if isinstance(v, list) else []


def analyse(raw, statuses, args):
    """Return a list of findings: dict(sev, area, title, evidence, owner, mins)."""
    F = []
    def add(sev, area, title, evidence, owner, mins):
        F.append(dict(sev=sev, area=area, title=title, evidence=evidence, owner=owner, mins=mins))

    unreadable = [(n, s, p) for n, (s, p) in statuses.items() if s not in (200, 201)]

    def ok(name):
        """True only if that endpoint really answered. Never claim a thing is absent
        from an endpoint that 401/403/404/422'd -- that is how an unreadable account
        gets reported as an empty one."""
        return statuses.get(name, (0, ""))[0] == 200

    for n, st, path in unreadable:
        add("INFO", "Token", "`%s` not readable (HTTP %s)" % (path, st),
            "Nothing is asserted about this area. Check it in the UI.", "-", 0)

    # ---------- business profile ----------
    locb = (raw.get("location") or {}).get("location", {}) or {}
    biz = locb.get("business", {}) or {}
    if args.expect_address and ok("location"):
        want, got = norm(args.expect_address), norm(" ".join(filter(None, [
            locb.get("address"), locb.get("city"), locb.get("state"), locb.get("postalCode")])))
        # UK/IE-style postcode, else a US ZIP or AU postcode, else no postcode check
        pc = (re.findall(r"[a-z]{1,2}\d[a-z\d]?\s*\d[a-z]{2}", args.expect_address.lower())
              or re.findall(r"\b\d{4,5}\b(?!.*\b\d{4,5}\b)", args.expect_address))
        pc_ok = (norm(pc[0]) in got) if pc else True
        if not pc_ok:
            add("P1", "Business profile", "Address does not match the business's real address",
                "Account: %s, %s, %s %s. Expected: %s" % (locb.get("address"), locb.get("city"),
                 locb.get("state"), locb.get("postalCode"), args.expect_address), OWNERS["ops"], 5)
    if ok("location") and args.expect_phone and norm(args.expect_phone) not in norm(locb.get("phone")):
        add("P1", "Business profile",
            "Account phone is not the business's main line",
            "Business Profile phone = %r. The main line is %s. This number appears in email footers, "
            "booking confirmations and anything using {{location.phone}}." % (locb.get("phone"), args.expect_phone),
            OWNERS["ops"], 5)
    for fld, label, sev in [("website", "Website", "P1"), ("logoUrl", "Logo", "P2"),
                            ("currency", "Currency", "P1")]:
        if ok("location") and not locb.get(fld):
            add(sev, "Business profile", "%s is blank on the business profile" % label,
                "GET /locations/{id} -> %s = \"\"" % fld, OWNERS["ops"], 3)
    if ok("location") and not (biz.get("email") or "").strip():
        add("P2", "Business profile", "Business email is blank",
            "location.business.email = \"\" (the account email is %s)" % locb.get("email"), OWNERS["ops"], 3)
    social = locb.get("social", {}) or {}
    if ok("location") and social and not any((social.get(k) or "").strip() for k in social):
        add("P2", "Business profile", "No social or Google Place ID on the profile",
            "Every social field and googlePlacesId is blank. Review-request automations need the Place ID.",
            OWNERS["ops"], 10)
    tz = locb.get("timezone")

    # ---------- users ----------
    users = lst(raw, "users", "users")
    admins = [u for u in users if (u.get("roles") or {}).get("role") == "admin"]
    if ok("users") and len(users) <= 1:
        add("P1", "Users", "Only %d user on the account" % len(users),
            "Users: %s. Nobody at the business other than the owner can see or answer a lead, and no "
            "agency or team user exists to be notified or to route calls to." %
            (", ".join("%s (%s)" % (u.get("name"), (u.get("roles") or {}).get("role")) for u in users) or "none"),
            OWNERS["lead"], 10)
    for u in users:
        if not (u.get("lcPhone") or {}):
            add("P2", "Users", "User %s has no phone number assigned" % u.get("name"),
                "users[].lcPhone = {} so calls cannot ring this user.", OWNERS["ops"], 5)

    # ---------- phone ----------
    nums = lst(raw, "phone_numbers", "numbers")
    if ok("phone_numbers") and not nums:
        add("P0", "Phone", "No phone number on the account",
            "GET /phone-system/numbers/location/{id} returned 0 numbers. No SMS can send.", OWNERS["ops"], 30)
    for n in nums:
        pn, fn = n.get("phoneNumber"), n.get("friendlyName") or ""
        caps = n.get("capabilities") or {}
        if not n.get("forwardingNumber") and not (n.get("linkedRingAllUsers") or []):
            add("P0", "Phone", "%s has no call forwarding and no users to ring" % pn,
                "forwardingNumber = \"\" and linkedRingAllUsers = []. A patient who calls the number in the "
                "ad hears nothing and nobody at the business knows they rang.", OWNERS["ops"], 10)
        if re.search(r"\b(test|temp|my number|number|personal|old)\b", fn, re.I) \
           and args.client and norm(args.client)[:6] not in norm(fn):
            add("P1", "Phone", "Number friendly name is %r" % fn,
                "This is the label staff and the team see beside every message. It should name the client.",
                OWNERS["ops"], 2)
        if not caps.get("sms"):
            add("P0", "Phone", "%s is not SMS capable" % pn, "capabilities.sms = false", OWNERS["ops"], 30)
        if not caps.get("voice"):
            add("P1", "Phone", "%s is not voice capable" % pn, "capabilities.voice = false", OWNERS["ops"], 15)
    if len([n for n in nums if n.get("isDefaultNumber")]) != 1 and nums:
        add("P1", "Phone", "No single default sender number",
            "%d of %d numbers are flagged isDefaultNumber." %
            (len([n for n in nums if n.get("isDefaultNumber")]), len(nums)), OWNERS["ops"], 5)

    # ---------- custom values ----------
    cvs = lst(raw, "custom_values", "customValues")
    empty = [c for c in cvs if not (c.get("value") or "").strip()]
    risky = [c for c in empty if re.search(r"t&c|terms|link|phone|email|name|address|booking|notif",
                                           c.get("name", ""), re.I)]
    if ok("custom_values") and cvs and len(empty) == len(cvs):
        add("P0", "Messaging", "All %d custom values are empty" % len(cvs),
            "Every merge field the snapshot's messages read from is blank, including: %s. Any workflow that "
            "sends one of these will send a blank, or the literal placeholder text typed into the action "
            "(this is how a literal \"[T&Cs link]\" ends up in a live lead's text)."
            % ", ".join(c["name"] for c in risky[:8]), OWNERS["ops"], 45)
    elif risky:
        add("P0", "Messaging", "%d merge fields used in patient messages are empty" % len(risky),
            "Empty: %s" % ", ".join(c["name"] for c in risky[:10]), OWNERS["ops"], 30)
    for c in cvs:
        v = (c.get("value") or "")
        if re.search(r"\[.*?\]|\{\{\s*\}\}|lorem|example\.com|your ?clinic|placeholder|xxx", v, re.I):
            add("P0", "Messaging", "Custom value %r holds placeholder text" % c.get("name"),
                "value = %r would be sent verbatim to a patient." % v[:120], OWNERS["ops"], 5)

    # ---------- templates / snippets ----------
    if ok("sms_templates") and not lst(raw, "sms_templates", "templates"):
        add("P2", "Messaging", "No saved SMS templates or snippets",
            "GET /locations/{id}/templates returned 0. Every reply is typed from scratch.", OWNERS["ops"], 20)

    # ---------- workflows ----------
    wfs = lst(raw, "workflows", "workflows")
    pub = [w for w in wfs if (w.get("status") or "").lower() == "published"]
    draft = [w for w in wfs if (w.get("status") or "").lower() != "published"]
    if ok("workflows") and wfs and not pub:
        add("P0", "Workflows", "All %d workflows are in draft" % len(wfs),
            "Nothing fires. A Meta lead form submission lands in the account and gets no text, no email, "
            "no notification and no pipeline stage. Drafts: %s" %
            ", ".join(w["name"] for w in draft[:6]) + (" ..." if len(draft) > 6 else ""), OWNERS["lead"], 60)
    if pub:
        add("INFO", "Workflows", "%d workflow(s) are PUBLISHED and can fire at a real contact today" % len(pub),
            ", ".join(w["name"] for w in pub), OWNERS["lead"], 20)
    names = [w.get("name", "") for w in wfs]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        add("P2", "Workflows", "Duplicate workflow names", "Appear more than once: %s" % ", ".join(dupes), OWNERS["ops"], 5)
    junk = [n for n in names if re.search(r"do not use|zz |old |copy|test", n, re.I)]
    if junk:
        add("P2", "Workflows", "Dead workflows still in the account",
            "Named as retired but still present: %s. A 'Remove from workflow' step that targets these by name "
            "will silently miss anything built later." % ", ".join(junk), OWNERS["ops"], 10)
    add("INFO", "Workflows", "Triggers and steps are not readable over the API",
        "GET /workflows/?locationId= returns id, name, status, version and timestamps only. There is no "
        "trigger or step data, and GET /workflows/{id} 404s. Every question about what a workflow does, what "
        "fires it, which ones set DND, and which 'Remove from workflow' steps exist has to be answered by "
        "opening each one in the UI.", OWNERS["lead"], 0)

    # ---------- calendars ----------
    cal_st = statuses.get("calendars", (0, ""))[0]
    if cal_st in (401, 403):
        add("P1", "Calendars", "Calendars are not readable with this token",
            "GET /calendars/?locationId= -> %d \"The token is not authorized for this scope.\" Whether a real "
            "team member and real opening hours are attached cannot be verified from here; check it in the UI "
            "before any booking link or AI assistant goes live, because an empty calendar makes automations "
            "invent availability." % cal_st, OWNERS["ops"], 10)
    else:
        cals = lst(raw, "calendars", "calendars")
        if not cals:
            add("P0", "Calendars", "No calendars exist",
                "Any booking link or AI booking step has nothing to book into.", OWNERS["ops"], 30)
        for c in cals:
            if not (c.get("teamMembers") or []):
                add("P0", "Calendars", "Calendar %r has no team member attached" % c.get("name"),
                    "teamMembers = []. Bookings have no owner and availability is undefined.", OWNERS["ops"], 10)
            hours = c.get("openHours") or []
            if not hours:
                add("P0", "Calendars", "Calendar %r has no opening hours" % c.get("name"),
                    "openHours = []. An AI or automation reading this calendar invents availability.", OWNERS["ops"], 10)

    # ---------- forms / surveys / funnels ----------
    forms = lst(raw, "forms", "forms")
    if ok("forms") and not forms:
        add("P1", "Forms", "No forms exist", "GET /forms/ returned 0.", OWNERS["ops"], 20)
    subs = lst(raw, "form_submissions", "submissions")
    add("INFO", "Forms", "%d form(s), %d submission(s) all time" % (len(forms), len(subs)),
        ", ".join(f.get("name", "?") for f in forms) or "none", "-", 0)
    add("INFO", "Forms", "Notification settings are not in the API",
        "Whether a form or funnel notifies anyone on submission is a UI-only setting. Check it before launch.",
        OWNERS["ops"], 10)
    funnels = lst(raw, "funnels", "funnels")
    for f in funnels:
        if not (f.get("domainId") or "").strip():
            add("P2", "Funnels", "Funnel %r has no domain attached" % f.get("name"),
                "domainId = \"\", so it only serves on the default preview URL.", OWNERS["ops"], 10)
    boiler = [f for f in funnels if re.search(r"\$\d|gift card|med spa|medspa|template|demo", f.get("name", ""), re.I)]
    if boiler:
        add("P1", "Funnels", "Snapshot boilerplate funnels still present",
            "%s. These carry another market's currency and offers and can be found by URL." %
            ", ".join(f["name"] for f in boiler), OWNERS["ops"], 15)
    emt = lst(raw, "email_templates", "builders")
    boilt = [t for t in emt if re.search(r"laser hair|prp|hydrafacial|body contour|saas|med ?spa", t.get("name",""), re.I)]
    if boilt:
        add("P2", "Messaging", "Snapshot email templates for services the business may not offer",
            ", ".join(t["name"] for t in boilt), OWNERS["lead"], 15)

    # ---------- pipelines ----------
    pipes = lst(raw, "pipelines", "pipelines")
    if ok("pipelines") and not pipes:
        add("P1", "Pipelines", "No pipelines exist", "Nothing to track a lead through.", OWNERS["ops"], 20)
    for p in pipes:
        st_names = [s.get("name") for s in (p.get("stages") or [])]
        if len(st_names) > 8:
            add("P2", "Pipelines", "Pipeline %r has %d stages" % (p.get("name"), len(st_names)),
                "Stages: %s. More stages than a small team will ever move a card through; every one is a "
                "place a lead silently parks." % ", ".join(st_names), OWNERS["lead"], 15)

    # ---------- contacts ----------
    cts = (raw.get("contacts") or {}).get("contacts", [])
    ctotal = (raw.get("contacts") or {}).get("total")
    n = len(cts)
    mob_re = re.compile(MOBILE.get(args.country, MOBILE["ANY"]))
    mob = sum(1 for c in cts if mob_re.match(re.sub(r"[ ()-]", "", c.get("phone") or "")))
    dnd = sum(1 for c in cts if c.get("dnd"))
    emails = [(c.get("email") or "").lower() for c in cts if c.get("email")]
    phones = [re.sub(r"[ ()-]", "", c.get("phone") or "") for c in cts if c.get("phone")]
    dup = (len(emails) - len(set(emails))) + (len(phones) - len(set(phones)))
    tagset = {}
    for c in cts:
        for t in (c.get("tags") or []):
            tagset[t] = tagset.get(t, 0) + 1
    cfs = lst(raw, "custom_fields", "customFields")
    consent = [f for f in cfs if re.search(r"consent|marketing|opt.?in|gdpr|accepts", f.get("name", ""), re.I)]
    if not ok("contacts"):
        pass
    elif n == 0:
        add("P0", "Contacts", "The account has ZERO contacts",
            "GET /contacts/ returns total = %s. There is no patient database in this account, so a database "
            "reactivation cannot run and no offer text can go out. The patient list has never been imported."
            % ctotal, OWNERS["client"], 30)
    else:
        add("INFO", "Contacts", "%d contacts, %d with a valid %s mobile, %d on DND, %d likely duplicates"
            % (n, mob, args.country, dnd, dup), "Tag taxonomy: %s" %
            (", ".join("%s (%d)" % (k, v) for k, v in sorted(tagset.items(), key=lambda x: -x[1])[:15]) or "no tags"),
            "-", 0)
        if mob / max(n, 1) < 0.6:
            add("P0", "Contacts", "Only %d of %d contacts have a valid %s mobile (%.0f%%)"
                % (mob, n, args.country, 100 * mob / n), "Everything else cannot receive a text.", OWNERS["client"], 30)
    if not ok("custom_fields"):
        pass
    elif not consent:
        add("P0", "Compliance", "No field records marketing consent",
            "No contact custom field matches consent / marketing / opt-in. Under %s you cannot text a "
            "marketing message to a patient or customer without a lawful basis, and nothing in this account "
            "records one." % CONSENT_LAW.get(args.country, CONSENT_LAW["ANY"]),
            OWNERS["lead"], 20)
    else:
        filled = 0
        keys = [f.get("fieldKey", "").split(".")[-1] for f in consent]
        for c in cts:
            cf = {x.get("id"): x.get("value") for x in (c.get("customFields") or [])}
            if any(v for v in cf.values()):
                filled += 1
        add("P0" if (n and filled == 0) else "INFO", "Compliance",
            "Consent fields exist (%s) but are filled on %d of %d contacts"
            % (", ".join(f["name"] for f in consent), filled, n),
            "A consent field with no value is not consent. The import must carry the answer, or the first "
            "text has to be a permission-based one the client can defend.", OWNERS["lead"], 20)
    if ok("tags") and not lst(raw, "tags", "tags"):
        add("P1", "Contacts", "No tags exist on the account",
            "There is no taxonomy to segment a reactivation batch, suppress the already-contacted, or "
            "separate ad leads from database patients.", OWNERS["ops"], 20)

    # ---------- conversations ----------
    convs = lst(raw, "conversations", "conversations")
    unans = [c for c in convs if (c.get("lastMessageDirection") == "inbound"
                                  and (c.get("unreadCount") or 0) > 0)]
    if unans:
        add("P0", "Conversations", "%d inbound message(s) nobody has answered" % len(unans),
            "; ".join("%s, last inbound %s" % (
                c.get("fullName") or c.get("contactName") or c.get("contactId"),
                datetime.fromtimestamp((c.get("lastMessageDate") or 0) / 1000, timezone.utc).strftime("%d %b %Y")
                if c.get("lastMessageDate") else "unknown") for c in unans[:10]), OWNERS["ops"], 15)
    else:
        add("INFO", "Conversations", "%d conversations, none unanswered" % len(convs), "", "-", 0)

    # ---------- integrations ----------
    socials = ((raw.get("social_accounts") or {}).get("results") or {}).get("accounts", [])
    if ok("social_accounts") and not socials:
        add("P1", "Integrations", "No social accounts connected",
            "GET /social-media-posting/{id}/accounts returns 0. Facebook and Instagram comments and DMs do "
            "not reach this inbox. It does NOT block ads, and Meta lead-ad delivery into the account is a "
            "separate connection that this API cannot see.", OWNERS["lead"], 20)
    if ok("payment_providers") and not lst(raw, "payment_providers", "providers"):
        add("P1", "Integrations", "No payment provider connected",
            "GET /payments/integrations/provider/whitelabel returns 0 providers, so deposits cannot be taken "
            "inside this account.", OWNERS["lead"], 20)
    add("INFO", "Integrations", "Meta lead-ads connection, Google, Stripe and calendar sync are not "
        "readable with a location PIT",
        "There is no public read endpoint for the lead-ads connection or the Google/calendar integrations. "
        "Confirm the lead form is mapped to this location in the UI before any spend starts.", OWNERS["lead"], 15)
    add("INFO", "Email", "Sending domain and its verification state are not readable with this token",
        "No public v2 endpoint returns LC Email domains (/emails/domains, /emails/verified-domains both 404). "
        "location.defaultEmailService = %r. Check Settings > Email Services in the UI."
        % (locb.get("defaultEmailService") or ""), OWNERS["ops"], 5)

    # ---------- token coverage ----------
    return F, dict(tz=tz, users=users, nums=nums, cvs=cvs, wfs=wfs, pipes=pipes, forms=forms,
                   funnels=funnels, contacts=n, ctotal=ctotal, mob=mob, dnd=dnd, dup=dup,
                   tagset=tagset, consent=consent, convs=convs, loc=locb, unreadable=unreadable,
                   country=args.country)


ORDER = {"P0": 0, "P1": 1, "P2": 2, "INFO": 3}


def write_audit(F, ctx, args, statuses, outdir):
    loc = ctx["loc"]
    now = datetime.now().strftime("%d %b %Y %H:%M %Z").strip()
    p0 = [f for f in F if f["sev"] == "P0"]
    p1 = [f for f in F if f["sev"] == "P1"]
    p2 = [f for f in F if f["sev"] == "P2"]
    L = []
    w = L.append
    w("# %s - GoHighLevel account audit" % (args.client or loc.get("name") or args.location))
    w("")
    w("Read-only sweep, %s. Location `%s`. GET requests only: nothing was sent, changed or enrolled." %
      (now, args.location))
    w("")
    w("**%d P0, %d P1, %d P2.**" % (len(p0), len(p1), len(p2)))
    w("")
    if p0:
        w("## What blocks the launch")
        w("")
        for f in p0:
            w("- **%s** (%s)" % (f["title"], f["area"]))
        w("")
    w("## Findings")
    w("")
    w("| # | Sev | Area | Finding | Evidence | Owner | Mins |")
    w("|---|-----|------|---------|----------|-------|------|")
    i = 0
    for f in sorted(F, key=lambda x: (ORDER[x["sev"]], x["area"])):
        i += 1
        w("| %d | %s | %s | %s | %s | %s | %s |" % (
            i, f["sev"], f["area"], f["title"].replace("|", "/"),
            f["evidence"].replace("|", "/").replace("\n", " "), f["owner"],
            f["mins"] or "-"))
    w("")
    w("## Account at a glance")
    w("")
    w("| | |")
    w("|---|---|")
    for k, v in [
        ("Name", loc.get("name")), ("Address", ", ".join(filter(None, [
            loc.get("address"), loc.get("city"), loc.get("state"), loc.get("postalCode"), loc.get("country")]))),
        ("Timezone", loc.get("timezone")), ("Profile phone", loc.get("phone")),
        ("Account email", loc.get("email")), ("Website", loc.get("website") or "(blank)"),
        ("Currency", loc.get("currency") or "(blank)"),
        ("Created", loc.get("dateAdded")), ("Built from snapshot", loc.get("snapshotId") or "(none)"),
        ("Users", len(ctx["users"])), ("Phone numbers", len(ctx["nums"])),
        ("Workflows", "%d (%d published)" % (len(ctx["wfs"]),
            len([x for x in ctx["wfs"] if (x.get("status") or "").lower() == "published"]))),
        ("Pipelines", len(ctx["pipes"])), ("Forms", len(ctx["forms"])),
        ("Funnels", len(ctx["funnels"])),
        ("Contacts", "%s (API total %s)" % (ctx["contacts"], ctx["ctotal"])),
        ("Valid %s mobiles" % ctx["country"], ctx["mob"]), ("On DND", ctx["dnd"]),
        ("Likely duplicates", ctx["dup"]), ("Tags in use", len(ctx["tagset"])),
        ("Conversations", len(ctx["convs"])),
        ("Custom values", "%d (%d empty)" % (len(ctx["cvs"]),
            len([c for c in ctx["cvs"] if not (c.get("value") or "").strip()]))),
    ]:
        w("| %s | %s |" % (k, v))
    w("")
    w("## Endpoints read")
    w("")
    w("| Endpoint | HTTP |")
    w("|---|---|")
    for name, (st, path) in sorted(statuses.items()):
        w("| `%s` | %s%s |" % (path, st, " (not readable with this token)" if st in (401, 403) else ""))
    w("")
    w("Raw JSON for every endpoint is in `raw/`.")
    w("")
    open(os.path.join(outdir, "AUDIT.md"), "w").write("\n".join(L))


def write_fixes(F, args, outdir):
    L = []
    w = L.append
    client = args.client or args.location
    w("# %s - GoHighLevel fix list" % client)
    w("")
    w("Everything below is inside the %s GoHighLevel account. Nothing here sends a message to a patient or customer. "
      "Work top to bottom and stop at the end of P0 if you run out of time." % client)
    w("")
    for sev, head, blurb in [
        ("P0", "Do these before anything goes live", "If one of these is still open, do not turn an ad on."),
        ("P1", "Do these this week", "None of these stop the launch, all of them cost money if left."),
        ("P2", "Tidy up when there is a gap", "Housekeeping."),
    ]:
        items = [f for f in F if f["sev"] == sev]
        if not items:
            continue
        w("## %s - %s" % (sev, head))
        w("")
        w("_%s_" % blurb)
        w("")
        for i, f in enumerate(items, 1):
            w("### %s%d. %s" % (sev[1], i, f["title"]))
            w("")
            w("- **Who:** %s" % f["owner"])
            w("- **How long:** about %s minutes" % f["mins"])
            w("- **What you will see:** %s" % f["evidence"])
            w("- **Done when:** you have re-opened the same screen and read the new value back. Post the "
              "screenshot in the task before marking it complete.")
            w("")
    info = [f for f in F if f["sev"] == "INFO"]
    if info:
        w("## For the record (no action)")
        w("")
        for f in info:
            w("- **%s** - %s" % (f["title"], f["evidence"]))
        w("")
    open(os.path.join(outdir, "FIXES.md"), "w").write("\n".join(L))


def main():
    ap = argparse.ArgumentParser(description="Read-only GoHighLevel sub-account audit (GET only).")
    ap.add_argument("--token-env", default="GHL_API_KEY",
                    help="NAME of the env var holding the Private Integration token (default GHL_API_KEY)")
    ap.add_argument("--location", default=os.environ.get("GHL_LOCATION_ID", ""),
                    help="sub-account location id (default $GHL_LOCATION_ID)")
    ap.add_argument("--out", default="./ghl-account-audit-output",
                    help="output folder (default ./ghl-account-audit-output)")
    ap.add_argument("--client", default="", help="readable account name for the report title")
    ap.add_argument("--expect-address", default="", help="the business's real address, to compare")
    ap.add_argument("--expect-phone", default="", help="the business's real main phone line, to compare")
    ap.add_argument("--country", default="ANY", choices=sorted(MOBILE),
                    help="market for mobile-number and consent checks (default ANY)")
    ap.add_argument("--owner-ops", default=OWNERS["ops"], help="who fixes settings (default: VA / account admin)")
    ap.add_argument("--owner-lead", default=OWNERS["lead"], help="who owns build decisions")
    ap.add_argument("--owner-client", default=OWNERS["client"], help="who owns the client-side data")
    a = ap.parse_args()
    OWNERS.update(ops=a.owner_ops, lead=a.owner_lead, client=a.owner_client)

    token = os.environ.get(a.token_env)
    if not token:
        print("ERROR: %s is not set. Run: set -a; source ~/.claude/skills/.env; set +a" % a.token_env)
        sys.exit(2)
    if not a.location:
        print("ERROR: no location id. Pass --location or set GHL_LOCATION_ID.")
        sys.exit(2)
    outdir = os.path.expanduser(a.out)
    os.makedirs(outdir, exist_ok=True)

    cl = Client(token, a.location)
    raw, statuses = sweep(cl, outdir)
    F, ctx = analyse(raw, statuses, a)
    write_audit(F, ctx, a, statuses, outdir)
    write_fixes(F, a, outdir)
    p0 = len([f for f in F if f["sev"] == "P0"])
    print("P0=%d  P1=%d  P2=%d  ->  %s" % (
        p0, len([f for f in F if f["sev"] == "P1"]),
        len([f for f in F if f["sev"] == "P2"]), outdir))
    for f in F:
        if f["sev"] == "P0":
            print("  P0 [%s] %s" % (f["area"], f["title"]))


if __name__ == "__main__":
    main()
