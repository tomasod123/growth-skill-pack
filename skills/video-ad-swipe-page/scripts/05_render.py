#!/usr/bin/env python3
"""Step 6 helper: fill templates/page.html from a page.json spec and copy the media in.

The template has {{TOKENS}} and repeat blocks:
  <!-- BEGIN WINNER --> ... <!-- END WINNER -->        one per top ad (02 · Watch the winners)
  <!-- BEGIN PATTERN --> ... <!-- END PATTERN -->      one per pattern-table row (03)
  <!-- BEGIN GROUP --> ... <!-- END GROUP -->          one per group (A/B/C...) each holding SCRIPT blocks
  <!-- BEGIN SCRIPT --> ... <!-- END SCRIPT -->        one per script to film
  <!-- BEGIN TAB --> ... <!-- END TAB -->              one nav tab per script

Layout rule: the script is the LEFT column, the competitor example the RIGHT column and the
larger media well; on a phone the example stacks above the script. Do not flip it.

Every competitor example (script reference AND winners grid) carries an "Enlarge" button that
opens the shared #zoom overlay: bigger video, the ad's detail (advertiser, country, days running,
their offer, format) and 2 to 3 insight lines. Fill those from the spec:
  script: ref_country, ref_offer, ref_format, ref_insights[]
  winner: country, offer, format, insights[]   (insights defaults to [why] when omitted)

HARD RULE when you open the rendered page in headless Chrome: headless Chrome on a desktop plays
page audio through the real speakers, and this page is a wall of competitor videos. A render was opened for a check and every video started at once
with no window to close. Every Chrome launched for a screenshot, a measurement or QC MUST carry
--mute-audio and --autoplay-policy=user-gesture-required, and MUST be killed by PID as soon as
the check ends. Never --autoplay-policy=no-user-gesture-required. To test whether a video plays
or pauses, read the element's `paused` / `currentTime` over CDP; if play() is genuinely needed,
set `muted = true` on the element first. `qc_page.mjs` in this folder does all of that and is
the command to use:  node qc_page.mjs http://127.0.0.1:8791/index.html

Spec shape: see ../templates/page.example.json (written by --example).

  python3 05_render.py --spec page.json --out ./video-ad-swipe-page-output/clinic-a/video-swipe-20260903/site
  python3 05_render.py --example > page.json
"""
import argparse
import datetime
import html
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

TPL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates", "page.html")

EXAMPLE = {
    "client": {"name": "Clinic A", "slug": "clinic-a",
               "logo": "./brand/clinic-a-logo.png",
               "primary": "#2563EB", "presenter": "Alex", "city": "Your City", "suburb": "",
               "market": "GB", "drive_folder": "https://example.com/upload-folder"},
    "agency": {"name": "Your Agency", "footer": ""},
    "page": {"title": "Filming kit · Skin consultations", "eyebrow": "Skin consultations · prepared for Clinic A · 2026",
             "h1": "Five ads to film on a phone.",
             "lead": "Each one is 20 to 45 seconds, one take, on a phone. The words are written out in full.",
             "howto": ["Pick an ad from the row at the top and read the script.",
                       "Say it in your own rhythm, one line at a time.",
                       "Name the file as shown, upload it, tick it off."],
             "recipe": "Speak to one person · about one concern · with one clear offer · send them to a quick form.",
             "hook_rule": "The first 3 seconds decide everything. Call out the person · name the problem · drop the number · make an invitation · take the blame off them.",
             "rules_chips": ["Hold the phone vertical · 9:16", "Face a window, not a light", "Captions · we add them"],
             "before_filming": ["Confirm the offer price with us before ad 1 is filmed."],
             "research_n": 250, "research_intro": "We looked at the ads running right now in your market and picked the ones that sell your kind of offer to your kind of customer.",
             "never_survives": ["Technical explainers about how the machine works.",
                                "Silent footage with music. Every strong example talks to the viewer."],
             "open_lanes": "Payment-plan framing, ads for men, seasonal moments.",
             "compliance_note": "Everything above sticks to what is safe to say in your market: no testimonials about outcomes, no before-and-after promises, no prescription medicines named.",
             "next_step": "On the call we'll choose which to record first and agree the offer. We handle captions, copy, targeting and launch.",
             "version": "v1.0"},
    "key_things": [{"count": "9 of 12", "text": "A person speaks to camera inside the first second."}],
    "winners": [{"rank": "#1", "days": 180, "page": "Competitor One", "market_pill": "", "media": "AD_ID_1",
                 "country": "GB", "offer": "Free skin consultation", "format": "Talking head, phone, clinic room",
                 "insights": ["Says her name and the clinic inside three seconds, so it reads as a person, not an ad.",
                              "The offer is said once, at the end, and never repeated."],
                 "why": "A person, one concern, one offer."}],
    "patterns": [{"what": "A person speaks to camera in the first second", "count": "9 of 12"}],
    "groups": [{"id": "B", "title": "Group B · direct offer", "lead": "Modelled on competitor ads that sell the same offer.",
                "scripts": [{"n": 1, "slug": "invite", "title": "The personal invite", "hook_job": "INVITATION",
                             "length": "about 30 seconds", "hot": "Film this one first",
                             "source": "from the 180-day example",
                             "hook": "Hi, I'm Alex from Clinic A, and I want to invite you in for a free skin consultation.",
                             "body": ["We'll look at what's going on with your skin and tell you honestly what will help.",
                                      "No pressure, no obligation."],
                             "close": "Tap below and fill in the quick form, and we'll be in touch to book you in.",
                             "on_screen": ["Free skin consultation", "No obligation", "Tap below"],
                             "offer": "[offer, to confirm]",
                             "lands_on": "Instant lead form (name, mobile, best time)",
                             "good": "Alex in the treatment room, name in the first two seconds, the offer said once, under 35 seconds.",
                             "shot": "Straight to camera, phone at eye height, facing a window.",
                             "ref_media": "AD_ID_2", "ref_page": "Competitor Two", "ref_days": 120,
                             "ref_len": "32s",
                             "ref_country": "GB", "ref_offer": "Free consultation, no obligation",
                             "ref_format": "Talking head, phone, clinic room, burned-in captions",
                             "ref_insights": ["She says her name and the clinic inside three seconds, so it reads as a person, not an ad.",
                                              "One promise, one offer, one tap.",
                                              "Take the pace and the framing. The words are already written for you."],
                             "callout": ""}]}],
    "transcripts": [{"label": "#1, 180 days", "text": "Hi, I'm ... from ..."}]
}


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=False)


def attr(s):
    """Escape for use inside a double-quoted HTML attribute (the data-* on the enlarge button)."""
    return html.escape(str(s if s is not None else ""), quote=True)


def jattr(items):
    """A JSON array safe to sit in a double-quoted attribute (data-insights)."""
    return html.escape(json.dumps([str(x) for x in (items or [])], ensure_ascii=False), quote=True)


def block(tpl, name):
    m = re.search(rf"<!-- BEGIN {name} -->(.*?)<!-- END {name} -->", tpl, re.S)
    if not m:
        sys.exit(f"template missing block {name}")
    return m.group(0), m.group(1)


def fill(frag, mapping):
    for k, v in mapping.items():
        frag = frag.replace("{{" + k + "}}", v)
    return frag


def lines(items, cls="say"):
    return "".join(f'<p class="{cls}">&ldquo;{esc(x)}&rdquo;</p>' if cls == "say" else f"<p>{esc(x)}</p>" for x in items)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec")
    ap.add_argument("--out", help="site dir to write index.html into (media copied alongside)")
    ap.add_argument("--media-src", help="research media dir (default: <spec dir>/media)")
    ap.add_argument("--example", action="store_true", help="print an example page.json and exit")
    ap.add_argument("--dry-run", action="store_true", help="render to stdout length only, write nothing")
    args = ap.parse_args()
    if args.example:
        print(json.dumps(EXAMPLE, indent=1))
        return
    if not args.spec:
        sys.exit("--spec required (or --example)")
    spec = C.load_json(args.spec)
    tpl = open(TPL, encoding="utf-8").read()
    c, p = spec["client"], spec["page"]
    ag = spec.get("agency") or {}

    # nav tabs + scripts + groups
    tab_full, tab_inner = block(tpl, "TAB")
    grp_full, grp_inner = block(tpl, "GROUP")
    scr_full, scr_inner = block(grp_inner, "SCRIPT")
    tabs, groups = [], []
    total = 0
    for g in spec["groups"]:
        scripts = []
        for s in g["scripts"]:
            total += 1
            tabs.append(fill(tab_inner, {"N": str(s["n"]), "TAB_LABEL": esc(s["title"])}))
            ref_has_video = bool(s.get("ref_media"))
            scripts.append(fill(scr_inner, {
                "N": str(s["n"]), "NN": f"{s['n']:02d}", "SLUG": esc(s.get("slug", f"ad{s['n']}")),
                "TITLE": esc(s["title"]), "HOOK_JOB": esc(s.get("hook_job", "")), "LENGTH": esc(s.get("length", "")),
                "HOT": esc(s.get("hot", "")), "SOURCE": esc(s.get("source", "")),
                "HOOK": esc(s["hook"]), "BODY_LINES": lines(s.get("body", [])), "CLOSE": esc(s["close"]),
                "ONSCREEN": " &middot; ".join(esc(x) for x in s.get("on_screen", [])) or "&mdash;",
                "OFFER": esc(s.get("offer", "")), "LANDS_ON": esc(s.get("lands_on", "")), "GOOD": esc(s.get("good", "")),
                "SHOT": esc(s.get("shot", "")), "CALLOUT": esc(s.get("callout", "")),
                "REF_MEDIA": esc(s.get("ref_media", "")), "REF_PAGE": attr(s.get("ref_page", "")),
                "REF_DAYS": attr(s.get("ref_days", "")), "REF_LEN": esc(s.get("ref_len", "")),
                "REF_KIND": "video" if ref_has_video else "thumb",
                # click-to-enlarge payload (see the ENLARGE BUTTON comment in the template)
                "REF_COUNTRY": attr(s.get("ref_country", "")), "REF_OFFER": attr(s.get("ref_offer", "")),
                "REF_FORMAT": attr(s.get("ref_format", "")), "REF_INSIGHTS": jattr(s.get("ref_insights", [])),
                "DRIVE": esc(c.get("drive_folder", "#")),
            }))
        groups.append(fill(grp_inner.replace(scr_full, "".join(scripts)), {
            "GROUP_ID": esc(g["id"]), "GROUP_TITLE": esc(g["title"]), "GROUP_LEAD": esc(g.get("lead", ""))}))
    win_full, win_inner = block(tpl, "WINNER")
    winners = "".join(fill(win_inner, {
        "RANK": esc(w["rank"]), "DAYS": attr(w["days"]), "PAGE": attr(w["page"]), "MEDIA": esc(w["media"]),
        "PILL": f'<span class="pill">{esc(w["market_pill"])}</span>' if w.get("market_pill") else "",
        "COUNTRY": attr(w.get("country", "")), "OFFER": attr(w.get("offer", "")), "FORMAT": attr(w.get("format", "")),
        "INSIGHTS": jattr(w.get("insights") or ([w["why"]] if w.get("why") else [])),
        "WHY": esc(w["why"])}) for w in spec.get("winners", []))
    pat_full, pat_inner = block(tpl, "PATTERN")
    patterns = "".join(fill(pat_inner, {"WHAT": esc(x["what"]), "COUNT": esc(x["count"])}) for x in spec.get("patterns", []))
    key_full, key_inner = block(tpl, "KEY")
    keys = "".join(fill(key_inner, {"COUNT": esc(x["count"]), "TEXT": esc(x["text"])}) for x in spec.get("key_things", []))
    tx_full, tx_inner = block(tpl, "TRANSCRIPT")
    txs = "".join(fill(tx_inner, {"LABEL": esc(x["label"]), "TEXT": esc(x["text"])}) for x in spec.get("transcripts", []))

    out = tpl.replace(tab_full, "".join(tabs)).replace(grp_full, "".join(groups)).replace(win_full, winners) \
             .replace(pat_full, patterns).replace(key_full, keys).replace(tx_full, txs)
    out = fill(out, {
        "CLIENT_NAME": esc(c["name"]), "CLIENT_LOGO": esc(os.path.basename(c.get("logo", ""))), "CLIENT_PRIMARY": c.get("primary", "#2563EB"),
        "CLIENT_SLUG": esc(c.get("slug", "client")), "DRIVE": esc(c.get("drive_folder", "#")),
        "PAGE_TITLE": esc(p["title"]), "EYEBROW": esc(p["eyebrow"]), "H1": esc(p["h1"]), "LEAD": esc(p["lead"]),
        "HOWTO": "".join(f"<p><strong>{i}.</strong> {esc(x)}</p>" for i, x in enumerate(p.get("howto", []), 1)),
        "RECIPE": esc(p.get("recipe", "")), "HOOK_RULE": esc(p.get("hook_rule", "")),
        "RULES_CHIPS": "".join(f'<span class="chip">{esc(x)}</span>' for x in p.get("rules_chips", [])),
        "BEFORE_FILMING": "".join(f'<div class="pf-item"><span class="pf-num">{i:02d}</span><p>{esc(x)}</p></div>'
                                  for i, x in enumerate(p.get("before_filming", []), 1)),
        "RESEARCH_N": esc(p.get("research_n", "")), "RESEARCH_INTRO": esc(p.get("research_intro", "")),
        "NEVER_SURVIVES": "".join(f"<li>{esc(x)}</li>" for x in p.get("never_survives", [])),
        "OPEN_LANES": esc(p.get("open_lanes", "")), "COMPLIANCE_NOTE": esc(p.get("compliance_note", "")),
        "NEXT_STEP": esc(p.get("next_step", "")), "TOTAL": str(total), "VERSION": esc(p.get("version", "v1.0")),
        "FOOTER": esc(ag.get("footer") or " · ".join(x for x in (f"© {datetime.date.today().year}", ag.get("name", ""), p.get("version", "v1.0")) if x)),
        "STORAGE_KEY": f"filming-kit-{c.get('slug', 'client')}-{re.sub(r'[^a-z0-9]+', '-', p['title'].lower())}",
    })
    leftover = sorted(set(re.findall(r"{{[A-Z_]+}}", out)))
    if leftover:
        print("WARNING unfilled tokens:", leftover)
    if args.dry_run:
        print(f"DRY RUN: rendered {len(out)} bytes, {total} scripts, {len(spec.get('winners', []))} winners; nothing written")
        return
    os.makedirs(os.path.join(args.out, "media"), exist_ok=True)
    with open(os.path.join(args.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(out)
    src = args.media_src or os.path.join(os.path.dirname(os.path.abspath(args.spec)), "media")
    ids = {w["media"] for w in spec.get("winners", [])} | {s.get("ref_media") for g in spec["groups"] for s in g["scripts"] if s.get("ref_media")}
    copied = 0
    for i in ids:
        for ext in ("mp4", "jpg"):
            sp = os.path.join(src, f"{i}.{ext}")
            if os.path.exists(sp):
                shutil.copy(sp, os.path.join(args.out, "media", f"{i}.{ext}"))
                copied += 1
    logo = os.path.expanduser(c.get("logo") or "")
    if logo and os.path.exists(logo):
        shutil.copy(logo, os.path.join(args.out, os.path.basename(logo)))
    print(f"-> {os.path.join(args.out, 'index.html')}  ({len(out)} bytes, {total} scripts, media files copied: {copied})")
    print(f"QC it SILENTLY (headless Chrome plays audio through the speakers):\n"
          f"  cd {args.out} && python3 -m http.server 8791 &\n"
          f"  node {os.path.join(os.path.dirname(os.path.abspath(__file__)), 'qc_page.mjs')} http://127.0.0.1:8791/index.html\n"
          f"  Never launch Chrome here without --mute-audio --autoplay-policy=user-gesture-required, and kill it by PID.")


if __name__ == "__main__":
    main()
