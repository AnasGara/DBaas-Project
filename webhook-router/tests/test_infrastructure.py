import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def resources():
    return yaml.safe_load((ROOT / "template.yaml").read_text())["Resources"]


def test_durable_tables_have_retention_backups_and_on_demand_capacity():
    for name in ("EventsTable", "RoutesTable", "OutboxTable"):
        resource = resources()[name]
        assert resource["DeletionPolicy"] == "Retain"
        assert resource["Properties"]["BillingMode"] == "PAY_PER_REQUEST"
        assert resource["Properties"]["PointInTimeRecoverySpecification"][
            "PointInTimeRecoveryEnabled"
        ]
    assert "TimeToLiveSpecification" not in resources()["OutboxTable"]["Properties"]


def test_delivery_visibility_exceeds_timeout_and_lease():
    template = yaml.safe_load((ROOT / "template.yaml").read_text())
    queue = template["Resources"]["DeliveryQueue"]["Properties"]
    assert queue["VisibilityTimeout"] >= 6 * template["Globals"]["Function"]["Timeout"]
    event = template["Resources"]["WorkerFunction"]["Properties"]["Events"]["Deliver"]["Properties"]
    assert event["BatchSize"] == 1
    assert event["FunctionResponseTypes"] == ["ReportBatchItemFailures"]


def test_roles_are_explicit_and_do_not_use_generated_basic_execution_policies():
    for name in ("Ingest", "Authorizer", "Dispatch", "Worker"):
        props = resources()[name + "Function"]["Properties"]
        assert "Policies" not in props
        assert props["Role"] == {"Fn::GetAtt": [name + "Role", "Arn"]}
        statements = resources()[name + "Role"]["Properties"]["Policies"][0]["PolicyDocument"][
            "Statement"
        ]
        assert not any(s.get("Action") == "*" for s in statements)


def test_authentication_usage_limits_and_monitoring_are_present():
    api = resources()["WebhookApi"]["Properties"]
    assert api["ApiKeySourceType"] == "AUTHORIZER"
    assert api["Auth"]["ApiKeyRequired"] is True
    assert api["Auth"]["Authorizers"]["TenantAuthorizer"]["Identity"]["ReauthorizeEvery"] == 0
    assert resources()["LambdaErrorRateAlarm"]["Properties"]["Threshold"] == 1
    assert "DeliveryFailureRateAlarm" in resources()
    assert "StreamFailureAlarm" in resources()
    dashboard = resources()["Dashboard"]["Properties"]["DashboardBody"]["Fn::Sub"]
    assert len(json.loads(dashboard)["widgets"]) == 6
