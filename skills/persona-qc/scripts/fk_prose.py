#!/usr/bin/env python3
"""Flesch-Kincaid grade on PROSE ONLY from an HTML file (or plain text). Stdlib.

Tables, code, nav, forms, captions and timestamps are dropped before measuring, because they drag the average down
and hide a grade-11 page inside a grade-6 number. Target for a client page: grade <= 7.

  python3 fk_prose.py page.html [--min-words 6] [--worst 8]
"""
import argparse
import re
import sys
from html.parser import HTMLParser

DROP = {"table", "thead", "tbody", "tr", "th", "td", "code", "pre", "nav", "script", "style", "form", "select", "option", "button", "label", "caption", "figcaption", "input", "textarea", "svg", "title", "head"}
# Void tags never get an end tag, so counting them into `skip` would drop every paragraph after the first
# bare <input> (a form page once measured on 94 of ~1,300 words).
VOID = {"input", "img", "br", "hr", "meta", "link", "source", "wbr", "area", "col", "embed", "param", "track"}


class P(HTMLParser):
    def __init__(self):
        super().__init__(); self.skip = 0; self.paras = []; self.cur = []

    def handle_starttag(self, tag, attrs):
        if tag in DROP and tag not in VOID:
            self.skip += 1
        if tag in ("p", "li", "h1", "h2", "h3", "h4", "div", "section") and self.cur:
            self.paras.append(" ".join(self.cur)); self.cur = []

    def handle_endtag(self, tag):
        if tag in DROP and tag not in VOID and self.skip:
            self.skip -= 1
        if tag in ("p", "li", "h1", "h2", "h3", "h4") and self.cur:
            self.paras.append(" ".join(self.cur)); self.cur = []

    def handle_data(self, d):
        if not self.skip and d.strip():
            self.cur.append(d.strip())


def syllables(w):
    w = w.lower(); w = re.sub(r"[^a-z]", "", w)
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", w); w = re.sub(r"^y", "", w)
    return max(1, len(re.findall(r"[aeiouy]{1,2}", w)))


def grade(text):
    sents = [s for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) >= 2]
    words = re.findall(r"[A-Za-z][A-Za-z'’-]*", text)
    if not sents or not words:
        return None, 0, 0
    syl = sum(syllables(w) for w in words)
    return 0.39 * len(words) / len(sents) + 11.8 * syl / len(words) - 15.59, len(words), len(sents)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHTMLFormatter if hasattr(argparse, "RawDescriptionHTMLFormatter") else argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--min-words", type=int, default=6, help="ignore fragments shorter than this")
    ap.add_argument("--worst", type=int, default=8, help="how many hardest paragraphs to print")
    a = ap.parse_args()
    raw = open(a.path, encoding="utf-8", errors="replace").read()
    if a.path.lower().endswith((".html", ".htm")):
        p = P(); p.feed(raw); paras = p.paras + ([" ".join(p.cur)] if p.cur else [])
    else:
        paras = [x.strip() for x in re.split(r"\n\s*\n", raw) if x.strip()]
    paras = [x for x in paras if len(x.split()) >= a.min_words and not re.match(r"^[\d£$€.,%:\s-]+$", x)]
    text = " ".join(paras)
    g, w, s = grade(text)
    if g is None:
        sys.exit("no prose found")
    print(f"  prose: {len(paras)} paragraphs, {w} words, {s} sentences, {w / s:.1f} words per sentence")
    print(f"  Flesch-Kincaid grade (prose only): {g:.1f}  {'OK (<= 7)' if g <= 7 else 'OVER the grade-7 bar'}")
    scored = sorted(((grade(x)[0] or 0, x) for x in paras), reverse=True)[:a.worst]
    print("  hardest paragraphs:")
    for gg, x in scored:
        print(f"   {gg:5.1f}  {x[:110]}{'...' if len(x) > 110 else ''}")


if __name__ == "__main__":
    main()
