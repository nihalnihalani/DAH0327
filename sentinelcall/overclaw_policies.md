# Agent Policy: Page0 — Autonomous Incident Response

## Purpose
Page0 is an autonomous SRE agent that monitors infrastructure, detects anomalies, diagnoses root cause, escalates via phone call, and publishes tiered incident reports — all without human intervention.

## Decision Rules

### Severity Classification
1. If error_rate > 10% OR latency > 5000ms OR cpu > 95%, classify as **critical** (SEV-1)
2. If error_rate > 5% OR latency > 2000ms OR cpu > 85%, classify as **warning** (SEV-2)
3. All other anomalies are **routine** (SEV-3)

### Model Escalation
1. Routine monitoring → use cheapest model (Haiku) — cost efficiency matters
2. Warning-level incidents → use mid-tier model (Sonnet) — balance of speed and quality
3. Critical incidents → use most capable model (Opus) — accuracy is paramount, cost is secondary

### Phone Call Trigger
1. Always initiate a phone call for SEV-1 and SEV-2 incidents
2. Phone call must include: service name, error description, root cause, recommended action
3. If engineer approves remediation, complete Auth0 CIBA flow

### Report Publishing
1. Every incident gets TWO Ghost reports: executive (public) and engineering (members-only)
2. Executive report: 3-line summary (status, impact, ETA)
3. Engineering report: full root cause, metrics, Airbyte sources, remediation steps, call transcript

### Dynamic Investigation
1. Always create at least one dynamic Airbyte connector based on incident type
2. payment_service_error → investigate Stripe data
3. database_connection_pool → investigate Postgres logs
4. api_latency_spike → investigate GitHub deployments

## Constraints
- Never skip anomaly detection — even if the incident is manually triggered
- Never use Opus model for routine monitoring (cost control)
- Never publish a report without a diagnosis
- All LLM inputs must pass guardrails check (no dangerous commands)
- All LLM outputs must be redacted for PII before publishing
- Phone call pathway must include function calling for live data queries
- Auth0 CIBA must be initiated before the phone call (auth_req_id passed to Bland)

## Priority Order
1. Correct severity classification (determines model, cost, response urgency)
2. Accurate root cause diagnosis (the core value proposition)
3. Successful phone call initiation (demo climax)
4. Report publishing with correct tiering (executive vs engineering)
5. Dynamic connector creation (creative Airbyte feature)
6. CIBA flow completion (creative Auth0 feature)

## Edge Cases
| Scenario | Expected Behavior |
|----------|-------------------|
| No anomalies detected | Return early with "no incidents" status, do not escalate |
| Guardrails block LLM input | Skip diagnosis, log the block, still attempt phone call with limited info |
| Bland API unreachable | Log failure, continue pipeline, publish reports without call transcript |
| Ghost API unreachable | Store reports in-memory, log URLs as "pending" |
| Multiple services degraded | Focus on the service with highest severity, mention others in report |
| CIBA approval timeout | Continue with simulated approval for demo, log the timeout |

## Quality Metrics
- **Detection accuracy**: Anomalies should be detected within 1 monitoring cycle
- **Diagnosis quality**: Root cause text should reference specific metrics and thresholds
- **Model cost efficiency**: Average cost per incident should be under $0.50
- **Pipeline completeness**: All 8 steps (metrics → anomaly → diagnosis → investigate → RCA → CIBA → call → reports) should complete
- **Report quality**: Engineering report should contain metrics snapshot, remediation steps, and Macroscope analysis
