# Page0 — Autonomous Incident Response Agent

## Deep Agents Hackathon | March 27, 2026 | Deadline: 4:30 PM PDT

### One-liner
An autonomous SRE agent that monitors infrastructure, detects anomalies, diagnoses root cause, CALLS the on-call engineer with an interactive voice briefing, and publishes tiered incident reports — all without human intervention.

---

## Time Budget

| Block | Duration | Notes |
|---|---|---|
| Setup (API keys, accounts, env) | 30 min | Do ALL signups in parallel |
| Core coding | 150 min | The build |
| Demo recording | 30 min | 3-minute video |
| Devpost + GitHub cleanup | 20 min | Submission |
| Buffer | 10 min | Murphy's law |
| **TOTAL** | **~4 hrs** | |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                            Page0 Agent                              │
│                                                                     │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────┐              │
│  │ Airbyte  │───▶│ Anomaly      │───▶│ Root Cause   │              │
│  │ Dynamic  │    │ Detection    │    │ Diagnosis    │              │
│  │ Ingest   │    │ Engine       │    │ (LLM via     │              │
│  │          │    │              │    │ TrueFoundry) │              │
│  └──────────┘    └──────────────┘    └──────┬───────┘              │
│                                             │                       │
│                              ┌──────────────┼──────────────┐       │
│                              ▼              ▼              ▼       │
│                     ┌──────────────┐ ┌────────────┐ ┌──────────┐  │
│                     │ Bland AI     │ │ Ghost CMS  │ │Macroscope│  │
│                     │ Phone Call   │ │ Incident   │ │ PR Root  │  │
│                     │ (Interactive │ │ Report     │ │ Cause ID │  │
│                     │  + CIBA auth)│ │ (Tiered)   │ │          │  │
│                     └──────────────┘ └────────────┘ └──────────┘  │
│                              │                                      │
│                     ┌──────────────┐                               │
│                     │ Auth0 CIBA   │                               │
│                     │ Approval     │◀── Engineer voice confirms    │
│                     │ Flow         │    remediation via phone      │
│                     └──────────────┘                               │
│                                                                     │
│  ┌──────────┐    ┌──────────────┐                                  │
│  │ Overmind │    │ TrueFoundry  │                                  │
│  │ Tracing  │    │ AI Gateway   │                                  │
│  │ + Optim  │    │ Model Escal. │                                  │
│  └──────────┘    └──────────────┘                                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Prize Targets

| Tool | Prize | Type | Our Integration |
|---|---|---|---|
| Auth0 | $1,000 1st | Amazon GC | CIBA + Token Vault (creative) |
| Airbyte | $1,000 1st | Visa GC | Dynamic connector orchestration (creative) |
| Ghost | $2,000 (4×$500) | Visa | Tiered incident reports + webhooks (creative) |
| Macroscope | $1,000 1st | Cash | PR-linked root cause identification (creative) |
| Overmind | $651 1st | Cash | Live prompt optimization (creative) |
| TrueFoundry | $600 1st | Cash | Dynamic model escalation + guardrails (creative) |
| Bland | $500 1st | Cash | Interactive two-way diagnosis + function calling (creative) |
| **TOTAL** | **$6,751** | | |

---

## PHASE 0: Environment Setup (30 min — ALL IN PARALLEL)

### 0.1 Account Creation (Person A — 15 min)
- [ ] Sign up for Auth0 tenant → get `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`
- [ ] Sign up for Bland AI → get `BLAND_API_KEY`
- [ ] Sign up for Ghost(Pro) trial OR spin up Ghost Docker container
- [ ] Get Ghost Admin API key (format: `{id}:{secret}`)

### 0.2 Account Creation (Person B — 15 min)
- [ ] Sign up for TrueFoundry → get gateway endpoint + API key
- [ ] Sign up for Overmind → get `OVERMIND_API_KEY` from console.overmindlab.ai
- [ ] Install Macroscope GitHub App on the hackathon repo
- [ ] Sign up for Airbyte Cloud OR install PyAirbyte locally

### 0.3 Project Scaffold (Person C — 15 min)
```bash
mkdir sentinelcall && cd sentinelcall
python -m venv .venv && source .venv/bin/activate
pip install airbyte auth0-python bland-ai ghost-admin-api overmind truefoundry-sdk
# OR requirements.txt — see Phase 1
git init && git remote add origin <repo>
```

### 0.4 Environment File
```bash
# .env (DO NOT COMMIT)
AUTH0_DOMAIN=
AUTH0_CLIENT_ID=
AUTH0_CLIENT_SECRET=
AUTH0_SECRET=
BLAND_API_KEY=
GHOST_URL=
GHOST_ADMIN_API_KEY=
TRUEFOUNDRY_API_KEY=
TRUEFOUNDRY_ENDPOINT=
OVERMIND_API_KEY=
AIRBYTE_API_KEY=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
```

### 0.5 Critical Validation (BEFORE CODING)
- [ ] **Bland AI test call** — Make ONE test call to a teammate's phone. If this fails, pivot strategy immediately.
- [ ] **Ghost test post** — Publish one test post via Admin API. Confirm it appears.
- [ ] **Auth0 test token** — Get one M2M token. Confirm it works.

**GATE:** If Bland fails after 15 min of debugging → pivot to PulsePost (swap Bland for deeper Ghost). The rest of the architecture is shared.

---

## PHASE 1: Bland AI — Interactive Two-Way Phone Diagnosis (35 min)

### Why first
The phone call is the demo climax. If it doesn't work, we need to know ASAP to pivot.

### 1.1 Basic Outbound Call (10 min)
```python
# bland_caller.py
import requests

def make_incident_call(phone_number: str, incident_context: dict):
    """Make an outbound incident briefing call via Bland AI."""
    response = requests.post(
        "https://public.api.bland.ai/v1/calls",
        headers={"Authorization": f"Bearer {BLAND_API_KEY}"},
        json={
            "phone_number": phone_number,
            "task": f"""You are Page0, an autonomous SRE incident response agent.
            You have detected a critical incident:
            Service: {incident_context['service']}
            Error: {incident_context['error']}
            Impact: {incident_context['impact']}
            Root Cause: {incident_context['root_cause']}

            Brief the engineer. Then ask if they authorize remediation.
            If they say yes, confirm you are proceeding.
            If they ask questions, answer from the incident data.""",
            "voice": "mason",
            "wait_for_greeting": True,
            "record": True
        }
    )
    return response.json()
```

### 1.2 Function Calling During Call — THE CREATIVE PART (15 min)
This is the "unpopular" Bland feature. The agent can call functions MID-CONVERSATION to query live data.

```python
# bland_pathway.py — Interactive diagnosis pathway
pathway = {
    "nodes": [
        {
            "id": "greeting",
            "type": "default",
            "text": "This is Page0. We've detected a critical incident on {service_name}. Error rate is at {error_rate} percent. The root cause appears to be {root_cause}. Would you like more details, or should I proceed with remediation?",
            "edges": [
                {"condition": "user asks for details", "next": "deep_dive"},
                {"condition": "user authorizes fix", "next": "authorize"},
                {"condition": "user wants to escalate", "next": "escalate"}
            ]
        },
        {
            "id": "deep_dive",
            "type": "function_call",
            "function": "query_live_metrics",  # Calls back to our API mid-call
            "text": "Let me pull the latest data... {function_result}. Do you want me to proceed with the fix?",
            "edges": [
                {"condition": "user authorizes", "next": "authorize"},
                {"condition": "user declines", "next": "end"}
            ]
        },
        {
            "id": "authorize",
            "type": "function_call",
            "function": "trigger_ciba_approval",  # Triggers Auth0 CIBA flow
            "text": "Authorization received. Initiating remediation now. I'll publish the incident report to your team's dashboard. Anything else?",
            "edges": [
                {"condition": "default", "next": "end"}
            ]
        },
        {
            "id": "escalate",
            "type": "function_call",
            "function": "escalate_to_vp",  # Calls next person in chain
            "text": "Escalating to the VP of Engineering now. I'll keep you posted. Goodbye.",
            "edges": [
                {"condition": "default", "next": "end"}
            ]
        },
        {
            "id": "end",
            "type": "end",
            "text": "Thank you. The incident report will be published to your Ghost dashboard within 60 seconds. Goodbye."
        }
    ]
}
```

### 1.3 Webhook Receiver for Call Events (10 min)
```python
# webhook_server.py (FastAPI)
@app.post("/bland/webhook")
async def bland_webhook(data: dict):
    """Receive call status updates and transcripts from Bland."""
    if data.get("status") == "completed":
        transcript = data.get("transcript", "")
        # Parse engineer's authorization from transcript
        authorized = parse_authorization(transcript)
        if authorized:
            await trigger_remediation(data["call_id"])
            await publish_incident_report(data["incident_id"])
    return {"status": "ok"}
```

### 1.4 Validation
- [ ] Make a test call that includes function calling
- [ ] Confirm the pathway branching works (ask a question → get live data back)
- [ ] Confirm webhook fires on call completion

---

## PHASE 2: Airbyte — Dynamic Connector Orchestration (35 min)

### Why creative
Instead of static "pull data" pipelines, the agent PROGRAMMATICALLY creates new connectors based on what incident it detects. This is Airbyte's catalog/schema introspection API — almost nobody uses it this way.

### 2.1 Base Monitoring Source (10 min)
```python
# airbyte_monitor.py
import airbyte as ab

# Primary source: simulated infrastructure metrics
# In production this would be Datadog/CloudWatch/Prometheus
source = ab.get_source(
    "source-faker",  # For demo; swap to real source if time permits
    config={
        "count": 1000,
        "seed": 42
    },
    install_if_missing=True
)

# OR use source-http-request to pull from a mock metrics API
metrics_source = ab.get_source(
    "source-http-request",
    config={
        "url": "https://our-mock-api.com/metrics",
        "method": "GET",
        "headers": {"Authorization": "Bearer {token}"}
    }
)

# Read into a local cache for the agent to analyze
cache = ab.get_default_cache()  # DuckDB
source.check()
result = source.read(cache=cache)
```

### 2.2 Dynamic Connector Creation — THE CREATIVE PART (15 min)
The agent doesn't just read from pre-configured sources. It CREATES new sources on-the-fly based on what it discovers.

```python
# airbyte_dynamic.py
async def dynamically_investigate(incident_type: str, context: dict):
    """
    Agent decides WHICH additional data sources to connect
    based on the type of incident detected.
    """
    if incident_type == "payment_service_error":
        # Agent spins up a Stripe connector to check transactions
        stripe_source = ab.get_source(
            "source-stripe",
            config={
                "client_secret": auth0_token_vault.get_token("stripe"),
                "account_id": context["stripe_account"],
                "start_date": context["incident_start"]
            },
            install_if_missing=True
        )
        # Use Airbyte's catalog introspection to discover available streams
        catalog = stripe_source.discovered_catalog
        relevant_streams = [s for s in catalog.streams
                          if s.name in ["charges", "disputes", "events"]]
        stripe_source.select_streams(relevant_streams)
        return stripe_source.read(cache=cache)

    elif incident_type == "database_connection_pool":
        # Agent spins up a Postgres connector to check query logs
        pg_source = ab.get_source(
            "source-postgres",
            config={
                "host": context["db_host"],
                "port": 5432,
                "database": context["db_name"],
                "username": auth0_token_vault.get_token("postgres_user"),
                "password": auth0_token_vault.get_token("postgres_pass"),
                "replication_method": "standard"
            },
            install_if_missing=True
        )
        catalog = pg_source.discovered_catalog
        # Introspect schema to find relevant tables
        log_streams = [s for s in catalog.streams
                      if "log" in s.name.lower() or "query" in s.name.lower()]
        pg_source.select_streams(log_streams)
        return pg_source.read(cache=cache)

    elif incident_type == "api_latency_spike":
        # Agent creates a GitHub connector to check recent deploys
        gh_source = ab.get_source(
            "source-github",
            config={
                "credentials": {"access_token": auth0_token_vault.get_token("github")},
                "repositories": [context["repo"]]
            },
            install_if_missing=True
        )
        catalog = gh_source.discovered_catalog
        deploy_streams = [s for s in catalog.streams
                         if s.name in ["deployments", "commits", "pull_requests"]]
        gh_source.select_streams(deploy_streams)
        return gh_source.read(cache=cache)
```

### 2.3 Anomaly Detection on Ingested Data (10 min)
```python
# anomaly_detector.py
import pandas as pd

async def detect_anomalies(cache) -> list[dict]:
    """
    Pull latest metrics from Airbyte cache,
    detect anomalies using statistical thresholds + LLM reasoning.
    """
    df = cache.streams["metrics"].to_pandas()

    # Simple statistical detection
    anomalies = []
    for metric in ["error_rate", "latency_p99", "cpu_usage", "memory_usage"]:
        mean = df[metric].mean()
        std = df[metric].std()
        latest = df[metric].iloc[-1]
        if latest > mean + 2 * std:
            anomalies.append({
                "metric": metric,
                "value": latest,
                "threshold": mean + 2 * std,
                "severity": "critical" if latest > mean + 3 * std else "warning"
            })

    if anomalies:
        # Use LLM (via TrueFoundry) to interpret the anomaly pattern
        diagnosis = await llm_diagnose(anomalies, df)
        return diagnosis

    return []
```

### 2.4 Validation
- [ ] PyAirbyte source reads data into DuckDB cache
- [ ] Dynamic connector creation works (at least 2 source types)
- [ ] Catalog introspection returns stream names
- [ ] Anomaly detection flags test anomalies

---

## PHASE 3: Auth0 — CIBA + Token Vault (15 min)

### Why creative
Not a login page. We use Auth0's GenAI-specific features: **CIBA** for async human-in-the-loop approval (the phone call IS the approval), and **Token Vault** so the agent never sees raw API credentials.

### 3.1 Token Vault Setup (5 min)
The agent accesses ALL third-party APIs through Auth0's Token Vault, never storing credentials directly.

```python
# auth0_vault.py
from auth0_ai import Auth0TokenVault

vault = Auth0TokenVault(
    domain=AUTH0_DOMAIN,
    client_id=AUTH0_CLIENT_ID,
    client_secret=AUTH0_CLIENT_SECRET
)

# Agent gets tokens for third-party services through Auth0
async def get_service_token(service: str) -> str:
    """
    Agent requests API tokens through Auth0 Token Vault.
    Tokens are managed, rotated, and secured by Auth0 —
    the agent never sees raw credentials.
    """
    token = await vault.get_token(
        connection=service,  # "github", "stripe", "datadog", etc.
        scopes=["read:metrics", "read:incidents"]
    )
    return token.access_token
```

### 3.2 CIBA — Phone Call as Authorization — THE CREATIVE PART (10 min)
The engineer's voice response on the Bland AI call triggers an Auth0 CIBA backchannel approval. This is the GLUE between Bland and Auth0 — the phone call IS the authentication.

```python
# auth0_ciba.py
from auth0.authentication import Database, GetToken

async def initiate_ciba_approval(engineer_id: str, action: str):
    """
    Start a CIBA (Client Initiated Backchannel Authentication) flow.
    The engineer approves via the phone call, not a browser.
    """
    # Step 1: Agent requests authorization for the remediation action
    ciba_response = requests.post(
        f"https://{AUTH0_DOMAIN}/bc-authorize",
        json={
            "client_id": AUTH0_CLIENT_ID,
            "client_secret": AUTH0_CLIENT_SECRET,
            "login_hint": {"format": "iss_sub", "iss": AUTH0_DOMAIN, "sub": engineer_id},
            "scope": "openid remediate:service",
            "binding_message": f"Page0 requests permission to: {action}",
            "requested_expiry": 300  # 5 min to respond
        }
    )
    auth_req_id = ciba_response.json()["auth_req_id"]

    # Step 2: Bland AI call handles the approval — when engineer says "yes",
    # the Bland function_call triggers this:
    return auth_req_id

async def complete_ciba_from_voice(auth_req_id: str):
    """
    Called by the Bland webhook when the engineer verbally approves.
    Completes the CIBA flow and returns an access token the agent
    can use to perform the remediation.
    """
    token_response = requests.post(
        f"https://{AUTH0_DOMAIN}/oauth/token",
        json={
            "client_id": AUTH0_CLIENT_ID,
            "client_secret": AUTH0_CLIENT_SECRET,
            "auth_req_id": auth_req_id,
            "grant_type": "urn:openid:params:grant-type:ciba"
        }
    )
    return token_response.json()["access_token"]
```

### 3.3 Validation
- [ ] Token Vault returns a valid token for at least one service
- [ ] CIBA flow initiates successfully
- [ ] CIBA token exchange completes after simulated approval

---

## PHASE 4: TrueFoundry — Dynamic Model Escalation + Guardrails (10 min)

### Why creative
Not just a proxy. The agent uses CHEAP models for routine monitoring, then AUTOMATICALLY escalates to expensive models for critical incidents. Plus guardrails prevent dangerous actions.

### 4.1 AI Gateway with Dynamic Routing (5 min)
```python
# truefoundry_gateway.py
from openai import OpenAI  # TrueFoundry uses OpenAI-compatible format

# All LLM calls go through TrueFoundry
tf_client = OpenAI(
    api_key=TRUEFOUNDRY_API_KEY,
    base_url=TRUEFOUNDRY_ENDPOINT
)

async def llm_call(prompt: str, severity: str = "routine"):
    """
    Dynamic model escalation via TrueFoundry AI Gateway.
    Routine monitoring uses cheap/fast models.
    Critical incidents escalate to powerful models.
    """
    model_map = {
        "routine": "claude-haiku-4-5-20251001",    # $0.001/call — monitoring
        "warning": "claude-sonnet-4-6",             # $0.01/call — analysis
        "critical": "claude-opus-4-6"               # $0.10/call — deep diagnosis
    }

    response = tf_client.chat.completions.create(
        model=model_map.get(severity, "claude-haiku-4-5-20251001"),
        messages=[{"role": "user", "content": prompt}],
        # TrueFoundry adds: cost tracking, rate limiting, fallback
    )
    return response.choices[0].message.content
```

### 4.2 Guardrails — THE CREATIVE PART (5 min)
TrueFoundry guardrails prevent the agent from taking dangerous actions without approval.

```python
# truefoundry_guardrails.py
guardrails_config = {
    "input_guardrails": [
        {
            "type": "keyword_block",
            "keywords": ["DROP TABLE", "rm -rf", "shutdown --now"],
            "action": "block_and_alert"
        }
    ],
    "output_guardrails": [
        {
            "type": "pii_detection",
            "action": "redact",
            "fields": ["phone_number", "api_key", "password"]
        },
        {
            "type": "cost_limit",
            "max_cost_per_call": 0.50,
            "action": "downgrade_model"  # Auto-fallback to cheaper model
        }
    ]
}

# Show in demo: "TrueFoundry prevented the agent from executing a dangerous
# command and automatically downgraded to a cheaper model when cost exceeded
# threshold. Here's the analytics dashboard showing cost savings."
```

### 4.3 Validation
- [ ] LLM call routes through TrueFoundry successfully
- [ ] Different severity levels use different models
- [ ] Cost analytics visible in TrueFoundry dashboard

---

## PHASE 5: Ghost — Tiered Incident Communication Hub (25 min)

### Why creative
Not just "publish a post." Ghost becomes the incident COMMUNICATION PLATFORM with tiered access — executives see high-level, engineers see detailed reports. Uses Ghost's Tiers, Webhooks, and Newsletter APIs.

### 5.1 Ghost Admin API Setup (5 min)
```python
# ghost_publisher.py
import jwt
import requests
from datetime import datetime

def get_ghost_token():
    """Generate Ghost Admin API JWT."""
    key_id, secret = GHOST_ADMIN_API_KEY.split(":")
    iat = int(datetime.now().timestamp())
    header = {"alg": "HS256", "typ": "JWT", "kid": key_id}
    payload = {"iat": iat, "exp": iat + 300, "aud": "/admin/"}
    return jwt.encode(payload, bytes.fromhex(secret), algorithm="HS256", headers=header)
```

### 5.2 Tiered Incident Reports — THE CREATIVE PART (15 min)
The agent publishes DIFFERENT content to DIFFERENT audience tiers using Ghost's membership system.

```python
# ghost_incident_reports.py

async def publish_incident_report(incident: dict, diagnosis: dict):
    """
    Publish tiered incident reports to Ghost.
    Executives get a 3-line summary. Engineers get full stack traces.
    """
    token = get_ghost_token()
    headers = {"Authorization": f"Ghost {token}", "Content-Type": "application/json"}

    # EXECUTIVE TIER — public post, high-level summary
    exec_report = {
        "posts": [{
            "title": f"[P{incident['severity']}] {incident['service']} — {incident['summary']}",
            "html": f"""
                <h2>Incident Summary</h2>
                <p><strong>Status:</strong> {incident['status']}</p>
                <p><strong>Impact:</strong> {incident['impact']}</p>
                <p><strong>ETA to Resolution:</strong> {incident['eta']}</p>
                <p><strong>Action Taken:</strong> {diagnosis['remediation_summary']}</p>
                <hr>
                <p><em>Auto-generated by Page0 at {datetime.now().isoformat()}</em></p>
            """,
            "status": "published",
            "tags": [{"name": f"P{incident['severity']}"}, {"name": incident['service']}],
            "visibility": "public",  # Executives (free tier) can see this
            "featured": incident['severity'] <= 1
        }]
    }

    # ENGINEERING TIER — members-only post with full technical details
    eng_report = {
        "posts": [{
            "title": f"[ENG] {incident['service']} — Full Diagnosis",
            "html": f"""
                <h2>Root Cause Analysis</h2>
                <pre><code>{diagnosis['root_cause_detail']}</code></pre>

                <h2>Metrics at Time of Incident</h2>
                <pre><code>{diagnosis['metrics_snapshot']}</code></pre>

                <h2>Airbyte Data Sources Consulted</h2>
                <ul>
                    {''.join(f"<li>{s}</li>" for s in diagnosis['data_sources'])}
                </ul>

                <h2>Remediation Steps Taken</h2>
                <ol>
                    {''.join(f"<li>{s}</li>" for s in diagnosis['remediation_steps'])}
                </ol>

                <h2>Related Code Changes (via Macroscope)</h2>
                <p>{diagnosis.get('macroscope_analysis', 'No related PRs identified')}</p>

                <h2>On-Call Interaction (Bland AI Transcript)</h2>
                <pre><code>{diagnosis.get('call_transcript', 'Pending')}</code></pre>

                <h2>Agent Decision Trace (Overmind)</h2>
                <pre><code>{diagnosis.get('overmind_trace', 'See Overmind dashboard')}</code></pre>
            """,
            "status": "published",
            "tags": [{"name": "engineering"}, {"name": f"P{incident['severity']}"}],
            "visibility": "members",  # Only engineering tier members
        }]
    }

    # Publish both
    exec_resp = requests.post(f"{GHOST_URL}/ghost/api/admin/posts/",
                              headers=headers, json=exec_report)
    eng_resp = requests.post(f"{GHOST_URL}/ghost/api/admin/posts/",
                             headers=headers, json=eng_report)

    return {
        "exec_post_url": exec_resp.json()["posts"][0]["url"],
        "eng_post_url": eng_resp.json()["posts"][0]["url"]
    }
```

### 5.3 Ghost Webhooks — Trigger Downstream Notifications (5 min)
```python
# ghost_webhooks.py
# Configure Ghost webhook: when a post is published with tag "P0" or "P1",
# trigger a notification to Slack/Teams/etc.

async def setup_ghost_webhooks():
    """Register webhooks so Ghost triggers downstream alerts on publish."""
    token = get_ghost_token()
    headers = {"Authorization": f"Ghost {token}", "Content-Type": "application/json"}

    webhook = {
        "webhooks": [{
            "event": "post.published",
            "target_url": f"{OUR_SERVER}/ghost/webhook",
            "name": "Page0 Incident Alert"
        }]
    }

    requests.post(f"{GHOST_URL}/ghost/api/admin/webhooks/",
                  headers=headers, json=webhook)
```

### 5.4 Validation
- [ ] Executive report publishes and is publicly visible
- [ ] Engineering report publishes and is members-only
- [ ] Posts have correct tags, formatting, and metadata
- [ ] Ghost webhook fires on publish

---

## PHASE 6: Macroscope — PR-Linked Root Cause Identification (10 min)

### Why creative
Not just "install the GitHub app." Macroscope identifies WHICH code change caused the incident, and that analysis is included in the incident report.

### 6.1 Install Macroscope (2 min)
- [ ] Go to macroscope.com → Install GitHub App on hackathon repo
- [ ] Macroscope auto-starts analyzing PRs and generating reviews

### 6.2 Query Macroscope for Root Cause — THE CREATIVE PART (8 min)
```python
# macroscope_rca.py

async def identify_causal_pr(incident: dict) -> dict:
    """
    Query recent PRs via GitHub API, cross-reference with Macroscope's
    analysis to identify which code change likely caused the incident.
    """
    # Get recent merged PRs around the incident timeframe
    gh_token = await auth0_vault.get_token("github")

    prs = requests.get(
        f"https://api.github.com/repos/{REPO}/pulls",
        headers={"Authorization": f"Bearer {gh_token}"},
        params={"state": "closed", "sort": "updated", "direction": "desc", "per_page": 10}
    ).json()

    # Filter PRs merged in the last 24 hours
    recent_prs = [pr for pr in prs if pr.get("merged_at") and
                  is_within_hours(pr["merged_at"], 24)]

    if not recent_prs:
        return {"analysis": "No recent PRs found. Incident may be infrastructure-related."}

    # Use LLM to correlate PR changes with incident symptoms
    pr_summaries = []
    for pr in recent_prs[:5]:
        # Macroscope will have left review comments — fetch them
        reviews = requests.get(
            f"https://api.github.com/repos/{REPO}/pulls/{pr['number']}/reviews",
            headers={"Authorization": f"Bearer {gh_token}"}
        ).json()

        macroscope_reviews = [r for r in reviews if "macroscope" in r.get("user", {}).get("login", "").lower()]

        pr_summaries.append({
            "pr_number": pr["number"],
            "title": pr["title"],
            "files_changed": pr.get("changed_files", 0),
            "merged_at": pr["merged_at"],
            "macroscope_analysis": macroscope_reviews[0]["body"] if macroscope_reviews else "No Macroscope review"
        })

    # LLM correlates PR changes with incident symptoms
    correlation = await llm_call(
        f"""Analyze these recent PRs and determine which one most likely caused this incident:

        Incident: {incident['summary']}
        Service: {incident['service']}
        Symptoms: {incident['symptoms']}

        Recent PRs:
        {json.dumps(pr_summaries, indent=2)}

        Identify the most likely causal PR and explain why.""",
        severity="critical"
    )

    return {
        "analysis": correlation,
        "prs_analyzed": pr_summaries,
        "source": "Macroscope + LLM correlation"
    }
```

### 6.3 Validation
- [ ] Macroscope GitHub app is installed and analyzing PRs
- [ ] GitHub API returns PR data with Macroscope reviews
- [ ] LLM correlation produces plausible root cause identification

---

## PHASE 7: Overmind — Live Agent Observability + Optimization (5 min)

### Why creative
Not just tracing. Overmind actively recommends prompt optimizations, and we SHOW this in the demo.

### 7.1 Initialize Overmind (2 min)
```python
# overmind_setup.py
import overmind

# One line to instrument ALL LLM calls
overmind.init(
    api_key=OVERMIND_API_KEY,
    service_name="page0-agent",
    environment="hackathon"
)

# That's it. All OpenAI/Anthropic/TrueFoundry calls are now traced.
# Overmind will:
# - Record every LLM call with latency, cost, tokens
# - Evaluate response quality with LLM judges
# - Recommend prompt optimizations
# - Show a dashboard with the full agent decision trace
```

### 7.2 Demo-Ready Optimization Display (3 min)
```python
# overmind_demo.py

async def get_optimization_report():
    """
    Pull Overmind's optimization recommendations for the demo.
    Show judges: "Overmind analyzed our agent's 47 LLM calls and
    found we could reduce cost by 35% with these prompt changes."
    """
    # Overmind dashboard URL for live demo
    dashboard_url = f"https://console.overmindlab.ai/services/page0-agent"

    # Pull evaluation results
    evaluations = overmind.get_evaluations(service="page0-agent")

    return {
        "total_calls": evaluations["total"],
        "avg_latency": evaluations["avg_latency_ms"],
        "total_cost": evaluations["total_cost"],
        "optimization_suggestions": evaluations["suggestions"],
        "dashboard_url": dashboard_url
    }
```

### 7.3 Validation
- [ ] Overmind captures LLM call traces
- [ ] Dashboard shows agent decision flow
- [ ] At least one optimization suggestion is generated

---

## PHASE 8: Agent Orchestrator — The Brain (25 min)

### 8.1 Main Agent Loop
```python
# agent.py — The core orchestrator
import asyncio

class SentinelCallAgent:
    def __init__(self):
        self.airbyte = AirbyteMonitor()
        self.bland = BlandCaller()
        self.ghost = GhostPublisher()
        self.auth0 = Auth0Manager()
        self.macroscope = MacroscopeAnalyzer()
        self.truefoundry = TrueFoundryGateway()
        # Overmind auto-instruments via overmind.init()

    async def run(self):
        """Main autonomous loop — zero human intervention."""
        print("[Page0] Agent started. Monitoring infrastructure...")

        while True:
            # STEP 1: Ingest metrics via Airbyte
            metrics = await self.airbyte.pull_latest_metrics()

            # STEP 2: Detect anomalies (cheap model via TrueFoundry)
            anomalies = await self.detect_anomalies(metrics, severity="routine")

            if not anomalies:
                await asyncio.sleep(10)  # Poll interval
                continue

            print(f"[Page0] ANOMALY DETECTED: {anomalies}")

            # STEP 3: Escalate to powerful model for deep diagnosis
            diagnosis = await self.diagnose(anomalies, severity="critical")

            # STEP 4: Dynamic data investigation via Airbyte
            additional_data = await self.airbyte.dynamically_investigate(
                incident_type=diagnosis["type"],
                context=diagnosis["context"]
            )
            diagnosis["additional_findings"] = additional_data

            # STEP 5: Query Macroscope for causal PR
            macroscope_rca = await self.macroscope.identify_causal_pr(diagnosis)
            diagnosis["macroscope_analysis"] = macroscope_rca["analysis"]

            # STEP 6: Initiate Auth0 CIBA flow
            auth_req_id = await self.auth0.initiate_ciba_approval(
                engineer_id=ON_CALL_ENGINEER_ID,
                action=diagnosis["recommended_action"]
            )

            # STEP 7: Call on-call engineer via Bland AI
            call_result = await self.bland.make_incident_call(
                phone_number=ON_CALL_PHONE,
                incident_context=diagnosis,
                ciba_auth_req_id=auth_req_id  # Passed to Bland pathway
            )

            # STEP 8: Publish tiered incident report to Ghost
            report_urls = await self.ghost.publish_incident_report(
                incident=diagnosis,
                diagnosis={
                    **diagnosis,
                    "call_transcript": call_result.get("transcript"),
                    "macroscope_analysis": macroscope_rca["analysis"],
                    "data_sources": additional_data.get("sources_used", [])
                }
            )

            print(f"[Page0] Incident response complete.")
            print(f"  Phone call: {call_result['status']}")
            print(f"  Exec report: {report_urls['exec_post_url']}")
            print(f"  Eng report: {report_urls['eng_post_url']}")

            # STEP 9: If engineer authorized via CIBA, execute remediation
            if call_result.get("authorized"):
                access_token = await self.auth0.complete_ciba_from_voice(auth_req_id)
                await self.remediate(diagnosis, access_token)

            await asyncio.sleep(30)  # Cooldown before next monitoring cycle
```

### 8.2 Mock Infrastructure for Demo
```python
# mock_infra.py — Simulated infrastructure for the demo
import random
import time

class MockInfrastructure:
    """
    Simulates a production environment with controllable incidents.
    Call trigger_incident() to simulate a P0/P1 for the demo.
    """
    def __init__(self):
        self.services = {
            "payment-service": {"error_rate": 0.1, "latency_p99": 120, "cpu": 45},
            "user-service": {"error_rate": 0.05, "latency_p99": 80, "cpu": 30},
            "notification-service": {"error_rate": 0.02, "latency_p99": 50, "cpu": 20}
        }
        self.incident_active = False

    def trigger_incident(self, service="payment-service"):
        """Trigger a simulated incident for the demo."""
        self.incident_active = True
        self.services[service] = {
            "error_rate": 45.2,       # 45% errors — clearly anomalous
            "latency_p99": 8500,      # 8.5s p99 — unacceptable
            "cpu": 98,                # CPU pegged
            "memory": 94,
            "db_connections": 495,    # Pool exhausted (max 500)
            "recent_deploy": "PR #47 — Update connection pool config"
        }

    def get_metrics(self):
        """Return current metrics (consumed by Airbyte source)."""
        return self.services
```

### 8.3 Simple Dashboard (FastAPI + HTML)
```python
# dashboard.py
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Minimal dashboard showing agent status and incident history."""
    return """
    <html>
    <head><title>Page0</title></head>
    <body style="font-family: monospace; background: #0a0a0a; color: #00ff00; padding: 2rem;">
        <h1>Page0 — Autonomous Incident Response</h1>
        <div id="status">Monitoring...</div>
        <div id="incidents"></div>
        <script>
            // SSE or polling for live updates
            setInterval(async () => {
                const res = await fetch('/api/status');
                const data = await res.json();
                document.getElementById('status').innerHTML = data.status;
                document.getElementById('incidents').innerHTML = data.incidents_html;
            }, 2000);
        </script>
    </body>
    </html>
    """

@app.get("/api/status")
async def status():
    return {"status": agent.current_status, "incidents_html": agent.incidents_html}

@app.post("/api/trigger-incident")
async def trigger():
    """Demo endpoint: trigger a simulated incident."""
    mock_infra.trigger_incident()
    return {"status": "incident triggered"}
```

---

## PHASE 9: Integration Testing + Polish (15 min)

### 9.1 End-to-End Test Flow
1. Start the agent (`python agent.py`)
2. Trigger a mock incident (`POST /api/trigger-incident`)
3. Verify: Agent detects anomaly in Airbyte data
4. Verify: Agent escalates LLM model via TrueFoundry
5. Verify: Agent queries Macroscope for causal PR
6. Verify: Phone rings via Bland with interactive diagnosis
7. Verify: Auth0 CIBA flow completes on voice approval
8. Verify: Ghost publishes tiered incident reports
9. Verify: Overmind dashboard shows full trace

### 9.2 Polish Checklist
- [ ] Dashboard looks clean and professional
- [ ] Ghost blog has proper branding (Page0 logo, dark theme)
- [ ] Error handling — graceful degradation if any tool fails
- [ ] Console output tells a clear story for screen recording

---

## PHASE 10: Demo Recording (30 min)

### 10.1 Demo Script (3 minutes — REHEARSE TWICE)

**[0:00-0:20] Hook + Problem**
"It's 3 AM. Your payment service is down. Revenue loss: $5,600 per minute. The Slack alert is buried under 47 other notifications. Meet Page0 — an autonomous SRE agent that detects, diagnoses, escalates, and resolves incidents without a human lifting a finger."

**[0:20-0:50] Architecture Flash (show diagram)**
"Page0 uses 7 sponsor tools: Airbyte for dynamic data ingestion, Auth0's CIBA for backchannel authorization, TrueFoundry for intelligent model routing, Bland AI for interactive phone escalation, Ghost for tiered incident reports, Macroscope for root cause identification, and Overmind for agent observability."

**[0:50-1:10] Live Demo — Trigger Incident**
Show dashboard (all green) → Click "Trigger Incident" → Dashboard turns red → Agent logs show anomaly detection in real-time.

**[1:10-1:40] Live Demo — Agent Investigates**
Agent dynamically creates Airbyte connectors to pull additional data. TrueFoundry escalates from Haiku to Opus. Macroscope identifies PR #47 as the cause.

**[1:40-2:20] Live Demo — THE PHONE RINGS**
Bland AI calls the on-call engineer (teammate's phone). Interactive conversation — engineer asks "what's the error rate?" → agent answers from live data. Engineer says "fix it" → Auth0 CIBA completes.

**[2:20-2:45] Live Demo — Resolution**
Ghost blog updates LIVE with two posts — executive summary (public) and engineering deep-dive (members-only). Agent confirms remediation complete.

**[2:45-3:00] Close**
"From detection to resolution: 47 seconds. Industry average MTTR: 45 minutes. Page0: because 3 AM pages shouldn't need a human. Thank you."

### 10.2 Demo Recording Tips
- Use OBS or QuickTime for screen recording
- Split screen: dashboard on left, terminal logs on right
- Have teammate's phone VISIBLE on camera when it rings
- Pre-test the full flow 2x before recording
- Have a backup recording ready in case live demo fails

---

## PHASE 11: Submission (20 min)

### 11.1 GitHub Repo
- [ ] Clean up code, remove debug prints
- [ ] Write clear README with setup instructions
- [ ] Add architecture diagram
- [ ] Ensure .env.example exists (no real keys)
- [ ] Make repo PUBLIC

### 11.2 Devpost Submission
- [ ] Project name: Page0
- [ ] Tagline: "Autonomous incident response that calls you before you check Slack"
- [ ] Description: Problem, solution, how it works, sponsor tools used
- [ ] Demo video: 3-minute recording
- [ ] Tech stack: Python, FastAPI, Airbyte, Auth0, Bland AI, Ghost, TrueFoundry, Macroscope, Overmind
- [ ] Submit to ALL relevant prize tracks:
  - Best Use of Auth0 for AI Agents
  - Airbyte: Conquer with Context
  - Best Use of Ghost
  - Most Innovative Project Using Macroscope
  - Overmind Builders Prize
  - Truefoundry: Best use of AI Gateway
  - Most Ab-Norm-al use of Bland

### 11.3 Shipables.dev
- [ ] Publish project as a skill on shipables.dev (hackathon requirement)

---

## Fallback Strategies

| Failure | Fallback | Time Cost |
|---|---|---|
| Bland AI doesn't work | Pre-record a successful call; show API request/response in demo | 10 min |
| Ghost API issues | Use Ghost(Pro) hosted instead of self-hosted; or show report as HTML page | 5 min |
| Auth0 CIBA not available on free tier | Demonstrate the CIBA flow architecture with mock; show Token Vault working | 5 min |
| Airbyte connector slow to install | Use `source-faker` with realistic mock data; explain dynamic connector concept | 5 min |
| TrueFoundry signup issues | Call LLM APIs directly; show the TrueFoundry concept in slides | 2 min |
| Macroscope no PRs to analyze | Create 2-3 dummy PRs before demo; Macroscope will analyze them | 10 min |
| Overmind not capturing traces | Show Overmind dashboard with whatever it captured; it's a 2-line integration | 2 min |

---

## Key Principles

1. **Test Bland FIRST** — it's the highest-risk, highest-reward integration
2. **Build the shared core early** — agent loop + Airbyte + TrueFoundry work for any pivot
3. **Every tool must be CREATIVE** — no checkbox integrations, use unpopular/unique features
4. **Demo > code** — a beautiful demo with mocked data beats perfect code with a broken demo
5. **The phone ringing is worth $6,751** — protect this moment at all costs
