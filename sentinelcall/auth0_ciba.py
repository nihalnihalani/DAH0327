"""Auth0 CIBA (Client-Initiated Backchannel Authentication) — phone call IS the auth.

The SentinelCall agent initiates a CIBA authorization request when it needs an
engineer's approval for a remediation action.  The Bland AI phone call acts as
the out-of-band authentication channel: when the engineer verbally approves,
the Bland webhook calls ``complete_ciba_from_voice`` to exchange the
``auth_req_id`` for an access token.

Falls back to a simulated flow when Auth0 CIBA is not available (free tier).
"""

import time
import uuid
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import requests

from sentinelcall.config import AUTH0_DOMAIN, AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET

logger = logging.getLogger(__name__)


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

    @property
    def is_expired(self) -> bool:
        return time.time() > self.created_at + self.expires_in


class CIBAManager:
    """Manages CIBA backchannel authorization flows.

    Live mode: POSTs to Auth0 ``/bc-authorize`` and polls / exchanges tokens
    via ``/oauth/token`` with grant_type ``urn:openid:params:grant-type:ciba``.

    Demo mode: simulates the entire flow with realistic payloads and timing.
    """

    def __init__(self) -> None:
        self._requests: dict[str, CIBARequest] = {}
        self.is_live = bool(AUTH0_DOMAIN and AUTH0_CLIENT_ID and AUTH0_CLIENT_SECRET)

        if self.is_live:
            logger.info("CIBAManager: Auth0 credentials detected — using live CIBA")
        else:
            logger.info("CIBAManager: No Auth0 credentials — using simulated CIBA flow")

    # ------------------------------------------------------------------
    # Initiate
    # ------------------------------------------------------------------

    def initiate_ciba_approval(self, engineer_id: str, action: str) -> dict:
        """Start a CIBA authorization request.

        Args:
            engineer_id: Login hint identifying the on-call engineer.
            action: Human-readable description of the remediation action
                    (e.g. "Roll back deployment v2.3.1 on prod-api-cluster").

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

    def _initiate_live(self, engineer_id: str, action: str) -> dict:
        resp = requests.post(
            f"https://{AUTH0_DOMAIN}/bc-authorize",
            json={
                "client_id": AUTH0_CLIENT_ID,
                "client_secret": AUTH0_CLIENT_SECRET,
                "login_hint": f"eng:{engineer_id}",
                "scope": "openid profile remediation:approve",
                "binding_message": action[:128],  # CIBA spec limits binding_message
                "requested_expiry": 300,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        auth_req_id = data["auth_req_id"]
        self._requests[auth_req_id] = CIBARequest(
            auth_req_id=auth_req_id,
            engineer_id=engineer_id,
            action=action,
            expires_in=data.get("expires_in", 300),
        )
        logger.info("CIBAManager: live CIBA initiated — auth_req_id=%s", auth_req_id)
        return {
            "auth_req_id": auth_req_id,
            "expires_in": data.get("expires_in", 300),
            "interval": data.get("interval", 5),
            "status": "pending",
            "source": "auth0_ciba",
        }

    def _complete_live(self, auth_req_id: str) -> dict:
        resp = requests.post(
            f"https://{AUTH0_DOMAIN}/oauth/token",
            json={
                "client_id": AUTH0_CLIENT_ID,
                "client_secret": AUTH0_CLIENT_SECRET,
                "grant_type": "urn:openid:params:grant-type:ciba",
                "auth_req_id": auth_req_id,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        req = self._requests.get(auth_req_id)
        if req:
            req.status = ApprovalStatus.APPROVED
            req.access_token = data["access_token"]

        logger.info("CIBAManager: live CIBA completed — auth_req_id=%s", auth_req_id)
        return {
            "auth_req_id": auth_req_id,
            "access_token": data["access_token"],
            "token_type": data.get("token_type", "Bearer"),
            "expires_in": data.get("expires_in", 3600),
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
