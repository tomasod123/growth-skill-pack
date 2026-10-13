#!/usr/bin/env python3
"""OCR every render and flag anything that looks like a phone number (6+ digits that are not a money figure).

Backstop for retouching: a client photo shot outside their premises can carry a phone number, signage
or a third party's branding. Retouch the master, then PROVE it here rather than trusting the retouch.

  python3 phone_sweep.py <dir or files...> [--known "5551234567"] [--out work/phone_sweep.json]
Needs tesseract. Exit code 1 if anything is flagged.
"""
import argparse, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

PHONE = re.compile(r'(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(?0?\d{1,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}(?!\w)')
MONEY = '£$€'


def ocr(f):
    try:
        return f, subprocess.run(['tesseract', f, 'stdout', '--psm', '11'], capture_output=True, text=True, timeout=90).stdout
    except Exception as e:
        return f, f'__ERR__{e}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='+'); ap.add_argument('--known', default='', help='comma list of digit strings that must never appear')
    ap.add_argument('--out', default='work/phone_sweep.json')
    a = ap.parse_args()
    files = []
    for p in a.paths:
        files += [os.path.join(p, x) for x in sorted(os.listdir(p)) if x.lower().endswith(('.png', '.jpg', '.jpeg'))] if os.path.isdir(p) else [p]
    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(ocr, files))
    known = [re.sub(r'\D', '', k) for k in a.known.split(',') if k.strip()]
    hits, errs = [], []
    for f, txt in res:
        if txt.startswith('__ERR__'): errs.append((f, txt)); continue
        flat = ' '.join(txt.split()); digits_all = re.sub(r'\D', '', flat)
        for m in PHONE.finditer(flat):
            d = re.sub(r'\D', '', m.group(0))
            if len(d) < 6: continue
            if any(ch in flat[max(0, m.start() - 2):m.start() + 1] for ch in MONEY): continue
            hits.append({'file': os.path.basename(f), 'match': m.group(0), 'context': flat[max(0, m.start() - 40):m.start() + 40]})
        for k in known:
            if k and k in digits_all:
                hits.append({'file': os.path.basename(f), 'match': k, 'context': 'KNOWN NUMBER'})
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump({'hits': hits, 'errors': errs, 'scanned': len(res)}, open(a.out, 'w'), indent=1)
    print(f'scanned {len(res)} | OCR errors {len(errs)} | PHONE-LIKE HITS {len(hits)}')
    for h in hits: print(f"  {h['file']}  {h['match']!r}  ...{h['context']}...")
    sys.exit(1 if hits else 0)


if __name__ == '__main__':
    main()
