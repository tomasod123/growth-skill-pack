#!/usr/bin/env python3
"""Mechanical QC of the concept file before anything is rendered.

Checks only AD-FACING fields (headline_on_image, other_text_on_image, primary_text, fb_headline, image_plan):
  - banned claims (regex per line in --blacklist, e.g. numbers you cannot substantiate, invented stats)
  - em / en dashes
  - wrong-locale terms (--locale uk flags US words, --locale us flags UK words)
  - sourcing instructions that must go to a human, never to the image model
  - banned garments / props named in image_plan (they beat the renderer's global ban)
  - missing keys, text_lines over the cap, Facebook headline length, primary text word count
  - duplicate ids and duplicate headlines
  python3 qc_concepts.py [--src data/concepts_final.json] [--blacklist data/claims_blacklist.txt] [--locale uk] [--max-text-lines 5]
Exit code 1 if any problem.
"""
import argparse, collections, json, re, sys

SPEC = ['concept_id', 'family_id', 'headline_on_image', 'other_text_on_image', 'text_lines', 'image_plan',
        'needs_asset', 'primary_text', 'fb_headline', 'reference_ad_id', 'reason_to_buy', 'why_this_should_work', 'risk']
LOCALE = {'uk': [r'\bmed ?spa\b', r'\bcalendar\b', r'\bcolor\b', r'\bcenter\b', r'\boptimiz', r'\bpractice owner'],
          'us': [r'\bcolour\b', r'\bcentre\b', r'\boptimis', r'\bdiary\b']}
SOURCING = r'SOURCING INSTRUCTION|real screenshot|cleared client|redact|find the real'
GARMENTS = r'\b(polo|scrubs|lab coat|tunic|gloves|mask|hoodie|branded)\b'
FACING = ['headline_on_image', 'other_text_on_image', 'primary_text', 'fb_headline', 'image_plan']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default='data/concepts_final.json'); ap.add_argument('--blacklist')
    ap.add_argument('--locale', default='uk', choices=['uk', 'us', 'none'])
    ap.add_argument('--max-text-lines', type=int, default=5)
    ap.add_argument('--fb-headline-max', type=int, default=40)
    ap.add_argument('--body-words', default='30,160', help='min,max words of primary text')
    ap.add_argument('--banned-garments', default=GARMENTS)
    a = ap.parse_args()
    banned = [l.strip() for l in open(a.blacklist) if l.strip() and not l.startswith('#')] if a.blacklist else []
    lo, hi = (int(x) for x in a.body_words.split(','))
    cs = json.load(open(a.src)); P = []
    for c in cs:
        cid = c.get('concept_id', '?')
        blob = ' '.join(str(c.get(k) or '') for k in FACING)
        for b in banned:
            if re.search(b, blob, re.I): P.append((cid, 'BANNED_CLAIM', b))
        if '—' in blob or '–' in blob: P.append((cid, 'DASH', ''))
        for u in LOCALE.get(a.locale, []):
            m = re.search(u, blob, re.I)
            if m: P.append((cid, 'LOCALE_TERM', m.group(0)))
        if re.search(SOURCING, str(c.get('image_plan') or ''), re.I):
            P.append((cid, 'SOURCING_NOT_RENDERABLE', 'route to a human; the model will invent the "real" thing'))
        m = re.search(a.banned_garments, str(c.get('image_plan') or ''), re.I)
        if m and c.get('needs_asset') == 'person_photo': P.append((cid, 'BANNED_GARMENT_IN_PLAN', m.group(0)))
        miss = [k for k in SPEC if k not in c]
        if miss: P.append((cid, 'MISSING_KEYS', ','.join(miss)))
        tl = c.get('text_lines')
        if not isinstance(tl, int) or tl > a.max_text_lines: P.append((cid, 'TEXT_LINES', str(tl)))
        if len(c.get('fb_headline') or '') > a.fb_headline_max: P.append((cid, 'FB_HEADLINE_LEN', str(len(c['fb_headline']))))
        w = len((c.get('primary_text') or '').split())
        if w < lo or w > hi: P.append((cid, 'BODY_WORDS', str(w)))
    ids = [c.get('concept_id') for c in cs]
    for k, v in collections.Counter(ids).items():
        if v > 1: P.append((k, 'DUPLICATE_ID', str(v)))
    hl = collections.defaultdict(list)
    for c in cs: hl[re.sub(r'[^a-z0-9 ]', '', (c.get('headline_on_image') or '').lower()).strip()].append(c.get('concept_id'))
    for k, v in hl.items():
        if k and len(v) > 1: P.append(('-', 'DUPLICATE_HEADLINE', f"{k[:40]} = {','.join(map(str, v))}"))
    print(f"concepts: {len(cs)}")
    print('by family:', collections.Counter(c.get('family_id') for c in cs).most_common(12))
    print('text_lines:', sorted(collections.Counter(c.get('text_lines') for c in cs if isinstance(c.get('text_lines'), int)).items()))
    print('reasons to buy:', len({c.get('reason_to_buy') for c in cs if c.get('reason_to_buy')}))
    print(f"\nPROBLEMS: {len(P)}")
    for p in P[:80]: print('  ', ' | '.join(str(x) for x in p))
    sys.exit(1 if P else 0)


if __name__ == '__main__':
    main()
