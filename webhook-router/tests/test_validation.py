import base64
import json
from decimal import Decimal

import pytest

from router.errors import ConfigurationError, InvalidEvent
from router.validation import canonical, decode_body, identity, normalize, pointer, prepare_route


@pytest.mark.parametrize(
    "body", ["[]", "null", '{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', "{"]
)
def test_rejects_ambiguous_or_invalid_json(body):
    with pytest.raises(InvalidEvent):
        decode_body({"body": body})


def test_enforces_size_and_base64():
    assert decode_body({"body": '{"number":1.25}'})[1]["number"] == 1.25
    with pytest.raises(InvalidEvent):
        decode_body({"body": " " * 65537})
    with pytest.raises(InvalidEvent):
        decode_body({"body": "%%%", "isBase64Encoded": True})
    assert decode_body(
        {"body": base64.b64encode(b'{"ok":true}').decode(), "isBase64Encoded": True}
    )[1] == {"ok": True}


def test_vapi_normalizes_actual_server_message():
    result = normalize(
        {
            "message": {
                "type": "end-of-call-report",
                "call": {"id": "call-123"},
                "endedReason": "hangup",
            }
        }
    )
    assert result["type"] == "vapi.call_ended"
    assert result["id"] == "vapi:end-of-call-report:call-123"


@pytest.mark.parametrize(
    "payload",
    [
        {"message": {"type": "tool-calls", "call": {"id": "1"}}},
        {"message": {"type": "end-of-call-report", "call": {}}},
        {"id": "bad\r\nheader", "type": "workflow.trigger", "data": {"workflow_id": "x"}},
        {"id": "valid", "type": "workflow.trigger", "data": {}},
        {"id": "valid", "type": "workflow.trigger", "data": []},
        {"id": "valid", "type": "vapi.call_ended", "data": {}},
        {"id": "valid", "type": "workflow.trigger", "data": {}, "spoofed_tenant": "other"},
    ],
)
def test_provider_validation(payload):
    with pytest.raises(InvalidEvent):
        normalize(payload)


def test_tenant_namespace_and_stable_hash():
    envelope = {"id": "same"}
    assert identity("acme", envelope) != identity("other", envelope)
    assert identity("acme", envelope) == identity("acme", envelope)
    with pytest.raises(InvalidEvent):
        identity("invalid#tenant", envelope)
    assert json.loads(canonical({"number": Decimal("1.25")}))["number"] == 1.25


def test_json_pointer_escaping_and_arrays():
    assert pointer({"a/b": {"~field": [42]}}, "/a~1b/~0field/0") == 42
    with pytest.raises(InvalidEvent):
        pointer({}, "/missing")
    with pytest.raises(ConfigurationError):
        pointer({}, "not-a-pointer")


def test_schema_and_transform_are_validated():
    route = {
        "enabled": True,
        "version": "1",
        "endpoint": "https://hooks.example.com",
        "mapping": {"event": "/id"},
        "schema": {"type": "object", "required": ["id"]},
    }
    snapshot, result = prepare_route(route, {"id": "hello"})
    assert result == {"event": "hello"} and snapshot["version"] == "1"
    with pytest.raises(InvalidEvent):
        prepare_route(route, {})
    with pytest.raises(ConfigurationError):
        prepare_route(
            {**route, "schema": {"$ref": "https://attacker.example/schema"}}, {"id": "hello"}
        )
    with pytest.raises(InvalidEvent):
        prepare_route({**route, "mapping": {"huge": "/large"}}, {"id": "hi", "large": "x" * 65537})
