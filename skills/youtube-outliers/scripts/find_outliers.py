#!/usr/bin/env python3
"""Find YouTube outlier videos (views far above the channel's normal) in your own niche
or in adjacent niches, pull transcripts, tag title/hook patterns, and write a local report.

  python3 find_outliers.py --config outliers-config.json --mode own
  python3 find_outliers.py --config outliers-config.json --mode adjacent --days 30
  python3 find_outliers.py --mode own --keywords "dental implants cost,hair transplant results" --dry-run

Modes
  own       keywords from config "own_keywords"; outlier score = views / channel median,
            with a recency boost. For "what is working in my market right now".
  adjacent  keywords from config "adjacent_keywords" plus "channels"; titles that contain
            any "own_niche_terms" are dropped (we want transferable ideas, not competitors),
            non-transferable formats are penalised and proven hook types get a bonus.

Sources (--source, default auto: youtube-api if YOUTUBE_API_KEY is set, else yt-dlp)
  youtube-api  YouTube Data API v3 (YOUTUBE_API_KEY). Most reliable. Each keyword search
               costs 100 quota units of the free 10,000/day.
  ytdlp        yt-dlp CLI, no key. Free but slow, and often blocked on cloud servers
               ("Sign in to confirm you're not a bot").
  tubelab      TubeLab API (TUBELAB_API_KEY). Pre-computed outlier ratios, paid credits.

Transcripts: youtube-transcript-api if installed, else/then Apify (APIFY_TOKEN).
Optional LLM steps (need ANTHROPIC_API_KEY): --summarize (hook / structure / how to adapt)
and --variants N (title variants adapted to your niche). Without them, Claude Code does the
analysis in-session from report.md and the transcripts folder.

Output: ./youtube-outliers-output/<YYYY-MM-DD>-<mode>/ (or --out): outliers.json,
outliers.csv (imports into Google Sheets), report.md, transcripts/<video_id>.txt
Env: load with  set -a; source ~/.claude/skills/.env; set +a
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

# ----------------------------------------------------------------------------- defaults
DEFAULTS = {
    "niche_description": "describe your channel / brand niche here",
    "own_keywords": [],
    "adjacent_keywords": [],
    "own_channels": [],          # competitors in your niche: ids (UC...), handles (@name) or URLs
    "adjacent_channels": [],     # channels outside your niche whose packaging you study
    "own_niche_terms": [],       # adjacent mode: titles containing these are dropped
    "exclude_terms": [],         # both modes: extra noise terms to drop
    "min_views": 1000,
    "per_keyword": 30,
    "per_channel": 15,
    "channel_sample": 15,        # recent uploads used for the channel median
}

# Titles containing these never appear (both modes)
NOISE = [
    "official music video", "official video", "lyric video", "music video", "official audio",
    "remix", "cover song", "minecraft", "fortnite", "valorant", "call of duty", "gta",
    "gameplay", "let's play", "walkthrough", "playthrough", "speedrun", "asmr", "mukbang",
    "#shorts", "tiktok compilation",
]

# Adjacent mode: formats whose success rarely transfers (score x0.3)
NON_TRANSFERABLE = [
    "desk setup", "room tour", "office tour", "studio tour", "what's in my bag", "unboxing",
    "hands on", "first look", "buying guide", "challenge", "prank", "react", "reaction",
    "roast", "drama", "day in my life", "day in the life", "morning routine", "what i eat",
    "get ready with me", "grwm", "haul", "travel vlog", "vacation", "q&a", "ask me anything",
    "compilation", "best of", "full episode", "full interview", "live stream", "livestream",
    "bloopers", "breaking news", "election", "bitcoin", "crypto", "stock market",
]

# Hook families: (tag, multiplier in adjacent mode, trigger phrases)
HOOKS = [
    ("money", 1.4, ["$", "£", "€", "revenue", "income", "profit", "money", "earn", "cash", "million",
                    "pricing", "charge more", "high ticket", "premium", "roi", "cost"]),
    ("curiosity", 1.3, ["?", "secret", "nobody", "no one tells you", "they don't want", "this changed",
                        "changed everything", "game changer", "shocking", "surprised", "unexpected",
                        "truth about", "real reason", "actually", "hidden", "insider"]),
    ("transformation", 1.25, ["before", "after", "transformed", "transformation", "from zero",
                              "from nothing", "how i went", "how i built", "how we built", "journey",
                              "changed my life", "breakthrough"]),
    ("contrarian", 1.25, ["wrong", "mistake", "myth", "lie", "lies", "overrated", "underrated",
                          "unpopular opinion", "controversial", "why i stopped", "why i quit",
                          "the problem with", "nobody talks about", "uncomfortable truth", "stop "]),
    ("speed", 1.2, ["faster", "save time", "productivity", "efficient", "quick", "in minutes",
                    "in seconds", "instantly", "overnight", "shortcut", "hack", "cheat code"]),
    ("urgency", 1.15, ["before it's too late", "while you still can", "last chance", "running out",
                       "don't miss", "must watch", "need to know"]),
]
NUMBER_BONUS = 1.1  # a number in the title (listicles, specific results)


def log(msg):
    print(msg, flush=True)


def has_term(title_l, term):
    """Word-boundary match for alphabetic terms (so 'ai' doesn't hit 'said'); substring otherwise."""
    t = term.lower()
    if re.fullmatch(r"[a-z0-9' ]+", t):
        return re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", title_l) is not None
    return t in title_l


def hook_tags(title):
    tl = title.lower()
    tags = [tag for tag, _, words in HOOKS if any(has_term(tl, w) for w in words)]
    if re.search(r"\d", title):
        tags.append("number")
    return tags


def recency_boost(days_old):
    # Newer videos have had less time to collect views
    if days_old <= 1:
        return 2.0
    if days_old <= 3:
        return 1.5
    if days_old <= 7:
        return 1.2
    return 1.0


def http_json(url, headers=None, data=None, timeout=60):
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    body = json.dumps(data).encode() if data is not None else None
    if body is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def parse_iso_duration(s):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def days_since(date_yyyymmdd):
    try:
        return max(0, (dt.datetime.now() - dt.datetime.strptime(date_yyyymmdd, "%Y%m%d")).days)
    except (TypeError, ValueError):
        return 999


# ----------------------------------------------------------------------------- source: YouTube Data API
class YouTubeAPI:
    BASE = "https://www.googleapis.com/youtube/v3"

    def __init__(self, key):
        self.key = key
        self.units = 0

    def get(self, path, cost, **params):
        params["key"] = self.key
        self.units += cost
        try:
            return http_json(f"{self.BASE}/{path}?{urllib.parse.urlencode(params)}")
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:300]
            if e.code == 403 and "quota" in msg.lower():
                sys.exit("YouTube API quota exhausted (10,000 units/day free; a search = 100). "
                         "Wait for the Pacific-midnight reset or use --source ytdlp.")
            raise RuntimeError(f"YouTube API {e.code}: {msg}")

    def videos(self, ids):
        out = []
        for i in range(0, len(ids), 50):
            j = self.get("videos", 1, part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50]))
            out.extend(j.get("items", []))
        return [self._norm(v) for v in out]

    @staticmethod
    def _norm(v):
        sn, st = v.get("snippet", {}), v.get("statistics", {})
        th = sn.get("thumbnails", {})
        thumb = (th.get("maxres") or th.get("high") or th.get("medium") or th.get("default") or {}).get("url", "")
        return {
            "video_id": v["id"], "title": sn.get("title", ""),
            "url": f"https://www.youtube.com/watch?v={v['id']}",
            "view_count": int(st.get("viewCount", 0) or 0),
            "like_count": int(st.get("likeCount", 0) or 0),
            "comment_count": int(st.get("commentCount", 0) or 0),
            "duration_s": parse_iso_duration(v.get("contentDetails", {}).get("duration")),
            "channel_id": sn.get("channelId", ""), "channel_name": sn.get("channelTitle", ""),
            "thumbnail_url": thumb,
            "date": (sn.get("publishedAt") or "")[:10].replace("-", ""),
        }

    def search(self, keyword, n, published_after):
        ids, token = [], None
        while len(ids) < n:
            p = dict(part="id", q=keyword, type="video", maxResults=min(50, n - len(ids)),
                     order="viewCount", publishedAfter=published_after, relevanceLanguage="en")
            if token:
                p["pageToken"] = token
            j = self.get("search", 100, **p)
            ids += [it["id"]["videoId"] for it in j.get("items", []) if it.get("id", {}).get("videoId")]
            token = j.get("nextPageToken")
            if not token:
                break
        return self.videos(ids)

    def resolve_channel(self, ref):
        ref = ref.strip().rstrip("/")
        m = re.search(r"(UC[A-Za-z0-9_-]{22})", ref)
        if m:
            return m.group(1)
        handle = ref.split("/")[-1]
        if not handle.startswith("@"):
            handle = "@" + handle
        j = self.get("channels", 1, part="id", forHandle=handle)
        items = j.get("items", [])
        return items[0]["id"] if items else None

    def recent_uploads(self, channel_id, n):
        uploads = "UU" + channel_id[2:]
        j = self.get("playlistItems", 1, part="contentDetails", playlistId=uploads, maxResults=min(50, n))
        ids = [it["contentDetails"]["videoId"] for it in j.get("items", [])]
        return self.videos(ids) if ids else []


# ----------------------------------------------------------------------------- source: yt-dlp
def ytdlp(args, timeout=300):
    if not shutil.which("yt-dlp"):
        sys.exit("yt-dlp not found. Install: pip install -U yt-dlp  (or set YOUTUBE_API_KEY and use --source youtube-api)")
    try:
        r = subprocess.run(["yt-dlp", "--no-warnings", "--skip-download"] + args,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return []
    if "confirm you" in (r.stderr or "") and "bot" in (r.stderr or ""):
        log("  !! yt-dlp is being blocked as a bot (common on cloud servers). Use --source youtube-api.")
    out = []
    for line in (r.stdout or "").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def ytdlp_norm(it):
    vid = it.get("id")
    return {
        "video_id": vid, "title": it.get("title") or "",
        "url": f"https://www.youtube.com/watch?v={vid}",
        "view_count": int(it.get("view_count") or 0),
        "like_count": int(it.get("like_count") or 0),
        "comment_count": int(it.get("comment_count") or 0),
        "duration_s": int(it.get("duration") or 0),
        "channel_id": it.get("channel_id") or "",
        "channel_name": it.get("uploader") or it.get("channel") or "",
        "channel_url": it.get("channel_url") or it.get("uploader_url") or "",
        "thumbnail_url": it.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        "date": it.get("upload_date") or "",
    }


def ytdlp_search(keyword, n):
    return [ytdlp_norm(i) for i in ytdlp([f"ytsearch{n}:{keyword}", "--dump-json", "--no-playlist"])]


def ytdlp_channel(ref, n, flat=False):
    url = ref if ref.startswith("http") else (f"https://www.youtube.com/{ref}" if ref.startswith("@")
                                              else f"https://www.youtube.com/channel/{ref}")
    if not url.rstrip("/").endswith("/videos"):
        url = url.rstrip("/") + "/videos"
    args = [url, "--dump-json", "--playlist-end", str(n)] + (["--flat-playlist"] if flat else [])
    return [ytdlp_norm(i) for i in ytdlp(args)]


# ----------------------------------------------------------------------------- source: TubeLab
def tubelab_search(keyword, n, min_views, published_after):
    key = os.environ.get("TUBELAB_API_KEY")
    if not key:
        sys.exit("TUBELAB_API_KEY not set")
    p = {"query": keyword, "size": n, "type": "video", "viewCountFrom": min_views,
         "language": "en", "publishedAtFrom": published_after}
    j = http_json("https://public-api.tubelab.net/v1/search/outliers?" + urllib.parse.urlencode(p),
                  headers={"Authorization": f"Api-Key {key}"}, timeout=60)
    out = []
    for h in j.get("hits", []):
        if h.get("kind") == "short":
            continue
        sn, st = h.get("snippet", {}), h.get("statistics", {})
        th = sn.get("thumbnails", {})
        out.append({
            "video_id": h.get("id"), "title": sn.get("title", ""),
            "url": f"https://www.youtube.com/watch?v={h.get('id')}",
            "view_count": int(st.get("viewCount", 0) or 0),
            "like_count": int(st.get("likeCount", 0) or 0),
            "comment_count": int(st.get("commentCount", 0) or 0),
            "duration_s": int(sn.get("duration", 0) or 0),
            "channel_id": sn.get("channelId", ""), "channel_name": sn.get("channelTitle", ""),
            "thumbnail_url": (th.get("high") or th.get("medium") or {}).get("url", ""),
            "date": (sn.get("publishedAt") or "")[:10].replace("-", ""),
            "precomputed_ratio": float(st.get("averageViewsRatio", 0) or 0),
        })
    time.sleep(6)  # TubeLab allows ~10 requests/minute
    return out


# ----------------------------------------------------------------------------- transcripts
def transcript_local(video_id):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None
    try:
        try:
            fetched = YouTubeTranscriptApi().fetch(video_id)  # v1.x API
            return " ".join(s.text for s in fetched)
        except AttributeError:
            return " ".join(e["text"] for e in YouTubeTranscriptApi.get_transcript(video_id))  # pre-1.0 API
    except Exception:
        return None


def transcript_apify(video_id):
    tok = os.environ.get("APIFY_TOKEN")
    if not tok:
        return None
    actor = os.environ.get("APIFY_TRANSCRIPT_ACTOR", "karamelo~youtube-transcripts").replace("/", "~")
    url = f"https://www.youtube.com/watch?v={video_id}"
    body = {"urls": [url], "videoUrl": url, "startUrls": [{"url": url}]}  # covers common input schemas
    try:
        items = http_json(f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?timeout=180",
                          headers={"Authorization": "Bearer " + tok}, data=body, timeout=240)
    except Exception as e:
        log(f"    apify transcript failed for {video_id}: {str(e)[:120]}")
        return None
    for it in items if isinstance(items, list) else []:
        for k in ("captions", "transcript", "data", "text", "subtitles"):
            v = it.get(k)
            if isinstance(v, str) and v.strip():
                return v
            if isinstance(v, list) and v:
                parts = [x if isinstance(x, str) else (x.get("text") or "") for x in v]
                txt = " ".join(p for p in parts if p)
                if txt.strip():
                    return txt
    return None


def get_transcript(video_id, order):
    for fn in order:
        t = fn(video_id)
        if t:
            return t
        time.sleep(1)  # be gentle; transcript endpoints rate-limit fast
    return None


# ----------------------------------------------------------------------------- optional LLM steps
def claude(prompt, max_tokens=700):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    model = os.environ.get("OUTLIERS_MODEL", "claude-sonnet-4-5")
    try:
        j = http_json("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                      data={"model": model, "max_tokens": max_tokens,
                            "messages": [{"role": "user", "content": prompt}]}, timeout=120)
        return "".join(b.get("text", "") for b in j.get("content", []))
    except Exception as e:
        return f"(LLM error: {str(e)[:120]})"


def summarize(v, niche):
    return claude(f"""Analyse this outlier YouTube video for patterns we can reuse.
Our niche: {niche}
Title: {v['title']}
Channel: {v['channel_name']} ({v['outlier_score']}x its normal views)
Transcript (first 8000 chars):
{(v.get('transcript') or '')[:8000]}

Answer in 4 short plain-text lines:
HOOK: what the first 30 seconds promise and why it grabs
STRUCTURE: the sequence of sections
WHY IT OVERPERFORMED: the most likely reason, in one sentence
ADAPT: one concrete way to use this angle in our niche""")


def title_variants(v, niche, n):
    out = claude(f"""You write YouTube titles for a channel about: {niche}.
This title overperformed ({v['outlier_score']}x the channel's normal views): "{v['title']}"
Write {n} new titles for OUR niche that keep the same emotional trigger and structure, are
meaningfully different from each other, stay under 70 characters, and make no claim we
couldn't back up. Return ONLY a JSON array of strings.""", max_tokens=400)
    if not out:
        return []
    m = re.search(r"\[.*\]", out, re.S)
    try:
        arr = json.loads(m.group(0)) if m else []
        return [str(x) for x in arr][:n]
    except json.JSONDecodeError:
        return []


# ----------------------------------------------------------------------------- pipeline
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="JSON config (see config.example.json)")
    ap.add_argument("--mode", choices=["own", "adjacent"], default="own")
    ap.add_argument("--source", choices=["auto", "youtube-api", "ytdlp", "tubelab"], default="auto")
    ap.add_argument("--keywords", help="comma-separated, overrides config keywords for this mode")
    ap.add_argument("--channels", help="comma-separated channel ids/handles/URLs, overrides config")
    ap.add_argument("--days", type=int, default=None, help="max video age (default 14 own, 30 adjacent)")
    ap.add_argument("--min-score", type=float, default=None, help="min score kept (default 2.0 own, 1.5 adjacent)")
    ap.add_argument("--top", type=int, default=20, help="how many outliers get transcripts + report entries")
    ap.add_argument("--no-transcripts", action="store_true")
    ap.add_argument("--summarize", action="store_true", help="LLM hook/structure summary per outlier (ANTHROPIC_API_KEY)")
    ap.add_argument("--variants", type=int, default=0, help="N title variants per outlier for your niche (ANTHROPIC_API_KEY)")
    ap.add_argument("--out", help="output dir (default ./youtube-outliers-output/<date>-<mode>)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and estimated quota/credits, call nothing")
    a = ap.parse_args()

    cfg = dict(DEFAULTS)
    if a.config:
        with open(a.config, encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    keywords = [k.strip() for k in (a.keywords.split(",") if a.keywords else
                                    cfg["own_keywords" if a.mode == "own" else "adjacent_keywords"]) if k.strip()]
    channels = [c.strip() for c in (a.channels.split(",") if a.channels else
                                    cfg["own_channels" if a.mode == "own" else "adjacent_channels"]) if c.strip()]
    days = a.days or (14 if a.mode == "own" else 30)
    min_score = a.min_score if a.min_score is not None else (2.0 if a.mode == "own" else 1.5)
    source = a.source
    if source == "auto":
        source = "youtube-api" if os.environ.get("YOUTUBE_API_KEY") else "ytdlp"
    if not keywords and not channels:
        sys.exit("No keywords or channels. Pass --keywords or fill own_keywords / adjacent_keywords / own_channels / adjacent_channels in the config.")

    if source == "youtube-api":
        est = f"~{len(keywords) * 100 * max(1, -(-cfg['per_keyword'] // 50)) + 200 + len(channels) * 3} quota units of 10,000/day (plus ~2 per channel for medians)"
    elif source == "tubelab":
        est = f"~{len(keywords) * 5} TubeLab credits"
    else:
        est = "free (yt-dlp), slow: allow ~1 min per keyword plus channel lookups"
    log(f"mode={a.mode} source={source} days={days} min_score={min_score}")
    log(f"keywords ({len(keywords)}): {keywords}")
    log(f"channels ({len(channels)}): {channels}")
    log(f"estimated cost: {est}")
    if a.dry_run:
        log("dry run: nothing called.")
        return

    published_after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    cutoff = (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y%m%d")
    if source == "youtube-api" and not os.environ.get("YOUTUBE_API_KEY"):
        sys.exit("YOUTUBE_API_KEY not set. Run: set -a; source ~/.claude/skills/.env; set +a")
    yt = YouTubeAPI(os.environ["YOUTUBE_API_KEY"]) if source == "youtube-api" else None

    # 1. discover
    found = []
    for kw in keywords:
        log(f"search: {kw}")
        if source == "youtube-api":
            vids = yt.search(kw, cfg["per_keyword"], published_after)
        elif source == "tubelab":
            vids = tubelab_search(kw, max(cfg["per_keyword"], 40), cfg["min_views"], published_after)
        else:
            vids = ytdlp_search(kw, cfg["per_keyword"])
        for v in vids:
            v["source"] = f"search: {kw}"
        found += vids
    for ch in channels:
        log(f"channel: {ch}")
        if source == "youtube-api":
            cid = yt.resolve_channel(ch)
            vids = yt.recent_uploads(cid, cfg["per_channel"]) if cid else []
        else:
            vids = ytdlp_channel(ch, cfg["per_channel"])
        for v in vids:
            v["source"] = f"channel: {ch}"
        found += vids

    seen, videos = set(), []
    noise = NOISE + [t.lower() for t in cfg.get("exclude_terms", [])]
    own_terms = [t.lower() for t in cfg.get("own_niche_terms", [])]
    dropped = {"noise": 0, "own_niche": 0, "old_or_small": 0, "short": 0}
    for v in found:
        if not v.get("video_id") or v["video_id"] in seen:
            continue
        seen.add(v["video_id"])
        tl = v["title"].lower()
        if any(has_term(tl, n) for n in noise):
            dropped["noise"] += 1; continue
        if a.mode == "adjacent" and any(has_term(tl, t) for t in own_terms):
            dropped["own_niche"] += 1; continue
        if (v.get("date") and v["date"] < cutoff) or v["view_count"] < cfg["min_views"]:
            dropped["old_or_small"] += 1; continue
        if 0 < v.get("duration_s", 0) <= 60:
            dropped["short"] += 1; continue
        videos.append(v)
    log(f"{len(videos)} candidate videos after filters (dropped {dropped})")
    if not videos:
        log("nothing to score. Widen --days, add keywords, or lower min_views in the config.")
        return

    # 2. channel baselines (median of recent uploads, excluding the video itself)
    def baseline(key):
        if source == "youtube-api":
            ups = yt.recent_uploads(key, cfg["channel_sample"])
        else:
            ups = ytdlp_channel(key, cfg["channel_sample"], flat=True)
        return [(u["video_id"], u["view_count"]) for u in ups if u.get("view_count")]

    need = {}
    for v in videos:
        if v.get("precomputed_ratio"):
            continue
        k = v.get("channel_id") if source == "youtube-api" else (v.get("channel_url") or v.get("channel_id"))
        if k:
            need.setdefault(k, []).append(v)
    log(f"channel baselines: {len(need)} channels")
    workers = 4 if source == "youtube-api" else 6
    with ThreadPoolExecutor(max_workers=workers) as ex:
        bases = dict(zip(need.keys(), ex.map(baseline, need.keys())))

    scored = []
    for v in videos:
        v["days_old"] = days_since(v.get("date"))
        if v.get("precomputed_ratio"):
            raw = v["precomputed_ratio"]
            v["channel_median"] = None
        else:
            k = v.get("channel_id") if source == "youtube-api" else (v.get("channel_url") or v.get("channel_id"))
            views = [n for vid, n in bases.get(k, []) if vid != v["video_id"]]
            if len(views) < 3:
                continue
            med = statistics.median(views)
            if med <= 0:
                continue
            raw = v["view_count"] / med
            v["channel_median"] = int(med)
        v["raw_ratio"] = round(raw, 2)
        v["outlier_score"] = round(raw * recency_boost(v["days_old"]), 2)
        v["hooks"] = hook_tags(v["title"])
        score = v["outlier_score"]
        if a.mode == "adjacent":
            tl = v["title"].lower()
            if any(has_term(tl, f) for f in NON_TRANSFERABLE):
                score *= 0.3
            for tag, mult, _ in HOOKS:
                if tag in v["hooks"]:
                    score *= mult
            if "number" in v["hooks"]:
                score *= NUMBER_BONUS
        v["score"] = round(score, 2)
        if v["score"] >= min_score:
            scored.append(v)
    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:a.top]
    log(f"{len(scored)} outliers at score >= {min_score}; processing top {len(top)}")

    out = a.out or os.path.join(os.getcwd(), "youtube-outliers-output", f"{dt.date.today():%Y-%m-%d}-{a.mode}")
    tdir = os.path.join(out, "transcripts")
    os.makedirs(tdir, exist_ok=True)

    # 3. transcripts + optional LLM
    order = [transcript_local, transcript_apify]
    for i, v in enumerate(top, 1):
        log(f"[{i}/{len(top)}] {v['score']}x  {v['title'][:70]}")
        if not a.no_transcripts:
            t = get_transcript(v["video_id"], order)
            v["transcript"] = t or ""
            if t:
                with open(os.path.join(tdir, f"{v['video_id']}.txt"), "w", encoding="utf-8") as fh:
                    fh.write(f"{v['title']}\n{v['url']}\n\n{t}\n")
        if a.summarize and v.get("transcript"):
            v["summary"] = summarize(v, cfg["niche_description"]) or ""
        if a.variants:
            v["title_variants"] = title_variants(v, cfg["niche_description"], a.variants)

    # 4. write
    slim = []
    for v in scored:
        row = {k: val for k, val in v.items() if k != "transcript"}
        row["has_transcript"] = bool(v.get("transcript"))
        slim.append(row)
    with open(os.path.join(out, "outliers.json"), "w", encoding="utf-8") as fh:
        json.dump(slim, fh, indent=1)
    cols = ["score", "outlier_score", "raw_ratio", "days_old", "title", "url", "view_count", "channel_median",
            "channel_name", "duration_s", "hooks", "date", "source", "thumbnail_url", "summary", "title_variants"]
    with open(os.path.join(out, "outliers.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for v in slim:
            w.writerow([" | ".join(v[c]) if isinstance(v.get(c), list) else v.get(c, "") for c in cols])

    from collections import Counter
    hc = Counter(h for v in top for h in v.get("hooks", []))
    lines = [f"# YouTube outliers: {a.mode} niche, {dt.date.today():%d %b %Y}", "",
             f"Source {source}; last {days} days; {len(videos)} candidates, {len(scored)} outliers at {min_score}x+.",
             "Score = views / channel median of recent uploads, x recency boost"
             + (", x hook/format modifiers (adjacent mode)." if a.mode == "adjacent" else "."), "",
             "## Hook patterns in the top results", ""]
    lines += [f"- {tag}: {n} of {len(top)}" for tag, n in hc.most_common()] or ["- none detected"]
    lines += ["", "## Top outliers", ""]
    for i, v in enumerate(top, 1):
        lines.append(f"### {i}. {v['title']}")
        lines.append(f"{v['score']}x score ({v['raw_ratio']}x channel median"
                     + (f" of {v['channel_median']:,}" if v.get("channel_median") else "")
                     + f") · {v['view_count']:,} views · {v['days_old']} days old · {v['channel_name']} · {v['url']}")
        lines.append(f"Hooks: {', '.join(v.get('hooks') or []) or 'none'} · transcript: "
                     + (f"transcripts/{v['video_id']}.txt" if v.get("transcript") else "none"))
        if v.get("summary"):
            lines += ["", v["summary"].strip()]
        if v.get("title_variants"):
            lines += [""] + [f"- Variant: {t}" for t in v["title_variants"]]
        lines.append("")
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    if yt:
        log(f"YouTube API quota used this run: ~{yt.units} units")
    log(f"done: {out}/report.md, outliers.csv, outliers.json, transcripts/")


if __name__ == "__main__":
    main()
