#!/usr/bin/env python3
"""Creative QC for static ads: contrast, text size, safe zones, margins, and text over faces.

Needs tesseract (apt install tesseract-ocr / brew install tesseract) and
pip install "opencv-python-headless<5" numpy pillow   (OpenCV 5 dropped CascadeClassifier)
  python3 creative_qc.py <img or dir> [...] --out ./meta-launch-audit-output/qc
Writes <out>/qc.json, <out>/QC.md and an annotated copy of each image (red = fail, amber = warn,
green = ok text line, blue = face). Exit code 1 if any image FAILS.

Checks (per OCR text line):
  contrast   WCAG ratio text vs its surroundings: FAIL < 3.0, WARN < 4.5 for small text
  size       line height vs image width: FAIL < 1.5% (legal lines < 1.3%), WARN < 2.2%
  safe zone  9:16 only: all text inside y285-y1380 (scaled) and 65px from each side, else FAIL
  margins    any text closer than 4% to an edge: WARN
  faces      text line intersecting a detected face (+10%): FAIL; 9:16 face in top 285px: WARN
OCR misses or invents text on busy photos; every FAIL is shown on the annotated image, so a person
confirms it in seconds. Plan before render (SKILL.md step 3) so this mostly comes back clean.
"""
import argparse, csv, io, json, os, subprocess, sys
import numpy as np
import cv2
from PIL import Image, ImageDraw

LEGAL_WORDS = ("t&cs", "18s", "apply", "terms")


def lum(rgb):
    c = np.asarray(rgb, dtype=float) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def ratio(l1, l2):
    a, b = max(l1, l2), min(l1, l2)
    return (a + 0.05) / (b + 0.05)


def ocr_lines(path):
    out = subprocess.run(["tesseract", path, "stdout", "--psm", "11", "tsv"], capture_output=True, text=True, errors="replace").stdout
    words = []
    for r in csv.DictReader(io.StringIO(out), delimiter="\t", quoting=csv.QUOTE_NONE):
        try:
            conf = float(r["conf"]); t = (r["text"] or "").strip()
        except (TypeError, ValueError):
            continue
        if conf < 70 or not any(ch.isalnum() for ch in t):
            continue
        if len(t) < 3 and not (t.startswith("£") or (len(t) == 2 and t.isdigit())):
            continue
        x, y, w, h = int(r["left"]), int(r["top"]), int(r["width"]), int(r["height"])
        words.append([x, y, x + w, y + h, t])
    # merge words into lines: same vertical band, close horizontally
    words.sort(key=lambda z: (z[1], z[0]))
    lines = []
    for w in words:
        for L in lines:
            cy = (w[1] + w[3]) / 2; lh = L[3] - L[1]
            if L[1] - lh * 0.4 <= cy <= L[3] + lh * 0.4 and w[0] - L[2] < lh * 2.5 and abs((w[3] - w[1]) - lh) < lh * 0.6:
                L[0] = min(L[0], w[0]); L[1] = min(L[1], w[1]); L[2] = max(L[2], w[2]); L[3] = max(L[3], w[3]); L[4] += " " + w[4]
                break
        else:
            lines.append(list(w))
    return lines


def faces(img_bgr, W):
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    fs = cas.detectMultiScale(g, scaleFactor=1.08, minNeighbors=7, minSize=(int(W * 0.06), int(W * 0.06)))
    return [list(map(int, f)) for f in fs]


def check(path):
    im = Image.open(path).convert("RGB"); W, H = im.size; a = np.asarray(im)
    story = H / W > 1.7
    sy = H / 1920
    res = {"file": os.path.basename(path), "size": [W, H], "issues": [], "lines": []}
    fcs = faces(cv2.cvtColor(a, cv2.COLOR_RGB2BGR), W)
    res["faces"] = fcs
    for (x0, y0, x1, y1, t) in ocr_lines(path):
        h = y1 - y0
        real = [w for w in t.split() if (len(w) >= 3 and sum(ch.isalpha() for ch in w) >= 3 and any(v in w.lower() for v in "aeiouy")) or any(ch.isdigit() for ch in w)]
        if not real:
            continue  # OCR noise from photo texture (neon, shelves, packaging)
        legal = any(k in t.lower() for k in LEGAL_WORDS)
        box = a[y0:y1, x0:x1].reshape(-1, 3)
        pad = max(4, h // 3)
        rx0, ry0, rx1, ry1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
        ring = np.concatenate([a[ry0:y0, rx0:rx1].reshape(-1, 3), a[y1:ry1, rx0:rx1].reshape(-1, 3),
                               a[y0:y1, rx0:x0].reshape(-1, 3), a[y0:y1, x1:rx1].reshape(-1, 3)])
        if len(box) == 0 or len(ring) == 0:
            continue
        lb = lum(ring).reshape(-1); lbg = float(np.median(lb))
        lx = lum(box).reshape(-1); d = np.abs(lx - lbg)
        fg = lx[d >= np.quantile(d, 0.85)]
        cr = ratio(float(np.median(fg)), lbg)
        line = {"text": t[:60], "box": [x0, y0, x1, y1], "h_pct": round(100 * h / W, 2), "contrast": round(cr, 2), "status": "ok", "why": []}
        small = h / W < 0.03
        if cr < 3.0:
            line["status"] = "FAIL"; line["why"].append(f"contrast {cr:.1f}:1 (min 3.0)")
        elif small and cr < 4.5:
            line["status"] = "WARN"; line["why"].append(f"contrast {cr:.1f}:1 on small text (aim 4.5)")
        minh = 0.013 if legal else 0.015
        if h / W < minh:
            line["status"] = "FAIL"; line["why"].append(f"text {100*h/W:.1f}% of width (min {100*minh:.1f}%)")
        elif h / W < 0.022 and not legal and line["status"] == "ok":
            line["status"] = "WARN"; line["why"].append(f"text {100*h/W:.1f}% of width, small on a phone")
        if story and (y0 < 285 * sy or y1 > 1380 * sy or x0 < 65 * W / 1080 or x1 > W - 65 * W / 1080):
            if h / W < 0.012:
                line["status"] = "WARN" if line["status"] == "ok" else line["status"]; line["why"].append("tiny text outside the safe zone (logo wordmark? fine if decorative)")
            else:
                line["status"] = "FAIL"; line["why"].append("outside the Reels/Stories safe zone (y285-1380, 65px sides)")
        elif min(x0, y0, W - x1, H - y1) < 0.03 * W and line["status"] == "ok":
            line["status"] = "WARN"; line["why"].append("within 3% of the edge")
        for (fx, fy, fw, fh) in fcs:
            ex, ey = fw * 0.1, fh * 0.1
            if x0 < fx + fw + ex and x1 > fx - ex and y0 < fy + fh + ey and y1 > fy - ey:
                line["status"] = "FAIL"; line["why"].append("text over a face")
        res["lines"].append(line)
    if story:
        for (fx, fy, fw, fh) in fcs:
            if fy < 285 * sy:
                res["issues"].append({"status": "WARN", "why": "face in the top 285px, under the Instagram header"})
    st = [l["status"] for l in res["lines"]] + [i["status"] for i in res["issues"]]
    res["verdict"] = "FAIL" if "FAIL" in st else ("WARN" if "WARN" in st else "PASS")
    if not res["lines"]:
        res["issues"].append({"status": "WARN", "why": "OCR found no text: check by eye"})
    return res, im


def annotate(im, res, out):
    d = ImageDraw.Draw(im)
    col = {"FAIL": (230, 30, 30), "WARN": (240, 160, 0), "ok": (40, 180, 70)}
    for (fx, fy, fw, fh) in res["faces"]:
        d.rectangle([fx, fy, fx + fw, fy + fh], outline=(40, 120, 255), width=4)
    for l in res["lines"]:
        d.rectangle(l["box"], outline=col[l["status"]], width=3)
    if res["size"][1] / res["size"][0] > 1.7:
        s = res["size"][1] / 1920
        for y in (285, 1380):
            d.line([(0, y * s), (res["size"][0], y * s)], fill=(230, 30, 30), width=2)
    im.save(out, quality=85)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("paths", nargs="+"); ap.add_argument("--out", required=True)
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    files = []
    for p in a.paths:
        files += [os.path.join(p, f) for f in sorted(os.listdir(p)) if f.lower().endswith((".png", ".jpg", ".jpeg"))] if os.path.isdir(p) else [p]
    allres = []
    for f in files:
        r, im = check(f); allres.append(r)
        annotate(im, r, os.path.join(a.out, "qc-" + os.path.splitext(os.path.basename(f))[0] + ".jpg"))
    json.dump(allres, open(os.path.join(a.out, "qc.json"), "w"), indent=1)
    L = ["# Creative QC", "", "| Image | Verdict | Problems |", "|---|---|---|"]
    for r in allres:
        probs = [f"{l['status']}: '{l['text'][:28]}' {', '.join(l['why'])}" for l in r["lines"] if l["status"] != "ok"] + [f"{i['status']}: {i['why']}" for i in r["issues"]]
        L.append(f"| {r['file']} | {r['verdict']} | {'<br>'.join(probs) or '-'} |")
    open(os.path.join(a.out, "QC.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))
    sys.exit(1 if any(r["verdict"] == "FAIL" for r in allres) else 0)


if __name__ == "__main__":
    main()
