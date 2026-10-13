#!/usr/bin/env python3
"""
mine_calls.py - pull ALL logged call recordings from one GoHighLevel location (every user),
read-only, to mine real objections for the sales kit.

Env (load with: set -a; source ~/.claude/skills/.env; set +a)
  GHL_API_KEY      Private Integration token (View Conversations + View Conversation Messages)
  GHL_LOCATION_ID  the sub-account (location) id

Usage
  python3 mine_calls.py [--min-seconds 30] [--out DIR] [--max-conversations N] [--dry-run]

Walks every conversation, keeps call messages (type 1 / TYPE_CALL) at or above --min-seconds,
downloads each recording .wav. PII-safe: file names are message id + direction + duration
(no lead names). Writes manifest.csv. A big account takes a while: run it with a long
timeout and read the log, do not pipe it through `tail`.
"""
import os, sys, time, csv, requests

BASE = "https://services.leadconnectorhq.com"
VER = "2021-07-28"


def env(name):
    v = os.environ.get(name)
    if not v:
        sys.exit(f"missing {name}. Run: set -a; source ~/.claude/skills/.env; set +a")
    return v


class GHL:
    def __init__(self, loc, token):
        self.loc = loc
        self.h = {"Authorization": f"Bearer {token}", "Version": VER, "Accept": "application/json"}

    def get(self, path, retries=5):
        for _ in range(retries):
            try:
                r = requests.get(BASE + path, headers=self.h, timeout=90)
                if r.status_code == 429 or r.status_code >= 500:
                    time.sleep(2); continue
                if r.status_code in (401, 403):
                    sys.exit(f"HTTP {r.status_code} on {path.split('?')[0]}: token missing a scope "
                             "(View Conversation Messages for recordings) or wrong location.")
                return r
            except requests.RequestException:
                time.sleep(1)
        return None

    def conversations(self):
        """Paginate every conversation via startAfterDate cursor (sort[0])."""
        out, cursor, page = [], None, 0
        while True:
            p = f"/conversations/search?locationId={self.loc}&limit=100&sortBy=last_message_date&sort=desc"
            if cursor is not None:
                p += f"&startAfterDate={cursor}"
            r = self.get(p)
            if not r or r.status_code != 200:
                print(f"  conv page {page}: HTTP {getattr(r,'status_code','ERR')} - stopping", flush=True)
                break
            arr = r.json().get("conversations") or []
            if not arr:
                break
            out.extend(arr)
            page += 1
            last_sort = arr[-1].get("sort") or []
            nxt = int(last_sort[0]) if last_sort and last_sort[0] is not None else None
            if nxt is None or nxt == cursor:
                break
            cursor = nxt
        return out

    def messages(self, conv_id):
        out, p = [], f"/conversations/{conv_id}/messages?limit=100"
        for _ in range(50):  # backstop; real termination is `not nxt` below
            r = self.get(p)
            if not r or r.status_code != 200:
                break
            m = r.json().get("messages", {})
            arr = m.get("messages") if isinstance(m, dict) else m
            out.extend(arr or [])
            nxt = m.get("nextPage") if isinstance(m, dict) else None
            last = m.get("lastMessageId") if isinstance(m, dict) else None
            if not nxt or not last:
                break
            p = f"/conversations/{conv_id}/messages?limit=100&lastMessageId={last}"
        return out

    def recording(self, mid):
        r = self.get(f"/conversations/messages/{mid}/locations/{self.loc}/recording")
        if r and r.status_code == 200 and r.content:
            return r.content
        return None


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Pull every recorded call (all users) from one GHL location.")
    ap.add_argument("--min-seconds", type=int, default=30, help="skip calls shorter than this (default 30)")
    ap.add_argument("--out", default=os.path.join("front-desk-sales-kit-output", "calls"),
                    help="output folder (default ./front-desk-sales-kit-output/calls)")
    ap.add_argument("--max-conversations", type=int, default=0, help="stop after N conversations (0 = all)")
    ap.add_argument("--dry-run", action="store_true", help="write the manifest, download no audio")
    a = ap.parse_args()
    min_dur, out_dir = a.min_seconds, a.out
    os.makedirs(out_dir, exist_ok=True)
    slug = "location"

    g = GHL(env("GHL_LOCATION_ID"), env("GHL_API_KEY"))
    print(f"[{slug}] pulling conversations...", flush=True)
    convs = g.conversations()
    if a.max_conversations:
        convs = convs[:a.max_conversations]
    print(f"[{slug}] {len(convs)} conversations to scan", flush=True)

    calls, short, downloaded = [], 0, 0
    for i, c in enumerate(convs):
        if i % 50 == 0:
            print(f"[{slug}] scanned {i}/{len(convs)} convs, {len(calls)} calls found", flush=True)
        for m in g.messages(c["id"]):
            t = m.get("type")
            if t != 1:
                continue
            dur = int((((m.get("meta") or {}).get("call") or {}).get("duration")) or 0)
            direction = m.get("direction") or "?"
            if dur < min_dur:
                short += 1
                continue
            calls.append({"mid": m["id"], "dur": dur, "dir": direction,
                          "date": m.get("dateAdded", "")})

    print(f"[{slug}] {len(calls)} qualifying calls (>= {min_dur}s); {short} shorter skipped", flush=True)

    man_path = os.path.join(out_dir, "manifest.csv")
    with open(man_path, "w", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["messageId", "direction", "duration_s", "dateAdded", "wav"])
        for c in calls:
            label = f"{c['mid'][:10]}-{c['dir']}-{c['dur']}s"
            data = None if a.dry_run else g.recording(c["mid"])
            wav = ""
            if data:
                wav = f"{label}.wav"
                with open(os.path.join(out_dir, wav), "wb") as af:
                    af.write(data)
                downloaded += 1
                print(f"  saved {wav} ({len(data)} bytes)", flush=True)
            else:
                print(f"  no recording for {c['mid'][:10]} ({c['dur']}s {c['dir']})", flush=True)
            w.writerow([c["mid"], c["dir"], c["dur"], c["date"], wav])

    print(f"[{slug}] DONE: {downloaded} recordings downloaded -> {out_dir}", flush=True)


if __name__ == "__main__":
    main()
