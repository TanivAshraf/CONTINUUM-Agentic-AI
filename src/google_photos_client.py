"""
src/google_photos_client.py
============================
Google Photos image ingestion client for CONTINUUM Agentic AI.

TWO-PATH ARCHITECTURE
─────────────────────
Path A — Google Photos Library API  (photoslibrary.googleapis.com)
  • Targets the "CHINA 2026" album by name via GET /v1/albums.
  • If the Photos Library API is enabled in Cloud Console, this path runs.
  • Downloads photos at s2048 resolution from baseUrl.

Path B — Google Photos Picker API  (photospicker.googleapis.com)
  • Used automatically when Path A returns 403 (Library API not enabled).
  • Session-based: creates a picker session → stores sessionId in
    data/system_memory.json → prompts user to open pickerUri in their
    browser and select photos → polls until mediaItemsSet=true → fetches
    the selected media items and downloads at s2048 resolution.
  • Subsequent pipeline runs resume the same session if still valid,
    so photos already selected are processed without re-prompting.

HARD LOCK: Root Google Drive is NEVER queried or searched.

SETUP REQUIRED (one-time):
  python3 scripts/setup_google_oauth.py
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Generator

import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from config.settings import settings

logger = logging.getLogger(__name__)

# ── API endpoints ─────────────────────────────────────────────────────────────
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_LIBRARY_BASE = "https://photoslibrary.googleapis.com/v1"
_PICKER_BASE = "https://photospicker.googleapis.com/v1"

# ── OAuth scopes ──────────────────────────────────────────────────────────────
_LIBRARY_SCOPES = [
    "https://www.googleapis.com/auth/photoslibrary.readonly",
    "https://www.googleapis.com/auth/photoslibrary",
]
_PICKER_SCOPES = [
    "https://www.googleapis.com/auth/photospicker.mediaitems.readonly",
]
_ALL_SCOPES = _LIBRARY_SCOPES + _PICKER_SCOPES

# Album name priority order (case-insensitive prefix match)
_TARGET_ALBUM_NAMES = ["china 2026", "china", "continuum photos"]

# Path to store Picker session state
_MEMORY_PATH = Path(__file__).resolve().parent.parent / "data" / "system_memory.json"

# Picker API polling config
_PICKER_POLL_INTERVAL_S = 5     # seconds between polls
_PICKER_MAX_WAIT_S = 600        # 10 minutes max wait for user selection


class GooglePhotosClient:
    """
    Dual-path Google Photos client.

    Tries Photos Library API first (album-targeted for 'CHINA 2026').
    Falls back to Picker API (session-based, user-selects photos) on 403.
    Google Drive is NEVER accessed.
    """

    def __init__(self) -> None:
        self._library_token: str | None = None
        self._picker_token: str | None = None
        self._album_id: str | None = None

    # ── Token Management ──────────────────────────────────────────────────────

    def _get_headless_access_token(self) -> str:
        """
        Refresh access token directly via HTTP POST to Google OAuth2 token endpoint.
        Sends client_id, client_secret, refresh_token, grant_type='refresh_token'.
        Does not rely on browser interaction or OAuth flow libraries.
        """
        payload = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "refresh_token": settings.GOOGLE_PHOTOS_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        }
        resp = requests.post(_TOKEN_URL, data=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        access_token = data.get("access_token")
        if not access_token:
            raise ValueError(f"No access_token returned in OAuth refresh response: {data}")
        return access_token

    def _get_token(self, scopes: list[str]) -> str:
        """Obtain a fresh access token for the given scopes via headless HTTP POST."""
        try:
            return self._get_headless_access_token()
        except Exception as exc:
            logger.warning("[GooglePhotos] Headless token refresh failed (%s) — falling back to google-auth", exc)
            creds = Credentials(
                token=None,
                refresh_token=settings.GOOGLE_PHOTOS_REFRESH_TOKEN,
                token_uri=_TOKEN_URL,
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET,
                scopes=scopes,
            )
            creds.refresh(Request())
            return creds.token

    def _library_headers(self) -> dict[str, str]:
        if not self._library_token:
            self._library_token = self._get_token(_LIBRARY_SCOPES)
            logger.info("[GooglePhotos] Library API token obtained.")
        return {"Authorization": f"Bearer {self._library_token}"}

    def _picker_headers(self) -> dict[str, str]:
        if not self._picker_token:
            self._picker_token = self._get_token(_PICKER_SCOPES)
            logger.info("[GooglePhotos] Picker API token obtained.")
        return {"Authorization": f"Bearer {self._picker_token}"}

    # ── System Memory (Picker session persistence) ────────────────────────────

    def _load_memory(self) -> dict:
        try:
            return json.loads(_MEMORY_PATH.read_text()) if _MEMORY_PATH.exists() else {}
        except Exception:
            return {}

    def _save_memory(self, memory: dict) -> None:
        try:
            _MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            _MEMORY_PATH.write_text(json.dumps(memory, indent=2))
        except Exception as exc:
            logger.warning("[GooglePhotos] Could not save memory: %s", exc)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PATH A — Photos Library API
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _find_album_id(self) -> str | None:
        """
        List all albums via GET /v1/albums and match 'CHINA 2026'.
        Returns albumId on success, None on 403 or no match.
        """
        if self._album_id:
            return self._album_id

        logger.info("[LibraryAPI] Fetching album list...")
        page_token: str | None = None
        all_albums: list[dict] = []

        while True:
            params: dict = {"pageSize": 50}
            if page_token:
                params["pageToken"] = page_token

            try:
                resp = requests.get(
                    f"{_LIBRARY_BASE}/albums",
                    headers=self._library_headers(),
                    params=params,
                    timeout=15,
                )
            except Exception as exc:
                logger.warning("[LibraryAPI] Album list request failed: %s", exc)
                return None

            if resp.status_code == 403:
                logger.warning(
                    "[LibraryAPI] 403 — Photos Library API not enabled or scope denied. "
                    "Switching to Picker API. Enable the API at:\n"
                    "  https://console.cloud.google.com/apis/library/"
                    "photoslibrary.googleapis.com"
                )
                return None

            if not resp.ok:
                logger.warning("[LibraryAPI] Album list error %d: %s", resp.status_code, resp.text[:200])
                return None

            data = resp.json()
            all_albums.extend(data.get("albums", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        logger.info("[LibraryAPI] Found %d album(s):", len(all_albums))
        for a in all_albums:
            logger.info("  · '%s'  (id=%s)", a.get("title"), a.get("id"))

        for target in _TARGET_ALBUM_NAMES:
            for album in all_albums:
                title = album.get("title", "").lower().strip()
                if title == target or title.startswith(target):
                    self._album_id = album["id"]
                    logger.info(
                        "[LibraryAPI] ✅ Matched album '%s' → albumId=%s",
                        album.get("title"), self._album_id,
                    )
                    return self._album_id

        logger.warning(
            "[LibraryAPI] No album matching %s found. Available: %s",
            _TARGET_ALBUM_NAMES,
            [a.get("title") for a in all_albums],
        )
        return None

    def _library_list_items(
        self,
        album_id: str,
        page_size: int,
        since_item_id: str | None,
    ) -> Generator[dict, None, None]:
        """Fetch photos from a Library API album. Yields standardised item dicts."""
        page_token: str | None = None
        yielded = 0

        while True:
            body: dict = {"albumId": album_id, "pageSize": min(page_size, 100)}
            if page_token:
                body["pageToken"] = page_token

            try:
                resp = requests.post(
                    f"{_LIBRARY_BASE}/mediaItems:search",
                    headers=self._library_headers(),
                    json=body,
                    timeout=30,
                )
            except Exception as exc:
                logger.warning("[LibraryAPI] mediaItems:search failed: %s", exc)
                return

            if not resp.ok:
                logger.warning("[LibraryAPI] Search error %d: %s", resp.status_code, resp.text[:200])
                return

            data = resp.json()
            for item in data.get("mediaItems", []):
                item_id = item.get("id", "")
                if not item.get("mimeType", "").startswith("image/"):
                    continue
                fname = item.get("filename", "").lower()
                if any(x in fname for x in ("screenshot", "screen_shot", "capture")):
                    logger.info("[LibraryAPI] Skipping screenshot: %s", fname)
                    continue
                if since_item_id and item_id == since_item_id:
                    logger.info("[LibraryAPI] Reached last processed item %s — stopping.", since_item_id)
                    return
                yield _normalise_item(item)
                yielded += 1
                if yielded >= page_size:
                    return

            page_token = data.get("nextPageToken")
            if not page_token:
                break

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PATH B — Photos Picker API
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _picker_get_or_create_session(self) -> dict | None:
        """
        Return an active Picker session dict.

        1. Check system_memory for a stored sessionId.
        2. If found, GET /v1/sessions/{id} — return it if still valid.
        3. Otherwise create a new session via POST /v1/sessions.
        """
        memory = self._load_memory()
        stored = memory.get("google_photos", {}).get("picker_session", {})
        session_id = stored.get("session_id")

        if session_id:
            logger.info("[PickerAPI] Resuming stored session: %s", session_id)
            try:
                resp = requests.get(
                    f"{_PICKER_BASE}/sessions/{session_id}",
                    headers=self._picker_headers(),
                    timeout=15,
                )
                if resp.ok:
                    session = resp.json()
                    logger.info(
                        "[PickerAPI] Session valid — mediaItemsSet=%s",
                        session.get("mediaItemsSet", False),
                    )
                    return session
                else:
                    logger.info("[PickerAPI] Stored session expired (%d) — creating new.", resp.status_code)
            except Exception as exc:
                logger.warning("[PickerAPI] Session check failed: %s", exc)

        # Create new session
        logger.info("[PickerAPI] Creating new Picker session...")
        try:
            resp = requests.post(
                f"{_PICKER_BASE}/sessions",
                headers=self._picker_headers(),
                json={},
                timeout=15,
            )
        except Exception as exc:
            logger.warning("[PickerAPI] Session creation failed: %s", exc)
            return None

        if not resp.ok:
            logger.error(
                "[PickerAPI] Could not create session %d: %s",
                resp.status_code, resp.text[:300],
            )
            return None

        session = resp.json()
        session_id = session.get("id")
        picker_uri = session.get("pickerUri", "")

        # Persist full session details to memory immediately
        memory.setdefault("google_photos", {})["picker_session"] = {
            "session_id": session_id,
            "picker_uri": picker_uri,
        }
        self._save_memory(memory)

        logger.info(
            "[PickerAPI] ✅ New session created: %s\n\n"
            "  ╔══════════════════════════════════════════════════════════════════╗\n"
            "  ║  📸  ACTION REQUIRED — Open this URL in your browser:          ║\n"
            "  ║                                                                ║\n"
            "  ║  %s  ║\n"
            "  ║                                                                ║\n"
            "  ║  Navigate to CHINA 2026 album → select photos → click Done    ║\n"
            "  ╚══════════════════════════════════════════════════════════════════╝\n",
            session_id,
            picker_uri,
        )
        return session

    def _picker_poll_until_ready(self, session_id: str) -> bool:
        """
        Poll GET /v1/sessions/{id} until mediaItemsSet=true or timeout.
        Returns True when items are ready.
        """
        deadline = time.time() + _PICKER_MAX_WAIT_S
        poll_interval = _PICKER_POLL_INTERVAL_S

        while time.time() < deadline:
            try:
                resp = requests.get(
                    f"{_PICKER_BASE}/sessions/{session_id}",
                    headers=self._picker_headers(),
                    timeout=15,
                )
                if not resp.ok:
                    logger.warning("[PickerAPI] Poll error %d", resp.status_code)
                    return False

                session_data: dict = resp.json()
                polling_cfg: dict = session_data.get("pollingConfig", {})

                # pollInterval is a duration string like '5s', not a nested dict
                raw_interval = polling_cfg.get("pollInterval", f"{_PICKER_POLL_INTERVAL_S}s")
                if isinstance(raw_interval, str) and raw_interval.endswith("s"):
                    suggested = int(raw_interval.rstrip("s"))
                elif isinstance(raw_interval, dict):
                    suggested = int(raw_interval.get("seconds", _PICKER_POLL_INTERVAL_S))
                else:
                    suggested = _PICKER_POLL_INTERVAL_S
                poll_interval = max(_PICKER_POLL_INTERVAL_S, suggested)

                if session_data.get("mediaItemsSet", False):
                    logger.info("[PickerAPI] ✅ Photos selection confirmed — mediaItemsSet=true")
                    return True

                logger.info(
                    "[PickerAPI] Waiting for user to finish photo selection (poll in %ds)...",
                    poll_interval,
                )
                time.sleep(poll_interval)

            except Exception as exc:
                logger.warning("[PickerAPI] Poll failed: %s", exc)
                return False

        logger.warning("[PickerAPI] Timed out waiting for photo selection after %ds.", _PICKER_MAX_WAIT_S)
        return False

    def _picker_list_items(
        self,
        session_id: str,
        page_size: int,
        since_item_id: str | None,
    ) -> Generator[dict, None, None]:
        """
        Fetch media items selected in a Picker session.

        Picker API response schema (different from Library API!):
          {
            "id": "ANqjti6...",
            "createTime": "2026-08-08T...",
            "type": "PHOTO",
            "mediaFile": {
              "baseUrl": "https://lh3.googleusercontent.com/...",
              "mimeType": "image/jpeg",
              "filename": "PXL_20260808.jpg",
              "mediaFileMetadata": { ... }
            }
          }
        """
        page_token: str | None = None
        yielded = 0

        while True:
            params: dict = {"sessionId": session_id, "pageSize": min(page_size, 100)}
            if page_token:
                params["pageToken"] = page_token

            try:
                resp = requests.get(
                    f"{_PICKER_BASE}/mediaItems",
                    headers=self._picker_headers(),
                    params=params,
                    timeout=30,
                )
            except Exception as exc:
                logger.warning("[PickerAPI] mediaItems list failed: %s", exc)
                return

            if not resp.ok:
                logger.warning("[PickerAPI] mediaItems error %d: %s", resp.status_code, resp.text[:300])
                return

            data = resp.json()
            raw_items = data.get("mediaItems", [])
            logger.info(
                "[PickerAPI] Page returned %d item(s). First item keys: %s",
                len(raw_items),
                list(raw_items[0].keys()) if raw_items else "(empty)",
            )

            for item in raw_items:
                item_id = item.get("id", "")
                # All media details live inside the 'mediaFile' sub-object
                media_file: dict = item.get("mediaFile", {})
                mime = media_file.get("mimeType", "")
                fname = media_file.get("filename", "").lower()
                base_url = media_file.get("baseUrl", "")
                create_time = item.get("createTime", "")

                logger.info(
                    "[PickerAPI]  · id=%-24s  type=%-8s  mime=%-12s  file=%s",
                    item_id[:24], item.get("type", "?"), mime, fname or "(no filename)",
                )

                if not mime.startswith("image/"):
                    logger.info("[PickerAPI]    → Skipped (not an image)")
                    continue
                if any(x in fname for x in ("screenshot", "screen_shot", "capture")):
                    logger.info("[PickerAPI]    → Skipped (screenshot filename)")
                    continue
                if since_item_id and item_id == since_item_id:
                    logger.info("[PickerAPI]    → Reached last processed item — stopping.")
                    return

                yield {
                    "id": item_id,
                    "name": media_file.get("filename", "photo.jpg"),
                    "baseUrl": base_url,
                    "mediaMetadata": {
                        "creationTime": create_time,
                        "photo": media_file.get("mediaFileMetadata", {}),
                    },
                    "mimeType": mime,
                }
                yielded += 1
                if yielded >= page_size:
                    return

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        # Clean up session after all items consumed
        if yielded > 0:
            self._delete_picker_session(session_id)

    def _delete_picker_session(self, session_id: str) -> None:
        """DELETE /v1/sessions/{id} to release the session after processing."""
        try:
            resp = requests.delete(
                f"{_PICKER_BASE}/sessions/{session_id}",
                headers=self._picker_headers(),
                timeout=10,
            )
            if resp.ok:
                logger.info("[PickerAPI] Session %s deleted after processing.", session_id)
                # Clear from memory
                memory = self._load_memory()
                memory.get("google_photos", {}).pop("picker_session", None)
                self._save_memory(memory)
        except Exception as exc:
            logger.warning("[PickerAPI] Could not delete session %s: %s", session_id, exc)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Public Interface
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def list_recent_media_items(
        self,
        page_size: int = 20,
        since_item_id: str | None = None,
    ) -> Generator[dict, None, None]:
        """
        Yield recent photos using whichever API path succeeds.

        Path A: Photos Library API — album 'CHINA 2026' via albumId search.
        Path B: Photos Picker API — session-based, prompts user if needed.

        Google Drive is NEVER queried.

        Args:
            page_size: Max number of photos to yield.
            since_item_id: Stop when this media item ID is encountered.

        Yields:
            Standardised media-item dict: id, name, baseUrl, mediaMetadata, mimeType.
        """
        # ── Path A: Library API ───────────────────────────────────────────────
        try:
            album_id = self._find_album_id()
        except Exception as exc:
            logger.warning("[LibraryAPI] Token/auth error: %s", exc)
            album_id = None

        if album_id:
            logger.info("[GooglePhotos] Using Path A — Library API (album: CHINA 2026)")
            yield from self._library_list_items(album_id, page_size, since_item_id)
            return

        # ── Path B: Picker API ────────────────────────────────────────────────
        logger.info("[GooglePhotos] Switching to Path B — Photos Picker API")

        try:
            picker_headers = self._picker_headers()
        except Exception as exc:
            logger.warning(
                "[PickerAPI] Token error — ensure photospicker.mediaitems.readonly "
                "scope is granted. Re-run: python3 scripts/setup_google_oauth.py\n"
                "Error: %s", exc,
            )
            return

        session = self._picker_get_or_create_session()
        if not session:
            logger.error("[PickerAPI] Could not obtain a Picker session.")
            return

        session_id = session.get("id")
        media_items_set = session.get("mediaItemsSet", False)

        if not media_items_set:
            logger.info("[PickerAPI] Waiting for user to select photos in the picker...")
            media_items_set = self._picker_poll_until_ready(session_id)

        if not media_items_set:
            logger.warning(
                "[PickerAPI] No photos selected yet. "
                "Run the pipeline again after opening the picker URL and selecting photos."
            )
            return

        logger.info("[PickerAPI] Fetching selected media items from session %s...", session_id)
        # NOTE: Do NOT pass since_item_id to the Picker path.
        # Picker sessions only contain user-selected photos — we always want all of them.
        # Incremental deduplication is handled by deleting the session post-processing.
        yield from self._picker_list_items(session_id, page_size, since_item_id=None)

    def download_image_bytes(self, base_url: str, width: int = 2048) -> bytes:
        """
        Download high-resolution image bytes from a Google Photos baseUrl.

        Uses the =s{width} suffix (s2048 = 2048px wide, high quality).
        Google Drive is NEVER accessed.

        Args:
            base_url: The Google Photos media item baseUrl.
            width: Requested image width in pixels (default 2048).

        Returns:
            Raw image bytes.
        """
        download_url = f"{base_url}=s{width}"
        logger.info("[GooglePhotos] Downloading image at s%d: %s...", width, base_url[:80])

        # Try downloading with Picker auth header, Library auth header, or direct request
        for headers_fn in (self._picker_headers, self._library_headers, lambda: {}):
            try:
                headers = headers_fn()
                resp = requests.get(download_url, headers=headers, timeout=60)
                if resp.status_code == 200:
                    return resp.content
            except Exception as exc:
                logger.debug("[GooglePhotos] Image download attempt failed: %s", exc)

        resp = requests.get(download_url, timeout=60)
        resp.raise_for_status()
        return resp.content

    def get_item_metadata(self, media_item_id: str) -> dict:
        """
        Fetch metadata for a single media item.
        Tries Library API first, then Picker API.
        """
        # Try Library API
        try:
            resp = requests.get(
                f"{_LIBRARY_BASE}/mediaItems/{media_item_id}",
                headers=self._library_headers(),
                timeout=15,
            )
            if resp.ok:
                return resp.json()
        except Exception:
            pass

        # Try Picker API
        try:
            memory = self._load_memory()
            session_id = memory.get("google_photos", {}).get("picker_session", {}).get("session_id")
            if session_id:
                resp = requests.get(
                    f"{_PICKER_BASE}/mediaItems/{media_item_id}",
                    headers=self._picker_headers(),
                    params={"sessionId": session_id},
                    timeout=15,
                )
                if resp.ok:
                    return resp.json()
        except Exception:
            pass

        logger.warning("[GooglePhotos] Could not fetch metadata for item %s", media_item_id)
        return {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalise_item(item: dict) -> dict:
    """Convert a raw API media item into the standardised CONTINUUM dict."""
    return {
        "id": item.get("id", ""),
        "name": item.get("filename", "photo.jpg"),
        "baseUrl": item.get("baseUrl", ""),
        "mediaMetadata": {
            "creationTime": item.get("mediaMetadata", {}).get("creationTime", ""),
            "photo": item.get("mediaMetadata", {}).get("photo", {}),
        },
        "mimeType": item.get("mimeType", "image/jpeg"),
    }
