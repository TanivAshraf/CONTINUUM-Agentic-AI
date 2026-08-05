"""
src/wordpress_publisher.py
============================
WordPress REST API client for CONTINUUM Agentic AI.

Handles authenticated publishing of posts (draft or live), featured image
upload via the WordPress media endpoint, and basic post management
(update, delete, fetch status).
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

from config.settings import settings

logger = logging.getLogger(__name__)


class WordPressPublisher:
    """
    Authenticated WordPress REST API client.

    Uses Application Passwords (WP 5.6+) for authentication — no plugin
    required. All operations target the /wp-json/wp/v2/ namespace.
    """

    def __init__(self) -> None:
        self._base_url = settings.WP_URL.rstrip("/")
        self._api_base = f"{self._base_url}/wp-json/wp/v2"
        self._auth = HTTPBasicAuth(settings.WP_USER, settings.WP_APP_PASSWORD)
        self._session = requests.Session()
        self._session.auth = self._auth
        self._session.headers.update({"User-Agent": "CONTINUUM-AgenticAI/1.0"})

    # ── Media Upload ──────────────────────────────────────────────────────────

    def upload_featured_image(
        self,
        image_bytes: bytes,
        filename: str = "continuum_featured.jpg",
        alt_text: str = "",
    ) -> int:
        """
        Upload an image to the WordPress media library.

        Args:
            image_bytes: Raw JPEG image data.
            filename: Desired filename for the media item.
            alt_text: Accessibility alt text for the image.

        Returns:
            The WordPress media attachment ID.
        """
        logger.info("Uploading featured image: %s (%d bytes)", filename, len(image_bytes))
        response = self._session.post(
            f"{self._api_base}/media",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "image/jpeg",
            },
            data=image_bytes,
            timeout=60,
        )
        response.raise_for_status()
        media_id: int = response.json()["id"]

        # Update alt text
        if alt_text:
            self._session.post(
                f"{self._api_base}/media/{media_id}",
                json={"alt_text": alt_text},
                timeout=30,
            )

        logger.info("Media uploaded — attachment ID: %d", media_id)
        return media_id

    # ── Post Publishing ───────────────────────────────────────────────────────

    def create_post(
        self,
        title: str,
        html_content: str,
        excerpt: str = "",
        tags: list[str] | None = None,
        categories: list[str] | None = None,
        featured_media_id: int | None = None,
        status: str | None = None,
        yoast_meta: dict | None = None,
    ) -> dict[str, Any]:
        """
        Create a new WordPress post via the REST API.

        Args:
            title: Post title (plain text).
            html_content: Full post body in HTML.
            excerpt: Short excerpt for SEO / archive pages.
            tags: List of tag slugs or names (resolved automatically).
            categories: List of category slugs or names (resolved automatically).
            featured_media_id: Attachment ID for the featured image.
            status: 'draft' | 'publish' | 'pending'. Defaults to settings value.
            yoast_meta: Optional dict for Yoast SEO meta fields.

        Returns:
            The created post object dict from the API.
        """
        post_status = status or settings.WP_DEFAULT_STATUS
        tag_ids = self._resolve_term_ids("tags", tags or [])
        category_ids = self._resolve_term_ids("categories", categories or [])

        payload: dict[str, Any] = {
            "title": title,
            "content": html_content,
            "excerpt": excerpt,
            "status": post_status,
            "tags": tag_ids,
            "categories": category_ids,
        }
        if featured_media_id:
            payload["featured_media"] = featured_media_id

        # Yoast SEO meta (requires Yoast plugin with REST API support)
        if yoast_meta:
            payload["yoast_head_json"] = yoast_meta

        logger.info(
            "Creating post '%s' with status='%s', %d tag(s), %d category(s)",
            title,
            post_status,
            len(tag_ids),
            len(category_ids),
        )
        response = self._session.post(
            f"{self._api_base}/posts",
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        post = response.json()
        logger.info(
            "Post created — ID: %d | URL: %s", post["id"], post.get("link", "n/a")
        )
        return post

    def update_post(self, post_id: int, **fields) -> dict[str, Any]:
        """Update an existing post by ID. Pass any REST API field as a kwarg."""
        response = self._session.post(
            f"{self._api_base}/posts/{post_id}",
            json=fields,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def get_post(self, post_id: int) -> dict[str, Any]:
        """Fetch a single post by ID."""
        response = self._session.get(
            f"{self._api_base}/posts/{post_id}",
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    # ── Term Resolution ───────────────────────────────────────────────────────

    def _resolve_term_ids(self, taxonomy: str, names: list[str]) -> list[int]:
        """
        Resolve tag/category names to WP term IDs, creating them if absent.

        Args:
            taxonomy: 'tags' or 'categories'.
            names: Human-readable names.

        Returns:
            List of WordPress term IDs.
        """
        ids: list[int] = []
        for name in names:
            slug = name.lower().replace(" ", "-")
            # Search first
            search_resp = self._session.get(
                f"{self._api_base}/{taxonomy}",
                params={"search": name, "per_page": 5},
                timeout=15,
            )
            search_resp.raise_for_status()
            results = search_resp.json()
            if results:
                ids.append(results[0]["id"])
            else:
                # Create the term
                create_resp = self._session.post(
                    f"{self._api_base}/{taxonomy}",
                    json={"name": name, "slug": slug},
                    timeout=15,
                )
                if create_resp.status_code in (200, 201):
                    ids.append(create_resp.json()["id"])
                else:
                    logger.warning("Could not create term '%s': %s", name, create_resp.text)
        return ids
