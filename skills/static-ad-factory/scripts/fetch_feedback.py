#!/usr/bin/env python3
"""OPTIONAL (Google Drive review loop): pull every reviewer comment on files in a Drive folder tree,
plus an export of the review Sheet, using rclone's existing Google Drive OAuth token (no extra auth).

  python3 fetch_feedback.py --folder-id <DRIVE_FOLDER_ID> --sheet-id <SHEET_ID> [--rclone-remote gdrive] [--out work/fb]
Writes <out>/comments.json, <out>/drive_inventory.json, <out>/review_sheet.xlsx.

Read BOTH sources: the Sheet's dropdowns carry the verdicts, file comments carry the art direction.
Then join comments to that reviewer's own verdict before doing any work (comments often sit on ads
the same reviewer rejected). Diff against the previous pull so you act only on new comments.
"""
import argparse, configparser, json, os, subprocess, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://www.googleapis.com/drive/v3"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--folder-id', required=True); ap.add_argument('--sheet-id')
    ap.add_argument('--rclone-remote', default='gdrive'); ap.add_argument('--out', default='work/fb')
    a = ap.parse_args()
    subprocess.run(["rclone", "lsd", f"{a.rclone_remote}:", "--max-depth", "1"], capture_output=True, timeout=90)
    c = configparser.ConfigParser(); c.read(os.path.expanduser("~/.config/rclone/rclone.conf"))
    tok = json.loads(c[a.rclone_remote]["token"])["access_token"]

    def get(url):
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return json.loads(r.read())
            except Exception:
                if attempt == 3: raise
                time.sleep(2 * (attempt + 1))

    def children(fid):
        out, page = [], None
        while True:
            q = urllib.parse.quote(f"'{fid}' in parents and trashed=false")
            url = f"{API}/files?q={q}&fields=nextPageToken,files(id,name,mimeType)&pageSize=1000"
            if page: url += f"&pageToken={page}"
            d = get(url); out += d.get("files", []); page = d.get("nextPageToken")
            if not page: return out

    def comments(fid):
        try:
            return get(f"{API}/files/{fid}/comments?fields=comments(id,content,resolved,createdTime,author(displayName),"
                       f"replies(content,author(displayName),createdTime))&includeDeleted=false&pageSize=100").get("comments", [])
        except Exception:
            return []

    rows, stack = [], [(a.folder_id, "")]
    while stack:
        fid, path = stack.pop()
        for f in children(fid):
            p = f"{path}/{f['name']}" if path else f["name"]
            if f["mimeType"] == "application/vnd.google-apps.folder": stack.append((f["id"], p))
            else: rows.append({"id": f["id"], "path": p, "name": f["name"], "mime": f["mimeType"]})
    print(f"{len(rows)} files", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=12) as ex:  # serial calls time out on a few hundred files
        allc = list(ex.map(lambda r: comments(r["id"]), rows))
    fb = [{"path": r["path"], "file": r["name"], "file_id": r["id"], "author": (x.get("author") or {}).get("displayName"),
           "comment": x.get("content"), "resolved": x.get("resolved"), "created": x.get("createdTime"),
           "replies": [{"author": (y.get("author") or {}).get("displayName"), "content": y.get("content")} for y in x.get("replies", [])]}
          for r, cs in zip(rows, allc) for x in cs]
    os.makedirs(a.out, exist_ok=True)
    json.dump(fb, open(f"{a.out}/comments.json", "w"), indent=1)
    json.dump(rows, open(f"{a.out}/drive_inventory.json", "w"), indent=1)
    print(f"{len(fb)} comments")
    if a.sheet_id:
        url = f"{API}/files/{a.sheet_id}/export?mimeType=" + urllib.parse.quote("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"}), timeout=120) as r:
            open(f"{a.out}/review_sheet.xlsx", "wb").write(r.read())
        meta = get(f"{API}/files/{a.sheet_id}?fields=id,name,trashed,modifiedTime")
        print("sheet exported; meta:", json.dumps(meta))
        if meta.get("trashed"): print("WARNING: the review Sheet is in the trash. Restore with a Drive PATCH {\"trashed\": false}.")


if __name__ == "__main__":
    main()
