"""Macroscope root cause analysis — PR-linked incident diagnosis.

Macroscope is a GitHub App that automatically reviews PRs and posts
plain-language summaries + correctness analysis as GitHub review comments.

SentinelCall queries those GitHub review comments (posted by the Macroscope
bot) to identify which recent PR introduced the regression, then surfaces
the causal PR in the incident report.

Setup: install the Macroscope GitHub App at app.macroscope.com, connect
your GitHub repo. Macroscope will start reviewing new PRs automatically.
"""
import os
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_REPO = os.environ.get('GITHUB_REPO', '')   # e.g. "org/repo"
MACROSCOPE_BOT = 'macroscope[bot]'

GITHUB_API = 'https://api.github.com'


def _gh_headers() -> dict:
    return {
        'Authorization': f'Bearer {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }


def get_recent_merged_prs(hours: int = 6) -> list[dict]:
    """Fetch PRs merged in the last N hours — the blast radius window."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    resp = requests.get(
        f'{GITHUB_API}/repos/{GITHUB_REPO}/pulls',
        headers=_gh_headers(),
        params={'state': 'closed', 'sort': 'updated', 'direction': 'desc', 'per_page': 20},
    )
    resp.raise_for_status()
    prs = resp.json()
    return [
        pr for pr in prs
        if pr.get('merged_at') and pr['merged_at'] > since
    ]


def get_macroscope_reviews(pr_number: int) -> list[dict]:
    """Fetch PR review comments posted by the Macroscope bot."""
    resp = requests.get(
        f'{GITHUB_API}/repos/{GITHUB_REPO}/pulls/{pr_number}/reviews',
        headers=_gh_headers(),
    )
    resp.raise_for_status()
    reviews = resp.json()
    return [r for r in reviews if r.get('user', {}).get('login') == MACROSCOPE_BOT]


def find_causal_pr(service: str, anomaly_keywords: list[str] | None = None) -> dict | None:
    """Identify the most likely causal PR for an incident.

    Checks recent merged PRs for Macroscope reviews that flag correctness
    issues or changes relevant to the affected service.

    Returns a dict with pr_number, pr_url, pr_title, macroscope_summary, or None.
    """
    if anomaly_keywords is None:
        anomaly_keywords = [service.lower(), 'error', 'timeout', 'latency', 'crash', 'null', 'exception']

    recent_prs = get_recent_merged_prs(hours=6)
    if not recent_prs:
        return None

    candidates = []
    for pr in recent_prs:
        macroscope_reviews = get_macroscope_reviews(pr['number'])
        if not macroscope_reviews:
            continue

        # Combine all Macroscope review bodies for this PR
        review_text = ' '.join(r.get('body', '') for r in macroscope_reviews).lower()
        score = sum(1 for kw in anomaly_keywords if kw in review_text)

        if score > 0:
            candidates.append({
                'pr_number': pr['number'],
                'pr_url': pr['html_url'],
                'pr_title': pr['title'],
                'merged_at': pr['merged_at'],
                'macroscope_summary': macroscope_reviews[0].get('body', ''),
                'relevance_score': score,
            })

    if not candidates:
        # Fall back to most recently merged PR if no keyword match
        pr = recent_prs[0]
        macroscope_reviews = get_macroscope_reviews(pr['number'])
        return {
            'pr_number': pr['number'],
            'pr_url': pr['html_url'],
            'pr_title': pr['title'],
            'merged_at': pr['merged_at'],
            'macroscope_summary': macroscope_reviews[0].get('body', '') if macroscope_reviews else '',
            'relevance_score': 0,
        }

    # Return highest-scoring candidate
    return max(candidates, key=lambda c: c['relevance_score'])
