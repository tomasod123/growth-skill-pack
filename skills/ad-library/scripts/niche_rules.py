# -*- coding: utf-8 -*-
"""Controlled niche vocabulary + the classifier that assigns it from the ad's own words.
Imported by ingest.py, refresh.py and audit.py, so the gate that writes rows and the audit that
checks them can never disagree.

Twelve niches, three families:

  clinical (patient-facing providers)
    skin · injectables · body-contouring · hair-and-tattoo-removal · hair-restoration · dental ·
    cosmetic-surgery · medical-wellness

  software (sold to a business)
    healthcare-software   SaaS, AI tools, platforms and apps sold to clinics, practices,
                          hospitals, health systems or clinicians (scribes, intake, scheduling,
                          RCM/billing, EHR add-ons, patient engagement, clinical AI)
    b2b-software          any other SaaS / platform sold to a business buyer

  services sold to businesses, and trades
    agency-to-smb         an agency, lead marketplace, web-build shop or coaching business selling
                          leads, marketing, websites or training TO small-business owners
                          (tradespeople, contractors, clinic owners)
    trades-home-services  a trade or home-services business advertising its OWN work to a
                          homeowner: plumbing, heating, electrical, roofing, landscaping, building

Add your own niche by appending to NICHES, PATTERNS and ORDER together (and re-run audit.py)."""
import re

NICHES = [
    "skin",
    "injectables",
    "body-contouring",
    "hair-and-tattoo-removal",
    "hair-restoration",
    "dental",
    "cosmetic-surgery",
    "medical-wellness",
    "healthcare-software",
    "b2b-software",
    "trades-home-services",
    "agency-to-smb",
]

# the eight clinical niches, kept separate so a caller can ask for "clinic rows only" without
# hard-coding the list again
CLINICAL_NICHES = NICHES[:8]
SOFTWARE_NICHES = ["healthcare-software", "b2b-software"]
NON_CLINICAL_NICHES = NICHES[8:]

# software signals: a product a business buys, not a treatment a patient books
RE_SOFTWARE = re.compile(
    r"\bsaas\b|\bsoftware\b|\bplatform\b|\bbook a (free )?demo\b|\brequest a demo\b|\bfree demo\b|"
    r"\bget a demo\b|\bfree trial\b|\bstart (your )?free\b|\bintegrat(es|ion|ions) with\b|\bapi\b|"
    r"\b(ehr|emr|pms)\b|\bpractice management (software|system)\b|\bai (scribe|assistant|agent|"
    r"receptionist|notes?)\b|\bambient (ai|documentation)\b|\bdashboard\b|\bhipaa[- ]compliant\b|"
    r"\bsoc ?2\b|\bworkflow automation\b|\bno[- ]code\b|\bper (user|seat|provider) per month\b", re.I)
# who the software is sold to, when it is healthcare
RE_HEALTH_BUYER = re.compile(
    r"\bclinic(s|ians?)?\b|\bpractices?\b|\bproviders?\b|\bphysicians?\b|\bdoctors?\b|\bnurses?\b|"
    r"\bhospitals?\b|\bhealth ?systems?\b|\bpatients?\b|\bcharting\b|\bclinical\b|\bmedical\b|"
    r"\bdental\b|\bmed ?spas?\b|\bhealthcare\b|\bhipaa\b|\brcm\b|\bprior auth", re.I)


def sells_software(text):
    """(True, niche, [what fired]) when the ad sells software/SaaS to a business. Needs TWO distinct
    software signals so a clinic that merely says "book online on our platform" stays a clinic."""
    hits = sorted({m.group(0).strip().lower() for m in RE_SOFTWARE.finditer(text or "")})
    if len(hits) < 2:
        return False, None, []
    niche = "healthcare-software" if RE_HEALTH_BUYER.search(text or "") else "b2b-software"
    return True, niche, hits[:4]


# matched against the ad's OWN text: offer + hook + body + transcript + format_note + device_shown
PATTERNS = [
    ("cosmetic-surgery", r"rhinoplast|face ?lift in turkey|surgical facelift(?! needed)|\bbbl\b|lipo ?360|liposuction|breast (aug|lift)|tummy tuck|abdominoplast|blepharoplast|plastic surge|\bsientra\b|neck lift in turkey|under the knife\b(?=.{0,60}book)|face & neck lift in turkey|facial plastic surgeon"),
    ("hair-restoration", r"hair loss|hair restoration|hair regrowth|thinning hair|receding hairline|alopecia|hair transplant|\bpdgf\b.{0,40}hair|scalp"),
    ("dental", r"\bdentist|dental|invisalign|veneer|denture|orthodont|\btooth\b|\bteeth\b|implant-supported|all-on-4"),
    ("hair-and-tattoo-removal", r"laser hair removal|hair removal|electrolysis|tattoo removal|remove that tattoo|stubborn hairs"),
    ("body-contouring", r"emsculpt|emsella|coolsculpt|body contour|body sculpt|fat freez|cryolipo|fat reduction|stubborn fat|cellulite|muscle building|hifem|vanquish|pelvic floor|inch loss|sculpt(ing)? your body|lose fat"),
    ("injectables", r"botox|botulinum|anti-?wrinkle inject|dermal filler|lip filler|\bfiller\b|polynucleotid|biostimulator|sculptra|\bprofhilo\b|skin booster|mesotherap|p-shot|\bprp\b|exosome|radiesse|facial balancing|\bjuvederm\b|inject(able|ion)s?\b"),
    ("medical-wellness", r"weight loss|weight-loss|semaglutide|tirzepatide|metabolis(m|ing)|"
                         r"\bnad\+|iv (drip|therapy|infusion)|erectile|\bed\b assessment|"
                         r"sexual health|varicose|spider vein|hormone|menopause|men's health"),
    ("trades-home-services",
        r"\bplumb(er|ers|ing)\b|\bboiler|central heating|\bheating engineer|\bgas safe\b|"
        r"\belectric(ian|ians|al contractor)\b|\brewire|consumer unit|\bniceic\b|"
        r"\broof(er|ers|ing)\b|roof repair|\bslate(d)? roof|\bguttering\b|gutter clean|"
        r"\bfascias?\b|soffit|\brendering\b|\bplaster(er|ing)\b|\btiler\b|\bcarpenter|"
        r"\bjoiner(y|s)?\b|\bkitchen fitter|\bbuilder(s)?\b|home (extension|renovation)|"
        r"\bloft conversion|\bdriveway|\bpatio\b|\btarmac|\bblock paving|\blandscap(er|ing)|"
        r"\bgroundwork|\bfencing\b|\bwindow (fitter|installer|fitting)|\bconservator(y|ies)\b|"
        r"\bexterior cleaning|pressure wash|power wash|\bpainter and decorator|\bdecorator\b|"
        r"\bhvac\b|air ?con(ditioning)?\b|\bpest control\b|\bgarage door|\bscaffold"),
    ("agency-to-smb",
        r"(leads?|jobs?|enquir\w+|customers?|clients?|work) for (tradesmen|tradespeople|trades|"
        r"plumbers|electricians|roofers|builders|contractors|clinics?|practices?|med ?spas)|"
        r"grow your (trade|trades|plumbing|roofing|electrical|clinic|practice|business)\b|"
        r"scale your (trade|clinic|practice|business|agency)\b|"
        r"more (jobs|leads|enquiries|customers|patients) (for|to) your\b|"
        r"we help (tradesmen|tradespeople|trades|plumbers|electricians|roofers|builders|"
        r"contractors|clinics|practices|med ?spas|business owners)\b|"
        r"\blead gen(eration)?\b|\bqualified leads\b|\bexclusive leads\b|\bjob leads\b|"
        r"\bmarketing agency\b|\bdigital agency\b|\bmarketing for (tradesmen|trades|plumbers|"
        r"electricians|roofers|builders|contractors)|\bseo for (plumbers|roofers|hvac|"
        r"contractors|trades|tradesmen)|(google|facebook|meta) ads for (tradesmen|trades|"
        r"plumbers|roofers|electricians|builders|contractors|clinics)|"
        r"done[- ]for[- ]you (leads|marketing|ads)|\bwebsite in 24 hours\b|"
        r"websites? for (tradesmen|tradespeople|trades|plumbers|electricians|roofers|builders|"
        r"contractors)|\btrade(s)? business owner|\bself[- ]employed tradesman"),
    ("healthcare-software", r"\bai scribe|ambient (ai|documentation)|clinical documentation|charting|"
                            r"patient intake|practice management (software|system)|\behr\b|\bemr\b|"
                            r"revenue cycle|\brcm\b|prior auth|patient engagement platform|"
                            r"healthcare (software|platform|saas)|hipaa[- ]compliant"),
    ("b2b-software", r"\bsaas\b|\bsoftware\b|book a (free )?demo|request a demo|free trial|"
                     r"per (user|seat) per month|integrat(es|ion) with|workflow automation"),
    ("skin", r"skin|thread vein|aesthetic (clinic|treatment|consult)|medical aesthetic|facial|hydrafacial|peel|microneedl|pigmentation|acne|rosacea|resurfac|\bipl\b|\bhifu\b|morpheus|endolift|fotona|collagen|complexion|glow|dermaplan|led (light )?therap|skin tightening|jowl|fine lines|wrinkl"),
]

# what the OFFER is built on wins over what is merely mentioned; this is the tiebreak order.
# The non-clinical niches sit LAST on purpose: a tie between a clinical niche and a stray software
# or trades word resolves clinical. What makes a software or agency ad one is the audience tests
# (sells_software, sells_to_a_business), not this order.
ORDER = ["cosmetic-surgery", "dental", "hair-restoration", "hair-and-tattoo-removal",
         "body-contouring", "injectables", "medical-wellness", "skin",
         "healthcare-software", "b2b-software", "agency-to-smb", "trades-home-services"]

# The audience test: WHO the ad is addressing beats WHAT it names. An agency ad that says
# "plumber" forty times is still an agency ad, and raw occurrence counting cannot see that - on
# a trades batch it filed more than half of the agency ads as trades-home-services.
#
# NOTE: this runs over `ad_text()`, which includes reviewer prose (notes, format_note).
# Keep every token here to words an ADVERTISER writes, never words a reviewer writes: the phrase
# "practice owner" in this list once convicted a dental clinic whose format_note read
# "a talking-head video of the practice owner".
#
# It is deliberately an AND of two things, not a phrase list: an ad is agency-to-smb when it
# ADDRESSES a business owner (or a trade, or a clinic) AND SELLS that owner leads, marketing,
# a website, ads, SEO, a lead platform or coaching. Either half alone is not enough - a roofer
# advertising to homeowners says "roofer" (audience half only), and a clinic says "book online"
# (offer half only). Both halves must fire.
RE_SMB_AUDIENCE = re.compile(
    r"\btradesm(a|e)n\b|\btradespeople\b|\btrades\b|\btrade business(es)?\b"
    r"|home[- ]?(service|improvement) (business|compan)\w*|\b(local )?service business(es)?\b"
    r"|\bcontractors?\b|\bplumbers\b|\belectricians\b|\broofers\b|\bbuilders\b"
    r"|\blandscapers\b|\binstallers\b|\bjoiners\b|\bsparks\b"
    r"|\bbusiness owners?\b|\bclinic owners?\b"
    r"|\byour (business|company|diary|crew|team|van|trade)\b"
    # "your plumbing company", "most plumbing companies", "every other roofer" - an agency talking
    # ABOUT the trade in the third person is still talking TO the trade
    r"|\byour (plumbing|roofing|electrical|heating|hvac|landscaping|building|cleaning) "
    r"(company|business|firm)\b"
    r"|\b(plumbing|roofing|electrical|hvac|landscaping|building) (compan(y|ies)|business(es)?|firms?)\b"
    r"|\bplumbers?\b|\broofers?\b|\belectricians?\b|\blandscapers?\b"
    r"|\byour (work|leads|jobs|calls|enquiries|quotes|customers|clients)\b"
    r"|if you(?:'re| are) a (tradesman|tradesperson|plumber|electrician|roofer|builder|"
    r"landscaper|joiner|contractor|clinic)"
    r"|attention [a-z ]{0,24}(tradesm\w+|business owners|roofers|plumbers|electricians|builders|"
    r"landscaping|contractors)", re.I)

RE_SELLS_GROWTH = re.compile(
    r"\bleads?\b|\blead gen\w*|\benquir\w+|\bmarketing\b|\bseo\b|\bgoogle ads\b"
    r"|\bfacebook ads\b|\bmeta ads\b|\bppc\b|\bagenc(y|ies)\b|\bwe (run|build|manage) your\b"
    r"|\bwe build\b|\bwebsite\b|\bweb design\b|\bgoogle (maps |business )?(ranking|profile)\b"
    r"|more (work|jobs|customers|calls|enquiries|clients|quotes)\b"
    r"|fill (your|the) diary|book(ed)? solid|quote (visits|requests)"
    r"|word of mouth|lead (platform|site|credit|sites)|\bcheckatrade\b|\bbark\b"
    r"|growth (engine|system|partner)|follow[- ]?up system|\bcrm\b|\bfunnel\b"
    r"|\bmastermind\b|\bcoaching\b|\bmentorship\b"
    r"|per month you'?ll get|no long contracts"
    r"|\bgoogle rankings?\b|rank(ing)? (on|in) (the )?(top \d+ (on|of) )?google"
    r"|top \d+ on google|first page of google|\bonline presence\b"
    r"|\bgoogle business profile\b|\bmarketing plan\b|\bsearch results\b", re.I)


def sells_to_a_business(text):
    """(True, [what fired]) when the ad addresses a business owner AND sells them growth."""
    a = RE_SMB_AUDIENCE.search(text or "")
    b = RE_SELLS_GROWTH.search(text or "")
    if a and b:
        return True, [a.group(0).strip().lower()[:40], b.group(0).strip().lower()[:40]]
    return False, []


def ad_text(row):
    parts = [row.get(k) or "" for k in
             ("offer", "hook", "body_excerpt", "format_note", "device_shown", "notes",
              "claim_text", "callout", "page_name", "advertiser")]
    parts += [str(row.get("page_categories") or "")]
    return " ".join(str(p) for p in parts)


def classify_niche(text):
    """Return (niche, matched_terms). Software sold to a business is decided first, then an agency
    selling growth to a business owner, then every niche is scored by how many distinct patterns
    hit and ties break on ORDER. `skin` is the fallback for a general aesthetic-clinic ad."""
    sw, sw_niche, sw_why = sells_software(text)
    if sw:
        return sw_niche, sw_why
    hit, why = sells_to_a_business(text)
    if hit:
        return "agency-to-smb", why
    scores, hits = {}, {}
    for niche, pat in PATTERNS:
        m = re.findall(pat, text, re.I)
        if m:
            scores[niche] = len(m)
            hits[niche] = sorted({(x if isinstance(x, str) else x[0]).lower() for x in m if x})[:4]
    if not scores:
        return None, []
    best = max(scores.values())
    top = [n for n, s in scores.items() if s == best]
    if len(top) > 1:
        top.sort(key=lambda n: ORDER.index(n))
    return top[0], hits.get(top[0], [])


# ---------------------------------------------------------------- the off-scope gate
# The library holds four kinds of advertiser: clinics selling a treatment to a patient (the eight
# clinical niches), software vendors selling to a business, agencies/coaches selling growth to a
# business owner, and trades selling their own work to a homeowner. Everything else is refused by
# name at ingest. Ads Library keyword searches do not respect any of this ("free consultation" and
# "new patient special" return personal-injury lawyers, a tax firm and a ride-hailing app), so the
# gate stays. Edit OFF_SCOPE to widen or narrow it for your own library.
#
# The gate is deliberately NOT a keyword blacklist on the advertiser name. A crude keyword scan once
# flagged dozens of rows, most of them false positives, including a doctor whose surname is Law. It
# scores the ad's own evidence both ways and only refuses when off-scope wins.

OFF_SCOPE = [
    ("legal", r"personal injury|injury (lawyer|attorney|claim)|accident claim|car accident|"
              r"\blaw firm\b|\bsolicitor|\battorney\b|compensation claim|no win no fee|"
              r"medical negligence|wrongful death|workers'? comp"),
    ("musculoskeletal_pain", r"chiropract|osteopath|\bsciatica\b|herniated disc|bulging disc|"
                             r"degenerative disc|spinal (decompression|stenosis)|back pain|neck pain|"
                             r"lower back|joint pain|physiotherap|\bphysio\b|sports injury|"
                             r"spinal adjustment|pain relief programme|migraine"),
    ("finance_insurance_tax", r"mortgage|remortgage|tax relief|tax rebate|insurance quote|life cover|"
                              r"\bloan\b|refinanc|debt (relief|consolidation)|pension|crypto|"
                              r"investment opportunity"),
    # consumer apps only: B2B software is IN scope (healthcare-software, b2b-software)
    ("consumer_apps", r"\bdownload the app\b|\bride[- ]?hailing\b|\bdating app\b|\bmobile game\b|"
                      r"\bplay now\b"),
    ("recruitment", r"we'?re hiring|now hiring|job vacanc|apply for this role|join our team as"),
    ("ecommerce_product", r"free shipping|add to cart|use code [A-Z0-9]{3,} at checkout|"
                          r"wholesale enquir|shop the (range|collection)"),
    ("other_medical_not_aesthetic", r"\blasik\b|laser eye surgery|alcohol detox|rehab programme|"
                                    r"functional[ -]medicine|\bthyroid\b|\bchiropractic\b|"
                                    r"telehealth (programme|program)|"
                                    r"at-home .{0,25}(detox|programme|program)"),
    ("non_clinical_beauty", r"hair (salon|colouris|colorist)|\bhair ?stylists?\b|\bhairdress|"
                            r"textured hair|beauty parlour|blow ?dry|balayage|"
                            r"barber ?shop|nail (bar|technician)|lash extensions|brow lamination|"
                            r"spray tan|massage therapist"),
]

OFF_SCOPE_CATEGORIES = {
    "chiropractor", "osteopathic doctor", "lawyer & law firm", "lawyer", "personal injury lawyer",
    "attorney", "insurance agent", "insurance company", "financial service",
    "recruiter", "employment agency", "barber shop", "hair salon", "nail salon", "tattoo & piercing shop",
    "real estate agent", "car dealership", "gym/physical fitness centre",
}


def scope_check(row, text=None):
    """(ok, reason, niche, detail). Judge the AD, never the advertiser's name alone.

    `ok` False means ingest refuses the row. The gate only fires when the off-scope evidence beats
    the in-scope evidence, so a chiropractor advertising body contouring (a treatment in scope) is
    kept and a chiropractor advertising sciatica relief is not. Software, agency and trades ads are
    admitted by scoring in-scope on their own patterns, not by an exception: an ad that names no
    treatment, product or trade and sells to nobody still gets refused."""
    import re as _re
    t = text if text is not None else ad_text(row)
    niche, _hits = classify_niche(t)
    # in-scope strength = how many niche families the ad's own words touch, doubled so
    # one clearly-named treatment outweighs one off-scope word. NOT a count of keyword occurrences:
    # repeating an advertiser's own name must never decide this.
    in_score = 2 * sum(1 for _n, _p in PATTERNS if _re.search(_p, t, _re.I))

    # DISTINCT categories, not raw occurrences: an advertiser whose page name contains
    # "Chiropractic" would otherwise be convicted by repetition of its own name.
    labels = [label for label, pat in OFF_SCOPE if _re.search(pat, t, _re.I)]
    off = len(labels)
    cats = row.get("page_categories") or []
    cats = cats if isinstance(cats, list) else [cats]
    cathit = [c for c in cats if str(c).strip().lower() in OFF_SCOPE_CATEGORIES]
    off += len(cathit)
    if cathit:
        labels.append("page category " + ", ".join(str(c) for c in cathit))

    if off == 0:
        return True, None, niche, None
    detail = (f"off-scope signals: {', '.join(sorted(set(labels)))} — the ad's own evidence scores "
              f"{off} off-scope against {in_score} in-scope")
    if in_score == 0 or off >= in_score + 2:
        return (False,
                detail + ". This is not a clinic selling a treatment to a patient, software or "
                         "services sold to a business, or a trade selling its own work",
                niche, None)
    # It survives the gate, but a human should still look: in practice the gate matches the human
    # call almost every time, and the misses are ads that tripped an off-scope signal and squeaked
    # through on one weak in-scope word.
    return True, None, niche, detail + " — kept, but worth a human eye"
