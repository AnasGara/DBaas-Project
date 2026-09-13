import hashlib
import json
import os
import time

from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from router.config import SHARD_COUNT, client, table
from router.errors import ConfigurationError, InvalidEvent
from router.telemetry import log, memory_metric, metric
from router.transport import validate_route_endpoint
from router.validation import canonical, decode_body, identity, normalize, prepare_route


def response(status_code, **body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body),
    }


def existing_result(existing, digest):
    if existing["payload_hash"] != digest:
        metric("Conflicts")
        return response(409, error="event_id_conflict")
    metric("Duplicates")
    return response(
        200, accepted=True, duplicate=True, event_id=existing["event_id"], status=existing["status"]
    )


def handler(event, context):
    started = time.monotonic()
    try:
        auth = event.get("requestContext", {}).get("authorizer", {})
        tenant = auth.get("tenant_id")
        if not tenant:
            return response(401, error="unauthorized")
        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        if headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            return response(415, error="application_json_required")
        if headers.get("content-encoding", "identity") != "identity":
            return response(415, error="content_encoding_not_supported")
        raw, payload = decode_body(event)
        envelope = normalize(payload)
        provider = "vapi" if "message" in payload else "workflow"
        if provider not in auth.get("providers", "").split(","):
            return response(403, error="provider_not_authorized")
        key = identity(tenant, envelope)
        digest = hashlib.sha256(canonical(payload).encode()).hexdigest()
        events = table("EVENTS_TABLE")
        existing = events.get_item(Key={"pk": key}, ConsistentRead=True).get("Item")
        if existing:
            return existing_result(existing, digest)
        route = (
            table("ROUTES_TABLE")
            .get_item(
                Key={"tenant_id": tenant, "event_type": envelope["type"]}, ConsistentRead=True
            )
            .get("Item")
        )
        snapshot, delivery = prepare_route(route, envelope)
        validate_route_endpoint(snapshot)
        now = int(time.time())
        item = {
            "pk": key,
            "tenant_id": tenant,
            "event_id": envelope["id"],
            "event_type": envelope["type"],
            "payload_hash": digest,
            "raw_body": raw,
            "route_json": canonical(snapshot),
            "delivery_json": canonical(delivery),
            "status": "ACCEPTED",
            "attempts": 0,
            "created_at": now,
            "expires_at": now + int(os.environ.get("EVENT_RETENTION_DAYS", "90")) * 86400,
        }
        outbox = {
            "pk": key,
            "shard": str(int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % SHARD_COUNT),
            "due_at": now,
            "created_at": now,
        }
        serializer = TypeSerializer()

        def serialize(obj):
            return {k: serializer.serialize(v) for k, v in obj.items()}

        try:
            client("dynamodb").transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": os.environ["EVENTS_TABLE"],
                            "Item": serialize(item),
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                    {
                        "Put": {
                            "TableName": os.environ["OUTBOX_TABLE"],
                            "Item": serialize(outbox),
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                ]
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "TransactionCanceledException":
                existing = events.get_item(Key={"pk": key}, ConsistentRead=True).get("Item")
                if existing:
                    return existing_result(existing, digest)
            raise
        metric("Accepted")
        log(
            "event_accepted",
            event_key=key,
            request_id=event.get("requestContext", {}).get("requestId"),
        )
        return response(202, accepted=True, duplicate=False, event_id=envelope["id"])
    except InvalidEvent:
        metric("ValidationFailures")
        return response(400, error="invalid_event_or_unconfigured_type")
    except ConfigurationError as exc:
        metric("ConfigurationFailures")
        log("configuration_failure", error_type=type(exc).__name__)
        return response(503, error="routing_configuration_unavailable")
    except Exception as exc:
        metric("IngestionFailures")
        log("ingestion_failed", error_type=type(exc).__name__)
        return response(503, error="temporarily_unavailable")
    finally:
        metric("IngestionLatency", (time.monotonic() - started) * 1000, "Milliseconds")
        memory_metric()
