#!/usr/bin/env python3
"""
pull_calls.py - read-only pull of call recordings from one GoHighLevel (GHL) location.

What it does
  1. Walks conversations in the location (newest first) until it passes the lookback window.
  2. Keeps call messages (type 1 / TYPE_CALL) longer than --min-seconds, optionally only those
     placed or taken by one GHL user (--user-id).
  3. Works out speed-to-lead per contact: minutes from the contact being created to the first
     OUTBOUND touch of any kind (speed_to_lead_min; automated texts count) and to the first
     outbound CALL (first_call_min; the human number to coach on).
  4. Downloads each recording as <out>/recordings/<label>.wav and writes <out>/manifest.csv.

PII-safe: file names use the message id, direction and duration only (never the lead's name).
Recordings stay on your machine. Nothing is written back to GHL.

Env (load with: set -a; source ~/.claude/skills/.env; set +a)
  GHL_API_KEY      Private Integration token for the sub-account (scopes below)
  GHL_LOCATION_ID  the sub-account (location) id

Scopes needed on the Private Integration: View Contacts (contacts.readonly), View Conversations
(conversations.readonly), View Conversation Messages (conversations/message.readonly; the recording
endpoint needs this one), View Users (users.readonly; only for --list-users).

Usage
  python3 pull_calls.py --list-users                       # map user ids to people first
  python3 pull_calls.py --user-id USER_ID_HERE --days 7    # one setter, last 7 days
  python3 pull_calls.py --days 1 --out ./setter-call-audit-output/2026-01-31
  python3 pull_calls.py --days 7 --dry-run                 # list calls, download nothing
"""
import argparse
import csv
import datetime as dt
import os
import sys
import time

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

BASE = "https://services.leadconnectorhq.com"
VERSION = "2021-07-28"


def env(name):
    v = os.environ.get(name)
    if not v:
        sys.exit(f"missing {name}. Run: set -a; source ~/.claude/skills/.env; set +a")
    return v


class GHL:
    def __init__(self, token, loc):
        self.loc = loc
        self.h = {"Authorization": f"Bearer {token}", "Version": VERSION, "Accept": "application/json"}

    def get(self, path, params=None, retries=5):
        for i in range(retries):
            try:
                r = requests.get(BASE + path, headers=self.h, params=params, timeout=90)
            except requests.RequestException:
                time.sleep(1 + i)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 + 2 * i)
                continue
            if r.status_code in (401, 403):
                sys.exit(f"HTTP {r.status_code} on {path}: the token is missing a scope "
                         "(see SETUP.md) or belongs to another location.")
            return r
        return None

    def users(self):
        r = self.get("/users/", {"locationId": self.loc})
        return (r.json().get("users") or []) if r is not None and r.ok else []

    def conversations(self, since_ms):
        """Newest first; stop once last_message_date falls before the window."""
        cursor = None
        while True:
            params = {"locationId": self.loc, "limit": 100, "sortBy": "last_message_date", "sort": "desc"}
            if cursor is not None:
                params["startAfterDate"] = cursor
            r = self.get("/conversations/search", params)
            if r is None or not r.ok:
                return
            arr = r.json().get("conversations") or []
            if not arr:
                return
            for c in arr:
                yield c
            last = arr[-1]
            last_ts = last.get("lastMessageDate") or 0
            if last_ts and int(last_ts) < since_ms:
                return
            srt = last.get("sort") or []
            nxt = int(srt[0]) if srt and srt[0] is not None else None
            if nxt is None or nxt == cursor:
                return
            cursor = nxt

    def messages(self, conv_id):
        out, params = [], {"limit": 100}
        for _ in range(50):
            r = self.get(f"/conversations/{conv_id}/messages", params)
            if r is None or not r.ok:
                break
            m = r.json().get("messages", {})
            arr = m.get("messages") if isinstance(m, dict) else m
            out.extend(arr or [])
            if not isinstance(m, dict) or not m.get("nextPage") or not m.get("lastMessageId"):
                break
            params = {"limit": 100, "lastMessageId": m["lastMessageId"]}
        return out

    def contact_created(self, contact_id):
        r = self.get(f"/contacts/{contact_id}")
        if r is None or not r.ok:
            return None
        return (r.json().get("contact") or {}).get("dateAdded")

    def recording(self, mid):
        r = self.get(f"/conversations/messages/{mid}/locations/{self.loc}/recording")
        if r is not None and r.status_code == 200 and r.content:
            return r.content
        return None


def parse_ts(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def is_call(m):
    return m.get("type") == 1 or m.get("messageType") == "TYPE_CALL"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user-id", help="only calls by this GHL user id (run --list-users first)")
    ap.add_argument("--days", type=int, default=1, help="lookback window in days (default 1)")
    ap.add_argument("--min-seconds", type=int, default=30, help="skip calls shorter than this (default 30)")
    ap.add_argument("--out", default=None, help="output folder (default ./setter-call-audit-output/<date>)")
    ap.add_argument("--list-users", action="store_true", help="print user id -> name for the location and exit")
    ap.add_argument("--dry-run", action="store_true", help="write the manifest but download no audio")
    a = ap.parse_args()

    g = GHL(env("GHL_API_KEY"), env("GHL_LOCATION_ID"))

    if a.list_users:
        for u in g.users():
            print(f"{u.get('id')}\t{u.get('name') or (u.get('firstName', '') + ' ' + u.get('lastName', '')).strip()}\t{u.get('roles', {}).get('role', '')}")
        return

    now = dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=a.days)
    since_ms = int(since.timestamp() * 1000)
    out = a.out or os.path.join("setter-call-audit-output", now.strftime("%Y-%m-%d"))
    rec_dir = os.path.join(out, "recordings")
    os.makedirs(rec_dir, exist_ok=True)

    rows, scanned = [], 0
    for c in g.conversations(since_ms):
        scanned += 1
        if scanned % 50 == 0:
            print(f"scanned {scanned} conversations, {len(rows)} calls so far", flush=True)
        msgs = g.messages(c["id"])
        calls = []
        for m in msgs:
            if not is_call(m):
                continue
            ts = parse_ts(m.get("dateAdded"))
            if ts is None or ts < since:
                continue
            dur = int((((m.get("meta") or {}).get("call") or {}).get("duration")) or 0)
            if dur < a.min_seconds:
                continue
            if a.user_id and m.get("userId") != a.user_id:
                continue
            calls.append((m, ts, dur))
        if not calls:
            continue
        # speed-to-lead for this contact
        # any outbound message counts as a touch (call, SMS, email, WhatsApp, automated or manual)
        outbound = [parse_ts(m.get("dateAdded")) for m in msgs if m.get("direction") == "outbound"]
        outbound = sorted(t for t in outbound if t)
        created = parse_ts(g.contact_created(c.get("contactId"))) if c.get("contactId") else None
        out_calls = sorted(t for t in (parse_ts(m.get("dateAdded")) for m in msgs
                                       if m.get("direction") == "outbound" and is_call(m)) if t)
        stl = stl_call = ""
        if created and outbound:
            stl = round((outbound[0] - created).total_seconds() / 60, 1)
        if created and out_calls:
            stl_call = round((out_calls[0] - created).total_seconds() / 60, 1)
        attempts = sum(1 for m in msgs if m.get("direction") == "outbound" and is_call(m))
        for m, ts, dur in calls:
            label = f"{m['id'][:10]}-{m.get('direction', 'na')}-{dur}s"
            rows.append({"label": label, "messageId": m["id"], "contactId": c.get("contactId", ""),
                         "userId": m.get("userId", ""), "direction": m.get("direction", ""),
                         "duration_s": dur, "call_at": ts.isoformat(),
                         "contact_created": created.isoformat() if created else "",
                         "speed_to_lead_min": stl, "first_call_min": stl_call, "outbound_call_attempts": attempts, "wav": ""})

    print(f"{len(rows)} qualifying calls across {scanned} conversations", flush=True)
    for r in rows:
        if a.dry_run:
            continue
        data = g.recording(r["messageId"])
        if data:
            r["wav"] = f"{r['label']}.wav"
            with open(os.path.join(rec_dir, r["wav"]), "wb") as fh:
                fh.write(data)
            print(f"  saved {r['wav']} ({len(data)} bytes)", flush=True)
        else:
            print(f"  no recording for {r['label']} (recording off, or not a recorded line)", flush=True)

    man = os.path.join(out, "manifest.csv")
    cols = ["label", "messageId", "contactId", "userId", "direction", "duration_s", "call_at",
            "contact_created", "speed_to_lead_min", "first_call_min", "outbound_call_attempts", "wav"]
    with open(man, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"manifest -> {man}")


if __name__ == "__main__":
    main()
