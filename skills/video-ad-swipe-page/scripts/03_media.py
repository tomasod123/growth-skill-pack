#!/usr/bin/env python3
"""Step 3: download the shortlisted videos WHILE THE URLS ARE FRESH, transcribe the hook,
cut a first-frame thumbnail, measure length.

Per ad id in shortlist.json:
  media/<id>.mp4      video (snapshot URL; falls back to yt-dlp if --ytdlp-map gives a public page URL)
  media/<id>.jpg      poster from the payload, else first frame via ffmpeg
  frames/<id>.jpg     first frame at t=0.5s (always, via ffmpeg)
  hooks/<id>.wav      first 8 s, 16 kHz mono (whisper tiny.en runs fast on this)
  hooks/<id>.txt      hook transcript (words spoken in the first 8 s)
  tx/<id>.txt         full transcript (only with --full, small.en)
  media_meta.json     duration, size, has_speech, hook text

  python3 03_media.py --client clinic-a
  python3 03_media.py --shortlist shortlist.json --out ./research --full
  python3 03_media.py --client clinic-a --dry-run     # lists what would be fetched, nothing downloaded
"""
import argparse
import concurrent.futures as cf
import json
import os
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

HOOK_SECONDS = 8


def run(cmd, timeout=1800):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def download(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return "cached"
    req = urllib.request.Request(url, headers=C.UA)
    with urllib.request.urlopen(req, context=C.CTX, timeout=120) as f, open(path, "wb") as o:
        o.write(f.read())
    return "ok"


def ytdlp(url, path):
    yt = C.which("yt-dlp")
    if not yt:
        return "no yt-dlp"
    # Gotcha: plain -f best; height selectors fail on single-format m3u8 sources.
    r = run([yt, "-f", "best", "-o", path, "--no-playlist", "-q", url])
    return "ok" if r.returncode == 0 and os.path.exists(path) else f"yt-dlp failed: {r.stderr[-200:]}"


def duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    try:
        return round(float(r.stdout.strip()), 1)
    except ValueError:
        return None


def whisper_bin():
    w = C.which("whisper")
    if w:
        return [w]
    if subprocess.run([sys.executable, "-c", "import whisper"], capture_output=True).returncode == 0:
        return [sys.executable, "-m", "whisper"]
    return None


def process(r, d, args):
    aid = r["id"]
    mp4 = os.path.join(d, "media", f"{aid}.mp4")
    jpg = os.path.join(d, "media", f"{aid}.jpg")
    frame = os.path.join(d, "frames", f"{aid}.jpg")
    wav = os.path.join(d, "hooks", f"{aid}.wav")
    hook_txt = os.path.join(d, "hooks", f"{aid}.txt")
    log = []
    try:
        if r.get("video"):
            log.append("mp4 " + download(r["video"], mp4))
    except Exception as e:  # noqa: BLE001
        log.append(f"mp4 ERR {str(e)[:80]}")
    if not (os.path.exists(mp4) and os.path.getsize(mp4) > 1000) and args.ytdlp_map.get(aid):
        log.append("yt-dlp " + ytdlp(args.ytdlp_map[aid], mp4))
    if r.get("poster"):
        try:
            log.append("poster " + download(r["poster"], jpg))
        except Exception as e:  # noqa: BLE001
            log.append(f"poster ERR {str(e)[:60]}")
    meta = {"id": aid, "page": r.get("page"), "days": r.get("days")}
    if os.path.exists(mp4) and os.path.getsize(mp4) > 1000:
        meta["duration_s"] = duration(mp4)
        meta["bytes"] = os.path.getsize(mp4)
        if not os.path.exists(frame):
            run(["ffmpeg", "-y", "-v", "error", "-ss", "0.5", "-i", mp4, "-frames:v", "1", "-q:v", "3", frame])
        if not os.path.exists(jpg) and os.path.exists(frame):
            import shutil
            shutil.copy(frame, jpg)
        if not os.path.exists(wav):
            run(["ffmpeg", "-y", "-v", "error", "-i", mp4, "-t", str(HOOK_SECONDS), "-ac", "1", "-ar", "16000", wav])
        meta["hook_wav"] = os.path.exists(wav)
    else:
        meta["missing_video"] = True
    return meta, log


def transcribe(paths, outdir, model, wb):
    """Sequential whisper (the model load dominates; parallel whisper on a laptop thrashes RAM)."""
    for p in paths:
        base = os.path.splitext(os.path.basename(p))[0]
        if os.path.exists(os.path.join(outdir, base + ".txt")):
            continue
        run(wb + [p, "--model", model, "--language", "en", "--output_format", "txt",
                  "--output_dir", outdir, "--fp16", "False", "--verbose", "False"], timeout=3600)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client")
    ap.add_argument("--workdir")
    ap.add_argument("--shortlist", help="explicit shortlist.json")
    ap.add_argument("--out", help="research dir (default = workdir)")
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--model", default="tiny.en", help="whisper model for the 8 s hook (tiny.en is enough)")
    ap.add_argument("--full", action="store_true", help="also transcribe full videos with small.en into tx/")
    ap.add_argument("--ytdlp-map", default="", help="JSON file {ad_id: public facebook video url} for fallbacks")
    ap.add_argument("--dry-run", action="store_true", help="list the fetch plan, download nothing")
    args = ap.parse_args()

    wd = args.workdir or (C.workdir(args.client) if args.client else None)
    sl = args.shortlist or (os.path.join(wd, "shortlist.json") if wd else None)
    if not sl or not os.path.exists(sl):
        sys.exit("shortlist.json not found; run 02_rank.py first or pass --shortlist")
    d = args.out or wd or os.path.dirname(os.path.abspath(sl))
    rows = C.load_json(sl)
    args.ytdlp_map = C.load_json(args.ytdlp_map, {}) if args.ytdlp_map else {}

    print(f"{len(rows)} ads in shortlist -> {d}")
    if args.dry_run:
        with_v = sum(1 for r in rows if r.get("video"))
        print(f"would download {with_v} mp4 + {sum(1 for r in rows if r.get('poster'))} posters, "
              f"cut {with_v} hook wavs, run whisper {args.model} on each"
              + (", then small.en full transcripts" if args.full else ""))
        for r in rows[:15]:
            print(f"  {r['id']} {r.get('days')}d {r.get('page','')[:32]:32s} video={'y' if r.get('video') else 'n'}")
        print("tools:", {t: bool(C.which(t)) for t in ("ffmpeg", "ffprobe", "yt-dlp")}, "whisper:", bool(whisper_bin()))
        print("DRY RUN: nothing fetched")
        return

    for sub in ("media", "frames", "hooks", "tx"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    metas = {}
    with cf.ThreadPoolExecutor(args.threads) as ex:
        for meta, log in ex.map(lambda r: process(r, d, args), rows):
            metas[meta["id"]] = meta
            print(meta["id"], meta.get("duration_s"), "|", "; ".join(log), flush=True)

    wb = whisper_bin()
    if not wb:
        print("whisper not found (pip install openai-whisper); skipping transcription")
    else:
        hooks = sorted(os.path.join(d, "hooks", f) for f in os.listdir(os.path.join(d, "hooks")) if f.endswith(".wav"))
        transcribe(hooks, os.path.join(d, "hooks"), args.model, wb)
        if args.full:
            vids = sorted(os.path.join(d, "media", f) for f in os.listdir(os.path.join(d, "media")) if f.endswith(".mp4"))
            transcribe(vids, os.path.join(d, "tx"), "small.en", wb)
    for aid, m in metas.items():
        p = os.path.join(d, "hooks", f"{aid}.txt")
        if os.path.exists(p):
            m["hook"] = " ".join(open(p, encoding="utf-8", errors="ignore").read().split())
            m["has_speech"] = len(m["hook"].split()) >= 3
        p2 = os.path.join(d, "tx", f"{aid}.txt")
        if os.path.exists(p2):
            m["transcript"] = " ".join(open(p2, encoding="utf-8", errors="ignore").read().split())
    C.save_json(os.path.join(d, "media_meta.json"), metas)
    ok = sum(1 for m in metas.values() if not m.get("missing_video"))
    print(f"videos on disk {ok}/{len(rows)}  -> {os.path.join(d, 'media_meta.json')}")


if __name__ == "__main__":
    main()
