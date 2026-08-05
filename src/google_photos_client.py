"""
src/google_photos_client.py
============================
Google Drive & Photos image ingestion module for CONTINUUM Agentic AI.

Uses Google Drive v3 API to search and ingest image files (JPEG, PNG, WebP)
from Google Drive and connected Photos storage, tracking processed file IDs
in system_memory.json for incremental pipeline processing.
"""

from __future__ import annotations

import logging
from typing import Generator

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from config.settings import settings

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GooglePhotosClient:
    """Authenticated client for Google Drive & Photos image ingestion."""

    def __init__(self) -> None:
        self._service = None

    def _get_service(self):
        """Build and cache authorised Google Drive API service."""
        if self._service is not None:
            return self._service

        creds = Credentials(
            token=None,
            refresh_token=settings.GOOGLE_PHOTOS_REFRESH_TOKEN,
            token_uri=_TOKEN_URL,
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/photoslibrary.readonly",
            ],
        )
        creds.refresh(Request())
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def list_recent_media_items(
        self,
        page_size: int = 10,
        since_item_id: str | None = None,
    ) -> Generator[dict, None, None]:
        """
        Yield recent image files from Google Drive / Photos in reverse-chronological order.

        Args:
            page_size: Number of items per API page.
            since_item_id: Stop iteration when this file ID is encountered.

        Yields:
            Standardised media-item dict compatible with CONTINUUM pipeline.
        """
        try:
            service = self._get_service()
        except Exception as exc:
            logger.warning("Google Drive client authorization error: %s", exc)
            return

        page_token: str | None = None
        query = (
            "mimeType contains 'image/' and trashed = false "
            "and not name contains 'Screenshot' "
            "and not name contains 'Screen_Shot' "
            "and not name contains 'capture'"
        )
        yielded_count = 0

        while True:
            params = {
                "q": query,
                "orderBy": "createdTime desc",
                "pageSize": min(page_size, 100),
                "fields": "nextPageToken, files(id, name, mimeType, createdTime, webContentLink, thumbnailLink)",
            }
            if page_token:
                params["pageToken"] = page_token

            try:
                result = service.files().list(**params).execute()
            except Exception as exc:
                logger.warning(
                    "Google Drive image query failed (insufficient scope or permission): %s",
                    exc,
                )
                return

            files = result.get("files", [])
            
            # Prioritise camera filenames (PXL_, IMG_, .jpg, .jpeg) over generic files
            def _is_camera_file(f: dict) -> bool:
                fname = f.get("name", "").lower()
                return (
                    fname.startswith("pxl_")
                    or fname.startswith("img_")
                    or fname.endswith(".jpg")
                    or fname.endswith(".jpeg")
                )

            # Sort files so camera photos come first
            files.sort(key=lambda f: 0 if _is_camera_file(f) else 1)

            for file_item in files:
                file_id = file_item["id"]
                fname = file_item.get("name", "").lower()

                # Additional python-side safeguard against screenshots/captures
                if any(x in fname for x in ("screenshot", "screen_shot", "screen", "capture")):
                    continue

                if since_item_id and file_id == since_item_id:
                    logger.info(
                        "Reached last processed image file %s — stopping.", since_item_id
                    )
                    return

                yield {
                    "id": file_id,
                    "name": file_item.get("name", "untitled.jpg"),
                    "baseUrl": file_id,
                    "mediaMetadata": {
                        "creationTime": file_item.get("createdTime", "")
                    },
                    "mimeType": file_item.get("mimeType", "image/jpeg"),
                }
                yielded_count += 1
                if yielded_count >= page_size:
                    return

            page_token = result.get("nextPageToken")
            if not page_token:
                break

    def download_image_bytes(self, file_id_or_url: str, width: int = 1024) -> bytes:
        """
        Download raw image bytes for a Google Drive file ID.

        Args:
            file_id_or_url: The Google Drive file ID.
            width: Parameter preserved for signature compatibility.

        Returns:
            Raw image bytes.
        """
        service = self._get_service()
        logger.info("Downloading image bytes for file ID: %s", file_id_or_url)
        return service.files().get_media(fileId=file_id_or_url).execute()

    def get_item_metadata(self, media_item_id: str) -> dict:
        """Fetch metadata for a single Google Drive file by ID."""
        service = self._get_service()
        return (
            service.files()
            .get(fileId=media_item_id, fields="id, name, mimeType, createdTime, size")
            .execute()
        )
