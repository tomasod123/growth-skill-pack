---
name: design-website
description: Generate a polished single-page mockup website for a prospect or client from one row of lead data (CSV or Google Sheet), in a bold editorial agency style. Use when the user asks to design a website, create a website mockup, build a prospect homepage, make a "what your site could look like" page for outreach, or pitch web design. Not for GoHighLevel paste blocks (use ghl-landing-page).
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./design-website-output/`.

# Design Website

## Goal
Generate a polished, single-page HTML mockup of a prospect's website. The look is an editorial agency style (inspired by buildinamsterdam.com): bold uppercase type, warm off-white background, editorial grid layouts, one warm accent colour. Use it to pitch web design, show a prospect "your new site" in cold outreach, or give a client a first visual direction.

Before running scripts: `set -a; source ~/.claude/skills/.env; set +a`

## Inputs
One of:
- **CSV file** + **row number** (1-indexed, excluding header). A template is in `templates/example-prospects.csv`.
- **Google Sheet URL** + **row number**, optional **worksheet name** (default first sheet).
- Or a hand-written JSON object with the keys below.

### Columns (case-insensitive, flexible matching)
| Column | Maps to |
|---|---|
| company_name / company / organization_name | Business name (hero, nav, footer) |
| description / about | About section + hero subtitle |
| keywords / services | Services grid (comma-separated, up to 8) |
| phone / phone_number | Contact section + Get In Touch fallback |
| email / contact_email | Contact section + Get In Touch button |
| address / full_address | Contact section |
| city, state, country | Location line, image search |
| industry / category | Stock photo search queries |
| first_name, last_name | Owner credit in About |
| title / role | Owner role |

## Scripts
- `scripts/read_prospect.py`: one row from CSV or Google Sheets to JSON on stdout.
- `scripts/generate_website.py`: prospect JSON (stdin or `--input`) to a self-contained HTML file.

## Process

### Step 1: Read prospect data
```bash
python3 ~/.claude/skills/design-website/scripts/read_prospect.py --csv leads.csv --row 3
# or
python3 ~/.claude/skills/design-website/scripts/read_prospect.py --url "SHEET_URL" --row 3 --worksheet "Leads"
```

### Step 2: Generate the website
```bash
python3 ~/.claude/skills/design-website/scripts/read_prospect.py --csv leads.csv --row 3 | \
  python3 ~/.claude/skills/design-website/scripts/generate_website.py
# or from a JSON file, to a chosen folder
python3 ~/.claude/skills/design-website/scripts/generate_website.py --input prospect.json --out ./design-website-output
```

### Step 3: Improve and check
1. Open the file (`open` on macOS, `xdg-open` on Linux).
2. Read the copy as the prospect would. The generator uses their description as-is; rewrite the hero subtitle and About text if the source description is thin or generic.
3. For healthcare prospects, check images and copy against the industry's ad rules before using the mockup in outreach (no before/after claims, no prescription-only medicine names on UK pages).
4. Check at phone width (390px) and desktop (1440px). If you have the `ghl-funnel-build` skill, `qc_sweep.mjs` checks overflow and broken images at every width.
5. If you have brand tokens for the prospect (their logo colour, font), edit the `:root` variables at the top of the generated file.

### Step 4: Share (optional)
Upload the HTML to any static host (Netlify Drop, Vercel, GitHub Pages, S3) to get a link for the outreach email. Do not send anything to the prospect without the user's approval.

## Outputs
- `./design-website-output/website_<company_slug>.html`: self-contained HTML, viewable in any browser. CSS is inline; images are external URLs (Unsplash or picsum placeholders).

## Environment
- `UNSPLASH_ACCESS_KEY` (optional): real stock photos matched to industry and services. Without it the script uses picsum.photos placeholders.
- Google Sheets only: `GOOGLE_OAUTH_CLIENT_FILE` (OAuth desktop client JSON) and `GOOGLE_TOKEN_FILE` (where the login token is stored). CSV needs nothing.

## Design system
- **Fonts:** Inter (UI and display) + Cormorant Garamond italic (subtitles), from Google Fonts.
- **Colours:** off-white `#F2EFE6`, black, white, terracotta accent `#C38133`. Change them in `:root`.
- **Type:** bold uppercase display (clamp 56-110px), section heads (32-56px), serif body (18px).
- **Layout:** 50/50 split hero (image collage left, name and tagline right), 2-column About with inset image, services card grid, full-width image break, contact rows, footer.
- **Buttons:** bordered, uppercase, letter-spaced.

## Edge cases
- Missing columns: sensible defaults (generic tagline, generic About line).
- No email: the Get In Touch button falls back to `tel:` then `#contact`.
- No Unsplash key or fewer than 8 photos returned: picsum placeholders.
- Long company names: the hero splits the name into 2-word lines; CSS wraps responsively.
- Special characters: HTML-escaped.
- Prices or numbers set in a display serif: add `font-variant-numeric: lining-nums` or "£0" can read as "£o".
