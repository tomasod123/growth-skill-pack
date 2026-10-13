#!/usr/bin/env python3
"""Stage the approved, ranked set into ONE flat folder named so it sorts in launch order:
'NN TIER PAINPOINT IDv - headline.png'. Flat beats nested when the owner wants to scroll everything once.

  python3 stage_approved.py [--order data/launch_order.json] [--renders renders] [--out work/stage_approved]
"""
import argparse, json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adkit_common import staged_name, find_render


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--order', default='data/launch_order.json'); ap.add_argument('--renders', default='renders')
    ap.add_argument('--out', default='work/stage_approved')
    a = ap.parse_args()
    order = json.load(open(a.order))
    if os.path.isdir(a.out): shutil.rmtree(a.out)
    os.makedirs(a.out); missing = []
    for r in order:
        src = find_render(a.renders, r['variant'])
        if not src: missing.append(r['variant']); continue
        shutil.copy2(src, os.path.join(a.out, staged_name(r)))
    print(f'staged {len(os.listdir(a.out))} of {len(order)} -> {a.out}')
    if missing: print('MISSING RENDERS:', missing); sys.exit(1)


if __name__ == '__main__':
    main()
