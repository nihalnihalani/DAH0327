"""Page0 Agent — autonomous incident response orchestrator.

Coordinates every module in the pipeline:
  Metrics -> Anomaly Detection -> LLM Diagnosis -> Dynamic Investigation ->
  Macroscope RCA -> Auth0 CIBA -> Bland AI Phone Call -> Ghost Reports ->
  Overmind Tracing

Works entirely in demo mode (mock data) when API keys are absent.
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sentinelcall.airbyte_monitor import AirbyteMonitor
from sentinelcall.airbyte_dynamic import DynamicConnectorManager
from sentinelcall.anomaly_detector import AnomalyDetector
from sentinelcall.auth0_vault import TokenVault
from sentinelcall.auth0_ciba import CIBAManager
from sentinelcall.truefoundry_gateway import TrueFoundryGateway
from sentinelcall.truefoundry_guardrails import GuardrailsConfig
from sentinelcall.bland_caller import make_incident_call, get_call_status, get_call_transcript
from sentinelcall.bland_pathway import create_pathway, get_pathway_id
from sentinelcall.ghost_publisher import GhostPublisher
from sentinelcall.ghost_incident_reports import IncidentReportPublisher
from sentinelcall.ghost_webhooks import setup_ghost_webhooks
from sentinelcall.macroscope_rca import MacroscopeAnalyzer
from sentinelcall.overmind_setup import OvermindTracer
from sentinelcall.mock_infra import MockInfrastructure
from sentinelcall.config import ON_CALL_ENGINEER_ID, WEBHOOK_BASE_URL

logger = logging.getLogger(__name__)


class SentinelCallAgent:
    """The brain of Page0 — orchestrates the full incident response pipeline."""

    def __init__(self) -> None:
        # Infrastructure & monitoring
        self.infra = MockInfrastructure()
        self.airbyte = AirbyteMonitor()
        self.dynamic_connectors = DynamicConnectorManager()
        self.anomaly_detector = AnomalyDetector()

        # Auth & security
        self.token_vault = TokenVault()
        self.ciba = CIBAManager()

        # LLM gateway
        self.gateway = TrueFoundryGateway()
        self.guardrails = GuardrailsConfig()

        # Incident communication
        self.ghost = GhostPublisher()
        self.report_publisher = IncidentReportPublisher(self.ghost)

        # Root cause analysis
        self.macroscope = MacroscopeAnalyzer()

        # Observability
        self.tracer = OvermindTracer()
        self.tracer.init()

        # State
        self.current_status: str = "idle"
        self.incidents: list[dict[str, Any]] = []
        self._event_subscribers: list[asyncio.Queue] = []

        logger.info("Page0 agent initialized — all modules ready")

    # ------------------------------------------------------------------
    # SSE event broadcasting
    # ------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        """Return a new queue that will receive SSE events."""
        q: asyncio.Queue = asyncio.Queue()
        self._event_subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a subscriber queue."""
        try:
            self._event_subscribers.remove(q)
        except ValueError:
            pass

    async def _broadcast(self, event_type: str, data: dict[str, Any]) -> None:
        """Push an event to all SSE subscribers."""
        payload = {"event": event_type, "data": data, "timestamp": time.time()}
        for q in list(self._event_subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    # ------------------------------------------------------------------
    # Full incident response pipeline
    # ------------------------------------------------------------------

    async def run_incident_response(self, service: str | None = None) -> dict[str, Any]:
        """Execute the complete incident response pipeline.

        Steps:
          1. Pull metrics
          2. Detect anomalies
          3. Classify severity & escalate LLM model
          4. Diagnose root cause with LLM
          5. Dynamic Airbyte investigation
          6. Macroscope PR correlation
          7. Auth0 CIBA approval flow
          8. Bland AI phone call
          9. Ghost tiered reports
         10. Overmind decision trace

        Args:
            service: Service to target. Defaults to ``payment-service``.

        Returns:
            Full incident record dict.
        """
        self.current_status = "responding"
        pipeline_start = time.time()
        service = service or "payment-service"
        incident_id = f"INC-{uuid.uuid4().hex[:8]}"
        incident_type = "cache_failure"

        incident_record: dict[str, Any] = {
            "incident_id": incident_id,
            "service": service,
            "incident_type": incident_type,
            "started_at": pipeline_start,
            "status": "investigating",
            "steps": {},
        }

        await self._broadcast("incident_start", {"incident_id": incident_id, "service": service})
        await asyncio.sleep(1.0)  # Let dashboard animate the incident start

        try:
            # ---- Step 1: Trigger incident & pull metrics ----
            step_start = time.time()
            self.infra.trigger_incident(service=service, incident_type=incident_type)
            metrics = self.infra.get_metrics()
            step_time = time.time() - step_start

            incident_record["steps"]["metrics"] = {
                "duration_ms": round(step_time * 1000, 1),
                "services_monitored": len(metrics),
            }
            self.tracer.record_decision(
                step="metrics_collection",
                input_data={"service": service},
                output_data={"services": len(metrics)},
                model_used="mock_infra",
            )
            await self._broadcast("step_complete", {"step": "metrics_collection", "duration_ms": round(step_time * 1000, 1)})
            await asyncio.sleep(1.5)  # Pause so dashboard can animate this step

            # ---- Step 2: Detect anomalies ----
            step_start = time.time()
            anomalies = self.anomaly_detector.detect_anomalies(metrics)
            severity = self.anomaly_detector.classify_severity(anomalies)
            anomaly_text = self.anomaly_detector.format_for_diagnosis(anomalies)
            step_time = time.time() - step_start

            incident_record["severity"] = f"SEV-{'1' if severity == 'critical' else '2' if severity == 'warning' else '3'}"
            incident_record["anomaly_count"] = len(anomalies)
            incident_record["steps"]["anomaly_detection"] = {
                "duration_ms": round(step_time * 1000, 1),
                "anomalies_found": len(anomalies),
                "severity": severity,
            }
            self.tracer.record_decision(
                step="anomaly_detection",
                input_data={"metrics_count": len(metrics)},
                output_data={"anomalies": len(anomalies), "severity": severity},
                model_used="statistical+threshold",
            )
            await self._broadcast("step_complete", {
                "step": "anomaly_detection",
                "anomalies": len(anomalies),
                "severity": severity,
            })
            await asyncio.sleep(1.5)  # Pause so dashboard can animate this step

            # ---- Step 3: LLM severity escalation & diagnosis ----
            step_start = time.time()
            is_safe, reason = self.guardrails.check_input(anomaly_text)
            if is_safe:
                diagnosis_result = self.gateway.llm_call(
                    prompt=anomaly_text,
                    severity=severity,
                    system_prompt=(
                        "You are Page0, an autonomous SRE agent. "
                        "Analyze these anomalies and provide root cause, "
                        "impact assessment, and remediation steps."
                    ),
                )
                diagnosis_text = diagnosis_result["response"]
                diagnosis_text, redactions = self.guardrails.check_output(diagnosis_text)
                model_used = diagnosis_result["model"]
            else:
                diagnosis_text = f"Guardrails blocked input: {reason}"
                model_used = "blocked"
                redactions = []

            step_time = time.time() - step_start
            incident_record["diagnosis"] = diagnosis_text
            incident_record["model_used"] = model_used
            incident_record["steps"]["llm_diagnosis"] = {
                "duration_ms": round(step_time * 1000, 1),
                "model": model_used,
                "severity_tier": severity,
                "redactions": len(redactions),
            }
            self.tracer.record_decision(
                step="llm_diagnosis",
                input_data={"anomaly_text_len": len(anomaly_text)},
                output_data={"model": model_used, "response_len": len(diagnosis_text)},
                model_used=model_used,
            )
            await self._broadcast("step_complete", {
                "step": "llm_diagnosis",
                "model": model_used,
                "severity": severity,
            })
            await asyncio.sleep(2.0)  # Pause so dashboard can animate this step (longer for LLM)

            # ---- Step 4: Dynamic Airbyte investigation ----
            step_start = time.time()
            investigation = self.dynamic_connectors.dynamically_investigate(
                incident_type=incident_type,
                context={"service": service},
            )
            connector_summary = self.dynamic_connectors.get_investigation_summary()
            step_time = time.time() - step_start

            incident_record["steps"]["dynamic_investigation"] = {
                "duration_ms": round(step_time * 1000, 1),
                "connectors_created": connector_summary["total_connectors_created"],
                "status": investigation.get("status"),
            }
            self.tracer.record_decision(
                step="dynamic_airbyte_investigation",
                input_data={"incident_type": incident_type},
                output_data={"connectors": connector_summary["total_connectors_created"]},
                model_used="airbyte_dynamic",
            )
            await self._broadcast("step_complete", {
                "step": "dynamic_investigation",
                "connectors_created": connector_summary["total_connectors_created"],
            })
            await asyncio.sleep(1.5)  # Pause so dashboard can animate this step

            # ---- Step 5: Macroscope PR root cause ----
            step_start = time.time()
            macroscope_result = self.macroscope.identify_causal_pr({
                "incident_id": incident_id,
                "service": service,
                "severity": incident_record["severity"],
                "description": diagnosis_text[:200],
                "symptoms": f"{len(anomalies)} anomalies detected",
            })
            step_time = time.time() - step_start

            incident_record["causal_pr"] = {
                "pr_number": macroscope_result.get("pr_number"),
                "pr_title": macroscope_result.get("pr_title"),
                "confidence": macroscope_result.get("confidence"),
                "explanation": macroscope_result.get("explanation", ""),
            }
            incident_record["steps"]["macroscope_rca"] = {
                "duration_ms": round(step_time * 1000, 1),
                "causal_pr": macroscope_result.get("pr_number"),
                "confidence": macroscope_result.get("confidence"),
            }
            self.tracer.record_decision(
                step="macroscope_rca",
                input_data={"incident_id": incident_id},
                output_data={"pr": macroscope_result.get("pr_number"), "confidence": macroscope_result.get("confidence")},
                model_used="macroscope+llm",
            )
            await self._broadcast("step_complete", {
                "step": "macroscope_rca",
                "causal_pr": macroscope_result.get("pr_number"),
            })
            await asyncio.sleep(1.5)  # Pause so dashboard can animate this step

            # ---- Step 6: Auth0 CIBA approval flow ----
            step_start = time.time()
            recommended_action = "Roll back PR #47 and restore connection pool to 100"
            ciba_result = self.ciba.initiate_ciba_approval(
                engineer_id=ON_CALL_ENGINEER_ID,
                action=recommended_action,
            )
            auth_req_id = ciba_result.get("auth_req_id", "")

            # Fetch a token from the vault to demonstrate the feature
            try:
                vault_token = self.token_vault.get_token("github")
            except Exception as exc:
                logger.warning("Token Vault unavailable (%s) — using mock token", exc)
                vault_token = {"service": "github", "source": "mock"}
            step_time = time.time() - step_start

            incident_record["ciba_auth_req_id"] = auth_req_id
            incident_record["recommended_action"] = recommended_action
            incident_record["steps"]["auth0_ciba"] = {
                "duration_ms": round(step_time * 1000, 1),
                "auth_req_id": auth_req_id,
                "vault_service": vault_token.get("service"),
            }
            self.tracer.record_decision(
                step="auth0_ciba_initiation",
                input_data={"engineer": ON_CALL_ENGINEER_ID, "action": recommended_action},
                output_data={"auth_req_id": auth_req_id},
                model_used="auth0",
            )
            await self._broadcast("step_complete", {
                "step": "auth0_ciba",
                "auth_req_id": auth_req_id,
            })
            await asyncio.sleep(1.5)  # Pause so dashboard can animate this step

            # ---- Step 7: Bland AI phone call ----
            step_start = time.time()
            pathway_result = create_pathway({
                "service": service,
                "severity": incident_record["severity"],
                "description": diagnosis_text[:300],
                "root_cause": macroscope_result.get("explanation", "Under investigation")[:300],
                "recommended_action": recommended_action,
                "engineer_id": ON_CALL_ENGINEER_ID,
            })
            pathway_id = get_pathway_id()

            call_result = make_incident_call(
                incident_context={
                    "incident_id": incident_id,
                    "service": service,
                    "severity": incident_record["severity"],
                    "description": diagnosis_text[:300],
                    "root_cause": macroscope_result.get("explanation", "Under investigation")[:300],
                    "recommended_action": recommended_action,
                    "engineer_id": ON_CALL_ENGINEER_ID,
                },
                pathway_id=pathway_id,
                ciba_auth_req_id=auth_req_id,
            )
            call_id = call_result.get("call_id", "unknown")

            # Simulate voice approval in demo mode
            self.ciba.simulate_approval(auth_req_id)

            # Get mock transcript
            transcript_data = get_call_transcript(call_id)
            step_time = time.time() - step_start

            incident_record["call_id"] = call_id
            incident_record["steps"]["bland_call"] = {
                "duration_ms": round(step_time * 1000, 1),
                "call_id": call_id,
                "pathway_id": pathway_id,
                "call_status": call_result.get("status"),
            }
            self.tracer.record_decision(
                step="bland_ai_phone_call",
                input_data={"pathway_id": pathway_id, "engineer": ON_CALL_ENGINEER_ID},
                output_data={"call_id": call_id, "status": call_result.get("status")},
                model_used="bland_ai",
            )
            await self._broadcast("step_complete", {
                "step": "bland_call",
                "call_id": call_id,
            })
            await asyncio.sleep(2.0)  # Pause so dashboard can animate this step (longer for phone call)

            # ---- Step 8: Ghost tiered reports ----
            step_start = time.time()
            # Register webhook first
            setup_ghost_webhooks(WEBHOOK_BASE_URL)

            report_result = self.report_publisher.publish_incident_report(
                incident={
                    "incident_id": incident_id,
                    "service": service,
                    "severity": incident_record["severity"],
                    "description": diagnosis_text[:500],
                    "started_at": pipeline_start,
                    "status": "remediation_in_progress",
                },
                diagnosis={
                    "root_cause": macroscope_result.get("explanation", "Under investigation"),
                    "metrics_snapshot": {
                        k: f"{v.get('error_rate', 0)}% error, {v.get('latency_ms', 0)}ms p99"
                        for k, v in metrics.items()
                        if k == service
                    },
                    "airbyte_sources": [
                        c.get("display_name", "unknown")
                        for c in connector_summary.get("connectors", [])
                    ],
                    "remediation_steps": [
                        "Roll back PR #47 (connection pool config change)",
                        "Restore max_pool_size from 20 to 100",
                        "Monitor error rates for 5 minutes post-rollback",
                        "Add CI check for connection pool size changes",
                    ],
                    "macroscope_analysis": incident_record.get("causal_pr", {}),
                    "bland_transcript": transcript_data.get("concatenated_transcript", ""),
                    "overmind_trace": self.tracer.get_decision_trace(),
                    "eta_minutes": 5,
                    "action_taken": recommended_action,
                    "impact": "Elevated error rates affecting checkout flow",
                },
            )
            step_time = time.time() - step_start

            incident_record["reports"] = {
                "executive_url": report_result.get("executive_report", {}).get("url"),
                "engineering_url": report_result.get("engineering_report", {}).get("url"),
            }
            incident_record["steps"]["ghost_reports"] = {
                "duration_ms": round(step_time * 1000, 1),
                "executive_url": report_result.get("executive_report", {}).get("url"),
                "engineering_url": report_result.get("engineering_report", {}).get("url"),
            }
            self.tracer.record_decision(
                step="ghost_report_publishing",
                input_data={"incident_id": incident_id},
                output_data={"reports_published": 2},
                model_used="ghost_cms",
            )
            await self._broadcast("step_complete", {
                "step": "ghost_reports",
                "reports_published": 2,
            })
            await asyncio.sleep(1.5)  # Pause so dashboard can animate this step

            # ---- Step 9: Resolve incident ----
            self.infra.resolve_incident()
            incident_record["status"] = "resolved"
            incident_record["resolved_at"] = time.time()
            incident_record["total_duration_seconds"] = round(time.time() - pipeline_start, 1)

            # ---- Step 10: Final Overmind trace ----
            self.tracer.record_decision(
                step="incident_resolved",
                input_data={"incident_id": incident_id},
                output_data={
                    "duration_s": incident_record["total_duration_seconds"],
                    "anomalies": len(anomalies),
                    "model_escalation": severity,
                },
                model_used="orchestrator",
            )
            incident_record["overmind_trace"] = self.tracer.get_decision_trace()
            incident_record["overmind_optimization"] = self.tracer.get_optimization_report()

            await asyncio.sleep(1.0)  # Pause before showing resolution
            await self._broadcast("incident_resolved", {
                "incident_id": incident_id,
                "duration_seconds": incident_record["total_duration_seconds"],
            })

        except Exception as exc:
            logger.exception("Incident response pipeline failed: %s", exc)
            incident_record["status"] = "failed"
            incident_record["error"] = str(exc)
            await self._broadcast("incident_error", {"incident_id": incident_id, "error": str(exc)})

        finally:
            self.current_status = "idle"
            self.incidents.append(incident_record)

        logger.info(
            "Incident %s %s in %.1fs",
            incident_id,
            incident_record["status"],
            incident_record.get("total_duration_seconds", 0),
        )
        return incident_record

    # ------------------------------------------------------------------
    # Status queries (for dashboard)
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return current agent status."""
        return {
            "agent_status": self.current_status,
            "services": {
                svc: self.infra.get_service_status(svc)
                for svc in self.infra._baselines
            },
            "total_incidents": len(self.incidents),
            "gateway_mode": self.gateway._mode,
            "token_vault_live": self.token_vault.is_live,
            "ciba_live": self.ciba.is_live,
            "guardrails": self.guardrails.get_guardrails_summary(),
            "overmind_url": self.tracer.get_dashboard_url(),
            "llm_usage": self.gateway.get_usage_stats(),
        }

    def get_incident_history(self) -> list[dict[str, Any]]:
        """Return all past incident records."""
        return list(self.incidents)
