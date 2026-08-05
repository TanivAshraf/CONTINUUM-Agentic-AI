"""
src/wordpress_publisher.py
============================
WordPress REST API client for CONTINUUM Agentic AI.

Handles authenticated media uploads, term resolution (categories and tags),
featured image assignment, HTML image figure embedding, and post publishing.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

from config.settings import settings

logger = logging.getLogger(__name__)


class WordPressPublisher:
    """
    Authenticated WordPress REST API client.

    Uses Application Passwords (WP 5.6+) for authentication.
    Targets the /wp-json/wp/v2/ namespace.
    """

    def __init__(self) -> None:
        self._base_url = settings.WP_URL.rstrip("/")
        self._api_base = f"{self._base_url}/wp-json/wp/v2"
        self._auth = HTTPBasicAuth(settings.WP_USER, settings.WP_APP_PASSWORD)
        self._session = requests.Session()
        self._session.auth = self._auth
        self._session.headers.update({"User-Agent": "CONTINUUM-AgenticAI/1.0"})

    # ── Media Upload ──────────────────────────────────────────────────────────

    def upload_media(
        self,
        image_bytes: bytes,
        filename: str = "photo.jpg",
        alt_text: str = "",
        caption: str = "",
    ) -> dict[str, Any]:
        """
        Upload raw image bytes to /wp-json/wp/v2/media using HTTP Basic Auth.

        Args:
            image_bytes: Raw image data.
            filename: Desired filename for the media item.
            alt_text: Accessibility alt text.
            caption: Media caption.

        Returns:
            Dict containing 'media_id' (int) and 'source_url' (str).
        """
        logger.info("Uploading media to WordPress: %s (%d bytes)", filename, len(image_bytes))

        content_type = "image/png" if filename.lower().endswith(".png") else "image/jpeg"

        response = self._session.post(
            f"{self._api_base}/media",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": content_type,
            },
            data=image_bytes,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        media_id: int = data["id"]
        source_url: str = data.get("source_url", "")

        # Update metadata if alt_text or caption provided
        update_fields = {}
        if alt_text:
            update_fields["alt_text"] = alt_text
        if caption:
            update_fields["caption"] = caption

        if update_fields:
            try:
                self._session.post(
                    f"{self._api_base}/media/{media_id}",
                    json=update_fields,
                    timeout=30,
                )
            except Exception as exc:
                logger.warning("Could not update media metadata for ID %d: %s", media_id, exc)

        logger.info("Media uploaded — ID: %d | Source URL: %s", media_id, source_url)
        return {"media_id": media_id, "source_url": source_url}

    def upload_featured_image(
        self,
        image_bytes: bytes,
        filename: str = "continuum_featured.jpg",
        alt_text: str = "",
    ) -> int:
        """Convenience method returning media_id for featured image upload."""
        res = self.upload_media(image_bytes=image_bytes, filename=filename, alt_text=alt_text)
        return res["media_id"]

    # ── Term ID Resolution ───────────────────────────────────────────────────

    def get_or_create_term(self, taxonomy: str = "categories", name: str = "Travel") -> int | None:
        """
        Search for a category or tag by name; if absent, attempt to create it.

        Args:
            taxonomy: 'categories' or 'tags'.
            name: Human-readable term name.

        Returns:
            Integer term ID if resolved/created, or None if creation fails.
        """
        slug = name.lower().replace(" ", "-").strip()
        try:
            # 1. Search for existing term
            search_resp = self._session.get(
                f"{self._api_base}/{taxonomy}",
                params={"search": name, "per_page": 10},
                timeout=15,
            )
            if search_resp.status_code == 200:
                results = search_resp.json()
                for item in results:
                    if item.get("name", "").lower() == name.lower() or item.get("slug") == slug:
                        return item["id"]
                if results:
                    return results[0]["id"]

            # 2. Term not found; attempt creation
            create_resp = self._session.post(
                f"{self._api_base}/{taxonomy}",
                json={"name": name, "slug": slug},
                timeout=15,
            )
            if create_resp.status_code in (200, 201):
                return create_resp.json()["id"]
            else:
                logger.warning("Could not create %s term '%s': %s", taxonomy, name, create_resp.text[:150])
        except Exception as exc:
            logger.warning("Error resolving term '%s' in taxonomy '%s': %s", name, taxonomy, exc)

        return None

    def _resolve_term_ids(self, taxonomy: str, names: list[str]) -> list[int]:
        """
        Convert list of term names into clean array of integer term IDs.
        Filters out None values to ensure strict integer array output.
        """
        term_ids: list[int] = []
        for name in names:
            tid = self.get_or_create_term(taxonomy=taxonomy, name=name)
            if tid is not None and tid not in term_ids:
                term_ids.append(tid)
        return term_ids

    # ── Post Publishing ───────────────────────────────────────────────────────

    def create_post(
        self,
        title: str,
        html_content: str,
        excerpt: str = "",
        tags: list[str] | None = None,
        categories: list[str] | None = None,
        image_bytes: bytes | None = None,
        image_filename: str = "continuum_photo.jpg",
        image_caption: str = "",
        image_alt_text: str = "",
        featured_media_id: int | None = None,
        status: str | None = None,
        yoast_meta: dict | None = None,
    ) -> dict[str, Any]:
        """
        Create a new WordPress post via the REST API.

        Features:
          - If image_bytes provided, uploads to media library, sets featured_media,
            and prepends an HTML figure block to post content.
          - Converts category and tag names to integer term ID arrays.
        """
        post_status = status or settings.WP_DEFAULT_STATUS
        tag_ids = self._resolve_term_ids("tags", tags or [])
        category_ids = self._resolve_term_ids("categories", categories or ["Travel Stories", "AI Agent Development"])

        final_content = html_content

        # Handle image upload and figure embedding if raw bytes are passed
        if image_bytes is not None and featured_media_id is None:
            media_info = self.upload_media(
                image_bytes=image_bytes,
                filename=image_filename,
                alt_text=image_alt_text or title,
                caption=image_caption,
            )
            featured_media_id = media_info["media_id"]
            source_url = media_info["source_url"]

            caption_html = (
                f"<figcaption>{image_caption}</figcaption>"
                if image_caption
                else f"<figcaption>{title}</figcaption>"
            )
            figure_html = (
                f'<figure class="wp-block-image">'
                f'<img src="{source_url}" alt="{image_alt_text or title}" />'
                f"{caption_html}"
                f"</figure>\n\n"
            )
            final_content = figure_html + html_content

        payload: dict[str, Any] = {
            "title": title,
            "content": final_content,
            "excerpt": excerpt,
            "status": post_status,
            "tags": tag_ids,
            "categories": category_ids,
        }
        if featured_media_id:
            payload["featured_media"] = featured_media_id

        if yoast_meta:
            payload["yoast_head_json"] = yoast_meta

        logger.info(
            "Creating post '%s' (status='%s', %d tag(s), %d category(s), featured_media=%s)",
            title,
            post_status,
            len(tag_ids),
            len(category_ids),
            featured_media_id,
        )
        response = self._session.post(
            f"{self._api_base}/posts",
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        post = response.json()
        logger.info("Post created — ID: %d | Link: %s", post["id"], post.get("link", "n/a"))
        return post

    def update_post(self, post_id: int, **fields) -> dict[str, Any]:
        """Update an existing post by ID."""
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
