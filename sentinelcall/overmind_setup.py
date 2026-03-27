"""Overmind — zero-code LLM observability for SentinelCall.

One call to overmind.init() auto-instruments every LLM call that routes
through TrueFoundry gateway — no proxy, no key sharing, no import changes.
The Overmind dashboard shows the full agent decision trace: which model was
escalated to, token costs, latency, and prompt/response for each step.
"""
import os
import overmind
from dotenv import load_dotenv

load_dotenv()


def init_overmind() -> None:
    """Initialize Overmind auto-instrumentation.

    Call this once at agent startup — before any LLM calls are made.
    All subsequent openai/anthropic SDK calls are traced automatically.
    """
    api_key = os.environ.get('OVERMIND_API_KEY', '')
    if not api_key:
        print('[Overmind] OVERMIND_API_KEY not set — skipping instrumentation')
        return

    overmind.init(
        overmind_api_key=api_key,
        service_name='sentinelcall',
        environment=os.environ.get('ENVIRONMENT', 'production'),
    )
    print('[Overmind] Auto-instrumentation active — all LLM calls will be traced')


def get_trace_url(incident_id: str) -> str:
    """Return the Overmind dashboard URL for a specific incident trace.

    The trace URL is embedded in Ghost engineering reports so engineers
    can click through to the full LLM decision trace.
    """
    workspace = os.environ.get('OVERMIND_WORKSPACE', 'sentinelcall')
    return f'https://app.overmind.ai/{workspace}/traces?filter={incident_id}'
