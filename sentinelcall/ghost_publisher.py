"""Ghost Admin API setup + JWT authentication.

Publishes posts to Ghost CMS via the Admin API using short-lived JWTs.
Falls back to in-memory storage when Ghost is not configured, so the
demo works without real API keys.
"""

import logging
import time
import uuid
from typing import Any, Optional

import requests

try:
    import jwt as pyjwt
except ImportError:
    pyjwt = None  # type: ignore[assignment]

from sentinelcall.config import GHOST_URL, GHOST_ADMIN_API_KEY

logger = logging.getLogger(__name__)


class GhostPublisher:
    """Manage Ghost Admin API interactions with JWT authentication."""

    def __init__(self, ghost_url: str | None = None, admin_api_key: str | None = None):
        self.ghost_url = (ghost_url or GHOST_URL).rstrip("/")
        self.admin_api_key = admin_api_key or GHOST_ADMIN_API_KEY
        self._in_memory_posts: list[dict[str, Any]] = []
        self._configured = bool(self.ghost_url and self.admin_api_key and pyjwt)

        if not self._configured:
            reasons = []
            if not self.ghost_url:
                reasons.append("GHOST_URL not set")
            if not self.admin_api_key:
                reasons.append("GHOST_ADMIN_API_KEY not set")
            if pyjwt is None:
                reasons.append("PyJWT not installed")
            logger.warning("Ghost not configured (%s). Using in-memory fallback.", ", ".join(reasons))

    def get_ghost_token(self) -> str:
        """Generate a short-lived Ghost Admin API JWT.

        The GHOST_ADMIN_API_KEY is in the format ``id:secret``. The JWT uses
        HS256 with the ``kid`` header set to the key id, audience ``/admin/``,
        and a 5-minute expiry.
        """
        if not self.admin_api_key or not pyjwt:
            raise RuntimeError("Cannot generate Ghost token: API key or PyJWT unavailable.")

        key_id, secret_hex = self.admin_api_key.split(":")
        secret_bytes = bytes.fromhex(secret_hex)

        iat = int(time.time())
        payload = {
            "iat": iat,
            "exp": iat + 5 * 60,
            "aud": "/admin/",
        }
        token = pyjwt.encode(
            payload,
            secret_bytes,
            algorithm="HS256",
            headers={"kid": key_id},
        )
        return token

    def _headers(self) -> dict[str, str]:
        """Return authorization headers for the Ghost Admin API."""
        return {
            "Authorization": f"Ghost {self.get_ghost_token()}",
            "Content-Type": "application/json",
        }

    def _api_url(self, path: str) -> str:
        """Build a full Ghost Admin API URL."""
        return f"{self.ghost_url}/ghost/api/admin/{path.lstrip('/')}"

    def publish_post(
        self,
        title: str,
        html: str,
        tags: list[str] | None = None,
        visibility: str = "public",
        featured: bool = False,
    ) -> dict[str, Any]:
        """Publish a post to Ghost CMS.

        Args:
            title: Post title.
            html: Post body as HTML.
            tags: List of tag names to attach.
            visibility: ``"public"`` or ``"members"`` (members-only).
            featured: Whether to feature the post.

        Returns:
            Dict with ``id``, ``url``, ``title``, and ``slug`` of the published post.
        """
        post_data: dict[str, Any] = {
            "title": title,
            "html": html,
            "status": "published",
            "visibility": visibility,
            "featured": featured,
        }
        if tags:
            post_data["tags"] = [{"name": t} for t in tags]

        if not self._configured:
            return self._mock_publish(post_data)

        try:
            response = requests.post(
                self._api_url("posts/"),
                json={"posts": [post_data]},
                headers=self._headers(),
                timeout=15,
            )
            response.raise_for_status()
            post = response.json()["posts"][0]
            logger.info("Ghost post published: %s (%s)", post["title"], post["url"])
            return {
                "id": post["id"],
                "url": post["url"],
                "title": post["title"],
                "slug": post["slug"],
            }
        except requests.RequestException as exc:
            logger.error("Ghost publish failed: %s. Falling back to in-memory.", exc)
            return self._mock_publish(post_data)

    def get_posts(self, tag: str | None = None) -> list[dict[str, Any]]:
        """List published posts, optionally filtered by tag.

        Args:
            tag: If provided, only return posts with this tag.

        Returns:
            List of post dicts with ``id``, ``url``, ``title``, ``slug``.
        """
        if not self._configured:
            if tag:
                return [
                    p for p in self._in_memory_posts
                    if tag in [t["name"] for t in p.get("tags", [])]
                ]
            return list(self._in_memory_posts)

        try:
            params: dict[str, str] = {"limit": "50"}
            if tag:
                params["filter"] = f"tag:{tag}"

            response = requests.get(
                self._api_url("posts/"),
                headers=self._headers(),
                params=params,
                timeout=15,
            )
            response.raise_for_status()
            posts = response.json().get("posts", [])
            return [
                {"id": p["id"], "url": p["url"], "title": p["title"], "slug": p["slug"]}
                for p in posts
            ]
        except requests.RequestException as exc:
            logger.error("Ghost get_posts failed: %s", exc)
            return list(self._in_memory_posts)

    def delete_post(self, post_id: str) -> bool:
        """Delete a post by ID.

        Returns:
            True if the post was deleted (or removed from in-memory store).
        """
        if not self._configured:
            before = len(self._in_memory_posts)
            self._in_memory_posts = [p for p in self._in_memory_posts if p.get("id") != post_id]
            return len(self._in_memory_posts) < before

        try:
            response = requests.delete(
                self._api_url(f"posts/{post_id}/"),
                headers=self._headers(),
                timeout=15,
            )
            response.raise_for_status()
            logger.info("Ghost post deleted: %s", post_id)
            return True
        except requests.RequestException as exc:
            logger.error("Ghost delete failed for %s: %s", post_id, exc)
            return False

    # -- Fallback helpers --

    def _mock_publish(self, post_data: dict[str, Any]) -> dict[str, Any]:
        """Store a post in memory and return a mock response."""
        post_id = f"ghost-{uuid.uuid4().hex[:12]}"
        slug = post_data["title"].lower().replace(" ", "-")[:60]
        mock_url = f"https://sentinelcall.ghost.io/{slug}/"
        record = {
            "id": post_id,
            "url": mock_url,
            "title": post_data["title"],
            "slug": slug,
            "html": post_data.get("html", ""),
            "visibility": post_data.get("visibility", "public"),
            "tags": post_data.get("tags", []),
            "mock": True,
        }
        self._in_memory_posts.append(record)
        logger.info("In-memory Ghost post stored: %s (%s)", record["title"], mock_url)
        return {
            "id": post_id,
            "url": mock_url,
            "title": record["title"],
            "slug": slug,
            "mock": True,
        }
