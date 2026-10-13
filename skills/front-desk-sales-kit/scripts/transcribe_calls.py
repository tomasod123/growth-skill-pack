#!/usr/bin/env python3
"""
transcribe_calls.py - transcribe every .wav/.mp3/.m4a in a folder with timestamps.

Default engine is LOCAL openai-whisper (free, private: audio never leaves the machine).
Optional --engine api uses the OpenAI Whisper API (OPENAI_API_KEY); only use it if your
privacy rules allow sending call audio to a third party (no PHI under HIPAA without a BAA).

Each transcript is written as <out_dir>/<name>.txt with one line per segment:
  [mm:ss] text
so the scorecard can quote exact timestamps.

Usage
  python3 transcribe_calls.py <audio_dir> <out_dir> [--model base|small|medium] [--engine local|api]

Gotcha: do not pass a "names" prompt to Whisper on short clips; it can hallucinate the
names into the text. Check proper nouns (people, company) by ear before quoting them.
"""
import argparse
import os
import sys

EXTS = (".wav", ".mp3", ".m4a", ".ogg", ".webm")


def fmt(t):
    t = int(t or 0)
    return f"{t // 60:02d}:{t % 60:02d}"


def local_segments(model, path):
    res = model.transcribe(path, fp16=False, verbose=False, language="en")
    return [(s["start"], s["text"].strip()) for s in res.get("segments", [])]


def api_segments(client, path):
    with open(path, "rb") as fh:
        res = client.audio.transcriptions.create(model="whisper-1", file=fh,
                                                 response_format="verbose_json", language="en")
    segs = getattr(res, "segments", None) or []
    return [(getattr(s, "start", None) if not isinstance(s, dict) else s.get("start"),
             (getattr(s, "text", "") if not isinstance(s, dict) else s.get("text", "")).strip())
            for s in segs]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--model", default="base", help="local whisper model (base is fast; small is more accurate)")
    ap.add_argument("--engine", choices=["local", "api"], default="local")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)

    files = sorted(f for f in os.listdir(a.audio_dir) if f.lower().endswith(EXTS))
    if not files:
        print(f"No audio files in {a.audio_dir}")
        return

    if a.engine == "local":
        try:
            import whisper
        except ImportError:
            sys.exit("pip install openai-whisper  (and install ffmpeg)")
        print(f"Loading local whisper '{a.model}' (first run downloads it)...", flush=True)
        model = whisper.load_model(a.model)
        run = lambda p: local_segments(model, p)
    else:
        if not os.environ.get("OPENAI_API_KEY"):
            sys.exit("missing OPENAI_API_KEY. Run: set -a; source ~/.claude/skills/.env; set +a")
        from openai import OpenAI
        client = OpenAI()
        run = lambda p: api_segments(client, p)

    for f in files:
        out_path = os.path.join(a.out_dir, os.path.splitext(f)[0] + ".txt")
        if os.path.exists(out_path):
            print(f"skip {f} (already transcribed)")
            continue
        print(f"=== {f}", flush=True)
        segs = run(os.path.join(a.audio_dir, f))
        with open(out_path, "w") as fh:
            for start, text in segs:
                fh.write(f"[{fmt(start)}] {text}\n")
        print(f"   -> {out_path} ({len(segs)} segments)", flush=True)
    print(f"Done. Transcripts in {a.out_dir}")


if __name__ == "__main__":
    main()
