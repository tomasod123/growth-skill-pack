#!/usr/bin/env python3
"""Derive 1:1 1080x1080 and 4:5 1080x1350 from the renders, in launch order.

  1:1  pure resize of the square render (no crop possible)
  4:5  from the 2:3 vertical render: crop ONLY rows measured flat, then extend any remaining
       difference with a SOLID colour sampled from the edge (never blind centre-crop, never row replication)
9:16 is built by make_story.py, because a story needs the interface bands verified.

  python3 make_ratios.py [--order data/launch_order.json] [--square renders] [--vert renders_vert] [--out work/ratios]
"""
import argparse, json, os, sys
from PIL import Image
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adkit_common import staged_name, flat_rows, extend_solid, find_render

SIZES = {'1x1 - 1080x1080': (1080, 1080), '4x5 - 1080x1350': (1080, 1350)}


def to_ratio(im, ratio):
    W, H = im.size
    want_h = int(W / ratio)
    if want_h < H:
        need = H - want_h
        a = np.asarray(im.convert('RGB'))
        t, b = flat_rows(a, 'top', need), flat_rows(a, 'bottom', need)
        take_t = min(t, need // 2 + need % 2)
        take_b = min(b, need - take_t)
        take_t = min(t, need - take_b)  # let one edge cover for the other
        im = im.crop((0, take_t, W, H - take_b))
    W, H = im.size
    tw, th = (W, int(W / ratio)) if int(W / ratio) >= H else (int(H * ratio), H)
    return extend_solid(im, tw, th)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--order', default='data/launch_order.json')
    ap.add_argument('--square', default='renders'); ap.add_argument('--vert', default='renders_vert')
    ap.add_argument('--out', default='work/ratios')
    a = ap.parse_args()
    order = json.load(open(a.order))
    for d in SIZES: os.makedirs(f'{a.out}/{d}', exist_ok=True)
    made, missing = {k: 0 for k in SIZES}, []
    for r in order:
        name = staged_name(r)
        sq, ve = find_render(a.square, r['variant']), find_render(a.vert, r['variant'])
        if sq:
            Image.open(sq).convert('RGB').resize(SIZES['1x1 - 1080x1080'], Image.LANCZOS).save(f"{a.out}/1x1 - 1080x1080/{name}")
            made['1x1 - 1080x1080'] += 1
        else:
            missing.append(('1x1', r['variant']))
        if ve:
            to_ratio(Image.open(ve).convert('RGB'), 0.8).resize(SIZES['4x5 - 1080x1350'], Image.LANCZOS).save(f"{a.out}/4x5 - 1080x1350/{name}")
            made['4x5 - 1080x1350'] += 1
        else:
            missing.append(('vert', r['variant']))
    print('built:', made)
    if missing: print(f'MISSING {len(missing)}:', missing[:20])


if __name__ == '__main__':
    main()
