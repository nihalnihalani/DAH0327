# Pager0: The Autonomous Incident Response Agent

## Inspiration

Every critical incident takes the industry average of **45+ minutes** to resolve. An on-call engineer wakes up to vague PagerDuty alerts at 3 AM, manually scrubs through logs, cross-references recent GitHub pull requests, and blindly tries to diagnose the root cause under immense stress. 

We asked: **What if we could clone a Level 2 SRE?** An agent that detects anomalies, dynamically pulls fresh metrics, reasons about cryptic infrastructure logs, identifies the exact causal PR, and **picks up the phone to call you** with the solution.

You groggily say "Yes, revert it," and go back to sleep. **That's zero-stress incident response.**

## What It Does

**Pager0** is an autonomous agent that fully automates incident triage and resolution — compressing a 45-minute nightmare into a 47-second interaction.

1. **Detects & Ingests** — Monitors simulated infrastructure. When an anomaly strikes, it doesn't just look at static dashboards; it *dynamically* spawns **Airbyte** connectors on the fly to ingest real-time metrics specific to the failing service.
2. **Reasons** — Routes investigation data through the **TrueFoundry** AI Gateway. It uses a dynamic model escalation cascade: cheap, fast models for initial anomaly confirmation, escalating to advanced reasoning models for Root Cause Analysis (RCA) while adhering to strict guardrails.
3. **Analyzes Code** — Queries the **Macroscope** GitHub App to analyze recent pull requests. It cross-references the telemetry spike with code changes, pinpointing the exact lines of code that broke the system.
4. **Asks for Permission** — Pager0 **calls your phone via Bland AI**. It verbally briefs you on the incident ("Latency spiked due to PR #42"). Because it uses Bland's interactive pathways with function calling, you can ask it questions mid-call ("What's the current error rate?") before saying "Revert it."
5. **Authenticates & Deploys** — Your verbal approval triggers an **Auth0** CIBA (Client Initiated Backchannel Authentication) flow. The fix is authorized and deployed. Pager0 never sees raw API keys; everything goes through the Auth0 Token Vault.
6. **Reports & Traces** — Immediately generates and publishes two tiered incident reports via the **Ghost CMS** Admin API: a high-level summary for executives, and a deep technical post-mortem for engineers. All LLM decisions are traced via **Overmind** for full observability.

### The Resolution Curve (Proven in Demo)

| | Human SRE | Pager0 |
|---|---|---|
| **Detection & Ingestion** | 10 mins (Alert fatigue, finding dashboards) | **3 seconds** (Dynamic Airbyte Connectors) |
| **Diagnosis & RCA** | 20 mins (Hunting through PRs and logs) | **12 seconds** (Macroscope + TrueFoundry) |
| **Escalation & Action** | 10 mins (Waking up, auth, reverting) | **28 seconds** (Bland Call + Auth0 CIBA) |
| **Post-Mortem Reporting** | 1-2 Days (Meetings, drafting docs) | **4 seconds** (Ghost CMS Tiered Publishing) |
| **Total MTTR** | **45+ minutes** | **~47 seconds** |

## Architecture

Our orchestrated FastAPI backend coordinates specialized tools without relying on simple "checkbox" integrations:

![Architecture Diagram](https://mermaid.ink/img/Z3JhcGggVEIKICAgIHN1YmdyYXBoIEluZnJhc3RydWN0dXJlCiAgICAgICAgQWlyYnl0ZVsiQWlyYnl0ZSAoUHlBaXJieXRlKTxicC8+RHluYW1pYyBDb25uZWN0b3JzIl0KICAgIGVuZAoKICAgIHN1YmdyYXBoIENvcmVBZ2VudFsiUGFnZXIwIENvcmUgQWdlbnQgKEZhc3RBUEkpIl0KICAgICAgICBPcmNoZXN0cmF0b3JbIkFnZW50IE9yY2hlc3RyYXRvciJdCiAgICBlbmQKCiAgICBzdWJncmFwaCBJbnRlbGxpZ2VuY2UKICAgICAgICBUcnVlRm91bmRyeVsiVHJ1ZUZvdW5kcnkgQUkgR2F0ZXdheTxici8+TW9kZWwgRXNjYWxhdGlvbiJdCiAgICAgICAgTWFjcm9zY29wZVsiTWFjcm9zY29wZTxici8+R2l0SHViIFBSIEFuYWx5c2lzIl0KICAgIGVuZAoKICAgIHN1YmdyYXBoIFJlc29sdXRpb24KICAgICAgICBCbGFuZFsiQmxhbmQgQUk8YnIvPkludGVyYWN0aXZlIFBob25lIENhbGwiXQogICAgICAgIEF1dGgwWyJBdXRoMDxici8+Q0lCQSBBdXRoICsgVG9rZW4gVmF1bHQiXQogICAgZW5kCgogICAgc3ViZ3JhcGggUmVwb3J0aW5nCiAgICAgICAgR2hvc3RbIkdob3N0IENNUzxici8+VGllcmVkIFJlcG9ydHMiXQogICAgICAgIE92ZXJtaW5kWyJPdmVybWluZDxici8+TExNIFRyYWNpbmciXQogICAgZW5kCgogICAgQWlyYnl0ZSAtLT58IkluZ2VzdCJ8IE9yY2hlc3RyYXRvcgogICAgT3JjaGVzdHJhdG9yIDwtLT58IlF1ZXJ5InwgVHJ1ZUZvdW5kcnkKICAgIFRydWVGb3VuZHJ5IC0uLT58IlRyYWNlInwgT3Zlcm1pbmQKICAgIE9yY2hlc3RyYXRvciA8LS0+fCJRdWVyeSBQUnMifCBNYWNyb3Njb3BlCiAgICBPcmNoZXN0cmF0b3IgLS0+fCJUcmlnZ2VyIENhbGwifCBCbGFuZAogICAgQmxhbmQgPC0tPnwiTWlkLWNhbGwgRGF0YSJ8IE9yY2hlc3RyYXRvcgogICAgQmxhbmQgLS0+fCJBcHByb3ZhbCJ8IEF1dGgwCiAgICBBdXRoMCAtLT58IkF1dGhvcml6ZSBGaXgifCBPcmNoZXN0cmF0b3IKICAgIE9yY2hlc3RyYXRvciAtLT58IlB1Ymxpc2gifCBHaG9zdA==)

## How We Built It (The Creative Uses)

We refused to do basic integrations. Every sponsor tool was pushed to handle unpopular or highly creative features:

### Auth0 — CIBA & Token Vault (`sentinelcall/auth0_ciba.py`)

Instead of a standard login page, we used Auth0's **CIBA (Client Initiated Backchannel Authentication)**. The auth flow isn't triggered by a browser—it's triggered by the engineer's voice on a phone call. Furthermore, the agent never holds raw API keys; everything is secured using Auth0's **Token Vault**.

### Airbyte — Dynamic Orchestration (`sentinelcall/airbyte_dynamic.py`)

Instead of static daily data pulls, Pager0 uses `PyAirbyte` to **dynamically create connectors** based on the incident type. If the database spikes, it spins up a Postgres connector on the fly; if Redis slows down, it spins up a Redis connector. 

### Bland AI — Mid-Call Function Calling (`sentinelcall/bland_pathway.py`)

Not just an outbound notification bot. We built an interactive pathway with **function calling**. The on-call engineer can interrupt the bot, ask for live metrics ("What's the CPU at?"), and the bot queries the FastAPI backend mid-conversation before proceeding.

### Ghost CMS — Tiered Publishing (`sentinelcall/ghost_incident_reports.py`)

Instead of publishing standard blog posts, we use the Admin API and JWT auth to publish **tiered incident reports**. It automatically tags a sanitized summary as `public` for the executive dashboard, and a deep-dive RCA as `members-only` for the engineering team.

### TrueFoundry & Overmind — Escalation & Observability

We route 100% of LLM calls through **TrueFoundry**, implementing **dynamic model escalation** (cheap models for log parsing, expensive models for RCA) and strict guardrails. We wrapped this entirely in **Overmind** (`overmind.init()`) to trace the agent's decision tree and display live prompt optimization recommendations.

### Macroscope — PR-Linked RCA (`sentinelcall/macroscope_rca.py`)

Instead of just installing a GitHub app, Pager0 queries Macroscope's PR reviews programmatically to identify the exact code change that caused the live infrastructure incident.

## Challenges We Ran Into

- **Syncing Voice with Backend Auth**: Tying a synchronous Bland AI phone call to an asynchronous Auth0 CIBA flow required careful state management in our FastAPI webhook server. We solved this by using the Bland pathway variables to pass a unique CIBA `auth_req_id` that the webhook could resolve upon verbal confirmation.
- **Dynamic Airbyte Connectors**: PyAirbyte is incredibly powerful but managing ephemeral caching and state for connectors created *during* an active incident required strict memory management to prevent the agent from bogging down.
- **LLM Hallucinations in RCA**: When dealing with infrastructure, guessing is dangerous. We utilized TrueFoundry's guardrails to force the LLM to ground its assertions strictly in the logs provided by Airbyte and the PR diffs from Macroscope.

## Accomplishments We're Proud Of

- **47-Second Resolution**: From anomaly detection to code revert and published post-mortem, the entire pipeline executes in under a minute.
- **Voice-First SRE**: We successfully proved that a phone call is the ultimate UI for high-stakes approvals. No laptops required at 3 AM.
- **Zero-Trust Agent**: By utilizing Auth0 Token Vault, our autonomous agent executes complex integrations without ever holding a raw API secret in its memory.

## What We Learned

- **Context is everything in incident response.** An LLM looking at a CPU spike is useless. An LLM looking at a CPU spike *and* the specific Macroscope GitHub PR that caused it is magic.
- **CIBA + Voice is the future of Ops.** Approving critical infrastructure changes verbally over a secure backchannel auth flow feels like science fiction, but it's entirely possible today.

## What's Next

- **Auto-Remediation Code Generation**: Instead of just reverting PRs, having the agent write the fix, open a new PR, and ask the engineer to approve the merge.
- **Predictive Anomaly Detection**: Shifting from reactive incident response to predictive scaling by analyzing Airbyte metrics trends before the threshold is breached.

## Built With

`python` `fastapi` `airbyte` `auth0` `bland-ai` `ghost-cms` `truefoundry` `macroscope` `overmind` `next.js`