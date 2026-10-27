# Deployment and incident runbook

Part of the [documentation index](README.md). Commands here assume an activated Python 3.12 virtual environment and working directory `webhook-router/`; [getting started](getting-started.md) gives explicit executable paths for PowerShell and POSIX. Consult [configuration](configuration.md) for every parameter/route field and [observability](observability.md) for exact alarm definitions.

## Prerequisites and deployment

1. Choose a dedicated account/region and short-lived role. Review the SAM changeset. Dev, staging and prod require separate stacks and Environment values; do not change an existing environment in place.
2. Configure the regional API Gateway account-level CloudWatch role with an administrator. The template deliberately does not overwrite this shared setting. `python scripts/manage.py --region eu-west-3 preflight` verifies identity and the role's presence; a staged request must verify its actual policy/log delivery.
3. Obtain approved HTTPS services with atomic destination idempotency. Set exact `AllowedDestinationHosts`. Private endpoints also need allowed CIDRs, worker subnets/security groups, DNS and DynamoDB/Secrets Manager endpoints or egress. This stack does not create NAT or network routing.
4. Check Lambda concurrency quotas against default reservations: 100 authorizer, 100 ingest, 5 dispatch and 20 worker, plus the account's unreserved minimum. Adjust the template before deployment if needed.
5. Set `AlarmEmail`, deploy, and confirm the SNS email subscription. Then test notification receipt; stack creation alone does not verify alerts.

```powershell
sam validate --lint --region eu-west-3
sam build
sam deploy --config-env dev --guided
```

Deployment creates billable API, compute, state, messaging, logging, monitoring and secret resources and needs `CAPABILITY_IAM`. CI validates/builds only; it does not deploy or receive long-lived AWS credentials. Add organizational deployment automation using OIDC/protected environments.

Review environment, allowed hosts/CIDRs, secret prefix and alarm email before promotion. Empty hosts deny delivery. Tables/queues are retained; deleting a stack does not delete audit data, and retained named tables require resource import or explicit migration before reusing their names.

## Tenant credentials

```powershell
python scripts/manage.py --region eu-west-3 --stack webhook-router-dev configure-client --tenant demo --providers workflow,vapi
python scripts/manage.py --region eu-west-3 --stack webhook-router-dev configure-client --tenant demo --providers workflow,vapi --rotate
python scripts/manage.py --region eu-west-3 --stack webhook-router-dev disable-client --tenant demo
```

Configure-client prompts invisibly for a new random token and never prints it. Supply the same token to the provider's secure credential mechanism. A per-tenant usage key is created; propagation can take minutes. Rotation changes the digest then removes the previous key; there is no dual-token grace period. Coordinate provider cutover and verify rejection of the old token. Disable-client requires no code redeployment or cache expiry.

Operator privileges: CloudFormation DescribeStacks; GetSecretValue/PutSecretValue/UpdateSecretVersionStage on the authentication secret; API Gateway create/delete keys and associate usage-plan keys; DynamoDB route GetItem/PutItem and event GetItem; SQS SendMessage for replay. Restrict resources to the intended environment. Providers receive none of these operator privileges.

## Dynamic route changes

```powershell
python scripts/manage.py --region eu-west-3 --stack webhook-router-dev put-route --file examples/route.json --sample examples/workflow.json
# Edit the file to version "2" before updating:
python scripts/manage.py --region eu-west-3 --stack webhook-router-dev put-route --file examples/route.json --sample examples/workflow.json --expected-version 1
```

Replace example hostnames with approved real destinations. The sample, schema, transformation and stack allowlist are validated; stale expected versions are rejected. For destination authentication, create a secret under the configured prefix containing `{"bearer_token":"..."}` through a secure secret-management workflow, then reference its ARN as `auth_secret_arn`. Never place tokens in a route file or shell arguments.

Publishing a higher-version route with `enabled:false` stops new matching events. Accepted events retain their snapshot. Emergency isolation may require credential revocation or network controls; changing the live route alone does not reroute old events.

## Alarm triage

| Signal | Action |
|---|---|
| API 4XX >5%, minimum 20 requests/5m | Distinguish credentials, usage-key propagation, schema 400, conflict 409, content-type 415 and throttling 429 |
| Native Lambda Errors >1%/5m | Check error classes, IAM and concurrency; rejected authorizer calls also count as errors |
| DeliveryFailures >1%/5m | Check destination/credentials; partial-batch failures do not increment native Lambda Errors |
| Queue age >120s / DLQ messages | Repair the destination and replay before retention expires; do not purge failures |
| Outbox age >120s or missing telemetry | Check reconciliation schedule, stream mapping, IAM and SQS; outbox has no TTL |
| Stream-failure messages | Fix dispatch and confirm scheduled recovery drains affected outbox items before acknowledging failure records |
| p95 ingestion >200ms | Compare client/Gateway/Lambda latency, cold starts, secrets/DynamoDB latency and throttles |

Logs contain event/message keys, not transcripts. Use an authorized operator role to inspect minimal state. Avoid screenshots or log exports containing secrets or customer payloads.

## Replay, recovery and rollback

Fix the cause, then use the original tenant-scoped event key:

```powershell
python scripts/manage.py --region eu-west-3 --stack webhook-router-dev replay --event-key 'demo#<64-character-event-id-hash>'
```

Replay rejects absent/expired, delivered or actively leased events. It queues the original reference, retaining payload, route and idempotency key. Confirm DELIVERED before deleting the original DLQ message using its receipt handle; replay does not delete that copy automatically. Without destination idempotency, investigate the external business state before retrying.

Delivery queue retention is four days, DLQ retention fourteen, event audit normally ninety. Respond within those windows. Practice PITR restoration to a new table, importing/switching resources and replaying unsettled events in staging. No multi-region DR exercise has been performed by this task.

Complete [acceptance](acceptance.md) before production promotion. Keep the previous deployment artifact for rollback. Rolling back code does not reverse destination effects, consumed messages or snapshotted routes. No automatic zero-downtime migration or regional failover is claimed.
