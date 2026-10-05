"""Explicit operator commands. No command runs automatically during deployment."""

import argparse
import getpass
import hashlib
import json
import os
import re
import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from router.transport import validate_route_endpoint  # noqa: E402
from router.validation import TENANT_PATTERN, canonical, normalize, prepare_route  # noqa: E402


def stack_state(session, name):
    stack = session.client("cloudformation").describe_stacks(StackName=name)["Stacks"][0]
    outputs = {x["OutputKey"]: x["OutputValue"] for x in stack["Outputs"]}
    params = {x["ParameterKey"]: x["ParameterValue"] for x in stack["Parameters"]}
    os.environ["ALLOWED_DESTINATION_HOSTS"] = params["AllowedDestinationHosts"]
    os.environ["ALLOWED_PRIVATE_CIDRS"] = params.get("AllowedPrivateCidrs", "")
    arn = outputs["AuthSecretArn"].split(":secret:")[0]
    os.environ["DESTINATION_SECRET_PREFIX_ARN"] = (
        arn
        + ":secret:"
        + params["ApplicationName"]
        + "/"
        + params["Environment"]
        + "/"
        + params["DestinationSecretPrefix"]
    )
    return outputs


def replace_credentials(secrets, secret_id, current, data):
    # Publish AWSCURRENT with a compare-and-swap stage movement: concurrent admins cannot overwrite changes.
    token = str(uuid.uuid4())
    stage = "pending-" + token
    secrets.put_secret_value(
        SecretId=secret_id,
        ClientRequestToken=token,
        SecretString=canonical(data),
        VersionStages=[stage],
    )
    try:
        secrets.update_secret_version_stage(
            SecretId=secret_id,
            VersionStage="AWSCURRENT",
            MoveToVersionId=token,
            RemoveFromVersionId=current["VersionId"],
        )
    except Exception:
        try:
            secrets.update_secret_version_stage(
                SecretId=secret_id, VersionStage=stage, RemoveFromVersionId=token
            )
        except Exception:
            print(
                "Credential publication failed; pending-label cleanup also requires attention.",
                file=sys.stderr,
            )
        raise
    try:
        secrets.update_secret_version_stage(
            SecretId=secret_id, VersionStage=stage, RemoveFromVersionId=token
        )
    except Exception:
        # Publication succeeded. Cleanup must not make callers revoke the newly active API key.
        print(
            "Credentials published; pending version-label cleanup requires operator attention.",
            file=sys.stderr,
        )


def client_config(args, session, outputs):
    secrets = session.client("secretsmanager")
    api = session.client("apigateway")
    current = secrets.get_secret_value(SecretId=outputs["AuthSecretArn"], VersionStage="AWSCURRENT")
    data = json.loads(current["SecretString"])
    existing = next((c for c in data["clients"] if c["tenant_id"] == args.tenant), None)
    if args.command == "disable-client":
        if not existing:
            raise ValueError("Tenant does not exist")
        existing["enabled"] = False
        replace_credentials(secrets, outputs["AuthSecretArn"], current, data)
        print("Tenant disabled; authorizer cache is disabled.")
        return
    if not TENANT_PATTERN.fullmatch(args.tenant):
        raise ValueError("Invalid tenant id")
    if existing and not args.rotate:
        raise ValueError("Tenant already exists; specify --rotate for a credential rotation")
    bearer = getpass.getpass("New provider bearer token (32+ random characters; never printed): ")
    if len(bearer) < 32 or any(ord(c) < 33 or ord(c) > 126 for c in bearer):
        raise ValueError("Use at least 32 printable non-space random characters")
    digest = hashlib.sha256(bearer.encode()).hexdigest()
    if any(c["token_sha256"] == digest and c["tenant_id"] != args.tenant for c in data["clients"]):
        raise ValueError("A bearer token cannot belong to two tenants")
    key = api.create_api_key(name=args.tenant + "-" + str(uuid.uuid4())[:8], enabled=True)
    try:
        api.create_usage_plan_key(
            usagePlanId=outputs["UsagePlanId"], keyId=key["id"], keyType="API_KEY"
        )
        entry = {
            "tenant_id": args.tenant,
            "token_sha256": digest,
            "providers": args.providers.split(","),
            "api_key": key["value"],
            "api_key_id": key["id"],
            "enabled": True,
        }
        if not entry["providers"] or any(p not in ("vapi", "workflow") for p in entry["providers"]):
            raise ValueError("Providers must be vapi and/or workflow")
        data["clients"] = [c for c in data["clients"] if c["tenant_id"] != args.tenant] + [entry]
        replace_credentials(secrets, outputs["AuthSecretArn"], current, data)
    except Exception:
        api.delete_api_key(apiKey=key["id"])
        raise
    if existing and existing.get("api_key_id"):
        api.delete_api_key(apiKey=existing["api_key_id"])
    print(
        "Tenant configured. Usage-plan propagation can take several minutes. No credentials printed."
    )


def put_route(args, session, outputs):
    route = json.loads(Path(args.file).read_text(encoding="utf-8"), parse_float=Decimal)
    sample = normalize(json.loads(Path(args.sample).read_text(encoding="utf-8")))
    if not TENANT_PATTERN.fullmatch(route["tenant_id"]) or route["event_type"] != sample["type"]:
        raise ValueError("Route tenant/type is invalid or does not match the sample")
    if not isinstance(route.get("enabled"), bool):
        raise ValueError("Route enabled must be a boolean")
    snapshot, _ = prepare_route({**route, "enabled": True}, sample)
    validate_route_endpoint(snapshot)
    if args.expected_version != "new" and route["version"] == args.expected_version:
        raise ValueError("Bump the route version before publishing an update")
    kwargs = {"Item": route, "ConditionExpression": "attribute_not_exists(tenant_id)"}
    if args.expected_version != "new":
        kwargs.update(
            ConditionExpression="#v=:expected",
            ExpressionAttributeNames={"#v": "version"},
            ExpressionAttributeValues={":expected": args.expected_version},
        )
    session.resource("dynamodb").Table(outputs["RoutesTableName"]).put_item(**kwargs)
    print(
        "Route published. New events use this version; accepted events keep their original snapshot."
    )


def replay(args, session, outputs):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}#[a-f0-9]{64}", args.event_key):
        raise ValueError("Invalid event key")
    item = (
        session.resource("dynamodb")
        .Table(outputs["EventsTableName"])
        .get_item(Key={"pk": args.event_key}, ConsistentRead=True)
        .get("Item")
    )
    if not item or int(item["expires_at"]) <= time.time():
        raise ValueError("Event is absent or outside the replay retention window")
    if item["status"] == "DELIVERED" or int(item.get("lease_until", 0)) >= time.time():
        raise ValueError("Refusing to replay a delivered or actively leased event")
    session.client("sqs").send_message(
        QueueUrl=outputs["DeliveryQueueUrl"], MessageBody=json.dumps({"event_key": args.event_key})
    )
    print("Replay queued with the original payload, destination snapshot and idempotency key.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", required=True)
    parser.add_argument("--stack")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    create = sub.add_parser("configure-client")
    create.add_argument("--tenant", required=True)
    create.add_argument("--providers", default="workflow")
    create.add_argument("--rotate", action="store_true")
    disable = sub.add_parser("disable-client")
    disable.add_argument("--tenant", required=True)
    route = sub.add_parser("put-route")
    route.add_argument("--file", required=True)
    route.add_argument("--sample", required=True)
    route.add_argument("--expected-version", default="new")
    retry = sub.add_parser("replay")
    retry.add_argument("--event-key", required=True)
    args = parser.parse_args()
    os.environ["AWS_DEFAULT_REGION"] = args.region
    session = boto3.Session(region_name=args.region)
    if args.command == "preflight":
        session.client("sts").get_caller_identity()
        account = session.client("apigateway").get_account()
        if not account.get("cloudwatchRoleArn"):
            raise ValueError(
                "Configure the regional API Gateway account CloudWatch logging role before deploying; this stack does not modify account-wide settings"
            )
        print("AWS identity and regional API Gateway logging prerequisite verified.")
        return
    if not args.stack:
        parser.error("--stack is required for mutation commands")
    outputs = stack_state(session, args.stack)
    if args.command in ("configure-client", "disable-client"):
        client_config(args, session, outputs)
    elif args.command == "put-route":
        put_route(args, session, outputs)
    else:
        replay(args, session, outputs)


if __name__ == "__main__":
    main()
