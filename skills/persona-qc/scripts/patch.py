#!/usr/bin/env python3
"""Apply a list of exact string replacements to files, reporting the count of every one. The one tool the apply agent edits with.

  python3 patch.py work/apply_r1.json [--round r1] [--dry-run]

apply_r1.json: [{"file": "/abs/or/relative/path.html", "old": "exact current text", "new": "replacement", "want": 1}, ...]
- Keeps <file>.bak-<round> before the first write to that file.
- Never asserts after a write (an assert chain once aborted mid-patch and left half the files changed).
- Idempotent: a row whose `old` is absent and `new` is present reports "done already"; a row whose `old` count differs from `want` is flagged `!!` and SKIPPED (fix the row, re-run).
- Prints the file size delta per file so a runaway replacement is visible.
Exit 1 if any row was flagged.
"""
import argparse
import io
import json
import os
import shutil
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("patchlist")
    ap.add_argument("--round", default="r1")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    rows = json.load(open(a.patchlist, encoding="utf-8"))
    base = os.path.dirname(os.path.abspath(a.patchlist))
    texts, sizes, flagged = {}, {}, 0
    for i, r in enumerate(rows, 1):
        f = r["file"] if os.path.isabs(r["file"]) else os.path.join(base, r["file"])
        if f not in texts:
            if not os.path.exists(f):
                print(f"  [{i}] !! missing file {f}"); flagged += 1; continue
            texts[f] = io.open(f, encoding="utf-8").read(); sizes[f] = len(texts[f])
        t = texts[f]; want = int(r.get("want", 1)); n = t.count(r["old"])
        if n == 0 and r["new"] and r["new"] in t:
            print(f"  [{i}] done already  {os.path.basename(f)}: {r['old'][:60]!r}"); continue
        if n != want:
            print(f"  [{i}] !! {n}/{want}   {os.path.basename(f)}: {r['old'][:60]!r}  (SKIPPED)"); flagged += 1; continue
        texts[f] = t.replace(r["old"], r["new"]); print(f"  [{i}] {n}/{want}  {os.path.basename(f)}: {r['old'][:50]!r} -> {r['new'][:50]!r}")
    for f, t in texts.items():
        d = len(t) - sizes[f]
        if a.dry_run:
            print(f"  [dry-run] {f}: {d:+d} bytes"); continue
        bak = f + f".bak-{a.round}"
        if not os.path.exists(bak):
            shutil.copy(f, bak)
        io.open(f, "w", encoding="utf-8").write(t); print(f"  wrote {f} ({d:+d} bytes; backup {os.path.basename(bak)})")
    print(f"  rows {len(rows)} · flagged {flagged}")
    sys.exit(1 if flagged else 0)


if __name__ == "__main__":
    main()
