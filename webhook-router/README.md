# Webhook router service

This directory contains the deployable **Serverless Webhook Event Router & Processing Engine**. It accepts authenticated webhooks, validates and snapshots routing configuration, atomically persists an audit/outbox entry, and delivers asynchronously with retries and idempotency keys.

- [Complete documentation index](docs/README.md)
- [Getting started: local validation through first delivery](docs/getting-started.md)
- [API reference](docs/api.md) and [OpenAPI contract](docs/openapi.yaml)
- [Configuration and routing reference](docs/configuration.md)
- [Architecture and delivery guarantees](docs/architecture.md)
- [Deployment and incident runbook](docs/runbook.md)

From the repository root, create a Python 3.12 virtual environment and install `webhook-router/requirements-dev.txt`. From this directory, run verification with that environment's Python:

```text
python -m pytest --cov=router --cov-fail-under=90
ruff check src tests scripts
ruff format --check src tests scripts
python scripts/audit_dependencies.py
sam validate --lint --region eu-west-3
sam build
```

Use the virtual environment's explicit executable paths if it is not activated; the getting started guide gives PowerShell and Linux/macOS commands.

Acceptance is asynchronous: `202` means durable acceptance, not downstream completion. Exactly-once external effects require a destination that atomically honors `Idempotency-Key`. Local verification has passed; deployed production acceptance is still required. See [recorded evidence](docs/verification.md) and [release gates](docs/acceptance.md).
