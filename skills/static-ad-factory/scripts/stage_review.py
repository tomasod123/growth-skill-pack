#!/usr/bin/env python3
"""Stage renders for the first review round: one flat folder, '<ID> - <headline>.png', plus labelled
contact sheets (ID stamped under each image) so a reviewer can point at a specific ad.
Folder links are the same for every file inside, so twelve pasted links all resolve to one folder:
contact sheets with IDs fix that.

  python3 stage_review.py [--renders renders] [--concepts data/concepts_final.json] [--out work/stage_review]
"""
import argparse, json, os, re, shutil, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adkit_common import safe


def contact_sheets(items, out, per=24, cols=6, tile=300):
    """items: [(label, path)]. Every sheet asserted under 2000 px: one oversized image in a multi-image
    read can break image reading for the rest of a Claude session."""
    n = 0
    for s in range(0, len(items), per):
        chunk = items[s:s + per]; rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * tile, rows * (tile + 24)), 'white'); d = ImageDraw.Draw(sheet)
        for k, (label, p) in enumerate(chunk):
            im = Image.open(p).convert('RGB'); im.thumbnail((tile - 8, tile - 8))
            x, y = (k % cols) * tile, (k // cols) * (tile + 24)
            sheet.paste(im, (x + 4, y + 4)); d.text((x + 6, y + tile + 4), label[:40], fill='black')
        assert max(sheet.size) < 1980, sheet.size
        n += 1; sheet.save(os.path.join(out, f'00 contact sheet {n:02d}.jpg'), quality=80)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--renders', default='renders'); ap.add_argument('--concepts', default='data/concepts_final.json')
    ap.add_argument('--out', default='work/stage_review')
    a = ap.parse_args()
    cs = {c['concept_id']: c for c in json.load(open(a.concepts))}
    os.makedirs(a.out, exist_ok=True); items = []; n = 0
    for f in sorted(os.listdir(a.renders)):
        m = re.match(r'([A-Z]+\d+)([ab])_.*\.png$', f)
        if not m or m.group(1) not in cs: continue
        cid, v = m.groups(); head = safe(cs[cid].get('headline_on_image') or 'no text', 46)
        dest = os.path.join(a.out, f'{cid}{v} - {head}.png')
        shutil.copy2(os.path.join(a.renders, f), dest); n += 1
        items.append((f'{cid}{v}', dest))
    k = contact_sheets(items, a.out)
    print(f'staged {n} files, {k} contact sheets -> {a.out}')


if __name__ == '__main__':
    main()
