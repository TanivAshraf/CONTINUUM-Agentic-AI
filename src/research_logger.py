"""
src/research_logger.py
=======================
Metrics logger and persistent state manager for CONTINUUM Agentic AI.

Responsibilities:
  - Append structured publishing metrics to daily JSONL log files.
  - Read and write system_memory.json for incremental state tracking.
  - Provide aggregated metrics for the Gemini research summary.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import settings

logger = logging.getLogger(__name__)

_MEMORY_PATH = Path(settings.MEMORY_FILE)
_LOGS_DIR = Path(settings.RESEARCH_LOGS_DIR)


class ResearchLogger:
    """
    Manages research metrics logging and persistent system memory.

    All log entries are appended to a daily JSONL file:
        research_logs/YYYY-MM-DD.jsonl

    System memory is stored in:
        data/system_memory.json
    """

    def __init__(self) -> None:
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        gitkeep_file = _LOGS_DIR / ".gitkeep"
        if not gitkeep_file.exists():
            gitkeep_file.touch()
        _MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    # ── System Memory ─────────────────────────────────────────────────────────

    def load_memory(self) -> dict[str, Any]:
        """Load system memory from disk. Returns empty defaults if file missing."""
        if not _MEMORY_PATH.exists():
            logger.warning(
                "system_memory.json not found — initialising empty memory."
            )
            return {
                "google_photos": {"last_processed_media_item_id": None},
                "gmail": {"last_processed_message_id": None},
                "wordpress": {
                    "last_published_post_id": None,
                    "total_posts_published": 0,
                    "past_titles": [],
                    "past_topics": [],
                },
                "research": {
                    "session_count": 0,
                    "processed_file_hashes": [],
                },
            }
        with _MEMORY_PATH.open("r", encoding="utf-8") as fh:
            mem = json.load(fh)

        mem.setdefault("wordpress", {}).setdefault("past_titles", [])
        mem.setdefault("wordpress", {}).setdefault("past_topics", [])
        mem.setdefault("research", {}).setdefault("processed_file_hashes", [])
        return mem

    def save_memory(self, memory: dict[str, Any]) -> None:
        """Persist updated system memory to disk."""
        memory.setdefault("_meta", {})["last_updated"] = datetime.now(
            timezone.utc
        ).isoformat()
        with _MEMORY_PATH.open("w", encoding="utf-8") as fh:
            json.dump(memory, fh, indent=2, ensure_ascii=False)
        logger.debug("System memory saved to %s", _MEMORY_PATH)

    # ── Metrics Logging ───────────────────────────────────────────────────────

    def log_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """
        Append a structured event to today's JSONL research log.

        Args:
            event_type: A short descriptor e.g. 'post_published', 'photo_processed'.
            payload: Arbitrary dict of event data.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = _LOGS_DIR / f"{today}.jsonl"

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            **payload,
        }
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

        logger.info("[ResearchLogger] %s: %s", event_type, payload)

    def log_post_published(
        self,
        post_id: int,
        title: str,
        url: str,
        tags: list[str],
        source_media_id: str | None = None,
    ) -> None:
        """Convenience method to log a WordPress publishing event."""
        self.log_event(
            "post_published",
            {
                "post_id": post_id,
                "title": title,
                "url": url,
                "tags": tags,
                "source_media_id": source_media_id,
            },
        )

    def log_photo_processed(
        self, media_item_id: str, capture_date: str, analysis_result: dict
    ) -> None:
        """Convenience method to log a photo-processing event."""
        self.log_event(
            "photo_processed",
            {
                "media_item_id": media_item_id,
                "capture_date": capture_date,
                "generated_title": analysis_result.get("title"),
                "detected_location": analysis_result.get("detected_location"),
                "tags": analysis_result.get("tags", []),
            },
        )

    def log_booking_parsed(
        self, message_id: str, subject: str, booking_data: dict
    ) -> None:
        """Convenience method to log a booking-parsing event."""
        self.log_event(
            "booking_parsed",
            {
                "message_id": message_id,
                "subject": subject,
                "booking_found": booking_data.get("booking_found", True),
                "booking_type": booking_data.get("booking_type"),
                "provider": booking_data.get("provider"),
                "dates": booking_data.get("dates"),
            },
        )

    # ── Metrics Aggregation ───────────────────────────────────────────────────

    def load_recent_metrics(self, days: int = 7) -> list[dict[str, Any]]:
        """
        Load and aggregate event logs from the last N days.

        Args:
            days: Number of days of history to include.

        Returns:
            List of all event dicts across the date range.
        """
        from datetime import timedelta

        events: list[dict] = []
        today = datetime.now(timezone.utc).date()

        for offset in range(days):
            date = today - timedelta(days=offset)
            log_file = _LOGS_DIR / f"{date.isoformat()}.jsonl"
            if not log_file.exists():
                continue
            with log_file.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            logger.warning("Skipping malformed log line in %s", log_file)

        logger.info("Loaded %d events from the last %d day(s)", len(events), days)
        return events
