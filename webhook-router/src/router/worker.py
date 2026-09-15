import json
import time
import uuid

from botocore.exceptions import ClientError

from router import transport
from router.config import LEASE_SECONDS, table
from router.telemetry import log, memory_metric, metric


def process(key):
    events = table("EVENTS_TABLE")
    item = events.get_item(Key={"pk": key}, ConsistentRead=True).get("Item")
    if not item:
        # Missing/expired audit records require operator investigation, not silent message loss.
        raise RuntimeError("Event does not exist")
    if item["status"] == "DELIVERED":
        metric("DeliveryDuplicates")
        return
    owner = str(uuid.uuid4())
    now = int(time.time())
    try:
        events.update_item(
            Key={"pk": key},
            UpdateExpression="SET #s=:processing, lease_owner=:owner, lease_until=:lease, updated_at=:now ADD attempts :one",
            ConditionExpression="attribute_exists(pk) AND #s <> :done AND (attribute_not_exists(lease_until) OR lease_until < :now)",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":processing": "PROCESSING",
                ":owner": owner,
                ":lease": now + LEASE_SECONDS,
                ":now": now,
                ":one": 1,
                ":done": "DELIVERED",
            },
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            # Do not ACK a leased event; its original worker may crash before sending it.
            raise RuntimeError("Event is already leased or completed concurrently") from exc
        raise
    metric("DeliveryAttempts")
    try:
        transport.send(item)
        events.update_item(
            Key={"pk": key},
            UpdateExpression="SET #s=:done, delivered_at=:now REMOVE lease_owner, lease_until",
            ConditionExpression="lease_owner=:owner",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":done": "DELIVERED",
                ":now": int(time.time()),
                ":owner": owner,
            },
        )
        metric("Delivered")
        log("event_delivered", event_key=key)
    except Exception as exc:
        metric("DeliveryFailures")
        log("delivery_failed", event_key=key, error_type=type(exc).__name__)
        events.update_item(
            Key={"pk": key},
            UpdateExpression="SET #s=:retry, last_error_type=:error REMOVE lease_owner, lease_until",
            ConditionExpression="lease_owner=:owner",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":retry": "RETRY",
                ":error": type(exc).__name__,
                ":owner": owner,
            },
        )
        raise


def handler(event, context):
    failures = []
    for record in event.get("Records", []):
        try:
            process(json.loads(record["body"])["event_key"])
        except Exception as exc:
            log("record_retry", message_id=record["messageId"], error_type=type(exc).__name__)
            failures.append({"itemIdentifier": record["messageId"]})
    memory_metric()
    return {"batchItemFailures": failures}
