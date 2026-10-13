"""One-page HTML report: inline CSS, no JavaScript, no external files, readable on a phone."""
from html import escape

from constraint import fmt

CSS = """
*{box-sizing:border-box}body{margin:0;background:#f6f6f4;color:#1c1f24;font:15px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif}
main{max-width:980px;margin:0 auto;padding:20px 16px 48px}h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 10px}
.sub{color:#5b6270;font-size:13px}.card{background:#fff;border:1px solid #e3e3df;border-radius:12px;padding:16px;margin:10px 0}
.constraint{border-left:5px solid #c2410c}.constraint b{color:#c2410c}.demo{background:#fff7e6;border:1px solid #f5c26b;border-radius:8px;padding:8px 12px;font-size:13px}
ol.actions{padding-left:22px}ol.actions li{margin:0 0 12px}.why{color:#5b6270;font-size:13px}.who{display:inline-block;background:#eef2ff;color:#1e3a8a;border-radius:999px;padding:1px 9px;font-size:12px;margin-right:6px}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}table{border-collapse:collapse;width:100%;font-size:13px;background:#fff}
th,td{padding:7px 9px;border-bottom:1px solid #ecece8;text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left;white-space:normal}
thead th{background:#fafaf8;font-weight:600;color:#3b414c}.bad{color:#b91c1c;font-weight:600}.good{color:#15803d}
.bar{height:8px;background:#e5e7eb;border-radius:4px;min-width:60px}.bar span{display:block;height:8px;background:#1e40af;border-radius:4px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}.kpi{background:#fff;border:1px solid #e3e3df;border-radius:10px;padding:10px 12px}
.kpi .v{font-size:20px;font-weight:650}.kpi .l{font-size:12px;color:#5b6270}.pill{font-size:12px;border-radius:6px;padding:1px 6px}
.ok{background:#dcfce7;color:#166534}.err{background:#fee2e2;color:#991b1b}.skip{background:#f1f5f9;color:#475569}
footer{margin-top:36px;color:#8a909b;font-size:12px}
"""

FUNNEL_ROWS = [("spend", "Spend", "money"), ("impressions", "Impressions", "n"), ("clicks", "Clicks", "n"),
               ("ctr", "CTR", "pct"), ("sessions", "Sessions (GA4)", "n"), ("click_to_session", "Click to session", "pct"),
               ("leads", "Leads", "n"), ("platform_leads", "Leads the ad platform reports", "n"),
               ("session_to_lead", "Session to lead", "pct"), ("booked", "Booked", "n"),
               ("lead_to_booked", "Booking rate", "pct"), ("showed", "Showed", "n"), ("no_show", "No-show", "n"),
               ("show_rate", "Show rate", "pct"), ("won", "Won", "n"), ("showed_to_won", "Close rate", "pct"),
               ("cpl", "Cost per lead", "money"), ("cost_per_booked", "Cost per booked call", "money"),
               ("cost_per_showed", "Cost per showed call", "money"), ("cost_per_won", "Cost per sale", "money")]


def e(x):
    return escape(str(x if x is not None else ""))


def table(head, rows):
    h = "".join(f"<th>{e(c)}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="scroll"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def html(r):
    cur = r["currency"]
    f = r["funnel"]
    flagged = {(x["channel"], x["stage"]) for x in r["findings"] if x["type"] in ("stage", "cost")}
    out = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>Growth report {e(r['window']['start'])} to {e(r['window']['end'])}</title><style>{CSS}</style></head><body><main>"]
    out.append(f"<h1>{e(r['business'] or 'Growth')} report</h1><div class='sub'>{e(r['window']['start'])} to {e(r['window']['end'])} "
               f"({r['window']['days']} days) &middot; generated {e(r['generated'])}</div>")
    if r["demo"]:
        out.append("<p class='demo'>Demo data from fixtures/. Run without --demo once .env and config.yaml are filled in.</p>")

    t = f["total"]
    kp = [("Spend", f"{cur} {fmt(t['spend'], 'money')}"), ("Leads", fmt(t["leads"], "n")),
          ("Cost per lead", f"{cur} {fmt(t['cpl'], 'money')}" if t.get("cpl") else "n/a")]
    if t.get("booked") is not None:
        kp += [("Booked", fmt(t["booked"], "n")), ("Show rate", fmt(t["show_rate"], "pct")), ("Won", fmt(t["won"], "n"))]
    out.append("<div class='kpis' style='margin-top:14px'>" + "".join(
        f"<div class='kpi'><div class='v'>{e(v)}</div><div class='l'>{e(l)}</div></div>" for l, v in kp) + "</div>")

    c = r["constraint"]
    if c:
        out.append(f"<div class='card constraint'><b>The constraint:</b> {e(c['metric'])} on {e(c['label'])} is "
                   f"<b>{fmt(c['value'], 'pct')}</b> against a floor of {fmt(c['benchmark'], 'pct')}. "
                   "Everything after this step is starved until it is fixed.</div>")
    else:
        out.append("<div class='card'>No funnel step is below its benchmark, or there is not yet enough data to judge one.</div>")

    out.append("<h2>Do these 5 things this week</h2><div class='card'><ol class='actions'>")
    for a in r["actions"]:
        out.append(f"<li><b>{e(a['action'])}</b><div class='why'>{e(a['trigger'])}</div>"
                   f"<span class='who'>{e(a['owner'])}</span><span class='why'>about {e(a['minutes'])} min</span></li>")
    out.append("</ol></div>")

    chans = [ch for ch in f["channels"] if ch["spend"] or ch["leads"] or ch["sessions"]]
    out.append("<h2>Funnel by channel</h2>")
    rows = []
    for key, label, kind in FUNNEL_ROWS:
        vals = [ch.get(key) for ch in chans] + [t.get(key)]
        if all(v is None or v == 0 for v in vals):
            continue
        cells = [e(label)]
        for ch, v in zip(chans + [t], vals):
            txt = (f"{cur} " if kind == "money" and v is not None else "") + fmt(v, kind)
            cls = " class='bad'" if (ch["key"], key) in flagged else ""
            cells.append(f"<span{cls}>{e(txt)}</span>")
        rows.append(cells)
    out.append(table([""] + [ch["label"] for ch in chans] + ["All"], rows))
    out.append("<p class='sub'>Leads come from the CRM when GoHighLevel is connected, otherwise from the ad platforms. "
               "Show rate counts only calls that have happened. Red = below benchmark.</p>")

    if r.get("meta"):
        m = r["meta"]
        out.append("<h2>Meta campaigns</h2>")
        out.append(table(["Campaign", "Spend", "Link clicks", "CTR", "CPM", "Leads", "CPL"],
                         [[e(x["name"]), f"{cur} {fmt(x['spend'], 'money')}", fmt(x["clicks"], "n"), fmt(x["ctr"], "pct"),
                           fmt(x["cpm"], "money"), fmt(x["leads"], "n"), fmt(x["cpl"], "money")] for x in m["campaigns"][:15]]))
        out.append("<h2>Meta ads (top 12 by spend)</h2>")
        out.append(table(["Ad", "Campaign", "Spend", "CTR", "Freq.", "Leads", "CPL"],
                         [[e(x["name"]), e(x["campaign"]), f"{cur} {fmt(x['spend'], 'money')}", fmt(x["ctr"], "pct"),
                           f"{x['frequency']:.1f}", fmt(x["leads"], "n"), fmt(x["cpl"], "money")] for x in m["ads"][:12]]))
    if r.get("google_ads"):
        g = r["google_ads"]
        out.append("<h2>Google Ads campaigns</h2>")
        out.append(table(["Campaign", "Spend", "Clicks", "CTR", "Conv.", "Cost/conv.", "Impr. share", "Lost: budget", "Lost: rank"],
                         [[e(x["name"]), f"{cur} {fmt(x['spend'], 'money')}", fmt(x["clicks"], "n"), fmt(x["ctr"], "pct"),
                           f"{x['conversions']:g}", fmt(x["cpa"], "money"), _is(x["impression_share"]),
                           _is(x["lost_is_budget"]), _is(x["lost_is_rank"])] for x in g["campaigns"][:15]]))
        if g.get("changes"):
            out.append(f"<p class='sub'>{len(g['changes'])} account changes in the change history window (newest: "
                       f"{e(g['changes'][0]['when'][:16])}, {e(g['changes'][0]['what'].lower())} on {e(g['changes'][0]['campaign'] or 'account')}).</p>")
    if r.get("ga4"):
        ga = r["ga4"]
        out.append("<h2>GA4: top landing pages</h2>")
        out.append(table(["Landing page", "Sessions", "Engaged", "Key events", "Key events / session"],
                         [[e(x["landing_page"]), fmt(x["sessions"], "n"), fmt(x["engagement_rate"], "pct"),
                           f"{x['key_events']:g}", fmt(x["key_events"] / x["sessions"] if x["sessions"] else None, "pct")]
                          for x in ga["by_landing_page"][:10]]))
        out.append("<h2>GA4: source / medium</h2>")
        out.append(table(["Source / medium", "Sessions", "Engaged", "Key events"],
                         [[e(x["source_medium"]), fmt(x["sessions"], "n"), fmt(x["engagement_rate"], "pct"), f"{x['key_events']:g}"]
                          for x in ga["by_source_medium"][:10]]))
    if r.get("clarity"):
        cl = r["clarity"]
        worst = {p["path"] for p in r.get("pages") or []}
        out.append(f"<h2>Clarity: page behaviour (last {cl['num_days']} days only)</h2>")
        out.append(table(["Page", "Sessions", "Scroll depth", "Dead clicks", "Rage clicks", "Quick backs"],
                         [[("<span class='bad'>" + e(p["path"]) + "</span>") if p["path"] in worst else e(p["path"]),
                           fmt(p["sessions"], "n"), _p(p.get("scroll_depth")), _p(p.get("dead_click_pct")),
                           _p(p.get("rage_click_pct")), _p(p.get("quickback_pct"))] for p in cl["pages"][:12]]))
        out.append("<p class='sub'>Percentages are the share of sessions on that page with at least one such event. "
                   "Clarity's export only covers the last 1 to 3 days, so read it as a spot check, not a trend.</p>")
    if r.get("ghl"):
        gh = r["ghl"]
        out.append("<h2>CRM (GoHighLevel)</h2>")
        out.append(table(["Pipeline / stage (contacts created in the window)", "Count"],
                         [[e(k), fmt(v, "n")] for k, v in list(gh["by_stage"].items())[:12]]))
        if gh.get("appointments_by_status"):
            out.append(table(["Appointments in the window, by status", "Count"],
                             [[e(k), fmt(v, "n")] for k, v in gh["appointments_by_status"].items()]))
        out.append(table(["Contact source", "New contacts"], [[e(k), fmt(v, "n")] for k, v in list(gh["by_source"].items())[:10]]))

    out.append("<h2>Sources</h2>")
    pill = {"ok": "ok", "error": "err", "skipped": "skip"}
    out.append(table(["Source", "State", "Note"], [[e(k), f"<span class='pill {pill.get(v['state'], 'skip')}'>{e(v['state'])}</span>",
                                                   e(v["why"])] for k, v in r["sources"].items()]))
    out.append("<footer>growth-data-hub &middot; read-only pulls &middot; benchmarks from benchmarks.yaml</footer></main></body></html>")
    return "".join(out)


def _p(v):
    return "n/a" if v is None else f"{v:.1f}%"


def _is(v):
    """Google reports impression share under 10% as 0.0999 and lost share over 90% as 0.9001."""
    if v is None:
        return "n/a"
    if abs(v - 0.0999) < 1e-6:
        return "&lt;10%"
    if abs(v - 0.9001) < 1e-6:
        return "&gt;90%"
    return fmt(v, "pct")
