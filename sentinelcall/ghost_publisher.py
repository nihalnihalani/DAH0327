"""Ghost Admin API setup + JWT authentication.

Publishes posts to Ghost CMS via the Admin API using short-lived JWTs.
Uses ``?source=html`` so we can send raw HTML that Ghost converts to its
internal Lexical format automatically.

Falls back to in-memory storage when Ghost is not configured, so the
demo works without real API keys.

Ref: https://docs.ghost.org/admin-api/
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

# Valid Ghost post visibility values:
#   "public"  — accessible to anyone
#   "members" — accessible to all signed-in members (free + paid)
#   "paid"    — accessible to paid members only
#   "tiers"   — accessible to members of specific tiers (requires tiers field)
VALID_VISIBILITIES = {"public", "members", "paid", "tiers"}


class GhostPublisher:
    """Manage Ghost Admin API interactions with JWT authentication.

    Authentication uses short-lived HS256 JWTs generated from the Admin API
    key (format ``id:secret``).  The hex-encoded secret is decoded to raw
    bytes before signing.

    JWT header: ``{"alg": "HS256", "typ": "JWT", "kid": "<id>"}``
    JWT payload: ``{"iat": <now>, "exp": <now+5min>, "aud": "/admin/"}``
    Auth header: ``Authorization: Ghost <token>``
    """

    def __init__(self, ghost_url: str | None = None, admin_api_key: str | None = None):
        self.ghost_url = (ghost_url or GHOST_URL or "").rstrip("/")
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

    # -- Authentication --------------------------------------------------------

    def get_ghost_token(self) -> str:
        """Generate a short-lived Ghost Admin API JWT.

        The ``GHOST_ADMIN_API_KEY`` is in ``id:secret`` format.  The secret
        half is hex-encoded; we decode it to raw bytes before signing.

        Ghost requires:
          - Header: ``alg=HS256``, ``typ=JWT``, ``kid=<id>``
          - Payload: ``iat`` (now, seconds), ``exp`` (now + 5 min), ``aud="/admin/"``
          - Timestamps in **seconds** since unix epoch (not milliseconds).
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
        token: str = pyjwt.encode(
            payload,
            secret_bytes,
            algorithm="HS256",
            headers={"kid": key_id, "typ": "JWT"},
        )
        return token

    def _headers(self) -> dict[str, str]:
        """Return authorization headers for the Ghost Admin API."""
        return {
            "Authorization": f"Ghost {self.get_ghost_token()}",
            "Content-Type": "application/json",
        }

    def _api_url(self, path: str, query: str = "") -> str:
        """Build a full Ghost Admin API URL.

        Args:
            path: API path relative to ``/ghost/api/admin/``.
            query: Optional query string (without leading ``?``).
        """
        url = f"{self.ghost_url}/ghost/api/admin/{path.lstrip('/')}"
        if query:
            url = f"{url}?{query}"
        return url

    # -- Posts -----------------------------------------------------------------

    def publish_post(
        self,
        title: str,
        html: str,
        tags: list[str] | None = None,
        visibility: str = "public",
        featured: bool = False,
        status: str = "published",
        tiers: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Publish (or draft) a post to Ghost CMS.

        Uses ``POST /ghost/api/admin/posts/?source=html`` so Ghost
        automatically converts the HTML body into its Lexical editor format.

        Args:
            title: Post title (the only required field).
            html: Post body as HTML.
            tags: Tag names — sent as short-form ``["name"]`` or long-form
                ``[{"name": "..."}]`` (Ghost accepts both).
            visibility: One of ``"public"``, ``"members"``, ``"paid"``,
                or ``"tiers"``.  When ``"tiers"`` is used, pass the
                *tiers* argument as well.
            featured: Whether to feature the post.
            status: ``"published"`` (default) or ``"draft"``.
            tiers: List of tier dicts ``[{"slug": "..."}]`` for tier-gated
                visibility.  Only used when *visibility* is ``"tiers"``.

        Returns:
            Dict with ``id``, ``url``, ``title``, ``slug`` (and ``mock=True``
            when the in-memory fallback is used).
        """
        if visibility not in VALID_VISIBILITIES:
            logger.warning(
                "Unknown Ghost visibility %r; defaulting to 'public'.", visibility
            )
            visibility = "public"

        post_data: dict[str, Any] = {
            "title": title,
            "html": html,
            "status": status,
            "visibility": visibility,
            "featured": featured,
        }
        if tags:
            post_data["tags"] = [{"name": t} for t in tags]
        if visibility == "tiers" and tiers:
            post_data["tiers"] = tiers

        if not self._configured:
            return self._mock_publish(post_data)

        try:
            response = requests.post(
                self._api_url("posts/", query="source=html"),
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
                    if tag in [t.get("name", t) if isinstance(t, dict) else t
                               for t in p.get("tags", [])]
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

    # -- Fallback helpers ------------------------------------------------------

    def _mock_publish(self, post_data: dict[str, Any]) -> dict[str, Any]:
        """Store a post in memory and return a mock response."""
        post_id = f"ghost-{uuid.uuid4().hex[:12]}"
        slug = post_data["title"].lower().replace(" ", "-")[:60]
        mock_url = f"https://pager0.ghost.io/{slug}/"
        record = {
            "id": post_id,
            "url": mock_url,
            "title": post_data["title"],
            "slug": slug,
            "html": post_data.get("html", ""),
            "visibility": post_data.get("visibility", "public"),
            "tags": post_data.get("tags", []),
            "featured": post_data.get("featured", False),
            "status": post_data.get("status", "published"),
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
