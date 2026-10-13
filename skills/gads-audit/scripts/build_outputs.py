#!/usr/bin/env python3
"""MODULE 5 - turn the four modules' JSON into the things a human uses.

  python3 build_outputs.py --dir WORKDIR --client SLUG --customer CUSTOMER_ID [options]

Reads whatever exists in WORKDIR: account-audit.json, keywords.json, landing-page.json,
competitors-pass-*.json. Always writes:
  actions.json           every recommended change, one row per action
  actions-<tab>.csv      one CSV per action type
  actions.xlsx           one sheet per action type (openpyxl if present, else CSVs only)
  CONTRACTOR-EMAIL.md    numbered change list for whoever runs the account, with a confirmation ask
  SUMMARY.html           one self-contained internal page: the three numbers, critical findings,
                         the one decision, and the action counts (open it in a browser)

Options
  --supabase             OPTIONAL: upsert gads_accounts, gads_daily and gads_audit_findings into
                         your own Supabase project (needs SUPABASE_URL + SUPABASE_SERVICE_KEY;
                         schema in ../references/supabase-schema.sql)
  --contractor "Name"    who the email is addressed to (default: GADS_AUDIT_OWNER or "there")
  --sender "Name"        who signs the email (default: GADS_AUDIT_SENDER or blank)
  --client-name "Name"   display name in the outputs
  --run-id UUID          audit run id (default: generated; same id groups the findings)

Action tabs
  keywords-to-add, negatives-to-add, keywords-to-pause, targeting-changes,
  bid-and-budget-changes, landing-page-fixes
Each row: item, why, evidence (a number computed this run), who, status.

Nothing here sends anything. The email is a draft and the summary page is internal. Import
actions.xlsx into Google Sheets yourself (File > Import) if you want a shared tracker.
Anything client-facing needs a human's approval first.
"""
import csv
import glob
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gadslib import md_table, now_stamp, read_json, write_json

# urllib on some Python installs (python.org macOS builds) has no CA bundle: every https call needs
# certifi explicitly or it dies CERTIFICATE_VERIFY_FAILED, which reads like the service being down.
try:
    import certifi
    CTX = __import__("ssl").create_default_context(cafile=certifi.where())
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    CTX = __import__("ssl").create_default_context()

TABS = ["keywords-to-add", "negatives-to-add", "keywords-to-pause", "targeting-changes",
        "bid-and-budget-changes", "landing-page-fixes"]
HEAD = ["item", "why", "evidence", "who", "status"]


def arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag) + 1
        if i < len(sys.argv):
            return sys.argv[i]
    return default


def flagged(n):
    return n in sys.argv


# --------------------------------------------------------------------- actions
def build_actions(audit, kw, lp, comp, who):
    A = {t: [] for t in TABS}
    cur = ((audit or {}).get("account") or {}).get("currency") or ""
    in_account = {k["text"].lower() for k in (audit or {}).get("keywords", [])}
    neg_now = set()
    for c in (audit or {}).get("campaigns", []):
        neg_now |= {(n["text"] or "").lower() for n in c["campaign_negatives"]}
    for s in (audit or {}).get("shared_sets", []):
        if not s["brand_safety"]:
            neg_now |= {(t["text"] or "").lower() for t in s["terms"]}
    neg_now |= {(n["text"] or "").lower() for n in (audit or {}).get("ad_group_negatives", [])}

    terms = (kw or {}).get("terms", [])
    for t in sorted([t for t in terms if t["intent"] == "CORE"], key=lambda t: -t["volume"]):
        if t["keyword"].lower() in in_account:
            continue
        bid = t.get("high_top_of_page_bid_account_currency")
        A["keywords-to-add"].append([
            t["keyword"],
            "Core buyer intent for what the live page sells, and not in the account.",
            f"{t['volume']} searches/month"
            + (f", top-of-page bid about {cur} {bid:.2f}" if bid else ", no bid data"),
            who, "proposed"])
    for t in sorted([t for t in terms if t["intent"] in ("NEGATIVE", "INVESTOR")],
                    key=lambda t: -t["volume"]):
        root = t.get("intent_token") or t["keyword"]
        if root.strip().lower() in neg_now:
            continue
        A["negatives-to-add"].append([
            root.strip(),
            ("Job seeker, course hunter or benefits search, not a service buyer."
             if t["intent"] == "NEGATIVE" else
             "Property investor intent, not a service buyer. A trap in this niche."),
            f"matched on '{root.strip()}', example '{t['keyword']}' at {t['volume']} searches/month",
            who, "proposed"])
    # one row per negative root, keeping the biggest example
    seen, dedup = set(), []
    for r in A["negatives-to-add"]:
        if r[0].lower() in seen:
            continue
        seen.add(r[0].lower())
        dedup.append(r)
    A["negatives-to-add"] = dedup

    vol = {t["keyword"].lower(): t["volume"] for t in terms}
    for k in (audit or {}).get("keywords", []):
        if k["status"] != "ENABLED":
            continue
        v = vol.get(k["text"].lower())
        if v is None and k["impressions"] == 0:
            A["keywords-to-pause"].append([
                k["text"],
                "No measurable monthly search volume in this run and no impressions in the window. "
                "Verify before pausing: absent from the keyword tool is not always absent from "
                "Google, but it is never worth a bid rise.",
                f"0 impressions, no volume returned for '{k['text']}'", who, "check first"])
        elif v is not None and v < 10 and k["impressions"] == 0:
            A["keywords-to-pause"].append([
                k["text"], "Under 10 searches a month and no impressions.",
                f"{v} searches/month, 0 impressions", who, "proposed"])

    for c in (audit or {}).get("campaigns", []):
        if c["status"] != "ENABLED":
            continue
        if c["ad_schedule_hours"] < 120:
            A["targeting-changes"].append([
                f"{c['name']}: widen the ad schedule",
                "Ads only run part of the week, so enquiries outside those hours never see them.",
                f"{c['ad_schedule_hours']:g} of 168 hours "
                f"({c['ad_schedule_hours'] / 168 * 100:.0f}% of the week)", who, "proposed"])
        for f in (audit or {}).get("findings", []):
            if f["code"] == "NEGATIVE_BLOCKS_PRIORITY_GEO":
                A["targeting-changes"].append([
                    f["title"],
                    "The client has named this place a priority, and a negative keyword stops ads "
                    "showing for it. One of the two has to change.",
                    f["detail"], who, "needs client confirmation"])
        geo_core = (kw or {}).get("by_geo", {})
        for gname, v in geo_core.items():
            if v["core"] >= 50 and not any(gname in (str(x) or "").lower() for x in c["location_targets"]):
                A["targeting-changes"].append([
                    f"{c['name']}: check coverage of {gname}",
                    f"Measurable core demand names {gname}, and no targeted location's NAME contains "
                    "it. A council or LGA target can still cover the place, so this is a check, not "
                    "a confirmed gap.",
                    f"{v['core']} core searches/month naming {gname}; current targets: "
                    + "; ".join(str(x) for x in c["location_targets"][:8]), who, "check first"])
        w = c["window"]
        rank, budget = w["search_lost_is_rank_pct"], w["search_lost_is_budget_pct"]
        market = ((kw or {}).get("market") or {}).get("core_median_top_of_page_bid_account_currency")
        bids = [k["bid"] for k in (audit or {}).get("keywords", [])
                if k["campaign"] == c["name"] and k["bid"]]
        med = sorted(bids)[len(bids) // 2] if bids else None
        if rank is not None and rank >= 25:
            A["bid-and-budget-changes"].append([
                f"{c['name']}: raise bids, leave the budget alone",
                "Impressions are lost to Ad Rank, not to money running out. More budget buys nothing.",
                f"{rank:.1f}% lost to rank vs {budget if budget is not None else 'no data'}% lost to "
                f"budget" + (f"; median bid {cur} {med:.2f} vs market {cur} {market:.2f}"
                             if med and market else ""), who, "proposed"])
        if budget is not None and budget >= 20:
            A["bid-and-budget-changes"].append([
                f"{c['name']}: raise the daily budget",
                "Impressions are genuinely being lost because the daily cap is reached.",
                f"{budget:.1f}% lost to budget, daily budget {cur} {c['daily_budget']:.2f}",
                who, "proposed"])
        absorb = ((kw or {}).get("market") or {}).get("max_absorbable_daily_spend_core")
        if absorb and c["daily_budget"] > absorb * 3:
            A["bid-and-budget-changes"].append([
                f"{c['name']}: the daily budget is far above what this market can absorb",
                "The ceiling is how many people search, not the cap. A budget this far above the "
                "market reads as headroom that does not exist.",
                f"budget {cur} {c['daily_budget']:.2f}/day vs about {cur} {absorb:.2f}/day absorbable "
                f"on core demand", who, "for discussion"])
        if c["bidding_strategy"] == "MANUAL_CPC":
            A["bid-and-budget-changes"].append([
                f"{c['name']}: bidding strategy",
                "Manual CPC means a person is guessing the auction price every week.",
                f"MANUAL_CPC, enhanced CPC {'on' if c['enhanced_cpc'] else 'off'}, "
                f"{c['lifetime']['conversions']:g} conversions on record", who, "proposed"])

    for p in (lp or {}).get("pages", []):
        for i in p.get("issues", []):
            A["landing-page-fixes"].append([
                p["url"], i, "measured this run at the widths listed in LANDING-PAGE.md",
                "web team", "proposed"])
    if (lp or {}).get("thankyou", {}).get("issue"):
        A["landing-page-fixes"].append([lp["thankyou"]["url"], lp["thankyou"]["issue"],
                                        f"HTTP {lp['thankyou']['status']}", "web team", "proposed"])
    for f in (audit or {}).get("findings", []):
        if f["code"] in ("QS_LANDING_PAGE_BELOW_AVERAGE", "AD_FINAL_URL_DRIFT",
                         "CLICKS_NO_CONVERSIONS"):
            A["landing-page-fixes"].append([f["title"], f["detail"], f["recommended_action"],
                                            "web team", "proposed"])
    return A


# --------------------------------------------------------------------- outputs
def write_csvs(A, out):
    paths = []
    for t, rows in A.items():
        p = os.path.join(out, f"actions-{t}.csv")
        with open(p, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(HEAD)
            w.writerows(rows)
        paths.append(p)
    return paths


def write_xlsx(A, out):
    try:
        from openpyxl import Workbook
    except ImportError:
        print("[out] openpyxl not installed, CSVs only", file=sys.stderr)
        return None
    wb = Workbook()
    wb.remove(wb.active)
    for t in TABS:
        ws = wb.create_sheet(t[:31])
        ws.append(HEAD)
        for r in A[t]:
            ws.append([str(x)[:3000] for x in r])
        for col, width in zip("ABCDE", (46, 70, 54, 18, 22)):
            ws.column_dimensions[col].width = width
        ws.freeze_panes = "A2"
    p = os.path.join(out, "actions.xlsx")
    wb.save(p)
    return p


def contractor_email(audit, kw, lp, A, client_name, contractor, run_id, sender=""):
    cur = ((audit or {}).get("account") or {}).get("currency") or ""
    crit = [f for f in (audit or {}).get("findings", []) if f["severity"] == "critical"]
    warn = [f for f in (audit or {}).get("findings", []) if f["severity"] == "warning"]
    camp = ((audit or {}).get("campaigns") or [{}])[0]
    w = camp.get("window", {})
    n = 0
    lines = []
    # structure and money first, then the long keyword lists: the bid/budget split is the actual fix
    email_order = ["bid-and-budget-changes", "negatives-to-add", "targeting-changes",
                   "landing-page-fixes", "keywords-to-pause", "keywords-to-add"]
    for t in email_order:
        if not A[t]:
            continue
        lines.append(f"**{t.replace('-', ' ')}**")
        cap = 6 if t.startswith("keywords") else 12
        for r in A[t][:cap]:
            n += 1
            lines.append(f"{n}. **{r[0]}** - {r[1]} ({r[2]})")
        if len(A[t]) > cap:
            lines.append(f"   (plus {len(A[t]) - cap} more under {t} in the sheet)")
        lines.append("")
    L = [f"# Draft email to {contractor} - {client_name} Google Ads", "",
         "DRAFT. Nothing is sent from this skill. Read it, change it, then send it yourself.", "",
         f"**Subject:** {client_name} Google Ads: {len(crit)} things to change, and one question", "",
         "---", "",
         f"Hi {contractor},", "",
         f"I went through the {client_name} account this morning and pulled the numbers straight from "
         "the API. Here is what I am seeing and what I would like changed. Numbers in brackets are "
         "from that pull, so shout if any of them look wrong at your end.", ""]
    if w:
        L += [f"Where it stands over the last {(audit or {}).get('window', {}).get('days', 30)} days: "
              f"{cur} {w.get('spend', 0):.2f} spent, {w.get('impressions', 0)} impressions, "
              f"{w.get('clicks', 0)} clicks, {w.get('conversions', 0):g} conversions. "
              + (f"Impression share {w['search_impression_share_pct']:.1f}%, "
                 f"{w['search_lost_is_rank_pct']:.1f}% lost to rank and "
                 f"{w['search_lost_is_budget_pct']:.1f}% lost to budget."
                 if w.get("search_lost_is_rank_pct") is not None else
                 "Google has not reported impression share yet."), ""]
        if (w.get("search_lost_is_rank_pct") or 0) >= 50 and (w.get("search_lost_is_budget_pct") or 0) < 10:
            L += ["That split is the whole story: nothing is being lost to budget, so the money is "
                  "not the constraint. The bids are not getting into the auction.", ""]
    L += ["## What I would like changed", ""] + lines + ["",
          "## One question back", "",
          "Can you confirm, item by item, which of these you are happy to do and which you would "
          "push back on, and anything you have already changed that I would not see yet? I would "
          "rather hear the disagreement now than find it in next week's numbers.", ""]
    L += ["The full list with the evidence per row is in the attached actions.xlsx.", ""]
    L += ["Thanks,", sender or "[your name]", "", "---", "",
          f"Audit run {run_id}. Source: Google Ads API read-only"
          + (f" plus DataForSEO (US${kw.get('run_cost_usd', 0):.2f})" if kw else "") + ".", ""]
    return "\n".join(L)


def summary_html(audit, kw, A, client_name, run_id):
    """One self-contained internal HTML page. Brand: if ~/.claude/brand/tokens.css exists its CSS
    variables (--color-primary, --font-body, --color-bg) are inlined; otherwise neutral defaults."""
    import html as H
    cur = ((audit or {}).get("account") or {}).get("currency") or ""
    crit = [f for f in (audit or {}).get("findings", []) if f["severity"] == "critical"]
    camp = ((audit or {}).get("campaigns") or [{}])[0]
    w = camp.get("window", {})
    market = (kw or {}).get("market") or {}
    absorb = market.get("max_absorbable_daily_spend_core")
    rank, budget = w.get("search_lost_is_rank_pct"), w.get("search_lost_is_budget_pct")
    verdict = ("Raise the bids, not the budget." if (rank or 0) >= 25 else
               "Raise the budget before touching the bids." if (budget or 0) >= 20 else
               "Fix serving, tracking and negatives first; neither bids nor budget is the constraint yet.")
    tokens = ""
    tp = os.path.expanduser("~/.claude/brand/tokens.css")
    if os.path.exists(tp):
        tokens = open(tp).read()
    fmt = lambda v: "no data" if v is None else f"{v:.0f}%"
    tiles = [("Spend in window", f"{cur} {w.get('spend', 0):.2f}" if w else "no data"),
             ("Lost to rank", fmt(rank)), ("Lost to budget", fmt(budget)),
             ("Critical findings", str(len(crit)))]
    body = (f"Lost to rank {fmt(rank)} against lost to budget {fmt(budget)}. "
            + (f"Core demand is about {market.get('core_monthly_searches')} searches a month, so the most "
               f"this market can absorb is roughly {cur} {absorb:.2f} a day against a daily budget of "
               f"{cur} {camp.get('daily_budget', 0):.2f}." if absorb else ""))
    rows = "".join(f"<li><b>{H.escape(f['title'])}</b>. {H.escape(f['recommended_action'] or '')}</li>"
                   for f in crit[:8]) or "<li>Nothing critical in this run. Read ACCOUNT-AUDIT.md for warnings.</li>"
    tile_html = "".join(f'<div class="tile">{H.escape(k)}<b>{H.escape(v)}</b></div>' for k, v in tiles)
    counts = "".join(f"<tr><td>{t.replace('-', ' ')}</td><td>{len(A[t])}</td></tr>" for t in TABS)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{H.escape(client_name)} Google Ads audit</title>
<style>{tokens}
body{{margin:0;padding:24px;max-width:860px;margin:auto;background:var(--color-bg,#f8f8f7);color:#111;
font-family:var(--font-body,system-ui,-apple-system,Segoe UI,Roboto,sans-serif);line-height:1.5}}
h1{{font-size:28px;margin:0 0 4px}} .eyebrow{{color:#666;font-size:13px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:20px 0}}
.tile{{background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:14px}}
.tile b{{display:block;font-size:24px;color:var(--color-primary,#1f2937)}}
.decision{{border-left:4px solid var(--color-primary,#1f2937);background:#fff;padding:14px 18px;border-radius:6px}}
table{{border-collapse:collapse}} td{{padding:4px 14px 4px 0;border-bottom:1px solid #eee}}
</style></head><body>
<div class="eyebrow">{H.escape(now_stamp())} &middot; run {H.escape(run_id[:8])} &middot; read-only API pull, nothing changed</div>
<h1>{H.escape(client_name)} Google Ads: what to change</h1>
<div class="tiles">{tile_html}</div>
<h2>The one decision</h2><div class="decision"><b>{H.escape(verdict)}</b><p>{H.escape(body)}</p></div>
<h2>Critical findings</h2><ul>{rows}</ul>
<h2>Actions in actions.xlsx</h2><table>{counts}</table>
<h2>Do not</h2><ul><li>Do not raise the budget on a campaign losing impressions to rank.</li>
<li>Do not add keywords for demand nobody has measured.</li>
<li>Do not tell anyone a competitor is or is not bidding off one SERP pull.</li>
<li>Do not quote a figure to a client that was not computed in this run.</li></ul>
</body></html>"""


# --------------------------------------------------------------------- Supabase
def supa_key():
    if os.environ.get("SUPABASE_SERVICE_KEY") and os.environ.get("SUPABASE_URL"):
        return os.environ["SUPABASE_SERVICE_KEY"]
    sys.exit("[out] --supabase needs SUPABASE_URL and SUPABASE_SERVICE_KEY in the environment")


def supa(table, rows, on_conflict):
    """PostgREST upsert. Every row is normalised to the UNION of keys first: PostgREST rejects a
    batch whose objects differ with PGRST102 'All object keys must match'."""
    if not rows:
        return 0
    keys = sorted({k for r in rows for k in r})
    rows = [{k: r.get(k) for k in keys} for r in rows]
    key = supa_key()
    sent = 0
    for i in range(0, len(rows), 400):
        body = json.dumps(rows[i:i + 400]).encode()
        url = f"{os.environ['SUPABASE_URL'].rstrip('/')}/rest/v1/{table}?on_conflict={urllib.parse.quote(on_conflict)}"
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal"})  # no browser UA: Supabase 401s on one
        try:
            urllib.request.urlopen(req, timeout=90, context=CTX).read()
            sent += len(rows[i:i + 400])
        except urllib.error.HTTPError as e:
            sys.exit(f"[out] Supabase {table} {e.code}: {e.read().decode()[:400]}")
    return sent


def persist(audit, run_id, client_hint):
    acc = audit["account"]
    # gads_daily and gads_audit_findings both FK to gads_accounts, so the account row goes first
    n_acc = supa("gads_accounts", [{
        "customer_id": str(audit["customer_id"]), "descriptive_name": acc.get("name"),
        "currency_code": acc.get("currency"), "time_zone": acc.get("time_zone"),
        "is_manager": False, "client_name_hint": client_hint, "active": True,
        "last_seen": "now()"}], "customer_id")
    daily = [{"customer_id": str(audit["customer_id"]), "campaign_id": d["campaign_id"],
              "campaign_name": d["campaign_name"], "campaign_status": d["campaign_status"],
              "date": d["date"], "impressions": d["impressions"], "clicks": d["clicks"],
              "cost_micros": d["cost_micros"], "conversions": d["conversions"],
              "conversions_value": d["conversions_value"], "avg_cpc_micros": d["avg_cpc_micros"],
              "search_impression_share": d["search_impression_share"],
              "search_lost_is_rank": d["search_lost_is_rank"],
              "search_lost_is_budget": d["search_lost_is_budget"],
              "currency_code": acc.get("currency")} for d in audit["daily"] if d.get("date")]
    n_daily = supa("gads_daily", daily, "customer_id,campaign_id,date")
    find = [{"run_id": run_id, "customer_id": str(audit["customer_id"]), "severity": f["severity"],
             "code": f["code"], "title": f["title"], "detail": f["detail"],
             "metric_value": f["metric_value"], "recommended_action": f["recommended_action"],
             "status": "open"} for f in audit["findings"]]
    n_find = supa("gads_audit_findings", find, "run_id,customer_id,code")
    return {"gads_accounts": n_acc, "gads_daily": n_daily, "gads_audit_findings": n_find}


def main():
    if any(a in sys.argv for a in ("-h", "--help")) or len(sys.argv) == 1:
        print(__doc__)
        return 0
    d = os.path.abspath(arg("--dir", "gads-audit-output"))
    if not os.path.isdir(d):
        print(__doc__)
        return 2
    slug = arg("--client") or os.path.basename(d)
    client_name = arg("--client-name") or slug.replace("-", " ").title()
    contractor = arg("--contractor") or os.environ.get("GADS_AUDIT_OWNER") or "there"
    sender = arg("--sender") or os.environ.get("GADS_AUDIT_SENDER") or ""
    run_id = arg("--run-id") or str(uuid.uuid4())
    audit = read_json(os.path.join(d, "account-audit.json"))
    kw = read_json(os.path.join(d, "keywords.json"))
    lp = read_json(os.path.join(d, "landing-page.json"))
    comp = [read_json(p) for p in sorted(glob.glob(os.path.join(d, "competitors-pass-*.json")))]
    if not audit:
        sys.exit(f"[out] no account-audit.json in {d}: run audit_account.py first")

    A = build_actions(audit, kw, lp, comp, contractor)
    write_json(os.path.join(d, "actions.json"),
               {"run_id": run_id, "client": slug, "customer_id": audit["customer_id"],
                "built_at": now_stamp(), "head": HEAD,
                "tabs": {t: [dict(zip(HEAD, r)) for r in A[t]] for t in TABS}})
    write_csvs(A, d)
    xlsx = write_xlsx(A, d)

    with open(os.path.join(d, "CONTRACTOR-EMAIL.md"), "w") as fh:
        fh.write(contractor_email(audit, kw, lp, A, client_name, contractor, run_id, sender))

    summary_path = os.path.join(d, "SUMMARY.html")
    with open(summary_path, "w") as fh:
        fh.write(summary_html(audit, kw, A, client_name, run_id))

    counts = {t: len(A[t]) for t in TABS}
    if flagged("--supabase"):
        n = persist(audit, run_id, slug)
        print(f"[out] Supabase: {n}", file=sys.stderr)

    print(json.dumps({"run_id": run_id, "dir": d, "action_counts": counts,
                      "summary": summary_path,
                      "files": sorted(os.path.basename(p) for p in
                                      glob.glob(os.path.join(d, "actions*")) +
                                      [os.path.join(d, "CONTRACTOR-EMAIL.md"),
                                       summary_path])}, indent=1))
    print(f"[out] {sum(counts.values())} actions across {len([t for t in TABS if A[t]])} tabs. "
          f"Nothing was sent or published.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
