"""The FCM access-token request is signed for real (RS256), not mocked: production failed with
"Algorithm 'RS256' could not be found" when `cryptography` was missing (review H-10)."""
from unittest import mock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache

from apps.notify import push


@pytest.fixture
def cred():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return key.public_key(), {"client_email": "push@example.iam.gserviceaccount.com",
                              "private_key": pem, "token_uri": "https://oauth2.example/token",
                              "project_id": "vayu-test"}


def test_access_token_request_carries_a_valid_rs256_assertion(cred):
    public, c = cred
    cache.delete("fcm-access-token")
    with mock.patch.object(push.requests, "post") as post:
        post.return_value.json.return_value = {"access_token": "tok"}
        assert push._access_token(c) == "tok"
    assertion = post.call_args.kwargs["data"]["assertion"]
    claims = jwt.decode(assertion, public, algorithms=["RS256"], audience=c["token_uri"])
    assert claims["iss"] == c["client_email"] and claims["scope"] == push.SCOPE
