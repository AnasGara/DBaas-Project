import json
import os
import time

from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeDeserializer

from router.config import SHARD_COUNT, client, table
from router.telemetry import log, metric


def publish(item):
    # If send succeeds but deletion fails, the next attempt may send twice. Worker dedup handles it.
    client("sqs").send_message(
        QueueUrl=os.environ["DELIVERY_QUEUE_URL"], MessageBody=json.dumps({"event_key": item["pk"]})
    )
    table("OUTBOX_TABLE").delete_item(Key={"pk": item["pk"]})
    metric("Enqueued")


def handler(event, context):
    if "Records" in event:
        failures = []
        deserializer = TypeDeserializer()
        for record in event["Records"]:
            if record["eventName"] != "INSERT":
                continue
            try:
                item = {
                    k: deserializer.deserialize(v)
                    for k, v in record["dynamodb"]["NewImage"].items()
                }
                publish(item)
            except Exception as exc:
                metric("DispatchFailures")
                log("dispatch_failed", error_type=type(exc).__name__)
                failures.append({"itemIdentifier": record["dynamodb"]["SequenceNumber"]})
        return {"batchItemFailures": failures}
    # Scheduled reconciliation closes the DynamoDB Streams 24-hour retention gap.
    oldest = 0
    failed = False
    for shard in range(SHARD_COUNT):
        result = table("OUTBOX_TABLE").query(
            IndexName="due",
            KeyConditionExpression=Key("shard").eq(str(shard))
            & Key("due_at").lte(int(time.time())),
            Limit=100,
        )
        for item in result.get("Items", []):
            oldest = max(oldest, int(time.time()) - int(item["created_at"]))
            try:
                publish(item)
            except Exception as exc:
                failed = True
                metric("DispatchFailures")
                log("outbox_recovery_failed", error_type=type(exc).__name__)
    metric("OutboxAge", oldest, "Seconds")
    if failed:
        raise RuntimeError("Outbox recovery incomplete")
    return {"reconciled": True}
