#!/usr/bin/env python3
"""Collapse an Ads Library scrape to unique STATIC creatives and download their images immediately
(Ads Library image URLs expire). Tolerates snake_case and camelCase actor output.

  python3 dedupe.py [--raw data/raw.json] [--out data/statics_unique.json] [--images images]
Unique key = (page, normalised body[:120], normalised title[:60]). Per unique creative:
ids, page, title, body, days (longest run of any copy), variants (copies), page_ads (ads that page runs),
cc, active, lib (Ads Library link), img (local path). If an image URL has expired, recover it from
snapshot.images / cards / extra_images in the ORIGINAL payload before paying to re-scrape.
"""
import argparse, collections, json, os, re, time, urllib.request
from datetime import datetime, timezone


def g(d, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ''):
            return d[k]
    return None


def ts(v):
    if v is None: return None
    try: return datetime.fromtimestamp(int(v), tz=timezone.utc)
    except (TypeError, ValueError):
        try: return datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        except ValueError: return None


def norm(s): return re.sub(r'[^a-z0-9 ]', '', (s or '').lower()).strip()


def image_urls(snap):
    urls = []
    for im in (g(snap, 'images') or []) + (g(snap, 'extra_images', 'extraImages') or []):
        urls.append(g(im, 'original_image_url', 'originalImageUrl', 'resized_image_url', 'resizedImageUrl'))
    for c in g(snap, 'cards') or []:
        urls.append(g(c, 'original_image_url', 'originalImageUrl', 'resized_image_url', 'resizedImageUrl'))
    return [u for u in urls if u]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', default='data/raw.json'); ap.add_argument('--out', default='data/statics_unique.json')
    ap.add_argument('--images', default='images')
    a = ap.parse_args()
    raw = json.load(open(a.raw)); now = datetime.now(timezone.utc)
    page_ads = collections.Counter(g(r, 'page_name', 'pageName') for r in raw)
    groups = {}
    for r in raw:
        snap = g(r, 'snapshot') or {}
        if g(snap, 'videos') : continue  # statics only
        imgs = image_urls(snap)
        if not imgs: continue
        body = g(g(snap, 'body') or {}, 'text') if isinstance(g(snap, 'body'), dict) else g(snap, 'body')
        title = g(snap, 'title'); page = g(r, 'page_name', 'pageName')
        key = (page, norm(body)[:120], norm(title)[:60])
        st, en = ts(g(r, 'start_date', 'startDate')), ts(g(r, 'end_date', 'endDate'))
        days = ((en or now) - st).days if st else 0
        aid = str(g(r, 'ad_archive_id', 'adArchiveID'))
        x = groups.setdefault(key, dict(ids=[], page=page, title=title, body=body, days=0, variants=0, cc=set(), active=False, urls=imgs))
        x['ids'].append(aid); x['variants'] += 1; x['days'] = max(x['days'], days)
        x['cc'].add(r.get('_country') or ''); x['active'] = x['active'] or bool(g(r, 'is_active', 'isActive'))
    os.makedirs(a.images, exist_ok=True); out = []; failed = 0
    for x in groups.values():
        i = x['ids'][0]; p = os.path.join(a.images, f'{i}.jpg')
        if not os.path.exists(p):
            for u in x['urls']:
                try:
                    open(p, 'wb').write(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30).read()); break
                except Exception:
                    time.sleep(0.2)
            else:
                failed += 1
        out.append(dict(ids=x['ids'], page=x['page'], title=x['title'], body=x['body'], days=x['days'], variants=x['variants'],
                        page_ads=page_ads[x['page']], cc=sorted(x['cc']), active=x['active'],
                        lib=f'https://www.facebook.com/ads/library/?id={i}', img=p if os.path.exists(p) else None))
    json.dump(out, open(a.out, 'w'), indent=1, ensure_ascii=False)
    print(f'{len(raw)} ads -> {len(out)} unique statics; images failed: {failed}')


if __name__ == '__main__':
    main()
