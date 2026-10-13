#!/usr/bin/env python3
"""Composite a background-removed photo of a real person into each ad's reserved side column.

Use when a real person (founder, clinician, customer who consented) must appear exactly, not as an
AI likeness. Make the cut-out first with rembg using the u2net_human_seg session (clean hair, fingers,
raised arms):  pip install "rembg[cpu]"; python3 -c "from rembg import remove,new_session; ..."
A cut-out also removes background signage, phone numbers and awkward crops in one step.

Concepts opt in with a field:  "person_panel": {"side": "left"|"right", "frac": 0.42}
and optionally "person_panel_vert" (a wider column, e.g. 0.55, for tall frames).

  python3 person_panel.py --cutout assets/person-cutout.png [--renders renders] [--concepts data/concepts_final.json]
The un-composited frames are kept in <renders>_frames/ so you can re-run with new settings.
"""
import argparse, json, os, shutil
from PIL import Image, ImageFilter, ImageDraw
import numpy as np

MARGIN = 0.03


def ground(canvas, cx, base_y, width, tone):
    """Soft elliptical contact shadow so the cut-out sits on the panel instead of hovering."""
    w, h = int(width * 0.72), max(6, int(width * 0.10))
    lay = Image.new('L', canvas.size, 0)
    ImageDraw.Draw(lay).ellipse([cx - w // 2, base_y - h // 2, cx + w // 2, base_y + h // 2], fill=150)
    lay = lay.filter(ImageFilter.GaussianBlur(radius=max(6, w // 12)))
    canvas.paste(Image.new('RGB', canvas.size, tone), (0, 0), lay)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cutout', required=True); ap.add_argument('--renders', default='renders')
    ap.add_argument('--concepts', default='data/concepts_final.json')
    ap.add_argument('--squeeze', type=float, default=0.0, help='horizontal squeeze 0-0.1 if the pose reads wide')
    a = ap.parse_args()
    cs = {c['concept_id']: c for c in json.load(open(a.concepts))}
    sub = Image.open(a.cutout); sub = sub.crop(sub.getbbox())
    if a.squeeze:
        sub = sub.resize((int(sub.width * (1 - a.squeeze)), sub.height), Image.LANCZOS)
    keepdir = a.renders.rstrip('/') + '_frames'; os.makedirs(keepdir, exist_ok=True)
    n = 0
    for f in sorted(os.listdir(a.renders)):
        if not f.endswith('.png'): continue
        cid = f.split('_')[0][:-1]; c = cs.get(cid)
        if not c or not c.get('person_panel'): continue
        p = os.path.join(a.renders, f); keep = os.path.join(keepdir, f)
        if not os.path.exists(keep): shutil.copy2(p, keep)
        frame = Image.open(keep).convert('RGB'); W, H = frame.size
        spec = (c.get('person_panel_vert') if H > W else None) or c['person_panel']
        w = int(W * spec['frac']); x0 = 0 if spec['side'] == 'left' else W - w
        ratio = H / W
        # foot line and height cap must stay inside the safe area of each frame shape
        foot, cap = (0.955, 0.92) if ratio <= 1.0 else ((0.86, 0.70) if ratio <= 1.6 else (0.76, 0.56))
        sc = min(int(w * (1 - MARGIN * 2)) / sub.width, (H * cap) / sub.height)
        s2 = sub.resize((max(1, int(sub.width * sc)), max(1, int(sub.height * sc))), Image.LANCZOS)
        out = frame.copy(); cx = x0 + w // 2; base = int(H * foot)
        px = np.asarray(out.crop((x0 + 4, 8, x0 + w - 4, 40))).reshape(-1, 3).mean(axis=0)
        ground(out, cx, base, s2.width, tuple(int(v * 0.55) for v in px))
        out.paste(s2, (cx - s2.width // 2, base - s2.height), s2)
        out.save(p); n += 1
        print(f"  {f}  ({spec['side']} {int(spec['frac'] * 100)}%, {s2.height}px tall)")
    print(f'composited {n} files')


if __name__ == '__main__':
    main()
