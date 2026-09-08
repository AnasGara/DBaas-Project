import hashlib
import json

import boto3
import pytest

from router.authorizer import handler


def setup_auth(monkeypatch, enabled=True):
    credentials = {
        "clients": [
            {
                "tenant_id": "acme",
                "token_sha256": hashlib.sha256(b"test-bearer-token").hexdigest(),
                "providers": ["vapi"],
                "api_key": "usage-key",
                "enabled": enabled,
            }
        ]
    }
    arn = boto3.client("secretsmanager").create_secret(
        Name="auth", SecretString=json.dumps(credentials)
    )["ARN"]
    monkeypatch.setenv("AUTH_SECRET_ARN", arn)
    return arn


def test_identity_and_usage_key_come_from_secret_not_headers(monkeypatch):
    setup_auth(monkeypatch)
    result = handler(
        {
            "authorizationToken": "Bearer test-bearer-token",
            "methodArn": "arn:aws:execute-api:eu-west-3:123:api/prod/POST/webhooks",
        },
        None,
    )
    assert result["principalId"] == "acme"
    assert result["usageIdentifierKey"] == "usage-key"
    assert result["context"] == {"tenant_id": "acme", "providers": "vapi"}


@pytest.mark.parametrize("token", ["", "Basic bad", "Bearer incorrect"])
def test_authentication_rejects_invalid_tokens(monkeypatch, token):
    setup_auth(monkeypatch)
    with pytest.raises(Exception, match="Unauthorized"):
        handler({"authorizationToken": token, "methodArn": "test"}, None)


def test_revocation_has_no_process_cache(monkeypatch):
    arn = setup_auth(monkeypatch)
    event = {"authorizationToken": "Bearer test-bearer-token", "methodArn": "test"}
    assert handler(event, None)["principalId"] == "acme"
    boto3.client("secretsmanager").put_secret_value(SecretId=arn, SecretString='{"clients":[]}')
    with pytest.raises(Exception, match="Unauthorized"):
        handler(event, None)
