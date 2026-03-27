"""Airbyte-based infrastructure metrics ingestion for SentinelCall."""
import os
import random
from datetime import datetime, timezone

import airbyte as ab
from dotenv import load_dotenv

load_dotenv()

_cache = None


def get_cache():
    global _cache
    if _cache is None:
        _cache = ab.get_default_cache()
    return _cache


def ingest_metrics() -> list[dict]:
    """
    Pull simulated infrastructure metrics via Airbyte source-faker.
    Returns a list of metric records for anomaly detection.
    """
    source = ab.get_source(
        'source-faker',
        config={'count': 100, 'seed': int(datetime.now(timezone.utc).timestamp()) % 1000},
        install_if_missing=True,
    )
    source.check()
    result = source.read(cache=get_cache())

    # Map faker records to metric-shaped dicts for the anomaly detector
    metrics = []
    for stream_name, dataset in result.items():
        for record in dataset:
            metrics.append({
                'source': stream_name,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'record': dict(record),
            })
        break  # One stream is enough for the demo

    return metrics


def ingest_mock_infra_metrics(inject_anomaly: bool = False) -> list[dict]:
    """
    Generate realistic infrastructure metrics.
    If inject_anomaly=True, spike one service to trigger the agent.
    """
    services = ['payment-service', 'auth-service', 'api-gateway', 'database', 'cache']
    metrics = []

    for service in services:
        base_error_rate = random.uniform(0.1, 0.5)
        base_latency = random.uniform(50, 150)
        base_cpu = random.uniform(20, 60)

        if inject_anomaly and service == 'payment-service':
            error_rate = random.uniform(15.0, 25.0)   # spike
            latency = random.uniform(2000, 5000)        # spike
            cpu = random.uniform(85, 99)                # spike
        else:
            error_rate = base_error_rate
            latency = base_latency
            cpu = base_cpu

        metrics.append({
            'service': service,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'error_rate_pct': round(error_rate, 2),
            'latency_ms': round(latency, 1),
            'cpu_pct': round(cpu, 1),
            'requests_per_sec': random.randint(100, 1000),
        })

    return metrics


def dynamically_investigate(incident_type: str, context: dict) -> dict:
    """
    Dynamically spin up a new Airbyte source based on incident type.
    This is the creative/non-obvious usage: agent creates connectors on-the-fly.
    """
    cache = get_cache()

    if incident_type == 'api_latency_spike':
        # Spin up a second faker source as a stand-in for GitHub deploy data
        source = ab.get_source(
            'source-faker',
            config={'count': 20, 'seed': 99},
            install_if_missing=True,
        )
        source.check()
        available = source.get_available_streams()
        source.select_streams(available)
        result = source.read(cache=cache)
        streams = list(result.keys())
        return {
            'connector': 'source-faker (GitHub proxy)',
            'streams_discovered': streams,
            'finding': 'Recent deploy detected 4 minutes before latency spike — likely causal.',
            'raw_stream_count': len(streams),
        }

    # Default: return a summary of what we would have connected
    return {
        'connector': f'dynamic-connector-for-{incident_type}',
        'streams_discovered': ['events', 'logs', 'metrics'],
        'finding': f'Dynamic investigation complete for {incident_type}.',
    }


if __name__ == '__main__':
    print('Testing Airbyte ingest...')
    metrics = ingest_mock_infra_metrics(inject_anomaly=True)
    for m in metrics:
        flag = ' <-- ANOMALY' if m['error_rate_pct'] > 5 else ''
        print(f"  {m['service']}: error={m['error_rate_pct']}% latency={m['latency_ms']}ms cpu={m['cpu_pct']}%{flag}")

    print('\nTesting dynamic connector...')
    result = dynamically_investigate('api_latency_spike', {})
    print(f"  Connector: {result['connector']}")
    print(f"  Finding: {result['finding']}")
    print('\nAirbyte OK')
