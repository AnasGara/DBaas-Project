import hashlib
import hmac
import json
import os

from router.config import client
from router.telemetry import log
from router.validation import TENANT_PATTERN


def handler(event, context):
    token = event.get("authorizationToken", "")
    if not isinstance(token, str) or not token.startswith("Bearer ") or len(token) > 1024:
        raise Exception("Unauthorized")
    digest = hashlib.sha256(token[7:].encode()).hexdigest()
    try:
        credentials = json.loads(
            client("secretsmanager").get_secret_value(
                SecretId=os.environ["AUTH_SECRET_ARN"], VersionStage="AWSCURRENT"
            )["SecretString"]
        )
        for credential in credentials.get("clients", []):
            if not hmac.compare_digest(digest, credential.get("token_sha256", "")):
                continue
            tenant = credential["tenant_id"]
            providers = credential["providers"]
            if not TENANT_PATTERN.fullmatch(tenant) or credential.get("enabled") is not True:
                break
            if (
                not isinstance(providers, list)
                or not providers
                or any(p not in ("vapi", "workflow") for p in providers)
            ):
                break
            return {
                "principalId": tenant,
                "policyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Action": "execute-api:Invoke",
                            "Effect": "Allow",
                            "Resource": event["methodArn"],
                        }
                    ],
                },
                "usageIdentifierKey": credential["api_key"],
                "context": {"tenant_id": tenant, "providers": ",".join(providers)},
            }
    except Exception as exc:
        log("authorization_failed", error_type=type(exc).__name__)
    raise Exception("Unauthorized")
