"""
AI Visibility & GEO Report -- PDF Generator
Usage: python build_report.py <path_to_data.json>

DETERMINISM CONTRACT
--------------------
Every section title and every table column header in this report is a literal
constant defined in the SECTION_TITLES and COLUMNS blocks below. They are NOT
read from the data JSON. The model that produces the data JSON supplies ONLY
data values (rows, numbers, narrative strings). It cannot rename a section or a
column. This guarantees the report has an identical skeleton on every run, for
every brand, regardless of how the data was generated.

WHITE-LABEL
-----------
Colours, agency name, report title, footer, logo and font are read from
config.white_label. If a value is missing, a neutral default is used.
"""

import sys, json, os

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
)
from reportlab.platypus.flowables import Flowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Base Unicode font registration ───────────────────────────────────────────
# DejaVu Sans is not bundled. It is looked up in (first hit wins):
#   $DEJAVU_FONT_DIR, ./fonts next to this script, common system font folders,
#   and matplotlib's bundled copy. Install with `sudo apt install fonts-dejavu-core`
#   (Linux), `brew install --cask font-dejavu` (macOS), or download from
#   https://dejavu-fonts.github.io/ and point DEJAVU_FONT_DIR at the folder.
# If none is found the report falls back to Helvetica (Latin-1 only: bullets,
# curly quotes and non-English characters may render as boxes).
_FONT_FILES = {"DejaVu": "DejaVuSans.ttf", "DejaVu-Bold": "DejaVuSans-Bold.ttf",
               "DejaVu-Oblique": "DejaVuSans-Oblique.ttf"}


def _font_dirs():
    dirs = []
    if os.environ.get("DEJAVU_FONT_DIR"):
        dirs.append(os.environ["DEJAVU_FONT_DIR"])
    dirs += [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"),
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/dejavu",
        "/usr/share/fonts/TTF",
        "/usr/local/share/fonts",
        os.path.expanduser("~/.local/share/fonts"),
        os.path.expanduser("~/.fonts"),
        os.path.expanduser("~/Library/Fonts"),
        "/Library/Fonts",
        "/opt/homebrew/share/fonts",
    ]
    try:
        import matplotlib
        dirs.append(os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf"))
    except Exception:
        pass
    return dirs


def _find_font(filename):
    for d in _font_dirs():
        p = os.path.join(d, filename)
        if os.path.isfile(p):
            return p
    return None


_found = {name: _find_font(fn) for name, fn in _FONT_FILES.items()}
if _found["DejaVu"]:
    for _name, _path in _found.items():
        pdfmetrics.registerFont(TTFont(_name, _path or _found["DejaVu"]))
    pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold",
                                  italic="DejaVu-Oblique")
    _BASE_FONTS = ("DejaVu", "DejaVu-Bold", "DejaVu-Oblique")
else:
    sys.stderr.write("[build_report] WARNING: DejaVu Sans not found (see SETUP.md). "
                     "Falling back to Helvetica; some glyphs may show as boxes.\n")
    _BASE_FONTS = ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique")

PW, PH = A4
MARGIN = 18 * mm

# Font family names actually used when drawing. Overridden by white-label font
# if the config supplies a valid TTF; otherwise these stay as the DejaVu family.
FONT, FONT_BOLD, FONT_ITAL = _BASE_FONTS

# ══════════════════════════════════════════════════════════════════════════════
#  FIXED REPORT STRUCTURE  --  do not make these dynamic
# ══════════════════════════════════════════════════════════════════════════════

SECTION_TITLES = {
    "summary":     "AI Visibility Summary",
    "by_llm":      "By-LLM Breakdown",
    "by_prompt":   "By Prompt & Topic",
    "citations":   "Citation Landscape",
    "competitors": "Competitor Comparison",
    "volume":      "AI Search Demand",
    "actions":     "Opportunities & Next Actions",
    "glossary":    "Methodology & Glossary",
}

# Every column header used anywhere in the report, defined once, in order.
COLUMNS = {
    "by_llm":            ["LLM Model", "Prompts Tested", "Mentions", "Mention Rate",
                          "Citations", "Citation Rate", "Typical Prominence"],
    "by_prompt":         ["Prompt", "Type", "Models Mentioning", "Prominence", "Cited"],
    "top_domains":       ["Cited Domain", "Citations", "Citation Share", "Owner"],
    "top_pages":         ["Cited Page", "Domain", "Citations", "Owner"],
    # Competitor metrics are SHARE OF VOICE (each entity's share of all brand+competitor
    # mentions/citations, summing to ~100%) — a DIFFERENT metric from the Section 1
    # headline, which is a response rate. Label them "SoV" in both modes so a number
    # never shares a header with the headline KPI. Dataset mode also prefixes "Dataset".
    "competitors_live":    ["Brand / Competitor", "Mention SoV", "Citation SoV",
                            "Visibility (SoV)"],
    "competitors_dataset": ["Brand / Competitor", "Dataset Mention SoV",
                            "Dataset Citation SoV", "Dataset Visibility (SoV)"],
    "volume":            ["Keyword / Topic", "AI Search Demand"],
    "prompt_set":        ["#", "Prompt", "Type", "Keyword"],
}

# Fixed vocab for prompt prominence (ordered strongest -> absent).
PROMINENCE_ORDER = ["Named first", "Shortlist", "Passing mention", "Absent"]

# Fixed vocab for prompt type labels.
PROMPT_TYPES = ["Informational", "Comparative", "Recommendation", "Branded"]

# ══════════════════════════════════════════════════════════════════════════════
#  THEME  (white-label)
# ══════════════════════════════════════════════════════════════════════════════

def _warn(msg):
    """Non-fatal warning to stderr; the operator sees it and can act."""
    sys.stderr.write("[build_report] WARNING: " + msg + "\n")

def build_theme(wl):
    """Merge white-label config over neutral defaults. Returns colour dict."""
    def hx(key, default):
        v = (wl or {}).get(key)
        if not v:
            return HexColor(default)
        try:
            return HexColor(v)
        except Exception:
            _warn(f"white_label.{key}={v!r} is not a valid hex colour; using default {default}.")
            return HexColor(default)
    return {
        "primary": hx("primary_color", "#1F2937"),
        "accent":  hx("accent_color",  "#2563EB"),
        "success": HexColor("#16A34A"),
        "danger":  HexColor("#DC2626"),
        "warn":    HexColor("#D97706"),
        "bg":      HexColor("#F3F4F6"),
        "muted":   HexColor("#6B7280"),
        "grid":    HexColor("#E5E7EB"),
        "soft":    HexColor("#EFF6FF"),
        "white":   colors.white,
    }

# Populated in build_pdf() before any drawing happens.
T = build_theme(None)

# Glyphs the report relies on; a custom font missing these renders "notdef" boxes.
_REQUIRED_GLYPHS = "•—–…"  # bullet, em-dash, en-dash, ellipsis

def _font_covers_required_glyphs(path):
    """Best-effort check that a TTF has the report's punctuation glyphs."""
    try:
        from reportlab.pdfbase.ttfonts import TTFontFile
        ff = TTFontFile(path)
        cmap = getattr(ff, "charToGlyph", None)
        if not cmap:
            return True  # can't inspect; don't block
        return all(ord(ch) in cmap for ch in _REQUIRED_GLYPHS)
    except Exception:
        return True  # inspection failed; don't block on it

def apply_white_label_font(wl):
    """If config supplies a TTF, register it and switch the drawing font.

    Bold/italic collapse to one weight unless separate faces are supplied via
    font_path_bold / font_path_italic. Warns (never silently) on any problem.
    """
    global FONT, FONT_BOLD, FONT_ITAL
    wl = wl or {}
    path = wl.get("font_path")
    name = wl.get("font_name")
    if not (path and name):
        return
    if not os.path.exists(path):
        _warn(f"white_label.font_path {path!r} not found; keeping default font.")
        return
    if not _font_covers_required_glyphs(path):
        _warn(f"custom font {name!r} is missing required punctuation glyphs "
              f"(bullet/dash/ellipsis); keeping default font to avoid tofu boxes.")
        return
    try:
        pdfmetrics.registerFont(TTFont(name, path))
        bold_path = wl.get("font_path_bold")
        ital_path = wl.get("font_path_italic")
        bold_name = name
        ital_name = name
        if bold_path and os.path.exists(bold_path):
            bold_name = name + "-Bold"; pdfmetrics.registerFont(TTFont(bold_name, bold_path))
        if ital_path and os.path.exists(ital_path):
            ital_name = name + "-Italic"; pdfmetrics.registerFont(TTFont(ital_name, ital_path))
        pdfmetrics.registerFontFamily(name, normal=name, bold=bold_name, italic=ital_name)
        FONT, FONT_BOLD, FONT_ITAL = name, bold_name, ital_name
        if bold_name == name or ital_name == name:
            _warn(f"custom font {name!r} supplied without separate bold/italic faces; "
                  f"weight/emphasis hierarchy is flattened.")
    except Exception as e:
        _warn(f"failed to register custom font {name!r} ({e}); keeping default font.")

# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_int(v, d=0):
    try: return int(round(float(v))) if v is not None else d
    except: return d

def safe_float(v, d=0.0):
    try: return float(v) if v is not None else d
    except: return d

def fmt_num(n):
    try: return f"{int(n):,}"
    except: return str(n) if n is not None else "n/a"

def fmt_pct(v):
    if v is None: return "n/a"
    try: f = float(v)
    except: return "n/a"
    # Guard: a share must be 0-100. Raw counts leaking through print as "n/a",
    # never as a bogus percentage (e.g. a count of 64 must not render "64%").
    if f < 0 or f > 100: return "n/a"
    return f"{f:.0f}%"

def delta_color(d):
    return T["success"] if d >= 0 else T["danger"]

def cell(val, bold=False, color=None, size=7.5, align="LEFT", italic=False):
    if isinstance(val, Paragraph):
        return val
    txt  = str(val) if val is not None else "n/a"
    font = FONT_BOLD if bold else (FONT_ITAL if italic else FONT)
    col  = color or T["primary"]
    amap = {"LEFT": 0, "CENTER": 1, "RIGHT": 2}
    return Paragraph(txt, ParagraphStyle(
        "tc", fontName=font, fontSize=size, textColor=col,
        leading=size * 1.35, alignment=amap.get(align, 0), wordWrap="LTR"))

def hcell(val, size=7.5):
    return cell(val, bold=True, color=colors.white, size=size, align="CENTER")

def make_styles():
    s = {}
    s["h3"]    = ParagraphStyle("h3",   fontName=FONT_BOLD, fontSize=10,
                                textColor=T["accent"], spaceAfter=2*mm, leading=13)
    s["h4"]    = ParagraphStyle("h4",   fontName=FONT_BOLD, fontSize=8.5,
                                textColor=T["primary"], spaceAfter=1.5*mm, leading=12)
    s["body"]  = ParagraphStyle("body", fontName=FONT, fontSize=9,
                                textColor=T["primary"], leading=13, spaceAfter=2*mm)
    s["muted"] = ParagraphStyle("muted",fontName=FONT, fontSize=8,
                                textColor=T["muted"], leading=11)
    s["small"] = ParagraphStyle("small",fontName=FONT, fontSize=7,
                                textColor=T["muted"], leading=10)
    return s

def std_table(headers, rows, ratios, accent=False):
    hdr_bg = T["accent"] if accent else T["primary"]
    cw = [(PW - 2*MARGIN) * r for r in ratios]
    data = [[hcell(h) for h in headers]] + rows
    t = Table(data, colWidths=cw, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  hdr_bg),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, T["bg"]]),
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ("GRID",          (0,0),(-1,-1), 0.3, T["grid"]),
        ("TOPPADDING",    (0,0),(-1,-1), 2*mm),
        ("BOTTOMPADDING", (0,0),(-1,-1), 2*mm),
        ("LEFTPADDING",   (0,0),(-1,-1), 2*mm),
        ("RIGHTPADDING",  (0,0),(-1,-1), 2*mm),
    ]))
    return t

def insight_box(text, styles):
    t = Table([[Paragraph(f"Takeaway: {text}",
                ParagraphStyle("ins", fontName=FONT_ITAL, fontSize=9,
                               textColor=T["primary"], leading=13, wordWrap="LTR"))]],
              colWidths=[PW - 2*MARGIN])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0),(-1,-1), T["soft"]),
        ("LEFTPADDING", (0,0),(-1,-1), 4*mm),
        ("TOPPADDING",  (0,0),(-1,-1), 2.5*mm),
        ("BOTTOMPADDING",(0,0),(-1,-1),2.5*mm),
        ("LINEAFTER",   (0,0),(0,-1),  2.5, T["accent"]),
    ]))
    return [t, Spacer(1, 3*mm)]

def notice_box(text, kind="info"):
    """kind: info (blue) / warn (amber). Used for the near-zero-visibility story."""
    bg   = T["soft"]     if kind == "info" else HexColor("#FEF9EC")
    line = T["accent"]   if kind == "info" else T["warn"]
    t = Table([[Paragraph(text, ParagraphStyle(
                "nb", fontName=FONT, fontSize=8.5, textColor=T["primary"],
                leading=12, wordWrap="LTR"))]],
              colWidths=[PW - 2*MARGIN])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0),(-1,-1), bg),
        ("LEFTPADDING", (0,0),(-1,-1), 4*mm),
        ("RIGHTPADDING",(0,0),(-1,-1), 4*mm),
        ("TOPPADDING",  (0,0),(-1,-1), 3*mm),
        ("BOTTOMPADDING",(0,0),(-1,-1),3*mm),
        ("LINEAFTER",   (0,0),(0,-1),  2.5, line),
    ]))
    return [t, Spacer(1, 3*mm)]

def no_data_box(section):
    t = Table([[Paragraph(
        f"No data available for {section} in this run.",
        ParagraphStyle("nd", fontName=FONT_ITAL, fontSize=9, textColor=T["muted"]))]],
        colWidths=[PW - 2*MARGIN])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0),(-1,-1), HexColor("#FEF9EC")),
        ("LEFTPADDING", (0,0),(-1,-1), 4*mm),
        ("TOPPADDING",  (0,0),(-1,-1), 3*mm),
        ("BOTTOMPADDING",(0,0),(-1,-1),3*mm),
        ("BOX",         (0,0),(-1,-1), 0.5, T["warn"]),
    ]))
    return [t, Spacer(1, 3*mm)]

def section_header(title, number):
    t = Table([[
        cell(str(number), bold=True, color=colors.white, size=11, align="CENTER"),
        cell(title, bold=True, color=colors.white, size=13),
    ]], colWidths=[12*mm, PW - 2*MARGIN - 12*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), T["primary"]),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("LEFTPADDING",   (1,0),(1,-1),  3*mm),
        ("TOPPADDING",    (0,0),(-1,-1), 2.5*mm),
        ("BOTTOMPADDING", (0,0),(-1,-1), 2.5*mm),
    ]))
    return [Spacer(1, 4*mm), t, Spacer(1, 4*mm)]


# ── KPI card ──────────────────────────────────────────────────────────────────

class KPICard(Flowable):
    def __init__(self, label, value, delta=None, positive=True,
                 width=44*mm, height=28*mm, sub=None, neutral=False):
        super().__init__()
        self.label, self.value = label, str(value) if value is not None else "n/a"
        self.delta, self.positive = delta, positive
        self.width, self.height, self.sub = width, height, sub
        self.neutral = neutral  # below significance threshold -> muted, not green/red

    def draw(self):
        c = self.canv
        w, h = self.width, self.height
        c.setFillColor(T["bg"]);   c.roundRect(0, 0, w, h, 3*mm, fill=1, stroke=0)
        c.setFillColor(T["accent"]); c.roundRect(0, h - 2*mm, w, 2*mm, 1, fill=1, stroke=0)
        c.setFillColor(T["muted"]); c.setFont(FONT, 6.5)
        c.drawString(3*mm, h - 9*mm, self.label.upper())
        c.setFillColor(T["primary"]); c.setFont(FONT_BOLD, 15)
        c.drawString(3*mm, h - 18*mm, self.value)
        if self.sub:
            c.setFillColor(T["muted"]); c.setFont(FONT, 5.5)
            c.drawString(3*mm, h - 21.5*mm, self.sub)
        if self.delta:
            col = T["muted"] if self.neutral else (T["success"] if self.positive else T["danger"])
            c.setFillColor(col); c.setFont(FONT, 7.5)
            c.drawString(3*mm, 3*mm, str(self.delta))


# ── Score gauge (donut-ish) for the headline AI Visibility Score ──────────────

class ScoreDial(Flowable):
    def __init__(self, score, size=44*mm):
        super().__init__()
        # Keep None distinct from a real 0 so a missing score renders "n/a", not 0.
        self.score = None if score is None else max(0.0, min(100.0, safe_float(score)))
        self.width = self.height = size

    def draw(self):
        c = self.canv
        s = self.width
        cx, cy, r = s/2, s/2, s/2 - 4
        # track
        c.setLineWidth(6); c.setStrokeColor(T["grid"])
        c.circle(cx, cy, r, stroke=1, fill=0)
        if self.score is None:
            c.setFillColor(T["muted"]); c.setFont(FONT_BOLD, 15)
            c.drawCentredString(cx, cy - 3, "n/a")
            return
        # arc proportional to score
        c.setStrokeColor(T["accent"])
        extent = -360.0 * (self.score / 100.0)
        c.arc(cx - r, cy - r, cx + r, cy + r, startAng=90, extent=extent)
        c.setFillColor(T["primary"]); c.setFont(FONT_BOLD, 20)
        c.drawCentredString(cx, cy - 3, f"{self.score:.0f}")
        c.setFillColor(T["muted"]); c.setFont(FONT, 6)
        c.drawCentredString(cx, cy - 12, "/ 100")


# ── Horizontal share bar (used in competitor comparison) ──────────────────────

class ShareBar(Flowable):
    def __init__(self, value, width, height=5*mm, color=None, maxval=100.0):
        super().__init__()
        self.value = safe_float(value)
        self.width, self.height = width, height
        self.color = color
        self.maxval = maxval or 100.0

    def draw(self):
        c = self.canv
        c.setFillColor(T["grid"])
        c.roundRect(0, 0, self.width, self.height, 1*mm, fill=1, stroke=0)
        frac = max(0.0, min(1.0, self.value / self.maxval))
        c.setFillColor(self.color or T["accent"])
        if frac > 0:
            c.roundRect(0, 0, max(self.width*frac, 1.2*mm), self.height, 1*mm, fill=1, stroke=0)


# ══════════════════════════════════════════════════════════════════════════════
#  COVER + PAGE TEMPLATE
# ══════════════════════════════════════════════════════════════════════════════

def draw_cover(canvas, doc, cfg):
    canvas.saveState()
    w, h = A4
    wl    = cfg.get("white_label", {}) or {}
    title = wl.get("report_title", "AI Visibility Report")
    agency= wl.get("agency_name", "")

    canvas.setFillColor(colors.white); canvas.rect(0, 0, w, h, fill=1, stroke=0)
    canvas.setFillColor(T["primary"]); canvas.rect(0, h - 14*mm, w, 14*mm, fill=1, stroke=0)
    canvas.setFillColor(T["accent"]);  canvas.rect(0, 0, 5*mm, h - 14*mm, fill=1, stroke=0)

    # Optional agency logo, top-left band
    logo = wl.get("logo_path")
    canvas.setFillColor(colors.white); canvas.setFont(FONT_BOLD, 9)
    if logo and os.path.exists(logo):
        try:
            canvas.drawImage(logo, MARGIN, h - 11.5*mm, height=9*mm, preserveAspectRatio=True,
                             mask="auto", anchor="sw")
        except Exception as e:
            _warn(f"logo {logo!r} could not be drawn ({e}); using agency name text instead.")
            canvas.drawString(MARGIN, h - 8.5*mm, agency.upper())
    else:
        if logo:
            _warn(f"white_label.logo_path {logo!r} not found; using agency name text instead.")
        canvas.drawString(MARGIN, h - 8.5*mm, agency.upper())
    canvas.setFont(FONT, 8)
    canvas.drawRightString(w - MARGIN, h - 8.5*mm, cfg.get("period_current", ""))

    canvas.setFillColor(T["primary"]); canvas.setFont(FONT_BOLD, 27)
    canvas.drawString(14*mm, h * 0.64, title)
    canvas.setFillColor(T["accent"]); canvas.rect(14*mm, h * 0.64 - 3*mm, 55*mm, 1.5, fill=1, stroke=0)

    canvas.setFillColor(T["accent"]); canvas.setFont(FONT_BOLD, 12)
    canvas.drawString(14*mm, h * 0.64 - 10*mm, cfg.get("period_current", ""))

    canvas.setFillColor(T["muted"]); canvas.setFont(FONT, 8)
    canvas.drawString(14*mm, h * 0.50, "BRAND ANALYSED")
    canvas.setFillColor(T["primary"]); canvas.setFont(FONT_BOLD, 20)
    canvas.drawString(14*mm, h * 0.465, cfg.get("brand_name", cfg.get("brand_domain", "")))
    canvas.setFillColor(T["muted"]); canvas.setFont(FONT, 10)
    canvas.drawString(14*mm, h * 0.44, cfg.get("brand_domain", ""))

    # scope line
    loc  = cfg.get("location_name", "")
    lang = cfg.get("language_name", cfg.get("language_code", ""))
    models = ", ".join(m.get("label", "") for m in cfg.get("llms_covered", []))
    canvas.setFillColor(T["muted"]); canvas.setFont(FONT, 8)
    canvas.drawString(14*mm, h * 0.40, f"Market: {loc}  •  Language: {lang}")
    canvas.drawString(14*mm, h * 0.375, f"Models covered: {models}")

    # footer
    footer = wl.get("footer_text", agency)
    canvas.setFillColor(T["muted"]); canvas.setFont(FONT, 7)
    canvas.drawCentredString(w/2, 8*mm, footer)
    canvas.restoreState()

def page_template(canvas, doc, cfg):
    canvas.saveState()
    wl     = cfg.get("white_label", {}) or {}
    brand  = cfg.get("brand_domain", "")
    period = cfg.get("period_current", "")
    footer = wl.get("footer_text", wl.get("agency_name", ""))

    canvas.setFillColor(T["primary"]); canvas.rect(0, PH - 12*mm, PW, 12*mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white); canvas.setFont(FONT, 8)
    canvas.drawString(MARGIN, PH - 7.5*mm, brand)
    canvas.drawRightString(PW - MARGIN, PH - 7.5*mm, period)

    canvas.setFillColor(T["bg"]); canvas.rect(0, 0, PW, 11*mm, fill=1, stroke=0)
    canvas.setFillColor(HexColor("#D1D5DB")); canvas.rect(0, 11*mm, PW, 0.4, fill=1, stroke=0)
    canvas.setFillColor(T["muted"]); canvas.setFont(FONT, 7)
    canvas.drawString(MARGIN, 7*mm, footer)
    canvas.drawRightString(PW - MARGIN, 7*mm, f"Page {doc.page}")
    canvas.restoreState()


# ══════════════════════════════════════════════════════════════════════════════
#  SCOPE PAGE  (prompt set shown transparently)
# ══════════════════════════════════════════════════════════════════════════════

def build_scope(cfg, styles):
    els = section_header("Scope & Prompt Set", "S")
    brand   = cfg.get("brand_name", cfg.get("brand_domain", ""))
    prompts = cfg.get("prompts", []) or []
    kws     = cfg.get("keywords", []) or []
    models  = cfg.get("llms_covered", []) or []
    comps   = cfg.get("competitors", []) or []

    els.append(Paragraph(
        f"This report measures how visible <b>{brand}</b> is inside AI-assistant answers "
        f"for the topics below. Two things are measured separately and never mixed: "
        f"<b>mentions</b> (the brand is named in the answer text) and <b>citations</b> "
        f"(the brand's domain is linked as a source). Every prompt below was generated "
        f"from your keywords and sent to each model listed; the exact wording is shown so "
        f"the method is fully transparent.", styles["body"]))
    els.append(Paragraph(
        "Scope note: live model answers (the Sections 1-3 headline) reflect the models' "
        "default region; the AI assistants take no location parameter. Market and language "
        "primarily scope the dataset-based sections (Citation Landscape, Competitor "
        "Comparison, AI Search Demand). Prompts are written in the selected language.",
        styles["small"]))
    els.append(Spacer(1, 2*mm))

    # scope facts
    kv = [
        ["Keywords / topics", ", ".join(kws) if kws else "n/a"],
        ["Models covered",    ", ".join(m.get("label","") for m in models) if models else "n/a"],
        ["Competitors",       ", ".join(c.get("domain","") for c in comps) if comps else "none provided"],
        ["Prompts generated", f"{len(prompts)} ({cfg.get('prompts_per_keyword','?')} per keyword)"],
    ]
    kv_rows = [[cell(k, bold=True), cell(v)] for k, v in kv]
    kt = Table(kv_rows, colWidths=[(PW-2*MARGIN)*0.28, (PW-2*MARGIN)*0.72])
    kt.setStyle(TableStyle([
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [colors.white, T["bg"]]),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("GRID",(0,0),(-1,-1),0.3,T["grid"]),
        ("TOPPADDING",(0,0),(-1,-1),1.8*mm),("BOTTOMPADDING",(0,0),(-1,-1),1.8*mm),
        ("LEFTPADDING",(0,0),(-1,-1),2*mm),("RIGHTPADDING",(0,0),(-1,-1),2*mm),
    ]))
    els += [kt, Spacer(1, 4*mm)]

    # the prompt set table (fixed columns)
    els.append(Paragraph("Generated prompt set", styles["h3"]))
    rows = []
    for i, p in enumerate(prompts, 1):
        rows.append([
            cell(str(i), align="CENTER"),
            cell(p.get("text", "")),
            cell(p.get("type", ""), align="CENTER"),
            cell(p.get("keyword", ""), align="CENTER"),
        ])
    if rows:
        els.append(std_table(COLUMNS["prompt_set"], rows, [0.06, 0.56, 0.20, 0.18]))
    else:
        els += no_data_box("prompt set")
    els.append(PageBreak())
    return els


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1  --  AI VISIBILITY SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def build_summary(sec, cfg, styles, num):
    els = section_header(SECTION_TITLES["summary"], num)
    if not sec:
        return els + no_data_box(SECTION_TITLES["summary"])

    # Keep raw values so a missing metric renders "n/a", never a fabricated 0.
    ment_raw  = sec.get("mention_share")
    cite_raw  = sec.get("citation_share")
    score_raw = sec.get("ai_visibility_score")
    prev  = sec.get("previous") or {}
    has_prev = bool(prev)
    weights = cfg.get("score_weights", {"mention": 0.6, "citation": 0.4})

    # Score denominator = the score's ACTUAL basis: unbranded prompts x models
    # (summary.prompts_total is the UNBRANDED count). This is distinct from
    # `cells_measured`, which counts the full live grid incl. branded cells and is used
    # only for the reliability note. Operator may override with `score_denominator`
    # (unbranded measured cells) when unbranded calls failed.
    grid = safe_int(sec.get("prompts_total")) * safe_int(sec.get("models_total"))
    score_denom = sec.get("score_denominator")
    denom = safe_int(score_denom) if score_denom is not None else grid
    cells_measured = sec.get("cells_measured")
    cells_total    = sec.get("cells_total")

    # headline row: score dial + explanation
    dial = ScoreDial(score_raw, size=42*mm)
    score_txt = f"{safe_float(score_raw):.0f}/100" if score_raw is not None else "n/a"
    denom_txt = f"  Based on {denom} unbranded model responses." if denom else ""
    expl = Paragraph(
        f"<b>AI Visibility Score {score_txt}.</b>  A single blended score, "
        f"weighting mention share at {int(weights.get('mention',0.6)*100)}% and citation "
        f"share at {int(weights.get('citation',0.4)*100)}%. Mention and citation are shown "
        f"separately below because they mean different things: being <i>named</i> in an "
        f"answer is broad visibility; being <i>cited as a source</i> is authority."
        f"{denom_txt} Figures are a point-in-time snapshot; small run-to-run differences "
        f"may be noise.",
        ParagraphStyle("expl", fontName=FONT, fontSize=9, textColor=T["primary"],
                       leading=14, wordWrap="LTR"))
    head = Table([[dial, expl]], colWidths=[46*mm, PW - 2*MARGIN - 46*mm])
    head.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                              ("LEFTPADDING",(1,0),(1,-1),4*mm)]))
    els += [head, Spacer(1, 5*mm)]

    # Significance threshold (fix #11): one response's worth of weight, min 3 points.
    # Deltas smaller than this render neutral everywhere (KPI cards and trend table).
    eps = max(3.0, 100.0 / max(denom, 1))

    def d(raw, key):
        if not has_prev or raw is None or prev.get(key) is None: return None
        return safe_float(raw) - safe_float(prev.get(key))

    dm, dc = d(ment_raw,"mention_share"), d(cite_raw,"citation_share")
    kpis = [
        KPICard("Mention Share", fmt_pct(ment_raw),
                f"{dm:+.0f} pts" if dm is not None else None, (dm or 0) >= 0,
                sub="answers naming the brand",
                neutral=(dm is not None and abs(dm) < eps)),
        KPICard("Citation Share", fmt_pct(cite_raw),
                f"{dc:+.0f} pts" if dc is not None else None, (dc or 0) >= 0,
                sub="answers citing brand domain",
                neutral=(dc is not None and abs(dc) < eps)),
        KPICard("Prompts w/ Mention",
                f"{safe_int(sec.get('prompts_with_mention'))}/{safe_int(sec.get('prompts_total'))}",
                None, True, sub="prompts with >=1 mention"),
        KPICard("Models Covered", str(safe_int(sec.get("models_total"))), None, True),
    ]
    kt = Table([[k for k in kpis]], colWidths=[44*mm]*4, rowHeights=[28*mm])
    kt.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                            ("LEFTPADDING",(0,0),(-1,-1),1*mm),("RIGHTPADDING",(0,0),(-1,-1),1*mm)]))
    els += [kt, Spacer(1, 4*mm)]

    # Reliability note (fix #2): surface excluded/failed cells if the operator tracked them.
    cells_failed = sec.get("cells_failed")
    if cells_failed:
        of_txt = f" of {safe_int(cells_total)}" if cells_total else ""
        els += notice_box(
            f"<b>Confidence:</b> {safe_int(cells_measured) if cells_measured is not None else denom}"
            f"{of_txt} live model responses were measured; {safe_int(cells_failed)} failed and were "
            f"excluded from the share denominators (not counted as \"not mentioned\").",
            kind="info")

    # trend table if we have a prior run
    if has_prev:
        els.append(Paragraph("Trend vs previous run", styles["h3"]))
        def ch(raw, p_):
            if raw is None or p_ is None: return cell("n/a", align="CENTER")
            dd = safe_float(raw) - safe_float(p_)
            col = delta_color(dd) if abs(dd) >= eps else T["muted"]
            return cell(f"{dd:+.0f}", bold=abs(dd) >= eps, color=col, align="CENTER")
        rows = [
            [cell("Mention Share (%)"),  cell(fmt_pct(ment_raw), align="CENTER"),
             cell(fmt_pct(prev.get("mention_share")), align="CENTER"), ch(ment_raw, prev.get("mention_share"))],
            [cell("Citation Share (%)"), cell(fmt_pct(cite_raw), align="CENTER"),
             cell(fmt_pct(prev.get("citation_share")), align="CENTER"), ch(cite_raw, prev.get("citation_share"))],
            [cell("AI Visibility Score"),
             cell(f"{safe_float(score_raw):.0f}" if score_raw is not None else "n/a", align="CENTER"),
             cell(f"{safe_float(prev.get('ai_visibility_score')):.0f}"
                  if prev.get("ai_visibility_score") is not None else "n/a", align="CENTER"),
             ch(score_raw, prev.get("ai_visibility_score"))],
        ]
        els.append(std_table(["Metric", cfg.get("period_current","Now"),
                              cfg.get("period_prev","Prev"), "Change"],
                             rows, [0.40, 0.20, 0.20, 0.20]))
        els.append(Paragraph(
            f"Changes smaller than ~{eps:.0f} points are shown neutral (within snapshot noise).",
            styles["small"]))
        els.append(Spacer(1, 3*mm))

    # near-zero visibility → make it actionable, not blank. Only fire on REAL measured
    # near-zeros (not on absent/None values, which mean "not measured").
    if ment_raw is not None and cite_raw is not None \
            and safe_float(ment_raw) <= 5 and safe_float(cite_raw) <= 5:
        els += notice_box(
            f"<b>The brand is effectively invisible in AI answers for this topic set.</b> "
            f"Across {safe_int(sec.get('prompts_total'))} prompts and "
            f"{safe_int(sec.get('models_total'))} models, the brand was named in "
            f"{safe_int(sec.get('prompts_with_mention'))} and cited in "
            f"{safe_int(sec.get('prompts_with_citation'))}. This is a common starting point, "
            f"not an error. The Citation Landscape and Opportunities sections below show which "
            f"sources the models rely on today and the fastest routes to appearing among them.",
            kind="warn")

    narrative = sec.get("narrative", "")
    if narrative:
        els += [Paragraph("What this means", styles["h3"]), Paragraph(narrative, styles["body"])]
    ins = sec.get("insight", "")
    if ins: els += insight_box(ins, styles)
    return els


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2  --  BY-LLM BREAKDOWN
# ══════════════════════════════════════════════════════════════════════════════

def build_by_llm(sec, cfg, styles, num):
    els = [PageBreak()] + section_header(SECTION_TITLES["by_llm"], num)
    rows_in = (sec or {}).get("rows", []) or []
    if not rows_in:
        return els + no_data_box(SECTION_TITLES["by_llm"])

    els.append(Paragraph(
        "How the brand performs in each model, measured on the same generated prompt set. "
        "Mention rate and citation rate are kept separate.", styles["muted"]))
    els.append(Spacer(1, 2*mm))

    rows = []
    for r in rows_in:
        mr = safe_float(r.get("mention_rate"))
        cr = safe_float(r.get("citation_rate"))
        rows.append([
            cell(r.get("model_label", ""), bold=True),
            cell(str(safe_int(r.get("prompts_tested"))), align="CENTER"),
            cell(str(safe_int(r.get("mentions"))), align="CENTER"),
            cell(fmt_pct(mr), align="CENTER",
                 color=T["success"] if mr >= 50 else (T["warn"] if mr >= 20 else T["danger"])),
            cell(str(safe_int(r.get("citations"))), align="CENTER"),
            cell(fmt_pct(cr), align="CENTER",
                 color=T["success"] if cr >= 30 else (T["warn"] if cr >= 10 else T["danger"])),
            cell(r.get("avg_prominence", "n/a"), align="CENTER"),
        ])
    els.append(std_table(COLUMNS["by_llm"], rows, [0.24, 0.13, 0.11, 0.13, 0.11, 0.13, 0.15]))
    els.append(Spacer(1, 3*mm))
    ins = (sec or {}).get("insight", "")
    if ins: els += insight_box(ins, styles)
    return els


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3  --  BY PROMPT & TOPIC
# ══════════════════════════════════════════════════════════════════════════════

def build_by_prompt(sec, cfg, styles, num):
    els = [PageBreak()] + section_header(SECTION_TITLES["by_prompt"], num)
    rows_in = (sec or {}).get("rows", []) or []
    if not rows_in:
        return els + no_data_box(SECTION_TITLES["by_prompt"])

    els.append(Paragraph(
        "Per prompt: which models named the brand, how prominently, and whether the brand "
        "domain was cited. A red prompt means no model named the brand. A red row with "
        "<b>Cited: Yes</b> is a citation-only gap — the brand's domain was used as a source "
        "but the assistant never wrote the brand's name.",
        styles["muted"]))
    els.append(Spacer(1, 2*mm))

    PROM_CLR = {"Named first": T["success"], "Shortlist": T["accent"],
                "Passing mention": T["warn"], "Absent": T["danger"]}
    rows = []
    for r in rows_in:
        prom    = r.get("prominence", "Absent")
        visible = bool(r.get("visible", prom != "Absent"))
        mm_list = r.get("models_mentioning", []) or []
        mm_str  = ", ".join(mm_list) if mm_list else "—"
        cited   = r.get("cited")
        cite_txt= "Yes" if cited else ("No" if cited is not None else "n/a")
        rows.append([
            cell(r.get("prompt", ""), color=T["danger"] if not visible else T["primary"]),
            cell(r.get("type", ""), align="CENTER"),
            cell(f"{mm_str}  ({len(mm_list)}/{safe_int(r.get('models_total'))})"
                 if mm_list else f"0/{safe_int(r.get('models_total'))}", align="LEFT"),
            cell(prom, bold=True, color=PROM_CLR.get(prom, T["muted"]), align="CENTER"),
            cell(cite_txt, bold=True, align="CENTER",
                 color=T["success"] if cited else T["muted"]),
        ])
    els.append(std_table(COLUMNS["by_prompt"], rows, [0.36, 0.14, 0.26, 0.14, 0.10]))
    els.append(Spacer(1, 3*mm))

    invisible = (sec or {}).get("invisible_prompts", []) or []
    if invisible:
        els += notice_box(
            "<b>Invisible prompts (no mention and no citation on any model):</b> "
            + "; ".join(invisible[:12]) + ("…" if len(invisible) > 12 else "")
            + ". These are the clearest GEO targets — see Opportunities.", kind="warn")
    ins = (sec or {}).get("insight", "")
    if ins: els += insight_box(ins, styles)
    return els


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4  --  CITATION LANDSCAPE
# ══════════════════════════════════════════════════════════════════════════════

def build_citations(sec, cfg, styles, num):
    els = [PageBreak()] + section_header(SECTION_TITLES["citations"], num)

    top_domains = (sec or {}).get("top_domains", []) or []
    top_pages   = (sec or {}).get("top_pages", []) or []
    brand_pages = (sec or {}).get("brand_cited_pages", []) or []

    # Guard on content, not on the object: an empty {top_domains:[],...} must NOT
    # print an intro promising tables that never render (fix #7).
    if not (top_domains or top_pages or brand_pages):
        return els + no_data_box(SECTION_TITLES["citations"])

    els.append(Paragraph(
        "The sources models lean on when answering these prompts. Winning citations here is "
        "how a brand earns its way into AI answers. Brand-owned rows are highlighted.",
        styles["muted"]))
    els.append(Spacer(1, 2*mm))

    if top_domains:
        els.append(Paragraph("Most-cited domains", styles["h3"]))
        rows = []
        for dmn in top_domains:
            is_brand = bool(dmn.get("is_brand"))
            rows.append([
                cell(dmn.get("domain",""), bold=is_brand,
                     color=T["accent"] if is_brand else T["primary"]),
                cell(str(safe_int(dmn.get("citations"))), align="CENTER"),
                cell(fmt_pct(dmn.get("share")), align="CENTER"),
                cell("Brand" if is_brand else "Third-party", align="CENTER",
                     bold=is_brand, color=T["accent"] if is_brand else T["muted"]),
            ])
        els.append(std_table(COLUMNS["top_domains"], rows, [0.44, 0.18, 0.20, 0.18]))
        els.append(Spacer(1, 4*mm))

    if top_pages:
        els.append(Paragraph("Most-cited pages", styles["h3"]))
        rows = []
        for pg in top_pages:
            is_brand = bool(pg.get("is_brand"))
            rows.append([
                cell(pg.get("page",""), bold=is_brand,
                     color=T["accent"] if is_brand else T["primary"]),
                cell(pg.get("domain",""), italic=True, color=T["muted"]),
                cell(str(safe_int(pg.get("citations"))), align="CENTER"),
                cell("Brand" if is_brand else "Third-party", align="CENTER",
                     bold=is_brand, color=T["accent"] if is_brand else T["muted"]),
            ])
        els.append(std_table(COLUMNS["top_pages"], rows, [0.42, 0.28, 0.14, 0.16]))
        els.append(Spacer(1, 3*mm))

    if brand_pages:
        els += notice_box("<b>Brand pages already earning AI citations:</b> "
                          + "; ".join(brand_pages[:8]), kind="info")
    elif top_domains or top_pages:
        els += notice_box("<b>No brand-owned page is currently cited</b> for these prompts. "
                          "Every citation above is going to a third party — the core GEO gap.",
                          kind="warn")
    ins = sec.get("insight", "")
    if ins: els += insight_box(ins, styles)
    return els


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 5  --  COMPETITOR COMPARISON
# ══════════════════════════════════════════════════════════════════════════════

def build_competitors(sec, cfg, styles, num):
    els = [PageBreak()] + section_header(SECTION_TITLES["competitors"], num)
    if not sec:
        return els + no_data_box(SECTION_TITLES["competitors"])
    rows_in = sec.get("rows", []) or []
    if not rows_in:
        return els + no_data_box(SECTION_TITLES["competitors"])

    live = bool(sec.get("live_basis"))
    # Column labels depend on basis so a dataset "share of voice" number never shares
    # a header with the live headline on page 1 (fix #1).
    comp_cols = COLUMNS["competitors_live"] if live else COLUMNS["competitors_dataset"]

    els.append(Paragraph(
        "Share of voice, brand vs each competitor: each entity's share of all "
        "brand+competitor mentions (and citations) on these topics — the shares sum to "
        "~100%. This is the \"who is winning AI visibility here\" view.", styles["muted"]))
    # Deterministic measurement-basis footnote (two fixed strings; boolean selects).
    # Fix #1: these SoV columns are a DIFFERENT metric from the Section 1 "Mention Share"
    # (a response rate), so the brand's number here differs from page 1 by design — in
    # BOTH modes. Say so, and note the data basis.
    if live:
        basis = ("Note: these are share-of-voice figures (share of all brand+competitor "
                 "mentions), not the Section 1 response rate — so the brand's numbers here "
                 "differ from page 1 by design. Both brand and competitors are measured "
                 "like-for-like on the same live unbranded prompt set, per model and overall.")
    else:
        basis = ("Note: these are share-of-voice figures (share of all brand+competitor "
                 "mentions), not the Section 1 response rate — so the brand's numbers here "
                 "differ from page 1 by design. In this mode BOTH the brand and competitors "
                 "come from the aggregated AI-mentions dataset (columns prefixed \"Dataset\"), "
                 "a different source from the live Section 1 headline.")
    els.append(Paragraph(basis, styles["small"]))
    els.append(Spacer(1, 2*mm))

    bar_w = (PW - 2*MARGIN) * 0.20
    max_ment = max([safe_float(r.get("mention_share")) for r in rows_in] + [1.0])
    rows = []
    for r in rows_in:
        is_brand = bool(r.get("is_brand"))
        name = r.get("name", r.get("domain",""))
        label = f"{name}  (you)" if is_brand else name
        ment = safe_float(r.get("mention_share"))
        cite = safe_float(r.get("citation_share"))
        score= safe_float(r.get("ai_visibility_score"))
        ment_cell = Table([[cell(fmt_pct(ment), align="LEFT",
                                 bold=is_brand, color=T["accent"] if is_brand else T["primary"]),
                             ShareBar(ment, bar_w, color=T["accent"] if is_brand else T["muted"],
                                      maxval=max_ment)]],
                          colWidths=[(PW-2*MARGIN)*0.09, bar_w])
        ment_cell.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                                       ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0)]))
        rows.append([
            cell(label, bold=is_brand, color=T["accent"] if is_brand else T["primary"]),
            ment_cell,
            cell(fmt_pct(cite), align="CENTER", bold=is_brand,
                 color=T["accent"] if is_brand else T["primary"]),
            cell(f"{score:.0f}", align="CENTER", bold=is_brand,
                 color=T["accent"] if is_brand else T["primary"]),
        ])
    # Build with manual style so the brand row can be tinted.
    cw = [(PW-2*MARGIN)*r for r in [0.34, 0.30, 0.18, 0.18]]
    data = [[hcell(h) for h in comp_cols]] + rows
    t = Table(data, colWidths=cw, repeatRows=1)
    style = [
        ("BACKGROUND",(0,0),(-1,0), T["primary"]),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, T["bg"]]),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("GRID",(0,0),(-1,-1),0.3,T["grid"]),
        ("TOPPADDING",(0,0),(-1,-1),2*mm),("BOTTOMPADDING",(0,0),(-1,-1),2*mm),
        ("LEFTPADDING",(0,0),(-1,-1),2*mm),("RIGHTPADDING",(0,0),(-1,-1),2*mm),
    ]
    for i, r in enumerate(rows_in, start=1):
        if r.get("is_brand"):
            style.append(("BACKGROUND",(0,i),(-1,i), T["soft"]))
            style.append(("LINEBELOW",(0,i),(-1,i), 1.2, T["accent"]))
    t.setStyle(TableStyle(style))
    els += [t, Spacer(1, 4*mm)]

    # optional per-model matrix
    by_model = sec.get("by_model", []) or []
    if by_model:
        title = "Mention share of voice by model" + ("" if live else " (ChatGPT only — dataset basis)")
        els.append(Paragraph(title, styles["h3"]))
        if not live:
            els.append(Paragraph(
                "In dataset mode only ChatGPT has a mentions dataset behind it, so this "
                "matrix covers ChatGPT only. The other models appear in the live headline.",
                styles["small"]))
        # Domain -> display name map (consistent with the main table), from rows + config.
        name_of = {}
        for r in rows_in:
            if r.get("domain"): name_of[r["domain"]] = r.get("name", r["domain"])
        for c in (cfg.get("competitors", []) or []):
            if c.get("domain"): name_of.setdefault(c["domain"], c.get("name", c["domain"]))
        # Union of competitor domains across ALL rows (fix #9: never positional).
        comp_domains = []
        for m in by_model:
            for c in (m.get("competitors", []) or []):
                d_ = c.get("domain","")
                if d_ and d_ not in comp_domains: comp_domains.append(d_)
        headers = ["LLM Model", "You"] + [name_of.get(d_, d_) for d_ in comp_domains]
        ratios  = [0.28, 0.14] + [ (0.58/max(len(comp_domains),1)) ]*len(comp_domains)
        rows2 = []
        for m in by_model:
            # look up each competitor cell BY DOMAIN KEY, not by position
            cmap = {c.get("domain",""): c.get("mention_share")
                    for c in (m.get("competitors", []) or [])}
            row = [cell(m.get("model_label",""), bold=True),
                   cell(fmt_pct(m.get("brand_mention_share")), align="CENTER",
                        bold=True, color=T["accent"])]
            for d_ in comp_domains:
                row.append(cell(fmt_pct(cmap.get(d_)), align="CENTER"))
            rows2.append(row)
        els.append(std_table(headers, rows2, ratios))
        els.append(Spacer(1, 3*mm))

    ins = sec.get("insight", "")
    if ins: els += insight_box(ins, styles)
    return els


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 6  --  AI SEARCH DEMAND
# ══════════════════════════════════════════════════════════════════════════════

def build_volume(sec, cfg, styles, num):
    els = [PageBreak()] + section_header(SECTION_TITLES["volume"], num)
    rows_in = (sec or {}).get("rows", []) or []
    if not rows_in:
        return els + no_data_box(SECTION_TITLES["volume"])
    els.append(Paragraph(
        "How much these topics are actually asked about — AI search demand (estimated LLM "
        "query usage), for context on which topics matter most to win.",
        styles["muted"]))
    els.append(Spacer(1, 2*mm))
    rows = []
    for r in rows_in:
        rows.append([
            cell(r.get("keyword","")),
            cell(fmt_num(r.get("ai_search_volume")), align="CENTER"),
        ])
    els.append(std_table(COLUMNS["volume"], rows, [0.70, 0.30]))
    els.append(Spacer(1, 3*mm))
    ins = (sec or {}).get("insight", "")
    if ins: els += insight_box(ins, styles)
    return els


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 7  --  OPPORTUNITIES & NEXT ACTIONS
# ══════════════════════════════════════════════════════════════════════════════

def build_actions(sec, cfg, styles, num):
    els = [PageBreak()] + section_header(SECTION_TITLES["actions"], num)
    actions = (sec or {}).get("actions", []) or []
    if not actions:
        return els + no_data_box(SECTION_TITLES["actions"])

    els.append(Paragraph(
        "GEO-specific moves tied to the findings above — which prompts to target, which "
        "citation sources to earn or pitch, and the content/entity gaps versus competitors.",
        styles["muted"]))
    els.append(Spacer(1, 3*mm))

    PRIO_CLR = {"High": T["success"], "Medium": T["warn"], "Low": T["accent"]}
    for idx, a in enumerate(actions, 1):
        title  = a.get("title","")
        why    = a.get("why","")
        acts   = a.get("actions","")
        effort = a.get("effort","n/a")
        impact = a.get("impact","")
        prio   = a.get("priority","Medium")

        hdr = Table([[
            Paragraph(f"<b>{idx}</b>", ParagraphStyle("an", fontName=FONT_BOLD, fontSize=12,
                      textColor=colors.white, alignment=TA_CENTER)),
            Paragraph(f"<b>{title}</b>", ParagraphStyle("at", fontName=FONT_BOLD, fontSize=10,
                      textColor=colors.white, leading=14, wordWrap="LTR")),
        ]], colWidths=[12*mm, PW - 2*MARGIN - 12*mm])
        hdr.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1), T["accent"]),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",(0,0),(-1,-1),2.5*mm),("BOTTOMPADDING",(0,0),(-1,-1),2.5*mm),
            ("LEFTPADDING",(1,0),(1,-1),3*mm),("RIGHTPADDING",(1,0),(1,-1),3*mm),
        ]))
        els.append(hdr)

        bs = ParagraphStyle("wb", fontName=FONT, fontSize=9, textColor=T["primary"],
                            leading=13, wordWrap="LTR")
        if why:
            bt = Table([[Paragraph(f"<b>Why:</b>  {why}", bs)]], colWidths=[PW - 2*MARGIN])
            bt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),T["bg"]),
                ("LEFTPADDING",(0,0),(-1,-1),4*mm),("RIGHTPADDING",(0,0),(-1,-1),4*mm),
                ("TOPPADDING",(0,0),(-1,-1),2*mm),("BOTTOMPADDING",(0,0),(-1,-1),1.5*mm)]))
            els.append(bt)
        if acts:
            act_str = acts if isinstance(acts, str) else "  ".join(acts)
            at = Table([[Paragraph(f"<b>GEO actions:</b>  {act_str}", bs)]], colWidths=[PW - 2*MARGIN])
            at.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.white),
                ("LEFTPADDING",(0,0),(-1,-1),4*mm),("RIGHTPADDING",(0,0),(-1,-1),4*mm),
                ("TOPPADDING",(0,0),(-1,-1),1.5*mm),("BOTTOMPADDING",(0,0),(-1,-1),2*mm)]))
            els.append(at)

        prio_col = PRIO_CLR.get(prio, T["muted"])
        ms = ParagraphStyle("m", fontName=FONT, fontSize=8, textColor=T["muted"], wordWrap="LTR")
        mt = Table([[
            Paragraph(f"<b>Effort:</b>  {effort}", ms),
            Paragraph(f"<b>Impact:</b>  {impact}", ms),
            Paragraph(f"<b>Priority:</b>  {prio}", ParagraphStyle("p", fontName=FONT_BOLD,
                      fontSize=8, textColor=prio_col, wordWrap="LTR")),
        ]], colWidths=[(PW - 2*MARGIN)/3]*3)
        mt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),T["soft"]),
            ("LEFTPADDING",(0,0),(-1,-1),4*mm),("RIGHTPADDING",(0,0),(-1,-1),3*mm),
            ("TOPPADDING",(0,0),(-1,-1),1.5*mm),("BOTTOMPADDING",(0,0),(-1,-1),1.5*mm),
            ("LINEABOVE",(0,0),(-1,0),0.5,T["grid"]),("VALIGN",(0,0),(-1,-1),"TOP")]))
        els += [mt, Spacer(1, 4*mm)]
    return els


# ══════════════════════════════════════════════════════════════════════════════
#  GLOSSARY
# ══════════════════════════════════════════════════════════════════════════════

def build_glossary(cfg, styles):
    els = [PageBreak()]
    t = Table([[cell(SECTION_TITLES["glossary"].upper(), bold=True, color=colors.white, size=11)]],
              colWidths=[PW - 2*MARGIN])
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),T["primary"]),
        ("TOPPADDING",(0,0),(-1,-1),3*mm),("BOTTOMPADDING",(0,0),(-1,-1),3*mm),
        ("LEFTPADDING",(0,0),(-1,-1),4*mm)]))
    els += [t, Spacer(1, 5*mm)]
    w = cfg.get("score_weights", {"mention": 0.6, "citation": 0.4})
    terms = [
        ("Mention Share",
         "The percentage of AI answers (across all tested prompts and models) in which the "
         "brand is named anywhere in the answer text. Measures broad visibility."),
        ("Citation Share",
         "The percentage of AI answers in which the brand's own domain is linked or referenced "
         "as a source. Measures authority. Mention and citation are always reported separately."),
        ("AI Visibility Score (0-100)",
         f"A single blended score: mention share weighted {int(w.get('mention',0.6)*100)}% and "
         f"citation share weighted {int(w.get('citation',0.4)*100)}%. Being named is broad "
         f"reach; being cited is harder-won authority, so both feed the score."),
        ("Share of Voice (competitor section)",
         "The Competitor Comparison uses share of voice: each entity's share of ALL "
         "brand+competitor mentions (or citations) on these topics, so the values sum to "
         "~100%. This is a different metric from the Section 1 \"Mention Share\", which is a "
         "response rate (share of answers naming the brand). The brand's SoV therefore does "
         "not equal its Section 1 headline — both are correct, they answer different questions."),
        ("Prominence",
         "How strongly the brand appears in an answer: Named first (the lead recommendation), "
         "Shortlist (one of several options), Passing mention (mentioned but not recommended), "
         "or Absent."),
        ("Prompt types",
         "Each keyword is expanded into natural user questions across four types: Informational, "
         "Comparative, Recommendation, and Branded. Branded prompts name the brand directly; the "
         "rest do not, so unbranded visibility can be isolated."),
        ("GEO — Generative Engine Optimization",
         "The practice of improving how a brand appears in AI-assistant answers, the way SEO "
         "improves how it appears in search results. GEO focuses on being mentioned and cited by "
         "large language models."),
        ("Measurement method",
         "Two sources. The live model responses to the generated prompt set (parsed for the "
         "brand name and domain) are the authoritative headline and power Sections 1-3. The "
         "aggregated AI-mentions dataset (ChatGPT/Google only) is a directional cross-check "
         "and powers the dataset sections; it can differ from the live headline because it "
         "covers a different platform and population. When they diverge by more than about 20 "
         "points, the live figures are treated as authoritative and the gap is noted."),
        ("Snapshot & run-to-run variance",
         "Each prompt is asked once, and LLM answers vary between runs. Figures are a "
         "point-in-time snapshot, shown as exact percentages for readability but not precise to "
         "the point. Small trend differences (under roughly one response's worth of weight) are "
         "shown neutral rather than as gains or losses."),
    ]
    for term, definition in terms:
        els.append(Paragraph(term, ParagraphStyle("gt", fontName=FONT_BOLD, fontSize=8.5,
                   textColor=T["accent"], spaceAfter=1.5*mm, leading=12)))
        els.append(Paragraph(definition, ParagraphStyle("gd", fontName=FONT, fontSize=9,
                   textColor=T["primary"], leading=13, spaceAfter=4*mm, wordWrap="LTR")))
    return els


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def build_pdf(data_path: str):
    global T
    with open(data_path, encoding="utf-8") as f:
        payload = json.load(f)

    cfg      = payload.get("config", {})
    sections = payload.get("sections", {})

    wl = cfg.get("white_label", {}) or {}
    T = build_theme(wl)
    apply_white_label_font(wl)
    styles = make_styles()

    output_path = cfg.get("output_path")
    if not output_path:
        output_path = os.path.splitext(data_path)[0] + ".pdf"

    # Contiguous section numbering: the counter only advances for sections that are
    # actually appended, so omitting an optional section never leaves a gap (fix #18).
    num = [0]
    def nxt():
        num[0] += 1
        return num[0]

    story = [PageBreak()]                              # cover is drawn on page 1
    story += build_scope(cfg, styles)                  # scope + prompt set (label "S")
    story += build_summary(sections.get("summary", {}), cfg, styles, nxt())
    story += build_by_llm(sections.get("by_llm", {}), cfg, styles, nxt())
    story += build_by_prompt(sections.get("by_prompt", {}), cfg, styles, nxt())
    story += build_citations(sections.get("citation_landscape", {}), cfg, styles, nxt())
    if cfg.get("competitors"):
        story += build_competitors(sections.get("competitors", {}), cfg, styles, nxt())
    if sections.get("search_volume"):
        story += build_volume(sections.get("search_volume", {}), cfg, styles, nxt())
    story += build_actions(sections.get("opportunities", {}), cfg, styles, nxt())
    story += build_glossary(cfg, styles)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=16*mm, bottomMargin=14*mm,
        title=f"{cfg.get('brand_domain','')} -- "
              f"{wl.get('report_title','AI Visibility Report')} -- {cfg.get('period_current','')}",
        subject="AI Visibility & GEO Report",
        author=wl.get("agency_name", ""),
    )
    def on_first(canvas, doc): draw_cover(canvas, doc, cfg)
    def on_later(canvas, doc): page_template(canvas, doc, cfg)
    doc.build(story, onFirstPage=on_first, onLaterPages=on_later)
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python build_report.py <data.json>")
        sys.exit(1)
    out = build_pdf(sys.argv[1])
    print(f"Report saved: {out}")
