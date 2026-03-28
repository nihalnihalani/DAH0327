"""Simulated production infrastructure for demo purposes.

Provides a MockInfrastructure class that models five services with
realistic baseline metrics. Supports incident injection, resolution,
and timeline tracking for the live demo.
"""

import random
import time
from datetime import datetime, timezone
from typing import Any


# Default healthy baselines for each service
_DEFAULT_BASELINES: dict[str, dict[str, float]] = {
    "payment-service": {
        "error_rate": 0.3,
        "latency_ms": 180.0,
        "cpu": 42.0,
        "memory": 58.0,
        "db_connections": 25.0,
        "requests_per_sec": 820.0,
    },
    "user-service": {
        "error_rate": 0.2,
        "latency_ms": 95.0,
        "cpu": 30.0,
        "memory": 48.0,
        "db_connections": 15.0,
        "requests_per_sec": 3200.0,
    },
    "api-gateway": {
        "error_rate": 0.4,
        "latency_ms": 120.0,
        "cpu": 35.0,
        "memory": 55.0,
        "db_connections": 10.0,
        "requests_per_sec": 8500.0,
    },
    "notification-service": {
        "error_rate": 0.1,
        "latency_ms": 60.0,
        "cpu": 20.0,
        "memory": 35.0,
        "db_connections": 8.0,
        "requests_per_sec": 1200.0,
    },
    "database-primary": {
        "error_rate": 0.05,
        "latency_ms": 12.0,
        "cpu": 55.0,
        "memory": 70.0,
        "db_connections": 120.0,
        "requests_per_sec": 12000.0,
    },
}

# Anomalous metric overrides per incident type
_INCIDENT_PROFILES: dict[str, dict[str, float]] = {
    "payment_service_error": {
        "error_rate": 18.4,
        "latency_ms": 3100.0,
        "cpu": 92.0,
        "memory": 81.0,
        "db_connections": 95.0,
        "requests_per_sec": 320.0,
    },
    "api_latency_spike": {
        "error_rate": 12.1,
        "latency_ms": 4500.0,
        "cpu": 89.0,
        "memory": 72.0,
        "db_connections": 48.0,
        "requests_per_sec": 3400.0,
    },
    "database_connection_pool": {
        "error_rate": 8.7,
        "latency_ms": 2800.0,
        "cpu": 97.0,
        "memory": 94.0,
        "db_connections": 200.0,
        "requests_per_sec": 450.0,
    },
    "memory_leak": {
        "error_rate": 5.2,
        "latency_ms": 1900.0,
        "cpu": 78.0,
        "memory": 97.0,
        "db_connections": 30.0,
        "requests_per_sec": 600.0,
    },
    "cache_failure": {
        "error_rate": 14.8,
        "latency_ms": 2600.0,
        "cpu": 85.0,
        "memory": 88.0,
        "db_connections": 140.0,
        "requests_per_sec": 210.0,
    },
}


class MockInfrastructure:
    """Simulates a production environment with five services.

    Tracks healthy baselines, allows incident injection, and records a
    timeline of events for the demo dashboard.
    """

    def __init__(self) -> None:
        self._baselines = {
            svc: dict(metrics) for svc, metrics in _DEFAULT_BASELINES.items()
        }
        self._active_incident: dict[str, Any] | None = None
        self._incident_service: str | None = None
        self._timeline: list[dict[str, Any]] = []

        self._record_event("system_start", "All services initialized with healthy baselines")

    # ------------------------------------------------------------------
    # Incident lifecycle
    # ------------------------------------------------------------------

    def trigger_incident(
        self,
        service: str = "payment-service",
        incident_type: str = "payment_service_error",
    ) -> dict[str, Any]:
        """Inject anomalous metrics into *service*.

        Args:
            service: Target service name.
            incident_type: Key from ``_INCIDENT_PROFILES``.

        Returns:
            Dict describing the triggered incident.
        """
        profile = _INCIDENT_PROFILES.get(incident_type, _INCIDENT_PROFILES["payment_service_error"])

        if service not in self._baselines:
            service = "payment-service"

        self._active_incident = {
            "service": service,
            "incident_type": incident_type,
            "started_at": time.time(),
            "profile": profile,
        }
        self._incident_service = service

        # Overwrite the service baseline with incident metrics
        self._baselines[service] = dict(profile)

        self._record_event(
            "incident_triggered",
            f"Incident '{incident_type}' injected into {service}",
            service=service,
        )
        return {
            "service": service,
            "incident_type": incident_type,
            "started_at": self._active_incident["started_at"],
        }

    def resolve_incident(self) -> dict[str, Any]:
        """Restore the affected service to healthy baselines.

        Returns:
            Dict describing the resolution.
        """
        if not self._active_incident:
            return {"status": "no_active_incident"}

        service = self._active_incident["service"]
        duration = time.time() - self._active_incident["started_at"]

        # Restore healthy baselines
        self._baselines[service] = dict(_DEFAULT_BASELINES[service])
        resolved = {
            "service": service,
            "resolved_at": time.time(),
            "duration_seconds": round(duration, 1),
        }
        self._record_event(
            "incident_resolved",
            f"Incident resolved on {service} after {duration:.1f}s",
            service=service,
        )
        self._active_incident = None
        self._incident_service = None
        return resolved

    # ------------------------------------------------------------------
    # Metric queries
    # ------------------------------------------------------------------

    def get_metrics(self) -> dict[str, dict[str, Any]]:
        """Return current metrics for every service with small jitter."""
        now = time.time()
        result: dict[str, dict[str, Any]] = {}
        for service, base in self._baselines.items():
            rng = random.Random(hash(service) + int(now))
            jitter = rng.uniform(0.95, 1.05)
            result[service] = {
                metric: round(value * jitter, 2) for metric, value in base.items()
            }
            result[service]["timestamp"] = now
        return result

    def get_service_status(self, service: str) -> str:
        """Return ``healthy``, ``degraded``, or ``critical`` for *service*."""
        base = self._baselines.get(service)
        if base is None:
            return "unknown"

        error_rate = base.get("error_rate", 0)
        cpu = base.get("cpu", 0)
        memory = base.get("memory", 0)
        latency = base.get("latency_ms", 0)

        if error_rate > 10 or cpu > 90 or memory > 93 or latency > 3000:
            return "critical"
        if error_rate > 3 or cpu > 80 or memory > 80 or latency > 1500:
            return "degraded"
        return "healthy"

    def get_incident_timeline(self) -> list[dict[str, Any]]:
        """Return the ordered list of timestamped events."""
        return list(self._timeline)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_event(
        self, event_type: str, message: str, service: str | None = None
    ) -> None:
        self._timeline.append({
            "event_type": event_type,
            "message": message,
            "service": service,
            "timestamp": time.time(),
            "time_str": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        })
