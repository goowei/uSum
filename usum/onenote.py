"""Push reports to Microsoft OneNote via the Microsoft Graph API.

Auth uses MSAL's device-code flow (good for a CLI): the first run prints a URL
and a code to enter in any browser; the token is then cached locally so later
runs are non-interactive until it expires.

Requirements (optional extra):  pip install msal requests
Setup: register an app at https://entra.microsoft.com (Azure) with the
delegated Graph permission ``Notes.ReadWrite`` and "Allow public client flows"
enabled, then set USUM_MS_CLIENT_ID to its Application (client) ID.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger("usum.onenote")

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = ["Notes.ReadWrite"]
# "common" works for both work/school and personal Microsoft accounts.
DEFAULT_TENANT = os.environ.get("USUM_MS_TENANT", "common")


def _config_dir() -> Path:
    d = Path.home() / ".usum"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path() -> Path:
    return _config_dir() / "msal_token_cache.json"


def get_token(client_id: str, tenant: str = DEFAULT_TENANT) -> str:
    """Acquire a Graph access token, using a cached one when possible."""
    import msal

    cache = msal.SerializableTokenCache()
    cache_file = _cache_path()
    if cache_file.exists():
        cache.deserialize(cache_file.read_text(encoding="utf-8"))

    app = msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant}",
        token_cache=cache,
    )

    result = None
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Failed to start device flow: {flow.get('error_description')}")
        print("\n=== Microsoft sign-in required ===")
        print(flow["message"])  # e.g. "go to https://microsoft.com/devicelogin and enter CODE"
        print("==================================\n")
        result = app.acquire_token_by_device_flow(flow)

    if cache.has_state_changed:
        cache_file.write_text(cache.serialize(), encoding="utf-8")

    if "access_token" not in result:
        raise RuntimeError(
            f"Auth failed: {result.get('error')}: {result.get('error_description')}"
        )
    return result["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _find_or_create(session, token: str, list_url: str, create_url: str, name: str) -> str:
    """Return the id of a notebook/section named ``name``, creating it if absent."""
    resp = session.get(list_url, headers=_headers(token), timeout=30)
    resp.raise_for_status()
    for item in resp.json().get("value", []):
        if item.get("displayName") == name:
            return item["id"]
    resp = session.post(
        create_url,
        headers={**_headers(token), "Content-Type": "application/json"},
        data=json.dumps({"displayName": name}),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def resolve_section(session, token: str, notebook: str, section: str) -> str:
    """Resolve (creating as needed) a notebook + section, return the section id."""
    notebook_id = _find_or_create(
        session,
        token,
        f"{GRAPH}/me/onenote/notebooks",
        f"{GRAPH}/me/onenote/notebooks",
        notebook,
    )
    return _find_or_create(
        session,
        token,
        f"{GRAPH}/me/onenote/notebooks/{notebook_id}/sections",
        f"{GRAPH}/me/onenote/notebooks/{notebook_id}/sections",
        section,
    )


def _page_html(title: str, body_markdown: str) -> str:
    import markdown as md

    body = md.markdown(body_markdown, extensions=["extra"])
    safe_title = (title or "uSum page").replace("<", "&lt;").replace(">", "&gt;")
    return (
        "<!DOCTYPE html><html><head>"
        f"<title>{safe_title}</title>"
        '<meta charset="utf-8" />'
        "</head><body>"
        f"{body}"
        "</body></html>"
    )


def create_page(session, token: str, section_id: str, title: str, body_markdown: str) -> str:
    html = _page_html(title, body_markdown)
    resp = session.post(
        f"{GRAPH}/me/onenote/sections/{section_id}/pages",
        headers={**_headers(token), "Content-Type": "text/html"},
        data=html.encode("utf-8"),
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("links", {}).get("oneNoteWebUrl", {}).get("href", data.get("id", ""))


def push_pages(
    pages: list[tuple[str, str]],
    client_id: str,
    notebook: str = "uSum",
    section: str = "Summaries",
    tenant: str = DEFAULT_TENANT,
) -> list[str]:
    """Push (title, markdown) pages to OneNote. Returns created page URLs/ids."""
    try:
        import requests  # noqa: F401
        import msal  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "OneNote push needs extra packages. Install with: pip install msal requests"
        ) from exc

    import requests

    token = get_token(client_id, tenant)
    session = requests.Session()
    section_id = resolve_section(session, token, notebook, section)

    urls: list[str] = []
    for title, body in pages:
        try:
            url = create_page(session, token, section_id, title, body)
            log.info("Created OneNote page: %s", title)
            urls.append(url)
        except Exception as exc:
            log.error("Failed to create OneNote page '%s': %s", title, exc)
    return urls


def get_client_id(explicit: Optional[str] = None) -> str:
    client_id = explicit or os.environ.get("USUM_MS_CLIENT_ID")
    if not client_id:
        raise RuntimeError(
            "OneNote push needs a Microsoft app client ID. Register an app at "
            "https://entra.microsoft.com (delegated permission Notes.ReadWrite, "
            "public client flows enabled) and set USUM_MS_CLIENT_ID or pass "
            "--onenote-client-id."
        )
    return client_id
