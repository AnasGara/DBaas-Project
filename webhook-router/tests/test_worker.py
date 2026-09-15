import json
import time

from router import ingest, worker


def accepted(cloud, request_event):
    ingest.handler(request_event, None)
    return cloud["events"].scan()["Items"][0]


def test_delivery_failure_releases_lease_and_retries(cloud, request_event, monkeypatch):
    item = accepted(cloud, request_event)
    calls = []

    def fail(item):
        calls.append(item["pk"])
        raise TimeoutError("do not log a sensitive remote URL")

    monkeypatch.setattr(worker.transport, "send", fail)
    event = {"Records": [{"messageId": "1", "body": json.dumps({"event_key": item["pk"]})}]}
    assert worker.handler(event, None) == {"batchItemFailures": [{"itemIdentifier": "1"}]}
    saved = cloud["events"].get_item(Key={"pk": item["pk"]})["Item"]
    assert saved["status"] == "RETRY" and "lease_owner" not in saved
    monkeypatch.setattr(worker.transport, "send", lambda item: calls.append(item["pk"]))
    assert worker.handler(event, None) == {"batchItemFailures": []}
    assert calls == [item["pk"], item["pk"]]


def test_active_lease_is_not_acknowledged(cloud, request_event, monkeypatch):
    item = accepted(cloud, request_event)
    cloud["events"].update_item(
        Key={"pk": item["pk"]},
        UpdateExpression="SET lease_until=:until, lease_owner=:owner",
        ExpressionAttributeValues={":until": int(time.time()) + 60, ":owner": "original-worker"},
    )

    def must_not_send(item):
        raise AssertionError("leased event was sent")

    monkeypatch.setattr(worker.transport, "send", must_not_send)
    event = {"Records": [{"messageId": "locked", "body": json.dumps({"event_key": item["pk"]})}]}
    assert worker.handler(event, None)["batchItemFailures"] == [{"itemIdentifier": "locked"}]


def test_expired_lease_is_recoverable(cloud, request_event, monkeypatch):
    item = accepted(cloud, request_event)
    cloud["events"].update_item(
        Key={"pk": item["pk"]},
        UpdateExpression="SET lease_until=:until",
        ExpressionAttributeValues={":until": int(time.time()) - 1},
    )
    delivered = []
    monkeypatch.setattr(worker.transport, "send", lambda item: delivered.append(item["pk"]))
    worker.process(item["pk"])
    assert delivered == [item["pk"]]


def test_partial_failure_does_not_retry_successful_record(cloud, request_event, monkeypatch):
    item = accepted(cloud, request_event)
    monkeypatch.setattr(worker.transport, "send", lambda item: None)
    result = worker.handler(
        {
            "Records": [
                {"messageId": "good", "body": json.dumps({"event_key": item["pk"]})},
                {"messageId": "bad", "body": "not-json"},
            ]
        },
        None,
    )
    assert result == {"batchItemFailures": [{"itemIdentifier": "bad"}]}
