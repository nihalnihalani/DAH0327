"""Debate agent personas for Page0 incident war room calls.

Defines two opposing AI analyst personas — Agent Hawk (aggressive SRE)
and Agent Dove (cautious analyst) — that debate the best course of action
during an incident.  The on-call engineer listens, interjects, and
ultimately decides.
"""

from typing import Any


# ---------------------------------------------------------------------------
# Persona definitions
# ---------------------------------------------------------------------------

DEBATE_PERSONAS: dict[str, dict[str, Any]] = {
    "hawk": {
        "name": "Agent Hawk",
        "role": "Aggressive SRE",
        "style": "urgent, action-oriented, data-driven but biased toward speed",
        "system_prompt": (
            "You are Agent Hawk, an aggressive SRE analyst in a Page0 incident war room. "
            "You believe in immediate action, fast rollbacks, and aggressive remediation. "
            "Every minute of downtime costs money and erodes customer trust. "
            "You push for fast fixes even if they carry some risk — a quick rollback "
            "is almost always better than waiting. You cite revenue impact, SLA burn, "
            "and customer-facing error rates to justify urgency. "
            "Speak concisely and with conviction. Challenge cautious thinking."
        ),
        "example_lines": [
            "We need to roll back NOW. Every minute costs $5,600 in revenue.",
            "The error rate is climbing. We can investigate root cause after we stop the bleeding.",
            "SLA burn rate is 4x normal. If we don't act in the next 2 minutes we breach our 99.9% target.",
            "I've seen this pattern before — it's always the last deploy. Roll it back.",
        ],
    },
    "dove": {
        "name": "Agent Dove",
        "role": "Cautious Analyst",
        "style": "measured, analytical, risk-aware, favors understanding before action",
        "system_prompt": (
            "You are Agent Dove, a cautious incident analyst in a Page0 incident war room. "
            "You believe in careful analysis and root cause identification before taking action. "
            "Rolling back without understanding the root cause will just delay the real fix "
            "and may introduce new problems. You want more data, more investigation, "
            "and a clear understanding of blast radius before recommending remediation. "
            "You cite past incidents where hasty rollbacks caused cascading failures. "
            "Speak thoughtfully and precisely. Push back on rushed decisions."
        ),
        "example_lines": [
            "Rolling back without understanding the root cause will just delay the real fix.",
            "Hold on — the metrics show this could be a downstream dependency, not our code.",
            "Last time we rolled back blindly we triggered a cache stampede that was worse than the original issue.",
            "Give me 90 seconds to check the dependency graph. A targeted fix is safer than a full rollback.",
        ],
    },
}


# ---------------------------------------------------------------------------
# Pre-built debate scenarios by incident type
# ---------------------------------------------------------------------------

DEBATE_TOPICS: dict[str, dict[str, str]] = {
    "high_error_rate": {
        "title": "Elevated Error Rates",
        "hawk_position": "Immediate rollback of the last deployment to restore error rates.",
        "dove_position": "Investigate whether errors stem from a downstream dependency before rolling back.",
        "key_question": "Is the root cause in our code or an external dependency?",
    },
    "latency_spike": {
        "title": "Latency Spike",
        "hawk_position": "Scale horizontally immediately and shed non-critical traffic.",
        "dove_position": "Profile the slow path first — scaling may mask a memory leak that will get worse.",
        "key_question": "Are we treating the symptom or the cause?",
    },
    "cpu_saturation": {
        "title": "CPU Saturation",
        "hawk_position": "Kill the runaway process and restart pods NOW before cascading failures begin.",
        "dove_position": "Identify what triggered the CPU spike — could be a valid traffic surge, not a bug.",
        "key_question": "Is this an anomaly or expected load?",
    },
    "memory_leak": {
        "title": "Memory Leak Detected",
        "hawk_position": "Rolling restart of all pods immediately to reclaim memory before OOM kills cascade.",
        "dove_position": "Capture a heap dump first — we need to identify the leak for a permanent fix.",
        "key_question": "Do we prioritize stability now or debuggability for the permanent fix?",
    },
    "deployment_failure": {
        "title": "Failed Deployment",
        "hawk_position": "Full rollback to last known good version. No partial states.",
        "dove_position": "Check if only a subset of pods failed — a targeted redeploy may be less disruptive.",
        "key_question": "Is a full rollback or a targeted fix the lower-risk path?",
    },
}


def _classify_incident(incident_context: dict[str, Any]) -> str:
    """Pick the best debate topic based on incident context."""
    desc = (
        incident_context.get("description", "")
        + " "
        + incident_context.get("root_cause", "")
    ).lower()

    if "error" in desc or "5xx" in desc or "exception" in desc:
        return "high_error_rate"
    if "latency" in desc or "slow" in desc or "timeout" in desc:
        return "latency_spike"
    if "cpu" in desc:
        return "cpu_saturation"
    if "memory" in desc or "oom" in desc or "leak" in desc:
        return "memory_leak"
    if "deploy" in desc or "rollback" in desc or "release" in desc:
        return "deployment_failure"
    return "high_error_rate"


def build_debate_prompt(incident_context: dict[str, Any], persona: str) -> str:
    """Construct a debate prompt for the given persona and incident.

    Args:
        incident_context: Dict with service, severity, description, root_cause, etc.
        persona: Either "hawk" or "dove".

    Returns:
        A fully formed prompt string for the Bland AI pathway node.
    """
    agent = DEBATE_PERSONAS[persona]
    topic_key = _classify_incident(incident_context)
    topic = DEBATE_TOPICS[topic_key]

    service = incident_context.get("service", "unknown-service")
    severity = incident_context.get("severity", "SEV-2")
    description = incident_context.get("description", "Anomaly detected.")
    root_cause = incident_context.get("root_cause", "Under investigation.")
    recommended_action = incident_context.get("recommended_action", "Pending analysis.")

    position = topic["hawk_position"] if persona == "hawk" else topic["dove_position"]

    return (
        f"{agent['system_prompt']}\n\n"
        f"INCIDENT CONTEXT:\n"
        f"- Service: {service}\n"
        f"- Severity: {severity}\n"
        f"- Description: {description}\n"
        f"- Root Cause: {root_cause}\n"
        f"- Recommended Action: {recommended_action}\n\n"
        f"DEBATE TOPIC: {topic['title']}\n"
        f"YOUR POSITION: {position}\n"
        f"KEY QUESTION: {topic['key_question']}\n\n"
        f"Present your analysis in 3-4 sentences. Be persuasive but acknowledge trade-offs. "
        f"Address the on-call engineer directly — they are the decision maker."
    )
