"""Small helpers shared by every source: .env loading, HTTP with retries, number parsing."""
import json
import os
import re
import time

import requests

# Some CRM endpoints (GoHighLevel among them) reject default library user agents behind their CDN.
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")


HINTS = [  # (text in the API reply, what to do) -> appended to the error so the fix is on screen
    ("code\":190", "Meta token wrong or expired: generate a new system user token (SETUP.md, Meta step 4)."),
    ("\"code\":200", "Meta: the system user is not assigned to this ad account (SETUP.md, Meta step 2)."),
    ("invalid_client", "Google OAuth client id/secret wrong (check .env has no comment text after the value)."),
    ("invalid_grant", "Google refresh token expired or revoked: publish the consent screen, re-run tools/google_oauth.py."),
    ("DEVELOPER_TOKEN_NOT_APPROVED", "Developer token is test-only: apply for Explorer/Basic access in API Center."),
    ("DEVELOPER_TOKEN_INVALID", "Developer token wrong: copy it again from Admin > API Center."),
    ("USER_PERMISSION_DENIED", "Set GOOGLE_ADS_LOGIN_CUSTOMER_ID to the manager id, or sign in as a user with access."),
    ("SERVICE_DISABLED", "Enable the API in the same Google Cloud project as your OAuth client / service account."),
    ("sufficient permissions", "Add the service account email as Viewer on the GA4 property; use the numeric property id."),
    ("clarity.ms", "Clarity: token wrong, regenerated, or not created by a project admin (Settings > Data Export)."),
    ("leadconnectorhq", "GoHighLevel: token missing a scope from SETUP.md, or it belongs to another sub-account."),
]


def hint(text):
    for needle, h in HINTS:
        if needle.lower().replace(" ", "") in text.lower().replace(" ", ""):
            return h
    return ""


class SourceError(Exception):
    """A source failed in a way the user can fix (bad token, missing access). The message says how."""


def load_env(path):
    """Read KEY=value lines. Real environment variables win over the file."""
    out = {}
    if path and os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip()
                if not v.startswith(("'", '"')):
                    v = re.split(r"\s+#", v, maxsplit=1)[0]  # KEY=value   # comment  ->  value
                out[k.strip().removeprefix("export ").strip()] = v.strip().strip('"').strip("'")
    for k, v in os.environ.items():
        if k in out or k.startswith(("META_", "GOOGLE_ADS_", "GA4_", "CLARITY_", "GHL_")):
            out[k] = v
    return out


def http(method, url, *, headers=None, params=None, json_body=None, data=None, retries=4,
         retry_on=(429, 500, 502, 503, 504), timeout=60):
    """One HTTP call with backoff on rate limits and server errors. Returns parsed JSON or raises SourceError."""
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.request(method, url, headers=headers, params=params, json=json_body, data=data,
                                 timeout=timeout)
        except requests.RequestException as e:
            last = f"network error ({type(e).__name__}) calling {url.split('?')[0]}"  # never echo query strings (tokens)
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise SourceError(last)
        if r.status_code in retry_on and attempt < retries:
            wait = r.headers.get("Retry-After")
            time.sleep(float(wait) if wait and wait.isdigit() else 2 * (attempt + 1))
            continue
        if r.status_code == 400 and attempt < retries and _meta_throttled(r):
            time.sleep(60 * (attempt + 1))  # Meta signals rate limits as HTTP 400 + error code, not 429
            continue
        if r.status_code >= 400:
            body = r.text.replace("\n", " ")
            h = hint(body) or (hint(url) if r.status_code in (401, 403) else "")
            raise SourceError(f"HTTP {r.status_code} from {url.split('?')[0]}: {body[:300]}" + (f" -> FIX: {h}" if h else ""))
        try:
            return r.json()
        except ValueError:
            raise SourceError(f"non-JSON reply from {url.split('?')[0]}: {r.text[:200]}")
    raise SourceError(last or "gave up after retries")


META_THROTTLE = {4, 17, 32, 613} | set(range(80000, 80015))


def _meta_throttled(r):
    try:
        return int((r.json().get("error") or {}).get("code", 0)) in META_THROTTLE
    except (ValueError, AttributeError, TypeError):
        return False


def num(v, default=0.0):
    """Meta and Google send numbers as strings; None and '' become default."""
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def dig(d, *path, default=None):
    for p in path:
        if not isinstance(d, dict):
            return default
        d = d.get(p)
        if d is None:
            return default
    return d


def load_fixture(fixtures_dir, name):
    with open(os.path.join(fixtures_dir, name + ".json")) as f:
        return json.load(f)
