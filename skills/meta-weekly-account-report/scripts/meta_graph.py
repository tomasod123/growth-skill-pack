"""Small read-only Meta Graph API client.

GET requests only. Follows paging.next and backs off on rate limits
(codes 4, 17, 32, 613 and the 80000-80014 ads-insights family, incl. 80004).
"""

from __future__ import annotations

import time

import requests

RATE_LIMIT_CODES = {4, 17, 32, 613} | set(range(80000, 80015))
MAX_PAGES = 200


class GraphError(Exception):
    def __init__(self, message: str, code: int | None = None, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


class GraphClient:
    def __init__(self, token: str, version: str = "v26.0", session=None,
                 max_retries: int = 5, base_delay: float = 5.0, sleep=time.sleep):
        self.token = token
        self.base = f"https://graph.facebook.com/{version}"
        self.session = session or requests.Session()
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.sleep = sleep

    def _get(self, url: str, params: dict | None) -> dict:
        for attempt in range(self.max_retries + 1):
            r = self.session.get(url, params=params, timeout=60)
            try:
                body = r.json()
            except ValueError:
                body = {}
            err = body.get("error") if isinstance(body, dict) else None
            if r.status_code == 200 and not err:
                return body
            err = err or {}
            code = err.get("code")
            retryable = (
                code in RATE_LIMIT_CODES
                or r.status_code == 429
                or r.status_code >= 500
                or bool(err.get("is_transient"))
            )
            if retryable and attempt < self.max_retries:
                self.sleep(min(self.base_delay * (2 ** attempt), 300))
                continue
            # Never echo the URL: it can carry the access token.
            msg = err.get("message") or f"HTTP {r.status_code}"
            raise GraphError(f"Meta API error {code or r.status_code}: {msg}",
                             code=code, status=r.status_code)
        raise GraphError("Meta API: retries exhausted")

    def get_all(self, path: str, params: dict | None = None) -> list[dict]:
        """GET an edge and return every row across all pages."""
        url = f"{self.base}/{path.lstrip('/')}"
        query = dict(params or {})
        query["access_token"] = self.token
        rows: list[dict] = []
        pages = 0
        while url and pages < MAX_PAGES:
            body = self._get(url, query)
            rows.extend(body.get("data") or [])
            pages += 1
            url = (body.get("paging") or {}).get("next")
            query = None  # the next URL already carries every parameter
        return rows


def count_leads(actions: list[dict] | None) -> int:
    """Leads = action_type 'lead' exactly.

    Never match on the substring 'lead': onsite_conversion.lead_grouped and
    offsite_conversion.fb_pixel_lead report the same submissions again.
    """
    total = 0.0
    for a in actions or []:
        if a.get("action_type") == "lead":
            total += float(a.get("value") or 0)
    return int(round(total))
