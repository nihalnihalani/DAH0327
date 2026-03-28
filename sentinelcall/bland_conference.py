"""Bland AI debate/conference call — persona-switching war room.

Since Bland AI does not support native conference calls, this module
implements a persona-switching approach: a single Bland call whose
pathway alternates between two AI analyst personas (Agent Hawk and
Agent Dove) debating the correct incident response, with the on-call
engineer able to interject at any point.

API calls match the real Bland API format used in bland_caller.py
and bland_pathway.py.
"""

import logging
import uuid
from typing import Any

import requests

from sentinelcall.config import BLAND_API_KEY, ON_CALL_PHONE, WEBHOOK_BASE_URL
from sentinelcall.debate_agents import (
    DEBATE_PERSONAS,
    build_debate_prompt,
)

logger = logging.getLogger(__name__)

BLAND_BASE_URL = "https://api.bland.ai/v1"


def _headers() -> dict[str, str]:
    """Return authorization headers for Bland AI API."""
    return {
        "authorization": BLAND_API_KEY,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Pathway construction
# ---------------------------------------------------------------------------

def build_debate_pathway(incident_context: dict[str, Any]) -> dict[str, Any]:
    """Build a Bland pathway with alternating persona nodes for a debate.

    Node flow:
      intro -> hawk_analysis -> user_response_1 -> dove_analysis ->
      user_response_2 -> synthesis -> end_call

    Uses the ReactFlow node format (id, type, data with name/prompt/isStart)
    and a separate edges array, matching bland_pathway.py conventions.

    Args:
        incident_context: Dict with service, severity, description, etc.

    Returns:
        Dict with "nodes" and "edges" keys.
    """
    service = incident_context.get("service", "unknown-service")
    severity = incident_context.get("severity", "SEV-2")

    hawk_prompt = build_debate_prompt(incident_context, "hawk")
    dove_prompt = build_debate_prompt(incident_context, "dove")

    nodes = [
        {
            "id": "intro",
            "type": "Default",
            "data": {
                "name": "War Room Introduction",
                "isStart": True,
                "text": "",
                "prompt": (
                    "You are the moderator of a Pager0 incident war room. "
                    "Greet the on-call engineer and say: "
                    "'Welcome to the Pager0 incident war room. We have a "
                    f"{severity} incident on {service}. "
                    "Two AI analysts will present opposing views on how to respond. "
                    "You can ask questions or weigh in at any time. "
                    "Let's start with Agent Hawk, our aggressive SRE analyst.'"
                ),
            },
        },
        {
            "id": "hawk_analysis",
            "type": "Default",
            "data": {
                "name": "Agent Hawk Analysis",
                "text": "",
                "prompt": hawk_prompt,
                "modelOptions": {"temperature": 0.6},
            },
        },
        {
            "id": "user_response_1",
            "type": "Default",
            "data": {
                "name": "Engineer Response 1",
                "text": "",
                "prompt": (
                    "You are the war room moderator. Agent Hawk just presented their analysis. "
                    "Ask the on-call engineer: 'What do you think? Do you agree with Agent Hawk's "
                    "push for immediate action, or would you like to hear Agent Dove's "
                    "counter-analysis first?' Wait for their response."
                ),
            },
        },
        {
            "id": "dove_analysis",
            "type": "Default",
            "data": {
                "name": "Agent Dove Analysis",
                "text": "",
                "prompt": dove_prompt,
                "modelOptions": {"temperature": 0.6},
            },
        },
        {
            "id": "user_response_2",
            "type": "Default",
            "data": {
                "name": "Engineer Response 2",
                "text": "",
                "prompt": (
                    "You are the war room moderator. Agent Dove just presented their "
                    "counter-analysis. Say: 'Agent Dove disagrees and recommends a more cautious "
                    "approach. As the on-call engineer, what is your call? "
                    "Should we act immediately, investigate further, or take a middle path?' "
                    "Wait for their response."
                ),
            },
        },
        {
            "id": "synthesis",
            "type": "Default",
            "data": {
                "name": "Synthesis & Decision",
                "text": "",
                "prompt": (
                    "You are the war room moderator wrapping up the debate. "
                    "Based on the engineer's input, synthesize the final decision. "
                    "Summarize: 1) What Agent Hawk recommended, 2) What Agent Dove recommended, "
                    "3) What the engineer decided, and 4) The action Pager0 will now execute. "
                    "Be concise and confirm the decision clearly."
                ),
            },
        },
        {
            "id": "end_call",
            "type": "End Call",
            "data": {
                "name": "End War Room",
                "prompt": (
                    "Thank the engineer for their time. Let them know Pager0 will execute "
                    "the agreed remediation and publish incident reports to Ghost CMS — "
                    "an executive summary and a detailed engineering report. "
                    "End the call politely."
                ),
            },
        },
    ]

    edges = [
        # intro -> hawk
        {
            "source": "intro",
            "target": "hawk_analysis",
            "data": {"label": "Introduction complete, proceed to Agent Hawk's analysis."},
        },
        # hawk -> user response 1
        {
            "source": "hawk_analysis",
            "target": "user_response_1",
            "data": {"label": "Agent Hawk has finished presenting. Get engineer's reaction."},
        },
        # user response 1 -> dove (default path)
        {
            "source": "user_response_1",
            "target": "dove_analysis",
            "data": {"label": "The engineer wants to hear Agent Dove's counter-analysis or hasn't decided yet."},
        },
        # user response 1 -> synthesis (engineer already decided)
        {
            "source": "user_response_1",
            "target": "synthesis",
            "data": {"label": "The engineer has already made a clear decision and doesn't need to hear more."},
        },
        # dove -> user response 2
        {
            "source": "dove_analysis",
            "target": "user_response_2",
            "data": {"label": "Agent Dove has finished presenting. Get engineer's final decision."},
        },
        # user response 2 -> synthesis
        {
            "source": "user_response_2",
            "target": "synthesis",
            "data": {"label": "The engineer has provided their decision or input."},
        },
        # user response 2 -> hawk (want to hear hawk again)
        {
            "source": "user_response_2",
            "target": "hawk_analysis",
            "data": {"label": "The engineer wants Agent Hawk to respond to Dove's points."},
        },
        # synthesis -> end
        {
            "source": "synthesis",
            "target": "end_call",
            "data": {"label": "Decision is confirmed and summarized. End the call."},
        },
    ]

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Pathway registration via Bland API
# ---------------------------------------------------------------------------

def _create_pathway_on_bland(incident_context: dict[str, Any]) -> str:
    """Create the debate pathway on Bland AI and return the pathway_id.

    Two-step process (same as bland_pathway.py):
      1. POST /v1/pathway/create  -- creates an empty pathway
      2. POST /v1/pathway/{id}    -- populates nodes and edges
    """
    pathway_data = build_debate_pathway(incident_context)
    service = incident_context.get("service", "unknown")
    pathway_name = f"Pager0 Debate War Room - {service}"

    # Step 1: create empty pathway
    logger.info("[REAL] Creating debate pathway: %s", pathway_name)
    create_resp = requests.post(
        f"{BLAND_BASE_URL}/pathway/create",
        json={
            "name": pathway_name,
            "description": (
                "Two-persona debate pathway for incident response. "
                "Agent Hawk (aggressive) vs Agent Dove (cautious)."
            ),
        },
        headers=_headers(),
        timeout=30,
    )
    create_resp.raise_for_status()
    resp_json = create_resp.json()
    pathway_id = resp_json.get("pathway_id") or (
        resp_json.get("data", {}).get("pathway_id")
    )
    if not pathway_id:
        raise ValueError(f"No pathway_id in create response: {resp_json}")

    # Step 2: populate nodes and edges
    logger.info(
        "[REAL] Populating debate pathway %s with %d nodes, %d edges",
        pathway_id,
        len(pathway_data["nodes"]),
        len(pathway_data["edges"]),
    )
    update_resp = requests.post(
        f"{BLAND_BASE_URL}/pathway/{pathway_id}",
        json={
            "name": pathway_name,
            "nodes": pathway_data["nodes"],
            "edges": pathway_data["edges"],
        },
        headers=_headers(),
        timeout=30,
    )
    update_resp.raise_for_status()

    logger.info("[REAL] Debate pathway created. pathway_id=%s", pathway_id)
    return pathway_id


# ---------------------------------------------------------------------------
# Mock fallback
# ---------------------------------------------------------------------------

def _mock_debate_response(phone_number: str, incident_context: dict[str, Any]) -> dict[str, Any]:
    """Return a realistic mock response for demo/testing."""
    call_id = f"debate-demo-{uuid.uuid4().hex[:12]}"
    logger.info("[MOCK] Debate call simulated (no API key). call_id=%s", call_id)
    return {
        "status": "success",
        "message": "Demo mode: debate call simulated successfully.",
        "call_id": call_id,
        "batch_id": None,
        "debate": True,
        "personas": ["Agent Hawk", "Agent Dove"],
        "mock": True,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_debate_call(
    phone_number: str | None = None,
    incident_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Initiate a debate call between two AI personas about an incident.

    Creates a Bland pathway with alternating Hawk/Dove persona nodes,
    then makes an outbound call using that pathway.

    Args:
        phone_number: E.164 phone number to call (defaults to ON_CALL_PHONE).
        incident_context: Dict with incident details.

    Returns:
        Dict with status, call_id, pathway_id, and persona info.
    """
    phone_number = phone_number or ON_CALL_PHONE
    incident_context = incident_context or {
        "service": "api-gateway",
        "severity": "SEV-2",
        "description": "Elevated error rates detected on api-gateway.",
        "root_cause": "Suspected bad deployment — last PR merged 12 minutes ago.",
        "recommended_action": "Roll back latest deployment or investigate dependency.",
    }

    if not BLAND_API_KEY:
        return _mock_debate_response(phone_number, incident_context)

    try:
        # Create the debate pathway
        pathway_id = _create_pathway_on_bland(incident_context)

        # Make the outbound call with the pathway
        service = incident_context.get("service", "unknown")
        severity = incident_context.get("severity", "SEV-2")

        payload = {
            "phone_number": phone_number,
            "pathway_id": pathway_id,
            "voice": "mason",
            "wait_for_greeting": True,
            "record": True,
            "max_duration": 8,
            "model": "base",
            "temperature": 0.5,
            "webhook": f"{WEBHOOK_BASE_URL}/bland/webhook",
            "request_data": {
                "service": service,
                "severity": severity,
                "description": incident_context.get("description", "Anomaly detected."),
                "root_cause": incident_context.get("root_cause", "Under investigation."),
                "recommended_action": incident_context.get("recommended_action", "Pending."),
            },
            "metadata": {
                "call_type": "debate_war_room",
                "incident_id": incident_context.get(
                    "incident_id", f"INC-{uuid.uuid4().hex[:8]}"
                ),
                "severity": severity,
                "source": "pager0",
            },
        }

        logger.info("[REAL] Sending debate call to %s with pathway %s", phone_number, pathway_id)
        response = requests.post(
            f"{BLAND_BASE_URL}/calls",
            json=payload,
            headers=_headers(),
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        data["pathway_id"] = pathway_id
        data["debate"] = True
        data["personas"] = ["Agent Hawk", "Agent Dove"]

        if data.get("status") == "success":
            logger.info("[REAL] Debate call queued. call_id=%s", data.get("call_id"))
        else:
            logger.warning("[REAL] Bland returned non-success for debate call: %s", data)

        return data

    except (requests.RequestException, ValueError) as exc:
        logger.error("[REAL] Debate call failed: %s — falling back to mock.", exc)
        result = _mock_debate_response(phone_number, incident_context)
        result["fallback_reason"] = str(exc)
        return result


def get_debate_status(call_id: str) -> dict[str, Any]:
    """Check the status of a debate call.

    Args:
        call_id: The Bland AI call ID.

    Returns:
        Dict with call status details.
    """
    if not BLAND_API_KEY or call_id.startswith("debate-demo-"):
        return {
            "call_id": call_id,
            "status": "completed",
            "completed": True,
            "call_length": 2.35,
            "answered_by": "human",
            "call_type": "debate_war_room",
            "personas": ["Agent Hawk", "Agent Dove"],
            "summary": (
                "Debate war room: Agent Hawk pushed for immediate rollback. "
                "Agent Dove recommended investigating the dependency graph first. "
                "Engineer decided on a targeted rollback of the last PR only."
            ),
            "mock": True,
        }

    try:
        logger.info("[REAL] Fetching debate call status for %s", call_id)
        response = requests.get(
            f"{BLAND_BASE_URL}/calls/{call_id}",
            headers=_headers(),
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        data["call_type"] = "debate_war_room"
        return data
    except requests.RequestException as exc:
        logger.error("[REAL] Failed to get debate call status for %s: %s", call_id, exc)
        return {"call_id": call_id, "status": "unknown", "error": str(exc)}


def get_debate_transcript(call_id: str) -> dict[str, Any]:
    """Get the transcript from a debate call.

    Args:
        call_id: The Bland AI call ID.

    Returns:
        Dict with call_id, transcripts array, and concatenated_transcript.
    """
    if not BLAND_API_KEY or call_id.startswith("debate-demo-"):
        return {
            "call_id": call_id,
            "call_type": "debate_war_room",
            "transcripts": [
                {"id": 1, "user": "assistant", "text": "Welcome to the Pager0 incident war room. We have a SEV-2 incident on api-gateway. Two AI analysts will present opposing views. Let's start with Agent Hawk.", "created_at": "2026-03-27T00:00:01Z"},
                {"id": 2, "user": "assistant", "text": "Agent Hawk here. We need to roll back NOW. Error rate is at 12.4% and climbing. Every minute costs $5,600 in revenue. The last deploy went out 12 minutes ago -- it's always the last deploy.", "created_at": "2026-03-27T00:00:05Z"},
                {"id": 3, "user": "assistant", "text": "What do you think? Do you agree with Agent Hawk's push for immediate action?", "created_at": "2026-03-27T00:00:12Z"},
                {"id": 4, "user": "user", "text": "Let me hear the other side first.", "created_at": "2026-03-27T00:00:16Z"},
                {"id": 5, "user": "assistant", "text": "Agent Dove here. Hold on -- the metrics show error spikes in the payment service too, which we didn't deploy to. This could be a downstream dependency. Rolling back our code won't fix an upstream issue and wastes precious time.", "created_at": "2026-03-27T00:00:20Z"},
                {"id": 6, "user": "assistant", "text": "Agent Dove disagrees. As the on-call engineer, what is your call?", "created_at": "2026-03-27T00:00:28Z"},
                {"id": 7, "user": "user", "text": "Roll back just the last PR but also check the payment service dependency.", "created_at": "2026-03-27T00:00:35Z"},
                {"id": 8, "user": "assistant", "text": "Decision confirmed: targeted rollback of the last PR plus parallel investigation of the payment service dependency. Pager0 will execute now. Thank you.", "created_at": "2026-03-27T00:00:40Z"},
            ],
            "concatenated_transcript": (
                "Moderator: Welcome to the Pager0 incident war room. Two AI analysts will present opposing views.\n"
                "Agent Hawk: We need to roll back NOW. Error rate is 12.4% and climbing. Every minute costs $5,600.\n"
                "Moderator: Do you agree with Agent Hawk's push for immediate action?\n"
                "Engineer: Let me hear the other side first.\n"
                "Agent Dove: The metrics show error spikes in payment service too. This could be downstream.\n"
                "Moderator: What is your call?\n"
                "Engineer: Roll back just the last PR but also check the payment service dependency.\n"
                "Moderator: Decision confirmed. Pager0 will execute now. Thank you."
            ),
            "mock": True,
        }

    try:
        logger.info("[REAL] Fetching debate transcript for %s", call_id)
        response = requests.get(
            f"{BLAND_BASE_URL}/calls/{call_id}",
            headers=_headers(),
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        transcripts = data.get("transcripts", [])
        concatenated = "\n".join(
            f"{t.get('user', 'unknown').replace('user', 'Engineer').replace('assistant', 'Agent').title()}: {t.get('text', '')}"
            for t in transcripts
            if t.get("user") in ("user", "assistant")
        )
        return {
            "call_id": call_id,
            "call_type": "debate_war_room",
            "transcripts": transcripts,
            "concatenated_transcript": data.get("concatenated_transcript", concatenated),
        }
    except requests.RequestException as exc:
        logger.error("[REAL] Failed to get debate transcript for %s: %s", call_id, exc)
        return {"call_id": call_id, "transcripts": [], "error": str(exc)}
