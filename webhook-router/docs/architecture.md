# Architecture and delivery semantics

## Authentication and ingestion

The regional REST API uses a token authorizer without authorization caching. Secrets Manager stores tenant IDs, SHA-256 bearer digests, allowed providers, usage key values and enabled flags. A tenant's generated usage key is returned as `usageIdentifierKey`; keys meter traffic rather than acting as the only authentication. Fetching credentials per authorizer invocation supports prompt revocation but adds latency and Secrets Manager cost. A single secret is limited to 64 KiB; use a dedicated keyed credential store for large tenant fleets.

Ingestion validates content type/encoding, strict UTF-8 JSON, duplicate keys, finite numbers, payload size and safe identifiers. Native Vapi `message.type=end-of-call-report` becomes `vapi.call_ended`, with an event ID derived from `message.call.id`. Vapi tool-calls and other synchronous request events are rejected.

Routes are read consistently by authenticated `(tenant_id,event_type)`. They contain a version, HTTPS endpoint, optional JSON Schema and JSON-pointer projection. No expressions, remote schema references or plugins execute from configuration. Route and transformed payload are snapshotted at acceptance; updates affect new events only.

## Atomic acceptance and outbox

The event key is `tenant_id + '#' + SHA256(event_id)`. A DynamoDB transaction conditionally creates both event/audit and outbox records. `202` is returned only after commit. The same ID and canonical payload receives a duplicate `200`; conflicting content receives `409`. Duplicate comparison precedes routing, so disabling a route does not invalidate acknowledgements for accepted events.

Raw bodies are stored in DynamoDB and never logged. Bounding raw and transformed payloads to 64 KiB each, plus a route to 16 KiB, keeps records below DynamoDB's 400 KiB limit. Raw data may contain sensitive transcripts; approve access and retention for real tenant data. Event TTL defaults to 90 days, but deletion is asynchronous. After audit deletion, reusing an ID may create another event.

The outbox has **no TTL**. Its stream invokes a dispatcher that sends an event reference to SQS, then deletes the outbox entry. A crash after send can create a duplicate. Every minute, reconciliation queries a 16-shard due index to recover entries that remain, including after a stream outage exceeds the stream's 24-hour retention. Each run processes a bounded page per shard and older backlog drains over subsequent runs. Eventually consistent GSI reads can cause harmless duplicate sends. Outbox age and stream failures are alarmed.

## Delivery and exactly-once boundary

A worker acquires a 60-second conditional lease with a unique owner token. Another worker's active lease is not acknowledged. SQS visibility is 180 seconds; Lambda timeout is 30 seconds. Batch size is one, partial-batch responses retain failures, and expired leases are recoverable. Owner tokens fence completion/release updates.

Every downstream POST has the same `Idempotency-Key` and pinned payload. The receiver must store that key and its business mutation in the **same transaction**, returning success for already committed keys. Receiver key retention must cover the replay horizon. Without this contract, side effects can repeat after a lost response, expired lease or worker crash. DynamoDB conditional writes alone do not guarantee exactly-once external effects.

Any HTTP 2xx transfers responsibility to the destination; it does not prove a business workflow finished. Redirects are not followed. Timeouts, non-2xx and credential/config failures remain retryable and eventually enter the DLQ after eight receives. Delivery messages are retained for four days, DLQ messages fourteen days. Operators must act within those windows; the event audit supports explicit replay within its retention horizon. Automated retries are bounded and eventual success cannot be promised against an indefinitely unavailable destination.

## Availability, latency and cost

The managed services provide regional multi-AZ availability; this is **not** multi-region failover. Private services require optional worker VPC attachment, approved CIDRs, DNS, endpoints/egress and security-group rules.

The 200 ms target refers to ingestion acknowledgement, not asynchronous delivery. Cold starts, Secrets Manager calls, AWS contention and client network delay can exceed it. The load probe measures client p50/p95; CloudWatch separates Gateway integration latency from Lambda ingestion time. No measured latency or 70% integration-time improvement is claimed.

Compute and request charges scale with usage. Secrets, dashboards, alarms, detailed metrics, X-Ray, retained data, PITR and optional NAT add baseline or additional costs. There are no customer-managed application servers, but dependency maintenance, configuration, incident response and cost management remain necessary.

References: [usage-plan security](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-api-usage-plans.html), [partial batch responses](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html), [API metric statistics](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-metrics-and-dimensions.html).
