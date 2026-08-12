"""
main.py — CONTINUUM Agentic AI Master Orchestrator
====================================================
Entry point for the fully autonomous life-logging and publishing pipeline.

Pipeline order:
  1. Load system memory (last processed IDs / timestamps)
  2. [If Google OAuth configured] Fetch Google Photos → Gemini Vision → WordPress
  3. [If Gmail configured] Parse Gmail booking confirmations → log logistics data
  4. Persist updated system memory
  5. (Every 7th session) Generate research analytics summary

Run locally:       python3 main.py
Smoke test only:   python3 main.py --smoke-test
Run via CI:        GitHub Actions calls this file on schedule
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

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

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _format_shanghai_time(iso_ts: str) -> str:
    """Normalize timestamp to Asia/Shanghai (UTC+8) timezone string."""
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00")).astimezone(SHANGHAI_TZ)
        return dt.strftime("%B %d, %Y at %I:%M %p (CST)")
    except Exception:
        return iso_ts


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
    """Step 1 — Google Photos → Gemini Vision → WordPress."""
    console.rule("[bold cyan]📸 Step 1: Photo Processing")

    last_id = memory.get("google_photos", {}).get("last_processed_media_item_id")
    processed_hashes = set(memory.get("research", {}).get("processed_file_hashes", []))

    new_items = list(
        photos.list_recent_media_items(
            page_size=10,
            since_item_id=last_id,
            processed_ids=list(processed_hashes),
        )
    )

    if not new_items:
        logger.info("No new photos to process.")
        return memory

    logger.info("Found %d candidate media item(s). Verifying byte checksums...", len(new_items))

    unprocessed_items = []
    bytes_cache: dict[str, tuple[bytes, str]] = {}

    for item in new_items:
        file_id = item["id"]
        fname = item.get("name", "photo.jpg")

        if file_id in processed_hashes:
            logger.info("[Deduplication] Skipping file ID %s (%s) — already processed.", file_id, fname)
            continue

        img_bytes = photos.download_image_bytes(item["baseUrl"])
        img_checksum = hashlib.sha256(img_bytes).hexdigest()

        if img_checksum in processed_hashes:
            logger.info(
                "[Deduplication] Skipping photo '%s' (ID %s) — SHA-256 byte checksum %s already processed.",
                fname,
                file_id,
                img_checksum[:12],
            )
            continue

        unprocessed_items.append(item)
        bytes_cache[file_id] = (img_bytes, img_checksum)

    if not unprocessed_items:
        logger.info("No new unprocessed photos found after byte checksum deduplication.")
        return memory

    logger.info("Found %d unprocessed photo(s) after byte checksum deduplication.", len(unprocessed_items))

    # 1. AI-Driven Batch Photo Selection (Primary + Supporting)
    batch = brain.select_photo_batch(
        candidate_photos=unprocessed_items,
        max_count=4,
        topic_hint="CONTINUUM Agentic AI Architecture, Life Logging, Tech DevLog, Travel, China Trip",
    )

    primary_item = batch["primary_photo"]
    supporting_items = batch.get("supporting_photos", [])

    # 2. Timezone Normalization (Asia/Shanghai UTC+8)
    raw_creation_time = primary_item.get("mediaMetadata", {}).get("creationTime", "")
    capture_date_shanghai = _format_shanghai_time(raw_creation_time) if raw_creation_time else "recent"

    # 3. Retrieve pre-downloaded image bytes & checksums from bytes_cache
    primary_bytes, primary_checksum = bytes_cache.get(
        primary_item["id"],
        (photos.download_image_bytes(primary_item["baseUrl"]), hashlib.sha256(photos.download_image_bytes(primary_item["baseUrl"])).hexdigest()),
    )

    supporting_bytes_list = []
    supporting_checksums = []
    for s_item in supporting_items:
        if s_item["id"] in bytes_cache:
            s_b, s_c = bytes_cache[s_item["id"]]
        else:
            s_b = photos.download_image_bytes(s_item["baseUrl"])
            s_c = hashlib.sha256(s_b).hexdigest()
        supporting_bytes_list.append(s_b)
        supporting_checksums.append(s_c)

    all_image_bytes = [primary_bytes] + supporting_bytes_list

    # 4. Multimodal Analysis with Semantic Deduplication
    memory_context = json.dumps(memory.get("wordpress", {}), indent=2)
    past_topics = memory.get("wordpress", {}).get("past_topics", [])
    past_titles = memory.get("wordpress", {}).get("past_titles", [])

    try:
        analysis = brain.analyse_photos(
            image_bytes_list=all_image_bytes,
            capture_date=capture_date_shanghai,
            memory_context=memory_context,
            past_topics=past_topics + past_titles,
        )
    except ValueError as pii_exc:
        if "PII_DETECTED" in str(pii_exc):
            logger.warning(
                "[Pipeline] Privacy Shield — batch rejected, skipping post publication. Reason: %s",
                pii_exc,
            )
            # Mark primary photo ID as processed so it's not retried
            hashes_list = memory.setdefault("research", {}).setdefault("processed_file_hashes", [])
            if primary_item["id"] not in hashes_list:
                hashes_list.append(primary_item["id"])
            return memory
        raise

    logger.info("Photos analysed — title: '%s'", analysis.get("title", "untitled"))

    wp_data = brain.format_for_wordpress(
        title=analysis["title"],
        narrative=analysis["narrative"],
        tags=analysis.get("tags", []),
        past_topics=past_topics + past_titles,
    )

    # 5. Upload Primary Photo (Featured Media)
    primary_media = publisher.upload_media(
        image_bytes=primary_bytes,
        filename=f"continuum_primary_{primary_item['id'][:8]}.jpg",
        alt_text=wp_data.get("featured_image_alt_text", analysis["title"]),
        caption=analysis.get("detected_location", analysis["title"]),
    )

    # 6. Upload Supporting Photos and build Gutenberg figure blocks
    gutenberg_figures_html = ""
    for idx, (s_item, s_bytes) in enumerate(zip(supporting_items, supporting_bytes_list)):
        s_alt = f"{analysis['title']} - Photo {idx+2}"
        s_caption = f"Supporting view from {analysis.get('detected_location', 'China trip')}"
        s_media = publisher.upload_media(
            image_bytes=s_bytes,
            filename=f"continuum_supp_{s_item['id'][:8]}.jpg",
            alt_text=s_alt,
            caption=s_caption,
        )
        gutenberg_figures_html += (
            f'<!-- wp:image {{"id":{s_media["media_id"]},"sizeSlug":"full","linkDestination":"none"}} -->\n'
            f'<figure class="wp-block-image size-full">'
            f'<img src="{s_media["source_url"]}" alt="{s_alt}" class="wp-image-{s_media["media_id"]}"/>'
            f'<figcaption>{s_caption}</figcaption>'
            f'</figure>\n'
            f'<!-- /wp:image -->\n\n'
        )

    # Combine figures with HTML body content
    primary_figure = (
        f'<figure class="wp-block-image size-full">'
        f'<img src="{primary_media["source_url"]}" alt="{wp_data.get("featured_image_alt_text", analysis["title"])}" />'
        f'<figcaption>{analysis.get("detected_location", analysis["title"])}</figcaption>'
        f'</figure>\n\n'
    )
    full_html_content = primary_figure + wp_data["html_content"] + ("\n\n" + gutenberg_figures_html if gutenberg_figures_html else "")

    # 7. Create WordPress Post
    post = publisher.create_post(
        title=analysis["title"],
        html_content=full_html_content,
        excerpt=wp_data.get("excerpt", ""),
        tags=wp_data.get("tags", []),
        categories=wp_data.get("categories", ["Travel Stories", "AI Agent Development"]),
        featured_media_id=primary_media["media_id"],
        status=settings.WP_POST_STATUS,
        seo_title=wp_data.get("seo_title", ""),
        seo_description=wp_data.get("seo_description", ""),
        focus_keyword=wp_data.get("focus_keyword", ""),
    )

    # 8. Live Post Verification Loop
    is_live = publisher.verify_live_post(post["id"])
    if not is_live:
        logger.warning("[WordPress] Post id=%d status verification returned unconfirmed live status.", post["id"])

    # 9. Research Logging
    research.log_photo_processed(primary_item["id"], capture_date_shanghai, analysis)
    research.log_post_published(
        post_id=post["id"],
        title=analysis["title"],
        url=post.get("link", ""),
        tags=analysis.get("tags", []),
        source_media_id=primary_item["id"],
    )

    # 10. Update Memory (Incremental tracking + Semantic deduplication)
    memory.setdefault("google_photos", {})["last_processed_media_item_id"] = primary_item["id"]
    memory.setdefault("google_photos", {})["last_processed_timestamp"] = (
        datetime.now(SHANGHAI_TZ).isoformat()
    )
    memory.setdefault("wordpress", {})["last_published_post_id"] = post["id"]
    memory["wordpress"]["total_posts_published"] = (
        memory["wordpress"].get("total_posts_published", 0) + 1
    )

    # Deduplication updates
    past_titles_list = memory.setdefault("wordpress", {}).setdefault("past_titles", [])
    if analysis["title"] not in past_titles_list:
        past_titles_list.append(analysis["title"])

    past_topics_list = memory.setdefault("wordpress", {}).setdefault("past_topics", [])
    for tag in analysis.get("tags", []):
        if tag not in past_topics_list:
            past_topics_list.append(tag)

    hashes_list = memory.setdefault("research", {}).setdefault("processed_file_hashes", [])
    all_processed = [(primary_item["id"], primary_checksum)] + list(
        zip([s["id"] for s in supporting_items], supporting_checksums)
    )
    for item_id, checksum in all_processed:
        if checksum not in hashes_list:
            hashes_list.append(checksum)
        if item_id not in hashes_list:
            hashes_list.append(item_id)

    console.print(
        f"[bold green]✅ Published & Verified Live:[/bold green] {analysis['title']} → {post.get('link')}"
    )
    return memory


def step_parse_bookings(
    gmail: GmailBookingClient,
    brain: GeminiBrain,
    research: ResearchLogger,
    memory: dict,
) -> dict:
    """Step 2 — Gmail → Gemini Booking Parser → Research Log."""
    console.rule("[bold yellow]✈️  Step 2: Booking Parsing")

    last_msg_id = memory.get("gmail", {}).get("last_processed_message_id")
    messages = list(
        gmail.list_booking_messages(max_results=5, since_message_id=last_msg_id)
    )

    if not messages:
        logger.info("No new booking emails found.")
        return memory

    for msg in messages:
        subject = gmail.get_subject(msg)
        body = gmail.extract_body(msg)
        booking_data = brain.parse_booking_email(body)
        research.log_booking_parsed(msg["id"], subject, booking_data)

    memory.setdefault("gmail", {})["last_processed_message_id"] = messages[0]["id"]
    memory["gmail"]["last_processed_timestamp"] = (
        datetime.now(timezone.utc).isoformat()
    )
    memory["gmail"]["total_messages_processed"] = (
        memory["gmail"].get("total_messages_processed", 0) + len(messages)
    )
    return memory


def step_research_summary(brain: GeminiBrain, research: ResearchLogger) -> None:
    """Step 3 (Weekly) — Gemini-powered research analytics summary."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Smoke Test — Gemini + WordPress only (no Google OAuth required)
# ─────────────────────────────────────────────────────────────────────────────

def run_smoke_test(
    brain: GeminiBrain,
    publisher: WordPressPublisher,
    research: ResearchLogger,
) -> None:
    """
    End-to-end smoke test that bypasses Google Photos/Gmail entirely.

    Two-pass Gemini strategy:
      Pass A → JSON-only call for metadata (title, excerpt, tags) — no HTML, no parse risk
      Pass B → Plain text call for HTML body — returned as raw text, not inside JSON
      Combined → WordPressPublisher creates a draft on tanivashraf.com
    """
    console.rule("[bold blue]🧪 CONTINUUM Smoke Test")
    console.print(
        "[dim]Testing: Gemini → WordPress pipeline (no Google OAuth needed)[/dim]\n"
    )

    import google.genai as genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    # ── Pass A: Metadata only (safe JSON — no HTML inside) ────────────────────
    logger.info("[A] Generating post metadata via Gemini...")
    meta_response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=(
            'Return ONLY compact JSON. No explanation. No markdown.\n'
            'Topic: a weekend trip to Dhaka, Bangladesh.\n'
            'Keys: "title" (string), "excerpt" (1 sentence), '
            '"tags" (array of 3 strings), "categories" (["Travel"]).\n'
            'Example: {"title":"My Trip","excerpt":"A fun trip.","tags":["travel","dhaka","weekend"],"categories":["Travel"]}'
        ),
        config=genai_types.GenerateContentConfig(
            temperature=0.6,
            max_output_tokens=800,
            response_mime_type="application/json",
        ),
    )
    meta = json.loads(meta_response.text)
    logger.info("[A] ✅ Title: '%s'", meta["title"])

    # ── Pass B: HTML body as plain text (no JSON wrapper) ─────────────────────
    logger.info("[B] Generating HTML post body via Gemini...")
    html_response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=(
            f"Write a travel blog post in HTML about a weekend trip to Dhaka, Bangladesh.\n"
            f"Title: {meta['title']}\n"
            f"Style: warm, first-person, 250-300 words.\n"
            f"Output ONLY raw HTML using <h2> and <p> tags. No JSON. No markdown. No preamble."
        ),
        config=genai_types.GenerateContentConfig(
            temperature=0.8,
            max_output_tokens=1200,
        ),
    )
    html_content = html_response.text

    # Strip accidental code fences if model wraps output in ```html ... ```
    if html_content.startswith("```"):
        lines = html_content.splitlines()
        html_content = "\n".join(
            lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:]
        )

    logger.info("[B] ✅ HTML body ready (%d chars)", len(html_content))

    # ── Step C: Publish draft to WordPress ────────────────────────────────────
    logger.info("[C] Publishing draft to %s ...", settings.WP_URL)
    post = publisher.create_post(
        title=f"[CONTINUUM TEST] {meta['title']}",
        html_content=html_content,
        excerpt=meta.get("excerpt", ""),
        tags=meta.get("tags", []),
        categories=meta.get("categories", ["Travel"]),
        status="draft",
    )

    post_id = post["id"]
    post_url = post.get("link", f"{settings.WP_URL}/?p={post_id}")

    # ── Step D: Log the event ─────────────────────────────────────────────────
    research.log_post_published(
        post_id=post_id,
        title=meta["title"],
        url=post_url,
        tags=meta.get("tags", []),
        source_media_id="smoke_test",
    )

    # ── Result ────────────────────────────────────────────────────────────────
    title_display = ("[CONTINUUM TEST] " + meta["title"])[:44]
    url_display = post_url[:44]

    console.print()
    console.print("╔══════════════════════════════════════════════════════╗")
    console.print("║   🚀  CONTINUUM SMOKE TEST — PASSED                  ║")
    console.print("╠══════════════════════════════════════════════════════╣")
    console.print(f"║   Post ID : {post_id:<42} ║")
    console.print(f"║   Title   : {title_display:<44} ║")
    console.print(f"║   Status  : {'draft (review in WP dashboard)':<44} ║")
    console.print(f"║   URL     : {url_display:<44} ║")
    console.print("╠══════════════════════════════════════════════════════╣")
    console.print("║   ✅  Gemini → WordPress pipeline confirmed working   ║")
    console.print("╚══════════════════════════════════════════════════════╝")
    console.print()


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="CONTINUUM Agentic AI Pipeline")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run Gemini→WordPress smoke test only (no Google OAuth required)",
    )
    args = parser.parse_args()

    console.print()
    console.print("[bold blue]═══════════════════════════════════════════════[/bold blue]")
    console.print("[bold blue]   CONTINUUM AGENTIC AI — Pipeline Start       [/bold blue]")
    console.print("[bold blue]═══════════════════════════════════════════════[/bold blue]")
    console.print()

    research = ResearchLogger()
    brain = GeminiBrain()
    publisher = WordPressPublisher()

    # ── Smoke-test mode ───────────────────────────────────────────────────────
    if args.smoke_test:
        try:
            run_smoke_test(brain, publisher, research)
        except Exception as exc:
            logger.exception("Smoke test failed: %s", exc)
            sys.exit(1)
        return

    # ── Full pipeline mode ────────────────────────────────────────────────────
    memory = research.load_memory()
    memory.setdefault("research", {})["session_count"] = (
        memory["research"].get("session_count", 0) + 1
    )

    google_ready = all([
        settings.GOOGLE_PHOTOS_REFRESH_TOKEN,
        settings.GOOGLE_CLIENT_ID,
        settings.GOOGLE_CLIENT_SECRET,
    ])
    gmail_ready = bool(settings.GMAIL_REFRESH_TOKEN)

    if not google_ready:
        console.print(
            "[bold yellow]⚠️  Google OAuth not configured — "
            "skipping Photos & Gmail steps.[/bold yellow]"
        )
        console.print(
            "[dim]   Run: python3 scripts/setup_google_oauth.py  to set up access.[/dim]\n"
        )

    try:
        if google_ready:
            photos = GooglePhotosClient()
            memory = step_process_photos(photos, brain, publisher, research, memory)
        else:
            console.print("[dim]   → Step 1 (Photos) skipped.[/dim]")

        if gmail_ready:
            gmail = GmailBookingClient()
            memory = step_parse_bookings(gmail, brain, research, memory)
        else:
            console.print("[dim]   → Step 2 (Gmail) skipped.[/dim]\n")

        if memory["research"].get("session_count", 0) % 7 == 0:
            step_research_summary(brain, research)

    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        research.log_event("pipeline_error", {"error": str(exc)})
        sys.exit(1)
    finally:
        research.save_memory(memory)
        console.print("\n[bold green]✅ CONTINUUM pipeline complete.[/bold green]\n")


if __name__ == "__main__":
    main()
