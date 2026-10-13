#!/usr/bin/env python3
"""Parallel renderer for OpenAI gpt-image models (default gpt-image-2).

Run from the project folder (the one holding data/concepts_final.json and data/families.json):
  set -a; source ~/.claude/skills/.env; set +a
  python3 render.py --aspect square   --out renders        [--ids-file ids.txt] [--variants a]
  python3 render.py --aspect vertical --out renders_vert   (2:3, 4:5 is cut from it by make_ratios.py)
  python3 render.py --aspect story    --out renders_story  (native 9:16, checked by make_story.py)
  python3 render.py --aspect fourfive --out renders_45     (native 4:5)

Concepts with needs_asset == "person_photo" are rendered with images.edit using the reference
photos in --ref (comma list, 4-6 crops of the SAME person from different angles works best) and
the person brief in --person-brief (a text file describing look, wardrobe, role; see
templates/person-brief.example.txt).

Existing output files are skipped, so a concept edited AFTER its first render keeps its stale
image: delete that file (or use --force) to re-render.
"""
import os, sys, json, base64, argparse, pathlib, time, threading, re
import concurrent.futures as cf

NEG = ("Do not add any text that is not listed. Do not invent extra words, logos, watermarks, badges, captions or numbers. "
       "Spelling must be exactly as written. Avoid the generic AI-ad look: warm cream backgrounds with serif display type and "
       "terracotta accents, pastel pill tags, floating rounded drop-shadow cards, three-column icon grids, emoji, and a centred "
       "stock-agency layout. ")
MARGIN = (" LAYOUT LAW, APPLIES TO EVERY IMAGE: the headline must be LARGE enough to read on a phone at thumbnail size, and it must "
          "also have a clear, even margin on all four sides. No text may touch or crowd an edge. Never solve a long headline by "
          "shrinking the type into a small line floating in a big empty field, and never by pushing the type out to the edges. "
          "If the words do not fit at a large size with margins, use fewer words, not smaller type. Text must never sit on top of a "
          "busy or dark part of a photograph where it loses contrast. ")
VAR = {'a': "Art direction variant A: bolder and more graphic. Push contrast and scale, let the headline dominate the canvas.",
       'b': "Art direction variant B: quieter and more editorial. More negative space, calmer palette, the same words in the same positions."}
PERSON_BASE = (
    "SEVERAL reference photographs of the SAME person are supplied, taken from different angles and in different light. "
    "They are all one individual, not several people. Study them together to build the likeness, then render exactly ONE of them in "
    "this advert. Never place a second person, a reflection or a duplicate anywhere in the frame. "
    "FACE FIDELITY IS THE HIGHEST PRIORITY. Keep the face clearly recognisable; do not age them, do not slim or widen the face, do not "
    "change eye colour or bone structure. PHOTOREALISM IS NON NEGOTIABLE: a real photograph on a real camera, true skin texture, natural "
    "micro-shadow, real depth of field; never illustrated, airbrushed, waxy, plastic, CGI or AI-looking. "
    "Expression: warm and engaged, eyes open and bright, looking down the lens; never tired, glazed, smug or unsettling. "
    "Teeth natural and correctly sized; eyes level, the same size, looking the same way. "
    "Lighting: soft key light slightly above eye level with gentle fill, no harsh shadow under eyes, nose or chin. "
    "Clothing pressed and well fitted, plain and unbranded: no logo, embroidery, badge or lettering on any garment. "
    "IF THE ART DIRECTION BELOW NAMES A SPECIFIC GARMENT, FOLLOW IT; otherwise use the wardrobe in the person brief. "
    "If the face is small in the composition, give it MORE detail, not less. ")
ASPECT = ['square']
FAMD = {}


def _strip_ratio(p):
    """Concept plans often open with '1:1.' / '4:5.' / '9:16.'; that fights an explicit size."""
    return re.sub(r'^\s*\d+\s*:\s*\d+\s*\.?\s*', '', p or '')


def prompt_for(c, v):
    fam = FAMD.get(c.get('family_id'), {})
    texts = [c.get('headline_on_image')] + list(c.get('other_text_on_image') or [])
    texts = [t for t in texts if t]
    if texts:
        ts = ("The ONLY text on the image, exactly as written: " + " | ".join(f'"{t}"' for t in texts) +
              f". That is {len(texts)} text element(s) in total and there must be no others. ")
    else:
        ts = "There must be NO text anywhere on the image. No words, no logo, no caption, no watermark. "
    if ASPECT[0] == 'story':
        pre = ("A 9:16 VERTICAL advertising image for Instagram and Facebook STORIES and REELS, full screen on a phone. "
               "STORIES SAFE AREA LAW: the phone's own interface sits ON TOP of this picture: profile photo, account name and close "
               "button cover the TOP 14 PER CENT, and the reply bar and call-to-action sticker cover the BOTTOM 20 PER CENT. "
               "Background and photography may run full bleed. But EVERY PIECE OF TYPE, every logo, every badge and ESPECIALLY THE CALL "
               "TO ACTION must sit inside the CENTRAL 66 PER CENT of the height. The call to action is the lowest element and finishes "
               "by 78 per cent from the top. NEVER pin it to the bottom edge or run it as a full-width base bar. Keep heads fully inside "
               "the safe area. Compose a true full-screen story; do NOT letterbox a square or float a card in a tall box. ")
    elif ASPECT[0] == 'vertical':
        pre = ("A TALL VERTICAL 2:3 advertising image for Instagram and Facebook feed and stories. SAFE BAND LAW: all type, logos and "
               "subjects sit inside the CENTRAL 76 PER CENT of the height. The top 12 per cent and bottom 12 per cent are COMPLETELY "
               "EMPTY FLAT BACKGROUND of one solid colour, because the image is later cropped or extended from those bands. Compose for a "
               "tall frame: stack the elements vertically, do not letterbox a square. ")
    elif ASPECT[0] == 'fourfive':
        pre = "A 4:5 portrait advertising image for the Instagram and Facebook feed. "
    else:
        pre = "A square 1:1 advertising image for Instagram and Facebook. "
    plan = (c.get('image_plan_vert') if ASPECT[0] in ('vertical', 'story') else None) or c.get('image_plan', '')
    return (pre + f"Layout recipe: {fam.get('recipe', '')} Art direction for this specific ad: {_strip_ratio(plan)} "
            f"{VAR[v]} {ts}{MARGIN}{NEG}")


lock = threading.Lock(); done = [0]


def render(args):
    c, v, a, cl, person = args
    fn = f"{a.out}/{c['concept_id']}{v}_{c.get('family_id', 'F00')}.png"
    if os.path.exists(fn) and not a.force:
        return dict(id=c['concept_id'] + v, skip=True)
    p = prompt_for(c, v); t0 = time.time()
    refs = [x for x in (a.ref or '').split(',') if x and os.path.exists(x)]
    for attempt in range(3):
        try:
            if c.get('needs_asset') == 'person_photo' and refs:
                fh = [open(x, 'rb') for x in refs]
                try:
                    r = cl.images.edit(model=a.model, image=(fh if len(fh) > 1 else fh[0]),
                                       prompt=PERSON_BASE + person + " " + p, size=a.size, quality=a.quality)
                finally:
                    for h in fh: h.close()
            else:
                r = cl.images.generate(model=a.model, prompt=p, size=a.size, quality=a.quality)
            open(fn, 'wb').write(base64.b64decode(r.data[0].b64_json))
            u = getattr(r, 'usage', None)
            with lock:
                done[0] += 1; print(f"[{done[0]}] ok {c['concept_id']}{v} {round(time.time() - t0, 1)}s", flush=True)
            return dict(id=c['concept_id'] + v, file=fn, tokens=(u.total_tokens if u else None), secs=round(time.time() - t0, 1))
        except Exception as e:
            msg = str(e)[:200]
            if 'insufficient_quota' in msg or 'billing' in msg.lower():
                with lock: print(f"FAIL {c['concept_id']}{v}: out of credit, not retrying: {msg}", flush=True)
                return dict(id=c['concept_id'] + v, error=msg)
            if attempt == 2:
                with lock: print(f"FAIL {c['concept_id']}{v}: {msg}", flush=True)
                return dict(id=c['concept_id'] + v, error=msg)
            time.sleep(8 * (attempt + 1) if ('rate' in msg.lower() or '429' in msg) else 3)
    return dict(id=c['concept_id'] + v, error='retries exhausted')  # never return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quality', default='medium'); ap.add_argument('--size', default='1024x1024')
    ap.add_argument('--model', default='gpt-image-2'); ap.add_argument('--out', default='renders')
    ap.add_argument('--ref', default='', help='comma list of reference photos for person_photo concepts')
    ap.add_argument('--person-brief', help='text file describing the person (look, wardrobe, role)')
    ap.add_argument('--workers', type=int, default=5)
    ap.add_argument('--variants', default='a'); ap.add_argument('--src', default='data/concepts_final.json')
    ap.add_argument('--families', default='data/families.json')
    ap.add_argument('--ids', nargs='*'); ap.add_argument('--ids-file')
    ap.add_argument('--aspect', default='square', choices=['square', 'vertical', 'story', 'fourfive'])
    ap.add_argument('--force', action='store_true', help='re-render even if the file exists')
    ap.add_argument('--dry-run', action='store_true', help='print the first prompt and the job count, no API call')
    a = ap.parse_args()
    ASPECT[0] = a.aspect
    if a.size == '1024x1024':
        # gpt-image-2: both sides divisible by 16. 1024x1280 is exactly 4:5, 1152x2048 exactly 9:16.
        a.size = {'vertical': '1024x1536', 'story': '1152x2048', 'fourfive': '1024x1280'}.get(a.aspect, a.size)
    if os.path.exists(a.families):
        FAMD.update({f['family_id']: f for f in json.load(open(a.families))})
    person = open(a.person_brief).read().strip() if a.person_brief else ''
    cs = json.load(open(a.src))
    ids = set(a.ids or [])
    if a.ids_file: ids |= set(open(a.ids_file).read().split())
    if ids: cs = [c for c in cs if c['concept_id'] in ids]
    jobs_spec = [(c, v) for c in cs for v in a.variants]
    print(f"{len(jobs_spec)} renders, {a.workers} workers, model {a.model} quality {a.quality} size {a.size}", flush=True)
    if a.dry_run:
        if jobs_spec: print(prompt_for(*jobs_spec[0]))
        return
    if not os.environ.get('OPENAI_API_KEY'):
        sys.exit('OPENAI_API_KEY not set. Run: set -a; source ~/.claude/skills/.env; set +a')
    from openai import OpenAI; cl = OpenAI()
    pathlib.Path(a.out).mkdir(parents=True, exist_ok=True)
    jobs = [(c, v, a, cl, person) for c, v in jobs_spec]
    t0 = time.time(); res = []
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for r in ex.map(render, jobs): res.append(r or dict(id='?', error='none returned'))
    ok = [r for r in res if r.get('file')]; fail = [r for r in res if r.get('error')]; sk = [r for r in res if r.get('skip')]
    tok = sum(r.get('tokens') or 0 for r in ok)
    lp = f'{a.out}/_log.json'
    old = json.load(open(lp)) if os.path.exists(lp) else []
    json.dump(old + [r for r in res if not r.get('skip')], open(lp, 'w'), indent=1)
    print(f"\ndone in {round((time.time() - t0) / 60, 1)} min | ok {len(ok)} | failed {len(fail)} | skipped {len(sk)} | "
          f"tokens {tok} | est ${round(tok * 30 / 1e6, 2)} at $30 per 1M image output tokens (check current pricing)")
    if fail: print('failures:', [r['id'] for r in fail][:20])


if __name__ == '__main__':
    main()
