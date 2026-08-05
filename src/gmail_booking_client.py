"""
src/gmail_booking_client.py
============================
Gmail / Booking-confirmation parser for CONTINUUM Agentic AI.

Uses the Gmail API to fetch unread emails matching booking-related labels or
keywords, then passes the raw email body to the Gemini Brain for structured
extraction of travel/logistics information.
"""

from __future__ import annotations

import base64
import logging
from typing import Generator

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from config.settings import settings

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Gmail search queries for booking-related emails
_BOOKING_QUERY = (
    "subject:(booking OR reservation OR confirmation OR itinerary OR e-ticket "
    "OR 'flight details' OR 'hotel confirmation' OR 'order confirmation') "
    "is:unread"
)


class GmailBookingClient:
    """Gmail API client that extracts booking / logistics emails."""

    def __init__(self) -> None:
        self._service = None

    # ── Authentication ────────────────────────────────────────────────────────

    def _get_service(self):
        """Build (and cache) an authorised Gmail API service object."""
        if self._service is not None:
            return self._service

        creds = Credentials(
            token=None,
            refresh_token=settings.GMAIL_REFRESH_TOKEN,
            token_uri=_TOKEN_URL,
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        )
        creds.refresh(Request())
        self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return self._service

    # ── Message Fetching ──────────────────────────────────────────────────────

    def list_booking_messages(
        self,
        max_results: int = 10,
        since_message_id: str | None = None,
    ) -> Generator[dict, None, None]:
        """
        Yield raw Gmail message dicts that look like booking confirmations.

        Args:
            max_results: Maximum number of messages to retrieve.
            since_message_id: Skip messages older than this ID (not supported
                              natively by Gmail API — used as a stop signal).

        Yields:
            Full message dicts including payload/body.
        """
        service = self._get_service()
        result = (
            service.users()
            .messages()
            .list(userId="me", q=_BOOKING_QUERY, maxResults=max_results)
            .execute()
        )

        messages = result.get("messages", [])
        if not messages:
            logger.info("No booking-related emails found.")
            return

        for msg_stub in messages:
            msg_id = msg_stub["id"]
            if since_message_id and msg_id == since_message_id:
                logger.info("Reached last processed message %s — stopping.", msg_id)
                return

            full_msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )
            yield full_msg

    # ── Payload Decoding ──────────────────────────────────────────────────────

    @staticmethod
    def extract_body(message: dict) -> str:
        """
        Extract the plain-text (or HTML-stripped) body from a Gmail message.

        Args:
            message: A full Gmail message dict.

        Returns:
            Decoded body string (up to 32 KB).
        """
        payload = message.get("payload", {})

        def _decode_part(part: dict) -> str | None:
            data = part.get("body", {}).get("data")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            return None

        # Try single-part message first
        body = _decode_part(payload)
        if body:
            return body[:32_768]

        # Walk multi-part; prefer text/plain
        for part in payload.get("parts", []):
            mime_type = part.get("mimeType", "")
            if "text/plain" in mime_type:
                text = _decode_part(part)
                if text:
                    return text[:32_768]

        # Fall back to any part
        for part in payload.get("parts", []):
            text = _decode_part(part)
            if text:
                return text[:32_768]

        return ""

    @staticmethod
    def get_subject(message: dict) -> str:
        """Extract the Subject header from a Gmail message."""
        headers = message.get("payload", {}).get("headers", [])
        for header in headers:
            if header.get("name", "").lower() == "subject":
                return header.get("value", "")
        return "(no subject)"
