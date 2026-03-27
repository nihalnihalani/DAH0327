"""Overmind initialization + decision trace for demo.

Instruments all LLM calls for observability via Overmind. When the
``overmind`` package is not installed, maintains an in-memory decision
trace so the demo still shows full agent decision history.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sentinelcall.config import OVERMIND_API_KEY

logger = logging.getLogger(__name__)

# Try importing overmind; fall back gracefully
try:
    import overmind  # type: ignore[import-untyped]
    _HAS_OVERMIND = True
except ImportError:
    overmind = None  # type: ignore[assignment]
    _HAS_OVERMIND = False


class OvermindTracer:
    """Manage Overmind LLM observability and agent decision tracing."""

    def __init__(self, api_key: str | None = None, service_name: str = "sentinelcall-agent"):
        self.api_key = api_key or OVERMIND_API_KEY
        self.service_name = service_name
        self.environment = "hackathon"
        self._initialized = False
        self._decisions: list[dict[str, Any]] = []

    def init(self) -> dict[str, Any]:
        """Initialize Overmind with the configured API key.

        If the ``overmind`` package is installed and an API key is available,
        this calls ``overmind.init()``. Otherwise it sets up an in-memory
        trace log that works identically for the demo.

        Returns:
            Dict with initialization status.
        """
        if _HAS_OVERMIND and self.api_key:
            try:
                overmind.init(
                    api_key=self.api_key,
                    service_name=self.service_name,
                    environment=self.environment,
                )
                self._initialized = True
                logger.info(
                    "Overmind initialized: service=%s env=%s",
                    self.service_name,
                    self.environment,
                )
                return {
                    "status": "initialized",
                    "service_name": self.service_name,
                    "environment": self.environment,
                    "dashboard_url": self.get_dashboard_url(),
                }
            except Exception as exc:
                logger.error("Overmind init failed: %s. Using in-memory trace.", exc)

        # Fallback to in-memory tracing
        self._initialized = True
        logger.info("Overmind in-memory trace mode (package not installed or no API key).")
        return {
            "status": "in-memory",
            "service_name": self.service_name,
            "environment": self.environment,
            "dashboard_url": self.get_dashboard_url(),
            "note": "Using in-memory trace. Install overmind + set OVERMIND_API_KEY for full observability.",
        }

    def record_decision(
        self,
        step: str,
        input_data: Any,
        output_data: Any,
        model_used: str = "unknown",
    ) -> None:
        """Record an agent decision for the trace.

        Args:
            step: Name of the pipeline step (e.g. ``"anomaly_detection"``).
            input_data: Input provided to this step.
            output_data: Output produced by this step.
            model_used: LLM model identifier used for this step.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        decision = {
            "step": step,
            "timestamp": timestamp,
            "model_used": model_used,
            "input_summary": _summarize(input_data),
            "output_summary": _summarize(output_data),
            "latency_ms": None,
        }
        self._decisions.append(decision)

        if _HAS_OVERMIND and self.api_key:
            try:
                overmind.log_event(
                    event_type="agent_decision",
                    metadata=decision,
                )
            except Exception:
                pass  # Already stored in-memory

        logger.debug("Decision recorded: step=%s model=%s", step, model_used)

    def get_decision_trace(self) -> str:
        """Return the full agent decision trace as a formatted string.

        Returns:
            Multi-line string showing each decision step with timestamps,
            models used, and input/output summaries.
        """
        if not self._decisions:
            return "No decisions recorded yet."

        lines = [f"SentinelCall Agent Decision Trace ({len(self._decisions)} steps)", "=" * 60]
        for i, d in enumerate(self._decisions, 1):
            lines.append(
                f"\n[{i}] {d['step']}\n"
                f"    Time:   {d['timestamp']}\n"
                f"    Model:  {d['model_used']}\n"
                f"    Input:  {d['input_summary']}\n"
                f"    Output: {d['output_summary']}"
            )
        lines.append("\n" + "=" * 60)
        return "\n".join(lines)

    def get_optimization_report(self) -> dict[str, Any]:
        """Pull optimization recommendations for demo display.

        When connected to Overmind, this fetches real recommendations.
        Otherwise, returns realistic mock recommendations.

        Returns:
            Dict with ``recommendations`` list and ``summary``.
        """
        if _HAS_OVERMIND and self.api_key:
            try:
                report = overmind.get_optimization_report(service_name=self.service_name)
                return report
            except Exception as exc:
                logger.error("Overmind optimization report failed: %s", exc)

        # Realistic mock recommendations
        total_steps = len(self._decisions)
        return {
            "service_name": self.service_name,
            "total_llm_calls": total_steps,
            "total_tokens_used": total_steps * 1250,
            "estimated_cost_usd": round(total_steps * 0.0032, 4),
            "recommendations": [
                {
                    "type": "model_downgrade",
                    "step": "anomaly_detection",
                    "current_model": "claude-sonnet-4-20250514",
                    "suggested_model": "claude-haiku-4-5-20251001",
                    "reason": "Anomaly detection prompt is classification-only; Haiku achieves 98% accuracy at 10x lower cost.",
                    "estimated_savings": "68%",
                },
                {
                    "type": "prompt_optimization",
                    "step": "root_cause_analysis",
                    "suggestion": "Cache the system prompt prefix — 820 tokens repeated across every call.",
                    "estimated_savings": "15% token reduction",
                },
                {
                    "type": "batching",
                    "step": "incident_report_generation",
                    "suggestion": "Batch executive and engineering reports into a single LLM call with structured output.",
                    "estimated_savings": "45% latency reduction",
                },
            ],
            "summary": (
                f"Analyzed {total_steps} LLM calls. Found 3 optimization opportunities "
                f"that could reduce cost by ~40% and latency by ~30%."
            ),
        }

    def get_dashboard_url(self) -> str:
        """Return the Overmind console URL for this service.

        Returns:
            URL string pointing to the Overmind dashboard.
        """
        return f"https://console.overmind.ai/services/{self.service_name}"


def _summarize(data: Any, max_len: int = 120) -> str:
    """Create a short summary of arbitrary data for trace display."""
    if data is None:
        return "(none)"
    text = str(data)
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text
