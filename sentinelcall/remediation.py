"""Remediation executor for Pager0.

Executes remediation actions after CIBA approval. Supports two backends:
1. GitHub Actions -- triggers a rollback workflow dispatch
2. Generic Webhook -- POSTs incident context to a webhook URL

If neither is configured, logs clearly and returns a 'not_configured' status.
"""

import hashlib
import hmac
import json
import logging
from typing import Any

import requests

from sentinelcall.config import (
    GITHUB_REPO,
    GITHUB_TOKEN,
    GITHUB_ROLLBACK_WORKFLOW_ID,
    REMEDIATION_WEBHOOK_URL,
    REMEDIATION_WEBHOOK_SECRET,
)

logger = logging.getLogger(__name__)


class RemediationExecutor:
    """Executes remediation actions after CIBA approval."""

    def __init__(self) -> None:
        self._github_configured = bool(GITHUB_ROLLBACK_WORKFLOW_ID and GITHUB_TOKEN and GITHUB_REPO)
        self._webhook_configured = bool(REMEDIATION_WEBHOOK_URL)

        if self._github_configured:
            logger.info("Remediation backend: GitHub Actions (repo=%s, workflow=%s)", GITHUB_REPO, GITHUB_ROLLBACK_WORKFLOW_ID)
        elif self._webhook_configured:
            logger.info("Remediation backend: Generic Webhook (url=%s)", REMEDIATION_WEBHOOK_URL)
        else:
            logger.info("Remediation backend: not configured (set GITHUB_ROLLBACK_WORKFLOW_ID or REMEDIATION_WEBHOOK_URL)")

    @property
    def is_configured(self) -> bool:
        """True if at least one remediation backend is available."""
        return self._github_configured or self._webhook_configured

    def execute(
        self,
        incident: dict[str, Any],
        diagnosis: dict[str, Any] | str,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        """Run the remediation action.

        Tries GitHub Actions first, then generic webhook. Returns a result dict
        with at least a ``status`` key.
        """
        if self._github_configured:
            return self._execute_github(incident, diagnosis, access_token)
        if self._webhook_configured:
            return self._execute_webhook(incident, diagnosis, access_token)

        return {
            "status": "not_configured",
            "message": "No remediation backend configured. Set GITHUB_ROLLBACK_WORKFLOW_ID or REMEDIATION_WEBHOOK_URL in .env",
        }

    def get_status(self) -> dict[str, Any]:
        """Return which backend is configured."""
        return {
            "github_configured": self._github_configured,
            "webhook_configured": self._webhook_configured,
            "active_backend": (
                "github" if self._github_configured
                else "webhook" if self._webhook_configured
                else "none"
            ),
        }

    # ------------------------------------------------------------------
    # Private backend implementations
    # ------------------------------------------------------------------

    def _execute_github(
        self,
        incident: dict[str, Any],
        diagnosis: dict[str, Any] | str,
        access_token: str | None,
    ) -> dict[str, Any]:
        """Trigger a GitHub Actions rollback workflow dispatch."""
        url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{GITHUB_ROLLBACK_WORKFLOW_ID}/dispatches"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {access_token or GITHUB_TOKEN}",
        }
        payload = {
            "ref": "main",
            "inputs": {
                "incident_id": incident.get("incident_id", "unknown"),
                "service": incident.get("service", "unknown"),
                "action": incident.get("recommended_action", "rollback"),
            },
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            if resp.status_code == 204:
                logger.info("GitHub Actions workflow dispatched for incident %s", incident.get("incident_id"))
                return {
                    "status": "dispatched",
                    "backend": "github",
                    "repo": GITHUB_REPO,
                    "workflow_id": GITHUB_ROLLBACK_WORKFLOW_ID,
                    "incident_id": incident.get("incident_id"),
                }
            else:
                logger.warning("GitHub Actions dispatch failed: %s %s", resp.status_code, resp.text[:200])
                return {
                    "status": "error",
                    "backend": "github",
                    "http_status": resp.status_code,
                    "message": resp.text[:200],
                }
        except requests.RequestException as exc:
            logger.error("GitHub Actions dispatch request failed: %s", exc)
            return {
                "status": "error",
                "backend": "github",
                "message": str(exc),
            }

    def _execute_webhook(
        self,
        incident: dict[str, Any],
        diagnosis: dict[str, Any] | str,
        access_token: str | None,
    ) -> dict[str, Any]:
        """POST incident context to a generic webhook URL."""
        body = {
            "incident": incident,
            "diagnosis": diagnosis,
            "access_token_present": access_token is not None,
        }
        body_bytes = json.dumps(body, default=str).encode()

        headers = {"Content-Type": "application/json"}
        if REMEDIATION_WEBHOOK_SECRET:
            sig = hmac.new(
                REMEDIATION_WEBHOOK_SECRET.encode(),
                body_bytes,
                hashlib.sha256,
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={sig}"

        try:
            resp = requests.post(
                REMEDIATION_WEBHOOK_URL,
                data=body_bytes,
                headers=headers,
                timeout=15,
            )
            logger.info(
                "Remediation webhook response: %s %s",
                resp.status_code, resp.text[:200],
            )
            return {
                "status": "sent",
                "backend": "webhook",
                "http_status": resp.status_code,
                "url": REMEDIATION_WEBHOOK_URL,
            }
        except requests.RequestException as exc:
            logger.error("Remediation webhook request failed: %s", exc)
            return {
                "status": "error",
                "backend": "webhook",
                "message": str(exc),
            }
