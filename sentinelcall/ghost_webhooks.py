"""Ghost webhook registration and handling.

Registers webhooks with the Ghost Admin API (``POST /ghost/api/admin/webhooks/``)
to receive notifications when incident reports are published, enabling downstream
automation (e.g. notify Slack, trigger status-page updates) when P0/P1 reports
go live.

Ghost supports 31 webhook events across posts, pages, tags, and members.
We register for ``post.published`` by default to capture new incident reports.

Ref: https://docs.ghost.org/admin-api/webhooks/creating-a-webhook
     https://docs.ghost.org/webhooks/
"""

import logging
from typing import Any

try:
    from fastapi import APIRouter, Request
except ImportError:
    APIRouter = None  # type: ignore[assignment,misc]
    Request = None  # type: ignore[assignment,misc]

import requests as http_requests

from sentinelcall.config import GHOST_URL, GHOST_ADMIN_API_KEY
from sentinelcall.ghost_publisher import GhostPublisher

logger = logging.getLogger(__name__)

# Complete list of Ghost webhook events (29 total).
# Ref: https://github.com/TryGhost/Ghost/issues/15537
GHOST_WEBHOOK_EVENTS = [
    # Site
    "site.changed",
    # Posts
    "post.added", "post.deleted", "post.edited",
    "post.published", "post.published.edited",
    "post.unpublished", "post.scheduled",
    "post.unscheduled", "post.rescheduled",
    # Pages
    "page.added", "page.deleted", "page.edited",
    "page.published", "page.published.edited",
    "page.unpublished", "page.scheduled",
    "page.unscheduled", "page.rescheduled",
    # Tags
    "tag.added", "tag.edited", "tag.deleted",
    "post.tag.attached", "post.tag.detached",
    "page.tag.attached", "page.tag.detached",
    # Members
    "member.added", "member.edited", "member.deleted",
]

# FastAPI router for the webhook endpoint
if APIRouter is not None:
    router = APIRouter(tags=["ghost-webhooks"])
else:
    router = None  # type: ignore[assignment]

# Module-level publisher instance (lazy init)
_publisher: GhostPublisher | None = None

_webhook_log: list[dict[str, Any]] = []


def _get_publisher() -> GhostPublisher:
    global _publisher
    if _publisher is None:
        _publisher = GhostPublisher()
    return _publisher


def setup_ghost_webhooks(
    callback_base_url: str,
    events: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Register Ghost webhooks for the given events.

    Uses ``POST /ghost/api/admin/webhooks/`` with token-based auth.
    Required fields: ``event``, ``target_url``.
    Optional fields: ``name``, ``secret``, ``api_version`` (defaults to ``"v6"``).

    Note: Ghost has no API to *list* existing webhooks — you can only
    create (POST), update (PUT), and delete (DELETE) them.

    Args:
        callback_base_url: The base URL where Ghost should send webhook
            payloads (e.g. ``http://localhost:8000``).
        events: List of Ghost event names to subscribe to.  Defaults to
            ``["post.published"]``.

    Returns:
        List of dicts, one per event, with webhook registration results.
    """
    if events is None:
        events = ["post.published"]

    publisher = _get_publisher()
    results: list[dict[str, Any]] = []

    for event in events:
        if event not in GHOST_WEBHOOK_EVENTS:
            logger.warning("Unknown Ghost webhook event %r; registering anyway.", event)

        target_url = f"{callback_base_url.rstrip('/')}/ghost/webhook/{event}"
        result = _register_single_webhook(publisher, event, target_url)
        results.append(result)

    return results


def _register_single_webhook(
    publisher: GhostPublisher,
    event: str,
    target_url: str,
) -> dict[str, Any]:
    """Register a single webhook with Ghost Admin API."""
    if not publisher._configured:
        logger.info("Ghost not configured. Webhook registration simulated for %s.", event)
        return {
            "id": f"mock-webhook-{event.replace('.', '-')}",
            "event": event,
            "target_url": target_url,
            "status": "registered",
            "mock": True,
        }

    webhook_payload = {
        "webhooks": [
            {
                "event": event,
                "target_url": target_url,
                "name": f"Page0: {event}",
            }
        ]
    }

    try:
        api_url = publisher._api_url("webhooks/")
        response = http_requests.post(
            api_url,
            json=webhook_payload,
            headers=publisher._headers(),
            timeout=15,
        )
        response.raise_for_status()
        webhook = response.json().get("webhooks", [{}])[0]
        logger.info("Ghost webhook registered: %s -> %s", event, target_url)
        return {
            "id": webhook.get("id"),
            "event": webhook.get("event", event),
            "target_url": target_url,
            "status": "registered",
        }
    except http_requests.RequestException as exc:
        logger.error("Ghost webhook registration failed for %s: %s", event, exc)
        return {
            "event": event,
            "target_url": target_url,
            "status": "failed",
            "error": str(exc),
        }


def delete_ghost_webhook(webhook_id: str) -> bool:
    """Delete a Ghost webhook by ID.

    Uses ``DELETE /ghost/api/admin/webhooks/{id}/``.

    Returns:
        True if the webhook was deleted successfully.
    """
    publisher = _get_publisher()
    if not publisher._configured:
        logger.info("Ghost not configured. Webhook deletion simulated for %s.", webhook_id)
        return True

    try:
        api_url = publisher._api_url(f"webhooks/{webhook_id}/")
        response = http_requests.delete(
            api_url,
            headers=publisher._headers(),
            timeout=15,
        )
        response.raise_for_status()
        logger.info("Ghost webhook deleted: %s", webhook_id)
        return True
    except http_requests.RequestException as exc:
        logger.error("Ghost webhook deletion failed for %s: %s", webhook_id, exc)
        return False


def handle_ghost_webhook(data: dict[str, Any]) -> dict[str, Any]:
    """Process an incoming Ghost webhook payload.

    Ghost sends a JSON body containing the affected resource.  For post
    events the payload contains a ``post`` (or ``current``) key with the
    full post object including tags.

    Checks if the published post is tagged as a P0 or P1 incident and
    returns a structured result for downstream consumers.

    Args:
        data: The webhook payload from Ghost.

    Returns:
        Dict with ``is_incident``, ``is_critical``, ``post_title``, ``tags``.
    """
    post = data.get("post", data.get("current", {}))
    title = post.get("title", "")
    tags = [t.get("name", "") for t in post.get("tags", [])]
    slug = post.get("slug", "")
    url = post.get("url", f"https://page0.ghost.io/{slug}/")

    is_incident = "incident" in tags
    is_critical = any(t in tags for t in ("sev-0", "sev-1", "p0", "p1"))

    result = {
        "is_incident": is_incident,
        "is_critical": is_critical,
        "post_title": title,
        "post_url": url,
        "tags": tags,
    }

    _webhook_log.append(result)

    if is_critical:
        logger.warning("CRITICAL incident report published: %s", title)
    elif is_incident:
        logger.info("Incident report published: %s", title)

    return result


def get_webhook_log() -> list[dict[str, Any]]:
    """Return the list of processed webhook events."""
    return list(_webhook_log)


# -- FastAPI endpoint --

if router is not None:

    @router.post("/ghost/webhook/{event}")
    async def ghost_webhook_endpoint(event: str, request: Request) -> dict[str, Any]:
        """Receive Ghost webhook payloads for any event type."""
        payload = await request.json()
        result = handle_ghost_webhook(payload)
        result["event"] = event
        return {"status": "processed", "result": result}

    @router.post("/ghost/webhook")
    async def ghost_webhook_endpoint_legacy(request: Request) -> dict[str, Any]:
        """Receive Ghost webhooks on the legacy path (no event in URL)."""
        payload = await request.json()
        result = handle_ghost_webhook(payload)
        return {"status": "processed", "result": result}
