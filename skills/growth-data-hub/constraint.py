"""Find the constraint (the biggest drop against benchmarks.yaml) and turn findings into this week's actions.

Every finding carries: the number that triggered it, the benchmark it was held against, a severity
(how far off, weighted by how much money flows through that channel), who should do it and how long it takes.
"""
from funnel import match_source_medium

# stage -> (what the drop means, denominator field that must be big enough to judge it)
STAGES = [
    ("ctr", "clicks", "impressions"),
    ("click_to_session", "sessions", "clicks"),
    ("session_to_lead", "leads", "sessions"),
    ("lead_to_booked", "booked", "leads"),
    ("show_rate", "showed", "booked"),
    ("showed_to_won", "won", "showed"),
]

STAGE_TEXT = {
    "ctr": "Ad click-through rate",
    "click_to_session": "Clicks that become tracked sessions",
    "session_to_lead": "Landing page conversion (sessions to leads)",
    "lead_to_booked": "Booking rate (leads to booked calls)",
    "show_rate": "Show rate (booked calls that happen)",
    "showed_to_won": "Close rate (showed to won)",
}

PLAYBOOK = {
    "ctr": ("Refresh creative on {label}: test 3 new hooks against the current best ad", "media_buyer", 120),
    "click_to_session": ("Check tracking and page speed for {label}: clicks are not arriving as sessions "
                         "(UTMs, consent banner, redirects, mobile load time)", "analytics_owner", 45),
    "session_to_lead": ("Fix the main {label} landing page: one offer, one form above the fold, cut fields", "web_owner", 120),
    "lead_to_booked": ("Tighten speed to lead for {label}: call within 5 minutes, then a 3-touch SMS and email follow-up "
                       "for anyone not booked", "sales_lead", 60),
    "show_rate": ("Lift show rate for {label}: confirmation call on booking, reminders 24 h and 2 h before, "
                  "reschedule link in every reminder", "crm_admin", 45),
    "showed_to_won": ("Review 3 lost {label} calls this week and fix the most common objection in the script",
                      "sales_lead", 90),
}

ROLE_TEXT = {"media_buyer": "Media buyer", "web_owner": "Landing page owner", "sales_lead": "Sales lead / setter",
             "crm_admin": "CRM admin", "analytics_owner": "Analytics owner", "growth_lead": "Growth lead"}


def fmt(v, kind):
    if v is None:
        return "n/a"
    if kind == "pct":
        return f"{v * 100:.1f}%"
    if kind == "money":
        return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}"
    return f"{v:,.0f}"


def _bench(bm, channel_key, stage):
    return (bm.get("funnel", {}).get(channel_key, {}) or {}).get(stage) or (bm.get("funnel", {}).get("default", {}) or {}).get(stage)


def owner(cfg, role):
    return (cfg.get("owners") or {}).get(role) or ROLE_TEXT.get(role, role)


def stage_findings(funnel, bm, cfg):
    mins = bm.get("minimums", {})
    total_spend = sum(c["spend"] for c in funnel["channels"]) or 0
    out = []
    for ch in funnel["channels"]:
        weight = (ch["spend"] / total_spend) if total_spend and ch["spend"] else 0.15  # unpaid channels still count a little
        for stage, num_f, den_f in STAGES:
            v, b = ch.get(stage), _bench(bm, ch["key"], stage)
            if v is None or not b or "low" not in b:
                continue
            if (ch.get(den_f) or 0) < mins.get(den_f, 0):
                continue  # too little data to judge this step
            if v >= b["low"]:
                continue
            gap = (b["low"] - v) / b["low"]
            text, role, mins_needed = PLAYBOOK[stage]
            out.append({"type": "stage", "stage": stage, "channel": ch["key"], "label": ch["label"],
                        "value": v, "benchmark": b["low"], "gap": gap, "severity": gap * (0.5 + weight),
                        "metric": STAGE_TEXT[stage],
                        "trigger": f"{ch['label']}: {STAGE_TEXT[stage].lower()} {fmt(v, 'pct')} vs at least {fmt(b['low'], 'pct')}",
                        "action": text.format(label=ch["label"]), "owner": owner(cfg, role), "minutes": mins_needed})
    return out


def cost_findings(funnel, bm, cfg):
    out, cur = [], cfg.get("currency", "")
    for ch in funnel["channels"]:
        if not ch["spend"]:
            continue
        for metric, label in (("cpl", "cost per lead"), ("cost_per_booked", "cost per booked call")):
            cap = (bm.get("costs", {}).get(metric) or {}).get("max")
            v = ch.get(metric)
            if cap and v and v > cap:
                gap = (v - cap) / cap
                out.append({"type": "cost", "stage": metric, "channel": ch["key"], "label": ch["label"],
                            "value": v, "benchmark": cap, "gap": gap, "severity": 0.6 * gap,
                            "metric": label, "trigger": f"{ch['label']}: {label} {cur} {fmt(v, 'money')} vs target {cur} {fmt(cap, 'money')}",
                            "action": f"Cut the most expensive {ch['label']} campaigns or ads first; see the step with the biggest drop",
                            "owner": owner(cfg, "media_buyer"), "minutes": 30})
    return out


def lead_gap_findings(funnel, bm, cfg):
    """Platform says N leads, CRM got M. Causes: broken integration, unmapped form, or GHL merging repeat contacts."""
    out, ratio = [], bm.get("lead_match", {}).get("min_crm_share", 0.8)
    for ch in funnel["channels"]:
        pl = ch.get("platform_leads")
        if ch["lead_source"] != "crm" or not pl or pl < bm.get("minimums", {}).get("leads", 10):
            continue
        share = ch["leads"] / pl
        if share < ratio:
            out.append({"type": "lead_gap", "stage": "lead_gap", "channel": ch["key"], "label": ch["label"],
                        "value": share, "benchmark": ratio, "gap": (ratio - share) / ratio,
                        "severity": (ratio - share) / ratio * 1.2,
                        "metric": "leads reaching the CRM",
                        "trigger": f"{ch['label']} reports {fmt(pl, 'n')} leads, the CRM got {fmt(ch['leads'], 'n')} ({fmt(share, 'pct')})",
                        "action": f"Reconcile {ch['label']} leads with the CRM: check every lead form is mapped, the integration is connected, "
                                  "and how many were merged into existing contacts (same email or phone)",
                        "owner": owner(cfg, "crm_admin"), "minutes": 30})
    return out


def search_findings(data, bm, cfg):
    ga = data.get("google_ads")
    if not ga:
        return []
    out, s = [], bm.get("search", {})
    target_cpa = (bm.get("costs", {}).get("cpl") or {}).get("max")
    for c in ga["campaigns"]:
        if c["spend"] <= 0:
            continue
        lb, lr = c.get("lost_is_budget"), c.get("lost_is_rank")
        cheap = c["cpa"] is not None and (not target_cpa or c["cpa"] <= target_cpa)
        if lb is not None and lb > s.get("lost_is_budget", {}).get("max", 1) and cheap:
            gap = lb - s["lost_is_budget"]["max"]
            out.append({"type": "search", "stage": "lost_is_budget", "channel": "google_ads", "label": c["name"],
                        "value": lb, "benchmark": s["lost_is_budget"]["max"], "gap": gap, "severity": 0.4 + gap,
                        "metric": "search impression share lost to budget",
                        "trigger": f"'{c['name']}' loses {fmt(lb, 'pct')} of searches to budget at {cfg.get('currency','')} {fmt(c['cpa'], 'money')} per conversion",
                        "action": f"Raise the daily budget of '{c['name']}' by 20% (it converts under target and runs out of money)",
                        "owner": owner(cfg, "media_buyer"), "minutes": 10})
        if lr is not None and lr > s.get("lost_is_rank", {}).get("max", 1):
            gap = lr - s["lost_is_rank"]["max"]
            out.append({"type": "search", "stage": "lost_is_rank", "channel": "google_ads", "label": c["name"],
                        "value": lr, "benchmark": s["lost_is_rank"]["max"], "gap": gap, "severity": 0.3 + gap,
                        "metric": "search impression share lost to rank",
                        "trigger": f"'{c['name']}' loses {fmt(lr, 'pct')} of searches to ad rank",
                        "action": f"Improve ad rank on '{c['name']}': tighter ad groups, keyword in headline 1, "
                                  "landing page that repeats the search term; then review bids",
                        "owner": owner(cfg, "media_buyer"), "minutes": 60})
    return out


def ad_findings(data, bm, cfg):
    meta = data.get("meta")
    if not meta:
        return []
    out, cur = [], cfg.get("currency", "")
    target = (bm.get("costs", {}).get("cpl") or {}).get("max")
    if not target:
        return out
    for a in meta["ads"]:
        if a["leads"] == 0 and a["spend"] >= 2 * target:
            out.append({"type": "ad", "stage": "kill_ad", "channel": "meta", "label": a["name"],
                        "value": a["spend"], "benchmark": 2 * target, "gap": a["spend"] / target - 2,
                        "severity": 0.5 + min(a["spend"] / target / 10, 0.5),
                        "metric": "spend with zero leads",
                        "trigger": f"Ad '{a['name']}' spent {cur} {fmt(a['spend'], 'money')} (more than 2x the {cur} {fmt(target, 'money')} CPL target) with 0 leads",
                        "action": f"Pause ad '{a['name']}'", "owner": owner(cfg, "media_buyer"), "minutes": 5})
        elif a["cpl"] and a["cpl"] > 2 * target and a["leads"] >= 2:
            out.append({"type": "ad", "stage": "kill_ad", "channel": "meta", "label": a["name"],
                        "value": a["cpl"], "benchmark": 2 * target, "gap": a["cpl"] / target - 2,
                        "severity": 0.35, "metric": "ad cost per lead",
                        "trigger": f"Ad '{a['name']}' CPL {cur} {fmt(a['cpl'], 'money')} vs target {cur} {fmt(target, 'money')}",
                        "action": f"Pause ad '{a['name']}' or cut its budget", "owner": owner(cfg, "media_buyer"), "minutes": 5})
    winners = [c for c in meta["campaigns"] if c["cpl"] and c["leads"] >= bm.get("minimums", {}).get("leads", 10)
               and c["cpl"] <= 0.7 * target]
    for c in sorted(winners, key=lambda c: c["cpl"])[:1]:
        out.append({"type": "ad", "stage": "scale", "channel": "meta", "label": c["name"],
                    "value": c["cpl"], "benchmark": 0.7 * target, "gap": 0, "severity": 0.3,
                    "metric": "campaign cost per lead",
                    "trigger": f"Campaign '{c['name']}' CPL {cur} {fmt(c['cpl'], 'money')} on {fmt(c['leads'], 'n')} leads (30%+ under target)",
                    "action": f"Scale '{c['name']}' budget by 20% and hold for 3 days before the next change",
                    "owner": owner(cfg, "media_buyer"), "minutes": 10})
    return out


def page_findings(data, bm, cfg, top=3):
    """Landing pages with the worst Clarity signals, and which channels send them traffic (from GA4)."""
    cl, ga4 = data.get("clarity"), data.get("ga4")
    if not cl:
        return [], []
    rules, min_s = bm.get("clarity", {}), bm.get("minimums", {}).get("clarity_sessions", 30)
    scored = []
    for p in cl["pages"]:
        if p["sessions"] < min_s:
            continue
        bad = []
        for m, r in rules.items():
            v = p.get(m)
            if v is None:
                continue
            if "max" in r and v > r["max"]:
                bad.append((m, v, r["max"], (v - r["max"]) / r["max"]))
            if "min" in r and v < r["min"]:
                bad.append((m, v, r["min"], (r["min"] - v) / r["min"]))
        if bad:
            mix = {}
            if ga4:
                for row in ga4["rows"]:
                    lp = (row["landing_page"] or "").split("?")[0].rstrip("/") or "/"
                    if lp == p["path"]:
                        k = match_source_medium(row["source_medium"], cfg)
                        mix[k] = mix.get(k, 0) + row["sessions"]
            tot = sum(mix.values())
            p = dict(p, problems=bad, score=sum(b[3] for b in bad),
                     channel_mix={k: v / tot for k, v in sorted(mix.items(), key=lambda kv: -kv[1])} if tot else {})
            scored.append(p)
    scored.sort(key=lambda p: -p["score"] * min(p["sessions"] / 200, 1.5))
    names = {"dead_click_pct": "dead clicks", "rage_click_pct": "rage clicks", "quickback_pct": "quick backs",
             "scroll_depth": "average scroll depth", "excessive_scroll_pct": "excessive scrolling",
             "error_click_pct": "error clicks", "script_error_pct": "script errors"}
    labels = {c["key"]: c.get("label", c["key"]) for c in (cfg.get("channels") or [])}
    labels["other"] = "organic and other"
    findings = []
    for p in scored[:top]:
        worst = max(p["problems"], key=lambda b: b[3])
        unit = "%" if worst[0] != "scroll_depth" else "% of the page"
        lead_ch = next(iter(p["channel_mix"]), None)
        via = (f"; {p['channel_mix'][lead_ch] * 100:.0f}% of its GA4 sessions come from {labels.get(lead_ch, lead_ch)}"
               if lead_ch else "")
        findings.append({"type": "page", "stage": "page", "channel": lead_ch or "other", "label": p["path"],
                         "value": worst[1], "benchmark": worst[2], "gap": worst[3],
                         "severity": 0.25 + min(p["score"], 2) * 0.3,
                         "metric": names.get(worst[0], worst[0]),
                         "trigger": f"{p['path']}: {names.get(worst[0], worst[0])} {worst[1]:.1f}{unit} vs "
                                    f"{'at most' if worst[0] != 'scroll_depth' else 'at least'} {worst[2]:g}{unit} "
                                    f"({p['sessions']} Clarity sessions, last {cl['num_days']} days){via}",
                         "action": f"Watch 10 Clarity recordings of {p['path']} filtered to {names.get(worst[0], worst[0])}, "
                                   "then fix the element people fight with (often an unclickable image, a hidden form or a slow embed)",
                         "owner": owner(cfg, "web_owner"), "minutes": 60})
    return findings, scored


def analyse(data, funnel, bm, cfg):
    stage = stage_findings(funnel, bm, cfg)
    pages, scored_pages = page_findings(data, bm, cfg)
    findings = stage + cost_findings(funnel, bm, cfg) + lead_gap_findings(funnel, bm, cfg) + \
        search_findings(data, bm, cfg) + ad_findings(data, bm, cfg) + pages
    findings.sort(key=lambda f: -f["severity"])
    constraint = max(stage, key=lambda f: f["severity"]) if stage else None
    # The constraint goes first; then the rest by severity, one action per (type, stage, channel) so the list stays varied.
    actions, seen = [], set()
    for f in ([constraint] if constraint else []) + findings:
        key = (f["type"], f["stage"], f["channel"], f["label"] if f["type"] in ("ad", "page", "search") else "")
        if key in seen:
            continue
        seen.add(key)
        actions.append(f)
        if len(actions) == 5:
            break
    return {"constraint": constraint, "findings": findings, "actions": actions, "pages": scored_pages}
