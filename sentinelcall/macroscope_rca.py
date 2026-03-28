"""PR-linked root cause analysis via Macroscope.

Queries the GitHub API for recently merged PRs, looks for Macroscope
review comments and check-run annotations, and uses LLM-based correlation
to identify which PR most likely caused a given incident. Falls back to
realistic mock data when API keys are unavailable.

Macroscope integration details (from docs.macroscope.com):
  - GitHub App: "MacroscopeApp" (github.com/apps/macroscopeapp)
  - Bot username on PRs: "macroscope-app[bot]"
  - Mentions respond to: @macroscope-app
  - Posts: inline PR comments + check runs
  - Check run names: "Macroscope - Correctness Check", "Macroscope - Custom Rules Check"
  - Check run status: NEUTRAL when issues found, SUCCESS when clean
  - Severity levels: CRITICAL, HIGH, MEDIUM, LOW
  - Webhook API: POST macrohook.macroscope.com/api/v1/workspaces/{type}/{id}/query-agent-webhook-trigger
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

# Macroscope GitHub App bot username — this is how the bot appears in PR
# comments and reviews.  The GitHub App is "MacroscopeApp" but the [bot]
# suffix is appended automatically by GitHub for app-authored content.
MACROSCOPE_BOT_LOGIN = "macroscope-app[bot]"

# Check-run names that Macroscope creates on PRs.
MACROSCOPE_CHECK_NAMES = frozenset({
    "Macroscope - Correctness Check",
    "Macroscope - Custom Rules Check",
})

# Severity levels used by Macroscope in review comments.
MACROSCOPE_SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

# Maximum pages to fetch when paginating GitHub API results.
MAX_GITHUB_PAGES = 5


class MacroscopeAnalyzer:
    """Identify the causal PR for an incident using Macroscope + LLM correlation."""

    def __init__(
        self,
        github_repo: str | None = None,
        github_token: str | None = None,
    ):
        self.repo = github_repo or GITHUB_REPO or "pager0/infra"
        self.github_token = github_token or GITHUB_TOKEN or None
        self._configured = bool(self.repo and self.github_token)

    def _gh_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    def _gh_get_paginated(
        self, url: str, params: dict[str, Any] | None = None, max_pages: int = MAX_GITHUB_PAGES
    ) -> list[dict[str, Any]]:
        """Fetch paginated results from the GitHub API with rate-limit handling.

        Args:
            url: Full GitHub API URL.
            params: Query parameters for the first request.
            max_pages: Maximum number of pages to fetch.

        Returns:
            Aggregated list of JSON objects across all pages.
        """
        results: list[dict[str, Any]] = []
        headers = self._gh_headers()
        current_url: str | None = url
        current_params = params
        page = 0

        while current_url and page < max_pages:
            response = requests.get(
                current_url, headers=headers, params=current_params, timeout=15
            )

            # Handle rate limiting with exponential backoff
            if response.status_code == 403 and "rate limit" in response.text.lower():
                reset_at = int(response.headers.get("X-RateLimit-Reset", 0))
                wait = max(reset_at - int(time.time()), 1)
                wait = min(wait, 60)  # Cap wait at 60s
                logger.warning("GitHub rate limited. Waiting %ds.", wait)
                time.sleep(wait)
                continue

            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                results.extend(data)
            else:
                results.append(data)

            # Follow GitHub pagination via Link header
            current_params = None  # params are baked into the next URL
            link_header = response.headers.get("Link", "")
            current_url = None
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    current_url = part.split(";")[0].strip().strip("<>")
                    break
            page += 1

        return results

    def get_recent_prs(self, hours: int = 24) -> list[dict[str, Any]]:
        """Fetch recently merged PRs from the GitHub API.

        Args:
            hours: Look-back window in hours. Defaults to 24.

        Returns:
            List of PR dicts with ``number``, ``title``, ``merged_at``,
            ``user``, ``html_url``.
        """
        if not self._configured:
            return self._mock_recent_prs()

        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        url = f"{GITHUB_API}/repos/{self.repo}/pulls"
        params: dict[str, Any] = {
            "state": "closed",
            "sort": "updated",
            "direction": "desc",
            "per_page": 30,
        }

        try:
            all_prs = self._gh_get_paginated(url, params=params, max_pages=3)
            prs = []
            for pr in all_prs:
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

        Macroscope posts as ``macroscope-app[bot]`` via its GitHub App
        (MacroscopeApp). This method collects both:
          1. PR review comments (inline code comments) from the bot
          2. Issue comments (top-level PR discussion) from the bot

        The GitHub App name is "MacroscopeApp" (github.com/apps/macroscopeapp).
        On GitHub, app-authored comments appear under the login
        ``macroscope-app[bot]`` with ``type: "Bot"``.

        Args:
            pr_number: The pull request number.

        Returns:
            List of review comment dicts with id, author, body, path,
            severity, and created_at.
        """
        if not self._configured:
            return self._mock_macroscope_reviews(pr_number)

        reviews: list[dict[str, Any]] = []

        # 1. Fetch inline review comments (code-level)
        #    GET /repos/{owner}/{repo}/pulls/{pull_number}/comments
        review_comments_url = (
            f"{GITHUB_API}/repos/{self.repo}/pulls/{pr_number}/comments"
        )
        try:
            all_review_comments = self._gh_get_paginated(
                review_comments_url, params={"per_page": 100}
            )
            for comment in all_review_comments:
                author = comment.get("user", {}).get("login", "")
                if author == MACROSCOPE_BOT_LOGIN:
                    reviews.append(self._parse_macroscope_comment(comment, kind="inline"))
        except requests.RequestException as exc:
            logger.error(
                "Failed to fetch review comments for PR #%s: %s", pr_number, exc
            )

        # 2. Fetch issue comments (top-level PR discussion)
        #    GET /repos/{owner}/{repo}/issues/{issue_number}/comments
        issue_comments_url = (
            f"{GITHUB_API}/repos/{self.repo}/issues/{pr_number}/comments"
        )
        try:
            all_issue_comments = self._gh_get_paginated(
                issue_comments_url, params={"per_page": 100}
            )
            for comment in all_issue_comments:
                author = comment.get("user", {}).get("login", "")
                if author == MACROSCOPE_BOT_LOGIN:
                    reviews.append(self._parse_macroscope_comment(comment, kind="discussion"))
        except requests.RequestException as exc:
            logger.error(
                "Failed to fetch issue comments for PR #%s: %s", pr_number, exc
            )

        return reviews

    def get_macroscope_check_runs(self, pr_number: int) -> list[dict[str, Any]]:
        """Fetch Macroscope check-run results for a PR.

        Macroscope creates check runs named:
          - "Macroscope - Correctness Check"
          - "Macroscope - Custom Rules Check"

        A NEUTRAL conclusion means issues were found; SUCCESS means clean.

        Args:
            pr_number: The pull request number.

        Returns:
            List of check-run dicts with name, conclusion, and annotations.
        """
        if not self._configured:
            return self._mock_check_runs(pr_number)

        # First get the PR's head SHA
        pr_url = f"{GITHUB_API}/repos/{self.repo}/pulls/{pr_number}"
        try:
            pr_resp = requests.get(pr_url, headers=self._gh_headers(), timeout=15)
            pr_resp.raise_for_status()
            head_sha = pr_resp.json()["head"]["sha"]
        except (requests.RequestException, KeyError) as exc:
            logger.error("Failed to get head SHA for PR #%s: %s", pr_number, exc)
            return self._mock_check_runs(pr_number)

        # Fetch check runs for that commit
        checks_url = f"{GITHUB_API}/repos/{self.repo}/commits/{head_sha}/check-runs"
        try:
            resp = requests.get(checks_url, headers=self._gh_headers(), timeout=15)
            resp.raise_for_status()
            check_runs = []
            for cr in resp.json().get("check_runs", []):
                if cr.get("name") in MACROSCOPE_CHECK_NAMES:
                    # Fetch annotations for this check run
                    annotations = []
                    ann_url = f"{GITHUB_API}/repos/{self.repo}/check-runs/{cr['id']}/annotations"
                    try:
                        annotations = self._gh_get_paginated(ann_url, params={"per_page": 100})
                    except requests.RequestException:
                        logger.warning("Could not fetch annotations for check run %s", cr["id"])

                    check_runs.append({
                        "name": cr["name"],
                        "conclusion": cr.get("conclusion"),  # "success", "neutral", "failure"
                        "status": cr.get("status"),
                        "output_title": cr.get("output", {}).get("title", ""),
                        "output_summary": cr.get("output", {}).get("summary", ""),
                        "annotations": [
                            {
                                "path": a.get("path", ""),
                                "message": a.get("message", ""),
                                "annotation_level": a.get("annotation_level", ""),
                                "start_line": a.get("start_line"),
                                "end_line": a.get("end_line"),
                            }
                            for a in annotations
                        ],
                    })
            return check_runs
        except requests.RequestException as exc:
            logger.error("Failed to fetch check runs for PR #%s: %s", pr_number, exc)
            return self._mock_check_runs(pr_number)

    @staticmethod
    def _parse_macroscope_comment(
        comment: dict[str, Any], kind: str = "inline"
    ) -> dict[str, Any]:
        """Parse a GitHub comment from Macroscope into a structured dict.

        Macroscope comments include severity levels (CRITICAL, HIGH, MEDIUM, LOW)
        and may use GitHub suggestion blocks, unified diffs, or text explanations.
        """
        body = comment.get("body", "")

        # Attempt to extract severity from the comment body
        severity = "UNKNOWN"
        for level in MACROSCOPE_SEVERITIES:
            if level in body.upper():
                severity = level
                break

        return {
            "id": comment["id"],
            "author": comment.get("user", {}).get("login", MACROSCOPE_BOT_LOGIN),
            "body": body,
            "path": comment.get("path", ""),
            "severity": severity,
            "kind": kind,  # "inline" for code comments, "discussion" for PR-level
            "created_at": comment.get("created_at", ""),
            "html_url": comment.get("html_url", ""),
        }

    def correlate_pr_with_incident(
        self, pr_summaries: list[dict[str, Any]], incident: dict[str, Any]
    ) -> str:
        """Format a prompt for LLM-based correlation between PRs and an incident.

        Includes Macroscope review comments, check-run results, and severity
        levels to help the LLM make an informed root-cause determination.

        Args:
            pr_summaries: List of PR dicts (from get_recent_prs + reviews + check runs).
            incident: Dict describing the incident.

        Returns:
            Formatted prompt string suitable for an LLM call.
        """
        pr_text = ""
        for pr in pr_summaries:
            # Format Macroscope inline/discussion reviews
            reviews_text = ""
            for review in pr.get("macroscope_reviews", []):
                severity = review.get("severity", "UNKNOWN")
                path = review.get("path", "")
                body_preview = review.get("body", "No comment.")[:300]
                kind = review.get("kind", "inline")
                reviews_text += (
                    f"    - [{severity}] ({kind}) {path}: {body_preview}\n"
                )

            # Format Macroscope check-run results
            checks_text = ""
            for cr in pr.get("macroscope_check_runs", []):
                conclusion = cr.get("conclusion", "unknown")
                checks_text += f"    - {cr['name']}: {conclusion}\n"
                for ann in cr.get("annotations", []):
                    checks_text += (
                        f"      * {ann.get('path', '')}:{ann.get('start_line', '?')} "
                        f"[{ann.get('annotation_level', '')}] {ann.get('message', '')[:200]}\n"
                    )

            pr_text += (
                f"  PR #{pr['number']}: {pr['title']} (by {pr.get('user', 'unknown')}, "
                f"merged {pr.get('merged_at', 'recently')})\n"
                f"    Macroscope Reviews:\n{reviews_text or '    - None\n'}"
                f"    Macroscope Check Runs:\n{checks_text or '    - None\n'}\n"
            )

        prompt = f"""You are an SRE incident analysis agent. Given the following incident and
recently merged pull requests (with Macroscope code-review comments and check-run results),
identify which PR most likely caused the incident. Explain your reasoning.

Macroscope severity levels: CRITICAL (data loss/security breach), HIGH (production crashes),
MEDIUM (broken functionality), LOW (cosmetic/edge-case).

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
3. Brief explanation linking the PR changes and Macroscope findings to the incident symptoms
"""
        return prompt

    def identify_causal_pr(self, incident: dict[str, Any]) -> dict[str, Any]:
        """Run the full root-cause analysis pipeline.

        1. Fetch recent PRs.
        2. Fetch Macroscope reviews (inline + discussion comments) for each.
        3. Fetch Macroscope check-run results for each.
        4. Correlate with the incident via LLM (or return mock analysis).

        Args:
            incident: Dict with incident details.

        Returns:
            Dict with ``pr_number``, ``pr_title``, ``confidence``,
            ``explanation``, ``all_prs``.
        """
        prs = self.get_recent_prs()

        # Enrich PRs with Macroscope reviews and check runs
        for pr in prs:
            pr["macroscope_reviews"] = self.get_macroscope_reviews(pr["number"])
            pr["macroscope_check_runs"] = self.get_macroscope_check_runs(pr["number"])

        # Build the correlation prompt
        prompt = self.correlate_pr_with_incident(prs, incident)

        # Attempt LLM call via TrueFoundry gateway
        if TRUEFOUNDRY_API_KEY and TRUEFOUNDRY_ENDPOINT:
            try:
                from openai import OpenAI
                from sentinelcall.config import TRUEFOUNDRY_PROVIDER_NAME

                base_url = TRUEFOUNDRY_ENDPOINT.rstrip("/") + "/proxy"
                provider = TRUEFOUNDRY_PROVIDER_NAME or "anthropic"
                client = OpenAI(
                    api_key=TRUEFOUNDRY_API_KEY,
                    base_url=base_url,
                    default_headers={
                        "x-tfy-provider-name": provider,
                    },
                )
                response = client.chat.completions.create(
                    model="claude-sonnet-4-6",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=500,
                )
                llm_output = response.choices[0].message.content or ""
                logger.info("LLM correlation complete for incident %s", incident.get("incident_id"))

                # Parse the LLM output to extract the identified PR
                identified_pr = self._extract_pr_from_llm_output(llm_output, prs)

                return {
                    "pr_number": identified_pr.get("number") if identified_pr else (prs[0]["number"] if prs else None),
                    "pr_title": identified_pr.get("title") if identified_pr else (prs[0]["title"] if prs else "Unknown"),
                    "confidence": "high",
                    "explanation": llm_output,
                    "all_prs": prs,
                    "prompt_used": prompt,
                }
            except Exception as exc:
                logger.error("LLM correlation failed: %s. Using mock analysis.", exc)

        return self._mock_analysis(prs, incident)

    @staticmethod
    def _extract_pr_from_llm_output(
        llm_output: str, prs: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Try to extract the PR number referenced in LLM output."""
        import re

        # Look for patterns like "PR #47" or "PR 47" or "#47"
        match = re.search(r"#(\d+)", llm_output)
        if match:
            pr_num = int(match.group(1))
            for pr in prs:
                if pr["number"] == pr_num:
                    return pr
        return None

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
        """Return realistic mock Macroscope reviews.

        Simulates the real Macroscope format: comments authored by
        macroscope-app[bot] with severity levels and inline code references.
        """
        reviews_by_pr: dict[int, list[dict[str, Any]]] = {
            47: [
                {
                    "id": 9001,
                    "author": MACROSCOPE_BOT_LOGIN,
                    "body": (
                        "**HIGH**: This PR reduces `max_pool_size` from 100 to 20 in "
                        "`config/database.yml`. Under current traffic patterns (~850 RPS), "
                        "this will likely cause connection starvation during peak hours. "
                        "Consider keeping pool size >= 50 or adding a circuit breaker.\n\n"
                        "```suggestion\n"
                        "max_pool_size: 50\n"
                        "```"
                    ),
                    "path": "config/database.yml",
                    "severity": "HIGH",
                    "kind": "inline",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "html_url": f"https://github.com/{self.repo}/pull/47#discussion_r9001",
                },
            ],
            46: [
                {
                    "id": 9002,
                    "author": MACROSCOPE_BOT_LOGIN,
                    "body": (
                        "**LOW**: Retry logic follows exponential backoff best practices. "
                        "No correctness issues found."
                    ),
                    "path": "services/payment/retry.py",
                    "severity": "LOW",
                    "kind": "inline",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "html_url": f"https://github.com/{self.repo}/pull/46#discussion_r9002",
                },
            ],
            45: [],
        }
        return reviews_by_pr.get(pr_number, [])

    def _mock_check_runs(self, pr_number: int) -> list[dict[str, Any]]:
        """Return realistic mock Macroscope check-run results.

        Simulates the check runs Macroscope creates:
        - "Macroscope - Correctness Check" with NEUTRAL when issues found
        - "Macroscope - Custom Rules Check"
        """
        check_runs_by_pr: dict[int, list[dict[str, Any]]] = {
            47: [
                {
                    "name": "Macroscope - Correctness Check",
                    "conclusion": "neutral",  # Issues found
                    "status": "completed",
                    "output_title": "1 issue found",
                    "output_summary": "Macroscope identified 1 high-severity issue.",
                    "annotations": [
                        {
                            "path": "config/database.yml",
                            "message": (
                                "Connection pool size reduced from 100 to 20. "
                                "This may cause connection starvation under current load."
                            ),
                            "annotation_level": "warning",
                            "start_line": 12,
                            "end_line": 12,
                        },
                    ],
                },
                {
                    "name": "Macroscope - Custom Rules Check",
                    "conclusion": "success",
                    "status": "completed",
                    "output_title": "All checks passed",
                    "output_summary": "No custom rule violations found.",
                    "annotations": [],
                },
            ],
            46: [
                {
                    "name": "Macroscope - Correctness Check",
                    "conclusion": "success",
                    "status": "completed",
                    "output_title": "No issues found",
                    "output_summary": "Macroscope found no correctness issues.",
                    "annotations": [],
                },
            ],
            45: [],
        }
        return check_runs_by_pr.get(pr_number, [])

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
                "Macroscope's Correctness Check flagged this with a NEUTRAL conclusion "
                "and a HIGH-severity inline review warning that current traffic (~850 RPS) "
                "would cause connection starvation. The incident symptoms — elevated "
                "p99 latency, database timeout errors, and cascading 503s on "
                f"{incident.get('service', 'api-gateway')} — are consistent with "
                "connection pool exhaustion. Timeline correlation: PR merged 2 hours "
                "before incident onset."
            ),
            "all_prs": prs,
            "mock": True,
        }
