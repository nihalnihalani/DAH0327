"""Auth0 CIBA (Client Initiated Backchannel Authentication).

When the on-call engineer verbally approves remediation on the Bland AI call,
this module initiates a CIBA flow — Auth0 pushes an auth request to the
engineer's registered device. Their tap/approval mints a token that
authorizes the agent to execute remediation actions.

This is the creative/non-obvious Auth0 usage: the phone call IS the auth
channel, not a browser redirect.
"""
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

AUTH0_DOMAIN = os.environ['AUTH0_DOMAIN']
AUTH0_CLIENT_ID = os.environ['AUTH0_CLIENT_ID']
AUTH0_CLIENT_SECRET = os.environ['AUTH0_CLIENT_SECRET']

# Scope granted when engineer approves remediation
REMEDIATION_SCOPE = 'openid profile email remediate:incident'

# How long to poll for engineer approval (seconds)
CIBA_POLL_TIMEOUT = 120
CIBA_POLL_INTERVAL = 5


def initiate_ciba(engineer_login_hint: str, incident_id: str, binding_message: str = None) -> dict:
    """Start a CIBA auth request for the engineer.

    Auth0 pushes a notification to the engineer's device asking them to
    approve the remediation action.

    Args:
        engineer_login_hint: Engineer's email or phone registered with Auth0.
        incident_id: Used in the binding message so the engineer sees context.
        binding_message: Short human-readable string shown on the push notification.

    Returns:
        Dict with 'auth_req_id' and 'expires_in'.
    """
    if binding_message is None:
        binding_message = f'Approve SentinelCall remediation for {incident_id}'

    resp = requests.post(
        f'https://{AUTH0_DOMAIN}/bc-authorize',
        json={
            'client_id': AUTH0_CLIENT_ID,
            'client_secret': AUTH0_CLIENT_SECRET,
            'login_hint': engineer_login_hint,
            'scope': REMEDIATION_SCOPE,
            'binding_message': binding_message,
            'request_expiry': CIBA_POLL_TIMEOUT,
        },
    )
    resp.raise_for_status()
    return resp.json()  # contains auth_req_id, expires_in, interval


def poll_for_token(auth_req_id: str, interval: int = CIBA_POLL_INTERVAL) -> dict | None:
    """Poll the token endpoint until the engineer approves or the request expires.

    Returns the token response dict on approval, or None on timeout/denial.
    """
    deadline = time.time() + CIBA_POLL_TIMEOUT
    while time.time() < deadline:
        resp = requests.post(
            f'https://{AUTH0_DOMAIN}/oauth/token',
            json={
                'grant_type': 'urn:openid:params:grant-type:ciba',
                'client_id': AUTH0_CLIENT_ID,
                'client_secret': AUTH0_CLIENT_SECRET,
                'auth_req_id': auth_req_id,
            },
        )
        data = resp.json()

        if resp.status_code == 200:
            return data  # approved — contains access_token, id_token

        error = data.get('error', '')
        if error == 'authorization_pending':
            time.sleep(interval)
            continue
        if error == 'slow_down':
            interval = min(interval + 5, 30)
            time.sleep(interval)
            continue
        if error in ('access_denied', 'expired_token'):
            return None  # engineer denied or timed out
        # unexpected error — surface it
        resp.raise_for_status()

    return None  # timed out


def request_remediation_approval(
    engineer_login_hint: str,
    incident_id: str,
) -> tuple[bool, 'str | None']:
    """Full CIBA flow: initiate + poll.

    Called by the agent after Bland AI transcript indicates verbal approval.
    The engineer still taps their phone to cryptographically confirm.

    Returns:
        (approved: bool, access_token: str | None)
    """
    try:
        ciba = initiate_ciba(engineer_login_hint, incident_id)
    except requests.HTTPError as e:
        print(f'[CIBA] Failed to initiate: {e}')
        return False, None

    auth_req_id = ciba['auth_req_id']
    poll_interval = ciba.get('interval', CIBA_POLL_INTERVAL)

    print(f'[CIBA] Waiting for engineer approval (auth_req_id={auth_req_id[:12]}…)')
    token_response = poll_for_token(auth_req_id, interval=poll_interval)

    if token_response:
        print('[CIBA] Engineer approved — remediation authorized.')
        return True, token_response['access_token']
    else:
        print('[CIBA] Engineer denied or timed out.')
        return False, None
