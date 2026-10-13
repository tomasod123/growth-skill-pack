#!/usr/bin/env python3
"""
Read a single prospect row from a CSV file or a Google Sheet and print it as JSON.

    python3 read_prospect.py --csv leads.csv --row 1
    python3 read_prospect.py --url "<Google Sheet URL or id>" --row 1 [--worksheet NAME]

Rows are 1-indexed, excluding the header. Column names are normalised
(company / company_name / organization_name -> company_name, etc.).

Google Sheets needs: pip install gspread google-auth google-auth-oauthlib
and an OAuth desktop client file. Paths come from env vars:
  GOOGLE_OAUTH_CLIENT_FILE  (default: credentials.json in the current folder)
  GOOGLE_TOKEN_FILE         (default: token.json in the current folder; created on first login)
"""

import argparse
import csv
import json
import os
import sys

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly',
]

MAPPING = {
    'company': 'company_name', 'company_name': 'company_name', 'organization_name': 'company_name',
    'about': 'description', 'description': 'description', 'company_description': 'description',
    'keywords': 'keywords', 'services': 'keywords', 'company_keywords': 'keywords',
    'phone': 'phone', 'phone_number': 'phone', 'company_phone': 'phone',
    'email': 'email', 'contact_email': 'email',
    'address': 'address', 'full_address': 'address', 'company_address': 'address',
    'city': 'city', 'state': 'state', 'country': 'country',
    'industry': 'industry', 'category': 'industry',
    'first_name': 'first_name', 'last_name': 'last_name',
    'title': 'title', 'role': 'title',
    'website': 'website', 'company_website': 'website',
}


def normalize_key(key):
    k = key.strip().lower().replace(' ', '_').replace('-', '_')
    return MAPPING.get(k, k)


def normalise_row(raw):
    out = {}
    for key, value in raw.items():
        if key is None:
            continue
        if value not in (None, ''):
            out[normalize_key(key)] = str(value)
    return out


def pick(records, row_number):
    if row_number < 1 or row_number > len(records):
        print(f"Error: Row {row_number} out of range (1-{len(records)})", file=sys.stderr)
        sys.exit(1)
    return normalise_row(records[row_number - 1])


def read_csv(path, row_number):
    with open(path, newline='', encoding='utf-8-sig') as f:
        records = list(csv.DictReader(f))
    return pick(records, row_number)


def get_credentials():
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
    except ImportError:
        sys.exit("Google libraries missing: pip install gspread google-auth google-auth-oauthlib "
                 "(or use --csv instead)")
    token_file = os.getenv("GOOGLE_TOKEN_FILE", "token.json")
    client_file = os.getenv("GOOGLE_OAUTH_CLIENT_FILE", "credentials.json")
    creds = None
    if os.path.exists(token_file):
        try:
            with open(token_file) as f:
                creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(client_file):
                sys.exit(f"OAuth client file not found: {client_file} (set GOOGLE_OAUTH_CLIENT_FILE)")
            flow = InstalledAppFlow.from_client_secrets_file(client_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'w') as f:
            f.write(creds.to_json())
    return creds


def extract_sheet_id(url):
    if '/d/' in url:
        return url.split('/d/')[1].split('/')[0]
    return url


def read_sheet(sheet_url, row_number, worksheet_name=None):
    try:
        import gspread
    except ImportError:
        sys.exit("gspread missing: pip install gspread google-auth google-auth-oauthlib (or use --csv)")
    client = gspread.authorize(get_credentials())
    spreadsheet = client.open_by_key(extract_sheet_id(sheet_url))
    ws = spreadsheet.worksheet(worksheet_name) if worksheet_name else spreadsheet.sheet1
    return pick(ws.get_all_records(), row_number)


def main():
    ap = argparse.ArgumentParser(description="Read one prospect row as JSON")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv", help="CSV file path")
    src.add_argument("--url", help="Google Sheets URL or id")
    ap.add_argument("--row", required=True, type=int, help="Row number (1-indexed, excluding header)")
    ap.add_argument("--worksheet", help="Worksheet name (Sheets only; default: first sheet)")
    args = ap.parse_args()
    if args.csv:
        prospect = read_csv(args.csv, args.row)
    else:
        prospect = read_sheet(args.url, args.row, args.worksheet)
    print(json.dumps(prospect, indent=2))


if __name__ == "__main__":
    main()
