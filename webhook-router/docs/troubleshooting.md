# Troubleshooting and FAQ

Start with the HTTP acknowledgement, then determine whether an event was accepted, published, attempted and marked delivered. Use the same event ID while investigating uncertain acknowledgements. The [API reference](api.md) and [data model](data-model.md) define those stages.

## Local setup

| Symptom | Check / resolution |
|---|---|
| `sam` or `ruff` is not found | Use the root virtual environment's executable path from getting-started.md, or activate that environment; the tools are pinned development dependencies |
| Wrong runtime or package errors | Verify Python 3.12 and that pip belongs to the same virtual environment; run `python -m pip check` |
| Tests attempt instance metadata or real AWS | Run the suite through its pytest configuration/fixtures; do not bypass Moto fixture setup or supply production credentials as a workaround |
| `sam local` cannot connect to Docker | Start your intended Docker daemon; local container invocation is optional and separate from tests/native build |
| OSV audit fails to connect | Restore access to `api.osv.dev`, then rerun; do not record an unavailable audit as “no vulnerabilities” |
| SAM ARM64 dependency resolution fails | Check exact pins and available Linux ARM64 wheels; preserve the Python/runtime architecture alignment rather than packaging Windows binaries |
| Root React page still shows DBaaS | That is the preserved legacy application. The webhook service's public surface is the deployed Gateway URL, not a replacement React console |

## Deployment

**Logging-role error or missing access logs:** run preflight in the exact region/account. A role's presence is only the first check; ask the account owner to review its trust/permissions and verify a real staged request emits an access record. This stack does not configure the account-wide API Gateway role for you.

**Production input assertion fails:** set an actual alarm recipient and destination allowlist. Empty values are intentionally blocked in prod. Providing an address still does not confirm the SNS subscription.

**Reserved concurrency allocation fails:** check the account's quota, other reservations and required unreserved pool. Defaults reserve 225 total across the four functions. `WorkerConcurrency` changes only the worker; the other reservations are template constants.

**Table already exists after deleting a stack:** tables are retained. Reuse/import or migrate them through a reviewed procedure; do not delete the retained audit just to force deployment through. An environment change in an existing stack is not a supported shortcut.

**Private receiver is unreachable:** verify exact host allowlist, allowed CIDR, worker subnets/security groups, route tables, DNS, receiver TLS certificate and endpoint/egress access to AWS dependencies. A nonempty subnet parameter does not create networking. Outside VPC mode, a private allowlist alone does not make an internal service reachable.

## Incoming requests

### 401 or 403

Check the exact environment URL and bearer prefix, tenant enablement, token rotation and provider scope. A Vapi-only token cannot send workflow envelopes. Check whether the per-tenant usage key association has propagated. `x-api-key` by itself is not the authentication contract. Do not copy another tenant's key or put credentials in URL query parameters.

### 400

The service deliberately groups several validation causes under `invalid_event_or_unconfigured_type`. Check:

1. UTF-8 JSON object with no duplicate keys/non-finite numbers, within 64 KiB.
2. Workflow root contains exactly `id`, `type`, `data`; workflow_id is a nonblank string for workflow.trigger.
3. Native Vapi uses `message.type=end-of-call-report` and `message.call.id`.
4. An enabled route exists for this authenticated tenant and normalized type.
5. Its full-envelope schema passes and every mapping pointer exists.

The code returns 400 for the application size cap, not 413. Adding more Gateway logging of raw payloads is not the supported diagnostic method; reproduce with sanitized synthetic input and the route sample locally.

### 409

An existing ID has different incoming content. Check whether the producer regenerates timestamps, adds retry metadata or reuses transaction IDs across event types. Preserve the original body for a retry. A different ID is appropriate only for a genuinely different logical event, not as a way around uncertain business state.

### 415

Use `Content-Type: application/json`; omit Content-Encoding or send `identity`. Sending JSON text with a form content type or gzip encoding does not satisfy the handler contract.

### 429 or 5xx

Use bounded backoff with jitter and resend the same ID/body. For repeated 503, inspect safe error classes, route endpoint/secret configuration and AWS dependency permissions. A timeout does not prove the event transaction failed; the next duplicate acknowledgement may resolve a committed request.

## Accepted but not delivered

| Observed state | Next investigation |
|---|---|
| Event `ACCEPTED`, matching outbox remains | Dispatcher stream mapping, due-index recovery, SQS send/delete permissions and OutboxAge |
| Outbox absent, no delivered state | Queue age, worker mapping, DLQ and whether an attempt is currently leased |
| `PROCESSING` with future lease | Allow the current bounded worker attempt to complete; do not override its owner token |
| `PROCESSING` with expired lease | A worker may have crashed; retry/replay must retain the original receiver idempotency key |
| `RETRY` | Receiver availability, destination secret/TLS/DNS/network failure, non-2xx, or failed completion update |
| DLQ contains a reference | Repair the cause, inspect business state/idempotency, then use operator replay; delete the DLQ copy only after verified recovery |

There is no `DEAD_LETTERED` event-table status. Do not manually set a record to DELIVERED merely to clear an alarm. A failed completion update can leave RETRY even if the receiver committed; its idempotency record is the safe way to resolve that ambiguity.

## Configuration and operator tools

**Conditional route update fails:** re-read the current version, review the competing change, choose a new version and publish with the actual prior version. Do not remove the condition to silently overwrite somebody else's edit.

**Route is “not allowed”:** compare its exact hostname and destination secret ARN with the deployed stack parameters. Allowed hosts are not suffix rules. Only HTTPS port 443 is supported; query strings, URL credentials, fragments, redirects and unapproved address ranges are rejected.

**Sample validates locally but real data fails:** the sample is representative validation, not a proof of every provider variant. Inspect required schema fields and mapping pointers against a sanitized variant. Remember that Vapi's raw `message` becomes normalized `data`.

**Credential publication reports cleanup attention:** staging-label cleanup failed after or during publication. Read the exact message and inspect AWSCURRENT through an authorized secret operator; avoid printing secret values. Do not assume publication failed and blindly revoke a newly active usage key. A separate old-key cleanup failure can also require operator attention after successful rotation.

**Replay refuses an event:** it is absent, past its explicit expiry, delivered or actively leased. Verify the key includes the correct tenant and SHA-256 of the **normalized** ID. Do not erase its audit or invent a new ID to bypass the guard.

## FAQ

**Does HTTP 202 mean the receiver finished?** No. It means the event and outbox transaction committed. Receiver processing is asynchronous.

**Why does repeating a failed event return duplicate instead of resending it?** Ingestion is deduplicated independently of delivery. Existing delivery attempts or operator replay handle recovery; accepting the same input twice would undermine the transaction boundary.

**Can I change a route to redirect a pending event?** A pending event retains its route/body snapshot. Current route edits affect new events. Destination secret values are resolved at send time, so credential rotation can affect pending attempts.

**Are exactly-once external effects guaranteed?** Only with a receiver that atomically enforces the provided idempotency key across its own side effects. The router alone cannot distinguish a committed destination operation from a lost response.

**Are tool-calls supported for Vapi?** No. This service accepts asynchronous end-of-call reports and does not implement synchronous tool responses.

**Can I poll status through HTTP?** No status endpoint is implemented. Authorized operators inspect storage/log metadata.

**Is this multi-region disaster recovery?** No. The design uses regional managed services; a regional recovery/failover procedure needs additional implementation and evidence.

**Is the service free when idle?** No. Managed services remove application servers but retained data, backups, secrets, monitoring and optional networking can still incur costs.

**Where should I report readiness?** Use [verification.md](verification.md) for dated local evidence and retain separate staging acceptance results. Do not substitute historical commit timestamps for evidence of deployed operation.
