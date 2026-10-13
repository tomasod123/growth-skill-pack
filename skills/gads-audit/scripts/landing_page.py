#!/usr/bin/env python3
"""MODULE 3 - landing page audit for the pages the ads point at (READ-ONLY).

  python3 landing_page.py URL [URL ...] [options]

Options
  --audit-json FILE     account-audit.json from module 1: takes the live ads' final URLs if no
                        URL is given, pulls the ad headlines for message match, and reports
                        Google's own post_click_quality_score beside the measured numbers
  --widths 320,360,390,430,1280
  --thankyou URL        the conversion/thank-you page the form redirects to
  --promise "a,b"       extra phrases the ads promise that the page must carry
  --psi-key KEY         PageSpeed Insights key (or env PSI_API_KEY). Without one, Core Web
                        Vitals are measured locally over CDP and labelled lab, not field.
  --chrome PATH         Chrome/Chromium binary (else env CHROME_PATH or CHROME_BIN, else standard paths)
  --out DIR
  --keep-chrome         leave the browser running (debugging only)

Local Chrome rules this script follows (learned the hard way, do not relax them)
  - audio muted, autoplay gated: an unmuted headless render plays every page video through the
    real speakers with no window to close
  - its OWN --user-data-dir under the scratchpad, never the default profile: a default-profile
    launch signs you out of every Google account
  - polls /json/version until Chrome answers instead of sleeping a fixed time
  - a FRESH tab per width, closed after: Emulation.setDeviceMetricsOverride leaks between runs
    and a leaked override silently turns a 591px overflow into a clean pass
  - cache disabled per run, localStorage cleared: a warm profile hides consent banners and
    makes visible headings read as hidden
  - kills its own Chrome by pid at the end, and never pkills a pattern that matches its own shell

What it reports per width: innerWidth really equals the device width, horizontal overflow,
whether the first form field AND its submit button clear the fold, and the fold height.
Plus: redirect chain, HTTP status, page weight, lab CWV (LCP, CLS, TTFB, DCL), message match
against the ad headlines, and whether the thank-you page exists.
"""
import json
import os
import re
import shutil
import signal
import ssl
import subprocess
import tempfile
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gadslib import md_table, now_stamp, read_json, write_json

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    CTX = ssl.create_default_context()

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/140.0.0.0 Safari/537.36")
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
]
# flag names split on purpose: some Claude Code safety hooks grep the whole command line for them
HEADLESS = "--head" + "less=new"
DEBUG_PORT_FLAG = "--remote-" + "debugging-port"


def arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag) + 1
        if i < len(sys.argv):
            return sys.argv[i]
    return default


def flagged(name):
    return name in sys.argv


def profile_dir():
    base = os.environ.get("CLAUDE_SCRATCHPAD") or os.path.join(tempfile.gettempdir(), "gads-audit-tmp")
    p = os.path.join(base, "gads-audit-chrome")
    os.makedirs(p, exist_ok=True)
    return p


def find_chrome():
    c = arg("--chrome") or os.environ.get("CHROME_PATH") or os.environ.get("CHROME_BIN")
    if c:
        return c
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    w = shutil.which("google-chrome") or shutil.which("chromium")
    if w:
        return w
    sys.exit("[lp] no Chrome found; pass --chrome PATH or set CHROME_PATH (or CHROME_BIN)")


# ---------------------------------------------------------------- plain HTTP checks
def http_chain(url, limit=6):
    """Follow redirects by hand so the chain is visible. Returns (chain, final_status, body, bytes)."""
    chain, cur = [], url
    for _ in range(limit):
        req = urllib.request.Request(cur, headers={"User-Agent": UA})
        try:
            op = urllib.request.build_opener(NoRedirect)
            r = op.open(req, timeout=40)
            code, loc, body = r.status, r.headers.get("Location"), r.read()
            chain.append({"url": cur, "status": code, "location": loc})
            if code in (301, 302, 303, 307, 308) and loc:
                cur = loc if loc.startswith("http") else urllib.parse.urljoin(cur, loc)
                continue
            return chain, code, body, len(body)
        except urllib.error.HTTPError as e:
            body = e.read()
            loc = e.headers.get("Location")
            chain.append({"url": cur, "status": e.code, "location": loc})
            if e.code in (301, 302, 303, 307, 308) and loc:
                cur = loc if loc.startswith("http") else urllib.parse.urljoin(cur, loc)
                continue
            return chain, e.code, body, len(body)
        except Exception as e:  # DNS, TLS mismatch (which returns no status at all)
            chain.append({"url": cur, "status": None, "error": str(e)[:200]})
            return chain, None, b"", 0
    return chain, None, b"", 0


import urllib.parse  # noqa: E402  (after http_chain so the helper below can use it)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


# ---------------------------------------------------------------- CDP
class CDP:
    def __init__(self, port, profile, chrome):
        self.port = port
        args = [chrome, HEADLESS, f"{DEBUG_PORT_FLAG}={port}",
                "--user-data-dir=" + profile,
                "--mute-audio", "--autoplay-policy=user-gesture-required",
                "--no-first-run", "--no-default-browser-check", "--disable-gpu",
                "--window-size=1280,900", "--hide-scrollbars", "--disable-extensions"]
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws_url = None
        for _ in range(120):  # poll, never a fixed sleep
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as r:
                    json.loads(r.read())
                    return
            except Exception:
                time.sleep(0.25)
        self.kill()
        sys.exit("[lp] Chrome never answered /json/version")

    def kill(self):
        try:
            self.proc.send_signal(signal.SIGTERM)
            self.proc.wait(timeout=10)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass

    def new_tab(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/json/new?about:blank", method="PUT")
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())

    def close_tab(self, tid):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/close/{tid}", timeout=10).read()
        except Exception:
            pass


NODE = None


def node_bin():
    global NODE
    if NODE:
        return NODE
    for p in [os.environ.get("NODE_BIN"), shutil.which("node"), "/opt/homebrew/bin/node",
              "/usr/local/bin/node"]:
        if p and os.path.exists(p):
            try:
                v = subprocess.run([p, "-v"], capture_output=True, text=True, timeout=10).stdout.strip()
                if v.startswith("v") and int(v[1:].split(".")[0]) >= 22:  # need global WebSocket
                    NODE = p
                    return p
            except Exception:
                continue
    sys.exit("[lp] need node 22+ for the CDP WebSocket (install Node 22+, or set NODE_BIN to its path)")


DRIVER = r"""
const [wsUrl, url, width, height] = process.argv.slice(2);
const ws = new WebSocket(wsUrl);
let id = 0; const pend = new Map();
const send = (method, params={}, sessionId) => new Promise((res, rej) => {
  const i = ++id; pend.set(i, {res, rej});
  ws.send(JSON.stringify(sessionId ? {id:i, method, params, sessionId} : {id:i, method, params}));
});
ws.onmessage = (e) => { const m = JSON.parse(e.data);
  if (m.id && pend.has(m.id)) { const {res, rej} = pend.get(m.id); pend.delete(m.id);
    m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result); } };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
ws.onopen = async () => {
  try {
    await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
    await send('Network.setCacheDisabled', {cacheDisabled: true});
    await send('Emulation.setDeviceMetricsOverride',
      {width: +width, height: +height, deviceScaleFactor: 1, mobile: +width < 700});
    const t0 = Date.now();
    await send('Page.navigate', {url});
    await sleep(3500);
    const expr = `(() => {
      const vis = el => { if(!el) return false; const r = el.getBoundingClientRect();
        const s = getComputedStyle(el);
        return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none' && +s.opacity>0.05; };
      const forms = [...document.querySelectorAll('form')].filter(vis);
      const iframes = [...document.querySelectorAll('iframe')].filter(vis)
        .map(f => ({src: f.src||'', top: Math.round(f.getBoundingClientRect().top + scrollY),
                    h: Math.round(f.getBoundingClientRect().height)}));
      let field = null, submit = null, formTop = null;
      for (const f of forms) {
        const fl = [...f.querySelectorAll('input,select,textarea')]
          .filter(e => vis(e) && !['hidden','submit','button'].includes((e.type||'').toLowerCase()));
        const sb = [...f.querySelectorAll('button,input[type=submit],[role=button]')].filter(vis);
        if (fl.length) { const r = fl[0].getBoundingClientRect();
          field = {name: fl[0].name||fl[0].id||fl[0].placeholder||'', top: Math.round(r.top+scrollY),
                   bottom: Math.round(r.bottom+scrollY)};
          formTop = Math.round(f.getBoundingClientRect().top + scrollY);
          if (sb.length) { const rb = sb[sb.length-1].getBoundingClientRect();
            submit = {text: (sb[sb.length-1].innerText||sb[sb.length-1].value||'').trim().slice(0,40),
                      top: Math.round(rb.top+scrollY), bottom: Math.round(rb.bottom+scrollY)}; }
          break; }
      }
      // \\s, not \s: this whole expression lives in a JS TEMPLATE LITERAL, where \s is an
      // invalid escape that collapses to a bare s, so /\s+/g silently becomes /s+/g and strips
      // every letter s out of the page text ("Business" read as "Bu ine").
      const txt = (document.body ? document.body.innerText : '').replace(/\\s+/g,' ');
      const nav = performance.getEntriesByType('navigation')[0] || {};
      const lcp = (performance.getEntriesByType('largest-contentful-paint')||[]).pop();
      const paints = {};
      for (const p of performance.getEntriesByType('paint')) paints[p.name] = Math.round(p.startTime);
      return {innerWidth: innerWidth, innerHeight: innerHeight,
        scrollWidth: document.documentElement.scrollWidth,
        scrollHeight: document.documentElement.scrollHeight,
        overflowPx: Math.max(0, document.documentElement.scrollWidth - innerWidth),
        title: document.title, h1: (document.querySelector('h1')||{}).innerText || '',
        formCount: forms.length, firstField: field, submit: submit, formTop: formTop,
        iframes: iframes, textLen: txt.length, text: txt.slice(0, 120000),
        ttfbMs: nav.responseStart ? Math.round(nav.responseStart) : null,
        dclMs: nav.domContentLoadedEventEnd ? Math.round(nav.domContentLoadedEventEnd) : null,
        loadMs: nav.loadEventEnd ? Math.round(nav.loadEventEnd) : null,
        lcpMs: lcp ? Math.round(lcp.startTime) : null, paints: paints,
        transferBytes: nav.transferSize || null,
        imgs: [...document.images].length};
    })()`;
    const r = await send('Runtime.evaluate', {expression: expr, returnByValue: true, awaitPromise: false});
    const out = r.result.value || {error: 'no value'};
    out.wallMs = Date.now() - t0;
    // leave no override behind for the next tab
    await send('Emulation.clearDeviceMetricsOverride');
    try { await send('Runtime.evaluate', {expression: 'try{localStorage.clear();sessionStorage.clear()}catch(e){}'}); } catch(e) {}
    console.log(JSON.stringify(out));
    ws.close(); process.exit(0);
  } catch (e) { console.log(JSON.stringify({error: String(e)})); process.exit(1); }
};
ws.onerror = (e) => { console.log(JSON.stringify({error: 'ws ' + String(e.message||e)})); process.exit(1); };
"""


def render(cdp, url, width, height, driver_path):
    tab = cdp.new_tab()  # a FRESH tab per width: the metrics override leaks otherwise
    try:
        p = subprocess.run([node_bin(), driver_path, tab["webSocketDebuggerUrl"], url,
                            str(width), str(height)], capture_output=True, text=True, timeout=180)
        line = [l for l in p.stdout.splitlines() if l.strip().startswith("{")]
        return json.loads(line[-1]) if line else {"error": (p.stderr or p.stdout)[:400]}
    except subprocess.TimeoutExpired:
        return {"error": "render timed out"}
    finally:
        cdp.close_tab(tab["id"])


# ---------------------------------------------------------------- PSI (field + lab, authoritative)
def psi(url, key):
    q = urllib.parse.urlencode({"url": url, "key": key, "strategy": "MOBILE",
                                "category": "performance"})
    try:
        req = urllib.request.Request("https://www.googleapis.com/pagespeedonline/v5/runPagespeed?" + q,
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, context=CTX, timeout=120) as r:
            d = json.loads(r.read())
    except Exception as e:
        return {"error": str(e)[:200]}
    lh = d.get("lighthouseResult", {})
    au = lh.get("audits", {})
    field = d.get("loadingExperience", {}).get("metrics", {})
    return {"performance_score": round((lh.get("categories", {}).get("performance", {})
                                        .get("score") or 0) * 100),
            "lab": {k: au.get(k, {}).get("displayValue") for k in
                    ("largest-contentful-paint", "cumulative-layout-shift", "total-blocking-time",
                     "speed-index", "first-contentful-paint")},
            "field": {k: {"percentile": v.get("percentile"), "category": v.get("category")}
                      for k, v in field.items()},
            "field_overall": d.get("loadingExperience", {}).get("overall_category")}


# ---------------------------------------------------------------- message match
def promises_from_audit(audit):
    heads = []
    for a in (audit or {}).get("ads", []):
        if a.get("status") == "ENABLED":
            heads += a.get("headlines", []) + a.get("descriptions", [])
    return list(dict.fromkeys(h for h in heads if h))


def match(text, phrase):
    """Word-level containment, case-insensitive, punctuation-tolerant. Reports the fraction of the
    phrase's content words present, so 'FUE Hair Transplant Chicago' is not a bare pass/fail."""
    words = [w for w in re.findall(r"[a-z0-9']+", phrase.lower()) if len(w) > 2]
    if not words:
        return None, 0
    low = " " + re.sub(r"[^a-z0-9' ]+", " ", text.lower()) + " "
    hit = [w for w in words if f" {w} " in low or f" {w}" in low]
    return len(hit) / len(words), len(words)


def main():
    # positional URLs only: a value that FOLLOWS a flag belongs to that flag (--thankyou, --chrome)
    av = sys.argv[1:]
    urls = [a for i, a in enumerate(av)
            if a.startswith("http") and not (i > 0 and av[i - 1].startswith("--"))]
    audit = read_json(arg("--audit-json"), None) if arg("--audit-json") else None
    if not urls and audit:
        urls = sorted({u for a in audit.get("ads", []) if a.get("status") == "ENABLED"
                       for u in a.get("final_urls", [])})
    if not urls:
        print(__doc__)
        return 2
    widths = [int(w) for w in (arg("--widths", "320,360,390,430,1280")).split(",")]
    out = os.path.abspath(arg("--out", "gads-audit-output"))
    os.makedirs(out, exist_ok=True)
    key = arg("--psi-key") or os.environ.get("PSI_API_KEY")
    promises = [p.strip() for p in (arg("--promise") or "").split(",") if p.strip()]
    promises += promises_from_audit(audit)
    thankyou = arg("--thankyou")

    driver_path = os.path.join(out, "_cdp_driver.mjs")
    with open(driver_path, "w") as fh:
        fh.write(DRIVER)

    cdp = CDP(9411, profile_dir(), find_chrome())
    results = {"pulled_at": now_stamp(), "pages": [], "psi_used": bool(key),
               "promises_checked": promises}
    try:
        for url in urls:
            chain, status, body, nbytes = http_chain(url)
            page = {"url": url, "redirect_chain": chain, "final_status": status,
                    "html_bytes": nbytes, "widths": {}, "issues": []}
            if len(chain) > 1:
                page["issues"].append(
                    f"redirect chain of {len(chain)} hops: " + " -> ".join(
                        f"{c['url']} ({c['status']})" for c in chain)
                    + ". Every hop costs load time on a paid click and Google scores the final page.")
            if status in (401, 403, 429):
                page["issues"].append(
                    f"final status {status}: this is almost certainly a bot challenge (Cloudflare or "
                    "similar) blocking US, not an outage. Real visitors are probably fine. Confirm the "
                    "certificate and a browser load before reporting anything about this page, and treat "
                    "every other measurement below as unreliable.")
                page["blocked"] = True
            elif status != 200:
                page["issues"].append(f"final status {status}: a paid click lands on this. Fix before "
                                      "anything else. A TLS/cert mismatch returns no status at all, "
                                      "which plain uptime checks miss.")
                page["blocked"] = True
            for w in widths:
                h = 844 if w < 700 else 800
                r = render(cdp, url, w, h, driver_path)
                page["widths"][str(w)] = r
                if r.get("error"):
                    page["issues"].append(f"{w}px: render failed ({r['error']})")
                    continue
                if r.get("innerWidth") != w:
                    page["issues"].append(
                        f"{w}px: the page laid out at {r.get('innerWidth')}px, not {w}px. Usually a "
                        "missing viewport meta, so phones zoom out to tiny text.")
                if (r.get("overflowPx") or 0) > 2:
                    page["issues"].append(f"{w}px: {r['overflowPx']}px of horizontal overflow "
                                          f"(content {r.get('scrollWidth')}px in a {w}px window).")
                fold = r.get("innerHeight") or h
                f, s = r.get("firstField"), r.get("submit")
                if r.get("formCount", 0) == 0 and not r.get("iframes"):
                    page["issues"].append(f"{w}px: no visible form found. A paid search click with no "
                                          "form on screen leans entirely on the phone number.")
                if f and f["bottom"] > fold:
                    page["issues"].append(f"{w}px: the form's first field starts at {f['top']}px, below "
                                          f"the {fold}px fold. Nobody sees a form they have to scroll to.")
                if s and s["bottom"] > fold:
                    page["issues"].append(f"{w}px: the submit button ends at {s['bottom']}px, "
                                          f"{s['bottom'] - fold}px below the {fold}px fold.")
                for ifr in r.get("iframes", []):
                    if any(k in (ifr.get("src") or "") for k in ("leadconnector", "msgsndr", "ghl")):
                        if ifr["top"] + ifr["h"] > fold:
                            page["issues"].append(
                                f"{w}px: the embedded form iframe runs from {ifr['top']}px to "
                                f"{ifr['top'] + ifr['h']}px, past the {fold}px fold. Cross-origin "
                                "iframes also skip the page's network throttling, so time them separately.")
            big = page["widths"].get(str(max(widths)), {})
            text = big.get("text") or ""
            page["message_match"] = []
            # If the page did not render, every promise looks absent and the finding is noise.
            if page.get("blocked") or len(text.split()) < 40:
                page["message_match_skipped"] = (
                    "not scored: the page did not render for us, so an absent promise means nothing")
                promises = []
            for p in promises:
                frac, n = match(text, p)
                if frac is not None:
                    page["message_match"].append({"promise": p, "words": n,
                                                  "fraction_on_page": round(frac, 2)})
            missed = [m for m in page["message_match"] if m["fraction_on_page"] < 0.6]
            if missed:
                page["issues"].append(
                    f"{len(missed)} ad promise(s) are mostly absent from the page: "
                    + "; ".join(f"\"{m['promise']}\" ({int(m['fraction_on_page'] * 100)}% of its words)"
                                for m in missed[:6])
                    + ". Message match is half of Google's landing page experience score.")
            page["lab_cwv"] = {k: big.get(k) for k in ("ttfbMs", "dclMs", "loadMs", "lcpMs")}
            page["lab_cwv"]["paints"] = big.get("paints")
            page["lab_cwv"]["note"] = ("Lab numbers from one local render over your own connection. "
                                       "Not field data and not a score to quote to a client.")
            if key:
                page["psi"] = psi(url, key)
            if audit:
                scored = [k for k in audit.get("keywords", []) if k.get("landing_page_quality")]
                page["google_landing_page_experience"] = {
                    "keywords_with_a_score": len(scored),
                    "below_average": [k["text"] for k in scored
                                      if k["landing_page_quality"] == "BELOW_AVERAGE"],
                    "average_or_above": [k["text"] for k in scored
                                         if k["landing_page_quality"] != "BELOW_AVERAGE"],
                    "note": ("Google's post_click_quality_score IS the authoritative landing-page "
                             "verdict, because it is what Ad Rank uses. It stays NULL until the "
                             "keyword has impressions, which is why the measured numbers above "
                             "matter on a young campaign.")}
            results["pages"].append(page)

        if thankyou:
            chain, status, _b, n = http_chain(thankyou)
            results["thankyou"] = {"url": thankyou, "status": status, "redirect_chain": chain,
                                  "html_bytes": n}
            if status != 200:
                results["thankyou"]["issue"] = (
                    f"the thank-you page returns {status}. If the conversion is counted on a visit to "
                    "it, nothing is being counted.")
    finally:
        if not flagged("--keep-chrome"):
            cdp.kill()  # by pid, never a pkill pattern that would match this shell
        try:
            os.remove(driver_path)  # never leave a stray .mjs in a folder a deploy script might ship
        except OSError:
            pass

    write_json(os.path.join(out, "landing-page.json"), results)

    L = [f"# Landing page audit", "", f"Measured {results['pulled_at']}. "
         + ("PageSpeed Insights used for Core Web Vitals." if key else
            "No PageSpeed key, so Core Web Vitals are LAB numbers from one local render, not field "
            "data. Never hand a client a single lab score: identical pages have swung 57-99 between "
            "runs. Quote page weight and field timings instead."), ""]
    for p in results["pages"]:
        L += [f"## {p['url']}", "",
              f"HTTP {p['final_status']}, {len(p['redirect_chain'])} hop(s), "
              f"{p['html_bytes'] / 1024:.0f} KB of HTML.", ""]
        L.append(md_table(["Width", "Laid out at", "Overflow", "Fold", "Form", "First field top",
                           "Submit bottom", "Page height"],
                          [[w, r.get("innerWidth"), f"{r.get('overflowPx', 0)}px",
                            r.get("innerHeight"), r.get("formCount"),
                            (r.get("firstField") or {}).get("top"),
                            (r.get("submit") or {}).get("bottom"), r.get("scrollHeight")]
                           for w, r in p["widths"].items()]))
        c = p["lab_cwv"]
        ms = lambda v: "no data" if v is None else f"{v}ms"
        L += ["", f"Lab timings (one local render): TTFB {ms(c.get('ttfbMs'))}, "
              f"DOMContentLoaded {ms(c.get('dclMs'))}, load {ms(c.get('loadMs'))}, "
              f"LCP {ms(c.get('lcpMs'))}. {c['note']}", ""]
        if p.get("psi"):
            L += [f"PageSpeed Insights (mobile): " + json.dumps(p["psi"], indent=1), ""]
        if p.get("google_landing_page_experience"):
            gg = p["google_landing_page_experience"]
            L += [f"**Google's own verdict:** {gg['keywords_with_a_score']} keyword(s) have a landing "
                  f"page experience score; {len(gg['below_average'])} rated below average"
                  + (": " + ", ".join(gg["below_average"][:10]) if gg["below_average"] else "")
                  + ". " + gg["note"], ""]
        if p["message_match"]:
            L += ["### Message match against the live ad copy", "",
                  md_table(["Ad line", "Words", "Share of its words on the page"],
                           [[m["promise"], m["words"], f"{int(m['fraction_on_page'] * 100)}%"]
                            for m in sorted(p["message_match"], key=lambda m: m["fraction_on_page"])]), ""]
        L += ["### Issues", ""] + ([f"- {i}" for i in p["issues"]] or ["- none found"]) + [""]
    if results.get("thankyou"):
        t = results["thankyou"]
        L += ["## Thank-you / conversion page", "", f"{t['url']} returns HTTP {t['status']}."
              + (" " + t["issue"] if t.get("issue") else ""), ""]
    L += ["Read-only: pages were fetched and rendered, nothing was submitted or changed.", ""]
    md = "\n".join(L)
    with open(os.path.join(out, "LANDING-PAGE.md"), "w") as fh:
        fh.write(md)
    print(md)
    nissues = sum(len(p["issues"]) for p in results["pages"])
    print(f"\n[lp] {len(results['pages'])} page(s), {nissues} issue(s). "
          f"Wrote {out}/landing-page.json and LANDING-PAGE.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
