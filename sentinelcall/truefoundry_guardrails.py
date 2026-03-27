"""TrueFoundry Guardrails — input validation and output sanitization.

TrueFoundry AI Gateway supports guardrails configuration via YAML rules
(type: gateway-guardrails-config) with four hook points:
  - llm_input_guardrails:  applied before LLM requests
  - llm_output_guardrails: applied after LLM responses
  - mcp_tool_pre_invoke_guardrails:  before MCP tool execution
  - mcp_tool_post_invoke_guardrails: after MCP tool results

Each rule has a ``when`` block for targeting specific models, users, or
metadata.  Page0 implements local guardrails that mirror what would
be deployed as a custom guardrails server (FastAPI) registered with
TrueFoundry.

The local guardrails always run regardless of mode.  When TrueFoundry
is configured, the gateway's server-side guardrails run in addition
to local checks.

See: https://github.com/truefoundry/custom-guardrails-template
"""

import re
import logging
from dataclasses import dataclass, field

from sentinelcall.config import TRUEFOUNDRY_API_KEY, TRUEFOUNDRY_ENDPOINT

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dangerous input patterns (local guardrails — always active)
# ---------------------------------------------------------------------------
INPUT_BLOCK_PATTERNS: list[dict] = [
    {"pattern": r"DROP\s+TABLE", "label": "SQL DROP TABLE", "flags": re.IGNORECASE},
    {"pattern": r"DELETE\s+FROM\s+\w+\s*(;|WHERE\s+1\s*=\s*1)", "label": "SQL mass delete", "flags": re.IGNORECASE},
    {"pattern": r"rm\s+-rf\s+/", "label": "Destructive rm -rf", "flags": 0},
    {"pattern": r"shutdown\s+--now", "label": "System shutdown", "flags": 0},
    {"pattern": r"mkfs\.\w+", "label": "Filesystem format", "flags": 0},
    {"pattern": r":(){ :\|:& };:", "label": "Fork bomb", "flags": 0},
    {"pattern": r"curl\s+.*\|\s*sh", "label": "Pipe to shell", "flags": 0},
    {"pattern": r"eval\s*\(", "label": "Eval injection", "flags": 0},
    {"pattern": r"__import__\s*\(", "label": "Python import injection", "flags": 0},
]

# ---------------------------------------------------------------------------
# PII / secret patterns for output redaction (local guardrails — always active)
#
# In production, TrueFoundry's custom guardrails server would handle PII
# detection via Presidio with presets like "US", "FINANCIAL", "COMPREHENSIVE".
# These local patterns are a lightweight baseline that always runs.
# ---------------------------------------------------------------------------
OUTPUT_REDACTION_PATTERNS: list[dict] = [
    {
        "pattern": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
        "label": "phone_number",
        "replacement": "[REDACTED_PHONE]",
    },
    {
        "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "label": "email",
        "replacement": "[REDACTED_EMAIL]",
    },
    {
        "pattern": r"\b\d{3}-\d{2}-\d{4}\b",
        "label": "ssn",
        "replacement": "[REDACTED_SSN]",
    },
    {
        "pattern": (
            r"(?:api[_-]?key|apikey|api[_-]?token|secret[_-]?key|access[_-]?token)"
            r"\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{16,}['\"]?"
        ),
        "label": "api_key",
        "replacement": "[REDACTED_API_KEY]",
        "flags": re.IGNORECASE,
    },
    {
        "pattern": (
            r"(?:password|passwd|pwd)\s*[=:]\s*['\"]?[^\s'\"]{4,}['\"]?"
        ),
        "label": "password",
        "replacement": "[REDACTED_PASSWORD]",
        "flags": re.IGNORECASE,
    },
    {
        "pattern": r"\b(?:sk|pk)[-_](?:live|test)[-_][A-Za-z0-9]{20,}\b",
        "label": "stripe_key",
        "replacement": "[REDACTED_STRIPE_KEY]",
    },
    {
        "pattern": r"\bghp_[A-Za-z0-9]{36,}\b",
        "label": "github_token",
        "replacement": "[REDACTED_GITHUB_TOKEN]",
    },
    {
        "pattern": r"\bxox[bpoas]-[A-Za-z0-9\-]{10,}\b",
        "label": "slack_token",
        "replacement": "[REDACTED_SLACK_TOKEN]",
    },
]


@dataclass
class GuardrailsConfig:
    """Guardrails for input validation and output sanitization.

    When TrueFoundry is configured, the gateway applies server-side
    guardrails (configured via ``gateway-guardrails-config`` YAML).
    Local pattern-based checks always run as a baseline defense layer.

    TrueFoundry guardrails YAML structure::

        name: page0-guardrails
        type: gateway-guardrails-config
        rules:
          - id: page0-safety
            when: {}  # match all requests
            llm_input_guardrails:
              - page0/input-safety-check
            llm_output_guardrails:
              - page0/pii-redaction
            mcp_tool_pre_invoke_guardrails: []
            mcp_tool_post_invoke_guardrails: []
    """

    max_output_cost_usd: float = 1.00
    max_prompt_length: int = 50_000
    blocked_input_count: int = 0
    redacted_output_count: int = 0
    is_live: bool = field(init=False)

    def __post_init__(self) -> None:
        self.is_live = bool(TRUEFOUNDRY_API_KEY and TRUEFOUNDRY_ENDPOINT)
        mode = "TrueFoundry + local" if self.is_live else "local-only"
        logger.info("GuardrailsConfig: initialized (%s mode)", mode)

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------

    def check_input(self, text: str) -> tuple[bool, str]:
        """Validate input text against guardrails.

        Local checks always run. When TrueFoundry is configured, the
        gateway's server-side input guardrails provide an additional
        layer (e.g. Palo Alto Prisma AIRS, custom classifiers).

        Args:
            text: The prompt or user input to validate.

        Returns:
            Tuple of ``(is_safe, reason)``.
        """
        # Length check
        if len(text) > self.max_prompt_length:
            self.blocked_input_count += 1
            return False, f"Prompt exceeds max length ({len(text)} > {self.max_prompt_length})"

        # Pattern checks (local baseline)
        for entry in INPUT_BLOCK_PATTERNS:
            flags = entry.get("flags", 0)
            if re.search(entry["pattern"], text, flags):
                self.blocked_input_count += 1
                reason = f"Blocked: input matches dangerous pattern [{entry['label']}]"
                logger.warning("Guardrails: %s", reason)
                return False, reason

        return True, "Input passed all guardrails"

    # ------------------------------------------------------------------
    # Output sanitization
    # ------------------------------------------------------------------

    def check_output(self, text: str) -> tuple[str, list[dict]]:
        """Validate and sanitize output text.

        Local PII/secret redaction always runs. When TrueFoundry is
        configured, the gateway's output guardrails provide additional
        protection (e.g. Presidio PII detection with configurable
        recognizer presets).

        Args:
            text: The LLM response or text to sanitize.

        Returns:
            Tuple of ``(cleaned_text, redactions)``.
        """
        redactions: list[dict] = []
        cleaned = text

        for entry in OUTPUT_REDACTION_PATTERNS:
            flags = entry.get("flags", 0)
            matches = list(re.finditer(entry["pattern"], cleaned, flags))
            if matches:
                for m in matches:
                    redactions.append({
                        "type": entry["label"],
                        "position": m.start(),
                        "length": len(m.group()),
                    })
                cleaned = re.sub(entry["pattern"], entry["replacement"], cleaned, flags=flags)

        if redactions:
            self.redacted_output_count += len(redactions)
            logger.info(
                "Guardrails: redacted %d sensitive items from output", len(redactions)
            )

        return cleaned, redactions

    # ------------------------------------------------------------------
    # TrueFoundry guardrails config export
    # ------------------------------------------------------------------

    def get_truefoundry_config(self) -> dict:
        """Return the TrueFoundry guardrails YAML config for this agent.

        This represents the ``gateway-guardrails-config`` that would be
        applied in the TrueFoundry UI or via CLI to enable server-side
        guardrails in addition to local checks.
        """
        return {
            "name": "page0-guardrails",
            "type": "gateway-guardrails-config",
            "rules": [
                {
                    "id": "page0-input-safety",
                    "when": {
                        "target": {
                            "operator": "or",
                            "conditions": {
                                "metadata": {
                                    "values": {"source": "page0"},
                                    "condition": "in",
                                },
                            },
                        },
                        "subjects": {
                            "operator": "and",
                            "conditions": {
                                "in": ["team:everyone"],
                            },
                        },
                    },
                    "llm_input_guardrails": [
                        "page0/input-safety-check",
                    ],
                    "llm_output_guardrails": [
                        "page0/pii-redaction",
                    ],
                    "mcp_tool_pre_invoke_guardrails": [],
                    "mcp_tool_post_invoke_guardrails": [],
                },
                {
                    "id": "page0-catch-all",
                    "when": {},
                    "llm_input_guardrails": [],
                    "llm_output_guardrails": [
                        "page0/pii-redaction",
                    ],
                    "mcp_tool_pre_invoke_guardrails": [],
                    "mcp_tool_post_invoke_guardrails": [],
                },
            ],
        }

    # ------------------------------------------------------------------
    # Summary (for demo dashboard)
    # ------------------------------------------------------------------

    def get_guardrails_summary(self) -> dict:
        """Return guardrails configuration summary for dashboard display."""
        return {
            "mode": "truefoundry_plus_local" if self.is_live else "local_only",
            "truefoundry_gateway_guardrails": {
                "enabled": self.is_live,
                "config_type": "gateway-guardrails-config",
                "hook_points": [
                    "llm_input_guardrails",
                    "llm_output_guardrails",
                    "mcp_tool_pre_invoke_guardrails",
                    "mcp_tool_post_invoke_guardrails",
                ],
                "description": (
                    "Server-side guardrails applied by TrueFoundry gateway. "
                    "Configured via YAML rules with model/user/metadata targeting."
                ),
            },
            "local_guardrails": {
                "input_guardrails": {
                    "patterns_count": len(INPUT_BLOCK_PATTERNS),
                    "patterns": [e["label"] for e in INPUT_BLOCK_PATTERNS],
                    "max_prompt_length": self.max_prompt_length,
                    "total_blocked": self.blocked_input_count,
                },
                "output_guardrails": {
                    "redaction_patterns_count": len(OUTPUT_REDACTION_PATTERNS),
                    "redaction_types": [e["label"] for e in OUTPUT_REDACTION_PATTERNS],
                    "max_output_cost_usd": self.max_output_cost_usd,
                    "total_redactions": self.redacted_output_count,
                },
            },
        }
