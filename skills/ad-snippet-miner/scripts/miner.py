#!/usr/bin/env python3
"""ad-snippet-miner - weekly TEXT digest of ad-worthy customer soundbites from Fathom
call recordings. No video cutting. Internal only: output is a local Markdown + HTML
digest (optionally also posted to one Slack DM or channel).

Pipeline:
  1. Pull Fathom calls (last N days) with transcripts.
  2. One `claude -p` pass per unprocessed call (Sonnet by default) returns candidate
     quotes as JSON (PRAISE / RESULTS / BEFORE), each rated 1-5 for ad use.
  3. Candidates land in a sqlite ledger with quote-hash dedupe + per-customer
     consent flags (none / verbal / written).
  4. Digest of unsent candidates -> ./ad-snippet-miner-output/digest-<week>.md/.html
     (and Slack if --slack). Zero candidates = no digest, no message.

Usage:
  miner.py --days 7 --dry-run              mine + print the digest, write/send NOTHING
  miner.py --days 7 --write                mine + write the digest files, stamp quotes as used
  miner.py --days 7 --write --slack        same, plus post to SLACK_CHANNEL_ID
  miner.py --check-slack                   verify bot token + channel (no message)
  miner.py --check-fathom                  one read-only Fathom call, prints the call count
  miner.py consent <slug> <none|verbal|written>   set a customer consent flag
  miner.py consent list                    show consent flags
  Common flags: --config config.json --out DIR

Env: FATHOM_API_KEY (required), SLACK_BOT_TOKEN + SLACK_CHANNEL_ID (optional),
MINER_CLAUDE_CMD (optional override of the `claude` command), MINER_WORKDIR (default --out:
digests + ledger.db; set it so interactive and cron runs share one ledger), MINER_CONFIG
(default --config), SNIPPET_LEDGER (optional ledger path). Load them first:
set -a; source ~/.claude/skills/.env; set +a
"""
import argparse
import hashlib
import html
import json
import os
import re
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

FATHOM_BASE = "https://api.fathom.ai/external/v1"
OUT_DEFAULT = os.path.expanduser(os.environ.get("MINER_WORKDIR", "").strip()) or os.path.join(os.getcwd(), "ad-snippet-miner-output")
CONFIG_DEFAULT = os.path.expanduser(os.environ.get("MINER_CONFIG", "").strip()) or None
CONFIG = {
    # Overridden by --config <file.json>; see config.example.json
    "business_description": "a business that runs ads (describe yours in config.json)",
    "team_names": [],          # your own people: never treated as the customer
    "consent_seed": {},        # {"customer_slug": "none|verbal|written"}
    "model": "sonnet",
    "min_rating": 3,
}
MAX_TRANSCRIPT_CHARS = 200_000
MIN_SEGMENTS = 8
DIGEST_MAX = 10

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    SSL_CTX = ssl.create_default_context()


def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] {msg}", flush=True)


def load_config(path):
    if path:
        with open(path, encoding="utf-8") as fh:
            CONFIG.update(json.load(fh))


# ---------------- ledger ----------------

def db_connect(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS consent (
      client_slug TEXT PRIMARY KEY,
      consent TEXT NOT NULL DEFAULT 'none' CHECK (consent IN ('none','verbal','written')),
      updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS processed_calls (
      recording_id TEXT PRIMARY KEY,
      title TEXT, call_date TEXT, n_candidates INTEGER,
      processed_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS quotes (
      id INTEGER PRIMARY KEY,
      quote_hash TEXT UNIQUE,
      recording_id TEXT, client_slug TEXT, category TEXT, quote TEXT, speaker TEXT,
      ts TEXT, ts_seconds INTEGER, clip_start TEXT, clip_end TEXT, rating INTEGER,
      fathom_url TEXT, call_title TEXT, call_date TEXT,
      mined_at TEXT DEFAULT (datetime('now')),
      digest_week TEXT
    );
    """)
    for slug, flag in (CONFIG.get("consent_seed") or {}).items():
        con.execute("INSERT OR IGNORE INTO consent (client_slug, consent) VALUES (?, ?)",
                    (slug, flag))
    con.commit()
    return con


def quote_hash(quote, client):
    norm = re.sub(r"[^a-z0-9]+", "", (quote or "").lower()) + "|" + (client or "")
    return hashlib.sha256(norm.encode()).hexdigest()


# ---------------- fathom ----------------

def fathom_fetch(days):
    key = os.environ.get("FATHOM_API_KEY")
    if not key:
        raise SystemExit("BLOCKER: FATHOM_API_KEY not set. Run: set -a; source ~/.claude/skills/.env; set +a")
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    meetings, cursor = [], None
    while True:
        qs = {"limit": "50", "include_transcript": "true", "created_after": since}
        if cursor:
            qs["cursor"] = cursor
        url = f"{FATHOM_BASE}/meetings?{urllib.parse.urlencode(qs)}"
        req = urllib.request.Request(url, headers={"X-Api-Key": key, "Accept": "application/json"})
        try:
            j = json.loads(urllib.request.urlopen(req, timeout=120, context=SSL_CTX).read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise SystemExit("BLOCKER: Fathom API returned 401 - FATHOM_API_KEY is wrong or revoked")
            raise
        meetings.extend(j.get("items") or [])
        cursor = j.get("next_cursor")
        if not cursor:
            break
    return meetings


def ts_to_seconds(ts):
    try:
        parts = [int(p) for p in str(ts).strip().split(":")]
    except ValueError:
        return None
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return None


def transcript_text(meeting):
    segs = meeting.get("transcript") or []
    if not isinstance(segs, list):
        return "", 0
    lines = []
    for s in segs:
        sp = (s.get("speaker") or {}).get("display_name") or "Unknown"
        lines.append(f"[{s.get('timestamp', '?')}] {sp}: {s.get('text', '')}")
    text = "\n".join(lines)
    if len(text) > MAX_TRANSCRIPT_CHARS:
        text = text[:MAX_TRANSCRIPT_CHARS] + "\n[... transcript truncated ...]"
    return text, len(segs)


# ---------------- mining pass (claude -p, Sonnet) ----------------

MINING_INSTRUCTION = """You are mining a customer call transcript for ad-worthy soundbites for {business}.

Our own team members (NEVER treat these as the customer): {team}.
Known customer slugs: {slugs}. If the customer on this call is not one of these, build a lowercase_underscore slug from their name or business.

Find verbatim quotes spoken by the CUSTOMER (the client, user or buyer) that could work in an ad or testimonial. Categories:
- PRAISE: customer praising us, the product, the service, or the experience
- RESULTS: customer stating concrete outcomes (bookings, revenue, patient numbers, hours saved, growth)
- BEFORE: customer describing the frustration or pain BEFORE working with us

For each candidate output an object:
{{"category": "PRAISE|RESULTS|BEFORE", "quote": "<verbatim>", "speaker": "<display name as shown>", "timestamp": "HH:MM:SS where the quote starts", "clip_start": "HH:MM:SS", "clip_end": "HH:MM:SS", "ad_usability": <1-5>, "client": "<slug>"}}

Rules:
- Quotes must be VERBATIM from the transcript. A quote may stitch consecutive segments from the same speaker; no paraphrasing.
- clip_start to clip_end must be roughly 5-20 seconds and contain the quote (estimate the end from the next segment's timestamp).
- ad_usability: 5 = could run in an ad today; 3 = usable with edits; only include candidates rated {min_rating} or higher.
- Speaker labels are ASR guesses and are sometimes wrong (customer lines occasionally pinned on one of our names, names misspelled). Judge from context who is really speaking; if attribution is uncertain, append "?" to the speaker value.
- Skip anything said by our team, prospects on sales calls, or third parties.
- If this is an internal call, a sales call, or has nothing usable, output [].

Respond with ONLY a JSON array. No markdown fences, no commentary. Do not use any tools.

TRANSCRIPT of "{title}" ({date}; invitees: {invitees}):
{transcript}"""


def claude_cmd():
    override = os.environ.get("MINER_CLAUDE_CMD")
    if override:
        return override.split()
    return ["claude"]


def mine_call(meeting):
    text, n_segs = transcript_text(meeting)
    if n_segs < MIN_SEGMENTS:
        return []
    invitees = ", ".join(
        f"{i.get('name') or '?'} <{i.get('email') or '?'}>"
        for i in (meeting.get("calendar_invitees") or [])[:10]
        if isinstance(i, dict)) or "unknown"
    prompt = MINING_INSTRUCTION.format(
        business=CONFIG["business_description"],
        team=", ".join(CONFIG.get("team_names") or []) or "(none listed)",
        slugs=", ".join((CONFIG.get("consent_seed") or {}).keys()) or "(none yet)",
        min_rating=CONFIG["min_rating"],
        title=meeting.get("title") or meeting.get("meeting_title") or "call",
        date=str(meeting.get("created_at") or "")[:10],
        invitees=invitees,
        transcript=text)
    # No tools are needed for this pass, so no permission mode is passed. If you add one,
    # note that --permission-mode bypassPermissions refuses to run as root.
    cmd = claude_cmd() + ["-p", "--model", CONFIG["model"]]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                       timeout=600, cwd=tempfile.gettempdir())
    if r.returncode != 0:
        raise RuntimeError(f"claude -p failed rc={r.returncode}: {(r.stderr or r.stdout)[:300]}")
    out = r.stdout.strip()
    m = re.search(r"\[.*\]", out, re.S)
    if not m:
        raise RuntimeError(f"no JSON array in claude output: {out[:300]}")
    cands = json.loads(m.group(0))
    if not isinstance(cands, list):
        raise RuntimeError("claude output parsed but is not a list")
    return cands


# ---------------- digest ----------------

CONSENT_TEXT = {"written": "written consent", "verbal": "verbal consent only"}
CONSENT_EMOJI = {"written": ":white_check_mark:", "verbal": ":speech_balloon:"}
FOOTER = ("Speaker labels are ASR guesses - verify on the video before using anything. "
          "Written consent needed before a quote goes in an ad.")


def digest_rows(con):
    rows = con.execute(
        "SELECT * FROM quotes WHERE digest_week IS NULL AND rating >= ? "
        "ORDER BY rating DESC, mined_at DESC", (CONFIG["min_rating"],)).fetchall()
    consent = {r["client_slug"]: r["consent"] for r in con.execute("SELECT * FROM consent")}
    return rows, consent


def deep_link(q):
    link = q["fathom_url"] or ""
    if link and q["ts_seconds"] is not None:
        link = f"{link}?timestamp={q['ts_seconds']}"
    return link


def build_markdown(top, consent, mined_calls, new_cands, slack=False):
    week_of = datetime.now(timezone.utc).strftime("%d %b %Y")
    b = "*" if slack else "**"
    lines = [f"{':clapper: ' if slack else '# '}{b if slack else ''}Ad soundbites - week of {week_of}{b if slack else ''}", ""]
    for i, q in enumerate(top, 1):
        flag = consent.get(q["client_slug"])
        label = CONSENT_TEXT.get(flag, "NO consent on file")
        if slack:
            label = f"{CONSENT_EMOJI.get(flag, ':warning:')} {label}"
        link = deep_link(q)
        if link:
            watch = f"<{link}|{q['ts']}>" if slack else f"[{q['ts']}]({link})"
        else:
            watch = q["ts"] or "?"
        lines.append(f"{b}{i}. [{q['category']}] {q['client_slug']} - {q['rating']}/5{b} · {label}")
        lines.append(f"> \"{q['quote']}\"")
        clip = f"clip {q['clip_start']}-{q['clip_end']}" if q["clip_start"] else "clip n/a"
        lines.append(f"Watch: {watch} · {clip} · {q['speaker']} · {q['call_title']} ({q['call_date']})")
        lines.append("")
    lines.append(f"_Mined {mined_calls} calls this run, {new_cands} new candidates. {FOOTER}_")
    return "\n".join(lines)


def build_html(top, consent, mined_calls, new_cands):
    esc = html.escape
    week_of = datetime.now(timezone.utc).strftime("%d %b %Y")
    cards = []
    for i, q in enumerate(top, 1):
        flag = consent.get(q["client_slug"])
        cls = {"written": "ok", "verbal": "warn"}.get(flag, "bad")
        link = deep_link(q)
        watch = f'<a href="{esc(link)}">{esc(q["ts"] or "?")}</a>' if link else esc(q["ts"] or "?")
        clip = f"clip {esc(q['clip_start'])}-{esc(q['clip_end'])}" if q["clip_start"] else "clip n/a"
        cards.append(
            f'<article><h2>{i}. <span class="cat">{esc(q["category"])}</span> {esc(q["client_slug"])} '
            f'<span class="rate">{q["rating"]}/5</span> <span class="c {cls}">'
            f'{esc(CONSENT_TEXT.get(flag, "NO consent on file"))}</span></h2>'
            f'<blockquote>"{esc(q["quote"])}"</blockquote>'
            f'<p class="meta">Watch: {watch} · {clip} · {esc(q["speaker"])} · '
            f'{esc(q["call_title"])} ({esc(q["call_date"])})</p></article>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ad soundbites - week of {esc(week_of)}</title>
<link rel="stylesheet" href="tokens.css">
<style>
body{{font-family:var(--font-ui,system-ui,sans-serif);background:var(--bg,#f8f8f7);color:var(--text,#1a1a1a);max-width:760px;margin:2rem auto;padding:0 1rem;line-height:1.5}}
h1{{font-family:var(--font-display,inherit)}} article{{background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:1rem 1.2rem;margin:1rem 0}}
h2{{font-size:1rem;margin:0 0 .5rem}} .cat{{color:var(--primary,#1d4ed8)}} .rate{{font-family:var(--font-data,monospace)}}
.c{{font-size:.8rem;padding:.1rem .5rem;border-radius:99px}} .ok{{background:#dcfce7}} .warn{{background:#fef3c7}} .bad{{background:#fee2e2}}
blockquote{{margin:.4rem 0;font-size:1.05rem}} .meta{{font-size:.85rem;color:#555}}
</style></head><body><h1>Ad soundbites - week of {esc(week_of)}</h1>
{''.join(cards)}
<p class="meta">Mined {mined_calls} calls this run, {new_cands} new candidates. {esc(FOOTER)}</p>
</body></html>"""


# ---------------- slack (optional; internal DM or private channel only) ----------------

def slack_api(method, payload, tok):
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
    return json.loads(urllib.request.urlopen(req, timeout=60, context=SSL_CTX).read().decode())


def open_dm(tok):
    """SLACK_CHANNEL_ID may be a channel id (C.../G...) or a user id (U.../W...) for a DM."""
    target = os.environ.get("SLACK_CHANNEL_ID", "").strip()
    if not target:
        raise SystemExit("BLOCKER: SLACK_CHANNEL_ID not set (a user id for a DM, or a private channel id)")
    if target[:1] in ("U", "W"):
        r = slack_api("conversations.open", {"users": target}, tok)
        if not r.get("ok"):
            raise RuntimeError(f"conversations.open failed: {r.get('error')}")
        return r["channel"]["id"]
    return target


def send_dm(text):
    tok = os.environ.get("SLACK_BOT_TOKEN")
    if not tok:
        raise SystemExit("BLOCKER: SLACK_BOT_TOKEN not set")
    ch = open_dm(tok)
    r = slack_api("chat.postMessage",
                  {"channel": ch, "text": text, "unfurl_links": False, "unfurl_media": False}, tok)
    if not r.get("ok"):
        raise RuntimeError(f"chat.postMessage failed: {r.get('error')}")
    return ch


# ---------------- main ----------------

def ledger_path(args):
    return os.environ.get("SNIPPET_LEDGER") or os.path.join(args.out, "ledger.db")


def run(args):
    load_config(args.config)
    con = db_connect(ledger_path(args))
    meetings = fathom_fetch(args.days)
    log(f"fathom: {len(meetings)} calls in last {args.days} days")
    mined = new_cands = 0
    for mt in meetings:
        rid = str(mt.get("recording_id") or "")
        title = mt.get("title") or mt.get("meeting_title") or "call"
        if not rid:
            continue
        if con.execute("SELECT 1 FROM processed_calls WHERE recording_id=?", (rid,)).fetchone():
            log(f"skip (already mined): {title} [{rid}]")
            continue
        if args.limit_calls and mined >= args.limit_calls:
            break
        log(f"mining: {title} [{rid}] ...")
        try:
            cands = mine_call(mt)
        except Exception as e:
            log(f"  MINING FAILED (will retry next run): {e}")
            continue
        mined += 1
        kept = 0
        for c in cands:
            try:
                rating = max(1, min(5, int(c.get("ad_usability") or 0)))
            except (TypeError, ValueError):
                rating = 1
            quote = (c.get("quote") or "").strip()
            if not quote or rating < CONFIG["min_rating"]:
                continue
            client = re.sub(r"[^a-z0-9_]+", "_", str(c.get("client") or "unknown").lower()).strip("_")
            h = quote_hash(quote, client)
            ts = str(c.get("timestamp") or "")
            cur = con.execute(
                "INSERT OR IGNORE INTO quotes (quote_hash, recording_id, client_slug, category, "
                "quote, speaker, ts, ts_seconds, clip_start, clip_end, rating, fathom_url, "
                "call_title, call_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (h, rid, client, str(c.get("category") or "?").upper()[:20], quote[:600],
                 str(c.get("speaker") or "?")[:80], ts, ts_to_seconds(ts),
                 str(c.get("clip_start") or ""), str(c.get("clip_end") or ""), rating,
                 mt.get("url") or "", title[:120], str(mt.get("created_at") or "")[:10]))
            kept += cur.rowcount
        new_cands += kept
        con.execute("INSERT OR REPLACE INTO processed_calls (recording_id, title, call_date, "
                    "n_candidates) VALUES (?,?,?,?)",
                    (rid, title[:120], str(mt.get("created_at") or "")[:10], kept))
        con.commit()
        log(f"  -> {len(cands)} raw, {kept} kept")

    unsent, consent = digest_rows(con)
    top = unsent[:DIGEST_MAX]
    if not top:
        log("zero candidates - no digest written, nothing sent (noise budget)")
        return
    if args.dry_run:
        print("\n===== DRY RUN - digest that WOULD be written =====\n")
        print(build_markdown(top, consent, mined, new_cands))
        print("\n===== END DRY RUN (nothing written or sent, quotes stay queued) =====")
        return
    if args.write or args.slack:
        week = datetime.now(timezone.utc).strftime("%G-W%V")
        os.makedirs(args.out, exist_ok=True)
        md_path = os.path.join(args.out, f"digest-{week}.md")
        html_path = os.path.join(args.out, f"digest-{week}.html")
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(build_markdown(top, consent, mined, new_cands))
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(build_html(top, consent, mined, new_cands))
        log(f"digest written: {md_path} and {html_path}")
        if args.slack:
            ch = send_dm(build_markdown(top, consent, mined, new_cands, slack=True))
            log(f"digest posted to Slack {ch}")
        ids = [r["id"] for r in unsent]
        con.executemany("UPDATE quotes SET digest_week=? WHERE id=?", [(week, i) for i in ids])
        con.commit()
        log(f"{len(unsent)} quotes stamped {week} (they will not resurface)")
    else:
        log("no --write/--slack/--dry-run flag; mined only, quotes stay queued.")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "consent":
        class A:  # consent subcommand uses MINER_WORKDIR (or ./ad-snippet-miner-output) / SNIPPET_LEDGER
            out = OUT_DEFAULT
        con = db_connect(ledger_path(A))
        if len(sys.argv) == 3 and sys.argv[2] == "list":
            for r in con.execute("SELECT client_slug, consent, updated_at FROM consent ORDER BY 1"):
                print(f"{r['client_slug']:<20} {r['consent']:<8} {r['updated_at']}")
            return
        if len(sys.argv) != 4 or sys.argv[3] not in ("none", "verbal", "written"):
            raise SystemExit("usage: miner.py consent <slug> <none|verbal|written>  |  miner.py consent list")
        slug, flag = sys.argv[2], sys.argv[3]
        con.execute("INSERT INTO consent (client_slug, consent, updated_at) VALUES (?,?,datetime('now')) "
                    "ON CONFLICT(client_slug) DO UPDATE SET consent=excluded.consent, "
                    "updated_at=datetime('now')", (slug, flag))
        con.commit()
        print(f"consent[{slug}] = {flag}")
        return

    ap = argparse.ArgumentParser(description="Mine Fathom calls for ad-worthy customer soundbites.")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--dry-run", action="store_true", help="print the digest; write and send nothing")
    ap.add_argument("--write", action="store_true", help="write digest .md + .html and stamp quotes as used")
    ap.add_argument("--slack", action="store_true", help="also post to SLACK_CHANNEL_ID (implies --write)")
    ap.add_argument("--limit-calls", type=int, default=0, help="mine at most N new calls this run")
    ap.add_argument("--config", default=CONFIG_DEFAULT, help="JSON config (see config.example.json; default $MINER_CONFIG)")
    ap.add_argument("--out", default=OUT_DEFAULT, help="output dir (digests + ledger.db; default $MINER_WORKDIR, else ./ad-snippet-miner-output)")
    ap.add_argument("--check-slack", action="store_true")
    ap.add_argument("--check-fathom", action="store_true")
    args = ap.parse_args()
    if args.check_fathom:
        print(f"Fathom ok: {len(fathom_fetch(1))} calls in the last day (read-only)")
        return
    if args.check_slack:
        tok = os.environ.get("SLACK_BOT_TOKEN")
        if not tok:
            raise SystemExit("BLOCKER: SLACK_BOT_TOKEN not set")
        print(f"DM channel ok: {open_dm(tok)} (no message sent)")
        return
    run(args)


if __name__ == "__main__":
    main()
