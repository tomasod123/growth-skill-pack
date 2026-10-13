#!/usr/bin/env python3
"""Step 4: the pattern table. One row per shortlisted ad:
hook type | offer | on-screen text | length | CTA | format | run days

Hook types:
  CALLOUT     names the city / the person / the role ("Women of Nashville", "Practice managers...")
  PROBLEM     names the concern, body part or business pain in the opening line
  NUMBER      drops a figure ("20,000 contractions", "$49", "3 hours a day")
  INVITATION  "I'm X from Y and I want to invite you..."
  BLAME-OFF   "it's not your fault / it isn't the cream you picked"
  SHOW        shows them something they cannot see (the scan on screen, the product on screen)
  QUESTION    opens on a question
  TEXT-ONLY   no voice in the first 8 s; hook is written on screen (needs a human to read the frame)

Writes patterns.json + patterns.md (paste-ready table) + a counts block for the page's "key things" panel.
On-screen text is OCR'd from the 0.5 s frame when tesseract is installed; otherwise "[read frame]".

  python3 04_patterns.py --client clinic-a
  python3 04_patterns.py --shortlist shortlist.json --meta media_meta.json --frames frames --out patterns
"""
import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

RX = {
    "CALLOUT": r"^(hey|hi|hello)?[ ,]*(women|men|mums|moms|ladies|guys|doctors|clinicians|nurses|practice managers|clinic owners|founders|melbourne|sydney|brisbane|perth|adelaide|london|manchester|"
               r"bristol|birmingham|glasgow|dublin|new jersey|nashville|[a-z]+ (women|men|mums|moms))\b|\b(of|in) [A-Z][a-z]+[,!?]",
    "INVITATION": r"\b(i'?m|this is|my name is) [a-z]+.{0,40}\b(invite|inviting|want to)\b",
    "BLAME-OFF": r"not your fault|isn'?t (that|because) you|nothing wrong with you|you'?ve tried everything|tried every",
    "NUMBER": r"\b\d[\d,\.]*\s*(%|contractions|crunches|squats|minutes?|mins?|hours?|days?|weeks?|sessions?|patients|clinics|\$|£|dollars)|[$£]\s?\d",
    "SHOW": r"(what|how) your skin (actually|really) looks|underneath|under the surface|on (the|this) screen|let me show you|"
            r"here'?s what .* looks like|watch (this|how)|in (this|the) (demo|video)",
    "QUESTION": r"\?",
    "PROBLEM": r"acne|scar|pigment|melasma|rosacea|pores?|texture|fine lines|wrinkl|sun damage|under.?eye|dark circle|redness|"
               r"uneven|stubborn|belly|love handles|muffin|sagg|loose skin|hair loss|thinning|breakout|"
               r"no.shows?|paperwork|documentation|charting|burnout|missed calls|admin|billing|denials?|churn|spreadsheets?",
}
OFFER_RX = [
    ("free/complimentary consultation", r"(free|complimentary|no.obligation) (skin )?(consult|assessment|analysis|scan)"),
    ("priced trial session", r"[$£]\s?\d+[^.]{0,40}(session|trial|first|intro)|(session|trial|first|intro)[^.]{0,40}[$£]\s?\d+"),
    ("demo / call", r"book a (demo|call|meeting)|free demo|see (it|a demo)|get a demo"),
    ("free trial", r"free trial|start (for )?free|try (it )?free|\d+.day trial"),
    ("content offer", r"(free|download|get) (the |our )?(guide|ebook|e-book|report|checklist|template|playbook|webinar|calculator)"),
    ("discount / saving", r"\d+% off|save \d|half price|\bfree\b"),
    ("consultation", r"consult|assessment|analysis|scan|appointment"),
    ("limited spots", r"(next|only|first) \d+ (women|men|people|spots|clients)|limited|spots? left"),
]


def classify_hook(hook, body):
    text = (hook or "").strip()
    if len(text.split()) < 3:
        return "TEXT-ONLY", text
    t = text.lower()
    for k in ("INVITATION", "BLAME-OFF", "SHOW", "CALLOUT", "PROBLEM", "NUMBER", "QUESTION"):
        if re.search(RX[k], t if k != "CALLOUT" else text, re.I):
            return k, text
    return "OTHER", text


def offer_of(body):
    b = (body or "").lower()
    hits = [name for name, rx in OFFER_RX if re.search(rx, b)]
    return " + ".join(hits[:2]) if hits else "none stated"


def ocr(frame):
    if not C.which("tesseract") or not os.path.exists(frame):
        return None
    try:
        r = subprocess.run(["tesseract", frame, "-", "--psm", "6"], capture_output=True, text=True, timeout=60)
        words, prev = [], None
        for w in r.stdout.split():
            if re.fullmatch(r"[A-Za-z][A-Za-z'&.,!?-]{2,}", w) and w.lower() != prev:
                words.append(w)
                prev = w.lower()
        return " ".join(words)[:120] if len(words) >= 2 else ""
    except Exception:  # noqa: BLE001
        return None


def length_bucket(s):
    if s is None:
        return "?"
    if s <= 15:
        return "under 15 s"
    if s <= 45:
        return "20 to 45 s"
    if s <= 75:
        return "45 to 75 s"
    return "over 75 s"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client")
    ap.add_argument("--workdir")
    ap.add_argument("--shortlist")
    ap.add_argument("--meta", help="media_meta.json from 03_media.py")
    ap.add_argument("--frames", help="frames dir for OCR")
    ap.add_argument("--out", help="output basename (default <workdir>/patterns)")
    ap.add_argument("--top", type=int, default=12, help="how many rows make the page table (8 to 12 is typical)")
    ap.add_argument("--dry-run", action="store_true", help="print the table, write nothing")
    args = ap.parse_args()

    wd = args.workdir or (C.workdir(args.client) if args.client else None)
    sl = args.shortlist or os.path.join(wd, "shortlist.json")
    meta = C.load_json(args.meta or os.path.join(wd or os.path.dirname(sl), "media_meta.json"), {}) or {}
    frames = args.frames or os.path.join(wd or os.path.dirname(sl), "frames")
    rows = C.load_json(sl)
    if not rows:
        sys.exit("shortlist.json missing/empty")

    out_rows = []
    for r in rows[:args.top]:
        m = meta.get(r["id"], {})
        hook_type, hook = classify_hook(m.get("hook"), r.get("body"))
        onscreen = ocr(os.path.join(frames, f"{r['id']}.jpg"))
        fmt = ("text on screen, no voice" if hook_type == "TEXT-ONLY"
               else "person to camera" if re.search(r"\b(i'?m|this is|my name is) [a-z]+\b.{0,30}\b(from|at|here)\b", (hook or "").lower())
               else "voiceover / spoken")
        out_rows.append({
            "id": r["id"], "page": r["page"], "country": r.get("country"), "days": r["days"],
            "hook_type": hook_type, "hook": hook or "", "offer": offer_of(r.get("body")),
            "on_screen_text": onscreen if onscreen is not None else "[read frame]",
            "length_s": m.get("duration_s"), "length": length_bucket(m.get("duration_s")),
            "cta": r.get("cta") or "", "format": fmt, "lib_url": r.get("lib_url"),
            "body_first_line": re.sub(r"\s+", " ", (r.get("body") or ""))[:110],
        })

    n = len(out_rows)
    counts = {
        "speaks or hook on screen in first second": sum(1 for x in out_rows if x["hook"] or x["on_screen_text"] not in ("", "[read frame]")),
        "sells a consultation, demo or call, not the product itself": sum(1 for x in out_rows if re.search(r"consult|demo", x["offer"])),
        "names a concern in the first 3 s": sum(1 for x in out_rows if x["hook_type"] == "PROBLEM" or re.search(RX["PROBLEM"], x["hook"], re.I)),
        "runs 20 to 45 s": sum(1 for x in out_rows if x["length"] == "20 to 45 s"),
        "carries a price or offer": sum(1 for x in out_rows if x["offer"] != "none stated"),
        "no voice, text only": sum(1 for x in out_rows if x["hook_type"] == "TEXT-ONLY"),
    }
    hook_mix = Counter(x["hook_type"] for x in out_rows)

    md = ["| # | Days | Mkt | Page | Hook type | Hook (first 8 s) | Offer | On-screen text | Length | CTA | Format |",
          "|--:|----:|:---|:-----|:----------|:-----------------|:------|:---------------|:-------|:----|:-------|"]
    for i, x in enumerate(out_rows, 1):
        md.append(f"| {i} | {x['days']} | {x['country']} | {x['page'][:28]} | {x['hook_type']} | {x['hook'][:80]} | {x['offer']} | "
                  f"{x['on_screen_text'][:50]} | {x['length_s'] or '?'} s | {x['cta']} | {x['format']} |")
    md.append("")
    md.append(f"**Counts of {n}:** " + " · ".join(f"{v} of {n} {k}" for k, v in counts.items()))
    md.append(f"**Hook mix:** {dict(hook_mix)}")
    md.append("")
    md.append("Rows marked [read frame] need a human to watch the first second and type the on-screen text. "
              "Always eyeball hook_type: the regex is a first pass, not a verdict.")
    text = "\n".join(md)
    print(text)
    if args.dry_run:
        print("DRY RUN: nothing written")
        return
    base = args.out or os.path.join(wd or os.path.dirname(sl), "patterns")
    C.save_json(base + ".json", {"n": n, "counts": counts, "hook_mix": dict(hook_mix), "rows": out_rows})
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print("->", base + ".json", base + ".md")


if __name__ == "__main__":
    main()
