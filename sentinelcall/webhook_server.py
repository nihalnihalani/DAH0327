"""FastAPI webhook receiver for Bland AI call events and mid-call tool calls.

Exposes two endpoints:
- POST /bland/webhook        -- receives post-call webhook payloads from Bland
- POST /bland/function-call  -- receives mid-call tool invocations from Bland

The webhook payload from Bland contains the full call record including
call_id, status, transcripts, variables, summary, and metadata.

The function-call endpoint is hit by Bland custom tools (or pathway webhook
nodes) during a live call.  We return JSON that Bland feeds back into the
conversation via the tool's ``response`` extraction config.

Ref:
  - https://docs.bland.ai/tutorials/post-call-webhooks
  - https://docs.bland.ai/tutorials/custom-tools
  - https://docs.bland.ai/tutorials/webhooks

Uses APIRouter so it can be mounted in the main dashboard app.
"""

import logging
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["bland"])

# Module-level storage for call results, keyed by call_id
call_results: dict[str, dict[str, Any]] = {}

# Module-level storage for function call logs
function_call_log: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Mock metric data for demo
# ---------------------------------------------------------------------------

_MOCK_METRICS: dict[str, dict[str, Any]] = {
    "api-gateway": {
        "latency": {"p50_ms": 145, "p95_ms": 890, "p99_ms": 2340, "status": "degraded"},
        "error_rate": {"rate_percent": 12.4, "5xx_count": 1847, "4xx_count": 312, "status": "critical"},
        "cpu": {"usage_percent": 89.2, "cores_used": 7.1, "cores_total": 8, "status": "critical"},
        "memory": {"usage_percent": 72.1, "used_gb": 11.5, "total_gb": 16, "status": "warning"},
        "throughput": {"requests_per_sec": 3420, "avg_rps_baseline": 8500, "status": "degraded"},
    },
    "payment-service": {
        "latency": {"p50_ms": 230, "p95_ms": 1200, "p99_ms": 3100, "status": "degraded"},
        "error_rate": {"rate_percent": 8.7, "5xx_count": 923, "4xx_count": 156, "status": "warning"},
        "cpu": {"usage_percent": 65.3, "cores_used": 5.2, "cores_total": 8, "status": "normal"},
        "memory": {"usage_percent": 81.4, "used_gb": 13.0, "total_gb": 16, "status": "warning"},
        "throughput": {"requests_per_sec": 1890, "avg_rps_baseline": 2400, "status": "degraded"},
    },
}


def _get_mock_metrics(service_name: str, metric_type: str = "all") -> dict[str, Any]:
    """Return mock metrics for a service."""
    service_metrics = _MOCK_METRICS.get(service_name, _MOCK_METRICS.get("api-gateway", {}))
    if metric_type == "all":
        return service_metrics
    return {metric_type: service_metrics.get(metric_type, {"status": "no_data"})}


# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------

_APPROVAL_PHRASES = [
    "go ahead",
    "approved",
    "approve",
    "proceed",
    "yes do it",
    "yes, do it",
    "authorize",
    "authorized",
    "confirm",
    "confirmed",
    "restart",
    "roll it back",
    "execute",
    "green light",
    "ship it",
    "do it",
    "yes please",
    "make it happen",
    "sounds good",
    "go for it",
]


def parse_authorization(transcript: list[dict[str, Any]] | str) -> dict[str, Any]:
    """Parse engineer's verbal authorization from a call transcript.

    Bland transcripts use ``user`` field with values:
      - "user"         -- the human on the call
      - "assistant"    -- the AI agent
      - "robot"        -- system messages
      - "agent-action" -- tool invocations

    We only check lines from the human ("user").

    Args:
        transcript: Either a Bland transcripts array or a plain string.

    Returns:
        Dict with authorized (bool), phrase_matched, and confidence.
    """
    if isinstance(transcript, list):
        # Bland transcript entries: {"id": ..., "user": "user"|"assistant"|..., "text": "..."}
        human_lines = [
            t.get("text", "").lower()
            for t in transcript
            if t.get("user", "").lower() in ("user",)
        ]
        text_to_check = " ".join(human_lines)
    else:
        text_to_check = transcript.lower()

    for phrase in _APPROVAL_PHRASES:
        if phrase in text_to_check:
            return {
                "authorized": True,
                "phrase_matched": phrase,
                "confidence": "high" if phrase in ("approved", "authorize", "confirmed") else "medium",
            }

    return {"authorized": False, "phrase_matched": None, "confidence": None}


# ---------------------------------------------------------------------------
# Webhook endpoint — post-call notifications from Bland
# ---------------------------------------------------------------------------

@router.post("/bland/webhook")
async def bland_webhook(request: Request) -> JSONResponse:
    """Receive post-call webhook payloads from Bland AI.

    Bland sends a POST with the full call record after the call completes.
    Key fields in the payload (same as GET /v1/calls/{call_id}):
      - call_id, status, completed, answered_by, call_ended_by
      - transcripts (array of {id, user, text, created_at})
      - concatenated_transcript (string)
      - variables, summary, call_length, metadata, price, recording_url
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    # Bland uses "call_id" as the primary identifier
    call_id = body.get("call_id", "unknown")
    status = body.get("status", "unknown")
    completed = body.get("completed", False)
    transcripts = body.get("transcripts", [])
    answered_by = body.get("answered_by")

    logger.info(
        "Bland webhook received: call_id=%s status=%s completed=%s answered_by=%s",
        call_id, status, completed, answered_by,
    )

    # Store/update call result
    if call_id not in call_results:
        call_results[call_id] = {"call_id": call_id, "events": []}

    call_results[call_id].update({
        "status": status,
        "completed": completed,
        "answered_by": answered_by,
        "call_ended_by": body.get("call_ended_by"),
        "call_length": body.get("call_length"),
        "transcripts": transcripts,
        "concatenated_transcript": body.get("concatenated_transcript", ""),
        "summary": body.get("summary", ""),
        "variables": body.get("variables", {}),
        "metadata": body.get("metadata", {}),
        "recording_url": body.get("recording_url"),
        "price": body.get("price"),
        "updated_at": time.time(),
        "raw_payload": body,
    })
    call_results[call_id]["events"].append({
        "status": status,
        "timestamp": time.time(),
    })

    # If call is completed, parse authorization from transcript
    if completed or status in ("completed",):
        auth_result = parse_authorization(transcripts)
        call_results[call_id]["authorization"] = auth_result
        logger.info(
            "Call %s completed. Authorization: %s (phrase: %s)",
            call_id,
            auth_result["authorized"],
            auth_result.get("phrase_matched"),
        )

    return JSONResponse({"received": True, "call_id": call_id})


# ---------------------------------------------------------------------------
# Function-call endpoint — mid-call tool invocations from Bland
# ---------------------------------------------------------------------------

@router.post("/bland/function-call")
async def bland_function_call(request: Request) -> JSONResponse:
    """Handle mid-call tool invocation requests from Bland AI.

    Bland custom tools and webhook nodes POST to this URL during a live call.
    The request body contains:
      - name: the function name (from the tool's body config)
      - call_id: the active call ID (from {{call_id}})
      - parameters: the tool-specific parameters

    The response JSON is parsed by Bland using the tool's ``response`` field
    (JSONPath extraction) and fed back into the agent's conversation context.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    function_name = body.get("name", "unknown")
    parameters = body.get("parameters", {})
    call_id = body.get("call_id", "unknown")

    logger.info("Bland function call: %s with params=%s (call_id=%s)", function_name, parameters, call_id)

    # Log the function call
    function_call_log.append({
        "function_name": function_name,
        "parameters": parameters,
        "call_id": call_id,
        "timestamp": time.time(),
    })

    # Dispatch to the appropriate handler
    if function_name == "query_live_metrics":
        result = _handle_query_live_metrics(parameters)
    elif function_name == "trigger_ciba_approval":
        result = _handle_trigger_ciba_approval(parameters, call_id)
    elif function_name == "escalate_to_vp":
        result = _handle_escalate_to_vp(parameters, call_id)
    else:
        logger.warning("Unknown function call: %s", function_name)
        result = {"error": f"Unknown function: {function_name}"}

    return JSONResponse(result)


# ---------------------------------------------------------------------------
# Function call handlers
# ---------------------------------------------------------------------------

def _handle_query_live_metrics(parameters: dict[str, Any]) -> dict[str, Any]:
    """Handle a query_live_metrics tool call from the Bland AI agent."""
    service_name = parameters.get("service_name", "api-gateway")
    metric_type = parameters.get("metric_type", "all")

    metrics = _get_mock_metrics(service_name, metric_type)
    logger.info("Returning metrics for %s (%s): %s", service_name, metric_type, metrics)

    return {
        "success": True,
        "service": service_name,
        "metric_type": metric_type,
        "metrics": metrics,
        "timestamp": time.time(),
    }


def _handle_trigger_ciba_approval(parameters: dict[str, Any], call_id: str) -> dict[str, Any]:
    """Handle a trigger_ciba_approval tool call.

    In production, this would initiate an Auth0 CIBA backchannel auth request.
    For demo, we simulate a successful approval.
    """
    engineer_id = parameters.get("engineer_id", "engineer-001")
    action_approved = parameters.get("action_approved", "remediation action")

    logger.info("CIBA approval triggered: engineer=%s action='%s' call=%s", engineer_id, action_approved, call_id)

    # Update call results with authorization
    if call_id in call_results:
        call_results[call_id]["authorization"] = {
            "authorized": True,
            "method": "ciba_voice",
            "engineer_id": engineer_id,
            "action_approved": action_approved,
        }

    return {
        "success": True,
        "auth_request_id": f"ciba-{call_id}",
        "engineer_id": engineer_id,
        "action_approved": action_approved,
        "status": "approved",
        "message": f"CIBA authorization initiated for {engineer_id}. Approval recorded.",
    }


def _handle_escalate_to_vp(parameters: dict[str, Any], call_id: str) -> dict[str, Any]:
    """Handle an escalate_to_vp tool call."""
    reason = parameters.get("reason", "Engineer requested escalation.")

    logger.info("Escalation to VP triggered: reason='%s' call=%s", reason, call_id)

    # Update call results
    if call_id in call_results:
        call_results[call_id]["escalated"] = True
        call_results[call_id]["escalation_reason"] = reason

    return {
        "success": True,
        "escalation_id": f"esc-{call_id}",
        "escalated_to": "VP of Engineering",
        "reason": reason,
        "status": "escalated",
        "message": "Incident escalated to VP of Engineering. They will be notified immediately.",
    }


# ---------------------------------------------------------------------------
# Query helpers (for the agent orchestrator to use)
# ---------------------------------------------------------------------------

def get_call_result(call_id: str) -> dict[str, Any] | None:
    """Retrieve stored results for a call by ID."""
    return call_results.get(call_id)


def get_all_call_results() -> dict[str, dict[str, Any]]:
    """Return all stored call results."""
    return call_results.copy()


def get_function_call_log() -> list[dict[str, Any]]:
    """Return the full function call log."""
    return function_call_log.copy()
