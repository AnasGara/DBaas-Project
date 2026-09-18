import json

import boto3
from boto3.dynamodb.types import TypeSerializer

from router import dispatch, ingest, worker


def test_full_pipeline_and_duplicate_queue_delivery(cloud, request_event, monkeypatch):
    ingest.handler(request_event, None)
    assert dispatch.handler({}, None) == {"reconciled": True}
    assert cloud["outbox"].scan()["Count"] == 0
    message = boto3.client("sqs").receive_message(QueueUrl=cloud["queue"])["Messages"][0]
    deliveries = []
    monkeypatch.setattr(worker.transport, "send", lambda item: deliveries.append(item["pk"]))
    event = {"Records": [{"messageId": "1", "body": message["Body"]}]}
    assert worker.handler(event, None) == {"batchItemFailures": []}
    assert worker.handler(event, None) == {"batchItemFailures": []}
    assert len(deliveries) == 1
    assert cloud["events"].get_item(Key={"pk": deliveries[0]})["Item"]["status"] == "DELIVERED"


def test_publish_failure_preserves_outbox_for_reconciliation(cloud, request_event, monkeypatch):
    ingest.handler(request_event, None)
    serializer = TypeSerializer()
    item = cloud["outbox"].scan()["Items"][0]
    record = {
        "eventName": "INSERT",
        "dynamodb": {
            "SequenceNumber": "42",
            "NewImage": {k: serializer.serialize(v) for k, v in item.items()},
        },
    }

    def fail(item):
        raise TimeoutError("queue unavailable")

    monkeypatch.setattr(dispatch, "publish", fail)
    assert dispatch.handler({"Records": [record]}, None) == {
        "batchItemFailures": [{"itemIdentifier": "42"}]
    }
    assert cloud["outbox"].get_item(Key={"pk": item["pk"]})["Item"]


def test_crash_after_enqueue_creates_safe_duplicate(cloud, request_event, monkeypatch):
    ingest.handler(request_event, None)
    item = cloud["outbox"].scan()["Items"][0]
    # Model queue acceptance followed by a process crash before outbox removal.
    boto3.client("sqs").send_message(
        QueueUrl=cloud["queue"], MessageBody=json.dumps({"event_key": item["pk"]})
    )
    dispatch.publish(item)
    messages = boto3.client("sqs").receive_message(QueueUrl=cloud["queue"], MaxNumberOfMessages=10)[
        "Messages"
    ]
    assert len(messages) == 2
