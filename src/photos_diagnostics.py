"""
src/photos_diagnostics.py
==========================
Deep diagnostic suite for Google Photos API endpoints and OAuth scope inspection.

Logs full status codes, request headers, response headers, and raw JSON error
responses to research_logs/photos_debug.log.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

# Resolve project root
ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "research_logs" / "photos_debug.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# Setup logging to file and console
logger = logging.getLogger("photos_diagnostics")
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(file_handler)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(stream_handler)


def log_debug_section(title: str, content: str) -> None:
    logger.info("=" * 60)
    logger.info("  %s", title)
    logger.info("=" * 60)
    logger.info("%s\n", content)


def main() -> None:
    load_dotenv(ROOT / ".env")

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_PHOTOS_REFRESH_TOKEN")

    logger.info("Starting Google Photos API Diagnostics Suite...")
    logger.info("Log file destination: %s\n", LOG_FILE)

    if not all([client_id, client_secret, refresh_token]):
        logger.error("Missing Google OAuth environment variables in .env")
        return

    # ── Step 1: Refresh Access Token ──────────────────────────────────────────
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    logger.info("[Step 1] Exchanging refresh token for access token...")
    token_res = requests.post(token_url, data=payload)
    if token_res.status_code != 200:
        logger.error("Token Exchange Failed (HTTP %d):\n%s", token_res.status_code, token_res.text)
        return

    access_token = token_res.json().get("access_token")
    logger.info("✅ Access token retrieved successfully.\n")

    # ── Step 2: Token Scope Inspection ────────────────────────────────────────
    logger.info("[Step 2] Inspecting granted scopes via TokenInfo endpoint...")
    token_info_res = requests.get(
        "https://oauth2.googleapis.com/tokeninfo",
        params={"access_token": access_token},
    )

    scope_report = []
    scope_report.append(f"HTTP Status: {token_info_res.status_code}")
    if token_info_res.status_code == 200:
        info_data = token_info_res.json()
        scope_report.append(f"Granted Scopes:\n{info_data.get('scope', 'None')}")
        scope_report.append(f"Audience / Client ID: {info_data.get('aud', '')}")
        scope_report.append(f"Expires In: {info_data.get('expires_in', '')} seconds")
    else:
        scope_report.append(f"Error: {token_info_res.text}")

    log_debug_section("TOKEN SCOPE INSPECTION REPORT", "\n".join(scope_report))

    # ── Step 3: Endpoint Probes ───────────────────────────────────────────────
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    endpoints = [
        (
            "Probe A: GET /v1/mediaItems?pageSize=1",
            "GET",
            "https://photoslibrary.googleapis.com/v1/mediaItems?pageSize=1",
            None,
        ),
        (
            "Probe B: GET /v1/albums",
            "GET",
            "https://photoslibrary.googleapis.com/v1/albums",
            None,
        ),
        (
            "Probe C: POST /v1/mediaItems:search",
            "POST",
            "https://photoslibrary.googleapis.com/v1/mediaItems:search",
            json.dumps({"pageSize": "1"}),
        ),
    ]

    for label, method, url, body in endpoints:
        logger.info("[Step 3] Running %s...", label)
        try:
            if method == "GET":
                res = requests.get(url, headers=headers, timeout=15)
            else:
                res = requests.post(url, headers=headers, data=body, timeout=15)

            report = []
            report.append(f"Method & URL: {method} {url}")
            report.append(f"HTTP Status Code: {res.status_code}")
            report.append("\n--- Request Headers ---")
            for k, v in headers.items():
                masked_v = v[:20] + "..." if k == "Authorization" else v
                report.append(f"{k}: {masked_v}")

            report.append("\n--- Response Headers ---")
            for k, v in res.headers.items():
                report.append(f"{k}: {v}")

            report.append("\n--- Response Body ---")
            try:
                report.append(json.dumps(res.json(), indent=2))
            except Exception:
                report.append(res.text)

            log_debug_section(f"PROBE RESULT: {label}", "\n".join(report))

        except Exception as exc:
            logger.error("Probe %s failed with exception: %s", label, exc)

    logger.info("Diagnostics completed. Detailed report written to %s\n", LOG_FILE)


if __name__ == "__main__":
    main()
