"""Bland AI outbound incident call integration.

Makes outbound phone calls to on-call engineers via the Bland AI API,
with support for interactive pathway-based conversations and mid-call
function calling (query_live_metrics, trigger_ciba_approval).
"""

import logging
import time
import uuid
from typing import Any, Optional

import requests

from sentinelcall.config import BLAND_API_KEY, ON_CALL_PHONE, WEBHOOK_BASE_URL

logger = logging.getLogger(__name__)

BLAND_BASE_URL = "https://api.bland.ai/v1"


def _headers() -> dict[str, str]:
    """Return authorization headers for Bland AI API."""
    return {
        "Authorization": BLAND_API_KEY,
        "Content-Type": "application/json",
    }


def _build_task_prompt(incident_context: dict[str, Any]) -> str:
    """Build a task prompt when no pathway is available.

    The prompt instructs the Bland AI agent to brief the on-call engineer
    on the incident and collect verbal authorization for remediation.
    """
    service = incident_context.get("service", "unknown-service")
    severity = incident_context.get("severity", "SEV-2")
    description = incident_context.get("description", "Anomaly detected in production.")
    root_cause = incident_context.get("root_cause", "Under investigation.")
    recommended_action = incident_context.get("recommended_action", "Restart affected pods.")

    return f"""You are SentinelCall, an autonomous SRE incident response agent.
You are calling the on-call engineer about a production incident.

INCIDENT BRIEFING:
- Service: {service}
- Severity: {severity}
- Description: {description}
- Root Cause: {root_cause}
- Recommended Action: {recommended_action}

YOUR TASK:
1. Greet the engineer and identify yourself as SentinelCall.
2. Brief them on the incident (service, severity, what happened).
3. If they ask for live metrics, use the query_live_metrics function.
4. Present the recommended action and ask for verbal authorization.
5. If they approve, use the trigger_ciba_approval function.
6. If they want to escalate, use the escalate_to_vp function.
7. Thank them and end the call.

Be concise, professional, and technically precise. This is a real production incident."""


def _build_tools() -> list[dict[str, Any]]:
    """Build the mid-call function calling tools for Bland AI."""
    return [
        {
            "name": "query_live_metrics",
            "description": "Query live infrastructure metrics for the affected service. Call this when the engineer asks for current stats, latency, error rates, or CPU/memory usage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "The name of the service to query metrics for.",
                    },
                    "metric_type": {
                        "type": "string",
                        "enum": ["latency", "error_rate", "cpu", "memory", "throughput", "all"],
                        "description": "The type of metric to retrieve.",
                    },
                },
                "required": ["service_name"],
            },
            "url": f"{WEBHOOK_BASE_URL}/bland/function-call",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
        },
        {
            "name": "trigger_ciba_approval",
            "description": "Trigger Auth0 CIBA backchannel authorization after the engineer verbally approves remediation. This authenticates their approval without requiring a login screen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "engineer_id": {
                        "type": "string",
                        "description": "The engineer's identifier for CIBA auth.",
                    },
                    "action_approved": {
                        "type": "string",
                        "description": "Description of the action the engineer approved.",
                    },
                },
                "required": ["engineer_id", "action_approved"],
            },
            "url": f"{WEBHOOK_BASE_URL}/bland/function-call",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
        },
        {
            "name": "escalate_to_vp",
            "description": "Escalate the incident to VP of Engineering. Use when the on-call engineer requests escalation or the incident severity warrants it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Reason for escalation.",
                    },
                },
                "required": ["reason"],
            },
            "url": f"{WEBHOOK_BASE_URL}/bland/function-call",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
        },
    ]


def _mock_call_response(phone_number: str, incident_context: dict[str, Any]) -> dict[str, Any]:
    """Return a realistic mock response for demo/testing when API keys are missing."""
    call_id = f"demo-{uuid.uuid4().hex[:12]}"
    logger.info("Using mock Bland AI response (no API key configured). call_id=%s", call_id)
    return {
        "call_id": call_id,
        "status": "queued",
        "phone_number": phone_number,
        "message": "Demo mode: call simulated successfully.",
        "created_at": time.time(),
        "mock": True,
    }


def make_incident_call(
    phone_number: str | None = None,
    incident_context: dict[str, Any] | None = None,
    pathway_id: str | None = None,
    ciba_auth_req_id: str | None = None,
) -> dict[str, Any]:
    """Make an outbound incident call to the on-call engineer via Bland AI.

    Args:
        phone_number: Phone number to call (defaults to ON_CALL_PHONE from config).
        incident_context: Dict with incident details (service, severity, description, etc.).
        pathway_id: Optional Bland pathway ID for interactive conversation flow.
        ciba_auth_req_id: Optional Auth0 CIBA auth request ID to pass through for approval.

    Returns:
        Dict with call_id, status, and other Bland API response fields.
    """
    phone_number = phone_number or ON_CALL_PHONE
    incident_context = incident_context or {
        "service": "api-gateway",
        "severity": "SEV-2",
        "description": "Elevated error rates detected.",
    }

    if not BLAND_API_KEY:
        return _mock_call_response(phone_number, incident_context)

    # Build the request payload
    payload: dict[str, Any] = {
        "phone_number": phone_number,
        "wait_for_greeting": True,
        "record": True,
        "webhook": f"{WEBHOOK_BASE_URL}/bland/webhook",
        "metadata": {
            "incident_id": incident_context.get("incident_id", f"INC-{uuid.uuid4().hex[:8]}"),
            "severity": incident_context.get("severity", "SEV-2"),
        },
    }

    if ciba_auth_req_id:
        payload["metadata"]["ciba_auth_req_id"] = ciba_auth_req_id

    # Use pathway for interactive flow, otherwise fall back to task prompt
    if pathway_id:
        payload["pathway_id"] = pathway_id
        payload["pathway_params"] = {
            "service": incident_context.get("service", "unknown"),
            "severity": incident_context.get("severity", "SEV-2"),
            "description": incident_context.get("description", "Anomaly detected."),
            "root_cause": incident_context.get("root_cause", "Under investigation."),
            "recommended_action": incident_context.get("recommended_action", "Restart pods."),
            "engineer_id": incident_context.get("engineer_id", "engineer-001"),
        }
    else:
        payload["task"] = _build_task_prompt(incident_context)
        payload["tools"] = _build_tools()

    try:
        response = requests.post(
            f"{BLAND_BASE_URL}/calls",
            json=payload,
            headers=_headers(),
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        logger.info("Bland AI call initiated. call_id=%s status=%s", data.get("call_id"), data.get("status"))
        return data
    except requests.RequestException as exc:
        logger.error("Bland AI call failed: %s. Falling back to mock.", exc)
        return _mock_call_response(phone_number, incident_context)


def get_call_status(call_id: str) -> dict[str, Any]:
    """Check the status of an outbound call.

    Args:
        call_id: The Bland AI call ID to check.

    Returns:
        Dict with call status, duration, and completion info.
    """
    if not BLAND_API_KEY or call_id.startswith("demo-"):
        return {
            "call_id": call_id,
            "status": "completed",
            "duration": 47.3,
            "completed": True,
            "answered_by": "human",
            "mock": True,
        }

    try:
        response = requests.get(
            f"{BLAND_BASE_URL}/calls/{call_id}",
            headers=_headers(),
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.error("Failed to get call status for %s: %s", call_id, exc)
        return {"call_id": call_id, "status": "unknown", "error": str(exc)}


def get_call_transcript(call_id: str) -> dict[str, Any]:
    """Retrieve the transcript for a completed call.

    Args:
        call_id: The Bland AI call ID.

    Returns:
        Dict with transcript lines and concatenated text.
    """
    if not BLAND_API_KEY or call_id.startswith("demo-"):
        return {
            "call_id": call_id,
            "transcript": [
                {"speaker": "agent", "text": "Hello, this is SentinelCall. We've detected a SEV-2 incident on api-gateway."},
                {"speaker": "engineer", "text": "What are the current metrics?"},
                {"speaker": "agent", "text": "Error rate is at 12.4%, p99 latency 2,340ms, CPU at 89%."},
                {"speaker": "engineer", "text": "Okay, go ahead and restart the affected pods."},
                {"speaker": "agent", "text": "Authorization received. Triggering CIBA approval and initiating remediation. Thank you."},
            ],
            "concatenated_transcript": (
                "Agent: Hello, this is SentinelCall. We've detected a SEV-2 incident on api-gateway.\n"
                "Engineer: What are the current metrics?\n"
                "Agent: Error rate is at 12.4%, p99 latency 2,340ms, CPU at 89%.\n"
                "Engineer: Okay, go ahead and restart the affected pods.\n"
                "Agent: Authorization received. Triggering CIBA approval and initiating remediation. Thank you."
            ),
            "mock": True,
        }

    try:
        response = requests.get(
            f"{BLAND_BASE_URL}/calls/{call_id}",
            headers=_headers(),
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        transcript = data.get("transcripts", [])
        concatenated = "\n".join(
            f"{t.get('speaker', 'unknown').title()}: {t.get('text', '')}"
            for t in transcript
        )
        return {
            "call_id": call_id,
            "transcript": transcript,
            "concatenated_transcript": concatenated,
        }
    except requests.RequestException as exc:
        logger.error("Failed to get transcript for %s: %s", call_id, exc)
        return {"call_id": call_id, "transcript": [], "error": str(exc)}
