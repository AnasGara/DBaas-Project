import json

from botocore.exceptions import ClientError

from router import ingest, worker


def test_ambiguous_success_uses_same_key_and_receiver_mutates_once(
    cloud, request_event, monkeypatch
):
    ingest.handler(request_event, None)
    event = cloud["events"].scan()["Items"][0]
    receiver_keys = set()
    requests = []

    def receiver(item):
        requests.append(item["pk"])
        receiver_keys.add(item["pk"])

    monkeypatch.setattr(worker.transport, "send", receiver)
    events = worker.table("EVENTS_TABLE")
    update = events.update_item
    failed = False

    def fail_first_completion(**kwargs):
        nonlocal failed
        if "delivered_at" in kwargs["UpdateExpression"] and not failed:
            failed = True
            raise ClientError(
                {"Error": {"Code": "InternalServerError", "Message": "unavailable"}}, "UpdateItem"
            )
        return update(**kwargs)

    monkeypatch.setattr(events, "update_item", fail_first_completion)
    batch = {"Records": [{"messageId": "1", "body": json.dumps({"event_key": event["pk"]})}]}
    assert worker.handler(batch, None)["batchItemFailures"]
    assert worker.handler(batch, None) == {"batchItemFailures": []}
    assert len(requests) == 2
    assert len(receiver_keys) == 1


def test_numeric_schema_constraints_survive_dynamodb_decimal_types(cloud, request_event):
    cloud["routes"].put_item(
        Item={
            **cloud["route"],
            "schema": {"type": "object", "properties": {"id": {"type": "string", "minLength": 2}}},
        }
    )
    assert ingest.handler(request_event, None)["statusCode"] == 202


def test_transaction_rolls_back_event_when_outbox_condition_conflicts(cloud, request_event):
    from router.validation import identity, normalize

    key = identity("acme", normalize(json.loads(request_event["body"])))
    cloud["outbox"].put_item(Item={"pk": key, "shard": "0", "due_at": 0, "created_at": 0})
    assert ingest.handler(request_event, None)["statusCode"] == 503
    assert "Item" not in cloud["events"].get_item(Key={"pk": key})
