# Configuration and routing reference

This reference follows [template.yaml](../template.yaml), [config.py](../src/router/config.py), and [manage.py](../scripts/manage.py). Deployment values belong to the intended environment; route and credential values are administered through IAM-authorized operator commands.

## SAM parameters

| Parameter | Default | Meaning / constraints |
|---|---|---|
| `ApplicationName` | `webhook-router` | 3–24 lowercase letters/digits/hyphens, beginning with a letter; namespaces functions, tables, metrics and destination secrets |
| `Environment` | `dev` | `dev`, `staging`, or `prod`; use a separate stack per environment |
| `AllowedDestinationHosts` | Empty | Comma-separated exact hostnames; empty denies every destination; no wildcard/suffix matching |
| `AllowedPrivateCidrs` | Empty | Comma-separated approved destination networks; private addresses otherwise denied; special prohibited addresses remain blocked |
| `DestinationSecretPrefix` | `destinations/` | Secret-name suffix below application/environment; must end in `/` and contain only letters, digits, `/`, `_`, `-` |
| `AlarmEmail` | Empty | Optional email in dev/staging; required by the prod input rule; SNS subscription still needs confirmation |
| `EventRetentionDays` | `90` | 30–365 days; event expiry measured from acceptance |
| `WorkerConcurrency` | `20` | 2–200; both reserved worker concurrency and SQS mapping maximum concurrency |
| `ApiRateLimit` | `100` | Minimum 1; stage and per-key usage-plan target rate, requests/second |
| `ApiBurstLimit` | `200` | Minimum 1; stage and per-key usage-plan burst capacity |
| `PrivateSubnetIds` | Empty | Optional comma-delimited worker subnets; enables worker VPC configuration when nonempty |
| `WorkerSecurityGroupIds` | Empty | Worker security groups; supply valid groups together with private subnets |

Production input rules reject empty alarm email and allowed-host values. They do not validate actual network reachability, SNS subscription confirmation or receiver behavior.

The checked-in [samconfig.toml](../samconfig.toml) supplies stack names `webhook-router-dev`, `webhook-router-staging`, `webhook-router-prod` and region `eu-west-3`. Only the environment override is prefilled. Use guided deployment to review and save complete environment-specific values; do not assume example hostnames or email recipients are configured.

## Runtime environment and fixed limits

SAM wires these variables; normally change the corresponding infrastructure parameter rather than manually editing Lambda settings:

| Variable | Source |
|---|---|
| `APPLICATION_NAME`, `ENVIRONMENT` | Application/environment parameters |
| `EVENTS_TABLE`, `OUTBOX_TABLE`, `ROUTES_TABLE` | Created DynamoDB tables |
| `DELIVERY_QUEUE_URL` | Created SQS queue |
| `AUTH_SECRET_ARN` | Stack authentication secret |
| `DESTINATION_SECRET_PREFIX_ARN` | Region/account-specific ARN prefix for application/environment destination secrets |
| `ALLOWED_DESTINATION_HOSTS`, `ALLOWED_PRIVATE_CIDRS` | Deployment allowlists |
| `EVENT_RETENTION_DAYS` | Retention parameter |
| `SERVICE` | Per-function dimension: `authorize`, `ingest`, `dispatch`, `worker` |

| Setting | Implemented value | Where to change |
|---|---|---|
| Runtime / architecture / memory | Python 3.12 / ARM64 / 512 MiB | SAM Globals |
| Function timeouts | Authorizer 10s, ingest 15s, dispatch 60s, worker 30s | Function SAM properties |
| Reserved concurrency | Authorizer 100, ingest 100, dispatch 5, worker parameterized | Function SAM properties |
| AWS SDK timeouts / attempts | Connect 2s, read 3s, total attempts 2 | `SDK_CONFIG` in `config.py` |
| Delivery socket timeout | 5s per blocking socket operation | `transport.py` |
| Lease | 60s | `LEASE_SECONDS` |
| Request / transformed size | 64 KiB each | `MAX_PAYLOAD_BYTES` |
| Route snapshot / mapping | 16 KiB / at most 64 output keys | Validation module |
| Outbox recovery | Every minute, 16 shard queries, at most 100 entries/query per run | Dispatcher and SAM schedule |
| SQS visibility / batch | 180s / one record | Delivery queue and mapping |
| Delivery queue retention / receives | 4 days / DLQ after configured 8 receives | Delivery queue |
| Delivery DLQ / stream-failure queue retention | 14 days | Queue properties |
| Stream mapping retries / max age | 3 retries / 3,600s; failure destination configured | Dispatch event mapping |
| Log retention | 30 days dev/staging, 90 days prod | Log group properties |

These limits are not all runtime-tunable. Changing worker timeout/lease/visibility requires reviewing their relationship together. Request throttles are best-effort; they are not hard budget controls.

## Route document

The DynamoDB key is `(tenant_id,event_type)`. A complete [workflow example](../examples/route.json) and [Vapi example](../examples/vapi-route.json) are included.

| Field | Required | Meaning |
|---|---|---|
| `tenant_id` | Yes | Trusted tenant namespace; must match the producer credential |
| `event_type` | Yes | Normalized event type, e.g. `workflow.trigger` or `vapi.call_ended` |
| `enabled` | Yes | Boolean; only `true` accepts new events |
| `version` | Yes | String identifier; change it on every published update |
| `endpoint` | Yes | HTTPS URL on an allowed hostname, port 443; no credentials, query or fragment |
| `schema` | No | Draft 2020-12 JSON Schema for the full normalized envelope; defaults to `{"type":"object"}` |
| `mapping` | No | Output-key → JSON-pointer projection; omitted/null sends the full normalized envelope |
| `auth_secret_arn` | No | Destination bearer secret inside the permitted application/environment prefix |

Example mapping:

```json
{
  "event_id": "/id",
  "workflow_id": "/data/workflow_id",
  "customer_id": "/data/customer_id"
}
```

For the sample workflow, the destination receives:

```json
{"event_id":"workflow-run-001","workflow_id":"customer-onboarding","customer_id":"demo-123"}
```

Pointers operate on the normalized envelope. `/data/call/id` reads a Vapi call ID; `/data/items/0` indexes an array. `~1` escapes `/` in a key and `~0` escapes `~`. An empty pointer selects the whole envelope. Missing values reject ingestion; there are no default values, concatenation, arithmetic, nested output-path expansion or executable expressions. A mapping key is a literal output key. An empty mapping produces `{}`, which is different from omitting the mapping.

Schema `$ref`, `$dynamicRef` and `$recursiveRef` are forbidden, including local references. Inline required definitions instead. Validation does not attach a format checker; do not rely on a `format` annotation alone to enforce email/URI/date constraints. Schemas are trusted operator configuration; review regex complexity and nesting for the expected untrusted payload size.

## Publishing, changing and disabling routes

From `webhook-router/`, using an activated virtual environment:

```powershell
python scripts/manage.py --region eu-west-3 --stack webhook-router-dev put-route --file examples/route.json --sample examples/workflow.json
```

The initial publish uses `--expected-version new` implicitly and requires the route not to exist. To update, edit the version to a new string and provide the old value:

```powershell
python scripts/manage.py --region eu-west-3 --stack webhook-router-dev put-route --file examples/route.json --sample examples/workflow.json --expected-version 1
```

For disablement, publish the higher version with `enabled:false`; the sample and other configuration still must validate. Disabled or missing routes reject new requests with 400. Events already accepted continue with their frozen route/body. Published versions are labels and are not automatically compared numerically; retain reviewed route files in version control without secrets.

## Credential configuration

The authentication secret initially contains `{"clients":[]}`, so deployment alone does not admit any producer. Use `configure-client`, `--rotate` or `disable-client` rather than editing the secret ad hoc. Secret updates use a staged version and checked AWSCURRENT movement to prevent silent concurrent overwrites. The authorizer reads AWSCURRENT on each call without an application cache.

Destination secrets follow this name namespace with default parameters:

```text
webhook-router/dev/destinations/<service-name>
webhook-router/staging/destinations/<service-name>
webhook-router/prod/destinations/<service-name>
```

Their JSON contract is `{"bearer_token":"<destination-only-token>"}`. Create values through an approved secret manager, never a checked-in file or command argument. Snapshotting stores the ARN; future attempts resolve the secret's current version. Rotation can therefore affect pending deliveries even though their route/body remains frozen.

## Operator CLI

All commands require `--region`; mutation commands also require `--stack`. Global arguments appear **before** the command name.

| Command | Arguments | Effect |
|---|---|---|
| `preflight` | None | Read AWS identity and check regional Gateway logging-role presence |
| `configure-client` | `--tenant`, optional `--providers workflow,vapi`, optional `--rotate` | Prompt for bearer token, create/associate usage key and publish tenant credential record |
| `disable-client` | `--tenant` | Set that tenant credential's enabled flag false |
| `put-route` | `--file`, `--sample`, optional `--expected-version` | Validate and conditionally publish routing configuration |
| `replay` | `--event-key` | Queue an existing eligible event reference using its original identity |

`configure-client` defaults to `workflow` scope. It requires at least 32 printable non-space token characters; generate random secrets rather than satisfying only this length check. Rotation has no dual-token overlap. A replay refuses an absent/expired, delivered or actively leased event. See the [runbook](runbook.md) for permissions, safe rotation and DLQ handling.
