#!/usr/bin/env python3
"""Composite the REAL logo PNG into the corner a render reserved.

Image models produce garbled lettering for any real wordmark, so concepts reserve an empty corner
and the actual logo is stamped in here. Auto-tints to an ivory mark when the corner samples dark.
Reserve a corner the CTA cannot reach (the CTA usually sits low), so top-left or top-right.

  python3 logo_stamp.py --logo assets/logo.png --ids A06,B07 --corner top-left [--renders renders] [--width 0.27]
Overwrites the renders in place; keep originals under version control.
"""
import argparse, os
from PIL import Image
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--logo', required=True); ap.add_argument('--ids', required=True, help='comma list of concept ids')
    ap.add_argument('--corner', default='top-left', choices=['top-left', 'top-right', 'bottom-left', 'bottom-right'])
    ap.add_argument('--renders', default='renders'); ap.add_argument('--width', type=float, default=0.27)
    ap.add_argument('--pad', type=float, default=0.05)
    a = ap.parse_args()
    logo = Image.open(a.logo).convert('RGBA'); n = 0
    ids = [i.strip() for i in a.ids.split(',') if i.strip()]
    for f in sorted(os.listdir(a.renders)):
        if not (f.endswith('.png') and any(f.startswith(i) and f[len(i):len(i) + 1] in 'ab' for i in ids)):
            continue
        p = os.path.join(a.renders, f)
        im = Image.open(p).convert('RGB'); W, H = im.size
        lw = int(W * a.width); lh = max(1, int(logo.height * lw / logo.width))
        x = int(W * a.pad) if 'left' in a.corner else W - lw - int(W * a.pad)
        y = int(H * a.pad) if 'top' in a.corner else H - lh - int(H * a.pad)
        dark = np.asarray(im.crop((x, y, x + lw, y + lh)).convert('L')).mean() < 128
        lg = logo.resize((lw, lh), Image.LANCZOS)
        alpha = np.asarray(lg)[:, :, 3]
        rgb = np.full((lh, lw, 3), (245, 244, 240), dtype=np.uint8) if dark else np.asarray(lg)[:, :, :3]
        lg2 = Image.fromarray(np.dstack([rgb, alpha]), 'RGBA')
        im.paste(lg2, (x, y), lg2); im.save(p); n += 1
        print(f"  {f}  logo {a.corner}, {'ivory on dark' if dark else 'as drawn on light'}")
    print(f'stamped {n} files')


if __name__ == '__main__':
    main()
