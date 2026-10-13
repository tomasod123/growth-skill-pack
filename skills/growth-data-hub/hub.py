#!/usr/bin/env python3
"""growth-data-hub: pull Meta, Google Ads, GA4, Clarity and GoHighLevel into one funnel, find the
constraint, and write report.json, ACTIONS.md and report.html.

  python3 hub.py --demo                 # fixture data, no keys needed
  python3 hub.py --days 28              # real run; every source is optional
  python3 hub.py --days 7 --only meta,ghl
  python3 hub.py --check                # say which sources are ready and what is missing
"""
import argparse
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import yaml  # noqa: E402
except ImportError:
    sys.exit("PyYAML is missing. Run: .venv/bin/pip install -r requirements.txt (see SETUP.md, Install)")

import constraint  # noqa: E402
import funnel  # noqa: E402
import render  # noqa: E402
from sources import ALL  # noqa: E402
from sources.common import SourceError, load_env, load_fixture  # noqa: E402

DEMO_END = "2026-10-12"  # the fixtures describe the 28 days ending on this date


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f) or {}


def window(days, end=None):
    end_d = dt.date.fromisoformat(end) if end else dt.date.today() - dt.timedelta(days=1)  # yesterday: full days only
    return (end_d - dt.timedelta(days=days - 1)).isoformat(), end_d.isoformat()


def pull(cfg, env, start, end, args):
    data, status = {}, {}
    only = set(args.only.split(",")) if args.only else None
    for src in ALL:
        if only and src.NAME not in only:
            status[src.NAME] = {"state": "skipped", "why": "not in --only"}
            data[src.NAME] = None
            continue
        if args.demo:
            data[src.NAME] = src.parse(load_fixture(os.path.join(HERE, "fixtures"), src.NAME), cfg, start, end)
            status[src.NAME] = {"state": "ok", "why": "demo fixture"}
            continue
        if (cfg.get(src.NAME) or {}).get("enabled") is False:
            status[src.NAME] = {"state": "skipped", "why": "enabled: false in config.yaml"}
            data[src.NAME] = None
            continue
        need = src.missing(cfg, env)
        if need:
            status[src.NAME] = {"state": "skipped", "why": "missing " + ", ".join(need)}
            data[src.NAME] = None
            continue
        print(f"  pulling {src.NAME} ...", file=sys.stderr, flush=True)
        try:
            if src.NAME == "clarity":
                raw = src.fetch(cfg, env, start, end, cache_dir=os.path.join(HERE, "cache"), refresh=args.refresh_clarity)
            else:
                raw = src.fetch(cfg, env, start, end)
            data[src.NAME] = src.parse(raw, cfg, start, end)
            status[src.NAME] = {"state": "ok", "why": "; ".join(data[src.NAME].get("warnings") or [])}
            if args.save_raw:
                os.makedirs(os.path.join(args.out, "raw"), exist_ok=True)
                with open(os.path.join(args.out, "raw", src.NAME + ".json"), "w") as f:
                    json.dump(raw, f, indent=1)
        except SourceError as e:
            status[src.NAME] = {"state": "error", "why": str(e)[:400]}
            data[src.NAME] = None
        except Exception as e:  # one broken source must never sink the whole report
            status[src.NAME] = {"state": "error", "why": f"{type(e).__name__}: {str(e)[:300]}"}
            data[src.NAME] = None
    return data, status


def fill_actions(result, data, funnel_out, cfg):
    """Always hand back 5 actions. When fewer than 5 problems were found, add steady-state moves."""
    acts = result["actions"]
    tot = funnel_out["total"]
    cur = cfg.get("currency", "")
    extras = []
    paid = [c for c in funnel_out["channels"] if c["spend"] and (c.get("cost_per_booked") or c.get("cpl"))]
    if paid:
        key = "cost_per_booked" if all(c.get("cost_per_booked") for c in paid) else "cpl"
        best = min(paid, key=lambda c: c[key])
        what = "cost per booked call" if key == "cost_per_booked" else "cost per lead"
        extras.append({"trigger": f"{best['label']} has the lowest {what}: {cur} {constraint.fmt(best[key], 'money')}",
                       "action": f"Move 10-20% more budget to {best['label']} and hold it for a week",
                       "owner": constraint.owner(cfg, "growth_lead"), "minutes": 15})
    if data.get("meta"):
        good = [a for a in data["meta"]["ads"] if a["cpl"] and a["leads"] >= 5]
        if good:
            a = min(good, key=lambda a: a["cpl"])
            extras.append({"trigger": f"Best ad '{a['name']}': {cur} {constraint.fmt(a['cpl'], 'money')} per lead on {constraint.fmt(a['leads'], 'n')} leads",
                           "action": f"Make 2 new variations of '{a['name']}' (same angle, new hook and first frame)",
                           "owner": constraint.owner(cfg, "media_buyer"), "minutes": 90})
    if data.get("ga4"):
        lps = [p for p in data["ga4"]["by_landing_page"] if p["sessions"] >= 100]
        if lps:
            p = max(lps, key=lambda p: p["key_events"] / p["sessions"])
            extras.append({"trigger": f"{p['landing_page']} converts best in GA4: {p['key_events'] / p['sessions'] * 100:.1f}% key events per session",
                           "action": f"Send more paid traffic to {p['landing_page']}, or copy its offer and form into the weaker pages",
                           "owner": constraint.owner(cfg, "web_owner"), "minutes": 30})
    if data.get("clarity"):
        p = data["clarity"]["pages"][:1]
        if p:
            extras.append({"trigger": f"{p[0]['path']} is the busiest page in Clarity ({p[0]['sessions']} sessions, last {data['clarity']['num_days']} days)",
                           "action": f"Watch 5 Clarity recordings of {p[0]['path']} from paid traffic and note the first thing people get stuck on",
                           "owner": constraint.owner(cfg, "web_owner"), "minutes": 30})
    extras.append({"trigger": "Benchmarks drive every flag in this report",
                   "action": "Check benchmarks.yaml cost targets match your real economics (deal value, close rate)",
                   "owner": constraint.owner(cfg, "growth_lead"), "minutes": 15})
    extras.append({"trigger": "Week-on-week trend",
                   "action": "Re-run this report next week with the same --days and compare the constraint",
                   "owner": constraint.owner(cfg, "growth_lead"), "minutes": 5})
    for e in extras:
        if len(acts) >= 5:
            break
        acts.append(dict(e, type="steady", stage="steady", channel="all", label="", severity=0))
    return acts


def _short(why):
    """Keep the API message and the fix, drop trace ids and long JSON."""
    import re
    fix = why.split(" -> FIX: ", 1)[1] if " -> FIX: " in why else ""
    msg = re.search(r'"message"\s*:\s*"([^"]+)"', why)
    head = why.split(":", 1)[0] if why.startswith("HTTP") else why.split(" -> FIX: ")[0]
    text = f"{head}: {msg.group(1)}" if msg else head
    return (text[:180] + (f" Fix: {fix}" if fix else "")).strip()


def actions_md(report):
    cur = report["currency"]
    name = f"{report['business']}: " if report.get("business") else ""
    lines = [f"# {name}this week's {len(report['actions'])} actions ({report['window']['start']} to {report['window']['end']})", ""]
    c = report["constraint"]
    if c:
        lines += [f"**Constraint:** {c['metric']} on {c['label']} is {constraint.fmt(c['value'], 'pct')} "
                  f"against a floor of {constraint.fmt(c['benchmark'], 'pct')}. Fix this before anything downstream.", ""]
    else:
        lines += ["**Constraint:** none of the funnel steps is below its benchmark (or there is not enough data yet).", ""]
    for i, a in enumerate(report["actions"], 1):
        lines += [f"{i}. **{a['action']}**",
                  f"   - Why: {a['trigger']}",
                  f"   - Who: {a['owner']} | Time: about {a['minutes']} min", ""]
    skipped = [f"- {k}: {v['state']}: {_short(v['why'])}" for k, v in report["sources"].items() if v["state"] != "ok"]
    if skipped:
        lines += ["**Sources not in this report** (fixes in SETUP.md, Common errors):"] + skipped + [""]
    warn = [f"- {k}: {v['why']}" for k, v in report["sources"].items() if v["state"] == "ok" and v["why"] and not report["demo"]]
    if warn:
        lines += ["**Warnings:**"] + warn + [""]
    t = report["funnel"]["total"]
    lines += [f"_Totals: spend {cur} {constraint.fmt(t['spend'], 'money')}, leads {constraint.fmt(t['leads'], 'n')}"
              + (f", booked {t['booked']}, showed {t['showed']}, won {t['won']}" if t.get("booked") is not None else "") + "._"]
    return "\n".join(lines) + "\n"


def _round(o):
    """Floats to 4 decimals so report.json stays readable."""
    if isinstance(o, float):
        return round(o, 4)
    if isinstance(o, dict):
        return {k: _round(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_round(v) for v in o]
    return o


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=None, help="window length in days, ending yesterday (default 28)")
    ap.add_argument("--end", help="last day of the window, YYYY-MM-DD (default yesterday)")
    ap.add_argument("--demo", action="store_true", help="use fixtures/ instead of live APIs")
    ap.add_argument("--config", default=os.path.join(HERE, "config.yaml"))
    ap.add_argument("--benchmarks", default=os.path.join(HERE, "benchmarks.yaml"))
    ap.add_argument("--env", default=os.path.join(HERE, ".env"))
    ap.add_argument("--out", default=None, help="output folder (default out/, or out/demo with --demo)")
    ap.add_argument("--only", help="comma list of sources: meta,google_ads,ga4,clarity,ghl")
    ap.add_argument("--refresh-clarity", action="store_true", help="ignore today's Clarity cache (uses 1 of ~10 daily calls)")
    ap.add_argument("--save-raw", action="store_true", help="also save raw API replies to out/raw/ for debugging")
    ap.add_argument("--check", action="store_true", help="list which sources are ready, then exit")
    args = ap.parse_args(argv)

    args.out = args.out or os.path.join(HERE, "out", "demo" if args.demo else "")
    args.out = args.out.rstrip("/")
    if args.demo:
        cfg = load_yaml(os.path.join(HERE, "fixtures", "demo-config.yaml"))
        args.end, args.days = DEMO_END, 28
    elif os.path.exists(args.config):
        cfg = load_yaml(args.config)
    elif args.check:
        print("No config.yaml yet (copy config.example.yaml to config.yaml). Checking .env only:\n")
        cfg = {}
    else:
        sys.exit(f"No config.yaml yet. Copy config.example.yaml to config.yaml and fill it in, or try --demo first.")
    args.days = args.days or int(cfg.get("days") or 28)
    env = {} if args.demo else load_env(args.env)
    bm = load_yaml(args.benchmarks)

    if args.check:
        for src in ALL:
            need = src.missing(cfg, env)
            print(f"{src.NAME:11s} {'ready' if not need else 'missing: ' + ', '.join(need)}")
        return 0

    start, end = window(args.days, args.end)
    print(f"growth-data-hub: {start} to {end}{' (demo)' if args.demo else ''}", file=sys.stderr)
    data, status = pull(cfg, env, start, end, args)
    if not any(v for v in data.values()):
        print("No source could be pulled:", file=sys.stderr)
        for k, v in status.items():
            print(f"  {k}: {v['why']}", file=sys.stderr)
        print("Run with --demo to see the report with sample data.", file=sys.stderr)
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "ACTIONS.md"), "w") as fh:
            fh.write(f"# No report: no source could be pulled ({start} to {end})\n\n" +
                     "".join(f"- {k}: {_short(v['why'])}\n" for k, v in status.items()) +
                     "\nFix the keys above (SETUP.md, Common errors), then run again.\n")
        for stale in ("report.html", "report.json"):
            if os.path.exists(os.path.join(args.out, stale)):
                os.remove(os.path.join(args.out, stale))
        return 2

    f = funnel.build(data, cfg)
    result = constraint.analyse(data, f, bm, cfg)
    fill_actions(result, data, f, cfg)
    report = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "demo": bool(args.demo), "business": cfg.get("business_name", ""), "currency": cfg.get("currency", ""),
        "window": {"start": start, "end": end, "days": args.days},
        "sources": status, "funnel": f, "constraint": result["constraint"], "actions": result["actions"],
        "findings": result["findings"], "pages": result["pages"],
        "meta": data.get("meta"), "google_ads": data.get("google_ads"),
        "ga4": {k: v for k, v in (data.get("ga4") or {}).items() if k != "rows"} or None,
        "clarity": data.get("clarity"),
        "ghl": {k: v for k, v in (data.get("ghl") or {}).items() if k not in ("contacts", "opportunities", "appointments")} or None,
    }
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "report.json"), "w") as fh:
        json.dump(_round(report), fh, indent=1, default=str)
    with open(os.path.join(args.out, "ACTIONS.md"), "w") as fh:
        fh.write(actions_md(report))
    with open(os.path.join(args.out, "report.html"), "w") as fh:
        fh.write(render.html(report))
    for k, v in status.items():
        print(f"  {k:11s} {v['state']}{': ' + v['why'] if v['why'] else ''}", file=sys.stderr)
    print(f"Wrote {args.out}/report.json, ACTIONS.md, report.html", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
