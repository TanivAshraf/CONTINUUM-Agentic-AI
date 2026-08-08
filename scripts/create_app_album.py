#!/usr/bin/env python3
"""
scripts/create_app_album.py
===========================
Creates an app-owned Google Photos Album ("CONTINUUM CHINA 2026") via the
Google Photos Library API and saves the created albumId to data/system_memory.json.

App-owned albums created by the API permit full read/write/list access without
triggering 403 Forbidden restrictions associated with user-created albums.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests

from config.settings import settings
from src.google_photos_client import GooglePhotosClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("create_app_album")

MEMORY_FILE = Path(settings.MEMORY_FILE)
_LIBRARY_BASE = "https://photoslibrary.googleapis.com/v1"


def create_app_album() -> None:
    client = GooglePhotosClient()
    token = client._get_headless_access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    payload = {"album": {"title": "CONTINUUM CHINA 2026"}}

    logger.info("Creating app-owned Google Photos album: 'CONTINUUM CHINA 2026'...")
    resp = requests.post(f"{_LIBRARY_BASE}/albums", headers=headers, json=payload, timeout=30)
    
    if not resp.ok:
        print("\n" + "═" * 60)
        print("  ❌ Album Creation Failed")
        print("═" * 60)
        print(f"  HTTP Status Code : {resp.status_code}")
        print(f"  Raw Error Body   :\n{resp.text}")
        print("═" * 60 + "\n")
        return

    album_data = resp.json()
    album_id = album_data.get("id")
    product_url = album_data.get("productUrl", "")

    print("\n" + "=" * 60)
    print("  ✅ App-Owned Google Photos Album Created Successfully!")
    print("=" * 60)
    print(f"  Album Title : {album_data.get('title')}")
    print(f"  Album ID    : {album_id}")
    print(f"  Product URL : {product_url}")
    print("=" * 60 + "\n")

    # Save albumId into data/system_memory.json under google_photos.app_album_id
    memory = {}
    if MEMORY_FILE.exists():
        try:
            memory = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            memory = {}

    memory.setdefault("google_photos", {})["app_album_id"] = album_id
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(memory, indent=2), encoding="utf-8")
    logger.info("Saved app_album_id '%s' to %s", album_id, MEMORY_FILE)


if __name__ == "__main__":
    create_app_album()
