"""Firebase Cloud Messaging (HTTP v1), no SDK: a signed JWT buys an access token, then one POST
per phone. Without a credential (FIREBASE_CREDENTIALS_FILE unset) nothing is sent; the bell
still works. Data-only messages, so the app always gets them, shows the notice itself and syncs."""
import json
import logging
import os
import time
from functools import lru_cache

import jwt
import requests
from django.conf import settings
from django.core.cache import cache

log = logging.getLogger(__name__)
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
GONE = ("UNREGISTERED", "INVALID_ARGUMENT")


@lru_cache(maxsize=1)
def credential() -> dict | None:
    path = settings.FCM_CREDENTIALS
    if not path:
        return None
    with open(os.path.expanduser(path)) as f:
        return json.load(f)


def _access_token(cred: dict) -> str:
    token = cache.get("fcm-access-token")
    if token:
        return token
    now = int(time.time())
    assertion = jwt.encode({"iss": cred["client_email"], "scope": SCOPE, "aud": cred["token_uri"],
                            "iat": now, "exp": now + 3600}, cred["private_key"], algorithm="RS256")
    r = requests.post(cred["token_uri"], timeout=10, data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
    r.raise_for_status()
    token = r.json()["access_token"]
    cache.set("fcm-access-token", token, 50 * 60)
    return token


def send(token: str, data: dict[str, str]) -> bool:
    """Push to one phone. False means the phone's token is dead and should be forgotten."""
    cred = credential()
    if cred is None:
        return True
    try:
        r = requests.post(
            f"https://fcm.googleapis.com/v1/projects/{cred['project_id']}/messages:send",
            timeout=10, headers={"Authorization": f"Bearer {_access_token(cred)}"},
            json={"message": {"token": token, "data": data, "android": {"priority": "HIGH"}}})
    except requests.RequestException as e:      # one slow call never stops the rest (F-140)
        log.warning("FCM push failed: %s", type(e).__name__)
        return True
    if r.status_code in (400, 404) and any(g in r.text for g in GONE):
        return False
    if r.status_code >= 400:
        log.warning("FCM push failed: %s %s", r.status_code, r.text[:200])
    return True
