# ai-visibility-report: setup

## What it does
Measures how often ChatGPT, Gemini, Claude and Perplexity mention and cite a brand versus its competitors, for the prompts buyers actually ask.
Outputs a white-label PDF (summary, by-model, by-prompt, citation landscape, competitors, AI search demand, next actions) plus a data JSON.

## What you need
- **A DataForSEO account with credit** (pay as you go, minimum top-up applies): https://app.dataforseo.com/register
- **DATAFORSEO_LOGIN** and **DATAFORSEO_PASSWORD**: DataForSEO dashboard > API Access (https://app.dataforseo.com/api-access). The API password is generated there and differs from your website login password.
- **MCP server (optional):** the DataForSEO MCP server (https://github.com/dataforseo/mcp-server-typescript). Not required: the bundled `scripts/dfs.py` calls the REST API directly with the same requests.
- **Python 3.9+** with packages: `pip install reportlab certifi`
- **DejaVu Sans font** (not bundled, licence-free). Install one of:
  - Linux: `sudo apt install fonts-dejavu-core` (Debian/Ubuntu) or `sudo dnf install dejavu-sans-fonts` (Fedora)
  - macOS: `brew install --cask font-dejavu`
  - Any OS: download from https://dejavu-fonts.github.io/ and set `DEJAVU_FONT_DIR` to the folder holding `DejaVuSans.ttf`, `DejaVuSans-Bold.ttf`, `DejaVuSans-Oblique.ttf`
  - `pip install matplotlib` also works (it ships DejaVu Sans and the script finds it).
  Without it the PDF falls back to Helvetica and some symbols may render as boxes.
- **Optional cost-ledger vars** (leave blank normally):
  - `DFS_LEDGER`: path of the JSONL file where `dfs.py` appends one line per paid call (endpoint, cost, run id). Default `./ai-visibility-report-output/dfs-cost-ledger.jsonl` under the folder you run from. Set a fixed path (e.g. `$HOME/dfs-cost-ledger.jsonl`) to keep one spend history across projects.
  - `DFS_RUN_ID`: label that groups ledger lines of one report run (default: today's date, `YYYYMMDD`). Set it, e.g. `DFS_RUN_ID=acme-2026-10`, when you run two reports on the same day and want each one's cost totalled separately.

## Install
1. Copy this folder to `~/.claude/skills/ai-visibility-report/`.
2. Add the variables from `.env.example` to `~/.claude/skills/.env` and fill in the two DataForSEO values.
3. Test access (free call, prints your balance only):
   ```
   set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/ai-visibility-report/scripts/dfs.py --balance; python3 ~/.claude/skills/ai-visibility-report/scripts/build_report.py 2>&1 | head -3   # balance, then usage; warns if DejaVu is missing
   ```

## First run (2 minutes)
Type to Claude: **"Run the AI visibility report for example.com against competitor1.com and competitor2.com, topics: [topic 1], [topic 2], [topic 3], United States, English."**
Claude asks the white-label questions one at a time (agency name, colours, logo), shows the generated prompt set and a cost estimate, and waits for your OK before any paid call.
You get `example.com_ai_visibility_YYYY-MM.pdf` and `.json` in `./ai-visibility-report-output/<brand-slug>/` in the folder you started Claude from.

## Common errors and fixes
- **HTTP 401 from DataForSEO:** wrong credentials. Use the API password from dashboard > API Access, not the website password, and re-run `set -a; source ~/.claude/skills/.env; set +a`.
- **40501 Invalid Field on ChatGPT live calls:** gpt-5.x rejects `max_output_tokens` and `temperature`. Drop both for `chat_gpt` only.
- **50301 overloaded on Claude live calls:** transient; retry once, then mark the cell `not_measured` (never as "not mentioned").
- **"Invalid Field" with `message_chain`:** each message is capped at 500 characters; pass a short summary of the prior answer.
- **TLS / certificate verify failed:** `pip install certifi` (the helper uses it automatically).
- **Boxes instead of bullets or dashes in the PDF:** DejaVu Sans not found; install it (see above) or set `DEJAVU_FONT_DIR`.
- **Dataset sections empty outside the US:** the ChatGPT mentions dataset is US / English only; other markets use the Google AI surface. Live sections are unaffected.

## Setup time
10 minutes.

## Cost per run
About US$2 to US$6 in DataForSEO credit per brand (20 to 40 live LLM answers at about US$0.10 each plus a few dataset calls). Competitors add no live calls. The `--balance` check is free.
