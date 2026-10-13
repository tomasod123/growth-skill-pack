#!/usr/bin/env python3
"""Minimal DataForSEO REST client for gads-audit (stdlib; certifi used if installed).

Credentials: DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD from the environment
(set -a; source ~/.claude/skills/.env; set +a). Get them at https://app.dataforseo.com/api-access
(the API password is NOT your dashboard password).

Every call prints its cost and appends a row to a cost ledger so separate CLI calls in one audit can
be totalled: ledger path = $DFS_LEDGER, default ./gads-audit-output/dfs-cost-ledger.jsonl.
Group calls with DFS_RUN_ID=<anything> (default: today's date).

  python3 dfs_client.py --balance       account balance (free call)
  python3 dfs_client.py --ledger        total cost of this DFS_RUN_ID
"""
import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.dataforseo.com"
LEDGER = os.environ.get("DFS_LEDGER") or os.path.join("gads-audit-output", "dfs-cost-ledger.jsonl")
RUN_ID = os.environ.get("DFS_RUN_ID") or time.strftime("%Y%m%d")
_cumulative = 0.0


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _auth_header():
    login = os.environ.get("DATAFORSEO_LOGIN")
    password = os.environ.get("DATAFORSEO_PASSWORD")
    if not login or not password:
        sys.exit("[dfs] missing DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD. Load ~/.claude/skills/.env "
                 "(set -a; source ~/.claude/skills/.env; set +a)")
    return "Basic " + base64.b64encode(f"{login}:{password}".encode()).decode()


def run_cost(run_id=RUN_ID):
    """Sum of `cost` for this run id from the ledger (covers separate CLI calls)."""
    total = 0.0
    if os.path.exists(LEDGER):
        with open(LEDGER) as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("run_id") == run_id:
                    total += float(row.get("cost") or 0)
    return round(total, 6)


def _ledger_append(path, cost, status):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(LEDGER)), exist_ok=True)
        with open(LEDGER, "a") as fh:
            fh.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "run_id": RUN_ID,
                                 "path": path, "cost": cost, "status": status}) + "\n")
    except OSError:
        pass


def call(path, data=None, method=None, timeout=180, quiet=False):
    global _cumulative
    if not path.startswith("/"):
        path = "/" + path
    if not path.startswith("/v3/"):
        path = "/v3" + path
    if method is None:
        method = "POST" if data is not None else "GET"
    body = None
    if data is not None:
        if isinstance(data, dict):
            data = [data]
        body = json.dumps(data).encode()
    req = urllib.request.Request(BASE + path, data=body, method=method.upper())
    req.add_header("Authorization", _auth_header())
    req.add_header("Content-Type", "application/json")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        if e.code == 401:
            sys.exit("[dfs] 401 from DataForSEO: check DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD "
                     "(the API password from app.dataforseo.com/api-access)")
    try:
        out = json.loads(raw)
    except ValueError:
        out = {"status_code": -1, "status_message": raw[:500], "tasks": []}
    out["elapsed"] = round(time.time() - t0, 2)
    cost = float(out.get("cost") or 0)
    _cumulative += cost
    _ledger_append(path, cost, out.get("status_code"))
    out["run_cumulative"] = run_cost()
    if not quiet:
        print(f"[dfs] {method.upper()} {path} status={out.get('status_code')} "
              f"cost=${cost:.4f} run total=${out['run_cumulative']:.4f} ({out['elapsed']}s)", file=sys.stderr)
    for t in out.get("tasks") or []:
        if t.get("status_code") not in (None, 20000):
            print(f"[dfs]   task status={t.get('status_code')} {t.get('status_message')}", file=sys.stderr)
    return out


def api_request(method, path, data=None, **kw):
    return call(path, data=data, method=method, **kw)


def result_items(resp, task=0):
    """tasks[task].result[0].items if present, else tasks[task].result, else []."""
    try:
        res = resp["tasks"][task]["result"]
    except (KeyError, IndexError, TypeError):
        return []
    if not res:
        return []
    first = res[0]
    if isinstance(first, dict) and "items" in first:
        return first.get("items") or []
    return res


def balance():
    r = call("/v3/appendix/user_data", quiet=True)
    try:
        return r["tasks"][0]["result"][0]["money"]["balance"]
    except (KeyError, IndexError, TypeError):
        return None


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--balance":
        print(balance())
    elif a and a[0] == "--ledger":
        print(f"run {RUN_ID}: US${run_cost():.4f} (ledger {LEDGER})")
    else:
        print(__doc__)
