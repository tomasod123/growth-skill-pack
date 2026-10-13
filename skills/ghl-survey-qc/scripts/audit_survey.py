#!/usr/bin/env python3
"""Audit any GoHighLevel (GHL) survey or form from its PUBLIC widget page.
No API key, no login, no submission. Reads the __NUXT_DATA__ payload and reports
every setting that matters, then flags the known traps.

  python3 audit_survey.py <surveyId|widget-url> [--kind survey|form] [--host https://links.yourdomain.com] [--json out.json]

Why the public page and not the API: GHL has no read endpoint for a survey's style
config. The widget page ships the whole thing inline.
White-label accounts serve the widget from their own link domain: pass it with --host
(or set GHL_WIDGET_HOST), or pass the full widget URL.
"""
import json, os, re, sys, ssl, urllib.request, argparse

# macOS python has no CA bundle of its own; without this every fetch dies on
# CERTIFICATE_VERIFY_FAILED and it reads like the page is gone.
try:
    import certifi
    _CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _CTX = ssl.create_default_context()

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
HOSTS = ["https://link.msgsndr.com", "https://links.leadconnectorhq.com", "https://api.leadconnectorhq.com"]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=45, context=_CTX).read().decode("utf-8", "replace")


def resolve(arr, i, depth=0):
    if depth > 16:
        return "<deep>"
    v = arr[i]
    if isinstance(v, list):
        return [resolve(arr, x, depth + 1) if isinstance(x, int) and 0 <= x < len(arr) else x for x in v]
    if isinstance(v, dict):
        return {k: (resolve(arr, x, depth + 1) if isinstance(x, int) and 0 <= x < len(arr) else x) for k, x in v.items()}
    return v


def load(target, kind, host=None):
    if target.startswith("http"):
        urls = [target]
    else:
        hosts = ([host.rstrip("/")] if host else []) + HOSTS
        urls = ["%s/widget/%s/%s" % (h, kind, target) for h in hosts]
    last = None
    for u in urls:
        try:
            html = fetch(u)
        except Exception as e:
            last = e
            continue
        m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        if not m:
            last = RuntimeError("no __NUXT_DATA__ at " + u)
            continue
        return u, resolve(json.loads(m.group(1)), 0)
    raise SystemExit("could not read the widget page: %s" % last)


def dig(o, *names):
    """find the first dict that contains all of `names`, breadth-first"""
    q = [o]
    while q:
        cur = q.pop(0)
        if isinstance(cur, dict):
            if all(n in cur for n in names):
                return cur
            q.extend(cur.values())
        elif isinstance(cur, list):
            q.extend(cur)
    return None


def hexof(v):
    if not isinstance(v, str) or not v:
        return None
    s = v.lstrip("#")
    return "#" + (s[:6].upper() if len(s) in (6, 8) else s.upper())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--kind", default="survey", choices=["survey", "form"])
    ap.add_argument("--host", default=os.environ.get("GHL_WIDGET_HOST", ""),
                    help="white-label link domain, e.g. https://links.yourdomain.com (optional)")
    ap.add_argument("--json")
    a = ap.parse_args()

    url, data = load(a.target, a.kind, a.host or None)
    fd = dig(data, "form", "slides") or dig(data, "form")
    if fd is None:
        raise SystemExit("could not find formData in the payload")
    f = fd.get("form", {})
    slides = fd.get("slides", [])

    print("SOURCE          %s\n" % url)

    # ---------- questions ----------
    print("QUESTIONS (%d)" % len(slides))
    tags = []
    for i, s in enumerate(slides, 1):
        for fl in s.get("slideData", []):
            tag = fl.get("tag") or fl.get("fieldKey") or "?"
            tags.append((i, tag, fl.get("label", ""), fl.get("placeholder", "")))
            print("  %-2d %-22s %-40s ph=%s" % (i, tag, (fl.get("label") or "")[:40], (fl.get("placeholder") or "")[:34]))
    print()

    # ---------- behaviour ----------
    fa = f.get("formAction", {}) or {}
    print("BEHAVIOUR")
    for k, v in [
        ("redirect after submit", fa.get("redirectUrl") or "(none, shows a message)"),
        ("sticky contact", f.get("stickyContact")),
        ("partial contact creation", fd.get("enablePartialContactCreation")),
        ("save and exit confirmation", f.get("enableSaveExitConfirmation")),
        ("auto navigation", not f.get("disableAutoNavigation", False)),
        ("progress bar", f.get("isProgressBarEnabled")),
        ("back button", f.get("isBackButtonEnable")),
        ("email notifications", fd.get("emailNotifications")),
        ("auto responder", fd.get("autoResponder")),
        ("show in conversations feed", f.get("showSubmissionInConversationsFeed")),
        ("facebook pixel id", f.get("fbPixelId") or "(none)"),
        ("submission event", f.get("formSubmissionEvent")),
    ]:
        print("  %-30s %s" % (k, v))
    print()

    # ---------- per-device map ----------
    def flat(o, pre=""):
        r = {}
        if isinstance(o, dict):
            for k, v in o.items():
                r[pre + k] = v
                if isinstance(v, dict):
                    r.update(flat(v, pre + k + "."))
        return r
    K = flat(f)
    K.update({k: v for k, v in fd.items() if not isinstance(v, list)})
    pairs = []
    for k in K:
        base = k.split(".")[-1]
        if base.startswith("mobile") and len(base) > 6:
            twin = base[6].lower() + base[7:]
            parent = ".".join(k.split(".")[:-1])
            cand = (parent + "." + twin) if parent else twin
            if cand in K:
                pairs.append((cand, k))
    print("SET SEPARATELY FOR DESKTOP AND MOBILE (%d) - changing one does NOT change the other" % len(pairs))
    for d, m in sorted(pairs):
        print("  %s" % d)
    print("\nSHARED - one value drives BOTH views, so a 'mobile' edit here also moves desktop")
    for k in ["style.background", "style.border.color", "style.border.radius", "style.border.border",
              "fieldStyle.primaryColor", "fieldStyle.border.color", "fieldStyle.labelFontFamily",
              "inputStyleType", "width", "style.fieldSpacing", "customStyle"]:
        if k in K:
            print("  %-34s %s" % (k, json.dumps(K[k])[:48]))
    print()

    # ---------- traps ----------
    foot = f.get("footerStyle", {}) or {}
    mfoot = f.get("mobileFooterStyle", {}) or {}
    fb, mb = foot.get("buttonStyle", {}) or {}, mfoot.get("buttonStyle", {}) or {}
    fs = f.get("fieldStyle", {}) or {}
    st = f.get("style", {}) or {}
    issues = []

    def add(sev, what, why, fix):
        issues.append((sev, what, why, fix))

    # 1. white-on-white Continue in the resume dialog
    for view, blk, btn in (("desktop", foot, fb), ("mobile", mfoot, mb)):
        bg, fc = hexof(blk.get("backgroundFill")), hexof(btn.get("fontColor"))
        if bg and fc and bg[:7] == fc[:7]:
            add("BLOCKER", "%s resume dialog: Continue button is invisible" % view,
                "GHL styles it background=footerStyle.backgroundFill (%s), color=buttonStyle.fontColor (%s). Same colour." % (bg, fc),
                "Change the %s footer button font colour to a dark brand colour." % view)
    if f.get("enableSaveExitConfirmation") and not issues:
        add("NOTE", "save-and-exit confirmation is on",
            "Returning visitors get a 'Submission in progress' dialog.",
            "Fine once Continue is legible. Check it on a real return visit.")

    # 2. mobile footer left on GHL defaults
    if hexof(mb.get("fontColor")) in ("#155EEF", "#155EEFFF") or hexof(mb.get("arrowFillColor")) == "#FFFFFF" and mb.get("buttonType") == "onlyArrow":
        add("HIGH", "mobile footer is still the GHL default blue",
            "buttonType=%s fontColor=%s" % (mb.get("buttonType"), hexof(mb.get("fontColor"))),
            "Set it to Text and arrow in brand colours. Mobile is a SEPARATE panel from desktop.")
    if mb.get("buttonType") != fb.get("buttonType"):
        add("HIGH", "Next button differs between desktop and mobile",
            "desktop=%s, mobile=%s" % (fb.get("buttonType"), mb.get("buttonType")),
            "Make them match unless you meant it.")

    # 3. survey card drawing its own frame inside an embedding card
    b = st.get("border", {}) or {}
    if b.get("border") and int(b.get("border") or 0) > 0:
        add("MED", "the survey draws its own border (%s, radius %s)" % (hexof(b.get("color")), b.get("radius")),
            "If the page already frames the form, you get two frames one inside the other.",
            "Advanced > Survey: border width 0, corner radius 0, shadow off, when embedded.")

    # 4. nobody notified
    if not fd.get("emailNotifications") and not fd.get("autoResponder") and not f.get("showSubmissionInConversationsFeed"):
        add("BLOCKER", "nothing tells anyone a lead came in",
            "email notifications, auto responder and conversations feed are all off.",
            "Turn on a notification, or confirm a PUBLISHED workflow covers it.")

    # 5. contact details asked late
    order = [t[1] for t in tags]
    for want in ("email", "phone", "phone_number"):
        if want in order:
            pos = order.index(want) + 1
            if pos > max(2, len(order) - 2) and len(order) > 3:
                add("MED", "'%s' is question %d of %d" % (want, pos, len(order)),
                    "Anyone who drops before it is unreachable, even with partial contact creation on.",
                    "Move at least email into the first two questions.")
            break

    # 6. locale-wrong placeholders
    for i, tag, label, ph in tags:
        if ph and re.search(r"\+1 ?\(?555|\(555\)|555-0", ph):
            add("MED", "US phone placeholder on question %d" % i, ph, "Use the client's local format.")

    # 7. off-brand field focus colour
    pc = hexof(fs.get("primaryColor"))
    if pc in ("#ED2929", "#ED2929FF"):
        add("LOW", "field focus colour is GHL's default red (%s)" % pc, "Shows on focus and on validation.",
            "Set Styles > Colors & Background > Primary Color to a brand colour.")

    print("FINDINGS (%d)" % len(issues))
    rank = {"BLOCKER": 0, "HIGH": 1, "MED": 2, "LOW": 3, "NOTE": 4}
    for sev, what, why, fix in sorted(issues, key=lambda x: rank.get(x[0], 9)):
        print("  [%s] %s\n      why: %s\n      fix: %s" % (sev, what, why, fix))
    if not issues:
        print("  none of the known traps")

    if a.json:
        json.dump({"source": url, "formData": fd,
                   "issues": [dict(zip(("severity", "what", "why", "fix"), i)) for i in issues]},
                  open(a.json, "w"), indent=1, ensure_ascii=False)
        print("\nfull config written to %s" % a.json)
    return 1 if any(i[0] == "BLOCKER" for i in issues) else 0


if __name__ == "__main__":
    sys.exit(main())
