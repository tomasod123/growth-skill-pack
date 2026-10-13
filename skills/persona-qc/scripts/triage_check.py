#!/usr/bin/env python3
"""Validate a TRIAGE.md: every table row carries one allowed verdict, every rejected row carries a reason, and print the counts.

  python3 triage_check.py qc/TRIAGE.md
  python3 triage_check.py qc/TRIAGE.md --rows team      # print the rows with that verdict (add --csv out.csv to export them for any task tool)

Allowed verdicts (bold, in the third column): implement, already fixed, team, client, owner decision, rejected.
  python3 triage_check.py qc/TRIAGE.md --rows team --csv qc/team-tasks.csv   # export team rows for ClickUp/Asana/Linear/Jira CSV import
Exit 1 on any bad row.
"""
import argparse
import re
import sys
from collections import Counter

VERDICTS = ["implement", "already fixed", "team", "client", "owner decision", "rejected"]


def rows(path):
    out = []
    for line in open(path, encoding="utf-8"):
        if not line.startswith("|") or re.match(r"^\|\s*#\s*\|", line) or re.match(r"^\|\s*-", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        out.append(cells)
    return out


def verdict_of(cell):
    c = cell.lower().replace("*", "").strip()
    for v in VERDICTS:
        if c.startswith(v):
            return v
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--rows", help="print rows with this verdict")
    ap.add_argument("--csv", help="with --rows: also write those rows to this CSV (id,item,verdict,where_why) for any task tool import")
    a = ap.parse_args()
    R = rows(a.path)
    bad, counts = [], Counter()
    for cells in R:
        v = verdict_of(cells[2])
        if not v:
            bad.append(("no allowed verdict", cells[0], cells[2][:40])); continue
        counts[v] += 1
        if v == "rejected" and len(cells[3]) < 12:
            bad.append(("rejected without a reason", cells[0], cells[3]))
        if v == "team" and not re.search(r"[A-Z][a-z]+", cells[3]):
            bad.append(("team row names nobody", cells[0], cells[3][:40]))
    if a.rows:
        sel = [cells for cells in R if verdict_of(cells[2]) == a.rows]
        for cells in sel:
            print(" | ".join(cells))
        if a.csv:
            import csv
            with open(a.csv, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["id", "item", "verdict", "where_why"])
                for cells in sel:
                    w.writerow([cells[0], cells[1], cells[2].replace("*", ""), " | ".join(cells[3:])])
            print(f"  wrote {len(sel)} rows to {a.csv}")
        return
    print("  rows:", len(R), "·", " · ".join(f"{k} {v}" for k, v in counts.items()))
    for b in bad:
        print("  !!", *b)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
