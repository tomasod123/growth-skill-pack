"""Daily lead-flow watchdog (read-only).

For each business in config.yaml, compares yesterday's Meta lead form submissions
with GoHighLevel contacts that look like Meta leads, and flags integration breaks,
processing breaks, delivery drops, CPL spikes and spend with no leads.

Usage:
    python scripts/watchdog.py --demo              # fixture data, no API calls
    python scripts/watchdog.py                     # check yesterday, print + write markdown
    python scripts/watchdog.py --day 2026-03-10    # check a specific day
    python scripts/watchdog.py --send              # also post to SLACK_WEBHOOK_URL if anything is WARNING or worse
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from detect import CRITICAL, INFO, RANK, WARNING, DayStats, detect, worst  # noqa: E402
from ghl_client import GHLClient, GHLError, classify, parse_date  # noqa: E402
from meta_graph import GraphClient, GraphError, count_leads  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
FIXTURES = SKILL_DIR / "fixtures"
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ---------------------------------------------------------------- data pulls

def meta_days(client: GraphClient, act: str, day: date) -> dict[str, tuple[float, int]]:
    """Spend and leads per day for day-7 .. day (ad account time zone)."""
    rows = client.get_all(f"{act}/insights", {
        "level": "account",
        "fields": "spend,actions,account_currency",
        "time_range": json.dumps({"since": (day - timedelta(days=7)).isoformat(), "until": day.isoformat()}),
        "time_increment": 1,
        "limit": 100,
    })
    out: dict[str, tuple[float, int]] = {}
    for r in rows:
        out[r.get("date_start")] = (float(r.get("spend") or 0), count_leads(r.get("actions")))
    return out


def crm_days(contacts: list[dict], rules: dict, tz: ZoneInfo) -> dict[str, dict]:
    """Per local day: tagged, meta-source and either-rule counts."""
    out: dict[str, dict] = {}
    for c in contacts:
        added = parse_date(c.get("dateAdded"))
        if not added:
            continue
        key = added.astimezone(tz).date().isoformat()
        tagged, source = classify(c, rules)
        d = out.setdefault(key, {"tagged": 0, "source": 0, "meta": 0})
        d["tagged"] += tagged
        d["source"] += source
        d["meta"] += tagged or source
    return out


def build_stats(biz: dict, day: date, tz: ZoneInfo, graph: GraphClient | None,
                ghl: GHLClient | None) -> DayStats:
    rules = biz.get("meta_lead_rules") or {}
    s = DayStats(name=biz.get("name", "Unnamed"), currency=biz.get("currency", ""),
                 target_cpl=biz.get("target_cpl"), tag_rules=bool(rules.get("tags")))
    ramp = biz.get("ramp_until")
    s.in_ramp = bool(ramp) and day <= (ramp if isinstance(ramp, date) else date.fromisoformat(str(ramp)))
    prior = [(day - timedelta(days=i)).isoformat() for i in range(1, 8)]

    if ghl is None:
        s.crm_error = "No GHL token found (check token_env in config and .env)."
    else:
        try:
            start = datetime.combine(day - timedelta(days=7), time.min, tz)
            end = datetime.combine(day + timedelta(days=1), time.min, tz)
            location = (biz.get("ghl") or {}).get("location_id")
            if not location:
                raise GHLError("ghl.location_id missing in config")
            days = crm_days(ghl.search_contacts(location, start, end), rules, tz)
            today = days.get(day.isoformat(), {})
            s.crm_tagged, s.crm_source, s.crm_meta = (today.get(k, 0) for k in ("tagged", "source", "meta"))
            s.crm_meta_avg7 = sum(days.get(d, {}).get("meta", 0) for d in prior) / 7
        except (GHLError, requests.RequestException) as exc:
            s.crm_error = str(exc)

    act = biz.get("meta_ad_account_id")
    if act and graph is not None:
        try:
            days = meta_days(graph, act, day)
            s.meta_spend, s.meta_leads = days.get(day.isoformat(), (0.0, 0))
            s.meta_spend_7d = sum(days.get(d, (0.0, 0))[0] for d in prior)
            s.meta_leads_7d = sum(days.get(d, (0.0, 0))[1] for d in prior)
            s.meta_leads_avg7 = s.meta_leads_7d / 7
        except (GraphError, requests.RequestException) as exc:
            s.meta_error = str(exc)
    elif act:
        s.meta_error = "META_ACCESS_TOKEN not set."
    return s


# ---------------------------------------------------------------- output

def status_line(s: DayStats) -> str:
    parts = []
    if s.meta_leads is not None and not s.meta_error:
        cpl = f", CPL {s.meta_cpl:,.2f}" if s.meta_cpl else ""
        parts.append(f"Meta {s.meta_leads} leads, spend {s.meta_spend:,.2f} {s.currency}{cpl}")
    if not s.crm_error:
        parts.append(f"CRM {s.crm_meta} Meta leads ({s.crm_tagged} tagged), 7-day avg {s.crm_meta_avg7:.1f}")
    return ". ".join(parts) or "no data"


def render_markdown(results: list[tuple[DayStats, list]], day: date) -> str:
    L = [f"# Lead flow watchdog, {day.isoformat()}", "",
         "Meta leads = lead form submissions (action_type 'lead' only). "
         "CRM Meta leads = GHL contacts matching your tag, source or UTM rules.", ""]
    L += ["| Business | Status | Meta leads | Meta spend | CRM Meta leads | CRM tagged | CRM 7-day avg |",
          "|---|---|---|---|---|---|---|"]
    for s, alerts in results:
        meta_ok = s.meta_leads is not None and not s.meta_error
        L.append(f"| {s.name} | {worst(alerts)} | {s.meta_leads if meta_ok else 'n/a'} | "
                 f"{f'{s.meta_spend:,.2f} {s.currency}' if meta_ok else 'n/a'} | "
                 f"{'n/a' if s.crm_error else s.crm_meta} | {'n/a' if s.crm_error else s.crm_tagged} | "
                 f"{'n/a' if s.crm_error else f'{s.crm_meta_avg7:.1f}'} |")
    L.append("")
    for s, alerts in results:
        L += [f"## {s.name}: {worst(alerts)}", "", status_line(s) + ".", ""]
        for a in alerts:
            L += [f"### [{a.severity}] {a.headline}", ""] + [f"- {d}" for d in a.detail]
            if a.next_steps:
                L += ["", "Next steps:"] + [f"{i}. {x}" for i, x in enumerate(a.next_steps, 1)]
            L.append("")
        if not alerts:
            L += ["No issues.", ""]
    return "\n".join(L)


def render_summary(results: list[tuple[DayStats, list]], day: date) -> str:
    L = [f"Lead flow watchdog, {day.strftime('%a %d %b %Y')}"]
    for s, alerts in sorted(results, key=lambda r: RANK.get(worst(r[1]), 3)):
        L.append("")
        L.append(f"{s.name}: {worst(alerts)}")
        L.append(f"  {status_line(s)}")
        for a in alerts:
            if a.severity != INFO or a.layer == "data-check":
                L.append(f"  [{a.severity}] {a.headline}")
                if a.next_steps:
                    L.append(f"    Next: {a.next_steps[0]}")
    return "\n".join(L)


# ---------------------------------------------------------------- demo transport

class _Resp:
    def __init__(self, body, status=200):
        self._body, self.status_code = body, status

    def json(self):
        return self._body


class DemoMetaSession:
    def __init__(self, data: dict):
        self.data = data

    def get(self, url, params=None, timeout=None):
        act = urlparse(url).path.split("/")[-2]
        return _Resp({"data": self.data.get(act, []), "paging": {}})


class DemoGHLSession:
    """Mimics POST /contacts/search: range filter, newest first, page/pageLimit, total."""

    def __init__(self, data: dict):
        self.data = data

    def post(self, url, json=None, headers=None, timeout=None):
        body = json or {}
        if not isinstance(body.get("pageLimit"), int):
            return _Resp({"message": "pageLimit must be a number"}, 422)
        rng = body["filters"][0]["value"]
        lo, hi = parse_date(rng["gte"]), parse_date(rng["lte"])
        rows = [c for c in self.data.get(body["locationId"], []) if lo <= parse_date(c["dateAdded"]) <= hi]
        rows.sort(key=lambda c: c["dateAdded"], reverse=True)
        n, page = body["pageLimit"], body["page"]
        return _Resp({"contacts": rows[(page - 1) * n: page * n], "total": len(rows)})


# ---------------------------------------------------------------- plumbing

def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def post_slack(text: str, webhook: str) -> None:
    r = requests.post(webhook, json={"text": text}, timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"Slack webhook returned {r.status_code}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Daily Meta to CRM lead-flow watchdog (read-only).")
    ap.add_argument("--config", default=str(SKILL_DIR / "config.yaml"))
    ap.add_argument("--day", help="day to check, YYYY-MM-DD (default: yesterday in the config time zone)")
    ap.add_argument("--business", help="only check the business with this name")
    ap.add_argument("--demo", action="store_true", help="use fixtures, no API calls")
    ap.add_argument("--send", action="store_true", help="post to SLACK_WEBHOOK_URL when anything is WARNING or worse")
    ap.add_argument("--send-all-clear", action="store_true", help="with --send, also post when everything is OK")
    ap.add_argument("--out", help="output folder for the markdown file")
    args = ap.parse_args(argv)

    load_env(SKILL_DIR / ".env")
    if args.demo:
        cfg = yaml.safe_load((FIXTURES / "demo_config.yaml").read_text())
        meta_fx = json.loads((FIXTURES / "demo_meta.json").read_text())
        ghl_fx = json.loads((FIXTURES / "demo_ghl.json").read_text())
        graph = GraphClient("demo", session=DemoMetaSession(meta_fx["insights"]))
        ghl_session = DemoGHLSession(ghl_fx["contacts"])
        day = date.fromisoformat(str(cfg["demo_day"]))
    else:
        path = Path(args.config)
        if not path.exists():
            print(f"No config at {path}. Copy config.example.yaml to config.yaml first.", file=sys.stderr)
            return 2
        cfg = yaml.safe_load(path.read_text()) or {}
        token = os.environ.get("META_ACCESS_TOKEN")
        graph = GraphClient(token, version=str(cfg.get("graph_version") or "v26.0")) if token else None
        ghl_session = None
        day = None

    tz = ZoneInfo(cfg.get("timezone") or "UTC")
    if args.day:
        day = date.fromisoformat(args.day)
    day = day or (datetime.now(timezone.utc).astimezone(tz).date() - timedelta(days=1))
    thresholds = cfg.get("thresholds") or {}
    page_limit = int(cfg.get("ghl_page_limit") or 100)

    results = []
    for biz in cfg.get("businesses") or []:
        if biz.get("active") is False or (args.business and biz.get("name") != args.business):
            continue
        watch = biz.get("watch_days") or WEEKDAYS
        if WEEKDAYS[day.weekday()] not in watch:
            print(f"{biz.get('name')}: {WEEKDAYS[day.weekday()]} not in watch_days, skipped.")
            continue
        ghl_token = "demo" if args.demo else os.environ.get((biz.get("ghl") or {}).get("token_env") or "GHL_TOKEN")
        ghl = GHLClient(ghl_token, session=ghl_session, page_limit=page_limit) if ghl_token else None
        biz_tz = ZoneInfo(biz["timezone"]) if biz.get("timezone") else tz
        stats = build_stats(biz, day, biz_tz, graph, ghl)
        results.append((stats, detect(stats, {**thresholds, **(biz.get("thresholds") or {})})))

    if not results:
        print("No businesses to check.", file=sys.stderr)
        return 2

    out_dir = Path(args.out) if args.out else SKILL_DIR / (cfg.get("output_dir") or "alerts") / ("demo" if args.demo else "")
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"watchdog_{day.isoformat()}.md"
    md_path.write_text(render_markdown(results, day))
    summary = render_summary(results, day)
    print(summary)
    print(f"\nFull report: {md_path}")

    if args.send:
        needs = any(a.severity in (CRITICAL, WARNING) for _, alerts in results for a in alerts)
        if args.demo:
            print("--send ignored in --demo mode.")
        elif not os.environ.get("SLACK_WEBHOOK_URL"):
            print("--send given but SLACK_WEBHOOK_URL is not set.", file=sys.stderr)
            return 1
        elif needs or args.send_all_clear:
            post_slack(summary, os.environ["SLACK_WEBHOOK_URL"])
            print("Posted to Slack.")
        else:
            print("All clear, nothing posted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
