"""TrueFoundry AI Gateway — dynamic model escalation by incident severity.

All LLM calls are routed through TrueFoundry's gateway, which provides
unified billing, rate-limiting, and observability.  The agent escalates to
more expensive (and capable) models as incident severity increases:

    routine  → claude-haiku-4-5-20251001   (~$0.001/call)
    warning  → claude-sonnet-4-6           (~$0.01/call)
    critical → claude-opus-4-6             (~$0.10/call)

Falls back to direct Anthropic/OpenAI calls or mock responses when
TrueFoundry is not configured.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

from sentinelcall.config import (
    TRUEFOUNDRY_API_KEY,
    TRUEFOUNDRY_ENDPOINT,
    ANTHROPIC_API_KEY,
    OPENAI_API_KEY,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model escalation tiers
# ---------------------------------------------------------------------------
MODEL_TIERS = {
    "routine": {
        "model": "claude-haiku-4-5-20251001",
        "cost_per_call": 0.001,
        "label": "Haiku (fast triage)",
    },
    "warning": {
        "model": "claude-sonnet-4-6",
        "cost_per_call": 0.01,
        "label": "Sonnet (detailed analysis)",
    },
    "critical": {
        "model": "claude-opus-4-6",
        "cost_per_call": 0.10,
        "label": "Opus (deep reasoning)",
    },
}

# ---------------------------------------------------------------------------
# Mock LLM responses for demo
# ---------------------------------------------------------------------------
MOCK_RESPONSES = {
    "routine": (
        "Preliminary triage complete. Metrics show elevated p99 latency on "
        "prod-api-us-east-1. The anomaly correlates with a 3x spike in "
        "database connection pool utilization starting at 14:32 UTC. "
        "Recommending escalation to WARNING severity for deeper analysis."
    ),
    "warning": (
        "Root cause analysis: The latency spike is caused by a missing database "
        "index on the `orders.customer_id` column introduced in PR #847. The "
        "query planner switched from an index scan to a sequential scan after "
        "the migration in commit abc123f. Connection pool saturation is a "
        "secondary effect.\n\n"
        "Recommended remediation:\n"
        "1. Add index: CREATE INDEX idx_orders_customer_id ON orders(customer_id)\n"
        "2. Increase connection pool max_size from 20 → 50 as temporary relief\n"
        "3. Roll back PR #847 if index creation takes >5 minutes"
    ),
    "critical": (
        "CRITICAL INCIDENT DIAGNOSIS — Full Analysis\n\n"
        "## Timeline\n"
        "- 14:30 UTC: PR #847 merged (migration removing index)\n"
        "- 14:32 UTC: p99 latency crosses 2s threshold\n"
        "- 14:33 UTC: Connection pool exhaustion begins\n"
        "- 14:35 UTC: 502 errors reach 12% of traffic\n\n"
        "## Root Cause\n"
        "Migration in PR #847 dropped `idx_orders_customer_id` as part of "
        "table restructuring. The ORM's query for the checkout flow now "
        "performs a full table scan on 47M rows.\n\n"
        "## Impact\n"
        "- 12% of checkout requests failing (502)\n"
        "- Estimated revenue impact: $4,200/minute\n"
        "- 3 downstream services degraded\n\n"
        "## Remediation Plan\n"
        "1. IMMEDIATE: Roll back PR #847 (ETA: 90 seconds)\n"
        "2. FOLLOW-UP: Re-apply migration with index preserved\n"
        "3. PREVENTION: Add CI check for index removal on high-traffic tables\n\n"
        "Confidence: 94% — based on query plan analysis and timing correlation."
    ),
}


@dataclass
class LLMCallRecord:
    """Tracks a single LLM call for observability and cost tracking."""

    model: str
    severity: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost: float
    latency_ms: float
    timestamp: float = field(default_factory=time.time)


class TrueFoundryGateway:
    """TrueFoundry AI Gateway with dynamic model escalation.

    Routes LLM calls through TrueFoundry when configured, falls back to
    direct provider calls or mock responses for demo purposes.
    """

    def __init__(self) -> None:
        self._call_log: list[LLMCallRecord] = []
        self._client = None
        self._mode = self._detect_mode()

        logger.info("TrueFoundryGateway: initialized in %s mode", self._mode)

    def _detect_mode(self) -> str:
        """Determine which backend to use."""
        if TRUEFOUNDRY_API_KEY and TRUEFOUNDRY_ENDPOINT:
            return "truefoundry"
        if ANTHROPIC_API_KEY:
            return "anthropic"
        if OPENAI_API_KEY:
            return "openai"
        return "mock"

    def _get_client(self):
        """Lazy-init the OpenAI-compatible client for the active backend."""
        if self._client is not None:
            return self._client

        try:
            from openai import OpenAI
        except ImportError:
            logger.warning("TrueFoundryGateway: openai package not installed — using mock mode")
            self._mode = "mock"
            return None

        if self._mode == "truefoundry":
            self._client = OpenAI(
                api_key=TRUEFOUNDRY_API_KEY,
                base_url=TRUEFOUNDRY_ENDPOINT.rstrip("/") + "/v1",
            )
        elif self._mode == "anthropic":
            # Many Anthropic-compatible proxies expose an OpenAI-compatible
            # endpoint; TrueFoundry does this natively.
            self._client = OpenAI(
                api_key=ANTHROPIC_API_KEY,
                base_url="https://api.anthropic.com/v1",
            )
        elif self._mode == "openai":
            self._client = OpenAI(api_key=OPENAI_API_KEY)

        return self._client

    # ------------------------------------------------------------------
    # Core LLM call
    # ------------------------------------------------------------------

    def llm_call(
        self,
        prompt: str,
        severity: str = "routine",
        system_prompt: Optional[str] = None,
    ) -> dict:
        """Make an LLM call routed through the appropriate model tier.

        Args:
            prompt: User/agent prompt.
            severity: One of ``routine``, ``warning``, ``critical``.
            system_prompt: Optional system message prepended to the call.

        Returns:
            dict with ``response``, ``model``, ``severity``, ``tokens``,
            ``estimated_cost``, ``latency_ms``.
        """
        tier = MODEL_TIERS.get(severity, MODEL_TIERS["routine"])
        model = tier["model"]
        start = time.time()

        if self._mode == "mock":
            response_text = self._mock_response(severity)
            prompt_tok, comp_tok = len(prompt.split()) * 2, len(response_text.split()) * 2
        else:
            response_text, prompt_tok, comp_tok = self._live_call(
                model, prompt, system_prompt
            )

        latency_ms = (time.time() - start) * 1000
        estimated_cost = tier["cost_per_call"]

        record = LLMCallRecord(
            model=model,
            severity=severity,
            prompt_tokens=prompt_tok,
            completion_tokens=comp_tok,
            estimated_cost=estimated_cost,
            latency_ms=latency_ms,
        )
        self._call_log.append(record)

        logger.info(
            "TrueFoundryGateway: %s call via %s — %s tokens, $%.4f, %dms",
            severity,
            model,
            prompt_tok + comp_tok,
            estimated_cost,
            latency_ms,
        )

        return {
            "response": response_text,
            "model": model,
            "severity": severity,
            "tokens": {"prompt": prompt_tok, "completion": comp_tok},
            "estimated_cost": estimated_cost,
            "latency_ms": round(latency_ms, 1),
        }

    # ------------------------------------------------------------------
    # Specialized: incident diagnosis
    # ------------------------------------------------------------------

    def diagnose_incident(self, anomalies: list[dict], context: dict) -> dict:
        """Build a specialized diagnosis prompt and call the LLM.

        Args:
            anomalies: List of detected anomaly dicts.
            context: Additional context (service info, recent deployments, etc.).

        Returns:
            LLM call result dict (same shape as ``llm_call``).
        """
        # Determine severity from anomaly severity strings (from AnomalyDetector)
        severity_levels = {a.get("severity", "") for a in anomalies}
        if "critical" in severity_levels:
            severity = "critical"
        elif "warning" in severity_levels:
            severity = "warning"
        else:
            severity = "routine"

        system_prompt = (
            "You are SentinelCall, an autonomous SRE incident response agent. "
            "Analyze the following infrastructure anomalies and provide a "
            "structured diagnosis with timeline, root cause, impact assessment, "
            "and remediation plan. Be specific and actionable."
        )

        prompt = (
            f"## Detected Anomalies\n"
            f"{_format_anomalies(anomalies)}\n\n"
            f"## Context\n"
            f"Service: {context.get('service', 'unknown')}\n"
            f"Region: {context.get('region', 'unknown')}\n"
            f"Recent deployments: {context.get('recent_deployments', 'none')}\n"
            f"Current error rate: {context.get('error_rate', 'unknown')}\n"
            f"Affected users: {context.get('affected_users', 'unknown')}\n\n"
            f"Provide a full incident diagnosis."
        )

        return self.llm_call(prompt, severity=severity, system_prompt=system_prompt)

    # ------------------------------------------------------------------
    # Usage stats (for demo dashboard)
    # ------------------------------------------------------------------

    def get_usage_stats(self) -> dict:
        """Return model usage breakdown for dashboard display."""
        stats: dict = {
            "total_calls": len(self._call_log),
            "total_cost": 0.0,
            "total_tokens": 0,
            "by_severity": {},
            "by_model": {},
            "mode": self._mode,
            "call_log": [],
        }

        for rec in self._call_log:
            stats["total_cost"] += rec.estimated_cost
            stats["total_tokens"] += rec.prompt_tokens + rec.completion_tokens

            sev = stats["by_severity"].setdefault(rec.severity, {
                "calls": 0, "cost": 0.0, "tokens": 0,
            })
            sev["calls"] += 1
            sev["cost"] += rec.estimated_cost
            sev["tokens"] += rec.prompt_tokens + rec.completion_tokens

            mdl = stats["by_model"].setdefault(rec.model, {
                "calls": 0, "cost": 0.0, "tokens": 0,
            })
            mdl["calls"] += 1
            mdl["cost"] += rec.estimated_cost
            mdl["tokens"] += rec.prompt_tokens + rec.completion_tokens

            stats["call_log"].append({
                "model": rec.model,
                "severity": rec.severity,
                "tokens": rec.prompt_tokens + rec.completion_tokens,
                "cost": round(rec.estimated_cost, 4),
                "latency_ms": round(rec.latency_ms, 1),
                "timestamp": rec.timestamp,
            })

        stats["total_cost"] = round(stats["total_cost"], 4)
        return stats

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _live_call(
        self, model: str, prompt: str, system_prompt: Optional[str]
    ) -> tuple[str, int, int]:
        """Execute a live LLM call via the OpenAI-compatible client."""
        client = self._get_client()
        if client is None:
            text = self._mock_response("routine")
            return text, len(prompt.split()) * 2, len(text.split()) * 2

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=2048,
                temperature=0.3,
            )
            text = resp.choices[0].message.content or ""
            usage = resp.usage
            return (
                text,
                usage.prompt_tokens if usage else len(prompt.split()) * 2,
                usage.completion_tokens if usage else len(text.split()) * 2,
            )
        except Exception as exc:
            logger.error("TrueFoundryGateway: LLM call failed — %s", exc)
            text = self._mock_response("routine")
            return text, len(prompt.split()) * 2, len(text.split()) * 2

    def _mock_response(self, severity: str) -> str:
        """Return a realistic mock LLM response for demo."""
        return MOCK_RESPONSES.get(severity, MOCK_RESPONSES["routine"])


def _format_anomalies(anomalies: list[dict]) -> str:
    """Format anomaly list into a readable string for the LLM prompt."""
    lines = []
    for i, a in enumerate(anomalies, 1):
        lines.append(
            f"{i}. [{a.get('method', a.get('type', 'unknown'))}] "
            f"{a.get('service', 'unknown')}/{a.get('metric', 'N/A')}: "
            f"{a.get('message', a.get('description', 'No description'))} "
            f"(severity={a.get('severity', 'unknown')})"
        )
    return "\n".join(lines) if lines else "No anomalies provided."
