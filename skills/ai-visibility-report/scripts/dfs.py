#!/usr/bin/env python3
"""
dfs.py  -  DataForSEO REST helper for the ai-visibility-report skill.

Why it exists: the DataForSEO MCP server is often not connected, so the skill must be
able to hit the REST API directly. This helper mirrors the MCP V3 tool
`api_request(method, path, data)` one to one, so a SKILL.md step written for the MCP
can be run unchanged through this file.

Credentials: read from the environment only (DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD).
Load them first with:  set -a; source ~/.claude/skills/.env; set +a
Never hardcode them, never print them.

TLS: some Python installs (notably python.org builds on macOS) fail TLS with urllib
unless certifi is used. The helper exports SSL_CERT_FILE from certifi itself when
certifi is installed (pip install certifi).

Cost discipline: every response carries a `cost` field (USD). The helper prints
`[dfs] <path> cost=$x cumulative=$y` to stderr on every call and appends one line
per call to a local ledger (default ./ai-visibility-report-output/dfs-cost-ledger.jsonl,
override with DFS_LEDGER=/path/file.jsonl) so the cumulative figure survives across
separate CLI invocations in one run (group them with DFS_RUN_ID=<anything>).

CLI
  python3 dfs.py GET  /v3/appendix/user_data
  python3 dfs.py POST /v3/serp/google/organic/live/advanced \
      '[{"keyword":"hair transplant cost","location_code":2840,"language_code":"en","depth":100}]'
  python3 dfs.py POST /v3/backlinks/summary/live --file body.json
  python3 dfs.py POST /v3/... '[...]' --out result.json   (writes JSON to file, prints only cost)
  python3 dfs.py --balance                                 (free: prints balance only)
  python3 dfs.py --ledger                                  (sum of this run's costs)

Python
  import sys, os; sys.path.insert(0, os.path.expanduser("~/.claude/skills/ai-visibility-report/scripts"))
  from dfs import api_request, call, result_items, run_cost
  r = api_request("POST", "/v3/backlinks/summary/live", [{"target": "example.com"}])
  items = result_items(r)          # tasks[0].result[0].items or tasks[0].result
  print(r["cost"], run_cost())

A single POST body may be a list of task dicts (DataForSEO convention) or one
dict, which is wrapped into a list. Location codes: UK 2826, Canada 2124,
US 2840, Australia 2036. Google Ads CPC values are USD regardless of location_code.
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
LEDGER = os.environ.get("DFS_LEDGER") or os.path.join(
    "ai-visibility-report-output", "dfs-cost-ledger.jsonl")
RUN_ID = os.environ.get("DFS_RUN_ID") or time.strftime("%Y%m%d")
_cumulative = 0.0


def _ssl_context():
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def load_env():
    """Read DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD from the environment."""
    login = os.environ.get("DATAFORSEO_LOGIN")
    password = os.environ.get("DATAFORSEO_PASSWORD")
    if not login or not password:
        sys.exit("[dfs] missing DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD. Run: "
                 "set -a; source ~/.claude/skills/.env; set +a")
    return login, password


def _auth_header():
    login, password = load_env()
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    return "Basic " + token


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
        d = os.path.dirname(LEDGER)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(LEDGER, "a") as fh:
            fh.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "run_id": RUN_ID,
                                 "path": path, "cost": cost, "status": status}) + "\n")
    except OSError:
        pass


def call(path, data=None, method=None, timeout=180, quiet=False):
    """Low-level call. Returns the parsed response dict plus `elapsed` and `cumulative`."""
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
    req.add_header("User-Agent", "curl/8.4.0")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        if e.code == 401:
            sys.exit("[dfs] 401 from DataForSEO: check DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD in ~/.claude/skills/.env (API password, not your account password; never paste it anywhere)")
    try:
        out = json.loads(raw)
    except ValueError:
        out = {"status_code": -1, "status_message": raw[:500], "tasks": []}
    out["elapsed"] = round(time.time() - t0, 2)
    cost = float(out.get("cost") or 0)
    _cumulative += cost
    out["cumulative"] = round(_cumulative, 6)
    _ledger_append(path, cost, out.get("status_code"))
    out["run_cumulative"] = run_cost()
    if not quiet:
        print(f"[dfs] {method.upper()} {path} status={out.get('status_code')} "
              f"cost=${cost:.4f} cumulative=${out['run_cumulative']:.4f} ({out['elapsed']}s)",
              file=sys.stderr)
    # surface task-level errors (40xxx) without hiding the payload
    for t in out.get("tasks") or []:
        if t.get("status_code") not in (None, 20000):
            print(f"[dfs]   task {t.get('id')} status={t.get('status_code')} {t.get('status_message')}",
                  file=sys.stderr)
    return out


def api_request(method, path, data=None, **kw):
    """Same signature as the DataForSEO MCP V3 tool `api_request`."""
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


def _main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--balance":
        print(json.dumps({"balance_usd": balance()}))
        return 0
    if argv[0] == "--ledger":
        print(json.dumps({"run_id": RUN_ID, "run_cost_usd": run_cost()}))
        return 0
    method, path = argv[0].upper(), argv[1]
    data, out_file = None, None
    rest = argv[2:]
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--file":
            with open(rest[i + 1]) as fh:
                data = json.load(fh)
            i += 2
        elif a == "--out":
            out_file = rest[i + 1]
            i += 2
        else:
            data = json.loads(a)
            i += 1
    r = call(path, data=data, method=method)
    if out_file:
        with open(out_file, "w") as fh:
            json.dump(r, fh, indent=1)
        print(json.dumps({"status_code": r.get("status_code"), "cost": r.get("cost"),
                          "run_cumulative": r.get("run_cumulative"), "out": out_file}))
    else:
        print(json.dumps(r, indent=1))
    return 0 if r.get("status_code") == 20000 else 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
