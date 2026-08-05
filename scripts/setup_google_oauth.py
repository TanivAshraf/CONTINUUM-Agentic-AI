#!/usr/bin/env python3
"""
scripts/setup_google_oauth.py
==============================
Interactive OAuth 2.0 token generator for CONTINUUM Agentic AI.

Authorises access to:
  - Google Photos Library API (read-only)
  - Gmail API (read-only)

On success, writes the following keys directly into your local .env file:
  GOOGLE_PHOTOS_REFRESH_TOKEN
  GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET

Usage:
    python3 scripts/setup_google_oauth.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# ── Resolve project root (one level up from scripts/) ─────────────────────────
ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
CLIENT_SECRET_FILE = ROOT / "client_secret.json"

# ── Required OAuth scopes ─────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/photoslibrary.readonly",
    "https://www.googleapis.com/auth/photoslibrary",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _print_banner() -> None:
    print()
    print("═" * 60)
    print("  CONTINUUM — Google OAuth 2.0 Setup")
    print("═" * 60)
    print()


def _print_instructions() -> None:
    """Print step-by-step instructions for obtaining client_secret.json."""
    print("⚠️   client_secret.json not found in the project root.")
    print()
    print("  Follow these steps to create one:")
    print()
    print("  1. Open Google Cloud Console:")
    print("     https://console.cloud.google.com/")
    print()
    print("  2. Select (or create) your project.")
    print()
    print("  3. Enable the required APIs:")
    print("     • Photos Library API:")
    print("       https://console.cloud.google.com/apis/library/photoslibrary.googleapis.com")
    print("     • Gmail API:")
    print("       https://console.cloud.google.com/apis/library/gmail.googleapis.com")
    print()
    print("  4. Go to: APIs & Services → Credentials")
    print("     https://console.cloud.google.com/apis/credentials")
    print()
    print("  5. Click  [+ CREATE CREDENTIALS]  →  OAuth client ID")
    print()
    print("  6. Application type:  Desktop app")
    print("     Name (any):        CONTINUUM Local")
    print()
    print("  7. Click [CREATE], then [DOWNLOAD JSON].")
    print()
    print("  8. Rename the downloaded file to  client_secret.json")
    print("     and place it in:")
    print(f"     {ROOT}/")
    print()
    print("  9. If prompted to configure the OAuth consent screen, set:")
    print("     • User type: External")
    print("     • Add your own Google account as a Test User")
    print()
    print("  Then re-run:  python3 scripts/setup_google_oauth.py")
    print()


def _update_env(key: str, value: str) -> None:
    """
    Upsert a key=value pair in the .env file.
    - If the key already exists, replace its line.
    - If it does not exist, append it.
    """
    content = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    pattern = re.compile(rf"^{re.escape(key)}\s*=.*$", re.MULTILINE)

    if pattern.search(content):
        new_content = pattern.sub(f"{key}={value}", content)
    else:
        new_content = content.rstrip("\n") + f"\n{key}={value}\n"

    ENV_FILE.write_text(new_content, encoding="utf-8")


def _check_dependencies() -> None:
    """Ensure required packages are importable; print install hint if not."""
    missing = []
    for pkg in ("google_auth_oauthlib", "google.auth"):
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            missing.append(pkg)
    if missing:
        print("❌  Missing Python packages:", ", ".join(missing))
        print()
        print("    Install them with:")
        print("      pip3 install google-auth-oauthlib google-auth")
        print()
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Main OAuth Flow
# ─────────────────────────────────────────────────────────────────────────────

def run_oauth_flow() -> None:
    _print_banner()
    _check_dependencies()

    # ── Check for client_secret.json ──────────────────────────────────────────
    if not CLIENT_SECRET_FILE.exists():
        _print_instructions()
        sys.exit(1)

    print(f"✅  Found: {CLIENT_SECRET_FILE.name}")
    print()
    print("  Scopes to be authorised:")
    for scope in SCOPES:
        print(f"    • {scope}")
    print()
    print("  Launching browser consent window...")
    print()

    # ── Run InstalledAppFlow ──────────────────────────────────────────────────
    from google_auth_oauthlib.flow import InstalledAppFlow

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRET_FILE),
            scopes=SCOPES,
        )
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        print("  If browser does not open automatically, visit this URL:")
        print(f"\n  {auth_url}\n")
        sys.stdout.flush()
        # run_local_server opens the browser and handles the redirect on localhost
        credentials = flow.run_local_server(
            port=0,                  # pick any available port
            prompt="consent",        # force consent screen to ensure refresh_token is issued
            access_type="offline",   # required to receive a refresh_token
        )
    except Exception as exc:
        print(f"\n❌  OAuth flow failed: {exc}")
        print()
        print("  Common causes:")
        print("  • Your Google account is not added as a Test User in Cloud Console.")
        print("  • The OAuth consent screen has not been configured.")
        print("  • A firewall is blocking localhost redirect.")
        sys.exit(1)

    # ── Extract tokens ────────────────────────────────────────────────────────
    refresh_token = credentials.refresh_token
    client_id = credentials.client_id
    client_secret = credentials.client_secret

    if not refresh_token:
        print()
        print("⚠️   No refresh_token was returned by Google.")
        print()
        print("  This usually means the app was already authorized without")
        print("  'offline' access. To fix this:")
        print()
        print("  1. Visit: https://myaccount.google.com/permissions")
        print("  2. Find your OAuth app (CONTINUUM Local) and click [Remove Access].")
        print("  3. Re-run this script — Google will issue a fresh refresh_token.")
        print()
        sys.exit(1)

    # ── Write to .env ─────────────────────────────────────────────────────────
    _update_env("GOOGLE_PHOTOS_REFRESH_TOKEN", refresh_token)
    _update_env("GOOGLE_CLIENT_ID", client_id)
    _update_env("GOOGLE_CLIENT_SECRET", client_secret)

    print()
    print("═" * 60)
    print("  ✅  Authorization successful!")
    print("═" * 60)
    print()
    print(f"  Written to: {ENV_FILE}")
    print()
    print("  Keys updated:")
    print(f"    GOOGLE_CLIENT_ID          = {client_id[:16]}...")
    print(f"    GOOGLE_CLIENT_SECRET      = {client_secret[:6]}...")
    print(f"    GOOGLE_PHOTOS_REFRESH_TOKEN = {refresh_token[:16]}...")
    print()
    print("  Note: The same refresh token covers both Photos and Gmail")
    print("  (both scopes were authorised in a single consent session).")
    print()
    print("  You can optionally copy the same refresh token value to")
    print("  GMAIL_REFRESH_TOKEN in your .env if you use Gmail separately.")
    print()

    # ── Optionally also write GMAIL_REFRESH_TOKEN ─────────────────────────────
    answer = input("  Also write this token as GMAIL_REFRESH_TOKEN? [Y/n]: ").strip().lower()
    if answer in ("", "y", "yes"):
        _update_env("GMAIL_REFRESH_TOKEN", refresh_token)
        print("  ✅  GMAIL_REFRESH_TOKEN written.")

    print()
    print("  CONTINUUM is now authorised. Run the pipeline with:")
    print("    python3 main.py")
    print()
    print("═" * 60)
    print()


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_oauth_flow()
