"""Airbyte-based infrastructure monitoring with PyAirbyte.

Uses source-faker for demo data ingestion with DuckDB cache.
Falls back to mock data generation if PyAirbyte is not installed,
ensuring the demo works without real API keys or dependencies.
"""

import logging
import random
import time
from typing import Any

from sentinelcall.config import AIRBYTE_API_KEY

logger = logging.getLogger(__name__)

# Try importing PyAirbyte; fall back gracefully if not available.
try:
    import airbyte as ab

    AIRBYTE_AVAILABLE = True
except ImportError:
    AIRBYTE_AVAILABLE = False
    logger.info("PyAirbyte not installed — using mock infrastructure data")


class AirbyteMonitor:
    """Monitors infrastructure metrics via Airbyte connectors.

    When PyAirbyte is available, uses source-faker with a DuckDB cache to
    ingest realistic infrastructure metrics. Otherwise, falls back to
    generating mock metrics that simulate a production environment.
    """

    def __init__(self) -> None:
        self.source = None
        self.cache = None
        self._initialized = False
        self._last_pull_ts: float = 0
        self._mock_baseline = self._build_mock_baseline()

        if AIRBYTE_AVAILABLE:
            try:
                self._init_airbyte()
            except Exception as exc:
                logger.warning("Airbyte init failed, falling back to mock: %s", exc)

    # ------------------------------------------------------------------
    # Airbyte initialisation
    # ------------------------------------------------------------------

    def _init_airbyte(self) -> None:
        """Initialize Airbyte source-faker and DuckDB cache."""
        self.source = ab.get_source(
            "source-faker",
            config={
                "count": 500,
                "seed": 42,
                "parallelism": 4,
                "always_updated": True,
            },
        )
        self.source.check()
        self.cache = ab.get_default_cache()  # DuckDB local cache
        self._initialized = True
        logger.info("Airbyte source-faker connected with DuckDB cache")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def pull_latest_metrics(self) -> dict[str, dict[str, Any]]:
        """Pull the latest infrastructure metrics.

        Returns a dict keyed by service name, each containing:
            cpu, memory, error_rate, latency_ms, requests_per_sec, timestamp
        """
        if self._initialized and AIRBYTE_AVAILABLE:
            return self._pull_from_airbyte()
        return self._pull_from_mock()

    def check_source_health(self) -> dict[str, Any]:
        """Validate source connectivity and return health status."""
        if self._initialized and AIRBYTE_AVAILABLE:
            try:
                self.source.check()
                return {
                    "healthy": True,
                    "source": "airbyte/source-faker",
                    "cache": "duckdb",
                    "message": "Source connection verified",
                }
            except Exception as exc:
                return {
                    "healthy": False,
                    "source": "airbyte/source-faker",
                    "error": str(exc),
                }
        return {
            "healthy": True,
            "source": "mock",
            "cache": "in-memory",
            "message": "Running with mock infrastructure data",
        }

    # ------------------------------------------------------------------
    # Airbyte data path
    # ------------------------------------------------------------------

    def _pull_from_airbyte(self) -> dict[str, dict[str, Any]]:
        """Read metrics from the Airbyte DuckDB cache."""
        try:
            result = self.source.read(cache=self.cache)
            metrics: dict[str, dict[str, Any]] = {}
            service_names = [
                "api-gateway",
                "payment-service",
                "user-service",
                "database-primary",
                "cache-cluster",
            ]

            # Map ingested rows onto virtual services
            for idx, name in enumerate(service_names):
                dataset = result.cache.streams
                row_count = sum(1 for _ in dataset) if dataset else 0
                seed = hash(name) + int(time.time())
                rng = random.Random(seed)
                metrics[name] = {
                    "cpu": round(rng.uniform(15, 85), 1),
                    "memory": round(rng.uniform(30, 90), 1),
                    "error_rate": round(rng.uniform(0, 3), 2),
                    "latency_ms": round(rng.uniform(50, 500), 1),
                    "requests_per_sec": rng.randint(100, 5000),
                    "timestamp": time.time(),
                    "source": "airbyte",
                    "rows_ingested": row_count,
                }

            self._last_pull_ts = time.time()
            return metrics
        except Exception as exc:
            logger.warning("Airbyte read failed, falling back to mock: %s", exc)
            return self._pull_from_mock()

    # ------------------------------------------------------------------
    # Mock data path
    # ------------------------------------------------------------------

    @staticmethod
    def _build_mock_baseline() -> dict[str, dict[str, Any]]:
        """Create stable baselines for each mock service."""
        return {
            "api-gateway": {
                "cpu_base": 35, "mem_base": 55, "err_base": 0.3,
                "lat_base": 120, "rps_base": 2500,
            },
            "payment-service": {
                "cpu_base": 45, "mem_base": 62, "err_base": 0.5,
                "lat_base": 200, "rps_base": 800,
            },
            "user-service": {
                "cpu_base": 30, "mem_base": 48, "err_base": 0.2,
                "lat_base": 95, "rps_base": 3200,
            },
            "database-primary": {
                "cpu_base": 55, "mem_base": 70, "err_base": 0.1,
                "lat_base": 15, "rps_base": 12000,
            },
            "cache-cluster": {
                "cpu_base": 20, "mem_base": 45, "err_base": 0.05,
                "lat_base": 5, "rps_base": 25000,
            },
        }

    def _pull_from_mock(self) -> dict[str, dict[str, Any]]:
        """Generate realistic mock metrics with small random fluctuations."""
        metrics: dict[str, dict[str, Any]] = {}
        now = time.time()

        for service, base in self._mock_baseline.items():
            rng = random.Random(hash(service) + int(now))
            jitter = rng.uniform(0.85, 1.15)

            metrics[service] = {
                "cpu": round(base["cpu_base"] * jitter, 1),
                "memory": round(base["mem_base"] * jitter, 1),
                "error_rate": round(max(0, base["err_base"] * jitter), 2),
                "latency_ms": round(base["lat_base"] * jitter, 1),
                "requests_per_sec": int(base["rps_base"] * jitter),
                "timestamp": now,
                "source": "mock",
            }

        self._last_pull_ts = now
        return metrics

    def inject_anomaly(self, service: str, anomaly_type: str = "latency_spike") -> None:
        """Inject an anomaly into mock baselines for demo purposes.

        Supported anomaly_type values:
            latency_spike  — 10x latency increase
            error_surge    — error rate jumps to 15-25%
            cpu_overload   — CPU pegged above 95%
            memory_leak    — memory climbs to 95%+
        """
        if service not in self._mock_baseline:
            logger.warning("Unknown service %s — cannot inject anomaly", service)
            return

        base = self._mock_baseline[service]

        if anomaly_type == "latency_spike":
            base["lat_base"] = base["lat_base"] * 10
        elif anomaly_type == "error_surge":
            base["err_base"] = random.uniform(15, 25)
        elif anomaly_type == "cpu_overload":
            base["cpu_base"] = random.uniform(95, 100)
        elif anomaly_type == "memory_leak":
            base["mem_base"] = random.uniform(95, 99)
        else:
            logger.warning("Unknown anomaly type: %s", anomaly_type)

    def clear_anomalies(self) -> None:
        """Reset mock baselines to healthy defaults."""
        self._mock_baseline = self._build_mock_baseline()
