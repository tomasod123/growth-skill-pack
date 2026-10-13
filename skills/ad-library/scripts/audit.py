#!/usr/bin/env python3
"""Data-quality audit for the ad library. Read-only: it never writes index.jsonl.

Runs every check on demand and exits NON-ZERO when any check fails, so the weekly refresh can
call it and know the library is still sound.

    python3 audit.py                 # every check except the network one
    python3 audit.py --http 40       # also HTTP-check a sample of 40 media/poster urls
    python3 audit.py --json          # machine-readable summary
    python3 audit.py --warn-only     # always exit 0 (report, never block)
    python3 audit.py --video-only    # treat still-image ads as a failure (default: a warning)
"""
import argparse, collections, datetime, json, os, random, re, sys, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import adlib_common as C
try:
    import lib_ids
except Exception:
    lib_ids = None

LIB = C.LIB_DEFAULT

# ---------------------------------------------------------------- controlled vocabularies
# single source of truth: niche_rules.NICHES. Imported rather than copied so the audit can never
# disagree with the gate that wrote the rows.
from niche_rules import NICHES  # noqa: E402

VOCAB = {
    "niche": NICHES,
    "niche_basis": ["ad_content", "transcript", "reviewed", "source_batch", None],
    "client_or_competitor": ["client", "competitor"],
    "format_class": ["talking_head", "silent_broll_text", "voiceover_broll", "testimonial",
                     "text_slides", "organic_reel_cta", "carousel_static", "screen_demo", "unclassified"],
    "format": ["talking_head", "silent_broll_text", "voiceover_broll", "testimonial",
               "text_slides", "organic_reel_cta", "carousel_static", "screen_demo", "unclassified"],
    "format_basis": ["watched", "transcript", "prose", "copy", "probe", "scores-json", "none"],
    "quality_basis": ["watched", "text_only", None],
    "personal_vs_slides": ["personal", "silent", "voiceover", "unknown"],
    "advertiser_type": ["single_site", "multi_site", "chain", "training_provider",
                        "product_brand", "software_vendor", "unknown"],
    "advertiser_type_basis": None,          # free text
    "country_basis": ["ad_field", "search", "ad_copy", "advertiser_copy", "own_client",
                      "batch_label", "none"],
    "tag_basis": ["watched", "transcript", "copy_only", "none", None],
    "offer_type": ["discount_amount", "discount_percent", "free_consultation",
                   "free_treatment_or_taster", "bundle", "membership_or_plan",
                   "finance_payment_plan", "price_led", "competition_giveaway",
                   "demo_booking", "free_trial", "lead_magnet", "free_audit_or_assessment", "none", None],
    "callout_type": ["demographic", "problem", "objection", "location", "none", None],
    "claim_type": ["results_promise", "credential_authority", "technology_novelty",
                   "social_proof", "education_only", "none", None],
    "urgency": ["deadline_date", "limited_places", "seasonal", "none", None],
    "social_proof": ["before_after", "patient_testimonial", "customer_testimonial", "review_count",
                     "customer_logos", "case_study_numbers", "celebrity_or_influencer", "none", None],
    "person_on_camera": ["named_practitioner", "unnamed_staff", "patient", "founder_or_exec",
                         "customer", "model_or_actor", "none", None],
    "setting": ["clinic_treatment_room", "clinic_reception", "office_or_workspace",
                "plain_wall_or_studio", "home_or_car", "outdoor", "screen_recording",
                "graphic_only", None],
    "captions": ["burned_in_full", "burned_in_keywords", "none", None],
    "music": ["none", "bed", "trending_track", None],
    "voice": ["on_camera_speech", "voiceover", "silent", None],
    "landing_type": ["booking_page", "lead_form", "messenger_or_whatsapp", "homepage",
                     "demo_booking", "trial_signup", "content_download", "unknown", None],
}
BOOLS = ["offer_tied", "low_res", "has_audio", "audio_speech", "is_active", "device_is_hero",
         "guarantee", "credentials_shown", "compliance_flag", "replicable_by_small_team",
         "price_shown_is_number"]

PERSONAL = {"talking_head": "personal", "testimonial": "personal", "organic_reel_cta": "personal",
            "silent_broll_text": "silent", "text_slides": "silent", "carousel_static": "silent",
            "voiceover_broll": "voiceover", "screen_demo": "voiceover", "unclassified": "unknown"}

# secrets / tokens that must never reach a row
TOKEN_PATTERNS = [
    ("apify token", r"\bapify_api_[A-Za-z0-9]{20,}"),
    ("supabase key", r"\b(?:sb|sbp)_[A-Za-z0-9]{20,}|\beyJhbGciOi[A-Za-z0-9_\-\.]{40,}"),
    # anchored and hyphen-free after the prefix: a loose \bsk-[A-Za-z0-9_-]{20,} matches ordinary
    # prose like "mask-with-caffeine-and-..." inside ad copy and hashtags (it produced over a hundred false hits)
    ("openai/anthropic key", r"(?<![A-Za-z0-9_\-])sk-(?:ant-)?(?:api\d\d-)?[A-Za-z0-9]{24,}"),
    ("slack token", r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),
    ("ghl pit token", r"\bpit-[0-9a-f\-]{20,}"),
    ("google api key", r"\bAIza[0-9A-Za-z_\-]{30,}"),
    ("aws key id", r"\bAKIA[0-9A-Z]{16}\b"),
    ("bearer header", r"[Aa]uthorization:\s*Bearer\s+\S{16,}"),
    ("private key block", r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]
# personally identifying junk: contact details for a real person, and local filesystem identity
PII_PATTERNS = [
    ("email address", r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    ("home directory path", r"/(?:Users|home)/[A-Za-z0-9._\-]+/"),
]
# fields where a URL or a path legitimately lives, so a path is not junk there
PATH_FIELDS = {"media_path", "poster_path", "transcript_path", "media_url", "poster_url",
               "lib_url", "ad_library_url", "source_scrape"}


def load(lib=LIB):
    C.ensure_library(lib)
    with open(os.path.join(lib, "index.jsonl"), encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def has_artifact(r):
    """Evidence that somebody could actually look at the creative."""
    for k in ("media_path", "poster_path"):
        p = r.get(k)
        if p and os.path.exists(p):
            return True
    if r.get("media_url") or r.get("poster_url"):
        return True
    p = r.get("transcript_path")
    if p and os.path.exists(p):
        return True
    if r.get("frames_dir") or r.get("contact_sheet"):
        return True
    return False


def has_transcript(r):
    p = r.get("transcript_path")
    return bool(p and os.path.exists(p)) or bool(r.get("transcript_text"))


def flat_strings(r):
    """(field, string) for every string anywhere in the row, lists and dicts included."""
    out = []

    def walk(k, v):
        if isinstance(v, str):
            out.append((k, v))
        elif isinstance(v, dict):
            for kk, vv in v.items():
                walk(f"{k}.{kk}", vv)
        elif isinstance(v, list):
            for vv in v:
                walk(k, vv)
    for k, v in r.items():
        walk(k, v)
    return out


# ------------------------------------------------------------------------------- the checks
def run(rows, http_sample=0, seed=20260904, video_only=False):
    R = []          # (check name, [failure strings], severity)

    def add(name, fails, sev="fail"):
        R.append({"check": name, "failures": fails, "count": len(fails), "severity": sev})

    ids = [r.get("id") for r in rows]

    # 1 controlled fields
    f = []
    for r in rows:
        for field, allowed in VOCAB.items():
            if allowed is None or field not in r:
                continue
            v = r.get(field)
            if v not in allowed:
                f.append(f"{r.get('id')}: {field}={v!r}")
    add("controlled fields hold a value from their vocabulary", f)

    # 1b personal_vs_slides must be derived from format_class
    f = [f"{r.get('id')}: format_class={r.get('format_class')} but personal_vs_slides={r.get('personal_vs_slides')}"
         for r in rows if PERSONAL.get(r.get("format_class")) not in (None, r.get("personal_vs_slides"))]
    add("personal_vs_slides matches format_class", f)

    # 1c format mirrors format_class
    f = [f"{r.get('id')}: format={r.get('format')} format_class={r.get('format_class')}"
         for r in rows if r.get("format") != r.get("format_class")]
    add("format mirrors format_class", f)

    # 1d booleans are booleans
    f = [f"{r.get('id')}: {b}={r.get(b)!r}" for r in rows for b in BOOLS
         if b in r and r.get(b) is not None and not isinstance(r.get(b), bool)]
    add("boolean fields hold booleans", f)

    # 1e unclassified / unscored rows must explain themselves
    f = [f"{r.get('id')}: {r.get('format_class')} with empty notes" for r in rows
         if (r.get("format_class") == "unclassified" or r.get("quality_score") is None)
         and not (r.get("notes") or "").strip()]
    add("unclassified or unscored rows carry a reason in notes", f)

    # 2 tag_basis watched needs a frame artefact or a transcript
    f = [f"{r.get('id')}: tag_basis=watched, no media/poster/frames/transcript"
         for r in rows if r.get("tag_basis") == "watched" and not has_artifact(r)]
    add("no row claims tag_basis=watched without a frame artefact or transcript", f)

    # 2b format_basis watched, same test
    f = [f"{r.get('id')}: format_basis=watched, no artefact" for r in rows
         if r.get("format_basis") == "watched" and not has_artifact(r)]
    add("no row claims format_basis=watched without an artefact", f)

    # 2c a copy_only row must not carry on-screen fields it could not have seen
    onscreen = ["person_on_camera", "setting", "captions", "voice", "music", "aspect_ratio"]
    f = [f"{r.get('id')}: tag_basis={r.get('tag_basis')} but {k}={r.get(k)!r}"
         for r in rows if r.get("tag_basis") in ("copy_only", "none")
         for k in onscreen if r.get(k) is not None]
    add("copy_only rows carry no on-screen fields", f)

    # 3 country_iso
    f, w = [], []
    for r in rows:
        cc, basis = r.get("country_iso"), r.get("country_basis")
        if not cc:
            f.append(f"{r.get('id')}: country_iso is null")
            continue
        if not re.fullmatch(r"[A-Z]{2}", str(cc)):
            f.append(f"{r.get('id')}: country_iso={cc!r} is not an ISO-3166 alpha-2 code")
        if r.get("market") != cc:
            f.append(f"{r.get('id')}: market={r.get('market')!r} != country_iso={cc!r}")
        copy_cc, copy_why = C.country_from_copy(" ".join(str(r.get(k) or "") for k in
                                                        ("body_excerpt", "hook", "offer", "cta",
                                                         "format_note", "notes", "lib_url")))
        if copy_cc and copy_cc != cc:
            f.append(f"{r.get('id')}: country_iso={cc} ({basis}) but the ad's own copy says "
                     f"{copy_cc} ({copy_why})")
        if basis == "batch_label":
            w.append(f"{r.get('id')}: country rests on the per-batch --market label only")
    add("country_iso is a real code, matches market, and is not contradicted by the ad copy", f)
    add("rows whose country rests only on the batch label", w, sev="warn")

    # 4 days_running / survival_days_at_last_check
    today = C.today()
    f = []
    for r in rows:
        sd, ed, ls = C.as_date(r.get("start_date")), C.as_date(r.get("end_date")), C.as_date(r.get("last_seen"))
        dr, sv = r.get("days_running"), r.get("survival_days_at_last_check")
        if sd is None:
            if dr is not None or sv is not None:
                f.append(f"{r.get('id')}: no start_date but days_running={dr} survival={sv}")
            continue
        want_dr = ((ed or today) - sd).days
        if dr is not None and dr != want_dr:
            f.append(f"{r.get('id')}: days_running={dr}, start_date->{'end_date' if ed else 'today'} is {want_dr}")
        # canonical (adlib_common.enrich_row): start_date -> end_date if it ended, else last_seen
        if ls is not None or ed is not None:
            want_sv = max(0, ((ed or ls) - sd).days)
            if sv is not None and sv != want_sv:
                f.append(f"{r.get('id')}: survival_days_at_last_check={sv}, start_date->"
                         f"{'end_date' if ed else 'last_seen'} is {want_sv}")
        if sv is not None and dr is not None and sv > dr:
            f.append(f"{r.get('id')}: survival {sv} > days_running {dr}")
        if ls and sd and ls < sd:
            f.append(f"{r.get('id')}: last_seen {r.get('last_seen')} is before start_date {r.get('start_date')}")
    add("days_running and survival_days agree with start_date, end_date and last_seen", f)

    # 5 performance_score recomputes from its own inputs
    f = []
    for r in rows:
        ps = r.get("performance_score")
        if ps is None:
            if not (r.get("performance_basis") or "").strip():
                f.append(f"{r.get('id')}: performance_score null with no performance_basis saying why")
            continue
        want = C.performance(r.get("survival_days_at_last_check"), r.get("is_active"),
                             r.get("variant_count"), r.get("platforms"),
                             r.get("relaunch_count"), r.get("advertiser_ads_live"))
        got = want[0] if isinstance(want, tuple) else want
        if got != ps:
            f.append(f"{r.get('id')}: performance_score={ps}, recomputes to {got}")
    add("performance_score recomputes from its own inputs", f)

    # 6 scores have a basis
    f = [f"{r.get('id')}: quality_score={r.get('quality_score')} with quality_basis={r.get('quality_basis')!r}"
         for r in rows if (r.get("quality_score") is None) != (r.get("quality_basis") is None)]
    f += [f"{r.get('id')}: quality_score={r.get('quality_score')} out of 1-5" for r in rows
          if r.get("quality_score") is not None and not (1 <= r["quality_score"] <= 5)]
    f += [f"{r.get('id')}: fit_score={r.get('fit_score')!r}" for r in rows
          if r.get("fit_score") is not None and not (1 <= r["fit_score"] <= 5)]
    f += [f"{r.get('id')}: fit_score is null" for r in rows if r.get("fit_score") is None]
    add("quality_score and fit_score are in range and have a basis", f)

    # 7 duplicates. A shared primary text is NOT a duplicate — advertisers reuse the same body
    # across different videos — so the same-creative test also needs the same runtime and frame size.
    f, w2 = [], []
    dup_id = [i for i, n in collections.Counter(ids).items() if n > 1]
    f += [f"duplicate row id {i}" for i in dup_id]
    dup_ad = collections.defaultdict(list)
    for r in rows:
        if r.get("ad_id"):
            dup_ad[str(r["ad_id"])].append(r.get("id"))
    f += [f"the same Meta ad_id {a} is stored under {len(v)} rows: {v}" for a, v in dup_ad.items()
          if len(v) > 1]

    def body_key(r):
        b = re.sub(r"\{\{[^}]+\}\}", "", re.sub(r"\s+", " ", (r.get("body_excerpt") or "")).strip().lower())
        return b[:180] if len(b) >= 40 else None

    same_creative, same_body = collections.defaultdict(list), collections.defaultdict(list)
    for r in rows:
        page = str(r.get("page_id") or r.get("advertiser") or "").lower()
        b = body_key(r)
        if not b:
            continue
        same_body[(page, b)].append(r.get("id"))
        d, w_, h_ = r.get("duration_s"), r.get("width"), r.get("height")
        if d and w_ and h_:
            same_creative[(page, b, round(float(d), 1), w_, h_)].append(r.get("id"))
    for k, v in same_creative.items():
        if len(v) > 1:
            f.append(f"one advertiser, the same creative (same body, {k[2]}s, {k[3]}x{k[4]}) under "
                     f"{len(v)} ad ids: {v}")
    dupset = {i for v in same_creative.values() if len(v) > 1 for i in v}
    for k, v in same_body.items():
        if len(v) > 1 and not set(v) <= dupset:
            w2.append(f"one advertiser reuses the same primary text across {len(v)} different "
                      f"videos (not a duplicate): {v}")
    add("no duplicate ads under different ids", f)
    add("advertisers reusing one primary text across different videos", w2, sev="warn")

    # 8 no still images
    f = []
    for r in rows:
        why = []
        if r.get("display_format") in ("IMAGE", "PHOTO"):
            why.append(f"display_format={r.get('display_format')}")
        if r.get("format_class") == "carousel_static" and not r.get("duration_s"):
            why.append("carousel_static with no duration")
        d = r.get("duration_s")
        if d is not None and d <= 0:
            why.append(f"duration_s={d}")
        if why:
            f.append(f"{r.get('id')}: " + ", ".join(why))
    # The library started as video-only. Still-image ads are real ads too and the refresh pulls
    # them, so by default they are a WARNING (filter on display_format if you want video only).
    # --video-only makes them a hard failure, which then blocks any downstream step.
    add("no still-image ads", f, sev="fail" if video_only else "warn")

    # 8b aspect_ratio agrees with width/height
    f = []
    for r in rows:
        w_, h_ = r.get("width"), r.get("height")
        ar = r.get("aspect_ratio")
        if not (w_ and h_ and ar and ":" in str(ar)):
            continue
        a, b = str(ar).split(":")
        try:
            if abs((int(a) / int(b)) - (w_ / h_)) > 0.06:
                f.append(f"{r.get('id')}: aspect_ratio={ar} but {w_}x{h_}")
        except (ValueError, ZeroDivisionError):
            f.append(f"{r.get('id')}: aspect_ratio={ar!r} unparseable")
    add("aspect_ratio agrees with width and height", f)

    # 9 tokens and PII
    f = []
    for r in rows:
        for field, s in flat_strings(r):
            for label, pat in TOKEN_PATTERNS:
                if re.search(pat, s):
                    f.append(f"{r.get('id')}: {label} in {field}")
            for label, pat in PII_PATTERNS:
                if field.split(".")[0] in PATH_FIELDS:
                    continue
                m = re.search(pat, s)
                if m:
                    f.append(f"{r.get('id')}: {label} in {field}: {m.group(0)[:60]}")
    add("no tokens, credentials or personally identifying junk in any field", f)

    # 10 compliance gate (rule 6 of SKILL.md)
    f = [f"{r.get('id')}: compliance_flag but notes do not say compliance-flagged" for r in rows
         if r.get("compliance_flag") and "compliance-flagged" not in (r.get("notes") or "")]
    add("every compliance_flag row carries 'compliance-flagged' in notes", f)

    # 11 network: media and poster urls resolve
    if http_sample:
        cands = []
        for r in rows:
            for k in ("media_url", "poster_url"):
                u = r.get(k)
                if u and str(u).startswith("http"):
                    cands.append((r.get("id"), k, u))
            if lib_ids:
                for kind, label in (("media_path", "media_url"), ("poster_path", "poster_url")):
                    if r.get(label):
                        continue
                    try:
                        u = lib_ids.media_url(r, kind)
                    except Exception:
                        u = None
                    if u and str(u).startswith("http"):
                        cands.append((r.get("id"), label + "(derived)", u))
        random.Random(seed).shuffle(cands)
        pick = cands[:http_sample]
        bad = []
        for rid, k, u in pick:
          last = None
          for attempt in (1, 2):          # one retry: small static servers drop the odd request under a burst
            try:
                # a RANGED GET, not HEAD: some static file servers stall on HEAD for larger mp4s
                # while the file itself serves instantly
                req = urllib.request.Request(u, headers={"Range": "bytes=0-2047"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    code = resp.status
                    body = resp.read(2048)
                if code >= 400 or not body:
                    last = f"{rid}: {k} HTTP {code} first-bytes={len(body)} {u}"
                else:
                    last = None
            except urllib.error.HTTPError as e:
                last = f"{rid}: {k} HTTP {e.code} {u}"
            except Exception as e:
                last = f"{rid}: {k} {type(e).__name__}: {e} {u}"
            if last is None:
                break
          if last:
            bad.append(last)
        R.append({"check": f"media and poster urls resolve (sampled {len(pick)} of {len(cands)})",
                  "failures": bad, "count": len(bad),
                  "severity": "fail", "sampled": len(pick), "pool": len(cands)})

    # 12 local media paths that are recorded but missing
    f = [f"{r.get('id')}: {k} recorded but the file is gone: {r.get(k)}" for r in rows
         for k in ("media_path", "poster_path", "transcript_path")
         if r.get(k) and not os.path.exists(r.get(k))]
    add("recorded local media, poster and transcript paths exist on disk", f, sev="warn")

    return R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=LIB)
    ap.add_argument("--http", type=int, default=0, help="HTTP-check this many media/poster urls")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--warn-only", action="store_true", help="always exit 0")
    ap.add_argument("--max-print", type=int, default=12)
    ap.add_argument("--video-only", action="store_true", help="still-image ads are a failure, not a warning")
    a = ap.parse_args()

    rows = load(a.lib)
    res = run(rows, http_sample=a.http, video_only=a.video_only)
    hard = sum(r["count"] for r in res if r["severity"] == "fail")
    if a.json:
        print(json.dumps({"rows": len(rows), "checks": res, "failures": hard}, indent=2))
    else:
        print(f"ad-library audit · {len(rows)} rows · {datetime.date.today()}\n")
        for r in res:
            mark = "ok  " if r["count"] == 0 else ("WARN" if r["severity"] == "warn" else "FAIL")
            print(f"[{mark}] {r['check']}" + (f"  ({r['count']})" if r["count"] else ""))
            for line in r["failures"][:a.max_print]:
                print(f"        {line}")
            if r["count"] > a.max_print:
                print(f"        ... and {r['count'] - a.max_print} more")
        print(f"\n{hard} hard failure(s)")
    return 0 if (a.warn_only or hard == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
