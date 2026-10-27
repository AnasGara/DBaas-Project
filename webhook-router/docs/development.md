# Development and contribution guide

## Working tree and service boundaries

Run the webhook service checks from `webhook-router/` with the Python 3.12 virtual environment described in [getting started](getting-started.md). No React, Laravel, PHP or Docker Compose service is required. The root `frontend/` and `backend/` belong to the legacy DBaaS prototype; changing them does not update the webhook engine.

| Source | Responsibility |
|---|---|
| `src/router/authorizer.py` | Tenant/provider authentication and authorizer-sourced API usage key |
| `src/router/validation.py` | Strict JSON, provider normalization, keys, schema and projection |
| `src/router/ingest.py` | HTTP acknowledgements, duplicate/conflict decisions and atomic persistence |
| `src/router/dispatch.py` | Outbox stream handling and scheduled publication reconciliation |
| `src/router/worker.py` | Conditional leases, delivery execution, completion and retry state |
| `src/router/transport.py` | HTTPS destination restrictions, DNS pinning, TLS and destination secrets |
| `src/router/config.py` | Limits and cached AWS client/table handles with bounded SDK retries |
| `src/router/telemetry.py` | Structured logs and Embedded Metric Format output |
| `scripts/manage.py` | Explicit operator configuration, rotation and replay |
| `scripts/load_test.py` | Opt-in deployed synthetic acceptance/latency probe |
| `scripts/audit_dependencies.py` | OSV query for the full pinned runtime closure |
| `template.yaml` | Functions, explicit roles, state/messaging, schedules and observability |

## Verification commands

With the environment activated:

```text
python -m pytest --cov=router --cov-report=term-missing --cov-report=xml --cov-fail-under=90
ruff check src tests scripts
ruff format --check src tests scripts
python scripts/audit_dependencies.py
sam validate --lint --region eu-west-3
sam build
```

Formatting changes can be applied with `ruff format src tests scripts`; review them before committing. Use `python -m pytest tests/test_worker.py` to isolate a failure while developing, then run the relevant broader checks after the change is complete. Running the deployed load probe is a separate operator activity, not part of the isolated unit test suite.

## Test strategy

`tests/conftest.py` sets fake AWS credentials, starts Moto, resets cached clients between tests, and creates isolated DynamoDB/SQS fixtures. Tests invoke real handler/state logic against those emulated services. Transport tests replace sockets/connections or destination calls so they do not send real business webhooks.

| Test area | Evidence |
|---|---|
| Validation | Strict/ambiguous JSON, safe IDs, provider types, pointers, schema constraints and size caps |
| Authorization | Tenant/provider context, invalid credentials and revocation |
| Ingestion | Atomic records, duplicate/conflicting IDs, tenant routes, pinned snapshots and unavailable state store |
| Dispatcher | Reconciliation, publication failure and enqueue-before-crash duplicates |
| Worker / delivery contract | Leases, recovery, partial batch behavior and receiver success with lost completion update |
| Transport | Allowlist, metadata/private address rejection, pinned socket with original TLS hostname and scoped secrets |
| Management | Stale concurrent secret edits and post-publication cleanup failures |
| Infrastructure | Retention, backups, visibility/timeout alignment, explicit roles, authentication and alarms |

Coverage includes branches and targets the runtime package, not a promise that every operator command or AWS behavior is fully exercised. A 90% floor is enforced by CI. Moto cannot prove real IAM authorization, multi-AZ operation, AWS throttling, network routes, SNS delivery or deployed latency. Complete [acceptance](acceptance.md) for those claims.

## CI and dependency maintenance

[router.yml](../../.github/workflows/router.yml) runs on changes under the service or its workflow. It installs pinned dependencies on Python 3.12, checks lint/format, audits runtime pins through OSV, runs coverage-gated tests, validates SAM, builds artifacts, and uploads coverage XML. It has read-only repository permission and no deployment credentials or deployment step. Root README-only changes do not trigger that path-filtered workflow.

`src/requirements.txt` pins the full runtime dependency closure. `requirements.txt` includes that file; `requirements-dev.txt` adds `requirements-dev.lock` for build/test tools. The Windows-only `pywin32` pin has a platform marker. Do not add SAM/test/audit tooling to the Lambda runtime manifest just because it is installed in the developer environment.

When updating a dependency:

1. Review its upstream changes and relevant advisories; use an isolated environment to resolve compatible exact versions.
2. Update direct and transitive runtime pins together, and the development lock where affected. Keep platform markers intact.
3. Run `python -m pip check`, the runtime advisory audit, tests and SAM build, including native ARM64 dependency resolution.
4. Retain the same validated source/pins for staging and production promotion; do not deploy an unreviewed floating dependency resolution.

OSV receives public package names and versions, not webhook payloads or credentials. Advisory unavailability is a failed audit, not a clean result. A clean scan covers known published advisories at that time; it is not a full security review. Dependabot configuration schedules dependency/action update proposals; it does not automatically prove compatibility or deploy updates.

## Change review checklist

- Preserve the transaction boundary between event acceptance and publication intent.
- Preserve tenant scoping, same-ID conflict checks and stable downstream idempotency keys.
- Keep accepted route/body snapshots immutable; document any migration or version-contract change.
- Review timeout, lease, visibility and concurrency settings together.
- Keep payloads, provider tokens, destination secrets and response bodies out of logs.
- Add tests for the failure/crash boundary being changed, rather than only the happy path.
- Update the matching API/configuration/operations guide when behavior changes.

Use ordinary, accurately dated commits for new work. The older synthetic schedule is disclosed in [history provenance](history-provenance.md); it does not establish historical development or deployments. Do not amend that schedule merely to make new work appear older.

## Documentation maintenance

Keep the root README concise and navigable, and put detailed references here. Check relative links and local OpenAPI references after moving files. The OpenAPI specification documents the public contract; modifying it alone does not change API Gateway or handler validation. Treat verification.md as dated evidence and distinguish a newly executed result from a copied historical claim.
