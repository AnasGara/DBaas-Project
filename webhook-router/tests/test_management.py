import importlib.util
import json
from pathlib import Path

import boto3
import pytest
from botocore.exceptions import ClientError


def load_manage():
    path = Path(__file__).resolve().parents[1] / "scripts" / "manage.py"
    spec = importlib.util.spec_from_file_location("router_manage", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_secret_updates_reject_concurrent_stale_edits():
    manage = load_manage()
    secrets = boto3.client("secretsmanager")
    arn = secrets.create_secret(Name="auth", SecretString='{"clients":[]}')["ARN"]
    current = secrets.get_secret_value(SecretId=arn, VersionStage="AWSCURRENT")
    manage.replace_credentials(secrets, arn, current, {"clients": [{"tenant_id": "first"}]})
    with pytest.raises(ClientError):
        manage.replace_credentials(
            secrets, arn, current, {"clients": [{"tenant_id": "stale-writer"}]}
        )
    assert json.loads(
        secrets.get_secret_value(SecretId=arn, VersionStage="AWSCURRENT")["SecretString"]
    )["clients"] == [{"tenant_id": "first"}]


def test_post_publish_label_cleanup_does_not_revoke_new_credentials(monkeypatch):
    manage = load_manage()
    secrets = boto3.client("secretsmanager")
    arn = secrets.create_secret(Name="auth", SecretString='{"clients":[]}')["ARN"]
    current = secrets.get_secret_value(SecretId=arn, VersionStage="AWSCURRENT")
    update = secrets.update_secret_version_stage

    def cleanup_fails(**kwargs):
        if kwargs["VersionStage"].startswith("pending-"):
            raise RuntimeError("cleanup temporarily unavailable")
        return update(**kwargs)

    monkeypatch.setattr(secrets, "update_secret_version_stage", cleanup_fails)
    manage.replace_credentials(secrets, arn, current, {"clients": [{"tenant_id": "new"}]})
    assert (
        json.loads(
            secrets.get_secret_value(SecretId=arn, VersionStage="AWSCURRENT")["SecretString"]
        )["clients"][0]["tenant_id"]
        == "new"
    )
