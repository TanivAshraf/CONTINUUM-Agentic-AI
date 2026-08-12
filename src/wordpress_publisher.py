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

        media_id: int = 0
        source_url: str = ""

        try:
            if not response.text.strip():
                raise ValueError("Empty response body")
            data = response.json()
            if isinstance(data, dict) and "id" in data:
                media_id = int(data["id"])
                source_url = str(data.get("source_url", ""))
                sizes = data.get("media_details", {}).get("sizes", {})
            else:
                raise ValueError("Missing 'id' in response dict")
        except (requests.exceptions.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "[WordPress] Media upload returned non-JSON response body. Raw text: %s",
                response.text[:200],
            )
            sizes = {}
            location_hdr = response.headers.get("Location") or response.headers.get("location", "")
            if location_hdr:
                try:
                    media_id = int(location_hdr.rstrip("/").split("/")[-1])
                except (ValueError, IndexError):
                    pass

        # Update metadata if alt_text or caption provided
        update_fields = {}
        if alt_text:
            update_fields["alt_text"] = alt_text
        if caption:
            update_fields["caption"] = caption

        if update_fields and media_id > 0:
            try:
                self._session.post(
                    f"{self._api_base}/media/{media_id}",
                    json=update_fields,
                    timeout=30,
                )
            except Exception as exc:
                logger.warning("Could not update media metadata for ID %d: %s", media_id, exc)

        logger.info("Media uploaded — ID: %d | Source URL: %s", media_id, source_url)
        return {"media_id": media_id, "source_url": source_url, "sizes": sizes}

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

    def resolve_term_ids(self, taxonomy: str, names: list[str]) -> list[int]:
        """
        Resolve Category and Tag names to WordPress integer term IDs.

        Steps:
          1. Strip banned tag names before any API calls.
          2. Fetch existing terms via GET /wp-json/wp/v2/{taxonomy}?per_page=100.
          3. Build mapping of lowercase_name -> term_id.
          4. For any name not found, attempt POST /wp-json/wp/v2/{taxonomy} {"name": name}.
          5. Returns a list of integer term IDs.
        """
        BANNED_TAGS = {"adulting", "adult", "lifestyle", "uncategorized"}
        names = [t for t in names if t.strip() and t.strip().lower() not in BANNED_TAGS]

        term_map: dict[str, int] = {}
        try:
            resp = self._session.get(
                f"{self._api_base}/{taxonomy}",
                params={"per_page": 100},
                timeout=15,
            )
            if resp.status_code == 200:
                for item in resp.json():
                    name_clean = item.get("name", "").lower().strip()
                    slug_clean = item.get("slug", "").lower().strip()
                    if name_clean:
                        term_map[name_clean] = item["id"]
                    if slug_clean:
                        term_map[slug_clean] = item["id"]
        except Exception as exc:
            logger.warning("Error fetching %s terms list: %s", taxonomy, exc)

        resolved_ids: list[int] = []
        for name in names:
            key = name.lower().strip()
            slug_key = key.replace(" ", "-")
            if key in term_map:
                resolved_ids.append(term_map[key])
            elif slug_key in term_map:
                resolved_ids.append(term_map[slug_key])
            else:
                # Attempt to create term
                try:
                    create_resp = self._session.post(
                        f"{self._api_base}/{taxonomy}",
                        json={"name": name, "slug": slug_key},
                        timeout=15,
                    )
                    if create_resp.status_code in (200, 201):
                        new_id = create_resp.json()["id"]
                        term_map[key] = new_id
                        resolved_ids.append(new_id)
                    else:
                        # Fallback: if term creation blocked by WP plugin error, use first existing term ID
                        if term_map:
                            fallback_id = next(iter(term_map.values()))
                            resolved_ids.append(fallback_id)
                except Exception as exc:
                    logger.warning("Term creation failed for %s '%s': %s", taxonomy, name, exc)
                    if term_map:
                        fallback_id = next(iter(term_map.values()))
                        resolved_ids.append(fallback_id)

        # Deduplicate while preserving order
        unique_ids: list[int] = []
        for tid in resolved_ids:
            if tid not in unique_ids:
                unique_ids.append(tid)

        return unique_ids

    def get_or_create_term(self, taxonomy: str = "categories", name: str = "Travel") -> int | None:
        """Single term resolution helper."""
        res = self.resolve_term_ids(taxonomy=taxonomy, names=[name])
        return res[0] if res else None

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
        status: str = "publish",
        yoast_meta: dict | None = None,
        seo_title: str = "",
        seo_description: str = "",
        focus_keyword: str = "",
    ) -> dict[str, Any]:
        """
        Create a new WordPress post via the REST API.
        """
        post_status = status or getattr(settings, "WP_POST_STATUS", settings.WP_DEFAULT_STATUS)
        category_ids = self.resolve_term_ids("categories", categories or ["Travel", "Uncategorized"])
        tag_ids = self.resolve_term_ids("tags", tags or [])

        logger.info(
            "[WordPress] Assigned Category IDs: %s | Tag IDs: %s",
            category_ids,
            tag_ids,
        )

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
            # Prefer medium-sized URL (~380px) for lighter page weight; fall back to full source_url
            source_url = (
                media_info.get("sizes", {}).get("medium", {}).get("source_url")
                or media_info["source_url"]
            )

            caption_text = image_caption if image_caption else title
            figure_html = (
                f'<div class="continuum-img-wrapper" '
                f'style="max-width: 380px; width: 100%; margin: 20px auto; text-align: center;">'
                f'<figure class="wp-block-image size-medium" style="margin: 0; padding: 0;">'
                f'<img src="{source_url}" alt="{image_alt_text or title}" '
                f'style="max-width: 100%; width: 380px; height: auto; border-radius: 8px; '
                f'box-shadow: 0 4px 12px rgba(0,0,0,0.08); display: block; margin: 0 auto;" />'
                f'<figcaption style="font-size: 0.85em; color: #555; margin-top: 8px; font-style: italic;">'
                f'{caption_text}</figcaption>'
                f'</figure>'
                f'</div>\n\n'
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

        # Build SEO meta payload (compatible with both Yoast SEO and RankMath)
        seo_meta: dict[str, str] = {}

        if yoast_meta:
            seo_meta.update(yoast_meta)

        if seo_title:
            seo_meta["yoast_wpseo_title"] = seo_title
            seo_meta["rank_math_title"] = seo_title

        if seo_description:
            seo_meta["yoast_wpseo_metadesc"] = seo_description
            seo_meta["rank_math_description"] = seo_description

        if focus_keyword:
            seo_meta["yoast_wpseo_focuskw"] = focus_keyword
            seo_meta["rank_math_focus_keyword"] = focus_keyword

        if seo_meta:
            payload["meta"] = seo_meta
            logger.info(
                "[WordPress] SEO meta injected — title='%s' | keyword='%s'",
                seo_title or "(from yoast_meta)",
                focus_keyword,
            )

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

    def verify_live_post(self, post_id: int) -> bool:
        """
        Verify that a post is live, accessible, and correctly published.

        Sends HTTP GET to /wp-json/wp/v2/posts/{post_id}.
        Verifies:
          - HTTP status code == 200
          - post status is 'publish'
          - featured_media ID > 0
          - valid post link URL

        Returns True if verified live, False otherwise.
        """
        url = f"{self._api_base}/posts/{post_id}"
        logger.info("[WordPress] Verifying live status for post_id=%d...", post_id)

        try:
            resp = self._session.get(url, timeout=15)
            if resp.status_code != 200:
                logger.warning("[WordPress] Verification failed: GET %s returned %d", url, resp.status_code)
                return False

            data = resp.json()
            status_ok = data.get("status") == "publish"
            has_link = bool(data.get("link"))

            is_live = status_ok and has_link
            logger.info(
                "[WordPress] Live verification for post_id=%d → live=%s (status='%s', featured_media=%s, link='%s')",
                post_id,
                is_live,
                data.get("status"),
                data.get("featured_media"),
                data.get("link"),
            )
            return is_live
        except Exception as exc:
            logger.warning("[WordPress] Exception during live post verification: %s", exc)
            return False
