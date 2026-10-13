#!/usr/bin/env python3
"""funnel_math.py - deterministic funnel maths for meta-ads-analyst (no network).

Two ways in:
  1) Numbers you read off screenshots / exports:
     python3 funnel_math.py --spend 4200 --leads 96 --qualified 41 --bookings 30 --shows 22 \
         --closes 6 --cash 9000 [--ltv-gp 30000] [--config ../config/analyst.json]
  2) Live pulls from meta_pull.py + ghl_pull.py:
     python3 funnel_math.py --meta ./meta-ads-analyst-output/<day>/meta.json \
         --ghl ./meta-ads-analyst-output/<day>/ghl.json [--config ...] [--window last_7d]

Prints a markdown block: the cost chain (CPL -> cost per qualified lead -> cost per booking ->
cost per show -> CAC), conversion rates, payback, each graded against your config targets,
the per-ad qualified join (live mode), speed-to-lead buckets, and a leads-per-day volatility note.
"""
import argparse, json, math, os, sys
from collections import defaultdict


def load_cfg(p):
    if not p:
        return {}
    c = json.load(open(os.path.expanduser(p)))
    return {k: v for k, v in c.items() if not k.startswith("_")}


def div(a, b):
    return (a / b) if (a is not None and b) else None


def fmt(v, kind="money"):
    if v is None:
        return "n/a"
    if kind == "pct":
        return f"{v:.1f}%"
    if kind == "x":
        return f"{v:.2f}x"
    return f"{v:,.2f}"


def grade(v, target, lower_is_better):
    if v is None:
        return "no data"
    if target is None:
        return "no target set"
    ok = v <= target if lower_is_better else v >= target
    near = (v <= target * 1.2) if lower_is_better else (v >= target * 0.8)
    return "IN TARGET" if ok else ("BORDERLINE" if near else "OFF TARGET")


def chain(spend, leads, qualified, bookings, shows, closes, cash, ltv_gp, cfg):
    rows = []
    R = lambda name, v, kind, tkey, lower: rows.append((name, fmt(v, kind), fmt(cfg.get(tkey), kind) if cfg.get(tkey) is not None else "-", grade(v, cfg.get(tkey), lower)))
    cac = div(spend, closes)
    roas = div(cash, spend)
    ltv_cac = div(ltv_gp, cac) if (ltv_gp and cac) else None
    R("CAC (spend / new customers)", cac, "money", "target_cac", True)
    R("Front-end cash ROAS", roas, "x", "min_front_end_cash_roas", False)
    R("LTV gross profit : CAC", ltv_cac, "x", "min_ltv_to_cac", False)
    R("CPL", div(spend, leads), "money", "target_cpl", True)
    R("Cost per qualified lead", div(spend, qualified), "money", "target_cost_per_qualified_lead", True)
    R("Cost per booking", div(spend, bookings), "money", "target_cost_per_booking", True)
    R("Cost per show", div(spend, shows), "money", None, True)
    pc = lambda a, b: (100 * a / b) if (a is not None and b) else None
    R("Qualified rate (qualified / leads)", pc(qualified, leads), "pct", None, False)
    R("Lead to booking", pc(bookings, leads), "pct", "target_lead_to_booking_pct", False)
    R("Show rate", pc(shows, bookings), "pct", "target_show_pct", False)
    R("Close rate (closes / shows)", pc(closes, shows), "pct", "target_close_pct", False)
    out = ["| Metric | Value | Target | Status |", "|---|---|---|---|"]
    out += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows]
    if qualified and bookings:
        br = bookings / leads if leads else None
        out.append(f"\nCost per qualified booking ~ cost per qualified lead / booking rate = "
                   f"{fmt(div(spend, qualified))} / {100 * (br or 0):.0f}% = {fmt(div(div(spend, qualified), br))} "
                   f"(shows whether lead cost or booking rate is the lever).")
    return "\n".join(out)


def volatility(leads, days):
    if not leads or not days:
        return ""
    lam = leads / days
    p0 = math.exp(-lam)
    return (f"\nVolatility: {lam:.1f} leads/day on average, so even a healthy campaign has a zero-lead day "
            f"about {100*p0:.0f}% of the time (~{7*p0:.1f} per week). Judge on 7-14 day windows, not daily.")


def live(meta, ghl, cfg, window, shows=None, closes=None, cash=None, ltv_gp=None):
    m = json.load(open(meta))
    w = m["windows"][window]
    t = w["totals"]
    spend = t.get("spend") or 0
    leads = t.get("leads") or 0
    g = json.load(open(ghl)) if ghl else {}
    qs = g.get("qualification_summary_7d") or {}
    qualified = qs.get("qualified")
    bookings = (g.get("bookings") or {}).get("booked_last_7d")
    out = [f"## Live funnel ({window}, {m['meta'].get('currency')})", "",
           f"Campaign {m['meta'].get('campaign_id')} | spend {fmt(spend)} | Meta leads {leads:.0f} | "
           f"CRM leads {g.get('recent_opps_count', 'n/a')} | bookings {bookings if bookings is not None else 'n/a'}", ""]
    if m.get("contamination_flag"):
        out += [f"> {m['contamination_flag']}", ""]
    out.append(chain(spend, leads, qualified, bookings, shows, closes, cash, ltv_gp, cfg))
    if closes is None:
        out.append("\n(Shows, closes and cash are not in the pulls: add them from the CRM or the client with --shows/--closes/--cash.)")
    # per-ad join on utm_content = ad name
    per = {a["ad_name"]: a for a in w.get("per_ad", [])}
    byad = defaultdict(lambda: {"crm": 0, "qualified": 0, "unqualified": 0})
    for l in g.get("recent_leads", []):
        k = l.get("ad_name") or "(no utm_content)"
        byad[k]["crm"] += 1
        if l.get("quality_tag"):
            byad[k][l["quality_tag"]] += 1
    if per or byad:
        out += ["", "### Per ad (Meta spend joined to CRM leads by utm_content = ad name)", "",
                "| Ad | Spend | Meta leads | CRM leads | Qualified | Unqualified | Cost per qualified |", "|---|---|---|---|---|---|---|"]
        for name in sorted(set(per) | set(byad), key=lambda n: -(per.get(n, {}).get("spend") or 0)):
            a, b = per.get(name, {}), byad.get(name, {"crm": 0, "qualified": 0, "unqualified": 0})
            out.append(f"| {name} | {fmt(a.get('spend'))} | {a.get('leads') or 0:.0f} | {b['crm']} | {b['qualified']} | {b['unqualified']} | {fmt(div(a.get('spend'), b['qualified']))} |")
    stl = (g.get("speed_to_lead") or {}).get("rows", [])
    if stl:
        buckets = [("Under 5 min", 0, 5), ("5-15 min", 5, 15), ("15-60 min", 15, 60), ("1-4 h", 60, 240), ("4-24 h", 240, 1440), ("24 h+", 1440, 1e12)]
        out += ["", "### Speed to lead (first human/outbound touch)", "", "| Bucket | Count |", "|---|---|"]
        for nm, lo, hi in buckets:
            out.append(f"| {nm} | {sum(1 for r in stl if r.get('stl_to_first_touch_min') is not None and lo <= r['stl_to_first_touch_min'] < hi)} |")
        out.append(f"| Never contacted | {sum(1 for r in stl if r.get('stl_to_first_touch_min') is None)} |")
        tgt = cfg.get("target_speed_to_lead_min")
        if tgt:
            within = sum(1 for r in stl if r.get("stl_to_first_touch_min") is not None and r["stl_to_first_touch_min"] <= tgt)
            out.append(f"\nWithin your {tgt}-minute target: {within} of {len(stl)}.")
    out.append(volatility(leads, 7 if window == "last_7d" else 3))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--meta"); ap.add_argument("--ghl"); ap.add_argument("--window", default="last_7d")
    for k in ("spend", "leads", "qualified", "bookings", "shows", "closes", "cash", "ltv-gp", "days"):
        ap.add_argument("--" + k, type=float)
    a = ap.parse_args()
    cfg = load_cfg(a.config)
    if a.meta:
        print(live(a.meta, a.ghl, cfg, a.window, a.shows, a.closes, a.cash, a.ltv_gp))
        return
    if a.spend is None:
        sys.exit("Give --spend plus whatever counts you have, or --meta (and --ghl) for live mode.")
    print(chain(a.spend, a.leads, a.qualified, a.bookings, a.shows, a.closes, a.cash, a.ltv_gp, cfg))
    if a.days:
        print(volatility(a.leads, a.days))


if __name__ == "__main__":
    main()
