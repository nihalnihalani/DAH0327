"""Statistical anomaly detection for infrastructure metrics.

Detects anomalies using threshold checks and statistical deviation.
Prepares structured anomaly data for LLM-based root cause analysis
(the actual LLM call happens in the agent via TrueFoundry — this
module only performs detection and formatting).
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Threshold definitions for each metric.
# warning = 2-sigma equivalent, critical = 3-sigma equivalent.
METRIC_THRESHOLDS: dict[str, dict[str, float]] = {
    "error_rate": {"warning": 5.0, "critical": 10.0},
    "latency_ms": {"warning": 2000.0, "critical": 5000.0},
    "cpu": {"warning": 85.0, "critical": 95.0},
    "memory": {"warning": 85.0, "critical": 95.0},
}

# Historical baselines (mean, stddev) used for statistical detection.
# In production these would be computed from a rolling window.
METRIC_BASELINES: dict[str, dict[str, float]] = {
    "cpu": {"mean": 40.0, "stddev": 12.0},
    "memory": {"mean": 55.0, "stddev": 10.0},
    "error_rate": {"mean": 0.5, "stddev": 0.8},
    "latency_ms": {"mean": 150.0, "stddev": 80.0},
    "requests_per_sec": {"mean": 3000.0, "stddev": 1500.0},
}


class AnomalyDetector:
    """Detects infrastructure anomalies using thresholds and statistical analysis.

    Works entirely with plain dicts and lists — no pandas or numpy required.
    """

    def __init__(
        self,
        thresholds: dict[str, dict[str, float]] | None = None,
        baselines: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self.thresholds = thresholds or METRIC_THRESHOLDS
        self.baselines = baselines or METRIC_BASELINES
        self._history: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Core detection
    # ------------------------------------------------------------------

    def detect_anomalies(self, metrics_data: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        """Scan all services for anomalies.

        Args:
            metrics_data: Dict keyed by service name, each value a dict of
                          metric_name → numeric_value (plus optional metadata).

        Returns:
            List of anomaly dicts, each containing:
                service, metric, value, threshold, severity,
                sigma (if statistical), method, timestamp
        """
        anomalies: list[dict[str, Any]] = []
        now = time.time()

        for service, metrics in metrics_data.items():
            # --- Threshold-based checks ---
            for metric, levels in self.thresholds.items():
                value = metrics.get(metric)
                if value is None:
                    continue

                if value >= levels["critical"]:
                    anomalies.append({
                        "service": service,
                        "metric": metric,
                        "value": value,
                        "threshold": levels["critical"],
                        "severity": "critical",
                        "method": "threshold",
                        "message": (
                            f"{service}/{metric} = {value} "
                            f"(critical threshold: {levels['critical']})"
                        ),
                        "timestamp": now,
                    })
                elif value >= levels["warning"]:
                    anomalies.append({
                        "service": service,
                        "metric": metric,
                        "value": value,
                        "threshold": levels["warning"],
                        "severity": "warning",
                        "method": "threshold",
                        "message": (
                            f"{service}/{metric} = {value} "
                            f"(warning threshold: {levels['warning']})"
                        ),
                        "timestamp": now,
                    })

            # --- Statistical (z-score) checks ---
            for metric, baseline in self.baselines.items():
                value = metrics.get(metric)
                if value is None or baseline["stddev"] == 0:
                    continue

                z_score = abs(value - baseline["mean"]) / baseline["stddev"]

                if z_score >= 3.0:
                    severity = "critical"
                elif z_score >= 2.0:
                    severity = "warning"
                else:
                    continue

                # Avoid duplicate if threshold already caught this
                already_reported = any(
                    a["service"] == service and a["metric"] == metric
                    for a in anomalies
                )
                if already_reported:
                    continue

                anomalies.append({
                    "service": service,
                    "metric": metric,
                    "value": value,
                    "baseline_mean": baseline["mean"],
                    "baseline_stddev": baseline["stddev"],
                    "z_score": round(z_score, 2),
                    "sigma": round(z_score, 1),
                    "severity": severity,
                    "method": "statistical",
                    "message": (
                        f"{service}/{metric} = {value} "
                        f"({z_score:.1f}σ from mean {baseline['mean']})"
                    ),
                    "timestamp": now,
                })

        # Store in history for trend analysis
        if anomalies:
            self._history.append({
                "timestamp": now,
                "count": len(anomalies),
                "anomalies": anomalies,
            })

        return anomalies

    # ------------------------------------------------------------------
    # Severity classification
    # ------------------------------------------------------------------

    @staticmethod
    def classify_severity(anomalies: list[dict[str, Any]]) -> str:
        """Classify the overall incident severity from a list of anomalies.

        Returns:
            "critical" — any critical anomaly present
            "warning"  — only warning-level anomalies
            "routine"  — no anomalies detected
        """
        if not anomalies:
            return "routine"

        severities = {a.get("severity") for a in anomalies}

        if "critical" in severities:
            return "critical"
        if "warning" in severities:
            return "warning"
        return "routine"

    # ------------------------------------------------------------------
    # Formatting for LLM consumption
    # ------------------------------------------------------------------

    @staticmethod
    def format_for_diagnosis(anomalies: list[dict[str, Any]]) -> str:
        """Format anomalies into a structured text block for LLM root-cause analysis.

        The output is designed to be appended to a system or user prompt
        that asks the LLM to diagnose the incident.
        """
        if not anomalies:
            return "No anomalies detected. All services operating within normal parameters."

        severity = AnomalyDetector.classify_severity(anomalies)
        critical = [a for a in anomalies if a["severity"] == "critical"]
        warnings = [a for a in anomalies if a["severity"] == "warning"]

        lines: list[str] = []
        lines.append(f"=== ANOMALY REPORT ===")
        lines.append(f"Overall severity: {severity.upper()}")
        lines.append(f"Total anomalies: {len(anomalies)} "
                      f"({len(critical)} critical, {len(warnings)} warning)")
        lines.append("")

        # Group by service
        services: dict[str, list[dict[str, Any]]] = {}
        for a in anomalies:
            services.setdefault(a["service"], []).append(a)

        for service, service_anomalies in services.items():
            lines.append(f"--- {service} ---")
            for a in service_anomalies:
                icon = "CRITICAL" if a["severity"] == "critical" else "WARNING"
                lines.append(f"  [{icon}] {a['message']}")
                if a["method"] == "statistical":
                    lines.append(
                        f"           (z-score: {a.get('z_score', 'N/A')}, "
                        f"baseline mean: {a.get('baseline_mean', 'N/A')})"
                    )
            lines.append("")

        lines.append("=== END ANOMALY REPORT ===")
        lines.append("")
        lines.append(
            "Based on the anomalies above, identify the most likely root cause, "
            "affected services, and recommended remediation steps."
        )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def get_anomaly_history(self) -> list[dict[str, Any]]:
        """Return historical anomaly snapshots for trend analysis."""
        return list(self._history)

    def clear_history(self) -> None:
        """Clear the anomaly history."""
        self._history.clear()
