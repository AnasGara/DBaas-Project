import json

import boto3
import pytest
from moto import mock_aws

from router.config import reset_clients


@pytest.fixture(autouse=True)
def isolated_aws(monkeypatch):
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "eu-west-3",
        "AWS_EC2_METADATA_DISABLED": "true",
        "EVENTS_TABLE": "events",
        "OUTBOX_TABLE": "outbox",
        "ROUTES_TABLE": "routes",
        "ENVIRONMENT": "test",
        "SERVICE": "test",
        "ALLOWED_DESTINATION_HOSTS": "hooks.example.com",
        "ALLOWED_PRIVATE_CIDRS": "",
        "DESTINATION_SECRET_PREFIX_ARN": "arn:aws:secretsmanager:eu-west-3:123456789012:secret:webhook-router/destinations/",
    }.items():
        monkeypatch.setenv(name, value)
    reset_clients()
    with mock_aws():
        yield
    reset_clients()


@pytest.fixture
def cloud(monkeypatch):
    db = boto3.resource("dynamodb")
    events = db.create_table(
        TableName="events",
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
    )
    outbox = db.create_table(
        TableName="outbox",
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "shard", "AttributeType": "S"},
            {"AttributeName": "due_at", "AttributeType": "N"},
        ],
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "due",
                "KeySchema": [
                    {"AttributeName": "shard", "KeyType": "HASH"},
                    {"AttributeName": "due_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )
    routes = db.create_table(
        TableName="routes",
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "tenant_id", "AttributeType": "S"},
            {"AttributeName": "event_type", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "tenant_id", "KeyType": "HASH"},
            {"AttributeName": "event_type", "KeyType": "RANGE"},
        ],
    )
    route = {
        "tenant_id": "acme",
        "event_type": "workflow.trigger",
        "enabled": True,
        "version": "1",
        "endpoint": "https://hooks.example.com/receive",
        "schema": {"type": "object"},
    }
    routes.put_item(Item=route)
    queue = boto3.client("sqs").create_queue(QueueName="delivery")["QueueUrl"]
    monkeypatch.setenv("DELIVERY_QUEUE_URL", queue)
    return {"events": events, "outbox": outbox, "routes": routes, "route": route, "queue": queue}


@pytest.fixture
def request_event():
    return {
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {
                "id": "event-001",
                "type": "workflow.trigger",
                "data": {"workflow_id": "onboard", "customer_id": "customer-123"},
            }
        ),
        "requestContext": {
            "requestId": "request-1",
            "authorizer": {"tenant_id": "acme", "providers": "workflow,vapi"},
        },
    }
