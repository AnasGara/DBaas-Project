# Getting started

This guide takes a new contributor from a clone to local verification, then explains the operator steps for a first AWS deployment. AWS deployment is optional for local unit tests.

## 1. Prerequisites

| Tool or access | Needed for |
|---|---|
| Git | Obtaining source and reviewing changes |
| Python 3.12 and pip | Runtime dependencies, tests, SAM CLI and operator scripts |
| Internet access to package indexes | Initial dependency installation and SAM dependency resolution |
| Internet access to OSV | Runtime advisory audit; it fails rather than reports success if unavailable |
| AWS CLI or configured SDK credential chain | Deployment and operator commands |
| Short-lived AWS credentials and intended region | Access to the deployment account; not required by Moto tests |
| Docker daemon | Optional `sam local` container execution; not needed for the documented unit tests or native `sam build` |

Python 3.12 matches the Lambda runtime. The SAM CLI is included in the pinned development tooling; installing it inside the virtual environment avoids depending on a different global version.

## 2. Install and verify locally

Run from the repository root. On PowerShell:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python -m pip install -r webhook-router/requirements-dev.txt
Set-Location webhook-router
..\.venv\Scripts\python -m pytest --cov=router --cov-report=term-missing --cov-fail-under=90
..\.venv\Scripts\ruff check src tests scripts
..\.venv\Scripts\ruff format --check src tests scripts
..\.venv\Scripts\python scripts/audit_dependencies.py
..\.venv\Scripts\sam validate --lint --region eu-west-3
..\.venv\Scripts\sam build
```

On Linux/macOS, from the repository root:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r webhook-router/requirements-dev.txt
cd webhook-router
../.venv/bin/python -m pytest --cov=router --cov-report=term-missing --cov-fail-under=90
../.venv/bin/ruff check src tests scripts
../.venv/bin/ruff format --check src tests scripts
../.venv/bin/python scripts/audit_dependencies.py
../.venv/bin/sam validate --lint --region eu-west-3
../.venv/bin/sam build
```

Expected: tests and lint succeed, coverage meets 90%, the advisory response lists no findings, the SAM template validates, and four Lambda artifacts are built under `.aws-sam/build/`. The [verification record](verification.md) captures a previous local run; your output is the evidence for your checkout and environment.

The test fixture supplies fake credentials and Moto AWS emulation. Do not replace those credentials with a production profile to make unit tests work. Build/validation do not create a deployed stack. The OSV audit requires a network connection even though the runtime tests are isolated.

## 3. Prepare an AWS environment

These steps require an operator and create billable resources when deployment runs.

1. Select the intended AWS account and authenticate with its short-lived role. Review the account, region and service quotas.
2. Have an account administrator configure the regional API Gateway CloudWatch logging role. This stack does not overwrite that account-wide setting.
3. Choose a safe HTTPS test destination that accepts synthetic events and implements the [receiver idempotency contract](api.md#downstream-delivery-contract).
4. Decide exact allowed destination hostnames and a monitored alarm email. Private services additionally need VPC connectivity, allowed CIDRs and endpoint/egress access; see [configuration](configuration.md).

From `webhook-router/`, on PowerShell:

```powershell
..\.venv\Scripts\python scripts/manage.py --region eu-west-3 preflight
..\.venv\Scripts\sam deploy --config-env dev --guided
```

If using POSIX, replace `..\.venv\Scripts\python` with `../.venv/bin/python` and the SAM path with `../.venv/bin/sam`.

During guided deployment, preserve `Environment=dev`, provide `AllowedDestinationHosts` for the actual receiver, and provide `AlarmEmail`. Review the changeset. The `prod` input rules require nonempty destination hosts and alarm email. Confirm the SNS email subscription after deployment. Preflight verifies the presence of the API Gateway logging role, not all its permissions or actual log delivery.

Read outputs without displaying secret values:

```powershell
aws cloudformation describe-stacks --region eu-west-3 --stack-name webhook-router-dev --query "Stacks[0].Outputs" --output table
```

Record `WebhookUrl`, queue URLs, table names and `AlarmTopicArn` in the environment handover. `AuthSecretArn` is a resource identifier, not the token value.

## 4. Configure one tenant and route

The commands below use the `demo` tenant in the checked-in examples. Generate a new high-entropy bearer token in your approved password/secret manager, and enter it at the hidden operator prompt. Supply the same token to your producer through its secure credential mechanism.

```powershell
..\.venv\Scripts\python scripts/manage.py --region eu-west-3 --stack webhook-router-dev configure-client --tenant demo --providers workflow,vapi
```

Copy [examples/route.json](../examples/route.json) to a working file, replace its endpoint with the approved HTTPS destination, and keep its tenant and event type aligned with your producer. The example domain is a placeholder, not a deployed receiver. Do not put credentials in the file. Optional destination authentication uses a Secrets Manager ARN.

Publish the route using a matching sample:

```powershell
..\.venv\Scripts\python scripts/manage.py --region eu-west-3 --stack webhook-router-dev put-route --file examples/route.json --sample examples/workflow.json
```

The command above uses the example path; use your working file path if you made a copy. The stack allowlist must contain the route's exact hostname. For Vapi, repeat with the Vapi route/sample after changing its endpoint. API Gateway usage-plan changes may take minutes to propagate.

## 5. Submit a synthetic event

For PowerShell 7+, set the actual `WebhookUrl`, then read the token without echoing it:

```powershell
$webhookUrl = 'https://YOUR_API_ID.execute-api.eu-west-3.amazonaws.com/dev/webhooks'
$routerToken = Read-Host 'Provider bearer token' -MaskInput
$requestHeaders = @{ Authorization = "Bearer $routerToken" }
try {
    $body = Get-Content -LiteralPath examples/workflow.json -Raw
    Invoke-RestMethod -Method Post -Uri $webhookUrl -ContentType 'application/json' -Headers $requestHeaders -Body $body
} finally {
    Remove-Variable routerToken, requestHeaders -ErrorAction SilentlyContinue
}
```

This avoids putting a literal token in saved command history. The token still exists transiently in process memory; do not enable shell tracing or print the request headers.

Expected first acknowledgement:

```json
{"accepted":true,"duplicate":false,"event_id":"workflow-run-001"}
```

HTTP status is `202`. Sending the same body and ID again returns `200` with `duplicate:true` and the current event status. Changing the content but reusing that ID returns `409`; use a new ID for a genuinely different event, not for retrying a failed acknowledgement.

## 6. Confirm delivery and prepare promotion

Verify the event record reaches `DELIVERED`, the destination received the expected projection, and the receiver recorded one business effect for the idempotency key. The public API does not expose event-status polling; authorized operators inspect the event table/logs. See the [data-model reference](data-model.md#locating-an-event).

Check the dashboard, empty failure queues, actual access logs and SNS delivery. Then complete [staging acceptance](acceptance.md). A successful `202`, SAM build, or stack creation alone does not establish production readiness.

For errors, use [troubleshooting](troubleshooting.md) before retrying deployment or changing credentials.
