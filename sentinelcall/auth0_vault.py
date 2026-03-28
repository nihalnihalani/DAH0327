"""Auth0 Token Vault — manages third-party API credentials through Auth0.

The agent never sees raw provider secrets. All tokens are fetched via Auth0's
Token Vault (federated token exchange), which exchanges an Auth0 access/refresh
token for a fresh external-provider access token.

Token Vault is built on OAuth 2.0 Token Exchange (RFC 8693) with an Auth0-specific
grant type for federated connection access tokens.

Ref: https://auth0.com/docs/secure/call-apis-on-users-behalf/token-vault/access-token-exchange-with-token-vault
Ref: https://auth0.com/ai/docs/intro/token-vault

Prerequisites (live mode):
- Token Vault enabled on the Auth0 tenant (available on paid plans; free tier includes 2 connected apps)
- External connections configured (e.g. google-oauth2, github, slack)
- Users have completed the Connected Accounts flow (so Auth0 stores their provider tokens)
- A Custom API Client with the Token Vault grant type enabled
- Refresh token rotation DISABLED (Token Vault does not support it)

Falls back to realistic mock tokens when Auth0 is not configured or Token Vault
is unavailable on the current plan.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import requests

from sentinelcall.config import AUTH0_DOMAIN, AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token Vault constants (from Auth0 docs)
# ---------------------------------------------------------------------------
TOKEN_VAULT_GRANT_TYPE = (
    "urn:auth0:params:oauth:grant-type:token-exchange:federated-connection-access-token"
)
SUBJECT_TOKEN_TYPE_ACCESS = "urn:ietf:params:oauth:token-type:access_token"
SUBJECT_TOKEN_TYPE_REFRESH = "urn:ietf:params:oauth:token-type:refresh_token"
REQUESTED_TOKEN_TYPE = "http://auth0.com/oauth/token-type/federated-connection-access-token"

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
    "google-oauth2": {
        "connection_id": "con_google_pqr678",
        "provider": "google-oauth2",
        "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
    },
}

MOCK_TOKENS = {
    "github": "gho_SentinelVault_k8sMonitor_2026Q1_xR9mT4",
    "datadog": "ddtok_SentinelVault_metricsRead_live_7Yp3Qw",
    "pagerduty": "pdkey_SentinelVault_incidentMgmt_a1B2c3",
    "stripe": "sk_live_SentinelVault_readOnly_4dE5fG",
    "slack": "xoxb-SentinelVault-botToken-h6I7jK8lM",
    "google-oauth2": "ya29.SentinelVault_googleCalendar_nO1pQ2",
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

    When Auth0 credentials are configured, it uses Token Vault's federated
    token exchange to swap an Auth0 access/refresh token for an external
    provider's access token.

    The exchange hits ``POST /oauth/token`` with:
    - ``grant_type``: ``urn:auth0:params:oauth:grant-type:token-exchange:federated-connection-access-token``
    - ``subject_token``: a valid Auth0 access or refresh token
    - ``subject_token_type``: ``urn:ietf:params:oauth:token-type:access_token`` or ``...refresh_token``
    - ``requested_token_type``: ``http://auth0.com/oauth/token-type/federated-connection-access-token``
    - ``connection``: the Auth0 connection name (e.g. ``google-oauth2``, ``github``)

    When credentials are absent it returns realistic mock tokens so the demo
    works without a paid Auth0 tenant.
    """

    def __init__(self) -> None:
        self._cache: dict[str, TokenEntry] = {}
        self._mgmt_token: Optional[str] = None
        self._mgmt_token_expires: float = 0.0
        # subject_token is set externally (e.g. from a user's Auth0 session)
        self._subject_token: Optional[str] = None
        self._subject_token_type: str = SUBJECT_TOKEN_TYPE_ACCESS
        self.is_live = bool(AUTH0_DOMAIN and AUTH0_CLIENT_ID and AUTH0_CLIENT_SECRET)

        if self.is_live:
            logger.info("TokenVault: Auth0 credentials detected — will attempt live Token Vault")
        else:
            logger.info("TokenVault: No Auth0 credentials — using mock tokens for demo")

    def set_subject_token(
        self,
        token: str,
        token_type: str = SUBJECT_TOKEN_TYPE_ACCESS,
    ) -> None:
        """Set the Auth0 access/refresh token to use for federated exchange.

        In a real deployment, this comes from the user's Auth0 session (e.g.
        after CIBA approval or standard login).  For M2M (machine-to-machine)
        flows, the agent can use a client_credentials token.

        Args:
            token: A valid Auth0 access_token or refresh_token.
            token_type: One of SUBJECT_TOKEN_TYPE_ACCESS or SUBJECT_TOKEN_TYPE_REFRESH.
        """
        self._subject_token = token
        self._subject_token_type = token_type
        logger.debug("TokenVault: subject_token set (type=%s)", token_type)

    # ------------------------------------------------------------------
    # Management API token (for listing connections)
    # ------------------------------------------------------------------

    def _get_mgmt_token(self) -> str:
        """Obtain or return cached Auth0 Management API token (client_credentials)."""
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
            service: Auth0 connection name (e.g. ``github``, ``google-oauth2``,
                     ``slack``).  This maps to the ``connection`` parameter in
                     the Token Vault exchange.
            scopes: Optional — not used in Token Vault exchange (scopes are
                    determined by the connection config), but kept for the
                    mock fallback.

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
        """List all available service connections.

        In live mode, queries the Auth0 Management API for configured
        social/enterprise connections.  In demo mode, returns mock connections.
        """
        if self.is_live:
            return self._list_live_connections()
        return [
            {"service": name, **meta}
            for name, meta in MOCK_CONNECTIONS.items()
        ]

    # ------------------------------------------------------------------
    # Live Auth0 Token Vault implementation
    # ------------------------------------------------------------------

    def _fetch_live_token(self, service: str, scopes: Optional[list[str]]) -> dict:
        """Fetch a federated token from Auth0 Token Vault.

        POST /oauth/token with the Token Vault grant type.  If no subject_token
        is set, falls back to using an M2M (client_credentials) token as the
        subject.
        """
        subject_token = self._subject_token
        subject_token_type = self._subject_token_type

        # If no subject_token has been set, obtain an M2M token and use that.
        # This works for M2M flows; for user-delegated flows the caller should
        # call set_subject_token() with the user's Auth0 token first.
        if not subject_token:
            logger.info(
                "TokenVault: no subject_token set — obtaining M2M token for exchange"
            )
            try:
                subject_token = self._get_mgmt_token()
            except requests.RequestException as exc:
                logger.warning(
                    "TokenVault: failed to obtain M2M token for %s — "
                    "falling back to mock. Error: %s",
                    service,
                    exc,
                )
                return self._fetch_mock_token(service, scopes)
            subject_token_type = SUBJECT_TOKEN_TYPE_ACCESS

        payload = {
            "grant_type": TOKEN_VAULT_GRANT_TYPE,
            "client_id": AUTH0_CLIENT_ID,
            "client_secret": AUTH0_CLIENT_SECRET,
            "subject_token": subject_token,
            "subject_token_type": subject_token_type,
            "requested_token_type": REQUESTED_TOKEN_TYPE,
            "connection": service,
        }

        try:
            resp = requests.post(
                f"https://{AUTH0_DOMAIN}/oauth/token",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
            )
            resp.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            logger.warning(
                "TokenVault: Token Vault exchange failed for %s (HTTP %d) — "
                "falling back to mock. Token Vault may not be enabled or "
                "the connection '%s' may not be configured. Error: %s",
                service,
                status,
                service,
                exc,
            )
            return self._fetch_mock_token(service, scopes)
        except requests.RequestException as exc:
            logger.warning(
                "TokenVault: request failed for %s — falling back to mock. Error: %s",
                service,
                exc,
            )
            return self._fetch_mock_token(service, scopes)

        data = resp.json()
        token_scopes = data.get("scope", "").split() if data.get("scope") else (scopes or [])

        entry = TokenEntry(
            service=service,
            access_token=data["access_token"],
            scopes=token_scopes,
            issued_at=time.time(),
            expires_in=data.get("expires_in", 3600),
        )
        self._cache[service] = entry
        logger.info("TokenVault: live token obtained for %s", service)
        return {
            "access_token": entry.access_token,
            "service": service,
            "scopes": entry.scopes,
            "issued_token_type": data.get("issued_token_type", REQUESTED_TOKEN_TYPE),
            "source": "auth0_token_vault",
        }

    def _list_live_connections(self) -> list[dict]:
        """List connections from Auth0 Management API."""
        try:
            mgmt = self._get_mgmt_token()
            resp = requests.get(
                f"https://{AUTH0_DOMAIN}/api/v2/connections",
                headers={"Authorization": f"Bearer {mgmt}"},
                params={"strategy": "oauth2", "per_page": 50},
                timeout=10,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning(
                "TokenVault: failed to list connections — returning mock list. Error: %s",
                exc,
            )
            return [
                {"service": name, **meta}
                for name, meta in MOCK_CONNECTIONS.items()
            ]

        return [
            {
                "service": c.get("name"),
                "connection_id": c.get("id"),
                "provider": c.get("strategy"),
                "enabled_clients": c.get("enabled_clients", []),
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
