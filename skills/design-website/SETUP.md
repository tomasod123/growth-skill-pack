# design-website setup

## What it does
Turns one row of lead data (company, services, city, contact details) into a polished single-page website mockup in a bold editorial style.
Use it for "here's what your new site could look like" outreach, web design pitches or a first visual direction for a client.

## What you need
- Python 3.8+. CSV input uses only the standard library.
- Optional, for real photos: an Unsplash developer key. Go to unsplash.com/developers > Your apps > New Application, accept the terms, then copy the **Access Key** into `UNSPLASH_ACCESS_KEY`. Free tier: 50 requests per hour (one mockup uses about 10).
- Optional, for Google Sheets input:
  - `pip install gspread google-auth google-auth-oauthlib`
  - Google Cloud Console > APIs & Services > Library: enable **Google Sheets API** and **Google Drive API**. Then APIs & Services > Credentials > Create credentials > OAuth client ID > Application type **Desktop app** > Download JSON. Put its path in `GOOGLE_OAUTH_CLIENT_FILE`.
  - Choose where the login token is stored and put that path in `GOOGLE_TOKEN_FILE` (created on first run after a browser login).
- No MCP servers.

## Install
1. Copy this folder to `~/.claude/skills/design-website/`.
2. Add the variables you want from `.env.example` to `~/.claude/skills/.env`, then `set -a; source ~/.claude/skills/.env; set +a`.
3. Test (offline unless an Unsplash key is set):
   ```bash
   python3 ~/.claude/skills/design-website/scripts/read_prospect.py --csv ~/.claude/skills/design-website/templates/example-prospects.csv --row 1 \
     | python3 ~/.claude/skills/design-website/scripts/generate_website.py --out ./design-website-output
   ```
   It prints `Website generated: design-website-output/website_example_clinic.html`.

## First run (2 minutes)
Type: `Design a website mockup for row 4 of leads.csv` (or `...for row 4 of <Google Sheet URL>`).
You get back the path of the HTML file in `./design-website-output/`, a short note on what Claude rewrote (tagline, About copy) and anything it could not fill (missing phone, thin description).

## Common errors and fixes
- **`Row N out of range`:** rows are counted from 1 and exclude the header row.
- **Placeholder photos instead of real ones:** `UNSPLASH_ACCESS_KEY` is not set in the shell (source the .env first) or the hourly limit was hit. The script prints a note when it falls back.
- **`OAuth client file not found` / Google login loop:** set `GOOGLE_OAUTH_CLIENT_FILE` to the downloaded Desktop-app JSON; delete the token file if it was created with other scopes.
- **`gspread missing`:** install the Google packages above, or export the sheet as CSV and use `--csv`.
- **Wrong or empty services grid:** the services column must be comma-separated text named `keywords` or `services`.

## Setup time
2 minutes for CSV; 10 minutes with Unsplash and Google Sheets.

## Cost per run
Free (Unsplash free tier; Google Sheets API free).
