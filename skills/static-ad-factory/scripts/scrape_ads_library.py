#!/usr/bin/env python3
"""Scrape the Meta Ads Library through Apify (actor curious_coder/facebook-ads-library-scraper).

ALWAYS check for an existing scrape first (an ad-library skill or a previous run's data/raw.json):
reusing a scrape costs nothing. This script estimates cost and refuses to run over --cap-usd.

  set -a; source ~/.claude/skills/.env; set +a
  python3 scrape_ads_library.py --query "hair transplant clinic" --country GB --count 500 --cap-usd 5 --dry-run
  python3 scrape_ads_library.py --url "https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=GB&q=..." --count 500
Writes data/raw.json (appends, de-duplicated by ad archive id). Each row gets _country and _query.
Ads Library image URLs expire within days: run dedupe.py (which downloads images) straight after.
The actor wants count >= 10. Check the actor's current price per ad on its Apify page.
"""
import argparse, json, os, sys, urllib.parse, urllib.request

ACTOR = 'curious_coder~facebook-ads-library-scraper'
PRICE_PER_AD = 0.00075  # USD, check the actor page; update if it changed


def lib_url(q, country):
    return ('https://www.facebook.com/ads/library/?' + urllib.parse.urlencode(
        {'active_status': 'all', 'ad_type': 'all', 'country': country, 'q': q, 'search_type': 'keyword_unordered', 'media_type': 'all'}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--query', action='append', default=[]); ap.add_argument('--url', action='append', default=[])
    ap.add_argument('--country', default='GB'); ap.add_argument('--count', type=int, default=200)
    ap.add_argument('--cap-usd', type=float, default=5.0); ap.add_argument('--out', default='data/raw.json')
    ap.add_argument('--extra-input', default='{}', help='JSON merged into the actor input')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    urls = a.url + [lib_url(q, a.country) for q in a.query]
    if not urls: sys.exit('give --query or --url')
    count = max(10, a.count)
    est = len(urls) * count * PRICE_PER_AD
    print(f'{len(urls)} search(es) x up to {count} ads = est ${est:.2f} (cap ${a.cap_usd:.2f})')
    if est > a.cap_usd: sys.exit('over the cost cap: lower --count or raise --cap-usd deliberately')
    if a.dry_run: return
    tok = os.environ.get('APIFY_TOKEN') or sys.exit('APIFY_TOKEN not set. Run: set -a; source ~/.claude/skills/.env; set +a')
    rows = json.load(open(a.out)) if os.path.exists(a.out) else []
    seen = {str(r.get('ad_archive_id') or r.get('adArchiveID')) for r in rows}
    for u, q in zip(urls, a.url + a.query):
        body = {'urls': [{'url': u}], 'count': count}; body.update(json.loads(a.extra_input))
        req = urllib.request.Request(f'https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items?token={tok}',
                                     data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'}, method='POST')
        items = json.load(urllib.request.urlopen(req, timeout=900))
        new = 0
        for it in items:
            k = str(it.get('ad_archive_id') or it.get('adArchiveID'))
            if k in seen: continue
            it['_country'] = a.country; it['_query'] = q; rows.append(it); seen.add(k); new += 1
        print(f'{q[:60]}: {len(items)} returned, {new} new')
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(rows, open(a.out, 'w'))
    print(f'{len(rows)} ads in {a.out}. Measure real spend as the change in your Apify monthly usage; per-run usage often reads $0 right after a run.')


if __name__ == '__main__':
    main()
