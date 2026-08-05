#!/usr/bin/env python3
"""
scripts/fix_photos_oauth.py
===========================
Script to force OAuth 2.0 consent with include_granted_scopes='true',
update .env with new tokens, and test fetching recent Google Photos media items.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
import requests
from google_auth_oauthlib.flow import InstalledAppFlow

# Resolve project root
ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
CLIENT_SECRET_FILE = ROOT / "client_secret.json"

SCOPES = [
    "https://www.googleapis.com/auth/photoslibrary.readonly",
    "https://www.googleapis.com/auth/photoslibrary",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def update_env(key: str, value: str) -> None:
    """Upsert key=value in .env file."""
    content = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    pattern = re.compile(rf"^{re.escape(key)}\s*=.*$", re.MULTILINE)

    if pattern.search(content):
        new_content = pattern.sub(f"{key}={value}", content)
    else:
        new_content = content.rstrip("\n") + f"\n{key}={value}\n"

    ENV_FILE.write_text(new_content, encoding="utf-8")


def main() -> None:
    print("\n════════════════════════════════════════════════════════════")
    print("  CONTINUUM — Google Photos OAuth Fix & Verification")
    print("════════════════════════════════════════════════════════════\n")

    if not CLIENT_SECRET_FILE.exists():
        print(f"❌ client_secret.json not found at {CLIENT_SECRET_FILE}")
        sys.exit(1)

    print(f"✅ Loaded client_secret.json")
    print("Scopes requested:")
    for scope in SCOPES:
        print(f"  • {scope}")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRET_FILE),
        scopes=SCOPES,
    )

    auth_url, _ = flow.authorization_url(
        prompt="consent",
        access_type="offline",
        include_granted_scopes="true",
    )

    print("Please authorize in your browser. If it doesn't open, visit:")
    print(f"\n  {auth_url}\n")
    sys.stdout.flush()

    credentials = flow.run_local_server(
        port=0,
        prompt="consent",
        access_type="offline",
        include_granted_scopes="true",
    )

    refresh_token = credentials.refresh_token
    client_id = credentials.client_id
    client_secret = credentials.client_secret

    if not refresh_token:
        print("\n⚠️ No refresh_token returned. Please revoke app permissions at myaccount.google.com/permissions and retry.")
        sys.exit(1)

    # Update .env file
    update_env("GOOGLE_CLIENT_ID", client_id)
    update_env("GOOGLE_CLIENT_SECRET", client_secret)
    update_env("GOOGLE_PHOTOS_REFRESH_TOKEN", refresh_token)
    update_env("GMAIL_REFRESH_TOKEN", refresh_token)

    print("✅ .env updated with new GOOGLE_PHOTOS_REFRESH_TOKEN and GMAIL_REFRESH_TOKEN\n")

    # Immediate Test: Fetch 3 most recent photos
    print("Testing Google Photos API access...")
    token_res = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    if token_res.status_code != 200:
        print(f"❌ Token refresh failed: {token_res.text}")
        sys.exit(1)

    access_token = token_res.json()["access_token"]
    photos_res = requests.get(
        "https://photoslibrary.googleapis.com/v1/mediaItems?pageSize=3",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    print(f"Photos API Status Code: {photos_res.status_code}")
    if photos_res.status_code == 200:
        data = photos_res.json()
        items = data.get("mediaItems", [])
        print(f"✅ Successfully retrieved {len(items)} media items:\n")
        for i, item in enumerate(items, 1):
            filename = item.get("filename", "unknown")
            creation_time = item.get("mediaMetadata", {}).get("creationTime", "unknown")
            item_id = item.get("id", "")
            print(f"  {i}. Filename: {filename}")
            print(f"     Creation Time: {creation_time}")
            print(f"     ID: {item_id[:20]}...\n")
    else:
        print("Response Body:")
        print(photos_res.text)

    print("════════════════════════════════════════════════════════════\n")


if __name__ == "__main__":
    main()
