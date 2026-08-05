"""
src/google_photos_client.py
============================
Google Photos API client for CONTINUUM Agentic AI.

Handles OAuth token refresh, media-item enumeration, and downloading raw
image bytes for downstream Gemini processing. Tracks the last processed
media item ID in system memory to avoid re-processing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Generator

import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from config.settings import settings

logger = logging.getLogger(__name__)

# Google Photos API base URL
_PHOTOS_API = "https://photoslibrary.googleapis.com/v1"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GooglePhotosClient:
    """Authenticated client for the Google Photos Library API."""

    def __init__(self) -> None:
        self._credentials: Credentials | None = None
        self._session = requests.Session()

    # ── Authentication ────────────────────────────────────────────────────────

    def _build_credentials(self) -> Credentials:
        """Build (and auto-refresh) OAuth2 credentials from stored tokens."""
        creds = Credentials(
            token=None,
            refresh_token=settings.GOOGLE_PHOTOS_REFRESH_TOKEN,
            token_uri=_TOKEN_URL,
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/photoslibrary.readonly"],
        )
        creds.refresh(Request())
        return creds

    def _get_headers(self) -> dict[str, str]:
        """Return authorised request headers, refreshing the token if needed."""
        if self._credentials is None or not self._credentials.valid:
            self._credentials = self._build_credentials()
        return {"Authorization": f"Bearer {self._credentials.token}"}

    # ── Media Item Retrieval ──────────────────────────────────────────────────

    def list_recent_media_items(
        self,
        page_size: int = 25,
        since_item_id: str | None = None,
    ) -> Generator[dict, None, None]:
        """
        Yield media items from Google Photos in reverse-chronological order.

        Args:
            page_size: Number of items per API page (max 100).
            since_item_id: Stop iteration when this item ID is encountered,
                           useful for incremental processing.

        Yields:
            Raw media-item dicts from the Google Photos API.
        """
        page_token: str | None = None

        while True:
            payload: dict = {"pageSize": page_size}
            if page_token:
                payload["pageToken"] = page_token

            response = self._session.get(
                f"{_PHOTOS_API}/mediaItems",
                headers=self._get_headers(),
                params=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            items = data.get("mediaItems", [])
            for item in items:
                if since_item_id and item.get("id") == since_item_id:
                    logger.info(
                        "Reached last processed item %s — stopping.", since_item_id
                    )
                    return
                yield item

            page_token = data.get("nextPageToken")
            if not page_token:
                break

    def download_image_bytes(self, base_url: str, width: int = 1024) -> bytes:
        """
        Download raw image bytes from a Google Photos base URL.

        Args:
            base_url: The baseUrl field from a media-item response.
            width: Desired width in pixels (height is auto-scaled).

        Returns:
            Raw image bytes (JPEG).
        """
        download_url = f"{base_url}=w{width}"
        response = self._session.get(download_url, timeout=60)
        response.raise_for_status()
        return response.content

    def get_item_metadata(self, media_item_id: str) -> dict:
        """Fetch metadata for a single media item by ID."""
        response = self._session.get(
            f"{_PHOTOS_API}/mediaItems/{media_item_id}",
            headers=self._get_headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
