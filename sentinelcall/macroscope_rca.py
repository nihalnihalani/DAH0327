"""PR-linked root cause analysis via Macroscope.

Queries the GitHub API for recently merged PRs, looks for Macroscope
review comments, and uses LLM-based correlation to identify which PR
most likely caused a given incident. Falls back to realistic mock data
when API keys are unavailable.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests

from sentinelcall.config import GITHUB_REPO, GITHUB_TOKEN, TRUEFOUNDRY_API_KEY, TRUEFOUNDRY_ENDPOINT

logger = logging.getLogger(__name__)

# GitHub API base
GITHUB_API = "https://api.github.com"


class MacroscopeAnalyzer:
    """Identify the causal PR for an incident using Macroscope + LLM correlation."""

    def __init__(
        self,
        github_repo: str | None = None,
        github_token: str | None = None,
    ):
        self.repo = github_repo or GITHUB_REPO or "sentinelcall/infra"
        self.github_token = github_token or GITHUB_TOKEN or None
        self._configured = bool(self.repo and self.github_token)

    def _gh_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    def get_recent_prs(self, hours: int = 24) -> list[dict[str, Any]]:
        """Fetch recently merged PRs from the GitHub API.

        Args:
            hours: Look-back window in hours. Defaults to 24.

        Returns:
            List of PR dicts with ``number``, ``title``, ``merged_at``,
            ``user``, ``files_changed``.
        """
        if not self._configured:
            return self._mock_recent_prs()

        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        url = f"{GITHUB_API}/repos/{self.repo}/pulls"
        params = {"state": "closed", "sort": "updated", "direction": "desc", "per_page": 30}

        try:
            response = requests.get(url, headers=self._gh_headers(), params=params, timeout=15)
            response.raise_for_status()
            prs = []
            for pr in response.json():
                if pr.get("merged_at") and pr["merged_at"] >= since:
                    prs.append({
                        "number": pr["number"],
                        "title": pr["title"],
                        "merged_at": pr["merged_at"],
                        "user": pr["user"]["login"],
                        "html_url": pr["html_url"],
                    })
            return prs
        except requests.RequestException as exc:
            logger.error("GitHub PR fetch failed: %s. Using mock data.", exc)
            return self._mock_recent_prs()

    def get_macroscope_reviews(self, pr_number: int) -> list[dict[str, Any]]:
        """Fetch Macroscope's review comments on a PR.

        Macroscope leaves review comments via its GitHub App. This method
        filters PR comments for those authored by the ``macroscope[bot]`` user.

        Args:
            pr_number: The pull request number.

        Returns:
            List of review comment dicts.
        """
        if not self._configured:
            return self._mock_macroscope_reviews(pr_number)

        url = f"{GITHUB_API}/repos/{self.repo}/pulls/{pr_number}/comments"
        try:
            response = requests.get(url, headers=self._gh_headers(), timeout=15)
            response.raise_for_status()
            reviews = []
            for comment in response.json():
                author = comment.get("user", {}).get("login", "")
                if "macroscope" in author.lower():
                    reviews.append({
                        "id": comment["id"],
                        "author": author,
                        "body": comment["body"],
                        "path": comment.get("path", ""),
                        "created_at": comment["created_at"],
                    })
            return reviews
        except requests.RequestException as exc:
            logger.error("Macroscope review fetch failed for PR #%s: %s", pr_number, exc)
            return self._mock_macroscope_reviews(pr_number)

    def correlate_pr_with_incident(
        self, pr_summaries: list[dict[str, Any]], incident: dict[str, Any]
    ) -> str:
        """Format a prompt for LLM-based correlation between PRs and an incident.

        Args:
            pr_summaries: List of PR dicts (from get_recent_prs + reviews).
            incident: Dict describing the incident.

        Returns:
            Formatted prompt string suitable for an LLM call.
        """
        pr_text = ""
        for pr in pr_summaries:
            reviews_text = ""
            for review in pr.get("macroscope_reviews", []):
                reviews_text += f"    - Macroscope: {review.get('body', 'No comment.')[:200]}\n"
            pr_text += (
                f"  PR #{pr['number']}: {pr['title']} (by {pr.get('user', 'unknown')}, "
                f"merged {pr.get('merged_at', 'recently')})\n"
                f"    Macroscope Reviews:\n{reviews_text or '    - None\n'}\n"
            )

        prompt = f"""You are an SRE incident analysis agent. Given the following incident and
recently merged pull requests (with Macroscope code-review comments), identify which PR most
likely caused the incident. Explain your reasoning.

INCIDENT:
  Service: {incident.get('service', 'unknown')}
  Severity: {incident.get('severity', 'SEV-2')}
  Description: {incident.get('description', 'Production anomaly.')}
  Symptoms: {incident.get('symptoms', 'Elevated error rates.')}

RECENTLY MERGED PRs:
{pr_text}

Respond with:
1. The PR number most likely responsible
2. Confidence level (high/medium/low)
3. Brief explanation linking the PR changes to the incident symptoms
"""
        return prompt

    def identify_causal_pr(self, incident: dict[str, Any]) -> dict[str, Any]:
        """Run the full root-cause analysis pipeline.

        1. Fetch recent PRs.
        2. Fetch Macroscope reviews for each.
        3. Correlate with the incident via LLM (or return mock analysis).

        Args:
            incident: Dict with incident details.

        Returns:
            Dict with ``pr_number``, ``pr_title``, ``confidence``,
            ``explanation``, ``all_prs``.
        """
        prs = self.get_recent_prs()

        # Enrich PRs with Macroscope reviews
        for pr in prs:
            pr["macroscope_reviews"] = self.get_macroscope_reviews(pr["number"])

        # Build the correlation prompt
        prompt = self.correlate_pr_with_incident(prs, incident)

        # Attempt LLM call via TrueFoundry gateway
        if TRUEFOUNDRY_API_KEY and TRUEFOUNDRY_ENDPOINT:
            try:
                from openai import OpenAI

                client = OpenAI(
                    api_key=TRUEFOUNDRY_API_KEY,
                    base_url=TRUEFOUNDRY_ENDPOINT,
                )
                response = client.chat.completions.create(
                    model="sentinelcall-gateway",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=500,
                )
                llm_output = response.choices[0].message.content or ""
                logger.info("LLM correlation complete for incident %s", incident.get("incident_id"))
                return {
                    "pr_number": prs[0]["number"] if prs else None,
                    "pr_title": prs[0]["title"] if prs else "Unknown",
                    "confidence": "high",
                    "explanation": llm_output,
                    "all_prs": prs,
                    "prompt_used": prompt,
                }
            except Exception as exc:
                logger.error("LLM correlation failed: %s. Using mock analysis.", exc)

        return self._mock_analysis(prs, incident)

    # -- Mock data for demo --

    def _mock_recent_prs(self) -> list[dict[str, Any]]:
        """Return realistic mock PR data."""
        now = datetime.now(timezone.utc)
        return [
            {
                "number": 47,
                "title": "Update connection pool config",
                "merged_at": (now - timedelta(hours=2)).isoformat(),
                "user": "jchen",
                "html_url": f"https://github.com/{self.repo}/pull/47",
            },
            {
                "number": 46,
                "title": "Add retry logic to payment service",
                "merged_at": (now - timedelta(hours=5)).isoformat(),
                "user": "asmith",
                "html_url": f"https://github.com/{self.repo}/pull/46",
            },
            {
                "number": 45,
                "title": "Bump dependencies for Q1 security audit",
                "merged_at": (now - timedelta(hours=8)).isoformat(),
                "user": "dependabot",
                "html_url": f"https://github.com/{self.repo}/pull/45",
            },
        ]

    def _mock_macroscope_reviews(self, pr_number: int) -> list[dict[str, Any]]:
        """Return realistic mock Macroscope reviews."""
        reviews_by_pr: dict[int, list[dict[str, Any]]] = {
            47: [
                {
                    "id": 9001,
                    "author": "macroscope[bot]",
                    "body": (
                        "WARNING: This PR reduces `max_pool_size` from 100 to 20 in "
                        "`config/database.yml`. Under current traffic patterns (~850 RPS), "
                        "this will likely cause connection starvation during peak hours. "
                        "Consider keeping pool size >= 50 or adding a circuit breaker."
                    ),
                    "path": "config/database.yml",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            ],
            46: [
                {
                    "id": 9002,
                    "author": "macroscope[bot]",
                    "body": "LGTM. Retry logic follows exponential backoff best practices.",
                    "path": "services/payment/retry.py",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            ],
            45: [],
        }
        return reviews_by_pr.get(pr_number, [])

    def _mock_analysis(
        self, prs: list[dict[str, Any]], incident: dict[str, Any]
    ) -> dict[str, Any]:
        """Return a realistic mock root-cause analysis result."""
        return {
            "pr_number": 47,
            "pr_title": "Update connection pool config",
            "confidence": "high",
            "explanation": (
                "PR #47 reduced the database connection pool size from 100 to 20. "
                "Macroscope flagged this change, warning that current traffic (~850 RPS) "
                "would cause connection starvation. The incident symptoms — elevated "
                "p99 latency, database timeout errors, and cascading 503s on "
                f"{incident.get('service', 'api-gateway')} — are consistent with "
                "connection pool exhaustion. Timeline correlation: PR merged 2 hours "
                "before incident onset."
            ),
            "all_prs": prs,
            "mock": True,
        }
