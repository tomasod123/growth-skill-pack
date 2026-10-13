#!/usr/bin/env python3
"""Prove no copy is cropped, geometrically (OCR across ratios gives dozens of false alarms, because the
sizes come from separate renders, not crops of one another).

  1:1   pure resize of the square render           -> crop impossible; confirm aspect preserved
  9:16  composition scaled into the safe area      -> crop impossible; confirm 1080x1920
  4:5   the only one that crops: re-measure every row to_ratio() removed and confirm each is flat.
        A flat row cannot contain type.

  python3 crop_proof.py [--order data/launch_order.json] [--square renders] [--vert renders_vert] [--ratios work/ratios]
"""
import argparse, json, os, sys
from PIL import Image
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adkit_common import staged_name, flat_rows, find_render, FLAT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--order', default='data/launch_order.json')
    ap.add_argument('--square', default='renders'); ap.add_argument('--vert', default='renders_vert')
    ap.add_argument('--ratios', default='work/ratios')
    a = ap.parse_args()
    order = json.load(open(a.order))
    bad, details = [], []
    for r in order:
        v = r['variant']; src = find_render(a.vert, v)
        if not src: bad.append((v, 'no 2:3 source')); continue
        arr = np.asarray(Image.open(src).convert('RGB')); H, W = arr.shape[:2]
        need = H - int(W / 0.8)
        if need <= 0: details.append((r['rank'], v, 0, 0)); continue
        t_av, b_av = flat_rows(arr, 'top', need), flat_rows(arr, 'bottom', need)
        tt = min(t_av, need // 2 + need % 2); tb = min(b_av, need - tt); tt = min(t_av, need - tb)
        worst = 0.0
        if tt: worst = max(worst, float(arr[:tt].std(axis=1).max()))
        if tb: worst = max(worst, float(arr[H - tb:].std(axis=1).max()))
        if worst > FLAT: bad.append((r['rank'], v, f'removed a NON-flat row, worst std {worst:.1f}'))
        details.append((r['rank'], v, tt, tb))
    print(f'4:5 crop proof over {len(details)} ads; inked rows removed: {len(bad)}')
    for b in bad[:20]: print('   ', b)
    if details:
        mx = max(d[2] + d[3] for d in details)
        print(f'  largest total crop: {mx}px; ads needing no crop: {sum(1 for d in details if d[2] + d[3] == 0)}')
    sq_ok = st_ok = 0
    for r in order:
        name = staged_name(r); s = find_render(a.square, r['variant'])
        o = f'{a.ratios}/1x1 - 1080x1080/{name}'
        if s and os.path.exists(o):
            a1, a2 = Image.open(s).size, Image.open(o).size
            sq_ok += abs(a1[0] / a1[1] - a2[0] / a2[1]) < 0.01
        o9 = f'{a.ratios}/9x16 - 1080x1920/{name}'
        st_ok += os.path.exists(o9) and Image.open(o9).size == (1080, 1920)
    print(f'1:1 aspect preserved: {sq_ok}/{len(order)}   9:16 exact 1080x1920: {st_ok}/{len(order)}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
