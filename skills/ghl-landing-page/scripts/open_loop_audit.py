#!/usr/bin/env python3
"""Open-loop and copy audit for a landing page paste block (GHL Custom HTML or any HTML).

    python3 open_loop_audit.py ghl-paste.html [--ban banned.txt] [--allow-host example.com] [--json]

Checks (FAIL = fix before shipping, WARN = look at it):
  1. Outbound links that exit the funnel (anything but #anchors, tel:, mailto:, and
     hosts passed with --allow-host). Embed/iframe/script src are not links.
  2. Call / plan durations named on the page ("45-minute call", "12-week plan").
  3. Banned phrases: a small default list plus your house-style file (--ban, one
     phrase per line, optional "phrase<TAB>reason", # comments).
  4. Em-dashes and double dashes in visible copy.
  5. Money thresholds: lists every "$X / £X per month" style figure so fit and
     disqualifier lists can be compared by eye.
  6. "choose a time" / "pick a time" copy on a page with no calendar embed.
  7. Two consent mechanisms (a checkbox AND a "by submitting" line).

Exit 1 if any FAIL.
"""
import json
import re
import sys

DEFAULT_BANS = [
    ("no pitch", "defensive framing: there is a pitch, say less"),
    ("no pressure", "defensive framing"),
    ("not a pitch", "defensive framing"),
    ("genuinely", "filler word that reads as AI-written"),
    ("here's the best part", "filler phrase"),
    ("built with claude", "no AI-authorship credit on client pages"),
]

DURATION = re.compile(
    r"\b\d{1,3}\s*[- ]?\s*(min|mins|minute|minutes|hour|hours|day|days|week|weeks|month|months)\b"
    r"[\s-]*(call|plan|game plan|sprint|program|programme|session|consult|consultation|roadmap)\b",
    re.I)
MONEY = re.compile(r"[$£€]\s?\d[\d,.]*\s?[kKmM]?\b(\s?(/|a|per)\s?(month|mo|year|yr))?")


def strip_tags(html):
    html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", html)


def load_bans(path):
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line.strip() or line.startswith("#"):
            continue
        phrase, _, why = line.partition("\t")
        out.append((phrase.lower(), why or "house-style ban"))
    return out


def audit(path, bans, allow_hosts):
    s = open(path, encoding="utf-8").read()
    text = strip_tags(s)
    low = text.lower()
    fails, warns, info = [], [], []

    # 1. exit links
    for m in re.finditer(r"<a\b[^>]*\bhref\s*=\s*['\"]([^'\"]*)['\"]", s, re.I):
        href = m.group(1).strip()
        if not href or href.startswith(("#", "tel:", "mailto:", "sms:")):
            continue
        host = re.sub(r"^https?://", "", href).split("/")[0].lower()
        if any(host == h or host.endswith("." + h) for h in allow_hosts):
            continue
        fails.append(f"exit link: {href[:90]} (every extra click is a conversion leak)")

    # 2. durations
    for m in DURATION.finditer(text):
        fails.append(f"duration named on the page: '{m.group(0).strip()}' (say 'call' / 'plan' only)")

    # 3. banned phrases
    for phrase, why in bans:
        if phrase in low:
            fails.append(f"banned phrase '{phrase}': {why}")

    # 4. dashes
    n_em = text.count("—")
    n_dd = len(re.findall(r"(?<!-)--(?!-)", text))
    if n_em:
        fails.append(f"{n_em} em-dash(es) in visible copy: use colons, commas or a new sentence")
    if n_dd:
        warns.append(f"{n_dd} double dash(es) in visible copy")

    # 5. money thresholds
    figs = sorted({m.group(0).strip() for m in MONEY.finditer(text)})
    if figs:
        info.append("money figures (check fit list vs disqualifier match): " + ", ".join(figs[:12]))

    # 6. booking promise without a calendar
    if re.search(r"\b(choose|pick|select) (a|your) time\b", low) and not re.search(
            r"booking|calendar|/widget/", s, re.I):
        fails.append("copy says 'choose a time' but no calendar embed found: match the copy to what the form does")

    # 7. double consent
    has_box = re.search(r"type\s*=\s*['\"]checkbox['\"]", s, re.I)
    has_line = re.search(r"by (submitting|clicking|continuing)", low)
    if has_box and has_line:
        warns.append("checkbox AND a 'by submitting' line: keep one consent mechanism")

    info.append(f"{len(s):,} bytes")
    return fails, warns, info


def main():
    argv = sys.argv[1:]
    bans = list(DEFAULT_BANS)
    allow = []
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    while "--ban" in argv:
        i = argv.index("--ban")
        bans += load_bans(argv[i + 1])
        del argv[i:i + 2]
    while "--allow-host" in argv:
        i = argv.index("--allow-host")
        allow.append(argv[i + 1].lower())
        del argv[i:i + 2]
    if not argv or argv[0] in ("-h", "--help"):
        sys.exit(__doc__)
    out, bad = {}, False
    for p in argv:
        f, w, i = audit(p, bans, allow)
        out[p] = {"fail": f, "warn": w, "info": i}
        bad = bad or bool(f)
        if not as_json:
            print(f"\n{p}")
            for x in f:
                print(f"   FAIL  {x}")
            for x in w:
                print(f"   warn  {x}")
            for x in i:
                print(f"   info  {x}")
            if not f and not w:
                print("   clean")
    if as_json:
        print(json.dumps(out, indent=1))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
