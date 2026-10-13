#!/usr/bin/env python3
"""One-time: get a Google Ads refresh token for GOOGLE_ADS_REFRESH_TOKEN.

Reads GOOGLE_ADS_CLIENT_ID and GOOGLE_ADS_CLIENT_SECRET from ../.env (or the environment), opens Google's
sign-in in your browser, and prints the refresh token. Sign in with the Google user that can see the
Google Ads account (or its manager account). Scope: adwords (the hub itself only reads).

  python3 tools/google_oauth.py              # opens a browser on this machine
  python3 tools/google_oauth.py --no-browser # prints the link instead (machines without a browser)
On a remote server, first open a tunnel from your laptop:  ssh -L 8085:localhost:8085 you@server
then open the printed link in your laptop's browser; Google redirects to localhost:8085, which the tunnel forwards.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sources.common import load_env  # noqa: E402

SCOPES = ["https://www.googleapis.com/auth/adwords"]


def main():
    env = load_env(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    cid, secret = env.get("GOOGLE_ADS_CLIENT_ID"), env.get("GOOGLE_ADS_CLIENT_SECRET")
    if not cid or not secret:
        sys.exit("Fill GOOGLE_ADS_CLIENT_ID and GOOGLE_ADS_CLIENT_SECRET in .env first (SETUP.md, Google Ads step 3).")
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_config(
        {"installed": {"client_id": cid, "client_secret": secret, "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                       "token_uri": "https://oauth2.googleapis.com/token", "redirect_uris": ["http://localhost"]}}, SCOPES)
    creds = flow.run_local_server(port=8085, prompt="consent", access_type="offline",
                                  open_browser="--no-browser" not in sys.argv)
    if not creds.refresh_token:
        sys.exit("Google returned no refresh token. Remove the app at myaccount.google.com/permissions and run again.")
    print("\nAdd this line to .env:\n")
    print("GOOGLE_ADS_REFRESH_TOKEN=" + creds.refresh_token)


if __name__ == "__main__":
    main()
