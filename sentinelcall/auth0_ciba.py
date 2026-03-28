"""Auth0 CIBA (Client-Initiated Backchannel Authentication) — phone call IS the auth.

The Pager0 agent initiates a CIBA authorization request when it needs an
engineer's approval for a remediation action.  The Bland AI phone call acts as
the out-of-band authentication channel: when the engineer verbally approves,
the Bland webhook calls ``complete_ciba_from_voice`` to exchange the
``auth_req_id`` for an access token.

Auth0 CIBA requires an **Enterprise plan** with CIBA enabled, plus users enrolled
in Auth0 Guardian MFA (push notifications).  When those prerequisites are not met,
the manager falls back to a realistic simulated flow suitable for demos.

Ref: https://auth0.com/docs/get-started/authentication-and-authorization-flow/client-initiated-backchannel-authentication-flow
Ref: https://auth0.com/docs/get-started/authentication-and-authorization-flow/client-initiated-backchannel-authentication-flow/user-authorization-with-ciba
"""

import json
import time
import uuid
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import requests

from sentinelcall.config import AUTH0_DOMAIN, AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CIBA constants (from Auth0 + OpenID Connect CIBA spec)
# ---------------------------------------------------------------------------
CIBA_GRANT_TYPE = "urn:openid:params:grant-type:ciba"

# /bc-authorize uses application/x-www-form-urlencoded per the CIBA spec
BC_AUTHORIZE_CONTENT_TYPE = "application/x-www-form-urlencoded"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


@dataclass
class CIBARequest:
    """Tracks a single CIBA authorization request."""

    auth_req_id: str
    engineer_id: str
    action: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    access_token: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    expires_in: int = 300  # 5-minute window for voice approval
    interval: int = 5  # polling interval in seconds

    @property
    def is_expired(self) -> bool:
        return time.time() > self.created_at + self.expires_in


class CIBAManager:
    """Manages CIBA backchannel authorization flows.

    Live mode
    ---------
    POSTs to Auth0 ``/bc-authorize`` (form-encoded) and polls ``/oauth/token``
    with ``grant_type=urn:openid:params:grant-type:ciba``.

    Auth0 CIBA requires:
    * Enterprise plan with CIBA enabled
    * Users enrolled in Auth0 Guardian MFA (push notifications) or CIBA email enabled
    * An ``audience`` configured for the API

    Demo mode
    ---------
    Simulates the entire flow with realistic payloads and timing when Auth0
    credentials are absent or CIBA is unavailable on the current plan.
    """

    def __init__(self, audience: str = "") -> None:
        self._requests: dict[str, CIBARequest] = {}
        self._audience = audience
        self.is_live = bool(AUTH0_DOMAIN and AUTH0_CLIENT_ID and AUTH0_CLIENT_SECRET)

        if self.is_live:
            logger.info("CIBAManager: Auth0 credentials detected — will attempt live CIBA")
            logger.info(
                "CIBAManager: NOTE — CIBA requires Enterprise plan + Guardian MFA enrollment. "
                "If /bc-authorize returns 403/404, the manager will fall back to simulation."
            )
        else:
            logger.info("CIBAManager: No Auth0 credentials — using simulated CIBA flow")

    # ------------------------------------------------------------------
    # Initiate
    # ------------------------------------------------------------------

    def initiate_ciba_approval(self, engineer_id: str, action: str) -> dict:
        """Start a CIBA authorization request.

        Args:
            engineer_id: Auth0 user_id (``auth0|abc123``) or email of the on-call
                         engineer.  This is used as the ``sub`` in the login_hint.
            action: Human-readable description of the remediation action
                    (e.g. "Roll back deployment v2.3.1 on prod-api-cluster").
                    Shown as the binding_message on the engineer's device.

        Returns:
            dict with ``auth_req_id``, ``expires_in``, ``interval``, ``status``.
        """
        if self.is_live:
            return self._initiate_live(engineer_id, action)
        return self._initiate_simulated(engineer_id, action)

    # ------------------------------------------------------------------
    # Complete (called by Bland webhook on voice approval)
    # ------------------------------------------------------------------

    def complete_ciba_from_voice(self, auth_req_id: str) -> dict:
        """Exchange CIBA auth_req_id for an access token after voice approval.

        This is called by the Bland AI webhook handler when the engineer
        verbally approves the remediation action during the phone call.

        In live mode, this polls ``/oauth/token`` with the CIBA grant type.
        The token endpoint returns one of:
        - ``authorization_pending`` — keep polling
        - ``slow_down`` — increase interval
        - ``access_denied`` — engineer rejected
        - ``expired_token`` — request expired
        - success with ``access_token``

        Returns:
            dict with ``access_token``, ``token_type``, ``expires_in``, ``status``.
        """
        if self.is_live:
            return self._complete_live(auth_req_id)
        return self._complete_simulated(auth_req_id)

    # ------------------------------------------------------------------
    # Poll / Check
    # ------------------------------------------------------------------

    def check_approval_status(self, auth_req_id: str) -> dict:
        """Check the current status of a CIBA request.

        Returns:
            dict with ``auth_req_id``, ``status``, ``engineer_id``, ``action``,
            ``elapsed_seconds``.
        """
        req = self._requests.get(auth_req_id)
        if not req:
            return {"auth_req_id": auth_req_id, "status": "not_found"}

        if req.is_expired and req.status == ApprovalStatus.PENDING:
            req.status = ApprovalStatus.EXPIRED

        return {
            "auth_req_id": auth_req_id,
            "status": req.status.value,
            "engineer_id": req.engineer_id,
            "action": req.action,
            "elapsed_seconds": round(time.time() - req.created_at, 1),
        }

    def poll_token(self, auth_req_id: str) -> dict:
        """Poll Auth0 /oauth/token for CIBA completion (live mode only).

        In live mode, sends the CIBA grant_type to /oauth/token and interprets
        the response.  In demo mode, delegates to check_approval_status.

        Returns:
            dict with status and optionally access_token, or error details.
        """
        if not self.is_live:
            return self.check_approval_status(auth_req_id)

        try:
            resp = requests.post(
                f"https://{AUTH0_DOMAIN}/oauth/token",
                data={
                    "client_id": AUTH0_CLIENT_ID,
                    "client_secret": AUTH0_CLIENT_SECRET,
                    "grant_type": CIBA_GRANT_TYPE,
                    "auth_req_id": auth_req_id,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
            )

            if resp.status_code == 200:
                data = resp.json()
                req = self._requests.get(auth_req_id)
                if req:
                    req.status = ApprovalStatus.APPROVED
                    req.access_token = data.get("access_token")
                return {
                    "auth_req_id": auth_req_id,
                    "status": "approved",
                    "access_token": data.get("access_token"),
                    "id_token": data.get("id_token"),
                    "token_type": data.get("token_type", "Bearer"),
                    "expires_in": data.get("expires_in"),
                    "scope": data.get("scope"),
                    "source": "auth0_ciba",
                }

            # Handle expected polling responses
            error_data = resp.json()
            error_code = error_data.get("error", "unknown")

            if error_code == "authorization_pending":
                return {
                    "auth_req_id": auth_req_id,
                    "status": "pending",
                    "error": "authorization_pending",
                    "error_description": error_data.get("error_description", ""),
                }
            elif error_code == "slow_down":
                new_interval = error_data.get("interval", 10)
                req = self._requests.get(auth_req_id)
                if req:
                    req.interval = new_interval
                return {
                    "auth_req_id": auth_req_id,
                    "status": "pending",
                    "error": "slow_down",
                    "interval": new_interval,
                }
            elif error_code == "access_denied":
                req = self._requests.get(auth_req_id)
                if req:
                    req.status = ApprovalStatus.DENIED
                return {
                    "auth_req_id": auth_req_id,
                    "status": "denied",
                    "error": "access_denied",
                    "error_description": error_data.get("error_description", ""),
                }
            elif error_code == "expired_token":
                req = self._requests.get(auth_req_id)
                if req:
                    req.status = ApprovalStatus.EXPIRED
                return {
                    "auth_req_id": auth_req_id,
                    "status": "expired",
                    "error": "expired_token",
                }
            else:
                return {
                    "auth_req_id": auth_req_id,
                    "status": "error",
                    "error": error_code,
                    "error_description": error_data.get("error_description", ""),
                    "http_status": resp.status_code,
                }

        except requests.RequestException as exc:
            logger.error("CIBAManager: poll_token failed — %s", exc)
            return {
                "auth_req_id": auth_req_id,
                "status": "error",
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Demo helper
    # ------------------------------------------------------------------

    def simulate_approval(self, auth_req_id: str) -> dict:
        """For demo: instantly simulate a successful voice approval.

        Transitions the CIBA request to APPROVED and generates a mock
        access token — useful for live demos without a real phone call.
        """
        req = self._requests.get(auth_req_id)
        if not req:
            return {"error": "auth_req_id not found", "auth_req_id": auth_req_id}

        req.status = ApprovalStatus.APPROVED
        req.access_token = f"ciba_at_{uuid.uuid4().hex[:16]}"

        logger.info(
            "CIBAManager: simulated approval for %s (engineer=%s)",
            auth_req_id,
            req.engineer_id,
        )
        return {
            "auth_req_id": auth_req_id,
            "status": "approved",
            "access_token": req.access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "source": "simulated",
        }

    def list_requests(self) -> list[dict]:
        """Return all tracked CIBA requests (for dashboard display)."""
        return [self.check_approval_status(rid) for rid in self._requests]

    # ------------------------------------------------------------------
    # Live Auth0 CIBA
    # ------------------------------------------------------------------

    def _build_login_hint(self, engineer_id: str) -> str:
        """Build the login_hint JSON per Auth0 CIBA spec.

        Auth0 expects ``login_hint`` as a JSON-encoded string with:
        - ``format``: ``"iss_sub"``
        - ``iss``: ``"https://{domain}/"``
        - ``sub``: the Auth0 user_id (e.g. ``auth0|abc123``)

        Ref: https://auth0.com/docs/get-started/authentication-and-authorization-flow/client-initiated-backchannel-authentication-flow/user-authorization-with-ciba
        """
        return json.dumps({
            "format": "iss_sub",
            "iss": f"https://{AUTH0_DOMAIN}/",
            "sub": engineer_id,
        })

    def _initiate_live(self, engineer_id: str, action: str) -> dict:
        """POST to /bc-authorize to start a CIBA flow.

        Uses application/x-www-form-urlencoded (per CIBA spec, NOT JSON).
        """
        # binding_message: max 64 chars, alphanumeric + +-_.,:#
        binding_msg = action[:64]

        payload = {
            "client_id": AUTH0_CLIENT_ID,
            "client_secret": AUTH0_CLIENT_SECRET,
            "login_hint": self._build_login_hint(engineer_id),
            "scope": "openid",
            "binding_message": binding_msg,
        }
        if self._audience:
            payload["audience"] = self._audience

        try:
            resp = requests.post(
                f"https://{AUTH0_DOMAIN}/bc-authorize",
                data=payload,  # form-encoded, NOT json=
                headers={"Content-Type": BC_AUTHORIZE_CONTENT_TYPE},
                timeout=10,
            )
            resp.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            logger.warning(
                "CIBAManager: /bc-authorize returned HTTP %d — falling back to simulation. "
                "CIBA requires Enterprise plan + Guardian MFA enrollment. Error: %s",
                status,
                exc,
            )
            return self._initiate_simulated(engineer_id, action)
        except requests.RequestException as exc:
            logger.warning(
                "CIBAManager: /bc-authorize request failed — falling back to simulation. Error: %s",
                exc,
            )
            return self._initiate_simulated(engineer_id, action)

        data = resp.json()
        auth_req_id = data["auth_req_id"]
        expires_in = data.get("expires_in", 300)
        interval = data.get("interval", 5)

        self._requests[auth_req_id] = CIBARequest(
            auth_req_id=auth_req_id,
            engineer_id=engineer_id,
            action=action,
            expires_in=expires_in,
            interval=interval,
        )
        logger.info("CIBAManager: live CIBA initiated — auth_req_id=%s", auth_req_id)
        return {
            "auth_req_id": auth_req_id,
            "expires_in": expires_in,
            "interval": interval,
            "status": "pending",
            "source": "auth0_ciba",
        }

    def _complete_live(self, auth_req_id: str) -> dict:
        """Exchange auth_req_id for tokens via /oauth/token with CIBA grant type.

        Uses application/x-www-form-urlencoded (standard OAuth token endpoint).
        """
        try:
            resp = requests.post(
                f"https://{AUTH0_DOMAIN}/oauth/token",
                data={
                    "client_id": AUTH0_CLIENT_ID,
                    "client_secret": AUTH0_CLIENT_SECRET,
                    "grant_type": CIBA_GRANT_TYPE,
                    "auth_req_id": auth_req_id,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
            )
            resp.raise_for_status()
        except requests.HTTPError as exc:
            error_body = {}
            try:
                error_body = exc.response.json() if exc.response is not None else {}
            except ValueError:
                pass
            error_code = error_body.get("error", "unknown")

            # authorization_pending is expected during polling
            if error_code == "authorization_pending":
                return {
                    "auth_req_id": auth_req_id,
                    "status": "pending",
                    "error": "authorization_pending",
                    "error_description": error_body.get("error_description", ""),
                    "source": "auth0_ciba",
                }
            if error_code == "access_denied":
                req = self._requests.get(auth_req_id)
                if req:
                    req.status = ApprovalStatus.DENIED
                return {
                    "auth_req_id": auth_req_id,
                    "status": "denied",
                    "error": "access_denied",
                    "source": "auth0_ciba",
                }

            logger.warning(
                "CIBAManager: /oauth/token CIBA exchange failed — falling back to simulation. "
                "Error: %s, Body: %s",
                exc,
                error_body,
            )
            return self._complete_simulated(auth_req_id)
        except requests.RequestException as exc:
            logger.warning(
                "CIBAManager: /oauth/token request failed — falling back to simulation. Error: %s",
                exc,
            )
            return self._complete_simulated(auth_req_id)

        data = resp.json()
        req = self._requests.get(auth_req_id)
        if req:
            req.status = ApprovalStatus.APPROVED
            req.access_token = data.get("access_token")

        logger.info("CIBAManager: live CIBA completed — auth_req_id=%s", auth_req_id)
        return {
            "auth_req_id": auth_req_id,
            "access_token": data.get("access_token"),
            "id_token": data.get("id_token"),
            "token_type": data.get("token_type", "Bearer"),
            "expires_in": data.get("expires_in", 3600),
            "scope": data.get("scope"),
            "status": "approved",
            "source": "auth0_ciba",
        }

    # ------------------------------------------------------------------
    # Simulated CIBA (demo / free-tier fallback)
    # ------------------------------------------------------------------

    def _initiate_simulated(self, engineer_id: str, action: str) -> dict:
        auth_req_id = f"ciba_{uuid.uuid4().hex[:12]}"
        self._requests[auth_req_id] = CIBARequest(
            auth_req_id=auth_req_id,
            engineer_id=engineer_id,
            action=action,
        )
        logger.info(
            "CIBAManager: simulated CIBA initiated — auth_req_id=%s, engineer=%s",
            auth_req_id,
            engineer_id,
        )
        return {
            "auth_req_id": auth_req_id,
            "expires_in": 300,
            "interval": 5,
            "status": "pending",
            "source": "simulated",
        }

    def _complete_simulated(self, auth_req_id: str) -> dict:
        req = self._requests.get(auth_req_id)
        if not req:
            return {"error": "auth_req_id not found", "auth_req_id": auth_req_id}

        req.status = ApprovalStatus.APPROVED
        req.access_token = f"ciba_at_{uuid.uuid4().hex[:16]}"

        logger.info("CIBAManager: simulated CIBA completed — auth_req_id=%s", auth_req_id)
        return {
            "auth_req_id": auth_req_id,
            "access_token": req.access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "status": "approved",
            "source": "simulated",
        }
