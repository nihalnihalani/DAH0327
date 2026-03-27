"""TrueFoundry AI Gateway — dynamic model escalation by incident severity.

Creative use: instead of hardcoding a single LLM, SentinelCall escalates
through a tiered model ladder based on anomaly severity score:

  low    → claude-haiku-4-5   (fast, cheap — routine noise)
  medium → claude-sonnet-4-5  (balanced — real but minor incident)
  high   → claude-opus-4-5    (powerful — major outage / exec comms)

All LLM calls route through TrueFoundry gateway — never call Anthropic directly.
"""
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

TRUEFOUNDRY_API_KEY = os.environ.get('TRUEFOUNDRY_API_KEY', '')
TRUEFOUNDRY_ENDPOINT = os.environ.get(
    'TRUEFOUNDRY_ENDPOINT', 'https://gateway.truefoundry.ai'
).rstrip('/')

# Model ladder: severity → TrueFoundry model name
MODEL_LADDER = {
    'low':      'anthropic-main/claude-haiku-4-5-20251001',
    'medium':   'anthropic-main/claude-sonnet-4-5-20251001',
    'high':     'anthropic-main/claude-opus-4-5-20251001',
    'critical': 'anthropic-main/claude-opus-4-5-20251001',
}

# Anomaly score thresholds → severity
def _score_to_severity(score: float) -> str:
    if score < 0.4:
        return 'low'
    if score < 0.7:
        return 'medium'
    if score < 0.9:
        return 'high'
    return 'critical'


def _client() -> OpenAI:
    return OpenAI(
        api_key=TRUEFOUNDRY_API_KEY,
        base_url=f'{TRUEFOUNDRY_ENDPOINT}',
    )


def call_llm(
    prompt: str,
    severity: str = 'medium',
    system: str = 'You are SentinelCall, an autonomous SRE incident response agent.',
    max_tokens: int = 1024,
) -> str:
    """Call the LLM via TrueFoundry gateway, auto-selecting model by severity.

    Args:
        prompt: User message / task for the LLM.
        severity: 'low' | 'medium' | 'high' | 'critical'
        system: System prompt override.
        max_tokens: Max response tokens.

    Returns:
        LLM response text.
    """
    model = MODEL_LADDER.get(severity, MODEL_LADDER['medium'])
    client = _client()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': prompt},
        ],
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def call_llm_by_score(prompt: str, anomaly_score: float, **kwargs) -> tuple[str, str]:
    """Call LLM with model auto-selected from anomaly score.

    Returns:
        (response_text, model_used) — model name is saved to incident dict
        so Ghost engineering report can show which model was escalated to.
    """
    severity = _score_to_severity(anomaly_score)
    model = MODEL_LADDER[severity]
    text = call_llm(prompt, severity=severity, **kwargs)
    return text, model


def diagnose_anomaly(metrics: dict, anomaly_score: float) -> str:
    """Ask the LLM to diagnose an anomaly, escalating model by score."""
    prompt = f"""Analyze this infrastructure anomaly and provide a concise root cause hypothesis.

Anomaly score: {anomaly_score:.2f}
Metrics snapshot:
{_fmt_metrics(metrics)}

Respond in 3 sentences max: what failed, why, and what the fix likely is."""

    text, model = call_llm_by_score(prompt, anomaly_score)
    print(f'[TrueFoundry] Diagnosed with {model} (score={anomaly_score:.2f})')
    return text


def generate_exec_summary(incident: dict) -> str:
    """Generate plain-English executive summary via the gateway."""
    prompt = f"""Write a 2-sentence executive summary of this incident for non-technical stakeholders.
Be reassuring but honest. No jargon.

Service: {incident.get('service')}
Duration: {incident.get('duration_min')} minutes
Root cause: {incident.get('root_cause')}
Resolution: {incident.get('remediation_action')}"""

    return call_llm(prompt, severity=incident.get('severity', 'medium'), max_tokens=200)


def _fmt_metrics(metrics: dict) -> str:
    return '\n'.join(f'  {k}: {v}' for k, v in metrics.items())
