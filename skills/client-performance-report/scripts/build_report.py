#!/usr/bin/env python3
"""Build two self-contained HTML one-pagers from a growth-data-hub report.json.

  internal.html  candid, for the team: the constraint, this week's actions, risks, the full funnel.
  client.html    client-branded, plain language: wins first, what we are doing next, a warm
                 speed-to-lead nudge when the booking rate is low. Always a DRAFT for human approval.

No JavaScript, no network calls, inline CSS, phone friendly.

Usage:
  python3 build_report.py --report out/report.json --brand brand.yaml --out reports/demo-clinic
  python3 build_report.py --report report.json --brand brand.yaml --out dir --benchmarks ../growth-data-hub/benchmarks.yaml
"""
import argparse
import base64
import mimetypes
import os
import re
import sys
from html import escape

import yaml

# Same defaults as growth-data-hub/benchmarks.yaml. Pass --benchmarks to use your tuned copy.
DEFAULT_BENCHMARKS = {
    "funnel": {"default": {"click_to_session": {"low": 0.70}, "session_to_lead": {"low": 0.04},
                           "lead_to_booked": {"low": 0.30}, "show_rate": {"low": 0.65}, "showed_to_won": {"low": 0.20}},
               "meta": {"ctr": {"low": 0.008}, "session_to_lead": {"low": 0.05}},
               "google_ads": {"ctr": {"low": 0.03}, "session_to_lead": {"low": 0.05}},
               "other": {"session_to_lead": {"low": 0.008}}},
    "costs": {"cpl": {"max": 60}, "cost_per_booked": {"max": 200}},
    "minimums": {"leads": 10, "booked": 8, "showed": 5},
}

SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€", "AUD": "A$", "CAD": "C$", "NZD": "NZ$"}
CLIENT_CHANNEL_NAMES = {"meta": "Facebook and Instagram ads", "google_ads": "Google search ads",
                        "other": "Your website, search and referrals"}
HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")
# Words that describe our data plumbing. They belong in internal.html, never in client.html.
INTERNAL_WORDS = ["Clarity", "GA4", "GoHighLevel", "CRM", "constraint", "severity", "benchmark", "Media buyer"]


# ------------------------------------------------------------------ helpers

def e(x):
    return escape(str(x if x is not None else ""))


def money(v, cur):
    if v is None:
        return "n/a"
    sym = SYMBOLS.get((cur or "").upper())
    return f"{sym}{v:,.2f}" if sym else f"{cur} {v:,.2f}".strip()


def pct(v):
    return "n/a" if v is None else f"{v * 100:.1f}%"


def num(v):
    return "n/a" if v is None else f"{v:,.0f}"


def bench(bm, channel, stage):
    f = bm.get("funnel", {})
    return ((f.get(channel) or {}).get(stage) or (f.get("default") or {}).get(stage) or {}).get("low")


def load_yaml(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_brand(path):
    b = load_yaml(path)
    if not b.get("client_name"):
        raise ValueError("brand.yaml needs client_name")
    colors = b.get("colors") or {}
    for k, default in (("primary", "#1F3A5F"), ("accent", "#C8963E")):
        v = str(colors.get(k) or default)
        if not HEX.match(v):
            raise ValueError(f"brand.yaml colors.{k} must be a hex colour like #1F3A5F, got {v!r}")
        colors[k] = v
    b["colors"] = colors
    font = re.sub(r"[^A-Za-z0-9 \-]", "", str(b.get("font") or "")).strip()
    b["font_stack"] = (f"'{font}', " if font else "") + "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif"
    b["logo_src"] = logo_src(b.get("logo"), os.path.dirname(os.path.abspath(path)))
    b.setdefault("prepared_by", "Your marketing team")
    return b


def logo_src(logo, base_dir):
    """Local file -> inline data URI (keeps the page self-contained). URL -> used as is. Missing -> None (text wordmark)."""
    if not logo:
        return None
    logo = str(logo)
    if logo.startswith(("http://", "https://")):
        return logo
    p = logo if os.path.isabs(logo) else os.path.join(base_dir, os.path.expanduser(logo))
    if not os.path.exists(p):
        print(f"warning: logo not found at {p}; using a text wordmark", file=sys.stderr)
        return None
    mime = mimetypes.guess_type(p)[0] or "image/png"
    with open(p, "rb") as fh:
        return f"data:{mime};base64,{base64.b64encode(fh.read()).decode()}"


def channel_name(ch, brand):
    return (brand.get("channel_names") or {}).get(ch["key"]) or CLIENT_CHANNEL_NAMES.get(ch["key"]) or ch["label"]


def mid(name):
    """Channel name for use mid-sentence: 'Your website...' becomes 'your website...'."""
    return name[0].lower() + name[1:] if name.startswith("Your ") else name


def enough(ch, field, bm):
    return (ch.get(field) or 0) >= bm.get("minimums", {}).get(field, 0)


# ------------------------------------------------------------------ the analysis behind the client copy

def wins(r, bm, brand):
    """Honest positives only, each backed by an exact number. Best first, at most 4."""
    cur, t = r["currency"], r["funnel"]["total"]
    out = []
    cpl_cap = (bm.get("costs", {}).get("cpl") or {}).get("max")
    if t.get("cpl") and cpl_cap and t["cpl"] <= cpl_cap and enough(t, "leads", bm):
        out.append((2.0, f"Each new enquiry cost {money(t['cpl'], cur)} on average, under the {money(cpl_cap, cur)} we aim for."))
    paid = [c for c in r["funnel"]["channels"] if c.get("spend") and c.get("booked")]
    if len(paid) > 1:
        best = min(paid, key=lambda c: c["cost_per_booked"])
        out.append((1.5, f"{channel_name(best, brand)} booked {num(best['booked'])} consultations at "
                         f"{money(best['cost_per_booked'], cur)} each, your best value channel this period."))
    labels = {"lead_to_booked": "of enquiries from {ch} booked a consultation",
              "show_rate": "of booked consultations from {ch} went ahead",
              "showed_to_won": "of people from {ch} who came in went ahead with treatment"}
    dens = {"lead_to_booked": "leads", "show_rate": "booked", "showed_to_won": "showed"}
    for ch in r["funnel"]["channels"]:
        for stage, text in labels.items():
            v, low = ch.get(stage), bench(bm, ch["key"], stage)
            if v is None or not low or v < low * 1.2 or not enough(ch, dens[stage], bm):
                continue
            out.append((1.0 + v / low / 10, f"{pct(v)} {text.format(ch=mid(channel_name(ch, brand)))}, "
                                             f"well ahead of the {pct(low)} we plan for."))
    for f in r.get("findings", []):
        if f["type"] == "ad" and f["stage"] == "scale":
            out.append((1.2, f"Your best value Facebook and Instagram campaign is bringing in enquiries at "
                             f"{money(f['value'], cur)} each."))
    out.sort(key=lambda w: -w[0])
    seen, final = set(), []
    for _, text in out:
        if text not in seen:
            seen.add(text)
            final.append(text)
    return final[:4]


def speed_nudge(r, bm, brand):
    """The paid channel with the lowest booking rate under its floor, with enough leads to judge. None if all fine."""
    cands = []
    for ch in r["funnel"]["channels"]:
        v, low = ch.get("lead_to_booked"), bench(bm, ch["key"], "lead_to_booked")
        if v is None or low is None or v >= low or not enough(ch, "leads", bm):
            continue
        cands.append((v, ch, low))
    if not cands:
        return None
    paid = [c for c in cands if c[1].get("spend")]
    v, ch, low = min(paid or cands, key=lambda c: c[0])
    return {"channel": channel_name(ch, brand), "leads": ch["leads"], "booked": ch["booked"],
            "waiting": ch["leads"] - ch["booked"], "rate": v, "floor": low}


def client_next_step(a, r, brand):
    """Plain-language version of one action, or None when it is internal housekeeping."""
    chans = {c["key"]: c for c in r["funnel"]["channels"]}
    ch = channel_name(chans[a["channel"]], brand) if a.get("channel") in chans else "your ads"
    t, s = a["type"], a["stage"]
    if t == "stage":
        return {
            "ctr": f"Testing fresh opening lines and images on {ch}, so more of the right people stop and take a look.",
            "click_to_session": f"Making sure everyone who clicks on {ch} lands on a fast page and is counted properly.",
            "session_to_lead": f"Simplifying the page people land on from {ch}: one clear offer and a shorter form, so more visitors get in touch.",
            "lead_to_booked": f"Helping more enquiries from {ch} turn into booked consultations, with quick first calls and friendly follow-up texts and emails.",
            "show_rate": "Adding a confirmation call and reminder messages, so more booked patients turn up on the day.",
            "showed_to_won": "Looking at recent consultations that did not go ahead, to sharpen how the most common questions get answered.",
        }.get(s)
    if t == "cost":
        return f"Moving budget on {ch} away from the most expensive ads and towards the ones bringing in enquiries for less."
    if t == "search" and s == "lost_is_budget":
        return "Your strongest Google search campaign keeps running out of daily budget while it brings in enquiries at a good price. We would like to give it a little more room, and will confirm any budget change with you first."
    if t == "search" and s == "lost_is_rank":
        return "Improving the quality of your Google search ads and the page they lead to, so they show up more often."
    if t == "ad" and s == "kill_ad":
        return "Switching off an ad that is not bringing in enquiries, so its budget goes to the ones that are."
    if t == "ad" and s == "scale":
        return "Giving more budget to your best value campaign, then holding it steady for a few days so it settles."
    if t == "page":
        what = {"dead clicks": "where visitors tap on something that does not respond",
                "rage clicks": "that visitors seem to find frustrating",
                "quick backs": "that some visitors leave very quickly",
                "average scroll depth": "so the key details sit higher up, where most visitors actually look"}.get(a["metric"], "to make it easier to use")
        return f"Tidying up a section of your {a['label']} page {what}."
    return None  # lead_gap and anything else: internal checks, not client news


# ------------------------------------------------------------------ shared page shell

BASE_CSS = """
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:#F7F7F5;color:#1D2128;font:15px/1.6 var(--font);}
main{max-width:860px;margin:0 auto;padding:20px 16px 56px}
h1{font-size:28px;line-height:1.2;margin:4px 0 8px}h2{font-size:19px;margin:34px 0 10px}
.eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#5B6270}
.card{background:#fff;border:1px solid #E4E4E0;border-radius:12px;padding:16px 18px;margin:10px 0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:14px}
.kpi{background:#fff;border:1px solid #E4E4E0;border-radius:12px;padding:12px 14px}
.kpi .v{font-size:24px;font-weight:700;line-height:1.2}.kpi .l{font-size:12px;color:#5B6270}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:14px;background:#fff}
th,td{padding:8px 10px;border-bottom:1px solid #ECECE8;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left;white-space:normal}thead th{font-weight:600;color:#3B414C;background:#FAFAF8}
ul,ol{padding-left:22px}li{margin:0 0 10px}.muted{color:#5B6270;font-size:13px}
footer{margin-top:40px;color:#7A808B;font-size:12px}
@media (max-width:560px){h1{font-size:23px}.kpi .v{font-size:20px}main{padding:14px 12px 44px}}
"""


def page(title, css, body, font_stack):
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'><meta name='robots' content='noindex,nofollow'>"
            f"<title>{e(title)}</title><style>:root{{--font:{font_stack}}}{BASE_CSS}{css}</style></head>"
            f"<body><main>{body}</main></body></html>")


def kpi(value, label):
    return f"<div class='kpi'><div class='v'>{e(value)}</div><div class='l'>{e(label)}</div></div>"


def table(head, rows):
    h = "".join(f"<th>{e(c)}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<div class='scroll'><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>"


# ------------------------------------------------------------------ client.html

def client_html(r, bm, brand, approved=False):
    cur, t, w = r["currency"], r["funnel"]["total"], r["window"]
    p, a = brand["colors"]["primary"], brand["colors"]["accent"]
    css = (f".top{{display:flex;justify-content:space-between;align-items:center;gap:12px;padding-bottom:14px;border-bottom:3px solid {p}}}"
           ".top img{max-height:52px;max-width:180px;object-fit:contain}"
           f".wordmark{{font-weight:700;font-size:20px;color:{p}}}"
           f"h1,h2{{color:{p}}}.kpi .v{{color:{p}}}"
           f".draft{{background:#FFF4D6;border:1px solid #E9C46A;color:#6B4E00;border-radius:8px;padding:8px 12px;font-size:13px;margin-bottom:14px}}"
           f".verdict{{font-size:17px;color:#2F3540;margin:0 0 6px}}"
           f".win{{border-left:5px solid {a}}}.nudge{{border-left:5px solid {p};background:#fff}}"
           f".big{{font-size:17px;font-weight:600;color:{p}}}"
           f"ul.ticks{{list-style:none;padding-left:0}}ul.ticks li{{padding-left:26px;position:relative}}"
           f"ul.ticks li:before{{content:'';position:absolute;left:4px;top:.55em;width:10px;height:10px;border-radius:50%;background:{a}}}")
    logo = (f"<img src='{e(brand['logo_src'])}' alt='{e(brand['client_name'])} logo'>" if brand.get("logo_src")
            else f"<span class='wordmark'>{e(brand['client_name'])}</span>")
    body = []
    if not approved:
        body.append("<div class='draft'>Draft for review. Not yet approved to share.</div>")
    if r.get("demo"):
        body.append("<div class='draft'>Built from sample data.</div>")
    body.append(f"<div class='top'><span class='eyebrow'>Marketing report</span>{logo}</div>")
    nudge = speed_nudge(r, bm, brand)
    hello = f"Hi {e(brand['greeting_name'])}. " if brand.get("greeting_name") else ""
    verdict = ("Your ads are bringing in a steady flow of enquiries, and everything is set up and running. "
               "Here is the picture, plus the one change that would turn more of them into booked patients."
               if nudge else
               "Everything is set up and running, and enquiries are coming in. Here is the picture for this period.")
    body.append(f"<p class='eyebrow' style='margin-top:18px'>{e(w['start'])} to {e(w['end'])} ({e(w['days'])} days)</p>"
                f"<h1>{e(brand['client_name'])}</h1><p class='verdict'>{hello}{verdict}</p>")

    tiles = [kpi(num(t["leads"]), "New enquiries")]
    if t.get("booked") is not None:
        tiles.append(kpi(num(t["booked"]), "Booked consultations"))
    if t.get("showed"):
        tiles.append(kpi(num(t["showed"]), "Consultations that went ahead"))
    if t.get("cpl"):
        tiles.append(kpi(money(t["cpl"], cur), "Average cost per enquiry"))
    body.append("<div class='kpis'>" + "".join(tiles) + "</div>")
    body.append("<p class='muted'>An enquiry is someone who filled in your form or got in touch with their name and number.</p>")

    ws = wins(r, bm, brand)
    if ws:
        body.append("<h2>What is going well</h2><div class='card win'><ul class='ticks'>"
                    + "".join(f"<li>{e(x)}</li>" for x in ws) + "</ul></div>")

    rows = []
    for ch in r["funnel"]["channels"]:
        if not ch.get("leads"):
            continue
        rows.append([e(channel_name(ch, brand)), num(ch["leads"]), num(ch.get("booked")),
                     money(ch["cpl"], cur) if ch.get("cpl") else "no ad cost"])
    if rows:
        body.append("<h2>Where your enquiries came from</h2>"
                    + table(["Channel", "Enquiries", "Booked", "Cost per enquiry"], rows))

    if nudge:
        body.append(
            "<h2>The one thing that would make the biggest difference</h2><div class='card nudge'>"
            f"<p class='big'>{num(nudge['waiting'])} people who enquired through {e(mid(nudge['channel']))} have not booked yet.</p>"
            f"<p>Of the {num(nudge['leads'])} enquiries from {e(mid(nudge['channel']))}, {num(nudge['booked'])} booked a consultation "
            f"({pct(nudge['rate'])}). That is a real opportunity: these are people who have already put their hand up.</p>"
            "<p>The quickest win we know of is speed. Research on lead response keeps finding that people called within "
            "the first five minutes are far more likely to book than people called an hour later, and that a few friendly "
            "follow-ups book many more than a single try.</p>"
            "<p><b>Could the team try this for the next two weeks?</b> Call each new enquiry within 5 minutes during opening "
            "hours, and try again later the same day if there is no answer. We will look after the follow-up texts and emails "
            "so nobody slips through, and we would love to hear which questions come up on those calls so we can help answer them.</p></div>")

    steps = [s for s in (client_next_step(x, r, brand) for x in r.get("actions", [])) if s]
    steps = list(dict.fromkeys(steps))
    if steps:
        body.append("<h2>What we are doing next</h2><div class='card'><ol>"
                    + "".join(f"<li>{e(s)}</li>" for s in steps) + "</ol></div>")
    body.append("<p>Thank you for trusting us with your growth. If anything here raises a question, just reply and we will talk it through.</p>")
    body.append(f"<footer>Prepared by {e(brand['prepared_by'])} for {e(brand['client_name'])}</footer>")
    return page(f"{brand['client_name']}: marketing report", css, "".join(body), brand["font_stack"])


# ------------------------------------------------------------------ internal.html

FUNNEL_ROWS = [("spend", "Spend", "money"), ("clicks", "Clicks", "n"), ("sessions", "Sessions", "n"),
               ("leads", "Leads (CRM)", "n"), ("platform_leads", "Leads (ad platform)", "n"),
               ("session_to_lead", "Session to lead", "pct"), ("booked", "Booked", "n"),
               ("lead_to_booked", "Booking rate", "pct"), ("showed", "Showed", "n"), ("show_rate", "Show rate", "pct"),
               ("won", "Won", "n"), ("showed_to_won", "Close rate", "pct"), ("cpl", "Cost per lead", "money"),
               ("cost_per_booked", "Cost per booked", "money"), ("cost_per_won", "Cost per sale", "money")]


def risks(r, bm):
    out = []
    for name, s in r.get("sources", {}).items():
        if s.get("state") != "ok":
            out.append(f"Source {name} is {s.get('state')}: {s.get('why')}. Its numbers are missing from both pages.")
    for f in r.get("findings", []):
        if f["type"] == "lead_gap":
            out.append(f"{f['trigger']}. Reconcile before quoting lead counts to the client.")
    for ch in r["funnel"]["channels"]:
        if ch.get("leads") and not enough(ch, "leads", bm):
            out.append(f"{ch['label']}: only {num(ch['leads'])} leads, too few to judge its booking rate.")
    if r.get("clarity"):
        out.append(f"Page behaviour data covers the last {r['clarity'].get('num_days')} days only: a spot check, not a trend.")
    for wmsg in (r.get("ghl") or {}).get("warnings") or []:
        out.append(f"CRM warning: {wmsg}")
    keys = {(a["type"], a["stage"], a["channel"], a["label"]) for a in r.get("actions", [])}
    for f in r.get("findings", []):
        if (f["type"], f["stage"], f["channel"], f["label"]) not in keys and f["type"] != "lead_gap":
            out.append(f"Not in this week's 5: {f['trigger']}.")
    if r.get("demo"):
        out.insert(0, "Demo data: do not share.")
    return out


def internal_html(r, bm, brand):
    cur, t, w, c = r["currency"], r["funnel"]["total"], r["window"], r.get("constraint")
    css = (".constraint{border-left:5px solid #B4471B}.risk{border-left:5px solid #B45309}"
           ".who{display:inline-block;background:#EEF2FF;color:#1E3A8A;border-radius:999px;padding:1px 9px;font-size:12px;margin-right:6px}"
           ".bad{color:#B91C1C;font-weight:600}.chk li{list-style:none;margin-left:-22px}")
    body = [f"<p class='eyebrow'>Internal, not for the client &middot; {e(w['start'])} to {e(w['end'])} ({e(w['days'])} days)</p>",
            f"<h1>{e(brand['client_name'])}: internal review</h1>"]
    body.append("<div class='kpis'>" + kpi(money(t["spend"], cur), "Spend") + kpi(num(t["leads"]), "Leads")
                + kpi(num(t.get("booked")), "Booked") + kpi(num(t.get("showed")), "Showed") + kpi(num(t.get("won")), "Won")
                + kpi(money(t.get("cpl"), cur), "Cost per lead") + kpi(money(t.get("cost_per_booked"), cur), "Cost per booked")
                + "</div>")
    if c:
        body.append(f"<h2>The constraint</h2><div class='card constraint'><p><b>{e(c['trigger'])}</b> "
                    f"(floor {pct(c['benchmark'])}). Everything after this step is starved until it is fixed.</p>"
                    f"<p>{e(c['action'])}</p><span class='who'>{e(c['owner'])}</span><span class='muted'>about {e(c['minutes'])} min</span></div>")
    else:
        body.append("<h2>The constraint</h2><div class='card'>No funnel step is below its floor, or there is not enough data yet.</div>")
    body.append("<h2>Actions this week</h2><div class='card'><ol>")
    for a in r.get("actions", []):
        body.append(f"<li><b>{e(a['action'])}</b><div class='muted'>{e(a['trigger'])}</div>"
                    f"<span class='who'>{e(a['owner'])}</span><span class='muted'>about {e(a['minutes'])} min</span></li>")
    body.append("</ol></div>")
    rs = risks(r, bm)
    if rs:
        body.append("<h2>Risks and caveats</h2><div class='card risk'><ul>" + "".join(f"<li>{e(x)}</li>" for x in rs) + "</ul></div>")

    chans = [ch for ch in r["funnel"]["channels"] if ch.get("spend") or ch.get("leads")]
    flagged = {(f["channel"], f["stage"]) for f in r.get("findings", []) if f["type"] in ("stage", "cost")}
    rows = []
    for key, label, kind in FUNNEL_ROWS:
        vals = [ch.get(key) for ch in chans] + [t.get(key)]
        if all(v in (None, 0) for v in vals):
            continue
        cells = [e(label)]
        for ch, v in zip(chans + [t], vals):
            txt = money(v, cur) if kind == "money" else pct(v) if kind == "pct" else num(v)
            cells.append(f"<span class='bad'>{e(txt)}</span>" if (ch.get("key"), key) in flagged else e(txt))
        rows.append(cells)
    body.append("<h2>Funnel by channel</h2>" + table([""] + [ch["label"] for ch in chans] + ["All"], rows)
                + "<p class='muted'>Red = below floor or over cost target.</p>")

    nudge, ws = speed_nudge(r, bm, brand), wins(r, bm, brand)
    body.append("<h2>What the client page says</h2><div class='card'><ul>"
                + "".join(f"<li>Win: {e(x)}</li>" for x in ws)
                + (f"<li>Speed-to-lead nudge: {e(nudge['channel'])}, {num(nudge['booked'])} of {num(nudge['leads'])} booked ({pct(nudge['rate'])}).</li>"
                   if nudge else "<li>No speed-to-lead nudge (booking rates at or above floor).</li>")
                + "<li>Hidden from the client: data source names, lead-count reconciliation, skipped sources.</li></ul></div>")
    body.append("<h2>Before client.html goes anywhere</h2><div class='card'><ul class='chk'>"
                "<li>&#9744; Every number on client.html matches report.json (and the source platform for anything surprising).</li>"
                "<li>&#9744; Status lines are current: nothing described as upcoming has already happened.</li>"
                "<li>&#9744; Tone reads warm and plain; nothing blames the client or highlights missing data.</li>"
                "<li>&#9744; The account owner has explicitly approved this specific version.</li></ul></div>")
    body.append(f"<footer>Built from report.json generated {e(r.get('generated'))}</footer>")
    return page(f"{brand['client_name']}: internal review", css, "".join(body), brand["font_stack"])


# ------------------------------------------------------------------ CLI

def build(report_path, brand_path, out_dir, benchmarks_path=None, approved=False):
    import json
    with open(report_path, encoding="utf-8") as fh:
        r = json.load(fh)
    for k in ("funnel", "window", "currency"):
        if k not in r:
            raise ValueError(f"{report_path} is not a growth-data-hub report.json (missing '{k}')")
    bm = load_yaml(benchmarks_path) if benchmarks_path else DEFAULT_BENCHMARKS
    brand = load_brand(brand_path)
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    for name, html in (("internal.html", internal_html(r, bm, brand)), ("client.html", client_html(r, bm, brand, approved))):
        paths[name] = os.path.join(out_dir, name)
        with open(paths[name], "w", encoding="utf-8") as fh:
            fh.write(html)
    return paths


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build internal.html and client.html (draft) from a growth-data-hub report.json")
    ap.add_argument("--report", required=True, help="growth-data-hub out/report.json")
    ap.add_argument("--brand", required=True, help="brand.yaml: client_name, logo, colors.primary/accent, font")
    ap.add_argument("--out", default="client-report", help="output folder (default ./client-report)")
    ap.add_argument("--benchmarks", help="growth-data-hub benchmarks.yaml (default: built-in copy of its defaults)")
    ap.add_argument("--approved", action="store_true",
                    help="drop the draft banner. Only after the account owner has approved this exact version.")
    a = ap.parse_args(argv)
    try:
        paths = build(a.report, a.brand, a.out, a.benchmarks, a.approved)
    except (OSError, ValueError, KeyError) as exc:
        sys.exit(f"error: {exc}")
    for p in paths.values():
        print(f"wrote {p}")
    if not a.approved:
        print("client.html is a DRAFT: do not send, post or publish it without the account owner's explicit approval.")


if __name__ == "__main__":
    main()
