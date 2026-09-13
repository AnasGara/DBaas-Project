import json

from botocore.exceptions import ClientError

from router import ingest
from router.config import client


def test_accepts_atomically_audits_without_logging_payload(cloud, request_event, capsys):
    result = ingest.handler(request_event, None)
    assert result["statusCode"] == 202
    event = cloud["events"].scan()["Items"][0]
    assert event["raw_body"] == request_event["body"]
    assert cloud["outbox"].get_item(Key={"pk": event["pk"]})["Item"]
    assert "customer-123" not in capsys.readouterr().out


def test_duplicates_and_conflicting_payloads(cloud, request_event):
    assert ingest.handler(request_event, None)["statusCode"] == 202
    assert ingest.handler(request_event, None)["statusCode"] == 200
    changed = json.loads(request_event["body"])
    changed["data"]["customer_id"] = "changed"
    request_event["body"] = json.dumps(changed)
    assert ingest.handler(request_event, None)["statusCode"] == 409
    assert cloud["events"].scan()["Count"] == 1


def test_routes_are_dynamic_but_accepted_delivery_is_pinned(cloud, request_event):
    ingest.handler(request_event, None)
    old = cloud["events"].scan()["Items"][0]
    cloud["routes"].put_item(
        Item={**cloud["route"], "version": "2", "endpoint": "https://hooks.example.com/new"}
    )
    payload = json.loads(request_event["body"])
    payload["id"] = "second"
    request_event["body"] = json.dumps(payload)
    assert ingest.handler(request_event, None)["statusCode"] == 202
    assert (
        json.loads(cloud["events"].get_item(Key={"pk": old["pk"]})["Item"]["route_json"])["version"]
        == "1"
    )
    assert {json.loads(x["route_json"])["version"] for x in cloud["events"].scan()["Items"]} == {
        "1",
        "2",
    }


def test_tenants_cannot_use_each_others_routes(cloud, request_event):
    request_event["requestContext"]["authorizer"]["tenant_id"] = "other"
    assert ingest.handler(request_event, None)["statusCode"] == 400
    assert cloud["events"].scan()["Count"] == 0


def test_auth_and_content_guards(cloud, request_event):
    request_event["headers"] = {}
    assert ingest.handler(request_event, None)["statusCode"] == 415
    request_event["headers"] = {"Content-Type": "application/json"}
    request_event["requestContext"]["authorizer"]["providers"] = "vapi"
    assert ingest.handler(request_event, None)["statusCode"] == 403
    request_event["requestContext"]["authorizer"] = {}
    assert ingest.handler(request_event, None)["statusCode"] == 401


def test_outage_is_not_acknowledged(cloud, request_event, monkeypatch):
    def unavailable(**kwargs):
        raise ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "unavailable"}},
            "TransactWriteItems",
        )

    monkeypatch.setattr(client("dynamodb"), "transact_write_items", unavailable)
    assert ingest.handler(request_event, None)["statusCode"] == 503
    assert cloud["events"].scan()["Count"] == 0
    assert cloud["outbox"].scan()["Count"] == 0


def test_bad_route_fails_closed_without_accepting(cloud, request_event):
    cloud["routes"].put_item(
        Item={**cloud["route"], "endpoint": "https://169.254.169.254/latest/meta-data"}
    )
    assert ingest.handler(request_event, None)["statusCode"] == 503
    assert cloud["events"].scan()["Count"] == 0


def test_raw_vapi_request_creates_expected_routing_key(cloud, request_event):
    cloud["routes"].put_item(Item={**cloud["route"], "event_type": "vapi.call_ended"})
    request_event["body"] = json.dumps(
        {
            "message": {
                "type": "end-of-call-report",
                "call": {"id": "call-123"},
                "endedReason": "hangup",
            }
        }
    )
    assert ingest.handler(request_event, None)["statusCode"] == 202
    assert cloud["events"].scan()["Items"][0]["event_id"] == "vapi:end-of-call-report:call-123"
