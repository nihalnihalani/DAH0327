"""Auth0 Token Vault — agent fetches upstream OAuth tokens at runtime.

Token Vault is Auth0's mechanism for storing OAuth connections on behalf of
users. The agent calls `get_access_token_for_connection()` to exchange its
Auth0 access token for a token scoped to the upstream provider (GitHub,
Slack, etc.) — it never handles raw secrets.

Creative use: the SentinelCall agent (not a user browser) calls GitHub's API
using the on-call engineer's connected GitHub account, stored in Token Vault.
This lets Macroscope PR analysis run under the engineer's identity without
the agent ever seeing a PAT.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

AUTH0_DOMAIN = os.environ['AUTH0_DOMAIN']
AUTH0_CLIENT_ID = os.environ['AUTH0_CLIENT_ID']
AUTH0_CLIENT_SECRET = os.environ['AUTH0_CLIENT_SECRET']
AUTH0_AUDIENCE = os.environ.get('AUTH0_AUDIENCE', f'https://{AUTH0_DOMAIN}/api/v2/')

# Auth0 Token Vault connections configured in the Auth0 dashboard
CONNECTIONS = {
    'github':  'github',    # engineer's GitHub account → PR/Macroscope analysis
    'slack':   'slack',     # post incident updates to Slack channel
}

_m2m_token_cache: dict = {}


def _get_m2m_token() -> str:
    """Obtain a machine-to-machine access token for the Token Vault API."""
    import time
    cached = _m2m_token_cache.get('token')
    if cached and time.time() < _m2m_token_cache.get('expires_at', 0) - 30:
        return cached

    resp = requests.post(
        f'https://{AUTH0_DOMAIN}/oauth/token',
        json={
            'grant_type': 'client_credentials',
            'client_id': AUTH0_CLIENT_ID,
            'client_secret': AUTH0_CLIENT_SECRET,
            'audience': AUTH0_AUDIENCE,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    _m2m_token_cache['token'] = data['access_token']
    _m2m_token_cache['expires_at'] = time.time() + data.get('expires_in', 3600)
    return data['access_token']


def get_connection_token(connection: str, subject_token: str) -> str:
    """Exchange an Auth0 access token for an upstream provider token via Token Vault.

    This is the core Token Vault pattern: the agent holds an Auth0 token for
    the on-call engineer's session and exchanges it for a scoped GitHub/Slack
    token without ever seeing raw credentials.

    Args:
        connection: Auth0 connection name (e.g. 'github', 'slack')
        subject_token: The Auth0 access token representing the engineer.

    Returns:
        Access token for the upstream provider.
    """
    resp = requests.post(
        f'https://{AUTH0_DOMAIN}/oauth/token',
        json={
            'grant_type': 'urn:ietf:params:oauth:grant-type:token-exchange',
            'client_id': AUTH0_CLIENT_ID,
            'client_secret': AUTH0_CLIENT_SECRET,
            'audience': AUTH0_AUDIENCE,
            'subject_token': subject_token,
            'subject_token_type': 'urn:ietf:params:oauth:token-type:access_token',
            'requested_token_type': 'urn:auth0:params:oauth:token-type:connection',
            'connection': connection,
        },
    )
    resp.raise_for_status()
    return resp.json()['access_token']


def get_github_token(engineer_auth0_token: str) -> str:
    """Get the engineer's GitHub token from Token Vault for PR/Macroscope analysis."""
    return get_connection_token(CONNECTIONS['github'], engineer_auth0_token)


def get_agent_m2m_token() -> str:
    """Expose M2M token for agent-level API calls (not user-delegated)."""
    return _get_m2m_token()
