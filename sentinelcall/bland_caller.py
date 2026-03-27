"""Bland AI outbound incident call integration.

Makes outbound phone calls to on-call engineers via the Bland AI API,
with support for interactive pathway-based conversations and mid-call
tool calling (query_live_metrics, trigger_ciba_approval, escalate_to_vp).

API reference: https://docs.bland.ai/api-v1/post/calls
"""

import logging
import time
import uuid
from typing import Any

import requests

from sentinelcall.config import BLAND_API_KEY, ON_CALL_PHONE, WEBHOOK_BASE_URL

logger = logging.getLogger(__name__)

BLAND_BASE_URL = "https://api.bland.ai/v1"


def _headers() -> dict[str, str]:
    """Return authorization headers for Bland AI API.

    Bland uses a lowercase ``authorization`` header with the raw API key
    (no "Bearer" prefix).  Ref: https://docs.bland.ai/api-v1/post/calls
    """
    return {
        "authorization": BLAND_API_KEY,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Task prompt (used when no pathway is registered)
# ---------------------------------------------------------------------------

def _build_task_prompt(incident_context: dict[str, Any]) -> str:
    """Build a task prompt when no pathway is available.

    The prompt instructs the Bland AI agent to brief the on-call engineer
    on the incident and collect verbal authorization for remediation.
    Max recommended length: 2,000 characters.
    """
    service = incident_context.get("service", "unknown-service")
    severity = incident_context.get("severity", "SEV-2")
    description = incident_context.get("description", "Anomaly detected in production.")
    root_cause = incident_context.get("root_cause", "Under investigation.")
    recommended_action = incident_context.get("recommended_action", "Restart affected pods.")

    return (
        "You are SentinelCall, an autonomous SRE incident response agent. "
        "You are calling the on-call engineer about a production incident.\n\n"
        "INCIDENT BRIEFING:\n"
        f"- Service: {service}\n"
        f"- Severity: {severity}\n"
        f"- Description: {description}\n"
        f"- Root Cause: {root_cause}\n"
        f"- Recommended Action: {recommended_action}\n\n"
        "YOUR TASK:\n"
        "1. Greet the engineer and identify yourself as SentinelCall.\n"
        "2. Brief them on the incident (service, severity, what happened).\n"
        "3. If they ask for live metrics, use the QueryLiveMetrics tool.\n"
        "4. Present the recommended action and ask for verbal authorization.\n"
        "5. If they approve, use the TriggerCIBAApproval tool.\n"
        "6. If they want to escalate, use the EscalateToVP tool.\n"
        "7. Thank them and end the call.\n\n"
        "Be concise, professional, and technically precise. This is a real production incident."
    )


# ---------------------------------------------------------------------------
# Custom tools (inline format for POST /v1/calls)
# ---------------------------------------------------------------------------

def _build_tools() -> list[dict[str, Any]]:
    """Build the mid-call custom tools for Bland AI.

    Each tool follows the Bland custom-tool schema:
      name, description, url, method, headers, body, input_schema, response, speech, timeout

    The AI agent decides when to invoke a tool based on its name and
    description combined with the conversation context.
    Ref: https://docs.bland.ai/tutorials/custom-tools
    """
    return [
        {
            "name": "QueryLiveMetrics",
            "description": (
                "Query live infrastructure metrics for the affected service. "
                "Call this when the engineer asks for current stats, latency, "
                "error rates, or CPU/memory usage."
            ),
            "url": f"{WEBHOOK_BASE_URL}/bland/function-call",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "body": {
                "name": "query_live_metrics",
                "call_id": "{{call_id}}",
                "parameters": {
                    "service_name": "{{input.service_name}}",
                    "metric_type": "{{input.metric_type}}",
                },
            },
            "input_schema": {
                "example": {
                    "service_name": "api-gateway",
                    "metric_type": "all",
                },
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "The name of the service to query metrics for.",
                    },
                    "metric_type": {
                        "type": "string",
                        "description": "The type of metric to retrieve: latency, error_rate, cpu, memory, throughput, or all.",
                    },
                },
                "required": ["service_name"],
            },
            "response": {
                "metrics_summary": "$.metrics",
                "status": "$.metrics.*.status",
            },
            "speech": "Let me pull up the live metrics for you now.",
            "timeout": 10000,
        },
        {
            "name": "TriggerCIBAApproval",
            "description": (
                "Trigger Auth0 CIBA backchannel authorization after the engineer "
                "verbally approves remediation. This authenticates their approval "
                "without requiring a login screen."
            ),
            "url": f"{WEBHOOK_BASE_URL}/bland/function-call",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "body": {
                "name": "trigger_ciba_approval",
                "call_id": "{{call_id}}",
                "parameters": {
                    "engineer_id": "{{input.engineer_id}}",
                    "action_approved": "{{input.action_approved}}",
                },
            },
            "input_schema": {
                "example": {
                    "engineer_id": "engineer-001",
                    "action_approved": "Restart affected pods",
                },
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
            "response": {
                "auth_status": "$.status",
                "auth_request_id": "$.auth_request_id",
            },
            "speech": "Recording your authorization now.",
            "timeout": 10000,
        },
        {
            "name": "EscalateToVP",
            "description": (
                "Escalate the incident to VP of Engineering. Use when the on-call "
                "engineer requests escalation or the incident severity warrants it."
            ),
            "url": f"{WEBHOOK_BASE_URL}/bland/function-call",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "body": {
                "name": "escalate_to_vp",
                "call_id": "{{call_id}}",
                "parameters": {
                    "reason": "{{input.reason}}",
                },
            },
            "input_schema": {
                "example": {
                    "reason": "Engineer requested VP involvement due to severity.",
                },
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Reason for escalation.",
                    },
                },
                "required": ["reason"],
            },
            "response": {
                "escalation_status": "$.status",
                "escalation_id": "$.escalation_id",
            },
            "speech": "Initiating escalation to VP of Engineering now.",
            "timeout": 10000,
        },
    ]


# ---------------------------------------------------------------------------
# Mock / demo fallback
# ---------------------------------------------------------------------------

def _mock_call_response(phone_number: str, incident_context: dict[str, Any]) -> dict[str, Any]:
    """Return a realistic mock response for demo/testing when API keys are missing."""
    call_id = f"demo-{uuid.uuid4().hex[:12]}"
    logger.info("[MOCK] Bland AI call simulated (no API key configured). call_id=%s", call_id)
    return {
        "status": "success",
        "message": "Demo mode: call simulated successfully.",
        "call_id": call_id,
        "batch_id": None,
        "mock": True,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def make_incident_call(
    phone_number: str | None = None,
    incident_context: dict[str, Any] | None = None,
    pathway_id: str | None = None,
    ciba_auth_req_id: str | None = None,
) -> dict[str, Any]:
    """Make an outbound incident call to the on-call engineer via Bland AI.

    Uses POST https://api.bland.ai/v1/calls.

    Either ``pathway_id`` (interactive pathway) or ``task`` (freeform prompt)
    is sent — they are mutually exclusive in the Bland API.

    Args:
        phone_number: E.164 phone number to call (defaults to ON_CALL_PHONE).
        incident_context: Dict with incident details (service, severity, etc.).
        pathway_id: Bland pathway ID for interactive conversation flow.
        ciba_auth_req_id: Auth0 CIBA auth request ID to embed in metadata.

    Returns:
        Dict with status, call_id, message, and batch_id from the Bland API.
    """
    phone_number = phone_number or ON_CALL_PHONE
    incident_context = incident_context or {
        "service": "api-gateway",
        "severity": "SEV-2",
        "description": "Elevated error rates detected.",
    }

    if not BLAND_API_KEY:
        return _mock_call_response(phone_number, incident_context)

    # Build the request payload per https://docs.bland.ai/api-v1/post/calls
    payload: dict[str, Any] = {
        "phone_number": phone_number,
        "voice": "Josh",
        "wait_for_greeting": True,
        "record": True,
        "max_duration": 5,
        "model": "base",
        "temperature": 0.4,
        "webhook": f"{WEBHOOK_BASE_URL}/bland/webhook",
        "metadata": {
            "incident_id": incident_context.get("incident_id", f"INC-{uuid.uuid4().hex[:8]}"),
            "severity": incident_context.get("severity", "SEV-2"),
            "source": "sentinelcall",
        },
    }

    if ciba_auth_req_id:
        payload["metadata"]["ciba_auth_req_id"] = ciba_auth_req_id

    # Pathway and task are mutually exclusive
    if pathway_id:
        payload["pathway_id"] = pathway_id
        # Pass incident context as request_data so pathway can use {{variable}} syntax
        payload["request_data"] = {
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
        # Provide incident data accessible via {{variable}} in task prompt
        payload["request_data"] = {
            "engineer_id": incident_context.get("engineer_id", "engineer-001"),
        }

    try:
        logger.info("[REAL] Sending Bland AI call to %s", phone_number)
        response = requests.post(
            f"{BLAND_BASE_URL}/calls",
            json=payload,
            headers=_headers(),
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") == "success":
            logger.info(
                "[REAL] Bland AI call queued. call_id=%s message=%s",
                data.get("call_id"),
                data.get("message"),
            )
        else:
            logger.warning("[REAL] Bland AI returned non-success: %s", data)

        return data
    except requests.RequestException as exc:
        logger.error("[REAL] Bland AI call failed: %s — falling back to mock.", exc)
        result = _mock_call_response(phone_number, incident_context)
        result["fallback_reason"] = str(exc)
        return result


def get_call_status(call_id: str) -> dict[str, Any]:
    """Retrieve detailed call information via GET /v1/calls/{call_id}.

    Returns status, call_length, answered_by, completed, transcripts, and more.
    Ref: https://docs.bland.ai/api-v1/get/calls-id
    """
    if not BLAND_API_KEY or call_id.startswith("demo-"):
        return {
            "call_id": call_id,
            "status": "completed",
            "completed": True,
            "call_length": 0.79,
            "answered_by": "human",
            "call_ended_by": "ASSISTANT",
            "summary": "SentinelCall briefed engineer on SEV-2 api-gateway incident. Engineer approved pod restart.",
            "mock": True,
        }

    try:
        logger.info("[REAL] Fetching call status for %s", call_id)
        response = requests.get(
            f"{BLAND_BASE_URL}/calls/{call_id}",
            headers=_headers(),
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.error("[REAL] Failed to get call status for %s: %s", call_id, exc)
        return {"call_id": call_id, "status": "unknown", "error": str(exc)}


def get_call_transcript(call_id: str) -> dict[str, Any]:
    """Retrieve the transcript for a completed call.

    The Bland API returns transcripts in the ``transcripts`` field as an array
    of objects with ``id``, ``created_at``, ``text``, and ``user`` (values:
    "user", "assistant", "robot", "agent-action").

    Args:
        call_id: The Bland AI call ID.

    Returns:
        Dict with call_id, transcripts array, and concatenated_transcript.
    """
    if not BLAND_API_KEY or call_id.startswith("demo-"):
        return {
            "call_id": call_id,
            "transcripts": [
                {"id": 1, "user": "assistant", "text": "Hello, this is SentinelCall. We've detected a SEV-2 incident on api-gateway.", "created_at": "2026-03-27T00:00:01Z"},
                {"id": 2, "user": "user", "text": "What are the current metrics?", "created_at": "2026-03-27T00:00:05Z"},
                {"id": 3, "user": "agent-action", "text": "Calling tool: QueryLiveMetrics", "created_at": "2026-03-27T00:00:06Z"},
                {"id": 4, "user": "assistant", "text": "Error rate is at 12.4%, p99 latency 2,340ms, CPU at 89%.", "created_at": "2026-03-27T00:00:08Z"},
                {"id": 5, "user": "user", "text": "Okay, go ahead and restart the affected pods.", "created_at": "2026-03-27T00:00:15Z"},
                {"id": 6, "user": "agent-action", "text": "Calling tool: TriggerCIBAApproval", "created_at": "2026-03-27T00:00:16Z"},
                {"id": 7, "user": "assistant", "text": "Authorization received. Triggering CIBA approval and initiating remediation. Thank you.", "created_at": "2026-03-27T00:00:18Z"},
            ],
            "concatenated_transcript": (
                "Assistant: Hello, this is SentinelCall. We've detected a SEV-2 incident on api-gateway.\n"
                "User: What are the current metrics?\n"
                "Assistant: Error rate is at 12.4%, p99 latency 2,340ms, CPU at 89%.\n"
                "User: Okay, go ahead and restart the affected pods.\n"
                "Assistant: Authorization received. Triggering CIBA approval and initiating remediation. Thank you."
            ),
            "mock": True,
        }

    try:
        logger.info("[REAL] Fetching transcript for call %s", call_id)
        response = requests.get(
            f"{BLAND_BASE_URL}/calls/{call_id}",
            headers=_headers(),
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        transcripts = data.get("transcripts", [])
        # Build a human-readable concatenated transcript
        # Bland uses "user" field with values: user, assistant, robot, agent-action
        concatenated = "\n".join(
            f"{t.get('user', 'unknown').replace('user', 'Engineer').replace('assistant', 'Agent').title()}: {t.get('text', '')}"
            for t in transcripts
            if t.get("user") in ("user", "assistant")
        )
        return {
            "call_id": call_id,
            "transcripts": transcripts,
            "concatenated_transcript": data.get("concatenated_transcript", concatenated),
        }
    except requests.RequestException as exc:
        logger.error("[REAL] Failed to get transcript for %s: %s", call_id, exc)
        return {"call_id": call_id, "transcripts": [], "error": str(exc)}
