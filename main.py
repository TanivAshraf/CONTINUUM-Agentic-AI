"""
main.py — CONTINUUM Agentic AI Master Orchestrator
====================================================
Entry point for the fully autonomous life-logging and publishing pipeline.

Pipeline order:
  1. Load system memory (last processed IDs / timestamps)
  2. Fetch new Google Photos media items → analyse with Gemini Vision
  3. Parse new Gmail booking confirmations → extract logistics data
  4. Format analysed content → publish to WordPress
  5. Persist updated system memory
  6. (Weekly) Generate research analytics summary

Run locally:  python main.py
Run via CI:   GitHub Actions calls this file on schedule (see .github/workflows/)
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from rich.console import Console
from rich.logging import RichHandler

# ── Logging Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger("continuum")
console = Console()

# ── CONTINUUM Modules ─────────────────────────────────────────────────────────
from config.settings import settings
from src import (
    GooglePhotosClient,
    GmailBookingClient,
    GeminiBrain,
    WordPressPublisher,
    ResearchLogger,
)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Steps
# ─────────────────────────────────────────────────────────────────────────────

def step_process_photos(
    photos: GooglePhotosClient,
    brain: GeminiBrain,
    publisher: WordPressPublisher,
    research: ResearchLogger,
    memory: dict,
) -> dict:
    """
    Step 1 — Google Photos → Gemini Vision → WordPress.

    Fetches new photos since the last run, analyses them as a batch,
    formats the output, and publishes a draft post.

    Returns updated memory dict.
    """
    console.rule("[bold cyan]📸 Step 1: Photo Processing")

    last_id = memory.get("google_photos", {}).get("last_processed_media_item_id")
    new_items = list(
        photos.list_recent_media_items(page_size=10, since_item_id=last_id)
    )

    if not new_items:
        logger.info("No new photos to process.")
        return memory

    logger.info("Found %d new media item(s) to process.", len(new_items))

    # Group items by date and process the most recent batch
    item = new_items[0]  # Most recent item
    capture_date = item.get("mediaMetadata", {}).get("creationTime", "unknown date")
    image_bytes = photos.download_image_bytes(item["baseUrl"])

    # Analyse with Gemini
    memory_context = json.dumps(memory.get("wordpress", {}), indent=2)
    analysis = brain.analyse_photos(
        image_bytes_list=[image_bytes],
        capture_date=capture_date,
        memory_context=memory_context,
    )
    logger.info("Photo analysed — title: '%s'", analysis.get("title", "untitled"))

    # Format for WordPress
    wp_data = brain.format_for_wordpress(
        title=analysis["title"],
        narrative=analysis["narrative"],
        tags=analysis.get("tags", []),
    )

    # Upload featured image
    media_id = publisher.upload_featured_image(
        image_bytes=image_bytes,
        filename=f"continuum_{item['id'][:8]}.jpg",
        alt_text=wp_data.get("featured_image_alt_text", ""),
    )

    # Publish post
    post = publisher.create_post(
        title=analysis["title"],
        html_content=wp_data["html_content"],
        excerpt=wp_data.get("excerpt", ""),
        tags=wp_data.get("tags", []),
        categories=wp_data.get("categories", ["Travel", "Life Log"]),
        featured_media_id=media_id,
    )

    # Log event
    research.log_photo_processed(item["id"], capture_date, analysis)
    research.log_post_published(
        post_id=post["id"],
        title=analysis["title"],
        url=post.get("link", ""),
        tags=analysis.get("tags", []),
        source_media_id=item["id"],
    )

    # Update memory
    memory.setdefault("google_photos", {})["last_processed_media_item_id"] = item["id"]
    memory.setdefault("google_photos", {})["last_processed_timestamp"] = datetime.now(
        timezone.utc
    ).isoformat()
    memory.setdefault("wordpress", {})["last_published_post_id"] = post["id"]
    memory["wordpress"]["total_posts_published"] = (
        memory["wordpress"].get("total_posts_published", 0) + 1
    )

    console.print(
        f"[bold green]✅ Published:[/bold green] {analysis['title']} → {post.get('link')}"
    )
    return memory


def step_parse_bookings(
    gmail: GmailBookingClient,
    brain: GeminiBrain,
    research: ResearchLogger,
    memory: dict,
) -> dict:
    """
    Step 2 — Gmail → Gemini Booking Parser → Research Log.

    Fetches unread booking-related emails, extracts structured logistics
    data, and logs it for the research record.

    Returns updated memory dict.
    """
    console.rule("[bold yellow]✈️  Step 2: Booking Parsing")

    last_msg_id = memory.get("gmail", {}).get("last_processed_message_id")
    messages = list(
        gmail.list_booking_messages(max_results=5, since_message_id=last_msg_id)
    )

    if not messages:
        logger.info("No new booking emails found.")
        return memory

    logger.info("Found %d new booking email(s).", len(messages))

    for msg in messages:
        subject = gmail.get_subject(msg)
        body = gmail.extract_body(msg)
        booking_data = brain.parse_booking_email(body)
        research.log_booking_parsed(msg["id"], subject, booking_data)
        logger.info(
            "Booking parsed — type: %s | provider: %s",
            booking_data.get("booking_type", "?"),
            booking_data.get("provider", "?"),
        )

    # Update memory with latest processed message ID
    memory.setdefault("gmail", {})["last_processed_message_id"] = messages[0]["id"]
    memory["gmail"]["last_processed_timestamp"] = datetime.now(
        timezone.utc
    ).isoformat()
    memory["gmail"]["total_messages_processed"] = (
        memory["gmail"].get("total_messages_processed", 0) + len(messages)
    )
    return memory


def step_research_summary(brain: GeminiBrain, research: ResearchLogger) -> None:
    """
    Step 3 (Weekly) — Generate a Gemini-powered research analytics summary.

    Loads the last 7 days of event logs, passes them to Gemini for analysis,
    and writes the summary to a dedicated log entry.
    """
    console.rule("[bold magenta]📊 Step 3: Research Summary")

    events = research.load_recent_metrics(days=7)
    if not events:
        logger.info("No events to summarise.")
        return

    today = datetime.now(timezone.utc)
    seven_days_ago = today.replace(day=max(1, today.day - 7))

    summary = brain.generate_research_summary(
        metrics_json=json.dumps(events, indent=2),
        start_date=seven_days_ago.date().isoformat(),
        end_date=today.date().isoformat(),
    )
    research.log_event("research_summary_generated", {"summary": summary})
    console.print(
        f"[bold magenta]📊 Research Summary:[/bold magenta] "
        f"{summary.get('summary_text', '(see log)')}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    console.print(
        "\n[bold blue]═══════════════════════════════════════════[/bold blue]"
    )
    console.print(
        "[bold blue]   CONTINUUM AGENTIC AI — Pipeline Start   [/bold blue]"
    )
    console.print(
        "[bold blue]═══════════════════════════════════════════[/bold blue]\n"
    )

    # ── Initialise clients ────────────────────────────────────────────────────
    research = ResearchLogger()
    memory = research.load_memory()
    memory.setdefault("research", {})["session_count"] = (
        memory["research"].get("session_count", 0) + 1
    )

    photos = GooglePhotosClient()
    gmail = GmailBookingClient()
    brain = GeminiBrain()
    publisher = WordPressPublisher()

    # ── Run pipeline ──────────────────────────────────────────────────────────
    try:
        memory = step_process_photos(photos, brain, publisher, research, memory)
        memory = step_parse_bookings(gmail, brain, research, memory)

        # Run research summary on every 7th session
        if memory["research"].get("session_count", 0) % 7 == 0:
            step_research_summary(brain, research)

    except Exception as exc:
        logger.exception("Pipeline failed with an unhandled error: %s", exc)
        research.log_event("pipeline_error", {"error": str(exc)})
        sys.exit(1)

    finally:
        research.save_memory(memory)
        console.print(
            "\n[bold green]✅ CONTINUUM pipeline complete.[/bold green]\n"
        )


if __name__ == "__main__":
    main()
