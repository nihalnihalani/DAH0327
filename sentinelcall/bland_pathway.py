"""Bland AI interactive conversation pathway for incident response.

Defines a multi-node conversation pathway that Bland AI follows during
the on-call engineer phone call.  Each node can trigger mid-call tool
calls (QueryLiveMetrics, TriggerCIBAApproval, EscalateToVP) via webhook
nodes -- this is the CREATIVE/UNPOPULAR Bland AI feature we showcase.

Pathways are created via POST /v1/pathway/create, then populated with
nodes/edges via POST /v1/pathway/{pathway_id}.

Ref:
  - https://docs.bland.ai/tutorials/pathways
  - https://docs.bland.ai/api-v1/post/pathways
  - https://docs.bland.ai/api-v1/post/update_pathways
"""

import logging
import uuid
from typing import Any

import requests

from sentinelcall.config import BLAND_API_KEY, WEBHOOK_BASE_URL

logger = logging.getLogger(__name__)

BLAND_BASE_URL = "https://api.bland.ai/v1"

# Module-level cache for the registered pathway ID
_pathway_id: str | None = None


def _headers() -> dict[str, str]:
    """Return authorization headers for Bland AI API."""
    return {
        "authorization": BLAND_API_KEY,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Pathway definition (ReactFlow-compatible nodes + edges)
# ---------------------------------------------------------------------------

def build_pathway_nodes(incident_context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Build the nodes array for an incident response pathway.

    Bland pathways use a ReactFlow graph structure.  Each node has:
      - id:   unique identifier
      - type: one of Default, Webhook, End Call, Transfer Call, Knowledge Base, etc.
      - data: contains name, text/prompt, isStart, extractVars, tools config, etc.

    We define five nodes:
      1. greeting   (Default)  -- introduce the incident
      2. deep_dive  (Webhook)  -- call QueryLiveMetrics webhook for live data
      3. authorize  (Webhook)  -- call TriggerCIBAApproval webhook on verbal OK
      4. escalate   (Webhook)  -- call EscalateToVP webhook if requested
      5. end        (End Call) -- wrap up and hang up

    Variables from the call's ``request_data`` are available as {{variable}}.
    """
    ctx = incident_context or {}
    service = ctx.get("service", "{{service}}")
    severity = ctx.get("severity", "{{severity}}")
    description = ctx.get("description", "{{description}}")
    root_cause = ctx.get("root_cause", "{{root_cause}}")
    recommended_action = ctx.get("recommended_action", "{{recommended_action}}")
    engineer_id = ctx.get("engineer_id", "{{engineer_id}}")

    return [
        {
            "id": "greeting",
            "type": "Default",
            "data": {
                "name": "Incident Briefing",
                "isStart": True,
                "text": "",
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
                "modelOptions": {
                    "temperature": 0.4,
                },
            },
        },
        {
            "id": "deep_dive",
            "type": "Webhook",
            "data": {
                "name": "Query Live Metrics",
                "prompt": (
                    "The engineer wants live metrics. Present the results after the webhook "
                    "returns.  After sharing metrics, ask if they want to approve the "
                    "recommended action or escalate."
                ),
                "url": f"{WEBHOOK_BASE_URL}/bland/function-call",
                "method": "POST",
                "body": {
                    "name": "query_live_metrics",
                    "call_id": "{{call_id}}",
                    "parameters": {
                        "service_name": service if service != "{{service}}" else "{{service}}",
                        "metric_type": "all",
                    },
                },
                "extractVars": [
                    {"name": "metrics_data", "type": "string", "description": "The live metrics returned from the infrastructure"},
                ],
                "responseData": [
                    {"name": "metrics", "path": "$.metrics"},
                    {"name": "service_status", "path": "$.metrics.*.status"},
                ],
                "responsePathways": [],
                "speech": "Let me pull up the live metrics for you now.",
            },
        },
        {
            "id": "authorize",
            "type": "Webhook",
            "data": {
                "name": "CIBA Authorization",
                "prompt": (
                    f"The engineer has approved the remediation action. "
                    f"Confirm what they are authorizing: '{recommended_action}'. "
                    f"Then trigger the CIBA authorization to formally record their approval."
                ),
                "url": f"{WEBHOOK_BASE_URL}/bland/function-call",
                "method": "POST",
                "body": {
                    "name": "trigger_ciba_approval",
                    "call_id": "{{call_id}}",
                    "parameters": {
                        "engineer_id": engineer_id if engineer_id != "{{engineer_id}}" else "{{engineer_id}}",
                        "action_approved": recommended_action if recommended_action != "{{recommended_action}}" else "{{recommended_action}}",
                    },
                },
                "extractVars": [],
                "responseData": [
                    {"name": "auth_status", "path": "$.status"},
                    {"name": "auth_request_id", "path": "$.auth_request_id"},
                ],
                "responsePathways": [],
                "speech": "Recording your authorization now.",
            },
        },
        {
            "id": "escalate",
            "type": "Webhook",
            "data": {
                "name": "Escalate to VP",
                "prompt": (
                    "The engineer wants to escalate this incident. "
                    "Confirm the reason for escalation and trigger the escalation "
                    "to VP of Engineering. Then thank them and end the call."
                ),
                "url": f"{WEBHOOK_BASE_URL}/bland/function-call",
                "method": "POST",
                "body": {
                    "name": "escalate_to_vp",
                    "call_id": "{{call_id}}",
                    "parameters": {
                        "reason": "{{input.reason}}",
                    },
                },
                "extractVars": [
                    {"name": "escalation_reason", "type": "string", "description": "Reason the engineer wants to escalate"},
                ],
                "responseData": [
                    {"name": "escalation_status", "path": "$.status"},
                    {"name": "escalation_id", "path": "$.escalation_id"},
                ],
                "responsePathways": [],
                "speech": "Initiating escalation to VP of Engineering now.",
            },
        },
        {
            "id": "end",
            "type": "End Call",
            "data": {
                "name": "End Call",
                "prompt": (
                    "Thank the engineer for their time. Let them know the incident report "
                    "will be published to Ghost CMS shortly with both executive and "
                    "engineering summaries. End the call politely."
                ),
            },
        },
    ]


def build_pathway_edges() -> list[dict[str, Any]]:
    """Build the edges array connecting pathway nodes.

    Bland edges follow the ReactFlow format:
      - source: originating node ID
      - target: destination node ID
      - data.label: natural-language condition for when the agent traverses this edge
    """
    return [
        # From greeting
        {
            "source": "greeting",
            "target": "deep_dive",
            "data": {
                "label": "The engineer wants to see metrics or asks about current stats, latency, errors, or performance.",
            },
        },
        {
            "source": "greeting",
            "target": "authorize",
            "data": {
                "label": "The engineer approves the recommended action or says to go ahead.",
            },
        },
        {
            "source": "greeting",
            "target": "escalate",
            "data": {
                "label": "The engineer wants to escalate or says this needs VP/leadership attention.",
            },
        },
        # From deep_dive
        {
            "source": "deep_dive",
            "target": "authorize",
            "data": {
                "label": "The engineer approves the action or says to proceed after reviewing metrics.",
            },
        },
        {
            "source": "deep_dive",
            "target": "escalate",
            "data": {
                "label": "The engineer wants to escalate after reviewing metrics.",
            },
        },
        {
            "source": "deep_dive",
            "target": "deep_dive",
            "data": {
                "label": "The engineer wants more metrics or a different metric type.",
            },
        },
        # From authorize
        {
            "source": "authorize",
            "target": "end",
            "data": {
                "label": "Authorization is complete or confirmed.",
            },
        },
        # From escalate
        {
            "source": "escalate",
            "target": "end",
            "data": {
                "label": "Escalation is confirmed or call should end.",
            },
        },
    ]


# ---------------------------------------------------------------------------
# Pathway CRUD via Bland API
# ---------------------------------------------------------------------------

def create_pathway(incident_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create and register a conversation pathway with the Bland AI API.

    Two-step process:
      1. POST /v1/pathway/create  -- creates an empty pathway, returns pathway_id
      2. POST /v1/pathway/{id}    -- populates nodes and edges

    Args:
        incident_context: Incident details to embed in the pathway.

    Returns:
        Dict with pathway_id, status, and creation details.
    """
    global _pathway_id

    ctx = incident_context or {}
    pathway_name = f"SentinelCall Incident Response - {ctx.get('service', 'general')}"
    nodes = build_pathway_nodes(incident_context)
    edges = build_pathway_edges()

    if not BLAND_API_KEY:
        mock_id = f"pathway-demo-{uuid.uuid4().hex[:8]}"
        _pathway_id = mock_id
        logger.info("[MOCK] Pathway created (no API key). pathway_id=%s", mock_id)
        return {
            "pathway_id": mock_id,
            "status": "created",
            "name": pathway_name,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "mock": True,
        }

    try:
        # Step 1: Create empty pathway
        logger.info("[REAL] Creating Bland pathway: %s", pathway_name)
        create_resp = requests.post(
            f"{BLAND_BASE_URL}/pathway/create",
            json={
                "name": pathway_name,
                "description": (
                    "Interactive incident response pathway with mid-call webhook "
                    "nodes for live metrics, CIBA authorization, and escalation."
                ),
            },
            headers=_headers(),
            timeout=30,
        )
        create_resp.raise_for_status()
        create_data = create_resp.json()
        new_pathway_id = create_data.get("pathway_id")

        if not new_pathway_id:
            raise ValueError(f"No pathway_id in create response: {create_data}")

        # Step 2: Populate nodes and edges
        logger.info("[REAL] Populating pathway %s with %d nodes, %d edges", new_pathway_id, len(nodes), len(edges))
        update_resp = requests.post(
            f"{BLAND_BASE_URL}/pathway/{new_pathway_id}",
            json={
                "name": pathway_name,
                "nodes": nodes,
                "edges": edges,
            },
            headers=_headers(),
            timeout=30,
        )
        update_resp.raise_for_status()

        _pathway_id = new_pathway_id
        logger.info("[REAL] Bland pathway created and populated. pathway_id=%s", _pathway_id)
        return {
            "pathway_id": _pathway_id,
            "status": "created",
            "name": pathway_name,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }
    except (requests.RequestException, ValueError) as exc:
        logger.error("[REAL] Failed to create Bland pathway: %s — using mock fallback.", exc)
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
