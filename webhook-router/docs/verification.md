# Verification evidence — October 27, 2026

Local validation on Windows, Python 3.12.6, SAM CLI 1.170.0. Runtime dependencies and build/test tools are pinned in the repository.

| Check | Observed result |
|---|---|
| `pytest --cov=router --cov-report=term-missing --cov-fail-under=90` | **67 passed**, **92.68%** combined runtime statement/branch coverage |
| `ruff check src tests scripts` | Passed |
| `ruff format --check src tests scripts` | Passed |
| `sam validate --lint --region eu-west-3` | Valid SAM template, including transformed-resource linting |
| `sam build` | All four Python 3.12 ARM64 Lambda artifacts built successfully |
| `python -m pip check` | No broken requirements |
| `python scripts/audit_dependencies.py` | OSV checked all **13** pinned runtime packages; **no known advisory findings** returned |

Tests cover authentication/revocation, tenant/provider isolation, schema constraints returned as DynamoDB Decimals, strict payload parsing, transactional rollback, duplicate/conflicting IDs, pinned routing, outbox recovery, enqueue-crash duplication, retry/lease fencing, ambiguous receiver success, partial-batch failures, DNS/IP/TLS protections and concurrent credential updates. AWS behavior is emulated with Moto and transport fakes; these are not live AWS tests.

No AWS resources were deployed or mutated, no production traffic was sent, and no deployed load test or SNS notification test was performed. Docker is not running in the workspace, so SAM local container invocation was not performed. GitHub-hosted CI has been authored but has not run in this session.

Complete [the staging acceptance gates](acceptance.md) before claiming production readiness, sub-200ms latency, exactly-once downstream effects, multi-region recovery, or a quantified business improvement. OSV results reflect its advisory database at scan time and are not a security certification.
