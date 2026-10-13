#!/usr/bin/env python3
"""Rank the APPROVED ads into an honest launch order, with diversity caps, and write data/launch_order.json.

Score per ad: structure longevity (its family's median days running in the competitor data),
text-load penalty, hook type, ICP fit, proof. Then caps per painpoint (reason to buy) and per style
so one angle cannot fill the launch tier (post-Andromeda: diversity = different reasons to buy).

  python3 rank_approved.py --review data/review.xlsx [--config ../config/ranking.json] \
      [--concepts data/concepts_final.json] [--families data/families.json] [--on-hold A07,B12] [--removed C03]
The review file needs columns ID (e.g. A01a) and Approve (Approve / Reject / Maybe).
"""
import argparse, collections, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adkit_common import load_review, variant_of

DEF = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config', 'ranking.example.json')))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--review', required=True); ap.add_argument('--config')
    ap.add_argument('--concepts', default='data/concepts_final.json'); ap.add_argument('--families', default='data/families.json')
    ap.add_argument('--on-hold', default=''); ap.add_argument('--removed', default='')
    ap.add_argument('--out', default='data/launch_order.json')
    a = ap.parse_args()
    W = dict(DEF); W.update(json.load(open(a.config)) if a.config else {})
    cs = {c['concept_id']: c for c in json.load(open(a.concepts))}
    fams = {f['family_id']: f for f in json.load(open(a.families))} if os.path.exists(a.families) else {}
    hold = set(x for x in a.on_hold.split(',') if x); removed = set(x for x in a.removed.split(',') if x)
    app = [r for r in load_review(a.review) if str(r.get('Approve') or '').strip().lower() == 'approve']

    def hook_bonus(c):
        h = (c.get('headline_on_image') or '') + ' ' + ' '.join(c.get('other_text_on_image') or [])
        b = W['question_hook_bonus'] if '?' in h else 0
        if re.search(r'[£$€]\s?\d|\d{2,}k|\d+%', h): b += W['big_number_hook_penalty']
        if re.search(r'\bnot\b|\bstop\b|\bnobody\b|\bnever\b', h, re.I): b += W['contrarian_word_bonus']
        return b

    scored = []
    for r in app:
        v = variant_of(r)
        if not v: print('SKIP no id:', r); continue
        cid = v[:-1]
        if cid in removed or cid not in cs: continue
        c = cs[cid]; fam = fams.get(c.get('family_id'), {})
        med = fam.get('median_days') or 20; tl = c.get('text_lines')
        s = min(med, W['days_cap']) * W['days_weight']
        s += W['text_penalty'].get(str(tl), W['text_penalty_over'])
        s += hook_bonus(c)
        fit = fam.get('fit') or c.get('fit')
        s += W['fit_high_bonus'] if fit == 'high' else (W['fit_low_penalty'] if fit == 'low' else 0)
        pain = c.get('painpoint') or c.get('reason_to_buy') or 'GENERAL'
        if str(pain).upper() == 'PROOF': s += W['proof_bonus']
        if cid in hold: s += W['on_hold_penalty']
        why = [f"structure ran {med}d median in competitor data", f"{tl} text element(s)"]
        if '?' in (c.get('headline_on_image') or ''): why.append('question hook')
        if cid in hold: why.append('FLAGGED: argued against in review')
        scored.append(dict(variant=v, cid=cid, score=round(s, 1), painpoint=pain, style=c.get('style', 'other'),
                           family=c.get('family_id'), text_lines=tl, median_days=med,
                           headline=c.get('headline_on_image') or '(no text)', fb_headline=c.get('fb_headline') or '',
                           primary=c.get('primary_text') or '', why=' / '.join(why), flagged=cid in hold))
    scored.sort(key=lambda r: -r['score'])
    pc, sc, launch, rest = collections.Counter(), collections.Counter(), [], []
    for r in scored:
        if len(launch) < W['launch_n'] and pc[r['painpoint']] < W['max_per_painpoint'] and sc[r['style']] < W['max_per_style']:
            pc[r['painpoint']] += 1; sc[r['style']] += 1; launch.append(r)
        else:
            rest.append(r)
    while len(launch) < W['launch_n'] and rest:
        launch.append(rest.pop(0))
    out = launch + rest
    for i, r in enumerate(out, 1):
        r['rank'] = i; r['tier'] = 'LAUNCH' if i <= W['launch_n'] else 'BACKLOG'
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, 'w'), indent=1, ensure_ascii=False)
    print(f"{len(out)} ranked | launch {sum(r['tier'] == 'LAUNCH' for r in out)} | backlog {sum(r['tier'] == 'BACKLOG' for r in out)}")
    print('launch painpoint spread:', dict(pc)); print('launch style spread:', dict(sc))
    for r in out[:15]:
        print(f"  {r['rank']:>2}. {r['variant']:<6} {r['score']:>5}  {str(r['painpoint'])[:10]:<10} {r['text_lines']}el  {r['headline'][:44]}")


if __name__ == '__main__':
    main()
