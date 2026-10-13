#!/usr/bin/env python3
"""Fold the creative-attribute sidecar into the index.

  python3 merge_tags.py --dry-run
  python3 merge_tags.py

The sidecar (`<library>/creative_tags.jsonl`) is written by a separate pass and is
keyed on the index row `id` (`row_key` and `ad_id` are accepted as fallbacks). One JSON object per
line: the key, plus whatever creative attributes that pass produced.

Rules
  * identity and provenance fields are NEVER overwritten from the sidecar
    (id, row_key, ad_id, client, client_or_competitor, source_scrape, date, ingested_at)
  * fields DERIVED from the raw scrapes are never overwritten either — the sidecar describes the
    creative, the scrape describes the delivery. Pass --allow-derived to override that.
  * format_class must be in the controlled vocabulary or the merge is refused
  * everything else is merged in, and the run prints exactly which fields landed
Idempotent: merging the same sidecar twice produces the same index.
"""
import argparse
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adlib_common import LIB_DEFAULT, V2_FIELDS, ensure_library, index_lock, write_index  # noqa: E402
from ingest import FORMAT_CLASSES, PVS  # noqa: E402

IDENTITY = {"id", "row_key", "ad_id", "client", "client_or_competitor", "source_scrape",
            "date", "ingested_at"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", default=LIB_DEFAULT)
    ap.add_argument("--sidecar")
    ap.add_argument("--allow-derived", action="store_true",
                    help="let the sidecar overwrite fields derived from the raw scrapes")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    side = a.sidecar or os.path.join(a.library, "creative_tags.jsonl")
    if not os.path.exists(side):
        print(f"  no sidecar at {side} — nothing to merge")
        return 0
    print(f"  merging {side}")
    ensure_library(a.library)
    idx_path = os.path.join(a.library, "index.jsonl")
    lock = index_lock(a.library)          # the weekly refresh rewrites the same file
    lock.__enter__()
    rows = [json.loads(l) for l in io.open(idx_path, encoding="utf-8") if l.strip()]
    by = {}
    for r in rows:
        for k in (r.get("id"), r.get("row_key"), r.get("ad_id")):
            if k not in (None, ""):       # str(None) is truthy; never index a row under "None"
                by.setdefault(str(k), r)

    protected = IDENTITY | (set() if a.allow_derived else set(V2_FIELDS))
    tags = [json.loads(l) for l in io.open(side, encoding="utf-8") if l.strip()]
    matched, missed, fields, blocked = 0, [], Counter(), Counter()
    for t in tags:
        key = str(t.get("id") or t.get("row_key") or t.get("ad_id") or "")
        row = by.get(key)
        if not row:
            missed.append(key)
            continue
        matched += 1
        for k, v in t.items():
            if k in ("id", "row_key", "ad_id"):
                continue
            if k in protected:
                blocked[k] += 1
                continue
            if v is None:
                continue
            if k == "format_class" and v not in FORMAT_CLASSES:
                raise SystemExit(f"sidecar row {key}: format_class {v!r} is not in {FORMAT_CLASSES}")
            row[k] = v
            fields[k] += 1
        if t.get("format_class") in FORMAT_CLASSES:
            row["format"] = t["format_class"]
            row["personal_vs_slides"] = PVS[t["format_class"]]

    print(f"  sidecar {side}: {len(tags)} tag rows · matched {matched} · unmatched {len(missed)}")
    if missed:
        print("    unmatched keys: " + ", ".join(missed[:10]) + (" ..." if len(missed) > 10 else ""))
    print("  fields merged: " + (", ".join(f"{k} {n}" for k, n in fields.most_common()) or "none"))
    if blocked:
        print("  fields BLOCKED (identity or scrape-derived): " +
              ", ".join(f"{k} {n}" for k, n in blocked.most_common()))
    if a.dry_run:
        lock.__exit__(None, None, None)
        print("  [dry-run] nothing written")
        return 0
    write_index(rows, a.library)          # temp file + os.replace + one .bak
    lock.__exit__(None, None, None)
    print(f"  -> {idx_path}: {len(rows)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
