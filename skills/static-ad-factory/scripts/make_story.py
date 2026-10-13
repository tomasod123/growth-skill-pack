#!/usr/bin/env python3
"""Build Stories-safe 9:16 1080x1920 assets, and PROVE each one is safe rather than trusting the prompt.

Instagram and Facebook draw their interface over a story: profile photo, name and close button over
the top ~14 per cent; reply bar and CTA sticker over the bottom ~20 per cent. Type in either band is
invisible. Prompting the model to respect the zones is not reliable, so:
  1. render natively at 1152x2048 (render.py --aspect story)
  2. OCR both interface bands with tesseract
  3. keep the native render only when both bands are provably empty; otherwise REBUILD: scale the
     4:5 composition to fit the safe area, centre it, fill outwards with a solid sampled colour.

  python3 make_story.py [--order data/launch_order.json] [--story renders_story] [--fallback "work/ratios/4x5 - 1080x1350"]
"""
import argparse, json, os, re, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adkit_common import staged_name, band_colour, find_render

FINAL = (1080, 1920)
TOP, BOT = 0.14, 0.20
SAFE = 1.0 - TOP - BOT


def ocr_band(args):
    path, which = args
    im = Image.open(path).convert('RGB'); W, H = im.size
    box = (0, 0, W, int(H * TOP)) if which == 'top' else (0, int(H * (1 - BOT)), W, H)
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as t:
        tmp = t.name
    im.crop(box).save(tmp)
    try:
        out = subprocess.run(['tesseract', tmp, 'stdout', '--psm', '11'], capture_output=True, text=True, timeout=90).stdout
    finally:
        os.remove(tmp)
    return re.findall(r'[A-Za-z£$€0-9]{3,}', out)  # 1-2 char hits are texture noise


def rebuild_safe(src_path):
    im = Image.open(src_path).convert('RGB')
    fw, fh = FINAL; safe_h = int(fh * SAFE)
    sc = min(fw / im.width, safe_h / im.height)
    block = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS)
    canvas = Image.new('RGB', (fw, fh))
    y = int(fh * TOP) + (safe_h - block.height) // 2
    x = (fw - block.width) // 2
    canvas.paste(Image.new('RGB', (fw, y), band_colour(block, 'top')), (0, 0))
    canvas.paste(Image.new('RGB', (fw, fh - y - block.height), band_colour(block, 'bottom')), (0, y + block.height))
    if x:
        canvas.paste(Image.new('RGB', (x, block.height), band_colour(block, 'left')), (0, y))
        canvas.paste(Image.new('RGB', (fw - x - block.width, block.height), band_colour(block, 'right')), (x + block.width, y))
    canvas.paste(block, (x, y))
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--order', default='data/launch_order.json')
    ap.add_argument('--story', default='renders_story')
    ap.add_argument('--fallback', default='work/ratios/4x5 - 1080x1350')
    ap.add_argument('--out', default='work/ratios/9x16 - 1080x1920')
    a = ap.parse_args()
    order = json.load(open(a.order)); os.makedirs(a.out, exist_ok=True)
    jobs = [(r, staged_name(r), find_render(a.story, r['variant'])) for r in order]
    native = [(j[2], b) for j in jobs if j[2] for b in ('top', 'bottom')]
    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(ocr_band, native))
    found = {}
    for (path, band), words in zip(native, res):
        if words: found.setdefault(path, []).append((band, words[:6]))
    kept, rebuilt, missing = 0, [], []
    for r, name, path in jobs:
        if path and path not in found:
            Image.open(path).convert('RGB').resize(FINAL, Image.LANCZOS).save(f'{a.out}/{name}'); kept += 1
        else:
            fb = os.path.join(a.fallback, name)
            if not os.path.exists(fb): missing.append(name); continue
            rebuild_safe(fb).save(f'{a.out}/{name}')
            rebuilt.append((name[:46], found.get(path, 'no native render')))
    print(f'native 9:16 kept (interface bands provably clear): {kept}')
    print(f'rebuilt into the safe area: {len(rebuilt)}')
    for n, why in rebuilt[:40]:
        w = why if isinstance(why, str) else '; '.join(f'{b}:{" ".join(ws[:3])}' for b, ws in why)
        print(f'   {n}  <- {w[:70]}')
    if missing: print('MISSING (run make_ratios.py first):', missing[:20])


if __name__ == '__main__':
    main()
