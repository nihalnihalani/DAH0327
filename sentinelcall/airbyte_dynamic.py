"""Dynamic Airbyte connector creation based on incident type.

This is the CREATIVE / non-obvious use of Airbyte: instead of pre-configuring
static connectors, the agent dynamically spins up new data sources mid-incident
to gather additional context relevant to the specific failure mode.

For example, a payment-service error triggers automatic creation of a Stripe
connector so the agent can inspect charges, disputes, and events — all without
any pre-existing configuration.

PyAirbyte API reference: https://airbytehq.github.io/PyAirbyte/airbyte.html
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

try:
    import airbyte as ab

    AIRBYTE_AVAILABLE = True
except ImportError:
    AIRBYTE_AVAILABLE = False
    logger.info("PyAirbyte not installed — dynamic connectors will use mock data")


# Maps incident types to the connector + streams that would be created.
CONNECTOR_RECIPES: dict[str, dict[str, Any]] = {
    "payment_service_error": {
        "source_name": "source-stripe",
        "display_name": "Stripe (dynamic — payment investigation)",
        "streams": ["charges", "disputes", "events", "balance_transactions"],
        "config_template": {
            "client_secret": "",  # Stripe API secret key
            "account_id": "",
            "start_date": "2023-01-01T00:00:00Z",
        },
        "rationale": (
            "Payment errors often correlate with upstream payment-provider "
            "issues. Pulling Stripe charges/disputes gives the agent direct "
            "evidence of failed transactions."
        ),
    },
    "database_connection_pool": {
        "source_name": "source-postgres",
        "display_name": "Postgres (dynamic — connection pool investigation)",
        "streams": ["pg_stat_activity", "pg_locks", "pg_stat_user_tables"],
        "config_template": {
            "host": "",
            "port": 5432,
            "database": "",
            "username": "",
            "password": "",
            "ssl_mode": {"mode": "prefer"},
        },
        "rationale": (
            "Connection-pool exhaustion is best diagnosed by looking at live "
            "Postgres activity and lock contention data directly."
        ),
    },
    "api_latency_spike": {
        "source_name": "source-github",
        "display_name": "GitHub (dynamic — deployment correlation)",
        "streams": ["deployments", "commits", "pull_requests", "workflow_runs"],
        "config_template": {
            "credentials": {
                "personal_access_token": "",
            },
            "repositories": [],
            "start_date": "2023-01-01T00:00:00Z",
        },
        "rationale": (
            "Latency spikes frequently follow new deployments. Pulling recent "
            "commits and deployment history helps the agent correlate timing."
        ),
    },
    "memory_leak": {
        "source_name": "source-datadog",
        "display_name": "Datadog (dynamic — memory profiling)",
        "streams": ["metrics", "events", "monitors"],
        "config_template": {
            "api_key": "",
            "application_key": "",
        },
        "rationale": (
            "Memory leaks need historical heap/GC metrics. Pulling from the "
            "observability platform gives the agent trend data for diagnosis."
        ),
    },
    "cache_failure": {
        "source_name": "source-faker",
        "display_name": "Simulated Redis (dynamic — cache investigation via faker)",
        "streams": ["users", "products", "purchases"],
        "config_template": {
            "count": 500,
            "seed": 99,
        },
        "rationale": (
            "Cache failures need Redis introspection. In demo mode, we use "
            "source-faker to simulate ingesting cache diagnostic data, "
            "demonstrating the dynamic connector creation pattern."
        ),
    },
}


class DynamicConnectorManager:
    """Creates and manages Airbyte connectors on-the-fly during incidents.

    The key insight: rather than pre-configuring every possible data source,
    the agent decides DURING an incident which additional data it needs and
    dynamically creates the appropriate connector to fetch it.

    PyAirbyte workflow for each dynamic connector:
    1. ab.get_source(name, config={...}, install_if_missing=True)
    2. source.check() to validate connectivity
    3. source.select_streams([...]) to choose relevant streams
    4. source.read() to sync data into local DuckDB cache
    5. read_result["stream"].to_pandas() to access data
    """

    def __init__(self) -> None:
        self.created_connectors: list[dict[str, Any]] = []
        self._investigation_data: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def dynamically_investigate(
        self, incident_type: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Create a new connector tailored to the incident and pull data.

        Args:
            incident_type: Key from CONNECTOR_RECIPES (e.g. "payment_service_error").
            context: Optional additional context with credential overrides
                     (e.g. {"client_secret": "sk_live_..."}).

        Returns:
            Dict with connector info, discovered streams, and investigation data.
        """
        context = context or {}
        recipe = CONNECTOR_RECIPES.get(incident_type)

        if recipe is None:
            logger.warning("No connector recipe for incident type: %s", incident_type)
            return {
                "status": "no_recipe",
                "incident_type": incident_type,
                "message": f"No dynamic connector recipe for '{incident_type}'",
            }

        logger.info(
            "Dynamically creating %s connector for %s investigation",
            recipe["source_name"],
            incident_type,
        )

        if AIRBYTE_AVAILABLE:
            return self._create_real_connector(incident_type, recipe, context)
        return self._create_mock_connector(incident_type, recipe, context)

    def discover_streams(self, source_name: str, config: dict[str, Any] | None = None) -> list[str]:
        """Discover available streams from a source.

        With real Airbyte, uses source.get_available_streams() which returns
        a list of stream name strings. In mock mode, returns recipe-defined streams.
        """
        if AIRBYTE_AVAILABLE and config:
            try:
                source = ab.get_source(
                    source_name,
                    config=config,
                    install_if_missing=True,
                )
                return source.get_available_streams()
            except Exception as exc:
                logger.warning("Stream discovery failed for %s: %s", source_name, exc)

        # Fall back to recipe-defined streams
        for recipe in CONNECTOR_RECIPES.values():
            if recipe["source_name"] == source_name:
                return recipe["streams"]
        return []

    def get_investigation_summary(self) -> dict[str, Any]:
        """Return a summary of all dynamic connectors created and data found."""
        return {
            "total_connectors_created": len(self.created_connectors),
            "connectors": [
                {
                    "source": c["source_name"],
                    "display_name": c["display_name"],
                    "incident_type": c["incident_type"],
                    "streams": c["streams"],
                    "created_at": c["created_at"],
                    "rationale": c["rationale"],
                }
                for c in self.created_connectors
            ],
            "investigation_data": self._investigation_data,
        }

    # ------------------------------------------------------------------
    # Real Airbyte path
    # ------------------------------------------------------------------

    def _create_real_connector(
        self,
        incident_type: str,
        recipe: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Create an actual Airbyte connector and read data.

        PyAirbyte real API:
        1. ab.get_source(name, config, install_if_missing=True)
        2. source.check()
        3. source.select_streams(stream_list)
        4. read_result = source.read()
        5. read_result["stream"].to_pandas() for data access
        """
        try:
            # Build config by merging template with runtime context overrides
            merged_config = {**recipe["config_template"]}
            for key, value in context.items():
                if key in merged_config and value:
                    merged_config[key] = value

            source = ab.get_source(
                recipe["source_name"],
                config=merged_config,
                install_if_missing=True,
            )
            source.check()

            # Select only the streams we need for this investigation
            available = source.get_available_streams()
            desired = [s for s in recipe["streams"] if s in available]
            if desired:
                source.select_streams(desired)
            else:
                source.select_all_streams()

            read_result = source.read()

            # Collect row counts per stream
            rows_read: dict[str, int] = {}
            for stream_name in read_result.streams:
                try:
                    df = read_result[stream_name].to_pandas()
                    rows_read[stream_name] = len(df)
                except Exception:
                    rows_read[stream_name] = 0

            record = {
                "source_name": recipe["source_name"],
                "display_name": recipe["display_name"],
                "incident_type": incident_type,
                "streams": list(read_result.streams.keys()) if hasattr(read_result.streams, 'keys') else desired,
                "rationale": recipe["rationale"],
                "created_at": time.time(),
                "status": "connected",
                "rows_read": rows_read,
            }
            self.created_connectors.append(record)

            return {
                "status": "connected",
                "connector": record,
                "data_available": True,
            }
        except Exception as exc:
            logger.warning(
                "Real connector creation failed for %s, falling back to mock: %s",
                recipe["source_name"],
                exc,
            )
            return self._create_mock_connector(incident_type, recipe, context)

    # ------------------------------------------------------------------
    # Mock connector path
    # ------------------------------------------------------------------

    def _create_mock_connector(
        self,
        incident_type: str,
        recipe: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Simulate connector creation and return realistic investigation data."""
        mock_data = self._generate_mock_investigation_data(incident_type, context)

        record = {
            "source_name": recipe["source_name"],
            "display_name": recipe["display_name"],
            "incident_type": incident_type,
            "streams": recipe["streams"],
            "rationale": recipe["rationale"],
            "created_at": time.time(),
            "status": "mock",
            "rows_read": {stream: len(mock_data.get(stream, [])) for stream in recipe["streams"]},
        }
        self.created_connectors.append(record)
        self._investigation_data[incident_type] = mock_data

        logger.info(
            "Mock connector created: %s (%d streams)",
            recipe["display_name"],
            len(recipe["streams"]),
        )

        return {
            "status": "mock",
            "connector": record,
            "data_available": True,
            "investigation_data": mock_data,
        }

    @staticmethod
    def _generate_mock_investigation_data(
        incident_type: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate realistic mock investigation data for each incident type."""
        now = time.time()

        if incident_type == "payment_service_error":
            return {
                "charges": [
                    {"id": "ch_3Ox9kL", "amount": 4999, "status": "failed",
                     "failure_code": "card_declined", "created": now - 120},
                    {"id": "ch_3Ox9mN", "amount": 12500, "status": "failed",
                     "failure_code": "processing_error", "created": now - 90},
                    {"id": "ch_3Ox9pQ", "amount": 7800, "status": "succeeded",
                     "created": now - 60},
                ],
                "disputes": [
                    {"id": "dp_1Kx4rT", "amount": 4999, "status": "needs_response",
                     "reason": "fraudulent", "created": now - 300},
                ],
                "events": [
                    {"id": "evt_1Ox9sV", "type": "charge.failed", "created": now - 120},
                    {"id": "evt_1Ox9uX", "type": "charge.failed", "created": now - 90},
                    {"id": "evt_1Ox9wZ", "type": "charge.succeeded", "created": now - 60},
                    {"id": "evt_1Ox9yB", "type": "payment_intent.payment_failed",
                     "created": now - 45},
                ],
                "summary": "67% charge failure rate in last 5 minutes. "
                           "Stripe processing_error suggests upstream provider issue.",
            }

        if incident_type == "database_connection_pool":
            return {
                "pg_stat_activity": [
                    {"pid": 14823, "state": "active", "query": "SELECT * FROM users WHERE...",
                     "wait_event": "Lock", "duration_sec": 45.2},
                    {"pid": 14891, "state": "active", "query": "UPDATE orders SET status...",
                     "wait_event": "Lock", "duration_sec": 38.7},
                    {"pid": 15002, "state": "idle in transaction",
                     "query": "BEGIN", "duration_sec": 120.5},
                ],
                "pg_locks": [
                    {"pid": 14823, "locktype": "relation", "mode": "AccessExclusiveLock",
                     "granted": True, "relation": "users"},
                    {"pid": 14891, "locktype": "relation", "mode": "RowExclusiveLock",
                     "granted": False, "relation": "orders"},
                ],
                "summary": "3 long-running queries detected. AccessExclusiveLock on 'users' "
                           "table blocking downstream queries. Idle transaction open for 120s.",
            }

        if incident_type == "api_latency_spike":
            return {
                "deployments": [
                    {"id": "dep_789", "sha": "a1b2c3d", "environment": "production",
                     "created_at": now - 600, "status": "success",
                     "description": "Deploy v2.14.3 — new caching layer"},
                    {"id": "dep_788", "sha": "e4f5g6h", "environment": "production",
                     "created_at": now - 7200, "status": "success",
                     "description": "Deploy v2.14.2 — minor fixes"},
                ],
                "commits": [
                    {"sha": "a1b2c3d", "message": "feat: add Redis caching to /api/users",
                     "author": "dev-jane", "timestamp": now - 900},
                    {"sha": "i7j8k9l", "message": "refactor: connection pool settings",
                     "author": "dev-bob", "timestamp": now - 1200},
                ],
                "pull_requests": [
                    {"number": 342, "title": "Add Redis caching layer",
                     "merged_at": now - 700, "author": "dev-jane",
                     "labels": ["performance", "caching"]},
                ],
                "summary": "Deploy v2.14.3 (10 min ago) introduced Redis caching. "
                           "PR #342 by dev-jane is the most likely cause of latency change.",
            }

        if incident_type == "memory_leak":
            return {
                "metrics": [
                    {"name": "system.mem.used", "value": 95.2, "timestamp": now},
                    {"name": "system.mem.used", "value": 88.1, "timestamp": now - 300},
                    {"name": "system.mem.used", "value": 76.4, "timestamp": now - 600},
                    {"name": "jvm.heap.used", "value": 92.8, "timestamp": now},
                ],
                "events": [
                    {"title": "OOM Kill", "text": "Process payment-worker killed by OOM",
                     "timestamp": now - 60},
                ],
                "summary": "Memory usage climbing steadily: 76% -> 88% -> 95% over 10 min. "
                           "JVM heap at 92.8%. OOM kill event 1 minute ago.",
            }

        if incident_type == "cache_failure":
            return {
                "info": {
                    "used_memory_human": "14.2G", "maxmemory_human": "16G",
                    "evicted_keys": 48231, "connected_clients": 847,
                    "rejected_connections": 152,
                },
                "slowlog": [
                    {"id": 1001, "duration_us": 250000, "command": "KEYS *",
                     "timestamp": now - 30},
                    {"id": 1000, "duration_us": 180000, "command": "SMEMBERS large_set",
                     "timestamp": now - 45},
                ],
                "summary": "Redis at 89% memory (14.2G/16G). 48K evicted keys, 152 rejected "
                           "connections. KEYS * command causing 250ms blocking.",
            }

        # Fallback for unknown incident types
        return {
            "summary": f"No specific investigation data for '{incident_type}'. "
                       "Generic monitoring data collected.",
        }
