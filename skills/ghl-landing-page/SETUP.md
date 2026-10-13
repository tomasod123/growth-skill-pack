# ghl-landing-page setup

## What it does
Builds landing, booking, application and thank-you pages for any business as a single block that pastes into a GoHighLevel Custom HTML element without style leaks, layout shift or exit links.
Ships with a starter template (GHL wrapper resets, form-first mobile layout, sticky mobile CTA) and an offline open-loop/copy audit script.

## What you need
- A GoHighLevel account with access to the funnel or website you are editing (white-label GHL works the same).
- Python 3.8+ (stdlib only) for `scripts/open_loop_audit.py`.
- Strongly recommended: the `ghl-funnel-build` skill from this pack (its `block_lint.py` and `qc_sweep.mjs` do the structure lint and phone-width fold check; Node 22+ and Chrome/Chromium).
- Optional: `~/.claude/brand/tokens.css` and `brand-guidelines.md` with your colours and fonts. Without them, give Claude the brand colour, fonts and a logo URL, or the client's website.
- Optional: git, and a clipboard tool (`pbcopy` on macOS is built in; on Linux `sudo apt install xclip`).
- No API keys, no MCP servers.

## Install
1. Copy this folder to `~/.claude/skills/ghl-landing-page/` (and `ghl-funnel-build` next to it).
2. No variables to add to `~/.claude/skills/.env`.
3. Test (offline):
   ```bash
   set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ghl-landing-page/scripts/open_loop_audit.py ~/.claude/skills/ghl-landing-page/templates/ghl-paste-skeleton.html
   ```
   It should print `info` lines and `clean`.

## First run (2 minutes)
Type: `Build a GHL landing page for a demo request: headline "Cut charting time in half", form is a GHL survey I will paste in, brand colour #2F5D50, Inter font. Paid traffic from Google Ads.`
You get back: `ghl-paste.html` in `./ghl-landing-page-output/<page-name>/`, the audit results, its byte count and version, and (on macOS) the block on your clipboard ready to paste into the Custom HTML element. Then paste your GHL survey embed into the marked wrapper and run the `ghl-funnel-build` fold check on the published URL.

## Common errors and fixes
- **CSS shows as text on the page:** GHL strips `<html>/<head>/<body>`; every rule must sit inside a `<style>` tag.
- **Grey borders or padding around the block:** the `:has(.lp-root)` resets did not match this template; zero padding/margins in GHL's Section, Row and Column style panels. If the page is clamped to ~1170px, keep the `.inner` reset in the skeleton.
- **Headline renders in Times / wrong font:** a variable is undeclared or the block does not link its own fonts. Run `block_lint.py`.
- **Page jumps on load (CLS):** CSS after markup, a font swap re-wrapping the H1, or an embed without a reserved wrapper height. See "Layout shift" in SKILL.md.
- **Visitors not tracked:** the survey embed carries `data-cookie-consent="true"`; change it to `"false"` unless you have a cookie banner.
- **Calendar widget styling ignored:** it is a cross-origin iframe. Style it in the calendar's Forms & Payment > Styles and Advanced > Custom CSS, not in the paste.

## Setup time
3 minutes.

## Cost per run
Free.
