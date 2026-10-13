# Growth skill pack for Claude Code

28 Claude Code skills for a head of growth: Meta and Google ads audits, GoHighLevel builds and QC, landing pages and CRO, competitor video ad research, cold email, sales call coaching, AI search visibility, and quality control for anything you send. Each one is a working method with checklists, scripts and the traps that cost real time to find. They are written to work for a B2B healthcare software team and for an agency running clinics.

Every skill has a `SETUP.md`. Start there. It tells you which accounts and keys you need, exactly where to get each one, how to test access, and the first thing to type.

## How Claude Code skills work

A skill is a folder in `~/.claude/skills/` with a `SKILL.md` file. The file has a short description at the top. Claude reads every description at the start of a session, and when your request matches one, it loads that skill's full instructions and follows them, using any `scripts/`, `references/` or `templates/` in the folder. You don't call skills by command: you just ask in plain words ("audit my Meta account before launch") and the right skill switches on. You can also name it ("use ghl-survey-qc on ...") to be sure.

## Install (all skills, about 10 minutes)

Works on macOS, Linux, or Windows through WSL (native Windows is not supported: several scripts are bash and one uses `fcntl`).

1. Install Claude Code if you don't have it: `npm install -g @anthropic-ai/claude-code`, then run `claude` once and log in.
2. Base tools: Python 3.10+, **Node 22+** (some page-QC scripts need it), ffmpeg, tesseract, and Google Chrome.
   ```bash
   # macOS
   brew install python node@22 ffmpeg tesseract && brew install --cask google-chrome
   # Ubuntu / Debian (apt's nodejs is too old; use nvm, and Google's Chrome .deb rather than the chromium snap)
   sudo apt install python3 python3-venv ffmpeg tesseract-ocr
   curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash && nvm install 22
   wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && sudo apt install ./google-chrome-stable_current_amd64.deb
   ```
3. Check for name clashes, then copy the skills in. `cp -n` never overwrites an existing `.env`.
   ```bash
   mkdir -p ~/.claude/skills
   for d in skills/*/; do [ -e ~/.claude/skills/$(basename $d) ] && echo "already have: $(basename $d)"; done
   cp -R skills/* ~/.claude/skills/        # rename or skip any clash listed above first
   cp -n .env.example ~/.claude/skills/.env && chmod 600 ~/.claude/skills/.env
   ```
4. Create the shared Python environment (required on recent macOS/Homebrew and Ubuntu, which refuse plain `pip install`). Each `SETUP.md` gives the exact `pip install` line for its skill; run it inside this venv.
   ```bash
   python3 -m venv ~/.claude/skills/.venv
   ~/.claude/skills/.venv/bin/pip install --upgrade pip
   ```
   Every `SKILL.md` tells Claude to use `~/.claude/skills/.venv/bin/python3` when it exists, so you don't need to activate it before starting `claude`.
5. Fill in `~/.claude/skills/.env` only for the skills you plan to use (table below). Put real values only in this file, never in a skill's own `.env.example`. **Wrap any value containing spaces in double quotes**, e.g. `COMPANY_STREET="123 Main St"`, or `source` will break. To run a script by hand: `set -a; source ~/.claude/skills/.env; set +a; <command>` (same line, because each shell starts fresh).
6. Start `claude` in any working folder and type a skill's first prompt from the index. Outputs land in `./<skill-name>-output/` in that folder.

Safety defaults, kept on purpose: the audits are read-only (GET calls only). Anything that spends money, sends email or changes a live account asks first or needs an explicit flag. Nothing posts to Slack or deploys a page unless you set those keys.

Optional brand tokens: skills that build pages or reports look for your colours and fonts in `~/.claude/brand/tokens.css` (CSS variables such as `--brand`, `--ink`, `--bg`, `--font-display`, `--font-ui`). Without it they use a neutral default.

## Environment variables

One shared file: copy `.env.example` to `~/.claude/skills/.env`, fill in only the rows for the skills you use. Optional rows can stay blank.

| Variable | What it is | Where to get it | Used by |
|---|---|---|---|
| `AD_LIBRARY_DIR` | Folder holding index.jsonl (the library) | Any folder you choose, e.g. ~/ad-library-data; default ./ad-library-data | ad-library |
| `AD_LIBRARY_EXTRA_SCRAPES` | Optional: extra scrape globs for raw_scan.py | You set it, e.g. ./video-ad-swipe-page-output/*/*/raw_ads.json | ad-library |
| `AD_LIBRARY_MARKETS` | Your markets in priority order for fit_score, e.g. GB,IE,US | You set it; ISO country codes | ad-library |
| `AD_LIBRARY_MEDIA_BASE` | Optional: base URL if you serve the media folder | Your static host URL | ad-library |
| `AD_LIBRARY_POST_CMD` | Optional: your own sync command, run after a passing audit | You set it | ad-library |
| `ANTHROPIC_API_KEY` | Optional --summarize and --variants passes | console.anthropic.com > Settings > API keys | youtube-outliers |
| `APIFY_TOKEN` | Apify API token: runs the Meta Ads Library and YouTube transcript scrapers (pay per use) | Apify Console > Settings > API & Integrations > Personal API tokens | ad-library, static-ad-factory, video-ad-swipe-page, youtube-outliers |
| `APIFY_TRANSCRIPT_ACTOR` | Optional Apify actor for the transcript fallback (default karamelo/youtube-transcripts) | Apify Store, search 'youtube transcript', copy owner/actor-name | youtube-outliers |
| `BLITZ_API_KEY` | Optional company phone enrichment | blitz.us dashboard > API | cold-email-starter-kit |
| `BLITZ_BASE_URL` | Optional Blitz base URL override | leave blank for the default | cold-email-starter-kit |
| `CHROME_BIN` | Older name, also accepted. | You choose the value (see the skill SETUP.md) | video-ad-swipe-page |
| `CHROME_PATH` | Optional: path to Chrome/Chromium if not auto-detected | Your local Chrome install, e.g. /usr/bin/chromium | gads-audit, ghl-funnel-build, ghl-survey-qc, video-ad-swipe-page |
| `COMPANY_CITY` | Your business address line for the CAN-SPAM footer (used in copy, not by scripts) | your business address | cold-email-starter-kit |
| `COMPANY_COUNTRY` | Your business address line for the CAN-SPAM footer (used in copy, not by scripts) | your business address | cold-email-starter-kit |
| `COMPANY_NAME` | Your business address line for the CAN-SPAM footer (used in copy, not by scripts) | your business address | cold-email-starter-kit |
| `COMPANY_STATE` | Your business address line for the CAN-SPAM footer (used in copy, not by scripts) | your business address | cold-email-starter-kit |
| `COMPANY_STREET` | Your business address line for the CAN-SPAM footer (used in copy, not by scripts) | your business address | cold-email-starter-kit |
| `COMPANY_ZIP` | Your business address line for the CAN-SPAM footer (used in copy, not by scripts) | your business address | cold-email-starter-kit |
| `DATAFORSEO_LOGIN` | DataForSEO API login | https://app.dataforseo.com/api-access (DataForSEO dashboard > API Access) | ai-visibility-report, gads-audit |
| `DATAFORSEO_PASSWORD` | DataForSEO API password (not the website login password) | https://app.dataforseo.com/api-access (DataForSEO dashboard > API Access) | ai-visibility-report, gads-audit |
| `DEFAULT_REPLY_TO_EMAIL` | Optional reply-to address | your choice; usually blank | cold-email-starter-kit |
| `DEJAVU_FONT_DIR` | Optional: folder with DejaVuSans*.ttf if not in a system font folder | https://dejavu-fonts.github.io/ or install fonts-dejavu-core (apt) / font-dejavu (brew cask) | ai-visibility-report |
| `DFS_LEDGER` | Optional: path of the per-call cost ledger | Defaults to ./ai-visibility-report-output/dfs-cost-ledger.jsonl | ai-visibility-report |
| `DFS_RUN_ID` | Optional: label grouping one run's cost ledger lines | Any text you choose, e.g. brand-2026-01 | ai-visibility-report |
| `DYNADOT_API_KEY` | Domain search, purchase and nameserver switch | dynadot.com > My Info (Tools) > API > generate key, then add your IP to the API whitelist | cold-email-starter-kit |
| `FATHOM_API_KEY` | Reads your Fathom meetings and transcripts | Fathom > Settings > API Access (Integrations) > Generate API key | ad-snippet-miner |
| `FOLD_IFRAME_HOSTS` | Optional. Extra iframe host(s) for fold.mjs on white-label accounts | Same domain as GHL_WIDGET_HOST, without https:// | ghl-survey-qc |
| `GADS_AUDIT_OWNER` | Optional: name shown in the "who" column and the email greeting (default "PPC manager"). | You choose the value (see the skill SETUP.md) | gads-audit |
| `GADS_AUDIT_SENDER` | Optional: name that signs the draft email. | You choose the value (see the skill SETUP.md) | gads-audit |
| `GHL_API_KEY` | GoHighLevel Private Integration token for one sub-account (scopes listed in each skill SETUP.md) | GHL sub-account > Settings > Private Integrations > Create new integration; tick the scopes the skill SETUP.md lists, copy the token once (it is shown only once) | front-desk-sales-kit, ghl-account-audit, ghl-funnel-backend, ghl-funnel-build, ghl-survey-qc, lp-webhook-tracking, meta-ads-analyst, setter-call-audit |
| `GHL_LOCATION_ID` | GoHighLevel sub-account (location) id | GHL sub-account > Settings > Business Profile (Location ID), or the id after /location/ in the GHL URL | front-desk-sales-kit, ghl-account-audit, ghl-funnel-backend, ghl-funnel-build, ghl-survey-qc, lp-webhook-tracking, meta-ads-analyst, setter-call-audit |
| `GHL_PIPELINE_ID` | Optional pipeline to audit | python3 scripts/ghl_pull.py --list-pipelines | meta-ads-analyst |
| `GHL_WEBHOOK_URL` | The workflow's inbound webhook URL | GHL sub-account > Automation > Workflows > your workflow > Inbound Webhook trigger > copy URL | lp-webhook-tracking |
| `GHL_WIDGET_HOST` | Optional. White-label link domain that serves your widgets | The iframe src in the survey's embed code (Sites > Surveys > Integrate) | ghl-survey-qc |
| `GOOGLE_ADS_API_VERSION` | Optional: API version override if the default has been sunset (e.g. v26). | You choose the value (see the skill SETUP.md) | gads-common |
| `GOOGLE_ADS_CLIENT_ID` | OAuth client id (shared) | Google Cloud Console > APIs & Services > Credentials > OAuth client ID > Desktop app | gads-audit, gads-common |
| `GOOGLE_ADS_CLIENT_SECRET` | OAuth client secret (shared) | Same Desktop app OAuth client | gads-audit, gads-common |
| `GOOGLE_ADS_CUSTOMER_ID` | Optional default client account id, 10 digits, no dashes. | Account id shown in Google Ads, 10 digits, no dashes | gads-audit, gads-common |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | API developer token (shared with gads-common) | Google Ads manager account > Tools > API Center | gads-audit, gads-common |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | Manager account id, no dashes (shared) | Top right of Google Ads in the manager account | gads-audit, gads-common |
| `GOOGLE_ADS_REFRESH_TOKEN` | Refresh token (shared) | python3 ~/.claude/skills/gads-common/scripts/gads.py login --save | gads-audit, gads-common |
| `GOOGLE_OAUTH_CLIENT_FILE` | Path to Google OAuth desktop client JSON (Sheets input only) | Google Cloud Console > APIs & Services > Credentials > Create credentials > OAuth client ID > Desktop app > Download JSON (enable Sheets API and Drive API first) | design-website |
| `GOOGLE_TOKEN_FILE` | Path where the Google login token is saved (Sheets input only) | Any local path you choose; created on first browser login | design-website |
| `INSTANTLY_API_KEY` | Create campaigns, add leads, pull analytics (if sending with Instantly) | app.instantly.ai > Settings > Integrations > API Keys (API v2 key) | cold-email-starter-kit |
| `LP_TEST_MARKER` | Optional. String every test email contains so the workflow's Real-enquiry branch skips client alerts (default +lptest) | You choose it; use the same string in the workflow If/Else | lp-webhook-tracking |
| `META_ACCESS_TOKEN` | Meta Marketing API token, read-only (ads_read) | Meta Business Settings > Users > System users > Generate new token, scope ads_read | meta-ads-analyst, meta-launch-audit |
| `META_AD_ACCOUNT_ID` | Ad account to pull (live mode) | Ads Manager account dropdown, or Business Settings > Accounts > Ad accounts | meta-ads-analyst, meta-launch-audit |
| `META_CAMPAIGN_ID` | Optional campaign pin | Ads Manager > Campaigns > Campaign ID column | meta-ads-analyst |
| `META_GRAPH_VERSION` | Optional Graph API version override (default v21.0) | developers.facebook.com/docs/graph-api/changelog, pick the current version | meta-ads-analyst, meta-launch-audit |
| `MINER_CLAUDE_CMD` | Optional: override the Claude CLI command used for the mining pass (default: claude). | You choose the value (see the skill SETUP.md) | ad-snippet-miner |
| `MINER_CONFIG` | Default config JSON path when --config is not passed | Copy config.example.json into MINER_WORKDIR and edit | ad-snippet-miner |
| `MINER_SLACK` | Set to 1 so the cron run also posts to Slack (optional) | Optional; needs SLACK_BOT_TOKEN + SLACK_CHANNEL_ID | ad-snippet-miner |
| `MINER_TZ` | Timezone for the Monday-morning cron gate (default Europe/London) | Your IANA timezone name, e.g. America/New_York | ad-snippet-miner |
| `MINER_WORKDIR` | One folder for digests + ledger.db, shared by interactive and cron runs (keep outside ~/.claude/skills/) | You choose, e.g. $HOME/ad-snippet-miner-output | ad-snippet-miner |
| `NETLIFY_ACCOUNT_SLUG` | Optional: Netlify team to create the site in | Netlify > Team settings > General > Team details (team slug) | video-ad-swipe-page |
| `NETLIFY_AUTH_TOKEN` | Optional: publish the page with scripts/deploy.sh | Netlify > User settings > Applications > Personal access tokens > New access token | video-ad-swipe-page |
| `NODE_BIN` | Optional: path to Node 22+ if `node` on PATH is older (module 3 needs the built-in WebSocket). | You choose the value (see the skill SETUP.md) | gads-audit |
| `OPENAI_API_KEY` | OpenAI API key: Whisper transcription, image generation for static ads (optional in most skills) | https://platform.openai.com/api-keys | front-desk-sales-kit, meta-launch-audit, setter-call-audit, static-ad-factory |
| `OPENROUTER_API_KEY` | Optional AI company analysis (gpt-4o-mini) | openrouter.ai > Keys | cold-email-starter-kit |
| `OUTLIERS_MODEL` | Optional Anthropic model id for --summarize / --variants (default claude-sonnet-4-5) | docs.anthropic.com > Models | youtube-outliers |
| `PROSPEO_API_KEY` | Lead search and export (credits) | app.prospeo.io > Settings > API | cold-email-starter-kit |
| `PSI_API_KEY` | Optional PageSpeed Insights key for field data | Google Cloud Console > enable PageSpeed Insights API > Credentials > API key | gads-audit |
| `RAPIDAPI_KEY` | Optional LinkedIn profile and news enrichment | rapidapi.com > Apps > default application > Authorization; subscribe to LinkedIn Bulk Data Scraper and OpenWebNinja | cold-email-starter-kit |
| `SENDER_EMAIL_PREFIX_1` | Local part of inbox 1 per domain | you choose, e.g. jane | cold-email-starter-kit |
| `SENDER_EMAIL_PREFIX_2` | Local part of inbox 2 per domain | you choose, e.g. janedoe | cold-email-starter-kit |
| `SENDER_FIRST_NAME` | Persona first name on the inboxes | you choose, e.g. Jane | cold-email-starter-kit |
| `SENDER_LAST_NAME` | Persona last name on the inboxes | you choose | cold-email-starter-kit |
| `SLACK_BOT_TOKEN` | Optional: Slack bot token to post summaries (scope chat:write) | api.slack.com/apps > your app > OAuth & Permissions > Bot User OAuth Token (scope chat:write) | ad-library, ad-snippet-miner, meta-ads-analyst, setter-call-audit |
| `SLACK_CHANNEL_ID` | Optional: Slack channel to post summaries to | Slack channel > channel name > About > Channel ID | ad-library, ad-snippet-miner, meta-ads-analyst, setter-call-audit |
| `SMARTLEAD_API_KEY` | Create campaigns, add leads, pull analytics (if sending with Smartlead) | app.smartlead.ai > Settings > API Keys > Create | cold-email-starter-kit, email-deliverability-audit |
| `SNIPPET_LEDGER` | Optional: full path to the sqlite ledger (default: <MINER_WORKDIR or --out>/ledger.db). Usually leave blank and set MINER_WORKDIR. | You choose the value (see the skill SETUP.md) | ad-snippet-miner |
| `SUPABASE_SERVICE_KEY` | Optional service_role key for --supabase | Supabase project > Project Settings > API | gads-audit |
| `SUPABASE_URL` | Optional, only for --supabase history tables | Supabase project > Project Settings > API | gads-audit |
| `SWIPE_OUTPUT_DIR` | Optional: where work dirs are created | Any folder; default ./video-ad-swipe-page-output | video-ad-swipe-page |
| `TUBELAB_API_KEY` | Optional source with pre-computed outlier ratios (paid credits) | tubelab.net > account > API | youtube-outliers |
| `UNSPLASH_ACCESS_KEY` | Unsplash API access key for real stock photos (optional) | unsplash.com/developers > Your apps > New Application > Access Key | design-website |
| `YOUTUBE_API_KEY` | Search and video stats via YouTube Data API v3 | console.cloud.google.com > APIs & Services > Library > YouTube Data API v3 > Enable; Credentials > Create credentials > API key | youtube-outliers |
| `ZAPMAIL_API_KEY` | Connect domains, create and export sending inboxes | zapmail.ai dashboard > Settings > API | cold-email-starter-kit |

## Skill index

Each skill folder has `SKILL.md` (what Claude follows), `SETUP.md` (what you follow) and `.env.example`.

### Meta ads

| Skill | What it does | Setup | First thing to type |
|---|---|---|---|
| [`meta-ads-analyst`](skills/meta-ads-analyst/SETUP.md) | Senior Meta ads analyst: screenshots, CSV exports or live pulls in, a graded money / pipeline / diagnostics read and a call per ad out. | 25 min | "Here are my Ads Manager screenshots for the last 14 days. Be my Meta ads analyst: grade it against my targets, find the constraint, and tell me what to scale, kill or change this week." |
| [`meta-launch-audit`](skills/meta-launch-audit/SETUP.md) | Pre-launch gate and weekly live check for any Meta campaign, ending in a DO NOT LAUNCH / LAUNCH + fix / READY verdict. | 15 min | "Run the meta launch audit on our ad account before we switch on. Business location is <postcode>, town <town>, market UK, local mode." |
| [`static-ad-factory`](skills/static-ad-factory/SETUP.md) | Competitor-researched, AI-rendered static ads in all three Meta sizes, QC'd and ranked into a launch order. | 20 min | "Use static-ad-factory: research what static ads are working for <niche> in <country>, then write 30 concepts for <offer> aimed at <audience>. Stop before rendering so I can approve the brief." |

### GoHighLevel

| Skill | What it does | Setup | First thing to type |
|---|---|---|---|
| [`ghl-account-audit`](skills/ghl-account-audit/SETUP.md) | Read-only pre-launch sweep of a whole GHL sub-account, ranked P0/P1/P2 with a VA-ready fix list. | 10 min | "Audit the GHL account for Clinic A before we turn the ads on. Real address is <address>, main line is <phone>, market US." |
| [`ghl-funnel-backend`](skills/ghl-funnel-backend/SETUP.md) | Wire the workflows, confirmations, calendar merge fields, links and QR codes behind a GHL funnel so converted leads get the right message. | 10 min | "Wire the backend for our demo-request funnel: nudge workflow, booking confirmation, and check the calendar and meeting link. Calendar id <id>." |
| [`ghl-funnel-build`](skills/ghl-funnel-build/SETUP.md) | Build and QC a full GoHighLevel funnel with the checks that catch silent failures before traffic hits it. | 10 min | "Run ghl-funnel-build QC on block.txt and on https://<your-funnel-domain>/demo-booking, form selector #lead-form input." |
| [`ghl-survey-qc`](skills/ghl-survey-qc/SETUP.md) | QC a GHL survey or form from its public widget page and check its Next button clears the fold on phones. | 10 min | "QC the survey on https://example.com/apply before it goes live. Survey id <id>. Check desktop and mobile." |

### Landing pages and CRO

| Skill | What it does | Setup | First thing to type |
|---|---|---|---|
| [`design-website`](skills/design-website/SETUP.md) | Turn one row of lead data into a polished single-page website mockup for outreach or pitching. | 2 min | "Design a website mockup for row 4 of leads.csv" |
| [`form-cro`](skills/form-cro/SETUP.md) | Cut form friction on lead, demo, contact and application forms without losing the data sales needs. | 2 min | "Use form-cro on our demo request form: first name, last name, work email, phone, company, company size, role, how did you hear about us, message. Completion is 18%." |
| [`ghl-landing-page`](skills/ghl-landing-page/SETUP.md) | Build landing, booking and thank-you pages that paste cleanly into a GoHighLevel Custom HTML block. | 3 min | "Build a GHL landing page for a demo request: headline "Cut charting time in half", form is a GHL survey I will paste in, brand colour #2F5D50, Inter font. Paid traffic from Google Ads." |
| [`lp-webhook-tracking`](skills/lp-webhook-tracking/SETUP.md) | Fast custom landing-page forms posting to one GHL webhook, with a tag per page and full Google Ads detail on every lead. | 30 min | "Wire the new landing page /fue-consult/ to our GHL webhook with page tagging and Google Ads tracking, then give me the test steps." |
| [`optimize-ppc-lp`](skills/optimize-ppc-lp/SETUP.md) | Full audit-and-rewrite workflow for a landing page receiving Google or Meta ad traffic. | 3 min | "Optimize this PPC landing page: https://example.com/demo. Traffic is Google Ads search on "clinical documentation AI". Goal is demo requests. Built in Webflow." |
| [`page-cro`](skills/page-cro/SETUP.md) | Audit any marketing page for conversion problems and get prioritised fixes and copy alternatives. | 2 min | "Run page-cro on https://example.com/pricing. Traffic is mostly Google Ads, goal is demo requests, current conversion about 2%." |

### Google Ads

| Skill | What it does | Setup | First thing to type |
|---|---|---|---|
| [`gads-audit`](skills/gads-audit/SETUP.md) | Read-only Google Ads setup-and-audit agent: account audit, keyword research and market size, landing page, competitors, then an action sheet and draft email. | 40 min | "Run a Google Ads audit on account XXXXXXXXXX. The ads should point at https://example.com/landing-page and the priority area is Chicago. Start with the account audit only." |
| [`gads-common`](skills/gads-common/SETUP.md) | Shared read-only Google Ads API access: one stdlib script for accounts, snapshots and any GAQL query. | 30 min | "List our Google Ads accounts, then give me a 7-day snapshot of the first one: are the ads live, where do they point, and which conversions count?" |

### Video and creative research

| Skill | What it does | Setup | First thing to type |
|---|---|---|---|
| [`ad-library`](skills/ad-library/SETUP.md) | A local, compounding JSONL library of competitor and own-client video ads you can query before paying for research again. | 5 min | "What ads do we already have in the ad library for healthcare software demo offers in the US?" |
| [`ad-snippet-miner`](skills/ad-snippet-miner/SETUP.md) | Weekly digest of verbatim customer soundbites from Fathom calls, ready to brief into ads. | 10 min | "Run ad snippet miner on the last 7 days as a dry run." |
| [`video-ad-swipe-page`](skills/video-ad-swipe-page/SETUP.md) | Competitor video ads from the Meta Ads Library, picked on fit to your offer, turned into ready-to-film scripts on one page. | 10 min | "Build a video ad swipe page for my-saas: the offer is "book a demo" of our AI scribe, profile b2b, markets US then GB, budget $5." |
| [`youtube-outliers`](skills/youtube-outliers/SETUP.md) | Find YouTube videos beating their channel's normal views, in your niche or adjacent ones, and steal the hook pattern. | 10 min | "Find YouTube outliers in my niche from the last 14 days and tell me which hooks to steal." |

### Cold email and outbound

| Skill | What it does | Setup | First thing to type |
|---|---|---|---|
| [`campaign-copywriting`](skills/campaign-copywriting/SETUP.md) | Writes a cold email campaign with you in four confirmed steps, then QA-scores it and saves paste-ready copy plus variants.yaml. | 2 min | "Use campaign-copywriting to write a cold email campaign for https://example.com targeting [job title] at [company type]. Proof point: [result]." |
| [`cold-email-starter-kit`](skills/cold-email-starter-kit/SETUP.md) | Zero to a live cold email campaign: domains, warmed inboxes, a lead list, copy and upload, with scripts for each step. | 45 min | "Use the cold-email-starter-kit skill. I'm new to cold email: check my credentials and tell me what I still need before my first campaign." |
| [`email-deliverability-audit`](skills/email-deliverability-audit/SETUP.md) | Audits a Smartlead sending fleet (DNS auth, inbox health, reply and bounce rates, optional placement test) and writes a prioritised fix list. | 10 min | "Run the email-deliverability-audit on my Smartlead account (skip the spam placement test)." |
| [`spam-word-checker`](skills/spam-word-checker/SETUP.md) | Standing guardrail that flags spam-trigger words, phishing language and bad closeout lines in cold email copy and rewrites them. | 1 min | "Spam word check this cold email: [paste subject and body]" |

### Sales

| Skill | What it does | Setup | First thing to type |
|---|---|---|---|
| [`front-desk-sales-kit`](skills/front-desk-sales-kit/SETUP.md) | Mine real call recordings for objections, then render a branded one-page cheat sheet and a full booking playbook from one config. | 5 min | "Build a front-desk sales kit for [business name]: offer is [offer and terms], booked call is a [consultation/demo], brand colours [hex], logo at [path]. Use the starter objection checklist for now." |
| [`setter-call-audit`](skills/setter-call-audit/SETUP.md) | Pull a setter's GHL call recordings, transcribe them locally and score each call on an 8-part rubric with quotes, timestamps and drills. | 30 min | "Audit my setter's calls from the last 7 days." |

### SEO and AI search

| Skill | What it does | Setup | First thing to type |
|---|---|---|---|
| [`ai-visibility-report`](skills/ai-visibility-report/SETUP.md) | White-label PDF showing how often ChatGPT, Gemini, Claude and Perplexity mention and cite a brand versus competitors. | 10 min | "Run the AI visibility report for example.com against competitor1.com and competitor2.com, topics: [topic 1], [topic 2], [topic 3], United States, English." |

### Quality control

| Skill | What it does | Setup | First thing to type |
|---|---|---|---|
| [`outcome-first`](skills/outcome-first/SETUP.md) | Kills word salad: every message leads with the one thing the reader must do, by when. | 2 min | "Outcome first this. The reader is the client's practice manager." |
| [`persona-qc`](skills/persona-qc/SETUP.md) | Parallel reader lenses find what the client will catch, then one agent fixes it once and proves it. | 3 min | "Persona QC this landing page: ./site/index.html. The reader is a clinic owner. Facts are in ./FACTS.md." |

## Where to start

- Week one: `gads-common` + `meta-launch-audit` (read-only access to both ad platforms), then `ghl-account-audit` on one sub-account.
- Creative research: `video-ad-swipe-page` feeds `ad-library`; `youtube-outliers` for organic hooks.
- Before anything goes to a customer or the public: `persona-qc`, then `outcome-first`.

## Notes

- Costs per run are in each `SETUP.md`. The paid APIs here are Apify, DataForSEO, OpenAI, Prospeo and the email senders; every paid script either previews the cost or has a cap.
- Healthcare: several skills carry compliance checks (UK ASA/CAP, Meta health and wellness ad rules, HIPAA notes for US forms and tracking pixels). They are guardrails, not legal advice.
- Sources: page-cro and form-cro are adapted from an open-source marketing skills collection (credited in their `SETUP.md`). The four cold email skills are adapted from a publicly shared cold email starter kit; check the original's terms before you redistribute them.

## Data and reporting (7 skills)

Start with **growth-data-hub**: `--demo` shows the full report with no keys.

- **growth-data-hub**: One command pulls Meta, Google Ads, GA4, Clarity and GoHighLevel into one funnel and tells you the 5 things to do this week. Setup about 60 min. See `skills/growth-data-hub/SETUP.md`.
- **meta-weekly-account-report**: Week-over-week Meta ads report with the best ad, the ads to kill, fatigue and a short do-this-week list. Setup about 15 min. See `skills/meta-weekly-account-report/SETUP.md`.
- **lead-flow-watchdog**: Daily check that Meta leads are actually arriving in GoHighLevel, with alerts on breaks, drops and CPL spikes. Setup about 20 min. See `skills/lead-flow-watchdog/SETUP.md`.
- **client-performance-report**: Turns a growth-data-hub report into an internal one-pager and a warm, client-branded draft report. Setup about 10 min. See `skills/client-performance-report/SETUP.md`.
- **analytics-tracking**: Plan, set up or audit analytics and conversion tracking: GA4 events, GTM, UTMs and key events. Setup about 5 min. See `skills/analytics-tracking/SETUP.md`.
- **analytics-access-setup**: Step-by-step read access to GA4, Search Console, Google Ads, Clarity, Meta and GoHighLevel, with a check for each. Setup about 45 min. See `skills/analytics-access-setup/SETUP.md`.
- **search-console**: Read-only Google Search Console: performance, queries, pages, sitemaps, index status, opportunities and redirect checks. Setup about 15 min. See `skills/search-console/SETUP.md`.
