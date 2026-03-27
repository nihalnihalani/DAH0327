"""Bland AI interactive conversation pathway for incident response.

Defines a multi-node conversation pathway that Bland AI follows during
the on-call engineer phone call. Each node can trigger mid-call function
calls (query_live_metrics, trigger_ciba_approval, escalate_to_vp) --
this is the CREATIVE/UNPOPULAR Bland AI feature we showcase.
"""

import logging
import uuid
from typing import Any, Optional

import requests

from sentinelcall.config import BLAND_API_KEY, WEBHOOK_BASE_URL

logger = logging.getLogger(__name__)

BLAND_BASE_URL = "https://api.bland.ai/v1"

# Module-level cache for the registered pathway ID
_pathway_id: str | None = None


def _headers() -> dict[str, str]:
    """Return authorization headers for Bland AI API."""
    return {
        "Authorization": BLAND_API_KEY,
        "Content-Type": "application/json",
    }


def build_pathway(incident_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the pathway definition dict for an incident response call.

    The pathway defines five nodes that guide the conversation:
    1. greeting    -- introduce the incident
    2. deep_dive   -- function_call to query_live_metrics when engineer asks for data
    3. authorize   -- function_call to trigger_ciba_approval on verbal approval
    4. escalate    -- function_call to escalate_to_vp if engineer wants to escalate
    5. end         -- wrap up and end the call

    Args:
        incident_context: Optional incident details to embed in the pathway prompts.

    Returns:
        Pathway definition dict ready for the Bland API.
    """
    ctx = incident_context or {}
    service = ctx.get("service", "{{service}}")
    severity = ctx.get("severity", "{{severity}}")
    description = ctx.get("description", "{{description}}")
    root_cause = ctx.get("root_cause", "{{root_cause}}")
    recommended_action = ctx.get("recommended_action", "{{recommended_action}}")
    engineer_id = ctx.get("engineer_id", "{{engineer_id}}")

    return {
        "name": f"SentinelCall Incident Response - {service}",
        "description": "Interactive incident response pathway with mid-call function calling for live metrics, CIBA authorization, and escalation.",
        "nodes": [
            {
                "id": "greeting",
                "type": "Default",
                "prompt": (
                    f"You are SentinelCall, an autonomous SRE incident response agent. "
                    f"Greet the engineer and brief them on the incident:\n"
                    f"- Service: {service}\n"
                    f"- Severity: {severity}\n"
                    f"- Description: {description}\n"
                    f"- Root Cause: {root_cause}\n"
                    f"- Recommended Action: {recommended_action}\n\n"
                    f"Ask if they would like to see live metrics before deciding."
                ),
                "edges": [
                    {
                        "condition": "The engineer wants to see metrics or asks about current stats, latency, errors, or performance.",
                        "next_node": "deep_dive",
                    },
                    {
                        "condition": "The engineer approves the recommended action or says to go ahead.",
                        "next_node": "authorize",
                    },
                    {
                        "condition": "The engineer wants to escalate or says this needs VP/leadership attention.",
                        "next_node": "escalate",
                    },
                ],
            },
            {
                "id": "deep_dive",
                "type": "Default",
                "prompt": (
                    "The engineer wants live metrics. Query the metrics system and present the results. "
                    "After sharing metrics, ask if they want to approve the recommended action or escalate."
                ),
                "tools": [
                    {
                        "name": "query_live_metrics",
                        "description": "Query live infrastructure metrics for the affected service.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "service_name": {
                                    "type": "string",
                                    "description": "The service to query.",
                                },
                                "metric_type": {
                                    "type": "string",
                                    "enum": ["latency", "error_rate", "cpu", "memory", "throughput", "all"],
                                    "description": "Type of metric to retrieve.",
                                },
                            },
                            "required": ["service_name"],
                        },
                        "url": f"{WEBHOOK_BASE_URL}/bland/function-call",
                        "method": "POST",
                        "headers": {"Content-Type": "application/json"},
                    }
                ],
                "edges": [
                    {
                        "condition": "The engineer approves the action or says to proceed.",
                        "next_node": "authorize",
                    },
                    {
                        "condition": "The engineer wants to escalate.",
                        "next_node": "escalate",
                    },
                    {
                        "condition": "The engineer wants more metrics or a different metric type.",
                        "next_node": "deep_dive",
                    },
                ],
            },
            {
                "id": "authorize",
                "type": "Default",
                "prompt": (
                    f"The engineer has approved the remediation action. "
                    f"Confirm what they are authorizing: '{recommended_action}'. "
                    f"Then trigger the CIBA authorization to formally record their approval. "
                    f"Use engineer_id '{engineer_id}'."
                ),
                "tools": [
                    {
                        "name": "trigger_ciba_approval",
                        "description": "Trigger Auth0 CIBA backchannel authorization for the engineer's verbal approval.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "engineer_id": {
                                    "type": "string",
                                    "description": "The engineer's ID.",
                                },
                                "action_approved": {
                                    "type": "string",
                                    "description": "The action being approved.",
                                },
                            },
                            "required": ["engineer_id", "action_approved"],
                        },
                        "url": f"{WEBHOOK_BASE_URL}/bland/function-call",
                        "method": "POST",
                        "headers": {"Content-Type": "application/json"},
                    }
                ],
                "edges": [
                    {
                        "condition": "Authorization is complete or confirmed.",
                        "next_node": "end",
                    },
                ],
            },
            {
                "id": "escalate",
                "type": "Default",
                "prompt": (
                    "The engineer wants to escalate this incident. "
                    "Confirm the reason for escalation and trigger the escalation to VP of Engineering. "
                    "Then thank them and end the call."
                ),
                "tools": [
                    {
                        "name": "escalate_to_vp",
                        "description": "Escalate the incident to VP of Engineering.",
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
                    }
                ],
                "edges": [
                    {
                        "condition": "Escalation is confirmed or call should end.",
                        "next_node": "end",
                    },
                ],
            },
            {
                "id": "end",
                "type": "Default",
                "prompt": (
                    "Thank the engineer for their time. Let them know the incident report will be "
                    "published to Ghost CMS shortly with both executive and engineering summaries. "
                    "End the call politely."
                ),
                "edges": [],
            },
        ],
    }


def create_pathway(incident_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create and register a conversation pathway with the Bland AI API.

    Args:
        incident_context: Incident details to embed in the pathway.

    Returns:
        Dict with pathway_id and creation status.
    """
    global _pathway_id

    pathway_def = build_pathway(incident_context)

    if not BLAND_API_KEY:
        mock_id = f"pathway-demo-{uuid.uuid4().hex[:8]}"
        _pathway_id = mock_id
        logger.info("Mock pathway created (no API key). pathway_id=%s", mock_id)
        return {
            "pathway_id": mock_id,
            "status": "created",
            "name": pathway_def["name"],
            "node_count": len(pathway_def["nodes"]),
            "mock": True,
        }

    try:
        response = requests.post(
            f"{BLAND_BASE_URL}/pathway",
            json=pathway_def,
            headers=_headers(),
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        _pathway_id = data.get("pathway_id") or data.get("id")
        logger.info("Bland pathway created. pathway_id=%s", _pathway_id)
        return {
            "pathway_id": _pathway_id,
            "status": "created",
            "name": pathway_def["name"],
            "node_count": len(pathway_def["nodes"]),
            "response": data,
        }
    except requests.RequestException as exc:
        logger.error("Failed to create Bland pathway: %s. Using mock.", exc)
        mock_id = f"pathway-fallback-{uuid.uuid4().hex[:8]}"
        _pathway_id = mock_id
        return {
            "pathway_id": mock_id,
            "status": "fallback",
            "error": str(exc),
            "mock": True,
        }


def get_pathway_id() -> str | None:
    """Return the currently registered pathway ID, or None if not yet created."""
    return _pathway_id
