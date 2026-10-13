"""Weekly Meta account report (read-only).

For each ad account in config.yaml: last 7 days (ending yesterday) vs the 7 days
before, at account, campaign and ad level. Writes a markdown report and prints a
short phone-readable summary. Posts to Slack only with --send.

Usage:
    python scripts/weekly_report.py --demo           # fixture data, no API calls
    python scripts/weekly_report.py                  # real run, print only
    python scripts/weekly_report.py --date 2026-03-12
    python scripts/weekly_report.py --send           # also post the summary to SLACK_WEBHOOK_URL
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from meta_graph import GraphClient, GraphError, count_leads  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
FIXTURES = SKILL_DIR / "fixtures"

DEFAULTS = {
    "graph_version": "v26.0",
    "min_leads_for_best": 3,
    "kill_multiplier": 2.0,
    "fatigue_frequency": 4.0,
    "drop_threshold": 0.40,
    "spend_held_ratio": 0.90,
    "fetch_budgets": True,
    "pacing_under": 0.80,
    "pacing_over": 1.15,
    "output_dir": "reports",
}

# Meta reports budgets in minor units. These currencies have no minor unit (offset 1).
ZERO_DECIMAL = {"CLP", "COP", "CRC", "HUF", "ISK", "IDR", "JPY", "KRW", "PYG", "TWD", "VND"}
SYMBOLS = {"GBP": "£", "USD": "$", "EUR": "€", "AUD": "A$", "CAD": "C$", "NZD": "NZ$"}

INSIGHT_FIELDS = {
    "account": "account_id,account_name,account_currency,spend,impressions,inline_link_clicks,ctr,cpm,frequency,actions",
    "campaign": "campaign_id,campaign_name,spend,impressions,inline_link_clicks,ctr,cpm,frequency,actions",
    "ad": "campaign_id,campaign_name,ad_id,ad_name,spend,impressions,inline_link_clicks,ctr,cpm,frequency,actions",
}


# ---------------------------------------------------------------- parsing

@dataclass
class Metrics:
    spend: float = 0.0
    impressions: int = 0
    clicks: int = 0
    leads: int = 0
    frequency: float | None = None

    @property
    def ctr(self) -> float | None:  # link CTR, %
        return self.clicks / self.impressions * 100 if self.impressions else None

    @property
    def cpm(self) -> float | None:
        return self.spend / self.impressions * 1000 if self.impressions else None

    @property
    def cpl(self) -> float | None:
        return self.spend / self.leads if self.leads else None


def parse_row(row: dict) -> Metrics:
    freq = row.get("frequency")
    return Metrics(
        spend=float(row.get("spend") or 0),
        impressions=int(float(row.get("impressions") or 0)),
        clicks=int(float(row.get("inline_link_clicks") or 0)),
        leads=count_leads(row.get("actions")),
        frequency=float(freq) if freq not in (None, "") else None,
    )


@dataclass
class Entity:
    id: str
    name: str
    this: Metrics = field(default_factory=Metrics)
    prior: Metrics = field(default_factory=Metrics)
    campaign_id: str | None = None


def join_rows(this_rows: list[dict], prior_rows: list[dict], level: str) -> dict[str, Entity]:
    out: dict[str, Entity] = {}
    for period, rows in (("this", this_rows), ("prior", prior_rows)):
        for r in rows:
            key = r.get(f"{level}_id") or "unknown"
            name = r.get(f"{level}_name") or key
            ent = out.setdefault(key, Entity(id=key, name=name, campaign_id=r.get("campaign_id")))
            if period == "this":
                ent.name = name
            setattr(ent, period, parse_row(r))
    return out


# ---------------------------------------------------------------- formatting

def money(v: float | None, cur: str) -> str:
    if v is None:
        return "n/a"
    sym = SYMBOLS.get(cur)
    digits = 0 if cur in ZERO_DECIMAL else (0 if abs(v) >= 1000 else 2)
    s = f"{v:,.{digits}f}"
    return f"{sym}{s}" if sym else f"{s} {cur}"


def delta(cur: float | None, prev: float | None) -> str:
    if cur is None or prev is None:
        return "n/a"
    if prev == 0:
        return "same" if cur == 0 else "▲ new"
    pct = (cur - prev) / prev * 100
    if abs(pct) < 0.5:
        return "= 0%"
    return f"{'▲' if pct > 0 else '▼'} {abs(pct):.0f}%"


def cell(text: str) -> str:
    """Make a name safe inside a markdown table."""
    return str(text).replace("|", "/").replace("\n", " ")


def num(v: float | None, digits: int = 0) -> str:
    return "n/a" if v is None else f"{v:,.{digits}f}"


# ---------------------------------------------------------------- analysis

@dataclass
class AccountResult:
    cfg: dict
    currency: str
    account: Entity
    campaigns: dict[str, Entity]
    ads: dict[str, Entity]
    budgets: list[dict] = field(default_factory=list)
    best: Entity | None = None
    kills: list[tuple[Entity, str]] = field(default_factory=list)
    fatigued: list[Entity] = field(default_factory=list)
    drops: list[tuple[str, Entity, float]] = field(default_factory=list)
    pacing: list[dict] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    error: str | None = None


def find_best(ads: dict[str, Entity], min_leads: int, exclude: set[str] | None = None) -> Entity | None:
    """Lowest CPL among ads with enough leads that are not kill candidates."""
    exclude = exclude or set()
    pool = [a for a in ads.values()
            if a.this.leads >= min_leads and a.this.cpl is not None and a.id not in exclude]
    return min(pool, key=lambda a: a.this.cpl) if pool else None


def find_kills(ads: dict[str, Entity], target: float | None, mult: float, cur: str) -> list[tuple[Entity, str]]:
    if not target:
        return []
    out = []
    for a in ads.values():
        m = a.this
        if m.leads == 0 and m.spend >= mult * target:
            out.append((a, f"spent {money(m.spend, cur)} with 0 leads"))
        elif m.leads > 0 and m.cpl is not None and m.cpl > mult * target:
            out.append((a, f"CPL {money(m.cpl, cur)} vs target {money(target, cur)}"))
    return sorted(out, key=lambda x: -x[0].this.spend)


def find_fatigue(ads: dict[str, Entity], threshold: float) -> list[Entity]:
    return sorted([a for a in ads.values() if (a.this.frequency or 0) >= threshold],
                  key=lambda a: -(a.this.frequency or 0))


def is_sudden_drop(e: Entity, drop: float, held: float) -> float | None:
    """Spend held or rose but leads fell by >= drop. Returns the fall (0-1) or None."""
    t, p = e.this, e.prior
    if p.leads <= 0 or p.spend <= 0:
        return None
    if t.spend < p.spend * held:
        return None
    fall = (p.leads - t.leads) / p.leads
    return fall if fall >= drop else None


def budget_divisor(cur: str, cfg: dict) -> float:
    if cfg.get("budget_divisor"):
        return float(cfg["budget_divisor"])
    return 1.0 if cur in ZERO_DECIMAL else 100.0


def compute_pacing(campaigns_meta: list[dict], camp_insights: dict[str, Entity], cur: str,
                   cfg: dict, opts: dict) -> list[dict]:
    div = budget_divisor(cur, cfg)
    out = []
    for c in campaigns_meta:
        if c.get("effective_status", "ACTIVE") != "ACTIVE":
            continue
        spend = camp_insights[c["id"]].this.spend if c["id"] in camp_insights else 0.0
        row = {"id": c["id"], "name": c.get("name", c["id"]), "spend": spend}
        if c.get("daily_budget"):
            daily = float(c["daily_budget"]) / div
            ratio = spend / (daily * 7) if daily else 0
            row.update(daily=daily, ratio=ratio,
                       status="underspending" if ratio < opts["pacing_under"]
                       else "overspending" if ratio > opts["pacing_over"] else "on pace")
        elif c.get("lifetime_budget"):
            row.update(status="lifetime budget, not paced weekly",
                       lifetime=float(c["lifetime_budget"]) / div)
        else:
            row.update(status="ad set budgets, not checked here")
        out.append(row)
    return out


def build_actions(res: AccountResult, opts: dict) -> list[str]:
    cur = res.currency
    acts: list[str] = []
    for level, ent, fall in res.drops:
        if level == "account":
            acts.append(f"Leads fell {fall*100:.0f}% while spend held: check the lead form to CRM sync "
                        "(submit a test lead, confirm it lands) before changing ads.")
            break
    if res.kills:
        names = ", ".join(f'"{a.name}" ({why})' for a, why in res.kills[:2])
        acts.append(f"Pause {names}.")
    if res.fatigued:
        a = res.fatigued[0]
        acts.append(f'Refresh creative on "{a.name}" (frequency {a.this.frequency:.1f}).')
    unders = [p for p in res.pacing if p.get("status") == "underspending"]
    if unders:
        p = unders[0]
        acts.append(f'"{p["name"]}" spent {p["ratio"]*100:.0f}% of its weekly budget: check delivery '
                    "(ad approvals, audience size, bid caps).")
    target = res.cfg.get("target_cpl")
    if res.best and len(acts) < 3 and (not target or res.best.this.cpl <= target):
        acts.append(f'Give more budget to "{res.best.name}" (CPL {money(res.best.this.cpl, cur)} '
                    f"on {res.best.this.leads} leads).")
    if not acts:
        acts.append("Nothing urgent. Hold steady and keep fresh creative in the pipeline.")
    return acts[:3]


def analyse(acct_cfg: dict, client: GraphClient, this_rng: tuple[date, date],
            prior_rng: tuple[date, date], opts: dict) -> AccountResult:
    act = acct_cfg["id"]

    def pull(level: str, rng: tuple[date, date]) -> list[dict]:
        return client.get_all(f"{act}/insights", {
            "level": level,
            "fields": INSIGHT_FIELDS[level],
            "time_range": json.dumps({"since": rng[0].isoformat(), "until": rng[1].isoformat()}),
            "limit": 500,
        })

    acc_this, acc_prior = pull("account", this_rng), pull("account", prior_rng)
    cur = acct_cfg.get("currency") or (acc_this or acc_prior or [{}])[0].get("account_currency") or "USD"
    account = Entity(id=act, name=acct_cfg.get("name") or (acc_this or acc_prior or [{}])[0].get("account_name") or act)
    account.this = parse_row(acc_this[0]) if acc_this else Metrics()
    account.prior = parse_row(acc_prior[0]) if acc_prior else Metrics()
    campaigns = join_rows(pull("campaign", this_rng), pull("campaign", prior_rng), "campaign")
    ads = join_rows(pull("ad", this_rng), pull("ad", prior_rng), "ad")

    res = AccountResult(cfg=acct_cfg, currency=cur, account=account, campaigns=campaigns, ads=ads)
    target = acct_cfg.get("target_cpl")
    res.kills = find_kills(ads, target, opts["kill_multiplier"], cur)
    res.best = find_best(ads, opts["min_leads_for_best"], {a.id for a, _ in res.kills})
    res.fatigued = find_fatigue(ads, opts["fatigue_frequency"])
    for level, ents in (("account", {"a": account}), ("campaign", campaigns)):
        for e in ents.values():
            fall = is_sudden_drop(e, opts["drop_threshold"], opts["spend_held_ratio"])
            if fall is not None:
                res.drops.append((level, e, fall))
    if opts["fetch_budgets"]:
        meta = client.get_all(f"{act}/campaigns", {
            "fields": "id,name,effective_status,daily_budget,lifetime_budget",
            "effective_status": json.dumps(["ACTIVE"]),
            "limit": 500,
        })
        res.pacing = compute_pacing(meta, campaigns, cur, acct_cfg, opts)
    res.actions = build_actions(res, opts)
    return res


# ---------------------------------------------------------------- output

def metric_rows(e: Entity, cur: str) -> list[tuple[str, str, str, str]]:
    t, p = e.this, e.prior
    return [
        ("Spend", money(t.spend, cur), money(p.spend, cur), delta(t.spend, p.spend)),
        ("Impressions", num(t.impressions), num(p.impressions), delta(t.impressions, p.impressions)),
        ("Link clicks", num(t.clicks), num(p.clicks), delta(t.clicks, p.clicks)),
        ("Link CTR", num(t.ctr, 2) + "%", num(p.ctr, 2) + "%", delta(t.ctr, p.ctr)),
        ("CPM", money(t.cpm, cur), money(p.cpm, cur), delta(t.cpm, p.cpm)),
        ("Frequency", num(t.frequency, 2), num(p.frequency, 2), delta(t.frequency, p.frequency)),
        ("Leads", num(t.leads), num(p.leads), delta(t.leads, p.leads)),
        ("CPL", money(t.cpl, cur), money(p.cpl, cur), delta(t.cpl, p.cpl)),
    ]


def render_markdown(results: list[AccountResult], this_rng, prior_rng) -> str:
    L = [f"# Weekly Meta account report, week ending {this_rng[1].isoformat()}", "",
         f"This week: {this_rng[0]} to {this_rng[1]}. Prior week: {prior_rng[0]} to {prior_rng[1]}.",
         "Leads = Meta 'lead' action only. Currencies are never added together.", ""]

    by_cur: dict[str, list[AccountResult]] = {}
    for r in results:
        if not r.error:
            by_cur.setdefault(r.currency, []).append(r)
    if by_cur:
        L += ["## Totals by currency", "", "| Currency | Spend | Change | Leads | Change | CPL |",
              "|---|---|---|---|---|---|"]
        for cur, rs in sorted(by_cur.items()):
            st, sp = sum(r.account.this.spend for r in rs), sum(r.account.prior.spend for r in rs)
            lt, lp = sum(r.account.this.leads for r in rs), sum(r.account.prior.leads for r in rs)
            L.append(f"| {cur} | {money(st, cur)} | {delta(st, sp)} | {lt} | {delta(lt, lp)} | "
                     f"{money(st / lt if lt else None, cur)} |")
        L.append("")

    for r in results:
        cur = r.currency
        L += [f"## {r.account.name} ({cur})", ""]
        if r.error:
            L += [f"Could not pull this account: {r.error}", ""]
            continue
        tgt = r.cfg.get("target_cpl")
        L.append(f"Target CPL: {money(tgt, cur) if tgt else 'not set (kill checks skipped)'}")
        L += ["", "### Do this week", ""] + [f"{i}. {a}" for i, a in enumerate(r.actions, 1)] + [""]
        L += ["### Account", "", "| Metric | This week | Prior week | Change |", "|---|---|---|---|"]
        L += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in metric_rows(r.account, cur)] + [""]

        L += ["### Flags", ""]
        flags = []
        if r.best:
            flags.append(f"- Best ad: {r.best.name}, CPL {money(r.best.this.cpl, cur)} on {r.best.this.leads} leads")
        flags += [f"- Kill candidate: {a.name}, {why}" for a, why in r.kills]
        flags += [f"- Fatigue: {a.name}, frequency {a.this.frequency:.2f}" for a in r.fatigued]
        flags += [f"- Sudden drop ({lvl}): {e.name if lvl != 'account' else 'whole account'}, spend "
                  f"{delta(e.this.spend, e.prior.spend)}, leads down {fall*100:.0f}%. "
                  "Check the lead form to CRM sync." for lvl, e, fall in r.drops]
        L += (flags or ["- None"]) + [""]

        L += ["### Campaigns", "", "| Campaign | Spend | Chg | Leads | Chg | CPL | Chg | Freq |",
              "|---|---|---|---|---|---|---|---|"]
        for c in sorted(r.campaigns.values(), key=lambda e: -e.this.spend):
            t, p = c.this, c.prior
            L.append(f"| {cell(c.name)} | {money(t.spend, cur)} | {delta(t.spend, p.spend)} | {t.leads} | "
                     f"{delta(t.leads, p.leads)} | {money(t.cpl, cur)} | {delta(t.cpl, p.cpl)} | "
                     f"{num(t.frequency, 2)} |")
        L += ["", "### Ads", "", "| Ad | Spend | Leads | CPL | CPL chg | Link CTR | CPM | Freq |",
              "|---|---|---|---|---|---|---|---|"]
        for a in sorted(r.ads.values(), key=lambda e: -e.this.spend):
            t, p = a.this, a.prior
            L.append(f"| {cell(a.name)} | {money(t.spend, cur)} | {t.leads} | {money(t.cpl, cur)} | "
                     f"{delta(t.cpl, p.cpl)} | {num(t.ctr, 2)}% | {money(t.cpm, cur)} | {num(t.frequency, 2)} |")
        if r.pacing:
            L += ["", "### Budget pacing (active campaigns)", "",
                  "| Campaign | Weekly budget | Spent | Pace | Status |", "|---|---|---|---|---|"]
            for p in r.pacing:
                wk = money(p["daily"] * 7, cur) if "daily" in p else "n/a"
                pace = f"{p['ratio']*100:.0f}%" if "ratio" in p else "n/a"
                L.append(f"| {cell(p['name'])} | {wk} | {money(p['spend'], cur)} | {pace} | {p['status']} |")
        L.append("")
    return "\n".join(L)


def render_summary(results: list[AccountResult], this_rng) -> str:
    L = [f"Meta weekly, w/e {this_rng[1].strftime('%d %b %Y')}"]
    for r in results:
        cur, t, p = r.currency, r.account.this, r.account.prior
        L.append("")
        if r.error:
            L.append(f"{r.account.name}: pull failed ({r.error})")
            continue
        L.append(f"{r.account.name} ({cur})")
        L.append(f"Spend {money(t.spend, cur)} {delta(t.spend, p.spend)} | Leads {t.leads} "
                 f"{delta(t.leads, p.leads)} | CPL {money(t.cpl, cur)} {delta(t.cpl, p.cpl)}")
        if any(lvl == "account" for lvl, _, _ in r.drops):
            L.append("ALERT: leads dropped while spend held. Check the lead form to CRM sync.")
        if r.best:
            L.append(f"Best: {r.best.name} ({money(r.best.this.cpl, cur)} CPL)")
        L.append("Do this week:")
        L += [f" {i}. {a}" for i, a in enumerate(r.actions, 1)]
    return "\n".join(L)


# ---------------------------------------------------------------- plumbing

def load_env(path: Path) -> None:
    """Minimal .env loader. Existing environment variables win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def windows(today: date) -> tuple[tuple[date, date], tuple[date, date]]:
    end = today - timedelta(days=1)
    this_rng = (end - timedelta(days=6), end)
    prior_rng = (end - timedelta(days=13), end - timedelta(days=7))
    return this_rng, prior_rng


class _FixtureResponse:
    def __init__(self, body: dict, status: int = 200):
        self._body, self.status_code = body, status

    def json(self):
        return self._body


class FixtureSession:
    """Serves fixture JSON in place of graph.facebook.com. Keys mirror the real request."""

    def __init__(self, responses: dict):
        self.responses = responses

    def get(self, url, params=None, timeout=None):
        if url.startswith("demo://"):
            key, idx = url[len("demo://"):].rsplit("#", 1)
            return _FixtureResponse(self.responses[key][int(idx)])
        path = urlparse(url).path.split("/")
        act, edge = path[-2], path[-1]
        params = params or {}
        if edge == "insights":
            since = json.loads(params["time_range"])["since"]
            key = f"{act}|insights|{params['level']}|{since}"
        else:
            key = f"{act}|{edge}"
        pages = self.responses.get(key, [{"data": []}])
        return _FixtureResponse(pages[0])


def post_slack(text: str, webhook: str) -> None:
    r = requests.post(webhook, json={"text": text}, timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"Slack webhook returned {r.status_code}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Weekly Meta account report (read-only).")
    ap.add_argument("--config", default=str(SKILL_DIR / "config.yaml"))
    ap.add_argument("--date", help="treat this date as today (YYYY-MM-DD); window ends the day before")
    ap.add_argument("--demo", action="store_true", help="use fixtures, no API calls")
    ap.add_argument("--send", action="store_true", help="also post the summary to SLACK_WEBHOOK_URL")
    ap.add_argument("--out", help="output folder for the markdown file")
    args = ap.parse_args(argv)

    load_env(SKILL_DIR / ".env")
    if args.demo:
        cfg = yaml.safe_load((FIXTURES / "demo_config.yaml").read_text())
        responses = json.loads((FIXTURES / "demo_graph.json").read_text())
        today = date.fromisoformat(responses["reference_date"])
        client = GraphClient("demo-token", session=FixtureSession(responses["responses"]))
    else:
        cfg_path = Path(args.config)
        if not cfg_path.exists():
            print(f"No config at {cfg_path}. Copy config.example.yaml to config.yaml first.", file=sys.stderr)
            return 2
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
        token = os.environ.get("META_ACCESS_TOKEN")
        if not token:
            print("META_ACCESS_TOKEN is not set (see SETUP.md).", file=sys.stderr)
            return 2
        today = date.fromisoformat(args.date) if args.date else date.today()
        client = GraphClient(token, version=str(cfg.get("graph_version") or DEFAULTS["graph_version"]))

    opts = {**DEFAULTS, **(cfg.get("defaults") or {})}
    this_rng, prior_rng = windows(today)
    results = []
    for acct in cfg.get("accounts") or []:
        try:
            results.append(analyse(acct, client, this_rng, prior_rng, opts))
        except GraphError as exc:
            results.append(AccountResult(cfg=acct, currency=acct.get("currency", "?"),
                                         account=Entity(id=acct["id"], name=acct.get("name", acct["id"])),
                                         campaigns={}, ads={}, error=str(exc)))
    if not results:
        print("No accounts in config.", file=sys.stderr)
        return 2

    out_dir = Path(args.out) if args.out else SKILL_DIR / opts["output_dir"] / ("demo" if args.demo else "")
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"weekly_report_{this_rng[1].isoformat()}.md"
    md_path.write_text(render_markdown(results, this_rng, prior_rng))
    summary = render_summary(results, this_rng)
    print(summary)
    print(f"\nFull report: {md_path}")

    if args.send:
        if args.demo:
            print("--send ignored in --demo mode.")
        elif not os.environ.get("SLACK_WEBHOOK_URL"):
            print("--send given but SLACK_WEBHOOK_URL is not set.", file=sys.stderr)
            return 1
        else:
            post_slack(summary, os.environ["SLACK_WEBHOOK_URL"])
            print("Posted to Slack.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
