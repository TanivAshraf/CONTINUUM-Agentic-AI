"""
config/settings.py
==================
Centralised environment-variable loader for the CONTINUUM Agentic AI platform.
All secrets and runtime options are sourced from a .env file (local dev) or
from the CI/CD environment (production / GitHub Actions).

Usage:
    from config.settings import settings
    print(settings.GEMINI_API_KEY)
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load .env from the project root (no-op if the file doesn't exist)
load_dotenv()


def _require(key: str) -> str:
    """Read an environment variable; raise a clear error if it's missing."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"[CONTINUUM] Required environment variable '{key}' is not set. "
            f"Add it to your .env file or CI secrets."
        )
    return value


def _optional(key: str, default: str = "") -> str:
    """Read an optional environment variable with a safe default."""
    return os.getenv(key, default)


@dataclass(frozen=True)
class Settings:
    # ── Gemini / AI ──────────────────────────────────────────────────────────
    GEMINI_API_KEY: str = field(default_factory=lambda: _require("GEMINI_API_KEY"))
    GEMINI_MODEL: str = field(
        default_factory=lambda: _optional("GEMINI_MODEL", "gemini-flash-latest")
    )

    # ── WordPress REST API ────────────────────────────────────────────────────
    WP_URL: str = field(default_factory=lambda: _require("WP_URL"))
    WP_USER: str = field(default_factory=lambda: _require("WP_USER"))
    WP_APP_PASSWORD: str = field(default_factory=lambda: _require("WP_APP_PASSWORD"))
    WP_DEFAULT_STATUS: str = field(
        default_factory=lambda: _optional("WP_DEFAULT_STATUS", "publish")
    )
    WP_POST_STATUS: str = field(
        default_factory=lambda: _optional("WP_POST_STATUS", "publish")
    )

    # ── Google OAuth / Photos ─────────────────────────────────────────────────
    # These become required once OAuth is configured via scripts/setup_google_oauth.py
    GOOGLE_PHOTOS_REFRESH_TOKEN: str = field(
        default_factory=lambda: _optional("GOOGLE_PHOTOS_REFRESH_TOKEN")
    )
    GOOGLE_CLIENT_ID: str = field(
        default_factory=lambda: _optional("GOOGLE_CLIENT_ID")
    )
    GOOGLE_CLIENT_SECRET: str = field(
        default_factory=lambda: _optional("GOOGLE_CLIENT_SECRET")
    )
    GOOGLE_PHOTOS_ALBUM_ID: str = field(
        default_factory=lambda: _optional(
            "GOOGLE_PHOTOS_ALBUM_ID",
            "AF1QipNV4MW6_c9WiJ7ugxSwmnUrqWxu_ZkJdg2r5Yc0",
        )
    )

    # ── Gmail / Booking ───────────────────────────────────────────────────────
    GMAIL_REFRESH_TOKEN: str = field(
        default_factory=lambda: _optional("GMAIL_REFRESH_TOKEN")
    )

    # ── Logging & Research ────────────────────────────────────────────────────
    LOG_LEVEL: str = field(
        default_factory=lambda: _optional("LOG_LEVEL", "INFO")
    )
    RESEARCH_LOGS_DIR: str = field(
        default_factory=lambda: _optional("RESEARCH_LOGS_DIR", "research_logs")
    )
    MEMORY_FILE: str = field(
        default_factory=lambda: _optional("MEMORY_FILE", "data/system_memory.json")
    )


# Singleton — import this object throughout the codebase
settings = Settings()
