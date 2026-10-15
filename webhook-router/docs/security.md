# Security model

Public callers authenticate using high-entropy tenant bearer tokens; only digests are stored. Separate generated API usage keys meter requests. Tenant/provider identity comes only from authorizer context. Do not put secrets in URLs, route files, shell arguments, CI output or Git.

Route updates, credential changes and replay require **operator IAM**, not a public administration endpoint. Use AWS SSO, short-lived credentials and separate deployment/route-admin/read roles. Enable CloudTrail management collection plus DynamoDB/SQS data events for route/replay audit; data-plane writes are not logged by default. Configure organization-level retention before production. Credential changes use an AWSCURRENT stage compare-and-swap and route changes use expected-version conditions.

Destinations require an exact hostname allowlist, HTTPS and port 443. URL credentials, query strings, fragments, control characters and redirects are rejected. DNS addresses are checked against metadata/link-local, loopback, multicast, unspecified and unapproved private networks. The socket connects to the checked address while validating TLS against the original hostname, preventing DNS-rebinding between validation and use. Independently restrict worker egress in the VPC. DNS/TLS failures remain retryable.

Destination bearer secrets must be inside the configured Secrets Manager ARN prefix, namespaced as `<ApplicationName>/<Environment>/<DestinationSecretPrefix>`. This keeps dev, staging and prod secret access separate. Provider credentials are never forwarded. Snapshots contain secret ARNs rather than values, so rotation is independent of the stored payload.

## Runtime permissions

Explicit function roles avoid generated broad basic-execution policies:

| Function | Permissions |
|---|---|
| Authorizer | Read its single authentication secret |
| Ingest | Read routes/events; PutItem for atomic event/outbox transaction |
| Dispatcher | Read its outbox stream; query due index; delete outbox; send delivery/failure messages |
| Worker | Read/update events; consume delivery messages; read secrets under the destination prefix |

Log writes target only precreated per-function groups. X-Ray write APIs and DynamoDB ListStreams require wildcard resources because they do not support resource-level scoping. Optional VPC ENI APIs require broad resource scope and are omitted outside VPC mode. Tables use SSE, PITR and prod deletion protection. Queues use service-managed encryption and TLS-only resource policies. Secrets Manager supplies encryption at rest. Add scoped customer-managed KMS policies if your organization requires its own keys.

## Data, logs and abuse

Raw accepted data can contain transcripts and customer identifiers; only the event table retains it. Invalid payload bodies are not retained. Application logs exclude payloads, secret values, destination response bodies and exception messages. API access logs include source IP/request IDs; assess their personal-data retention. Error logs use exception classes and internal keys only.

The application cap is 64 KiB; API Gateway can receive larger requests before that check. Add WAF size/rate rules where the threat model requires them. Usage throttles are best-effort and do not enforce hard cost limits. Reserved concurrency protects backend pressure, not request costs. Configure AWS Budgets and organizational guardrails.

There is no public admin API, CORS configuration or payload tracing. CloudTrail, GuardDuty, Config, dependency review and rotation are organizational prerequisites, not account-wide settings silently changed by the stack. No compliance certification is claimed.
