"""Summarisation backends.

Two ways to reach Claude:
  * ApiBackend  — Anthropic API (needs ANTHROPIC_API_KEY, billed per token).
  * CliBackend  — the local `claude` CLI in headless mode (`claude -p`), which
                  runs on an existing Claude Code login such as a Max/Pro
                  subscription. No API key required.

``choose_backend`` picks one automatically: API if a key is present, otherwise
the CLI if it is installed.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from typing import Optional

log = logging.getLogger("usum.backends")


class BackendError(RuntimeError):
    pass


class ApiBackend:
    """Anthropic API via the official SDK."""

    name = "api"
    default_model = "claude-sonnet-4-6"

    def __init__(self, model: str, api_key: str):
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover
            raise BackendError(
                "The 'anthropic' package is not installed. Run: pip install anthropic"
            ) from exc
        self.model = model
        self._client = Anthropic(api_key=api_key)

    def complete(self, system: str, user: str, max_tokens: int = 4096) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()


class CliBackend:
    """The `claude` CLI in headless mode — uses your Claude Code subscription."""

    name = "cli"
    default_model = "sonnet"

    def __init__(self, model: str, timeout: int = 900):
        self.model = model
        self.timeout = timeout
        self._cmd = self._locate()

    @staticmethod
    def is_available() -> bool:
        return (
            shutil.which("claude") is not None
            or shutil.which("claude.cmd") is not None
        )

    @staticmethod
    def _locate() -> list[str]:
        if sys.platform == "win32":
            # Prefer the .cmd shim and run it through cmd.exe so subprocess can
            # launch it reliably.
            cmd = shutil.which("claude.cmd") or shutil.which("claude")
            if cmd and cmd.lower().endswith(".cmd"):
                return ["cmd", "/c", cmd]
            if cmd:
                return [cmd]
        else:
            exe = shutil.which("claude")
            if exe:
                return [exe]
        raise BackendError(
            "The 'claude' CLI was not found on PATH. Install Claude Code, or use "
            "the API backend with --backend api and an ANTHROPIC_API_KEY."
        )

    def complete(self, system: str, user: str, max_tokens: int = 4096) -> str:
        # Headless mode takes the prompt on stdin. We fold the system guidance
        # into the prompt rather than relying on Claude Code's agent system prompt.
        prompt = f"{system}\n\n---\n\n{user}"
        args = self._cmd + ["-p", "--model", self.model]
        try:
            proc = subprocess.run(
                args,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise BackendError(f"claude CLI timed out after {self.timeout}s") from exc
        except FileNotFoundError as exc:  # pragma: no cover
            raise BackendError("Could not launch the 'claude' CLI.") from exc

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise BackendError(f"claude CLI failed (exit {proc.returncode}): {err[:500]}")
        return (proc.stdout or "").strip()


def choose_backend(
    requested: str,
    model: Optional[str],
    api_key: Optional[str],
) -> "ApiBackend | CliBackend":
    """Build a backend. ``requested`` is 'auto', 'api' or 'cli'."""
    have_key = bool(api_key or os.environ.get("ANTHROPIC_API_KEY"))
    have_cli = CliBackend.is_available()

    if requested == "auto":
        requested = "api" if have_key else ("cli" if have_cli else "api")

    if requested == "cli":
        chosen = model or CliBackend.default_model
        log.info("Using Claude CLI backend (model=%s) — your Claude Code subscription.", chosen)
        return CliBackend(chosen)

    # api
    from .config import get_api_key

    key = api_key or get_api_key()  # raises a helpful error if missing
    chosen = model or ApiBackend.default_model
    log.info("Using Anthropic API backend (model=%s).", chosen)
    return ApiBackend(chosen, key)
