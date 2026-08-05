"""
src/gemini_brain.py
====================
Gemini API Multimodal Processing Engine for CONTINUUM Agentic AI.

Uses the current `google-genai` SDK (replaces deprecated `google-generativeai`).

Provides a unified interface for:
  - Text-only generation (booking parsing, research summaries)
  - Multimodal generation (photo analysis with inline image bytes)
  - Structured JSON extraction with retry logic

All calls use tenacity for exponential back-off on transient API errors.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import google.genai as genai
from google.genai import types as genai_types
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from config.settings import settings
from config.system_prompts import (
    PHOTO_ANALYSIS_SYSTEM,
    PHOTO_ANALYSIS_USER,
    BOOKING_PARSER_SYSTEM,
    BOOKING_PARSER_USER,
    WP_FORMATTER_SYSTEM,
    WP_FORMATTER_USER,
    RESEARCH_SUMMARY_SYSTEM,
    RESEARCH_SUMMARY_USER,
)

logger = logging.getLogger(__name__)


import os


class GeminiBrain:
    """
    Unified Gemini API client for all CONTINUUM AI processing tasks.

    Configures the SDK once at instantiation and exposes task-specific
    methods that construct appropriate prompts, call the model, and parse
    the structured JSON responses. Supports smart model failover on 429 quota errors.
    """

    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        primary_model = os.getenv(
            "GEMINI_MODEL", getattr(settings, "GEMINI_MODEL", "gemini-flash-latest")
        )

        # Candidate model failover chain (validated against API model list)
        candidates = [
            primary_model,
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-2.5-pro",
            "gemini-pro-latest",
        ]
        # Deduplicate while preserving order
        self.candidate_models: list[str] = []
        for m in candidates:
            if m and m not in self.candidate_models:
                self.candidate_models.append(m)

        self._model_index = 0
        self._model = self.candidate_models[0]
        self._config = genai_types.GenerateContentConfig(
            temperature=0.7,
            top_p=0.9,
            max_output_tokens=8192,
        )
        logger.info(
            "GeminiBrain initialised with primary model: '%s' (Failover chain: %s)",
            self._model,
            self.candidate_models,
        )

    # ── Internal Helpers ──────────────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(2),
        reraise=True,
    )
    def _call_model_with_retry(self, model_name: str, contents: list) -> str:
        """Single model call with exponential backoff on transient errors."""
        response = self._client.models.generate_content(
            model=model_name,
            contents=contents,
            config=self._config,
        )
        return response.text

    def _generate(self, contents: list) -> str:
        """
        Low-level generation call with smart model failover on 429 / quota / 404 errors.
        Iterates through candidate_models on rate limit or 429 quota exhaustion.
        """
        last_exception = None

        for idx in range(self._model_index, len(self.candidate_models)):
            current_model = self.candidate_models[idx]
            self._model_index = idx
            self._model = current_model

            try:
                return self._call_model_with_retry(current_model, contents)
            except Exception as exc:
                err_msg = str(exc)
                should_failover = (
                    "429" in err_msg
                    or "404" in err_msg
                    or "RESOURCE_EXHAUSTED" in err_msg
                    or "Quota" in err_msg
                    or "quota" in err_msg
                    or "not found" in err_msg
                )
                if should_failover:
                    next_idx = idx + 1
                    if next_idx < len(self.candidate_models):
                        next_model = self.candidate_models[next_idx]
                        logger.warning(
                            "[GeminiBrain] Rate limit (429) hit on model '%s'. Failing over to next model...",
                            current_model,
                        )
                        last_exception = exc
                        continue

                logger.error("Generation failed on model '%s': %s", current_model, exc)
                raise exc

        if last_exception:
            raise last_exception
        raise RuntimeError("All candidate Gemini models failed generation.")

    @staticmethod
    def _extract_json(raw_text: str) -> dict[str, Any]:
        """
        Extract a JSON object from the model's raw text output.
        Handles markdown code-fenced JSON (```json ... ```) gracefully.
        """
        text = raw_text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse JSON from model output: %s", exc)
            logger.debug("Raw model output:\n%s", raw_text)
            raise ValueError(f"Model returned non-JSON output: {exc}") from exc

    # ── Task-Specific Methods ─────────────────────────────────────────────────

    def analyse_photos(
        self,
        image_bytes_list: list[bytes],
        capture_date: str,
        memory_context: str = "",
    ) -> dict[str, Any]:
        """
        Analyse one or more photos and generate blog content.

        Args:
            image_bytes_list: List of raw JPEG image byte strings.
            capture_date: Human-readable date string for the images.
            memory_context: Optional context string from system memory.

        Returns:
            Parsed JSON dict with title, narrative, tags, etc.
        """
        logger.info(
            "Analysing %d image(s) captured on %s", len(image_bytes_list), capture_date
        )

        # Build multimodal content list: [system text, images..., user text]
        contents: list = [PHOTO_ANALYSIS_SYSTEM]
        for img_bytes in image_bytes_list:
            contents.append(
                genai_types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
            )
        contents.append(
            PHOTO_ANALYSIS_USER.format(
                n_images=len(image_bytes_list),
                capture_date=capture_date,
                memory_context=memory_context or "No prior context.",
            )
        )

        raw = self._generate(contents)
        return self._extract_json(raw)

    def select_best_photo(
        self,
        candidate_photos: list[dict[str, Any]],
        topic_hint: str = "",
    ) -> dict[str, Any]:
        """
        AI-driven intelligent photo selection.

        Passes candidate photo metadata to Gemini 2.0 to judge which photo
        best matches the post topic/story.

        Args:
            candidate_photos: List of media item dicts ('id', 'name', 'mediaMetadata', etc.).
            topic_hint: Optional topic or title context hint.

        Returns:
            The chosen media item dict from candidate_photos.
        """
        if not candidate_photos:
            raise ValueError("No candidate photos provided for selection.")

        if len(candidate_photos) == 1:
            return candidate_photos[0]

        logger.info(
            "Selecting best photo out of %d candidates using Gemini AI (topic_hint='%s')...",
            len(candidate_photos),
            topic_hint,
        )

        candidates_summary = []
        for idx, item in enumerate(candidate_photos):
            creation_time = item.get("mediaMetadata", {}).get("creationTime", "unknown")
            candidates_summary.append({
                "candidate_index": idx,
                "file_id": item.get("id"),
                "filename": item.get("name", "untitled"),
                "creation_time": creation_time,
                "mime_type": item.get("mimeType", "image/jpeg"),
            })

        prompt = (
            "You are an AI photo editor selecting the single best photo for a blog post.\n"
            f"Topic Context: {topic_hint or 'Life logging, tech devlog, travel, digital nomad'}\n\n"
            "Candidate Photos:\n"
            f"{json.dumps(candidates_summary, indent=2)}\n\n"
            "Evaluate the candidates based on freshness, image type, and story relevance.\n"
            "Respond with ONLY a JSON object with this exact key:\n"
            '{"selected_index": 0, "reasoning": "..."}\n'
            "where selected_index is the 0-based integer index of your chosen photo."
        )

        try:
            raw = self._generate([prompt])
            parsed = self._extract_json(raw)
            selected_idx = int(parsed.get("selected_index", 0))
            if 0 <= selected_idx < len(candidate_photos):
                selected_photo = candidate_photos[selected_idx]
                logger.info(
                    "Gemini selected candidate #%d ('%s') — reasoning: %s",
                    selected_idx,
                    selected_photo.get("name", selected_photo["id"]),
                    parsed.get("reasoning", "highest relevance"),
                )
                return selected_photo
        except Exception as exc:
            logger.warning("Photo selection fallback due to error: %s", exc)

        return candidate_photos[0]

    def parse_booking_email(self, email_body: str) -> dict[str, Any]:
        """
        Extract structured booking data from raw email text.

        Args:
            email_body: The decoded plain-text email body.

        Returns:
            Parsed JSON dict with booking_type, provider, dates, etc.
        """
        logger.info("Parsing booking email (%d chars)", len(email_body))
        contents = [
            BOOKING_PARSER_SYSTEM,
            BOOKING_PARSER_USER.format(email_body=email_body),
        ]
        raw = self._generate(contents)
        return self._extract_json(raw)

    def format_for_wordpress(
        self,
        title: str,
        narrative: str,
        tags: list[str],
        target_audience: str = "general travel readers",
        tone: str = "warm, personal, and inspiring",
    ) -> dict[str, Any]:
        """
        Format a narrative draft into a publication-ready WordPress post.

        Args:
            title: The post title.
            narrative: Raw narrative text from photo analysis.
            tags: List of tags for the post.
            target_audience: Description of the target reader.
            tone: Desired writing tone.

        Returns:
            Parsed JSON dict with html_content, excerpt, yoast_keyphrase, etc.
        """
        logger.info("Formatting WordPress post: '%s'", title)
        contents = [
            WP_FORMATTER_SYSTEM,
            WP_FORMATTER_USER.format(
                title=title,
                narrative=narrative,
                tags=", ".join(tags),
                target_audience=target_audience,
                tone=tone,
            ),
        ]
        raw = self._generate(contents)
        return self._extract_json(raw)

    def generate_research_summary(
        self,
        metrics_json: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """
        Generate a research analytics summary from publishing metrics.

        Args:
            metrics_json: JSON string of publishing performance data.
            start_date: Start of the analysis period (ISO date).
            end_date: End of the analysis period (ISO date).

        Returns:
            Parsed JSON dict with summary_text, top_posts, optimisations, etc.
        """
        logger.info(
            "Generating research summary for %s → %s", start_date, end_date
        )
        contents = [
            RESEARCH_SUMMARY_SYSTEM,
            RESEARCH_SUMMARY_USER.format(
                metrics_json=metrics_json,
                start_date=start_date,
                end_date=end_date,
            ),
        ]
        raw = self._generate(contents)
        return self._extract_json(raw)
