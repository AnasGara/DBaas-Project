# Project documentation

This documentation describes the implemented AWS webhook service. The [root README](../../README.md) gives the project overview; the [legacy DBaaS documentation](../../docs/dbaas.md) covers the separate React/Laravel prototype.

## Start here

1. Follow [getting started](getting-started.md) to install tooling, run local checks, prepare AWS, and submit a first synthetic event.
2. Read the [API contract](api.md) before configuring a webhook producer or downstream receiver.
3. Use [configuration](configuration.md) to create a tenant and publish versioned routes.
4. Run the [staging acceptance gates](acceptance.md) before promoting to production.

## Guides and references

| Document | Purpose |
|---|---|
| [Getting started](getting-started.md) | Prerequisites, PowerShell/POSIX commands, AWS setup, first request and expected results |
| [API reference](api.md) | Authentication, payloads, response codes, retries, Vapi normalization and receiver responsibilities |
| [OpenAPI 3.1 specification](openapi.yaml) | Machine-readable documentation for `POST /webhooks`; not a second deployment template |
| [Configuration reference](configuration.md) | Every SAM parameter, runtime constants, routing format, secrets and operator commands |
| [Architecture](architecture.md) | Transactional outbox, leases, delivery semantics, availability and tradeoffs |
| [Data model](data-model.md) | Table keys, fields, state transitions, retention and event correlation |
| [Development](development.md) | Source map, test strategy, CI, dependency updates and contribution workflow |
| [Observability](observability.md) | Metrics, dashboard, exact alarm thresholds and log queries |
| [Deployment and incident runbook](runbook.md) | Provisioning, rotation, route updates, replay, rollback and recovery |
| [Troubleshooting](troubleshooting.md) | Symptom-to-cause diagnostics, local setup problems and common integration mistakes |
| [Security](security.md) | Trust boundaries, permissions, data handling and network protections |
| [Production acceptance](acceptance.md) | Required deployed evidence and safe load-testing procedure |
| [Verification evidence](verification.md) | Results observed locally on October 27, 2026, with their limitations |
| [History provenance](history-provenance.md) | Explanation of the explicitly synthetic historical Git dates |

## Documentation conventions

- Unless stated otherwise, commands run from `webhook-router/` after installing the root `.venv` environment.
- `demo`, example IDs, example hostnames and payloads are synthetic. Replace deployment values with approved environment-specific configuration.
- `eu-west-3` is the repository's configured example region. Select the intended account and region explicitly.
- Setup and verification are local; deployment and operator commands can mutate AWS and incur charges. Each guide distinguishes these steps.
- `202 accepted`, `DELIVERED`, and completion of the destination's business workflow are different milestones.
- The source of truth for infrastructure is [template.yaml](../template.yaml); the source of truth for HTTP behavior is [ingest.py](../src/router/ingest.py) and [validation.py](../src/router/validation.py).

## Terminology

| Term | Meaning |
|---|---|
| Tenant | Trusted namespace obtained from the Lambda authorizer, not a caller-supplied payload field |
| Event ID | Provider's stable identifier; unique across event types within one tenant |
| Event key | Tenant plus SHA-256 of event ID; used in storage, queue references and downstream idempotency |
| Route | Current configuration selected by tenant and normalized event type |
| Snapshot | Route and transformed payload frozen when an event is accepted |
| Outbox | Durable publication intent written atomically with the audit record |
| Lease | Temporary conditional claim on processing an event, fenced by an owner token |
| DLQ | Dead-letter queue for exhausted delivery attempts; requires operator attention |
| Replay | Requeueing an existing event reference without inventing another event ID or payload |
