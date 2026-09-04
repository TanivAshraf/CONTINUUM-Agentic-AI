"""
scripts/academic_data_exporter.py
====================================
CONTINUUM Academic Dataset Exporter & NotebookLM Corpus Generator.

Outputs:
  1. research_logs/continuum_master_dataset.csv  — quantitative dataset
  2. research_logs/ALL_PUBLISHED_ARTICLES_CORPUS.md — full text corpus for NotebookLM
"""

from __future__ import annotations

import csv
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
WP_URL = os.getenv("WP_URL", "").rstrip("/")
WP_USER = os.getenv("WP_USER", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")

if not all([WP_URL, WP_USER, WP_APP_PASSWORD]):
    print("❌ Missing WP credentials in .env. Aborting.")
    sys.exit(1)

API_BASE = f"{WP_URL}/wp-json/wp/v2"
SESSION = requests.Session()
SESSION.auth = HTTPBasicAuth(WP_USER, WP_APP_PASSWORD)
SESSION.headers.update({"User-Agent": "CONTINUUM-AcademicExporter/1.0"})

BASE_DIR = Path(__file__).resolve().parent.parent
MEMORY_PATH = BASE_DIR / "data" / "system_memory.json"
RESEARCH_LOGS_DIR = BASE_DIR / "research_logs"
CSV_OUT = RESEARCH_LOGS_DIR / "continuum_master_dataset.csv"
CORPUS_OUT = RESEARCH_LOGS_DIR / "ALL_PUBLISHED_ARTICLES_CORPUS.md"

RESEARCH_LOGS_DIR.mkdir(exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    """Remove HTML tags and decode HTML entities."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def html_to_markdown(text: str) -> str:
    """Lightweight HTML → Markdown conversion for corpus readability."""
    # Block-level elements
    text = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n# \1\n", text, flags=re.S)
    text = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n## \1\n", text, flags=re.S)
    text = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n### \1\n", text, flags=re.S)
    text = re.sub(r"<p[^>]*>(.*?)</p>", r"\n\1\n", text, flags=re.S)
    text = re.sub(r"<li[^>]*>(.*?)</li>", r"\n- \1", text, flags=re.S)
    text = re.sub(r"<ul[^>]*>|</ul>", "\n", text, flags=re.S)
    text = re.sub(r"<ol[^>]*>|</ol>", "\n", text, flags=re.S)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<figcaption[^>]*>(.*?)</figcaption>", r"\n*📷 \1*\n", text, flags=re.S)
    # Inline elements
    text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text, flags=re.S)
    text = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", text, flags=re.S)
    text = re.sub(r"<a[^>]+href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", r"[\2](\1)", text, flags=re.S)
    # Remove remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    # Normalise whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def estimate_word_count(html_text: str) -> int:
    plain = strip_html(html_text)
    return len(plain.split())


def fetch_all_posts() -> list[dict]:
    """Fetch all published posts from WordPress REST API (paginated)."""
    posts = []
    page = 1
    print("  Fetching posts from WordPress REST API...")
    while True:
        resp = SESSION.get(
            f"{API_BASE}/posts",
            params={
                "per_page": 100,
                "page": page,
                "status": "publish",
                "_fields": "id,title,link,date,excerpt,content,tags,categories,featured_media,yoast_head_json",
            },
            timeout=30,
        )
        if resp.status_code == 400:
            break
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        posts.extend(batch)
        total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
        print(f"    Page {page}/{total_pages} — fetched {len(batch)} posts (cumulative: {len(posts)})")
        if page >= total_pages:
            break
        page += 1
    return posts


def fetch_tag_names(tag_ids: list[int]) -> list[str]:
    """Resolve tag IDs to name strings."""
    if not tag_ids:
        return []
    names = []
    for tid in tag_ids:
        try:
            r = SESSION.get(f"{API_BASE}/tags/{tid}", timeout=10)
            if r.status_code == 200:
                names.append(r.json().get("name", str(tid)))
        except Exception:
            names.append(str(tid))
    return names


def fetch_category_names(cat_ids: list[int]) -> list[str]:
    """Resolve category IDs to name strings."""
    if not cat_ids:
        return []
    names = []
    for cid in cat_ids:
        try:
            r = SESSION.get(f"{API_BASE}/categories/{cid}", timeout=10)
            if r.status_code == 200:
                names.append(r.json().get("name", str(cid)))
        except Exception:
            names.append(str(cid))
    return names


def load_memory() -> dict:
    with open(MEMORY_PATH, encoding="utf-8") as f:
        return json.load(f)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n" + "="*65)
    print("  CONTINUUM Academic Dataset Exporter")
    print(f"  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("="*65 + "\n")

    # 1. Load system memory
    print("📂 Loading system_memory.json...")
    memory = load_memory()
    processed_hashes = memory.get("research", {}).get("processed_file_hashes", [])
    gmail_count = memory.get("gmail", {}).get("total_messages_processed", 0)
    memory_last_updated = memory.get("_meta", {}).get("last_updated", "unknown")
    session_count = memory.get("research", {}).get("session_count", 0)
    past_topics = memory.get("wordpress", {}).get("past_topics", [])
    print(f"  ✅ Memory loaded — {len(processed_hashes)} hashes, {gmail_count} Gmail messages, {session_count} sessions")

    # 2. Fetch all WordPress posts
    print("\n📡 Fetching all published WordPress posts...")
    posts = fetch_all_posts()
    total_posts = len(posts)
    print(f"  ✅ Fetched {total_posts} published post(s)\n")

    # 3. Build CSV dataset
    print("📊 Building quantitative CSV dataset...")
    csv_rows = []
    # Sort posts oldest → newest for chronological analysis
    posts_sorted = sorted(posts, key=lambda p: p.get("date", ""))

    # Pre-resolve tags/categories cache
    tag_cache: dict[int, str] = {}
    cat_cache: dict[int, str] = {}

    for post in posts_sorted:
        post_id = post["id"]
        title = strip_html(post.get("title", {}).get("rendered", ""))
        url = post.get("link", "")
        date_raw = post.get("date", "")
        content_html = post.get("content", {}).get("rendered", "")
        excerpt_html = post.get("excerpt", {}).get("rendered", "")
        word_count = estimate_word_count(content_html)

        # Resolve tags
        tag_ids = post.get("tags", [])
        resolved_tags = []
        for tid in tag_ids:
            if tid not in tag_cache:
                try:
                    r = SESSION.get(f"{API_BASE}/tags/{tid}", timeout=10)
                    tag_cache[tid] = r.json().get("name", str(tid)) if r.status_code == 200 else str(tid)
                except Exception:
                    tag_cache[tid] = str(tid)
            resolved_tags.append(tag_cache[tid])

        # Resolve categories
        cat_ids = post.get("categories", [])
        resolved_cats = []
        for cid in cat_ids:
            if cid not in cat_cache:
                try:
                    r = SESSION.get(f"{API_BASE}/categories/{cid}", timeout=10)
                    cat_cache[cid] = r.json().get("name", str(cid)) if r.status_code == 200 else str(cid)
                except Exception:
                    cat_cache[cid] = str(cid)
            resolved_cats.append(cat_cache[cid])

        # Yoast SEO title
        yoast = post.get("yoast_head_json") or {}
        seo_title = yoast.get("title", title)
        seo_title_length = len(seo_title)

        primary_topic = resolved_tags[0] if resolved_tags else "General"
        category = " | ".join(resolved_cats) if resolved_cats else "Uncategorized"

        csv_rows.append({
            "post_id": post_id,
            "post_title": title,
            "url": url,
            "publish_date": date_raw,
            "primary_topic": primary_topic,
            "all_tags": " | ".join(resolved_tags),
            "category": category,
            "word_count_estimate": word_count,
            "seo_title": seo_title,
            "seo_title_length": seo_title_length,
            "verification_status": "live",
        })

        print(f"    #{post_id} — {title[:60]} ({word_count} words)")

    # Write CSV
    fieldnames = [
        "post_id", "post_title", "url", "publish_date", "primary_topic",
        "all_tags", "category", "word_count_estimate",
        "seo_title", "seo_title_length", "verification_status",
    ]
    with open(CSV_OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    total_words = sum(r["word_count_estimate"] for r in csv_rows)
    print(f"\n  ✅ CSV saved → {CSV_OUT}")
    print(f"     {total_posts} posts | ~{total_words:,} total words | avg {total_words // max(total_posts, 1)} words/post")

    # 4. Build NotebookLM Markdown corpus
    print("\n📝 Generating NotebookLM corpus (ALL_PUBLISHED_ARTICLES_CORPUS.md)...")
    corpus_lines = [
        "# CONTINUUM Agentic AI — Complete Published Articles Corpus",
        "",
        f"> **Dataset generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"> **Total articles:** {total_posts}  ",
        f"> **Total estimated words:** {total_words:,}  ",
        f"> **System sessions:** {session_count}  ",
        f"> **Processed image hashes:** {len(processed_hashes)}  ",
        f"> **Gmail bookings parsed:** {gmail_count}  ",
        f"> **Memory last updated:** {memory_last_updated}  ",
        "",
        "---",
        "",
        "## Summary Index",
        "",
    ]

    for i, row in enumerate(csv_rows, 1):
        corpus_lines.append(
            f"{i}. [{row['post_title']}]({row['url']}) — *{row['primary_topic']}* ({row['word_count_estimate']} words)"
        )

    corpus_lines += ["", "---", "", "## Full Article Archive", ""]

    for i, post in enumerate(posts_sorted, 1):
        post_id = post["id"]
        title = strip_html(post.get("title", {}).get("rendered", "Untitled"))
        url = post.get("link", "")
        date_raw = post.get("date", "")
        content_html = post.get("content", {}).get("rendered", "")
        excerpt_html = post.get("excerpt", {}).get("rendered", "")
        content_md = html_to_markdown(content_html)
        excerpt_text = strip_html(excerpt_html)

        tag_ids = post.get("tags", [])
        tags_str = " | ".join(tag_cache.get(tid, str(tid)) for tid in tag_ids)
        cat_ids = post.get("categories", [])
        cats_str = " | ".join(cat_cache.get(cid, str(cid)) for cid in cat_ids)

        yoast = post.get("yoast_head_json") or {}
        seo_desc = yoast.get("description", excerpt_text)

        corpus_lines += [
            f"---",
            "",
            f"### Article {i} of {total_posts}: {title}",
            "",
            f"| Field | Value |",
            f"|---|---|",
            f"| **URL** | {url} |",
            f"| **Published** | {date_raw} |",
            f"| **Tags** | {tags_str or '—'} |",
            f"| **Categories** | {cats_str or '—'} |",
            f"| **SEO Description** | {seo_desc[:200] if seo_desc else '—'} |",
            "",
            f"**Excerpt:** {excerpt_text}",
            "",
            "**Full Content:**",
            "",
            content_md,
            "",
        ]

    corpus_lines += [
        "---",
        "",
        "## System Memory Snapshot",
        "",
        f"- **Sessions run:** {session_count}",
        f"- **Processed image hashes:** {len(processed_hashes)}",
        f"- **Gmail booking messages parsed:** {gmail_count}",
        f"- **Memory last updated:** {memory_last_updated}",
        "",
        "### Topics Covered (from memory)",
        "",
    ]
    for topic in past_topics:
        corpus_lines.append(f"- {topic}")

    corpus_lines += ["", "---", "", "*End of CONTINUUM Corpus — generated by `academic_data_exporter.py`*", ""]

    with open(CORPUS_OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(corpus_lines))

    corpus_size_kb = CORPUS_OUT.stat().st_size // 1024
    print(f"  ✅ Corpus saved → {CORPUS_OUT}")
    print(f"     {corpus_size_kb} KB | {len(corpus_lines)} lines")

    # 5. Print summary
    print("\n" + "="*65)
    print("  📊 EXPORT SUMMARY")
    print("="*65)
    print(f"  Total published posts       : {total_posts}")
    print(f"  Total estimated words       : {total_words:,}")
    print(f"  Average words per post      : {total_words // max(total_posts, 1)}")
    print(f"  Processed image hashes      : {len(processed_hashes)}")
    print(f"  Gmail messages parsed       : {gmail_count}")
    print(f"  Pipeline sessions run       : {session_count}")
    print(f"  Unique topics tracked       : {len(past_topics)}")
    print(f"  CSV dataset                 : {CSV_OUT.name}")
    print(f"  NotebookLM corpus           : {CORPUS_OUT.name} ({corpus_size_kb} KB)")
    print("="*65 + "\n")


if __name__ == "__main__":
    main()
