"""
src/google_photos_client.py
============================
Pure Headless Google Photos Library API Client for CONTINUUM Agentic AI.

Connects strictly to Google Photos Library API (photoslibrary.googleapis.com).
Target Album: "CHINA 2026" (fallbacks: "China Photos", "Continuum Photos").

Features:
  - 100% Headless OAuth2 token refresh via HTTP POST to https://oauth2.googleapis.com/token.
  - Zero interactive polling loops, browser prompts, or waiting logic.
  - Zero Google Drive API dependency.
  - Queries GET /v1/albums to resolve the target albumId.
  - Queries POST /v1/mediaItems:search with {"albumId": album_id, "pageSize": 10}.
  - Downloads high-resolution photo bytes directly via baseUrl=s2048.
  - Incremental filtering using system_memory.json last_processed_media_item_id.
"""

from __future__ import annotations

import logging
from typing import Generator

import requests

from config.settings import settings

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_LIBRARY_BASE = "https://photoslibrary.googleapis.com/v1"

_TARGET_ALBUM_NAMES = ["china 2026", "china photos", "china", "continuum photos"]


class GooglePhotosClient:
    """Headless Google Photos Library API client for targeted album ingestion."""

    def __init__(self) -> None:
        self._access_token: str | None = None
        self._album_id: str | None = None

    def _get_headless_access_token(self) -> str:
        """
        Refresh access token directly via HTTP POST to Google OAuth2 token endpoint.
        Returns access_token or raises an exception.
        """
        if self._access_token:
            return self._access_token

        payload = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "refresh_token": settings.GOOGLE_PHOTOS_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        }
        resp = requests.post(_TOKEN_URL, data=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise ValueError(f"No access_token returned in OAuth refresh response: {data}")
        self._access_token = token
        logger.info("[GooglePhotos] Headless access token obtained.")
        return self._access_token

    def _headers(self) -> dict[str, str]:
        """Return Authorization headers for Google Photos Library API."""
        return {"Authorization": f"Bearer {self._get_headless_access_token()}"}

    def _find_album_id(self) -> str | None:
        """
        Query GET /v1/albums to locate album matching CHINA 2026.
        Returns albumId string if found, None otherwise.
        """
        if self._album_id:
            return self._album_id

        logger.info("[GooglePhotos] Querying GET /v1/albums for target album...")
        page_token: str | None = None
        all_albums: list[dict] = []

        while True:
            params: dict = {"pageSize": 50}
            if page_token:
                params["pageToken"] = page_token

            try:
                resp = requests.get(
                    f"{_LIBRARY_BASE}/albums",
                    headers=self._headers(),
                    params=params,
                    timeout=15,
                )
            except Exception as exc:
                logger.warning("[GooglePhotos] Album lookup request failed: %s", exc)
                return None

            if resp.status_code == 403:
                logger.warning(
                    "[GooglePhotos] 403 Forbidden — Photos Library API not enabled or scope missing. "
                    "Ensure 'Photos Library API' is enabled in Google Cloud Console."
                )
                return None

            if not resp.ok:
                logger.warning("[GooglePhotos] GET /v1/albums error %d: %s", resp.status_code, resp.text[:200])
                return None

            data = resp.json()
            all_albums.extend(data.get("albums", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        logger.info("[GooglePhotos] Found %d total album(s) in Google Photos.", len(all_albums))
        for album in all_albums:
            logger.info("  · Album title: '%s' (id=%s)", album.get("title"), album.get("id"))

        # Match against target album names in order of priority
        for target in _TARGET_ALBUM_NAMES:
            for album in all_albums:
                title = album.get("title", "").lower().strip()
                if title == target or title.startswith(target):
                    self._album_id = album["id"]
                    logger.info(
                        "[GooglePhotos] ✅ Matched target album '%s' → albumId=%s",
                        album.get("title"),
                        self._album_id,
                    )
                    return self._album_id

        logger.warning(
            "[GooglePhotos] Target album %s not found among user's Google Photos albums.",
            _TARGET_ALBUM_NAMES,
        )
        return None

    def list_recent_media_items(
        self,
        page_size: int = 10,
        since_item_id: str | None = None,
    ) -> Generator[dict, None, None]:
        """
        Yield recent image files from the target album ('CHINA 2026') in reverse-chronological order.

        Excludes videos and screenshot files. Stops when since_item_id is encountered.
        Returns immediately (non-blocking, pure headless execution).

        Args:
            page_size: Number of items per page.
            since_item_id: Stop iteration when this item ID is encountered.

        Yields:
            Standardised media-item dict: id, name, baseUrl, mediaMetadata, mimeType.
        """
        try:
            album_id = self._find_album_id()
        except Exception as exc:
            logger.warning("[GooglePhotos] Headless token error: %s", exc)
            return

        if not album_id:
            logger.warning("[GooglePhotos] Skipping photo search — no target album found.")
            return

        logger.info("[GooglePhotos] Fetching media items for albumId=%s...", album_id)
        page_token: str | None = None
        yielded_count = 0

        while True:
            body: dict = {
                "albumId": album_id,
                "pageSize": min(page_size, 100),
            }
            if page_token:
                body["pageToken"] = page_token

            try:
                resp = requests.post(
                    f"{_LIBRARY_BASE}/mediaItems:search",
                    headers=self._headers(),
                    json=body,
                    timeout=15,
                )
            except Exception as exc:
                logger.warning("[GooglePhotos] mediaItems:search failed: %s", exc)
                return

            if not resp.ok:
                logger.warning("[GooglePhotos] mediaItems:search error %d: %s", resp.status_code, resp.text[:200])
                return

            data = resp.json()
            items = data.get("mediaItems", [])

            for item in items:
                item_id = item.get("id", "")
                mime = item.get("mimeType", "")

                if not mime.startswith("image/"):
                    continue

                filename = item.get("filename", "").lower()
                if any(x in filename for x in ("screenshot", "screen_shot", "capture")):
                    logger.info("[GooglePhotos] Skipping screenshot file: %s", filename)
                    continue

                if since_item_id and item_id == since_item_id:
                    logger.info("[GooglePhotos] Reached last processed item %s — stopping.", since_item_id)
                    return

                creation_time = item.get("mediaMetadata", {}).get("creationTime", "")
                base_url = item.get("baseUrl", "")

                yield {
                    "id": item_id,
                    "name": item.get("filename", "photo.jpg"),
                    "baseUrl": base_url,
                    "mediaMetadata": {
                        "creationTime": creation_time,
                        "photo": item.get("mediaMetadata", {}).get("photo", {}),
                    },
                    "mimeType": mime,
                }
                yielded_count += 1
                if yielded_count >= page_size:
                    return

            page_token = data.get("nextPageToken")
            if not page_token:
                break

    def download_image_bytes(self, base_url: str, width: int = 2048) -> bytes:
        """
        Download high-resolution image bytes from Google Photos baseUrl.

        Appends =s{width} for high-quality pixels (default s2048).

        Args:
            base_url: The Google Photos media item baseUrl.
            width: Image width in pixels.

        Returns:
            Raw image bytes.
        """
        download_url = f"{base_url}=s{width}"
        logger.info("[GooglePhotos] Downloading image at s%d: %s...", width, base_url[:80])

        # Attempt download with Bearer auth header, then fallback to direct request
        try:
            resp = requests.get(download_url, headers=self._headers(), timeout=30)
            if resp.status_code == 200:
                return resp.content
        except Exception as exc:
            logger.debug("[GooglePhotos] Download with auth header failed: %s", exc)

        resp = requests.get(download_url, timeout=30)
        resp.raise_for_status()
        return resp.content

    def get_item_metadata(self, media_item_id: str) -> dict:
        """Fetch metadata for a single Google Photos media item by ID."""
        try:
            resp = requests.get(
                f"{_LIBRARY_BASE}/mediaItems/{media_item_id}",
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("[GooglePhotos] Could not fetch metadata for %s: %s", media_item_id, exc)
            return {}
