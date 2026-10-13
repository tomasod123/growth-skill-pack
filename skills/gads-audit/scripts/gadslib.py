#!/usr/bin/env python3
"""Shared helpers for the gads-audit skill. Stdlib only (plus certifi via the layers it loads).

Everything Google Ads goes through ../gads-common/scripts/gads.py (READ-ONLY: search /
listAccessibleCustomers only). Everything DataForSEO goes through dfs_client.py in this folder.
This module never writes to any ad platform.

Exports
  gads_search(customer, gaql)      paginated GAQL read, list of row dicts
  g(row, "a.b.c")                  safe nested get (the REST API omits false/0/default fields,
                                   so a missing key means false/zero, never "unknown")
  money(micros), pct(x)
  Finding / finding()              one audit finding, severity in critical|warning|info
  SEVERITY_ORDER                   sort key
  md_table(head, rows)             markdown table
  dfs_api(method, path, data)      DataForSEO call through dfs_client.py (prints cost)
  dfs_run_cost()                   this run's cumulative DataForSEO spend, USD
  write_json(path, obj), read_json(path)
  now_stamp()                      ISO local timestamp, never hand-written
"""
import datetime as dt
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# gads-common sits beside this skill: ~/.claude/skills/gads-common/scripts/gads.py
GADS_PY = os.environ.get("GADS_COMMON_PY") or os.path.normpath(
    os.path.join(HERE, "..", "..", "gads-common", "scripts", "gads.py"))
DFS_PY = os.path.join(HERE, "dfs_client.py")
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _load(path, name):
    if not os.path.exists(path):
        sys.exit(f"[gads-audit] missing dependency: {path} "
                 "(install the gads-common skill beside this one, or set GADS_COMMON_PY)")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_gads = None


def gads():
    """The gads-common reader module (lazy: so DataForSEO-only scripts need no Google sign-in)."""
    global _gads
    if _gads is None:
        _gads = _load(GADS_PY, "gads_reader")
    return _gads


def gads_search(customer, gaql):
    return gads().search(customer, gaql)


def g(row, path, default=None):
    cur = row
    for key in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return default if cur is None else cur


def money(micros, nd=2):
    return round(int(micros or 0) / 1e6, nd)


def pct(x, nd=2):
    """Google returns impression share as a 0-1 fraction. None stays None (no data != 0%)."""
    return None if x is None else round(float(x) * 100, nd)


_dfs = None


def dfs():
    global _dfs
    if _dfs is None:
        _dfs = _load(DFS_PY, "dfs_helper")
    return _dfs


def dfs_api(method, path, data=None):
    return dfs().api_request(method, path, data)


def dfs_items(resp, task=0):
    return dfs().result_items(resp, task)


def dfs_run_cost():
    return dfs().run_cost()


class Finding(dict):
    """code / severity / title / detail / metric_value / recommended_action / owner."""


def finding(code, severity, title, detail="", metric_value=None, action="", owner=None):
    if severity not in SEVERITY_ORDER:
        raise ValueError(f"severity must be critical|warning|info, got {severity!r}")
    owner = owner or os.environ.get("GADS_AUDIT_OWNER") or "PPC manager"
    return Finding(code=code, severity=severity, title=title, detail=detail,
                   metric_value=None if metric_value is None else float(metric_value),
                   recommended_action=action, owner=owner)


def sort_findings(findings):
    return sorted(findings, key=lambda f: (SEVERITY_ORDER[f["severity"]], f["code"]))


def md_table(head, rows):
    out = ["| " + " | ".join(str(h) for h in head) + " |",
           "|" + "|".join("---" for _ in head) + "|"]
    for r in rows:
        cells = ["" if c is None else str(c).replace("|", "\\|") for c in r]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=1, default=str)
    return path


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path) as fh:
        return json.load(fh)


def now_stamp():
    return dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")


def today():
    return dt.date.today()


LOCATION_CODES = {"AU": 2036, "UK": 2826, "GB": 2826, "CA": 2124, "US": 2840, "IE": 2372, "NZ": 2554}


def location_code(name_or_code):
    s = str(name_or_code).strip().upper()
    if s.isdigit():
        return int(s)
    if s in LOCATION_CODES:
        return LOCATION_CODES[s]
    sys.exit(f"[gads-audit] unknown location {name_or_code!r}; use a code or one of {sorted(LOCATION_CODES)}")
