#!/usr/bin/env python3
"""Merge classification labels + vision tags onto the unique statics, score them, write data/ranked.json,
a text-load table (on-image text elements vs days running) and a contact sheet of the top 40.

Inputs (written by the classify and vision-tag subagents, see references/schemas.md):
  data/statics_unique.json        from dedupe.py
  work/classify/labels*.json      [{id, is_target: true/false, fit: 0..1, segment}]
  work/tags_*.json                [{id, layout, hook_type, text_lines, headline_on_image, icp_callout_text, ...}]
Score = 45% days running + 20% variants + 10% advertiser scale + 25% fit (all log-scaled, 0-100).
Days running is the honest public proxy (Meta shows no impressions for most ads) but it also rewards
ads nobody switched off: trust the 91-200 day band most.

  python3 merge_rank.py [--prefer-country GB]
"""
import argparse, collections, glob, json, math, os, statistics


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--prefer-country', default='')
    ap.add_argument('--top', type=int, default=40)
    a = ap.parse_args()
    out = {g['ids'][0]: g for g in json.load(open('data/statics_unique.json'))}
    labels = {}
    for f in glob.glob('work/classify/labels*.json'):
        for x in json.load(open(f)): labels[str(x['id'])] = x
    tags = {}
    for f in sorted(glob.glob('work/tags_*.json')):
        try:
            for x in json.load(open(f)):
                k = str(x['id']); cur = tags.get(k)
                if cur is None or (cur.get('layout') is None and x.get('layout') is not None): tags[k] = x  # complete beats null
        except Exception as e:
            print('bad file', f, e)
    rows = []
    for i, g in out.items():
        l = labels.get(i)
        if not l or l.get('is_target') is not True: continue
        t = tags.get(i, {})
        s_days = min(math.log1p(g['days']) / math.log1p(400), 1.0)
        s_var = min(math.log1p(g['variants'] - 1) / math.log1p(10), 1.0)
        s_page = min(math.log1p(g.get('page_ads') or 1) / math.log1p(50), 1.0)
        fit = float(l.get('fit') or 0.5)
        callout = 1.0 if t.get('icp_callout_text') else 0.6
        geo = 1.0 if (not a.prefer_country or a.prefer_country in g.get('cc', [])) else 0.85
        s_fit = fit * 0.6 + callout * 0.25 + geo * 0.15
        score = round(100 * (0.45 * s_days + 0.20 * s_var + 0.10 * s_page + 0.25 * s_fit), 1)
        rows.append(dict(id=i, score=score, days=g['days'], variants=g['variants'], page_ads=g.get('page_ads'), cc=g.get('cc'),
                         page=g['page'], segment=l.get('segment'), active=g.get('active'), title=g.get('title'),
                         body=(g.get('body') or '')[:240], lib=g['lib'], img=g.get('img'), tag=t))
    rows.sort(key=lambda r: -r['score'])
    json.dump(rows, open('data/ranked.json', 'w'), indent=1, ensure_ascii=False)
    print('ranked', len(rows), '| tagged', sum(1 for r in rows if r['tag']), '| with image', sum(1 for r in rows if r['img']))
    print('layouts', collections.Counter(r['tag'].get('layout') for r in rows if r['tag']).most_common(10))
    print('hooks', collections.Counter(r['tag'].get('hook_type') for r in rows if r['tag']).most_common(10))
    # text-load table: the finding to re-derive on every new niche
    by = collections.defaultdict(list)
    for r in rows:
        tl = r['tag'].get('text_lines')
        if isinstance(tl, int): by[min(tl, 7)].append(r['days'])
    tbl = {k: dict(n=len(v), median_days=statistics.median(v), pct_over_90=round(100 * sum(d > 90 for d in v) / len(v))) for k, v in sorted(by.items())}
    json.dump(tbl, open('data/textload.json', 'w'), indent=1)
    print('\ntext elements on image -> days running (7 = 7 or more)')
    for k, v in tbl.items(): print(f"  {k}: n={v['n']:<4} median {v['median_days']:>5}d  {v['pct_over_90']}% past 90 days")
    from PIL import Image, ImageDraw
    top = [r for r in rows if r['img'] and os.path.exists(r['img'])][:a.top]; W = 240; cols = 8
    if top:
        sheet = Image.new('RGB', (cols * W, ((len(top) + cols - 1) // cols) * (W + 30)), 'white'); d = ImageDraw.Draw(sheet)
        for k, r in enumerate(top):
            try: im = Image.open(r['img']).convert('RGB'); im.thumbnail((W - 8, W - 8))
            except Exception: continue
            x, y = (k % cols) * W, (k // cols) * (W + 30)
            sheet.paste(im, (x + 4, y + 4)); d.text((x + 4, y + W + 2), f"#{k + 1} {r['score']:.0f} {r['days']}d {str(r['page'])[:20]}", fill='black')
        assert max(sheet.size) < 1980, sheet.size
        os.makedirs('work', exist_ok=True); sheet.save('work/top_sheet.jpg', quality=72); print('sheet', sheet.size)


if __name__ == '__main__':
    main()
