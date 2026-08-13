"""
scripts/cleanup_legacy_tags.py
================================
One-shot cleanup script to purge legacy banned tags from all past WordPress posts.

Banned tags: adulting, adult, lifestyle

Steps:
  1. Fetch each banned tag term by name via GET /wp-json/wp/v2/tags?search={name}
  2. Find all posts assigned to that tag ID
  3. Strip the banned tag from each post's tags array via POST /wp-json/wp/v2/posts/{id}
  4. Delete the tag term completely via DELETE /wp-json/wp/v2/tags/{id}?force=true
"""

from __future__ import annotations

import os
import sys
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth

load_dotenv()

WP_URL = os.getenv("WP_URL", "").rstrip("/")
WP_USER = os.getenv("WP_USER", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")

if not all([WP_URL, WP_USER, WP_APP_PASSWORD]):
    print("❌ Missing WP_URL, WP_USER, or WP_APP_PASSWORD in environment. Aborting.")
    sys.exit(1)

API_BASE = f"{WP_URL}/wp-json/wp/v2"
AUTH = HTTPBasicAuth(WP_USER, WP_APP_PASSWORD)
SESSION = requests.Session()
SESSION.auth = AUTH
SESSION.headers.update({"User-Agent": "CONTINUUM-CleanupScript/1.0"})

BANNED_TAG_NAMES = ["adulting", "adult", "lifestyle"]


def find_tag(name: str) -> list:
    resp = SESSION.get(f"{API_BASE}/tags", params={"search": name, "per_page": 100}, timeout=15)
    if resp.status_code != 200:
        print(f"  ⚠️  Could not search for tag '{name}': HTTP {resp.status_code}")
        return []
    tags = resp.json()
    return [t for t in tags if t["name"].lower().strip() == name.lower() or t["slug"].lower() == name.lower()]


def get_posts_with_tag(tag_id: int) -> list:
    posts = []
    page = 1
    while True:
        resp = SESSION.get(
            f"{API_BASE}/posts",
            params={"tags": tag_id, "per_page": 100, "page": page, "status": "any"},
            timeout=20,
        )
        if resp.status_code == 400:
            break
        if resp.status_code != 200:
            print(f"  ⚠️  Error fetching posts for tag_id={tag_id}: HTTP {resp.status_code}")
            break
        batch = resp.json()
        if not batch:
            break
        posts.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return posts


def remove_tag_from_post(post_id: int, post_title: str, tag_id: int, current_tags: list) -> bool:
    new_tags = [t for t in current_tags if t != tag_id]
    resp = SESSION.post(
        f"{API_BASE}/posts/{post_id}",
        json={"tags": new_tags},
        timeout=20,
    )
    if resp.status_code in (200, 201):
        print(f"    ✅ Removed tag {tag_id} from post #{post_id} — '{post_title}'")
        return True
    else:
        print(f"    ❌ Failed to update post #{post_id}: HTTP {resp.status_code} — {resp.text[:120]}")
        return False


def delete_tag_term(tag_id: int, tag_name: str) -> bool:
    resp = SESSION.delete(
        f"{API_BASE}/tags/{tag_id}",
        params={"force": "true"},
        timeout=15,
    )
    if resp.status_code == 200:
        print(f"  🗑️  Tag term '{tag_name}' (ID {tag_id}) permanently deleted.")
        return True
    else:
        print(f"  ⚠️  Could not delete tag '{tag_name}' (ID {tag_id}): HTTP {resp.status_code} — {resp.text[:120]}")
        return False


def main() -> None:
    print(f"\n🔧 CONTINUUM — Legacy Tag Cleanup")
    print(f"   Target site : {WP_URL}")
    print(f"   Banned tags : {BANNED_TAG_NAMES}\n")

    for tag_name in BANNED_TAG_NAMES:
        print(f"── Processing banned tag: '{tag_name}' ──────────────────────────")
        matching_tags = find_tag(tag_name)

        if not matching_tags:
            print(f"  ✅ Tag '{tag_name}' not found on WordPress — nothing to clean up.\n")
            continue

        for tag in matching_tags:
            tag_id = tag["id"]
            tag_label = tag["name"]
            print(f"  Found: '{tag_label}' (ID {tag_id}, slug='{tag['slug']}')")

            posts = get_posts_with_tag(tag_id)
            if not posts:
                print(f"  ℹ️  No posts assigned to tag '{tag_label}' — skipping post updates.")
            else:
                print(f"  Found {len(posts)} post(s) with tag '{tag_label}':")
                for post in posts:
                    post_id = post["id"]
                    post_title = post.get("title", {}).get("rendered", "(untitled)")
                    current_tags = post.get("tags", [])
                    remove_tag_from_post(post_id, post_title, tag_id, current_tags)

            delete_tag_term(tag_id, tag_label)
        print()

    print("✅ Legacy tag cleanup complete.\n")


if __name__ == "__main__":
    main()
