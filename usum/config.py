"""Configuration loading (env / .env)."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()  # load .env from cwd if present, silently no-op otherwise

DEFAULT_MODEL = os.environ.get("USUM_MODEL", "claude-sonnet-4-6")
DEFAULT_WHISPER_MODEL = os.environ.get("USUM_WHISPER_MODEL", "base")


def get_api_key(explicit: str | None = None) -> str:
    """Resolve the Anthropic API key from the CLI flag or environment."""
    key = explicit or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "No Anthropic API key found. Set ANTHROPIC_API_KEY in your environment "
            "or a .env file, or pass --api-key. See .env.example."
        )
    return key
