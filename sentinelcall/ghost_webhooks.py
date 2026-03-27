"""Ghost webhook registration and handling.

Registers webhooks with Ghost Admin API to receive notifications when
incident reports are published, enabling downstream automation (e.g.
notify Slack, trigger status-page updates) when P0/P1 reports go live.
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


def setup_ghost_webhooks(callback_base_url: str) -> dict[str, Any]:
    """Register a Ghost webhook for the ``post.published`` event.

    Args:
        callback_base_url: The base URL where Ghost should send webhook
            payloads (e.g. ``http://localhost:8000``).

    Returns:
        Dict with webhook registration result.
    """
    publisher = _get_publisher()
    target_url = f"{callback_base_url.rstrip('/')}/ghost/webhook"

    if not publisher._configured:
        logger.info("Ghost not configured. Webhook registration simulated.")
        return {
            "id": "mock-webhook-001",
            "event": "post.published",
            "target_url": target_url,
            "status": "registered",
            "mock": True,
        }

    webhook_data = {
        "webhooks": [
            {
                "event": "post.published",
                "target_url": target_url,
                "name": "SentinelCall Incident Report Published",
            }
        ]
    }

    try:
        api_url = f"{publisher.ghost_url}/ghost/api/admin/webhooks/"
        response = http_requests.post(
            api_url,
            json=webhook_data,
            headers=publisher._headers(),
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        webhook = result.get("webhooks", [{}])[0]
        logger.info("Ghost webhook registered: %s -> %s", webhook.get("event"), target_url)
        return {
            "id": webhook.get("id"),
            "event": webhook.get("event"),
            "target_url": target_url,
            "status": "registered",
        }
    except http_requests.RequestException as exc:
        logger.error("Ghost webhook registration failed: %s", exc)
        return {
            "event": "post.published",
            "target_url": target_url,
            "status": "failed",
            "error": str(exc),
        }


def handle_ghost_webhook(data: dict[str, Any]) -> dict[str, Any]:
    """Process an incoming Ghost webhook payload.

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
    url = post.get("url", f"https://sentinelcall.ghost.io/{slug}/")

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


# -- FastAPI endpoint --

if router is not None:

    @router.post("/ghost/webhook")
    async def ghost_webhook_endpoint(request: Request) -> dict[str, Any]:
        """Receive Ghost post.published webhooks."""
        payload = await request.json()
        result = handle_ghost_webhook(payload)
        return {"status": "processed", "result": result}
