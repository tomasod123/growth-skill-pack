"""Read-only GoHighLevel contact search.

Gotchas this handles:
- POST /contacts/search needs pageLimit as a NUMBER. A string gives 422 or an empty list.
- Send Version: 2021-07-28 and a normal browser User-Agent (bare clients can be blocked).
- Filter by dateAdded range on the server, then re-check dates locally.
- Stop paging once the reported total is reached; de-duplicate by contact id.
- GHL merges contacts that share an email or phone, so CRM counts can be lower than Meta's.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import requests

GHL_BASE = "https://services.leadconnectorhq.com"
GHL_VERSION = "2021-07-28"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class GHLError(Exception):
    pass


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def parse_date(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class GHLClient:
    def __init__(self, token: str, session=None, page_limit: int = 100, max_pages: int = 100,
                 max_retries: int = 4, base_delay: float = 2.0, sleep=time.sleep):
        self.token = token
        self.session = session or requests.Session()
        self.page_limit = int(page_limit)
        self.max_pages = max_pages
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.sleep = sleep

    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Version": GHL_VERSION,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }

    def _post(self, path: str, body: dict) -> dict:
        for attempt in range(self.max_retries + 1):
            r = self.session.post(f"{GHL_BASE}{path}", json=body, headers=self.headers(), timeout=60)
            if r.status_code == 200 or r.status_code == 201:
                return r.json() or {}
            if (r.status_code == 429 or r.status_code >= 500) and attempt < self.max_retries:
                self.sleep(min(self.base_delay * (2 ** attempt), 60))
                continue
            hint = {
                401: "token invalid, or it belongs to a different sub-account than the location id",
                403: "token is missing a scope (needs contacts.readonly)",
                422: "request rejected; pageLimit must be a number and the location id must be right",
            }.get(r.status_code, "")
            raise GHLError(f"GHL {r.status_code} on {path}" + (f": {hint}" if hint else ""))
        raise GHLError("GHL: retries exhausted")

    def search_contacts(self, location_id: str, start: datetime, end: datetime) -> list[dict]:
        """All contacts with dateAdded in [start, end), de-duplicated by id."""
        seen: dict[str, dict] = {}
        total = None
        for page in range(1, self.max_pages + 1):
            body = {
                "locationId": location_id,
                "page": page,
                "pageLimit": self.page_limit,  # int, never a string
                "filters": [{"field": "dateAdded", "operator": "range",
                             # gte/lte is the form used in production; dates are re-checked locally below
                             "value": {"gte": iso(start), "lte": iso(end)}}],
                "sort": [{"field": "dateAdded", "direction": "desc"}],
            }
            data = self._post("/contacts/search", body)
            contacts = data.get("contacts") or []
            if data.get("total") is not None:
                total = int(data["total"])
            for c in contacts:
                cid = c.get("id")
                if cid and cid not in seen:
                    seen[cid] = c
            if not contacts or (total is not None and (len(seen) >= total or page * self.page_limit >= total)):
                break
        out = []
        for c in seen.values():
            added = parse_date(c.get("dateAdded"))
            if added and start <= added < end:
                out.append(c)
        return out


def _attribution_values(contact: dict) -> list[str]:
    vals = []
    for key in ("attributionSource", "lastAttributionSource"):
        v = contact.get(key)
        if isinstance(v, dict):
            vals.append(v)
    for v in contact.get("attributions") or []:
        if isinstance(v, dict):
            vals.append(v)
    out = []
    for d in vals:
        for k in ("utmSource", "utm_source"):
            if d.get(k):
                out.append(str(d[k]).strip().lower())
    return out


def classify(contact: dict, rules: dict) -> tuple[bool, bool]:
    """Return (tagged, meta_source) for one contact.

    tagged: has one of rules['tags'] (exact, case-insensitive).
    meta_source: its source field contains one of rules['sources'], or a UTM source
    equals one of rules['utm_sources']. Tag-independent, so it still counts a Meta lead
    that the tagging workflow missed.
    """
    tags = {str(t).strip().lower() for t in rules.get("tags") or []}
    sources = [str(s).strip().lower() for s in rules.get("sources") or []]
    utms = {str(u).strip().lower() for u in rules.get("utm_sources") or []}
    contact_tags = {str(t).strip().lower() for t in contact.get("tags") or []}
    tagged = bool(tags & contact_tags)
    src = str(contact.get("source") or "").lower()
    meta_source = any(s and s in src for s in sources) or bool(utms & set(_attribution_values(contact)))
    return tagged, meta_source
