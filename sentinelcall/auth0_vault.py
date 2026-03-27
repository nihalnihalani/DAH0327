"""Auth0 Token Vault — manages third-party API credentials through Auth0.

The agent never sees raw secrets. All tokens are fetched from Auth0's Token Vault
(federated token exchange), with a realistic mock fallback for demo/free-tier usage.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import requests

from sentinelcall.config import AUTH0_DOMAIN, AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mock data — realistic tokens returned when Auth0 is not configured
# ---------------------------------------------------------------------------
MOCK_CONNECTIONS = {
    "github": {
        "connection_id": "con_github_abc123",
        "provider": "github",
        "scopes": ["repo", "read:org", "read:packages"],
    },
    "datadog": {
        "connection_id": "con_datadog_def456",
        "provider": "datadog",
        "scopes": ["metrics:read", "events:read", "logs:read"],
    },
    "pagerduty": {
        "connection_id": "con_pagerduty_ghi789",
        "provider": "pagerduty",
        "scopes": ["read", "write", "incidents"],
    },
    "stripe": {
        "connection_id": "con_stripe_jkl012",
        "provider": "stripe",
        "scopes": ["read_only"],
    },
    "slack": {
        "connection_id": "con_slack_mno345",
        "provider": "slack",
        "scopes": ["chat:write", "channels:read", "users:read"],
    },
}

MOCK_TOKENS = {
    "github": "gho_SentinelVault_k8sMonitor_2026Q1_xR9mT4",
    "datadog": "ddtok_SentinelVault_metricsRead_live_7Yp3Qw",
    "pagerduty": "pdkey_SentinelVault_incidentMgmt_a1B2c3",
    "stripe": "sk_live_SentinelVault_readOnly_4dE5fG",
    "slack": "xoxb-SentinelVault-botToken-h6I7jK8lM",
}


@dataclass
class TokenEntry:
    """Cached token with expiry tracking."""

    service: str
    access_token: str
    scopes: list[str]
    issued_at: float
    expires_in: int = 3600  # seconds

    @property
    def is_expired(self) -> bool:
        return time.time() > self.issued_at + self.expires_in


class TokenVault:
    """Auth0 Token Vault — federated token exchange for third-party services.

    When Auth0 credentials are configured, it uses the Management API's
    ``/api/v2/users/{user_id}/tokens`` endpoint (Token Vault) to obtain
    federated tokens.  When credentials are absent it returns realistic
    mock tokens so the demo works without a paid Auth0 tenant.
    """

    def __init__(self) -> None:
        self._cache: dict[str, TokenEntry] = {}
        self._mgmt_token: Optional[str] = None
        self._mgmt_token_expires: float = 0.0
        self.is_live = bool(AUTH0_DOMAIN and AUTH0_CLIENT_ID and AUTH0_CLIENT_SECRET)

        if self.is_live:
            logger.info("TokenVault: Auth0 credentials detected — using live Token Vault")
        else:
            logger.info("TokenVault: No Auth0 credentials — using mock tokens for demo")

    # ------------------------------------------------------------------
    # Management API token (needed to call Token Vault endpoints)
    # ------------------------------------------------------------------

    def _get_mgmt_token(self) -> str:
        """Obtain or return cached Auth0 Management API token."""
        if self._mgmt_token and time.time() < self._mgmt_token_expires:
            return self._mgmt_token

        resp = requests.post(
            f"https://{AUTH0_DOMAIN}/oauth/token",
            json={
                "client_id": AUTH0_CLIENT_ID,
                "client_secret": AUTH0_CLIENT_SECRET,
                "audience": f"https://{AUTH0_DOMAIN}/api/v2/",
                "grant_type": "client_credentials",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._mgmt_token = data["access_token"]
        self._mgmt_token_expires = time.time() + data.get("expires_in", 86400) - 60
        return self._mgmt_token

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_token(self, service: str, scopes: Optional[list[str]] = None) -> dict:
        """Retrieve a federated access token for *service*.

        Args:
            service: Third-party provider name (github, datadog, …).
            scopes: Optional scope override.

        Returns:
            dict with ``access_token``, ``service``, ``scopes``, ``source``.
        """
        # Return from cache if still valid
        cached = self._cache.get(service)
        if cached and not cached.is_expired:
            logger.debug("TokenVault: cache hit for %s", service)
            return {
                "access_token": cached.access_token,
                "service": service,
                "scopes": cached.scopes,
                "source": "cache",
            }

        if self.is_live:
            return self._fetch_live_token(service, scopes)
        return self._fetch_mock_token(service, scopes)

    def refresh_token(self, service: str) -> dict:
        """Force-refresh the token for *service* (evicts cache first)."""
        self._cache.pop(service, None)
        logger.info("TokenVault: force-refreshing token for %s", service)
        return self.get_token(service)

    def list_connections(self) -> list[dict]:
        """List all available Token Vault service connections."""
        if self.is_live:
            return self._list_live_connections()
        return [
            {"service": name, **meta}
            for name, meta in MOCK_CONNECTIONS.items()
        ]

    # ------------------------------------------------------------------
    # Live Auth0 implementation
    # ------------------------------------------------------------------

    def _fetch_live_token(self, service: str, scopes: Optional[list[str]]) -> dict:
        """Fetch a federated token from Auth0 Token Vault."""
        mgmt = self._get_mgmt_token()
        # Token Vault uses the federated token exchange endpoint
        resp = requests.post(
            f"https://{AUTH0_DOMAIN}/oauth/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "client_id": AUTH0_CLIENT_ID,
                "client_secret": AUTH0_CLIENT_SECRET,
                "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "subject_token": mgmt,
                "requested_token_type": f"urn:auth0:token-vault:{service}",
                "scope": " ".join(scopes) if scopes else "",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        entry = TokenEntry(
            service=service,
            access_token=data["access_token"],
            scopes=scopes or [],
            issued_at=time.time(),
            expires_in=data.get("expires_in", 3600),
        )
        self._cache[service] = entry
        logger.info("TokenVault: live token obtained for %s", service)
        return {
            "access_token": entry.access_token,
            "service": service,
            "scopes": entry.scopes,
            "source": "auth0_token_vault",
        }

    def _list_live_connections(self) -> list[dict]:
        mgmt = self._get_mgmt_token()
        resp = requests.get(
            f"https://{AUTH0_DOMAIN}/api/v2/connections",
            headers={"Authorization": f"Bearer {mgmt}"},
            params={"strategy": "oauth2"},
            timeout=10,
        )
        resp.raise_for_status()
        return [
            {
                "service": c.get("name"),
                "connection_id": c.get("id"),
                "provider": c.get("strategy"),
                "scopes": c.get("enabled_clients", []),
            }
            for c in resp.json()
        ]

    # ------------------------------------------------------------------
    # Mock implementation (demo / free-tier fallback)
    # ------------------------------------------------------------------

    def _fetch_mock_token(self, service: str, scopes: Optional[list[str]]) -> dict:
        """Return a realistic-looking mock token for demo purposes."""
        conn = MOCK_CONNECTIONS.get(service)
        token_str = MOCK_TOKENS.get(service, f"tok_sentinel_{service}_mock")
        resolved_scopes = scopes or (conn["scopes"] if conn else [])

        entry = TokenEntry(
            service=service,
            access_token=token_str,
            scopes=resolved_scopes,
            issued_at=time.time(),
            expires_in=3600,
        )
        self._cache[service] = entry
        logger.info("TokenVault: mock token issued for %s", service)
        return {
            "access_token": entry.access_token,
            "service": service,
            "scopes": entry.scopes,
            "source": "mock_vault",
        }
