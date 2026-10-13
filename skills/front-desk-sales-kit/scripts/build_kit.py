#!/usr/bin/env python3
"""
build_kit.py - render the front-desk sales kit (cheat sheet + full playbook) from one config.

Usage
  python3 build_kit.py <config.json> [--out DIR] [--only cheatsheet|playbook]

Writes <out>/<slug>-cheatsheet.html and <out>/<slug>-playbook.html
(default out: ./front-desk-sales-kit-output/<slug>/). Copies LOGO_FILE next to them
if it is a local path relative to the config.

Config = scalar {{TOKENS}} (BUSINESS_NAME, OFFER_NAME, BRAND_PRIMARY ...) plus lists
(OPENERS, CALL_STEPS, OBJECTIONS, TEXTS, DRILLS, FAQS, SPEED_HABITS, OFFER_TERMS,
KEEP_BY_THE_PHONE). Scalar tokens are also replaced inside list text, so an objection
handler can say "{{BOOKED_CALL}}". See references/tokens-registry.md.

Tokens that look like GHL merge fields ({{contact.first_name}}, {{custom_values.x}})
are lowercase/dotted and are left alone on purpose. Any UPPERCASE {{TOKEN}} left
unreplaced is reported so a raw token never ships.
"""
import argparse
import html
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TPL_DIR = os.path.join(HERE, "..", "templates")
TOKEN_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "business"


def esc(s):
    """HTML-escape but keep simple <b>/<em> the config author typed."""
    t = html.escape(str(s), quote=False)
    for tag in ("b", "em", "strong", "i", "br"):
        t = t.replace(f"&lt;{tag}&gt;", f"<{tag}>").replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    return t.replace("&lt;br/&gt;", "<br/>")


def fill(text, scalars):
    return TOKEN_RE.sub(lambda m: str(scalars[m.group(1)]) if m.group(1) in scalars else m.group(0), text)


def says(lines, cls="say"):
    return "".join(f'<div class="{cls}">"{esc(x)}"</div>' for x in lines or [])


def build_blocks(c):
    b = {}
    # cheat sheet pieces
    b["OPENER_BLOCK"] = says((c.get("OPENERS") or [{}])[0].get("lines"))
    b["OPENER_BRANCHES"] = " &nbsp;·&nbsp; ".join(
        f"<b>{esc(o['label'])}</b> {esc(o['note'])}" for o in (c.get("OPENERS") or [])[1:] if o.get("note"))
    b["KEEP_BY_THE_PHONE"] = "".join(
        f'<div class="c"><div class="w">{esc(k["word"])}</div><div class="d">{esc(k["what"])}</div></div>'
        for k in c.get("KEEP_BY_THE_PHONE") or [])
    b["KEEP_TIPS"] = " ".join(esc(t) for t in c.get("KEEP_TIPS") or [])
    objs = c.get("OBJECTIONS") or []
    top = c.get("CHEATSHEET_TOP_N", 11)
    b["OBJECTION_ROWS"] = "".join(
        f'<tr><td class="rk">{i}</td><td class="q">{esc(o["q"])}</td><td class="a">"{esc(o.get("short") or o["handle"])}"</td></tr>'
        for i, o in enumerate(objs[:top], 1))
    b["OFFER_TERMS"] = "".join(f'<span class="t">{esc(t)}</span>' for t in c.get("OFFER_TERMS") or [])

    # playbook pieces
    b["PRINCIPLES_LIST"] = "".join(f"<li>{esc(p)}</li>" for p in c.get("PRINCIPLES") or [])
    b["OPENER_CARDS"] = "".join(
        f'<div class="step"><div class="step-no">{esc(o["label"])}</div>{says(o.get("lines"), "quote")}'
        + (f'<p class="note">{esc(o["note"])}</p>' if o.get("note") else "") + "</div>"
        for o in c.get("OPENERS") or [])
    steps = []
    for i, s in enumerate(c.get("CALL_STEPS") or [], 1):
        h = (f'<div class="step"><div class="step-no">{i:02d} · {esc(s["title"])}</div>'
             f'<p class="goal">{esc(s.get("goal", ""))}</p>{says(s.get("say"), "quote")}')
        if s.get("cue"):
            h += f'<p class="note"><strong>Cue:</strong> {esc(s["cue"])}</p>'
        if s.get("compliance"):
            h += f'<p class="compliance"><strong>Compliance:</strong> {esc(s["compliance"])}</p>'
        steps.append(h + "</div>")
    b["CALL_STEPS"] = "".join(steps)
    cards = []
    for i, o in enumerate(objs, 1):
        h = (f'<div class="obj-card"><div class="obj-head"><span class="rank">#{i}</span>'
             f'<span class="freq">{esc(o.get("freq", ""))}</span>'
             f'<span class="bucket-tag">{esc(o.get("bucket", ""))}</span></div>'
             f'<h3>{esc(o["q"])}</h3>')
        if o.get("variants"):
            h += f'<p class="says">Also heard as: {esc(" · ".join(o["variants"]))}</p>'
        h += f'<div class="rebuttal">"{esc(o["handle"])}"</div>'
        if o.get("note"):
            h += f'<p class="rebuttal-note"><strong>Coaching note:</strong> {esc(o["note"])}</p>'
        cards.append(h + "</div>")
    b["OBJECTION_CARDS"] = "".join(cards)
    b["TEXT_CARDS"] = "".join(
        f'<div class="sms-card"><div class="sms-meta"><span class="pill">{esc(t["label"])}</span>'
        f'<span>{esc(t.get("when", ""))}</span></div><div class="sms-body">{esc(t["body"])}</div></div>'
        for t in c.get("TEXTS") or [])
    b["FAQ_LIST"] = "".join(
        f'<div class="faq"><p class="fq">"{esc(f["q"])}"</p><p class="fa">"{esc(f["a"])}"</p></div>'
        for f in c.get("FAQS") or [])
    b["DRILL_CARDS"] = "".join(
        f'<div class="drill"><div class="drill-no">Drill {i:02d}</div><h3>{esc(d["title"])}</h3>'
        f'<div class="lead-says">{esc(d["situation"])}</div>'
        f'<p class="target-move"><strong>Target move:</strong> {esc(d["target"])}</p>'
        f'<p class="principle">{esc(d.get("principle", ""))}</p>'
        f'<p class="success">Aim: {esc(d.get("aim", ""))}</p></div>'
        for i, d in enumerate(c.get("DRILLS") or [], 1))
    b["SPEED_HABITS"] = "".join(f"<li>{esc(h)}</li>" for h in c.get("SPEED_HABITS") or [])
    return b


def render(tpl_name, scalars, blocks):
    tpl = open(os.path.join(TPL_DIR, tpl_name), encoding="utf-8").read()
    # blocks first (they may contain scalar tokens), then scalars
    for k, v in blocks.items():
        tpl = tpl.replace("{{" + k + "}}", v)
    tpl = fill(tpl, {k: esc(v) for k, v in scalars.items()})
    left = sorted(set(TOKEN_RE.findall(tpl)))
    return tpl, left


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config")
    ap.add_argument("--out")
    ap.add_argument("--only", choices=["cheatsheet", "playbook"])
    a = ap.parse_args()

    cfg = json.load(open(a.config, encoding="utf-8"))
    scalars = {k: v for k, v in cfg.items() if isinstance(v, (str, int, float)) and not k.startswith("_")}
    for _ in range(3):  # scalars may reference other scalars, e.g. SHEET_HEADLINE uses {{OFFER_NAME}}
        scalars = {k: fill(v, scalars) if isinstance(v, str) else v for k, v in scalars.items()}
    # let list text use scalar tokens: fill them before building blocks
    def deep(v):
        if isinstance(v, str):
            return fill(v, scalars)
        if isinstance(v, list):
            return [deep(x) for x in v]
        if isinstance(v, dict):
            return {k: deep(x) for k, x in v.items()}
        return v
    lists = {k: deep(v) for k, v in cfg.items() if isinstance(v, list)}
    cfg_filled = {**cfg, **lists}
    blocks = build_blocks(cfg_filled)

    slug = slugify(cfg.get("BUSINESS_NAME", "business"))
    out = a.out or os.path.join("front-desk-sales-kit-output", slug)
    os.makedirs(out, exist_ok=True)

    logo = cfg.get("LOGO_FILE", "")
    if logo and not re.match(r"^(https?:|data:)", logo):
        src = os.path.join(os.path.dirname(os.path.abspath(a.config)), logo)
        if os.path.isfile(src):
            dst = os.path.join(out, logo)
            os.makedirs(os.path.dirname(dst) or out, exist_ok=True)
            shutil.copyfile(src, dst)
        else:
            print(f"note: LOGO_FILE {logo!r} not found next to the config; the page shows the business name instead")

    bad = 0
    for kind in ("cheatsheet", "playbook"):
        if a.only and a.only != kind:
            continue
        html_out, left = render(f"{kind}.html", scalars, blocks)
        path = os.path.join(out, f"{slug}-{kind}.html")
        open(path, "w", encoding="utf-8").write(html_out)
        if left:
            bad += 1
            print(f"WARNING {kind}: unreplaced tokens: {', '.join(left)}")
        dashes = html_out.count("—")
        if dashes:
            print(f"note {kind}: {dashes} em-dash(es) in the copy; replace with commas if your style bans them")
        print(f"OK {kind} -> {path}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
