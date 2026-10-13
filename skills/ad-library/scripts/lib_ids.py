"""Stable row ids and media paths for the ad library. Stdlib only.

Useful if you mirror the library somewhere else (a database, a sheet, a static file server):
row_id() gives every row a stable 16-char key that survives re-ingest and path moves, and
media_url() builds a served URL from AD_LIBRARY_MEDIA_BASE (optional, e.g. https://files.example.com/ad-library).
"""
import hashlib
import io
import json
import os

from adlib_common import LIB_DEFAULT

MEDIA_BASE = os.environ.get("AD_LIBRARY_MEDIA_BASE", "").rstrip("/")


def load_rows(lib=LIB_DEFAULT):
    p = os.path.join(lib, "index.jsonl")
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]


def row_id(r):
    """Stable id: sha1(source_scrape | ad_id)[:16]. Survives re-ingest and path moves."""
    return hashlib.sha1(f"{r.get('source_scrape','')}|{r.get('ad_id','')}".encode("utf-8")).hexdigest()[:16]


def rel_media(r, kind):
    """Served path for a row's media ('media_path' or 'poster_path'): <client>/<id><ext>."""
    p = r.get(kind)
    if not p:
        return None
    ext = os.path.splitext(p)[1].lower() or (".mp4" if kind == "media_path" else ".jpg")
    return f"{(r.get('client') or 'unknown')}/{row_id(r)}{ext}"


def media_url(r, kind, base=MEDIA_BASE):
    """Served URL for a row's media. A row may carry its own `media_url` / `poster_url` when the
    file lives only on a server and not locally (`media_path` null by design). That explicit URL
    wins; otherwise it is derived from the local path, and None when no base is configured."""
    explicit = r.get("media_url" if kind == "media_path" else "poster_url")
    if explicit:
        return explicit
    rel = rel_media(r, kind)
    return f"{base}/{rel}" if (rel and base) else None
