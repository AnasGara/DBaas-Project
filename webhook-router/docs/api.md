# HTTP API and integration reference

The deployed public interface has one operation: **`POST /{Environment}/webhooks`**. The full URL is the CloudFormation `WebhookUrl` output. There is no public route-management API, event-list endpoint, health route or status-polling endpoint in this service. The [OpenAPI document](openapi.yaml) describes this contract; [template.yaml](../template.yaml) remains the deployment source of truth.

## Authentication and headers

| Header | Requirement |
|---|---|
| `Authorization` | `Bearer <tenant-token>` from operator onboarding; required by the Lambda authorizer |
| `Content-Type` | `application/json`; an optional charset parameter is accepted |
| `Content-Encoding` | Omit, or use `identity`; compressed bodies are rejected |

You do not submit a tenant ID or API usage key in the request. The authorizer supplies trusted tenant/provider scope and the API Gateway usage key. An incoming `Idempotency-Key` header does **not** override event identity; the body event ID determines deduplication. Bearer tokens are not forwarded to receivers.

## Workflow envelope

```json
{
  "id": "workflow-run-001",
  "type": "workflow.trigger",
  "data": {
    "workflow_id": "customer-onboarding",
    "customer_id": "demo-123"
  }
}
```

| Field | Contract |
|---|---|
| `id` | String, 1–200 characters, matching `^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$` |
| `type` | String matching `^[a-z][a-z0-9_.-]{0,79}$`; must have an enabled tenant route |
| `data` | JSON object; validated against the selected route's schema |
| `data.workflow_id` | Nonblank string required for `workflow.trigger` |

Exactly `id`, `type` and `data` are permitted at the workflow root. Put additional business metadata inside `data`. Types prefixed `vapi.` cannot be impersonated through this workflow envelope. Other event types can be introduced through routes without hardcoding their schema, provided they satisfy the shared envelope/provider rules.

The schema validates the **normalized full envelope**, not just `data`. A route may require additional fields such as `data.customer_id`; the sample route does. Passing the shared envelope checks does not imply passing a particular tenant's schema or transformation.

## Native Vapi reports

The service accepts this raw provider shape:

```json
{
  "message": {
    "type": "end-of-call-report",
    "call": {"id": "call-demo-001"},
    "endedReason": "customer-ended-call"
  }
}
```

It normalizes to:

```json
{
  "id": "vapi:end-of-call-report:call-demo-001",
  "type": "vapi.call_ended",
  "data": {
    "type": "end-of-call-report",
    "call": {"id": "call-demo-001"},
    "endedReason": "customer-ended-call"
  }
}
```

`message.call.id` must satisfy the safe identifier rule; the prefixed normalized ID must also fit the 200-character limit. Configure a tenant with the `vapi` provider scope and a route for `vapi.call_ended`. The supplied Vapi route additionally requires `endedReason` for its projection.

Configure Vapi's saved server configuration with the deployed URL and a custom bearer credential. Subscribe this URL to end-of-call reports only. `tool-calls`, `assistant-request` and other events needing synchronous business responses are not implemented here; they are rejected rather than answered asynchronously.

## JSON and size constraints

- Maximum decoded request body: **65,536 bytes**, measured as UTF-8 bytes rather than characters.
- Root must be an object; malformed JSON, duplicate object keys, non-finite numbers and invalid UTF-8 are rejected.
- Route snapshot limit: **16,384 bytes**; transformed JSON limit: **65,536 bytes**.
- JSON-pointer mapping allows at most **64 output fields**. Missing required pointer targets reject ingestion.
- Request bodies over the application limit currently return **400**, not a dedicated 413 response. API Gateway can reject a request before the Lambda executes under its own limits.

## Responses

All handler responses use JSON and `Cache-Control: no-store`. Gateway-generated failures have their own body shape.

### Durable acceptance — 202

```json
{"accepted":true,"duplicate":false,"event_id":"workflow-run-001"}
```

Both the event audit and publication intent have committed. Downstream processing happens later. This is not a receipt for completed business processing.

### Duplicate — 200

```json
{"accepted":true,"duplicate":true,"event_id":"workflow-run-001","status":"DELIVERED"}
```

The status can also be `ACCEPTED`, `PROCESSING` or `RETRY`. A duplicate does not create another outbox entry or reschedule an existing failed delivery. Operators use replay when appropriate.

### Error reference

| HTTP status | Application error / gateway behavior | Producer action |
|---|---|---|
| 400 | `invalid_event_or_unconfigured_type` | Check JSON, ID/type/data, provider shape, route enablement, schema and required mapping fields |
| 401 | Authorizer rejection; handler fallback `unauthorized` | Correct the bearer credential; do not loop indefinitely |
| 403 | `provider_not_authorized` or Gateway key/access rejection | Check scope, enabled tenant, usage-plan propagation and environment |
| 409 | `event_id_conflict` | Investigate changed content under the same ID; do not invent a retry ID to bypass the conflict |
| 415 | `application_json_required` or `content_encoding_not_supported` | Correct headers/body encoding |
| 429 | Gateway throttling | Retry with bounded exponential backoff and jitter |
| 503 | `routing_configuration_unavailable` or `temporarily_unavailable` | Retry the identical event with backoff; notify the operator if persistent |
| Other 5xx | Gateway/integration/platform failure | Treat acknowledgement as uncertain and retry the same ID/body |

Example application error:

```json
{"error":"event_id_conflict"}
```

The configured default Gateway 4xx template uses `{"error":"request_rejected","request_id":"..."}`; the 5xx template uses `temporarily_unavailable` with a request ID. Some service failures may differ. Base retry decisions on the HTTP status, not on parsing one exact Gateway error string.

## Producer retry and identity rules

Use one stable event ID for the life of a logical event. Identity is scoped by tenant, not event type: reusing an ID for a different type also conflicts. Fingerprints use parsed, sorted-key JSON serialization, so object key order/formatting changes do not create another event; arbitrary payload mutations do conflict. This serialization is not advertised as RFC 8785 canonicalization.

On timeouts, disconnects, 429 or retryable 5xx, resend the same body and ID with bounded exponential backoff and jitter. A transaction may have committed even when its response was lost. A duplicate acknowledgement safely resolves that uncertainty. Do not refresh timestamps or mutate retry metadata inside the body between attempts. Audit/deduplication retention defaults to 90 days; once a record is deleted, the same ID can be accepted again.

## Downstream delivery contract

The worker sends an HTTPS POST to the **snapshotted route endpoint**. With no `mapping`, its body is the normalized `{id,type,data}` envelope. With a mapping, its body is the projected object. It sends:

| Header | Value |
|---|---|
| `Content-Type` | `application/json` |
| `User-Agent` | `WebhookRouter/1.0` |
| `Idempotency-Key` | `<tenant_id>#<sha256(normalized-event-id)>` |
| `X-Webhook-Event-ID` | Normalized event ID |
| `X-Webhook-Event-Type` | Normalized type |
| `Authorization` | Optional `Bearer <destination-token>` resolved from the approved destination secret |

The receiver must atomically persist the idempotency key and business mutation, then return a 2xx response for an already committed duplicate. Illustrative receiver logic:

```text
begin transaction
  claim the idempotency key with a unique constraint
  if a committed claim already exists:
    return the previously recorded success
  perform the business mutation
  record the successful result under that key
commit transaction
return success
```

The transaction and contention handling depend on the receiver's database; this is a contract, not a supplied receiver implementation. If the receiver performs another external side effect, it must extend idempotency across that boundary as well. Retain receiver keys for at least the agreed replay horizon.

Any 2xx marks the event `DELIVERED`, including a receiver's asynchronous 202. Non-2xx responses, TLS/DNS failures and timeouts are retryable; redirects are not followed. Error response bodies are not used for routing or logged. The socket timeout is five seconds per operation, not a guaranteed five-second end-to-end deadline; the worker Lambda timeout is 30 seconds.

The router provides at-least-once delivery attempts with DLQ escalation. Exactly-once business effects require the receiver behavior above. See [architecture](architecture.md) for crash windows and [runbook](runbook.md) for replay.
