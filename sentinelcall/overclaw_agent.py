"""OverClaw-compatible agent entrypoint for Pager0.

This module exposes a ``run(input: dict) -> dict`` function that OverClaw
calls for each test case during optimization.  It wraps the full
SentinelCallAgent pipeline and returns a structured result that OverClaw
scores against the evaluation spec.

Register with OverClaw:
    overclaw agent register pager0 sentinelcall.overclaw_agent:run

Setup evaluation:
    overclaw setup pager0 --policy sentinelcall/overclaw_policies.md

Optimize:
    overclaw optimize pager0
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Try to import OverClaw tracer wrappers for full span recording
try:
    from overclaw.core.tracer import call_llm, call_tool  # type: ignore[import-untyped]
    _HAS_OVERCLAW = True
except ImportError:
    _HAS_OVERCLAW = False


def run(input: dict) -> dict:
    """OverClaw agent entrypoint.

    Accepts an incident scenario as input and runs the full Pager0
    pipeline.  Returns a structured dict that OverClaw evaluates.

    Args:
        input: Dict with keys:
            - ``service`` (str): Target service name
            - ``incident_type`` (str): Type of incident to simulate
            - ``severity_expected`` (str): Expected severity classification
            - ``should_call_engineer`` (bool): Whether phone call should be triggered
            - ``should_publish_reports`` (bool): Whether Ghost reports expected

    Returns:
        Dict with keys:
            - ``incident_id`` (str): Generated incident ID
            - ``severity`` (str): Classified severity (SEV-1/2/3)
            - ``anomalies_detected`` (int): Number of anomalies found
            - ``model_used`` (str): LLM model selected for diagnosis
            - ``diagnosis`` (str): Root cause diagnosis text
            - ``causal_pr`` (dict): Identified causal PR
            - ``call_initiated`` (bool): Whether Bland AI call was made
            - ``reports_published`` (bool): Whether Ghost reports were created
            - ``ciba_approved`` (bool): Whether Auth0 CIBA flow completed
            - ``total_duration_seconds`` (float): Pipeline execution time
            - ``steps_completed`` (list[str]): Names of completed pipeline steps
            - ``connector_count`` (int): Dynamic Airbyte connectors created
    """
    # Lazy import to avoid circular deps and allow OverClaw to modify agent code
    from sentinelcall.agent import SentinelCallAgent

    service = input.get("service", "payment-service")
    incident_type = input.get("incident_type", "payment_service_error")

    agent = SentinelCallAgent()

    # Run the full pipeline
    result = asyncio.run(agent.run_incident_response(service))

    # Extract structured output for OverClaw scoring
    steps = result.get("steps", {})
    return {
        "incident_id": result.get("incident_id", ""),
        "severity": result.get("severity", "unknown"),
        "anomalies_detected": result.get("anomaly_count", 0),
        "model_used": result.get("model_used", "unknown"),
        "diagnosis": result.get("diagnosis", ""),
        "causal_pr": result.get("causal_pr", {}),
        "call_initiated": "bland_call" in steps,
        "reports_published": "ghost_reports" in steps,
        "ciba_approved": "auth0_ciba" in steps,
        "total_duration_seconds": result.get("total_duration_seconds", 0),
        "steps_completed": list(steps.keys()),
        "connector_count": steps.get("dynamic_investigation", {}).get(
            "connectors_created", 0
        ),
        "status": result.get("status", "unknown"),
    }
