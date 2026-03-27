# Pager0 — Autonomous Incident Response Agent

## Project Overview

**Pager0** — An autonomous SRE agent that monitors infrastructure, detects anomalies, diagnoses root cause, calls the on-call engineer via AI phone call, and publishes tiered incident reports — all without human intervention.

**Hackathon:** Deep Agents Hackathon | **Deadline:** Mar 27, 2026 @ 4:30 PM PDT

### Architecture

- **Core Agent**: Python (FastAPI) — orchestrates the full incident response pipeline
- **Data Ingestion**: Airbyte (PyAirbyte) — dynamic connector orchestration for real-time metrics
- **Authentication**: Auth0 — CIBA backchannel authorization + Token Vault for API credentials
- **Phone Escalation**: Bland AI — interactive two-way voice diagnosis with function calling
- **Incident Reports**: Ghost CMS — tiered publishing (executive vs. engineering) via Admin API
- **LLM Gateway**: TrueFoundry — dynamic model escalation (cheap→expensive) + guardrails
- **Code Analysis**: Macroscope — PR-linked root cause identification via GitHub App
- **Observability**: Overmind — LLM call tracing + prompt optimization recommendations

### Project Structure

```text
sentinelcall/
  agent.py                # Main agent orchestrator loop
  bland_caller.py         # Bland AI phone call + pathway integration
  bland_pathway.py        # Interactive conversation decision tree
  airbyte_monitor.py      # Airbyte data ingestion + dynamic connectors
  airbyte_dynamic.py      # Dynamic connector creation per incident type
  anomaly_detector.py     # Statistical + LLM anomaly detection
  auth0_vault.py          # Auth0 Token Vault for API credentials
  auth0_ciba.py           # CIBA backchannel auth (phone = approval)
  truefoundry_gateway.py  # TrueFoundry AI Gateway + model escalation
  truefoundry_guardrails.py # Guardrails config
  ghost_publisher.py      # Ghost Admin API setup + JWT auth
  ghost_incident_reports.py # Tiered incident report publishing
  ghost_webhooks.py       # Ghost webhook registration
  macroscope_rca.py       # PR-linked root cause analysis
  overmind_setup.py       # Overmind initialization + demo report
  mock_infra.py           # Simulated infrastructure for demo
  dashboard.py            # FastAPI dashboard + API endpoints
  webhook_server.py       # Bland webhook receiver
  requirements.txt        # Python dependencies
  .env.example            # Environment variable template
```

### Key Technical Decisions

- All LLM calls route through TrueFoundry AI Gateway — never call providers directly
- Auth0 Token Vault manages ALL third-party API credentials — agent never sees raw secrets
- Airbyte connectors are created dynamically based on incident type, not pre-configured
- Ghost publishes TWO reports per incident: public (executives) and members-only (engineers)
- Bland AI uses pathway system with function calling for interactive mid-call data queries
- Auth0 CIBA flow is triggered by the engineer's voice approval on the Bland call
- Overmind auto-instruments all LLM calls via `overmind.init()` — zero code changes needed
- Macroscope GitHub App analyzes PRs and the agent queries its reviews to identify causal PRs

### Dependencies

- **Python** >= 3.10
- **FastAPI** + **uvicorn** for dashboard and webhook server
- **PyAirbyte** (`airbyte`) for data connectors
- **auth0-python** for Auth0 integration
- **requests** for API calls (Bland, Ghost, GitHub)
- **PyJWT** for Ghost Admin API authentication
- **overmind** for LLM observability
- **openai** SDK (used with TrueFoundry base_url override)
- **python-dotenv** for environment variable management

### Environment Variables

```bash
AUTH0_DOMAIN=           # Auth0 tenant domain
AUTH0_CLIENT_ID=        # Auth0 application client ID
AUTH0_CLIENT_SECRET=    # Auth0 application client secret
BLAND_API_KEY=          # Bland AI API key
GHOST_URL=              # Ghost instance URL
GHOST_ADMIN_API_KEY=    # Ghost Admin API key (id:secret format)
TRUEFOUNDRY_API_KEY=    # TrueFoundry gateway API key
TRUEFOUNDRY_ENDPOINT=   # TrueFoundry gateway endpoint URL
OVERMIND_API_KEY=       # Overmind API key
ANTHROPIC_API_KEY=      # Anthropic API key (for TrueFoundry backend)
```

## Sponsor Tool Usage (Creative/Non-obvious)

Each tool is used for its UNPOPULAR or non-core features, not basic usage:

| Tool | Basic Use (DON'T) | Our Creative Use (DO) |
|---|---|---|
| Auth0 | Login page | CIBA backchannel auth via phone call + Token Vault |
| Airbyte | Static data pull | Dynamic connector creation based on incident type |
| Ghost | Publish a blog post | Tiered incident reports (exec vs eng) + webhooks |
| Bland | Make a phone call | Interactive pathway with function calling mid-call |
| TrueFoundry | Proxy LLM calls | Dynamic model escalation by severity + guardrails |
| Macroscope | Install GitHub app | PR-linked root cause identification in reports |
| Overmind | 2-line wrapper | Live optimization recommendations shown in demo |

## Build & Run

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Fill in API keys

# Run
uvicorn dashboard:app --reload --port 8000

# Trigger demo incident
curl -X POST http://localhost:8000/api/trigger-incident
```

## Demo Flow

1. Dashboard shows all services green
2. Trigger incident → dashboard turns red
3. Agent detects anomaly via Airbyte → escalates LLM via TrueFoundry
4. Agent dynamically creates new Airbyte connectors to investigate
5. Macroscope identifies the causal PR
6. Bland AI calls on-call engineer with interactive briefing
7. Engineer approves remediation → Auth0 CIBA completes
8. Ghost publishes tiered incident reports (exec + eng)
9. Overmind dashboard shows full agent decision trace
10. Resolution in 47 seconds vs. industry average 45 minutes

## Prize Targets

- Auth0: $1,000 Amazon GC
- Airbyte: $1,000 Visa GC
- Ghost: $2,000 Visa ($500×4)
- Macroscope: $1,000 Cash
- Overmind: $651 Cash
- TrueFoundry: $600 Cash
- Bland: $500 Cash
- **Total: $6,751**

## Critical Rules

1. **Test Bland phone call FIRST** — if it fails after 15 min, pivot to PulsePost (swap Bland for deeper Ghost)
2. **Never hardcode API keys** — everything through Auth0 Token Vault or .env
3. **Every tool must use a creative/unpopular feature** — no checkbox integrations
4. **Demo > code quality** — a working demo with mocked data beats perfect code with a broken demo
5. **Commit frequently** — clean git history for judges reviewing the repo
