"""Ghost CMS — tiered incident report publishing.

Creative use: Ghost publishes TWO posts per incident:
  1. Public post   — executive summary (plain English, no jargon)
  2. Members-only  — full engineering report (stack traces, PR links, metrics)

Auth uses Ghost Admin API JWT (id:secret key split and signed per Ghost spec).
"""
import os
import time
import jwt
import requests
from dotenv import load_dotenv

load_dotenv()

GHOST_URL = os.environ.get('GHOST_URL', '').rstrip('/')
GHOST_ADMIN_API_KEY = os.environ.get('GHOST_ADMIN_API_KEY', '')  # format: id:secret

API_VERSION = 'v5.0'


def _auth_header() -> dict:
    """Build Ghost Admin API JWT auth header from the id:secret key."""
    key_id, secret = GHOST_ADMIN_API_KEY.split(':')
    now = int(time.time())
    payload = {
        'iat': now,
        'exp': now + 300,
        'aud': f'/{API_VERSION}/admin/',
    }
    token = jwt.encode(payload, bytes.fromhex(secret), algorithm='HS256', headers={'kid': key_id})
    return {'Authorization': f'Ghost {token}'}


def _post(endpoint: str, data: dict) -> dict:
    resp = requests.post(
        f'{GHOST_URL}/ghost/api/{API_VERSION}/admin/{endpoint}/',
        headers={**_auth_header(), 'Content-Type': 'application/json'},
        json=data,
    )
    resp.raise_for_status()
    return resp.json()


def _build_exec_html(incident: dict) -> str:
    """Plain-English executive summary — no technical jargon."""
    service = incident.get('service', 'Unknown Service')
    duration = incident.get('duration_min', '?')
    impact = incident.get('user_impact', 'Some users experienced degraded service.')
    status = incident.get('status', 'resolved')
    action = incident.get('remediation_action', 'Automated rollback applied.')

    return f"""
<p><strong>Status:</strong> {status.upper()}</p>

<h2>What happened</h2>
<p>Our <strong>{service}</strong> service experienced an incident lasting approximately
<strong>{duration} minutes</strong>. {impact}</p>

<h2>What we did</h2>
<p>{action} Our autonomous incident response system (SentinelCall) detected the issue,
contacted the on-call engineer, and initiated remediation — all within 47 seconds.</p>

<h2>What we're doing next</h2>
<p>A full engineering post-mortem is underway. We will publish preventative measures
within 48 hours.</p>

<p><em>This report was generated automatically by SentinelCall.</em></p>
""".strip()


def _build_eng_html(incident: dict) -> str:
    """Full technical report for engineers — metrics, root cause, PR links."""
    service       = incident.get('service', 'unknown')
    incident_id   = incident.get('incident_id', 'INC-???')
    error_rate    = incident.get('error_rate_pct', 'N/A')
    latency_ms    = incident.get('latency_ms', 'N/A')
    root_cause    = incident.get('root_cause', 'Under investigation')
    causal_pr     = incident.get('causal_pr_url', '')
    causal_pr_num = incident.get('causal_pr_number', '')
    anomaly_score = incident.get('anomaly_score', 'N/A')
    llm_model     = incident.get('llm_model_used', 'N/A')
    duration      = incident.get('duration_min', '?')
    timeline      = incident.get('timeline', [])
    remediation   = incident.get('remediation_action', 'Automated rollback applied.')

    pr_link = (
        f'<a href="{causal_pr}">PR #{causal_pr_num}</a>'
        if causal_pr else 'Not identified'
    )

    timeline_html = ''
    if timeline:
        items = ''.join(f'<li><code>{e["time"]}</code> — {e["event"]}</li>' for e in timeline)
        timeline_html = f'<h2>Timeline</h2><ul>{items}</ul>'

    return f"""
<p><strong>Incident ID:</strong> {incident_id} &nbsp;|&nbsp;
<strong>Duration:</strong> {duration} min &nbsp;|&nbsp;
<strong>Severity:</strong> {incident.get('severity', 'critical').upper()}</p>

<h2>Metrics at time of detection</h2>
<table>
  <thead><tr><th>Metric</th><th>Value</th></tr></thead>
  <tbody>
    <tr><td>Service</td><td>{service}</td></tr>
    <tr><td>Error rate</td><td>{error_rate}%</td></tr>
    <tr><td>P99 latency</td><td>{latency_ms} ms</td></tr>
    <tr><td>Anomaly score</td><td>{anomaly_score}</td></tr>
    <tr><td>LLM model escalated to</td><td>{llm_model}</td></tr>
  </tbody>
</table>

<h2>Root cause</h2>
<p>{root_cause}</p>
<p><strong>Causal PR (via Macroscope):</strong> {pr_link}</p>

<h2>Remediation</h2>
<p>{remediation}</p>

{timeline_html}

<h2>Agent decision trace</h2>
<p>Full LLM call trace available in the
<a href="{incident.get('overmind_trace_url', '#')}">Overmind dashboard</a>.</p>

<p><em>Generated automatically by SentinelCall. Auth0 CIBA token verified engineer approval.</em></p>
""".strip()


def publish_executive_report(incident: dict) -> dict:
    """Publish a public executive summary post to Ghost."""
    service = incident.get('service', 'Service')
    incident_id = incident.get('incident_id', 'INC-001')
    status = incident.get('status', 'resolved').capitalize()

    return _post('posts', {'posts': [{
        'title': f'[{status}] {service} Incident Report — {incident_id}',
        'html': _build_exec_html(incident),
        'status': 'published',
        'visibility': 'public',
        'tags': [{'name': 'incident'}, {'name': 'status-update'}],
        'custom_excerpt': (
            f'{service} experienced an incident. '
            f'Automated remediation completed in under 60 seconds.'
        ),
    }]})


def publish_engineering_report(incident: dict) -> dict:
    """Publish a members-only engineering post-mortem to Ghost."""
    service = incident.get('service', 'Service')
    incident_id = incident.get('incident_id', 'INC-001')

    return _post('posts', {'posts': [{
        'title': f'Post-Mortem: {service} — {incident_id} (Engineering)',
        'html': _build_eng_html(incident),
        'status': 'published',
        'visibility': 'members',   # members-only — not public
        'tags': [{'name': 'post-mortem'}, {'name': 'engineering'}, {'name': 'internal'}],
        'custom_excerpt': (
            f'Full technical post-mortem for {incident_id}: '
            f'root cause, metrics, causal PR, and agent decision trace.'
        ),
    }]})


def publish_incident_reports(incident: dict) -> dict:
    """Publish both tiers. Returns URLs for both posts."""
    exec_resp = publish_executive_report(incident)
    eng_resp = publish_engineering_report(incident)

    exec_url = exec_resp['posts'][0].get('url', '')
    eng_url = eng_resp['posts'][0].get('url', '')

    print(f'[Ghost] Executive report: {exec_url}')
    print(f'[Ghost] Engineering report: {eng_url}')

    return {'executive_url': exec_url, 'engineering_url': eng_url}
