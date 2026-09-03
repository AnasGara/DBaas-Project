import base64
import binascii
import hashlib
import json
import math
import re
from decimal import Decimal

from jsonschema import Draft202012Validator, SchemaError

from router.config import MAX_PAYLOAD_BYTES, MAX_ROUTE_BYTES
from router.errors import ConfigurationError, InvalidEvent

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
TENANT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def canonical(value):
    def number(value):
        if isinstance(value, Decimal):
            return int(value) if value == value.to_integral_value() else float(value)
        raise TypeError("Unsupported JSON value")

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=number,
    )


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidEvent("Duplicate JSON object keys are forbidden")
        result[key] = value
    return result


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise InvalidEvent("Non-finite numbers are forbidden")
    return number


def decode_body(event):
    body = event.get("body")
    if not isinstance(body, str):
        raise InvalidEvent("A JSON request body is required")
    try:
        raw = (
            base64.b64decode(body, validate=True)
            if event.get("isBase64Encoded")
            else body.encode("utf-8")
        )
        if len(raw) > MAX_PAYLOAD_BYTES:
            raise InvalidEvent("Payload exceeds 64 KiB")
        text = raw.decode("utf-8")
        payload = json.loads(
            text,
            object_pairs_hook=strict_object,
            parse_float=finite_float,
            parse_constant=lambda _: (_ for _ in ()).throw(
                InvalidEvent("Non-finite numbers are forbidden")
            ),
        )
    except (ValueError, UnicodeError, binascii.Error, RecursionError) as exc:
        raise InvalidEvent("Invalid UTF-8 JSON payload") from exc
    if not isinstance(payload, dict):
        raise InvalidEvent("The JSON root must be an object")
    return text, payload


def normalize(payload):
    if "message" in payload:
        message = payload["message"]
        if not isinstance(message, dict) or message.get("type") != "end-of-call-report":
            raise InvalidEvent("Only asynchronous Vapi end-of-call-report events are supported")
        call = message.get("call")
        call_id = call.get("id") if isinstance(call, dict) else None
        if not isinstance(call_id, str) or not ID_PATTERN.fullmatch(call_id):
            raise InvalidEvent("Vapi message.call.id is required")
        event_id = "vapi:end-of-call-report:" + call_id
        event_type = "vapi.call_ended"
        data = message
    else:
        if set(payload) != {"id", "type", "data"}:
            raise InvalidEvent("Workflow envelopes require exactly id, type and data")
        event_id, event_type, data = payload.get("id"), payload.get("type"), payload.get("data")
        if isinstance(event_type, str) and event_type.startswith("vapi."):
            raise InvalidEvent("Vapi event types require a native Vapi server message")
    if not isinstance(event_id, str) or not ID_PATTERN.fullmatch(event_id):
        raise InvalidEvent("id must contain 1–200 safe identifier characters")
    if not isinstance(event_type, str) or not TYPE_PATTERN.fullmatch(event_type):
        raise InvalidEvent("type is invalid")
    if not isinstance(data, dict):
        raise InvalidEvent("data must be an object")
    if event_type == "workflow.trigger" and (
        not isinstance(data.get("workflow_id"), str) or not data["workflow_id"].strip()
    ):
        raise InvalidEvent("workflow.trigger requires data.workflow_id")
    return {"id": event_id, "type": event_type, "data": data}


def identity(tenant, envelope):
    if not isinstance(tenant, str) or not TENANT_PATTERN.fullmatch(tenant):
        raise InvalidEvent("Invalid authenticated tenant")
    return tenant + "#" + hashlib.sha256(envelope["id"].encode()).hexdigest()


def pointer(document, path):
    if not isinstance(path, str) or (path and not path.startswith("/")):
        raise ConfigurationError("Mappings must use JSON pointers")
    value = document
    for part in path.split("/")[1:] if path else []:
        part = part.replace("~1", "/").replace("~0", "~")
        try:
            value = value[int(part)] if isinstance(value, list) and part.isdigit() else value[part]
        except (KeyError, TypeError, IndexError) as exc:
            raise InvalidEvent("A required transformation field is missing") from exc
    return value


def prepare_route(route, envelope):
    if not route or route.get("enabled") is not True:
        raise InvalidEvent("No enabled route for this event type")
    # Store only operational configuration, never arbitrary DynamoDB metadata.
    snapshot = {
        key: route[key]
        for key in ("version", "endpoint", "mapping", "schema", "auth_secret_arn")
        if key in route
    }
    if not isinstance(snapshot.get("version"), str) or not isinstance(
        snapshot.get("endpoint"), str
    ):
        raise ConfigurationError("Route version and endpoint are required")
    if len(canonical(snapshot).encode()) > MAX_ROUTE_BYTES:
        raise ConfigurationError("Route configuration exceeds 16 KiB")
    # DynamoDB returns Decimal even for integer schema constraints such as minLength.
    snapshot = json.loads(canonical(snapshot))
    schema = snapshot.get("schema", {"type": "object"})

    # No remote reference resolution or recursive schemas at runtime.
    def reject_refs(value):
        if isinstance(value, dict):
            if any(key in value for key in ("$ref", "$dynamicRef", "$recursiveRef")):
                raise ConfigurationError("Schema references are forbidden")
            for child in value.values():
                reject_refs(child)
        elif isinstance(value, list):
            for child in value:
                reject_refs(child)

    try:
        reject_refs(schema)
        Draft202012Validator.check_schema(schema)
        if not Draft202012Validator(schema).is_valid(envelope):
            raise InvalidEvent("Payload does not match the configured event schema")
    except (SchemaError, RecursionError) as exc:
        raise ConfigurationError("Invalid route schema") from exc
    mapping = snapshot.get("mapping")
    if mapping is not None and (not isinstance(mapping, dict) or len(mapping) > 64):
        raise ConfigurationError("Invalid route mapping")
    transformed = (
        {key: pointer(envelope, path) for key, path in mapping.items()}
        if mapping is not None
        else envelope
    )
    if len(canonical(transformed).encode()) > MAX_PAYLOAD_BYTES:
        raise InvalidEvent("Transformed payload exceeds 64 KiB")
    return snapshot, transformed
