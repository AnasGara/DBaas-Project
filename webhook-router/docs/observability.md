# Observability reference

The SAM stack creates per-function CloudWatch log groups, an API access log group, an operational dashboard, alarms and an SNS topic. Functions emit JSON logs and custom Embedded Metric Format records; runtime roles do not need direct `PutMetricData` permission for this log-based mechanism. See [template.yaml](../template.yaml) and [telemetry.py](../src/router/telemetry.py).

## Dashboard

Dashboard name: `<ApplicationName>-<Environment>`. It contains six widgets:

1. API request traffic and 4xx/5xx counts over five-minute periods.
2. API Gateway `IntegrationLatency` at p95, in milliseconds.
3. Worker delivered, failed and duplicate outcomes.
4. Custom process peak memory utilization for ingestion and worker functions.
5. Delivery queue and outbox age in seconds.
6. Delivery DLQ and stream-failure queue visible-message counts.

Gateway integration latency excludes time before Gateway invokes the backend, such as authorizer work; it is not client-observed request latency. Compare it with the external load probe and Lambda `IngestionLatency`. Downstream completion lag is a different measure again.

## Custom metrics

Namespace: `WebhookRouter`. Every series has `Application`, `Environment` and `Service` dimensions. Use all three to avoid combining environments or applications.

| Metric | Service | Unit | Interpretation |
|---|---|---|---|
| `Accepted` | ingest | Count | Newly accepted transaction |
| `Duplicates` | ingest | Count | Matching existing event acknowledged |
| `Conflicts` | ingest | Count | Existing ID has different content |
| `ValidationFailures` | ingest | Count | Invalid event, missing/disabled route, schema or projection rejection |
| `ConfigurationFailures` | ingest | Count | Route configuration cannot be used |
| `IngestionFailures` | ingest | Count | Other caught ingestion dependency/runtime failure |
| `IngestionLatency` | ingest | Milliseconds | Handler execution through response construction/final telemetry |
| `Enqueued` | dispatch | Count | Successful queue send followed by outbox deletion |
| `DispatchFailures` | dispatch | Count | Failed stream publication or reconciliation attempt |
| `OutboxAge` | dispatch | Seconds | Oldest due item observed during that reconciliation run; zero when none observed |
| `DeliveryAttempts` | worker | Count | Successful lease acquisitions followed by delivery execution |
| `Delivered` | worker | Count | Downstream success recorded in the event table |
| `DeliveryFailures` | worker | Count | Exception during send or completion-state update |
| `DeliveryDuplicates` | worker | Count | Queue references already marked delivered |
| `MemoryUtilization` | ingest, worker | Percent | Linux process peak resident memory / configured Lambda memory |

The memory series is custom, not a native `AWS/Lambda` metric and not the Lambda Insights extension metric. It is a process-lifetime peak in a reused execution environment, not instantaneous memory for each event. Local Windows runs skip this measurement; tests emulate its calculation.

Metrics are emitted on their code paths, not as a full set of zero-valued counters on every invocation. Not every rejected request emits a dedicated application counter: some auth/content/scope checks return before those counters. Gateway status metrics are the broader view of incoming failures. Missing telemetry must be interpreted with the source's expected activity.

## Alarm definitions

All thresholds below come from the checked-in template. Alarms send notifications to `AlarmTopic`; an email recipient must confirm the SNS subscription.

| Logical ID | Condition | Evaluation | Missing data |
|---|---|---|---|
| `LambdaErrorRateAlarm` | Combined native errors / invocations across four functions >1% | One 300s period | Not breaching |
| `DeliveryFailureRateAlarm` | Application delivery failures / attempts >1% | One 300s period | Not breaching |
| `Api4xxRateAlarm` | Gateway 4xx / request count >5%, only if at least 20 requests | One 300s period | Not breaching |
| `Api5xxAlarm` | Gateway 5xx count >0 | One 300s period | Not breaching |
| `DeliveryDLQAlarm` | Delivery DLQ visible messages >0 | One 60s period | Not breaching |
| `StreamFailureAlarm` | Stream-failure queue visible messages >0 | One 60s period | Not breaching |
| `BacklogAgeAlarm` | Oldest delivery message >120s | Three 60s periods | Not breaching |
| `OutboxAgeAlarm` | Observed outbox age >120s | Three 60s periods | **Breaching** |
| `IngestionLatencyAlarm` | Ingestion p95 >200ms | Three 300s periods; low-sample percentile evaluation ignored | Not breaching |

Native Lambda `Errors` does not capture a caught error returned as an HTTP 503 or a successful Lambda invocation returning partial batch failures. That is why Gateway 5xx and application delivery failure alarms are separate. Authorizer rejection throws an error and can contribute to the native error-rate alarm.

The API request denominator uses `Count` with `SampleCount`; 4xx counts use `Sum`. A small number of failures can trigger the Lambda/application percentage alarms because those do not have the API alarm's minimum-traffic guard.

These alarms are not an exhaustive observability policy. Dedicated alarms for Lambda throttles, DynamoDB throttles, stream iterator age, authentication-secret failures or memory pressure are not created by the current template. Add them through a reviewed infrastructure change when the deployment's operational policy requires them. Retaining this distinction avoids assuming a dashboard metric is automatically alarmed.

## Logs and correlation

Application records contain `action` plus minimal safe fields. Examples:

```jsonl
{"action":"event_accepted","event_key":"demo#<hash>","request_id":"<gateway-request-id>"}
{"action":"event_delivered","event_key":"demo#<hash>"}
{"action":"delivery_failed","event_key":"demo#<hash>","error_type":"TimeoutError"}
```

Access logs contain request ID, status, integration latency and source IP. They exclude Authorization and payload tracing. Function groups use `/aws/lambda/<ApplicationName>-<Environment>-<service>`; the authorizer's function suffix is `authorize`. The access log group's physical name is generated; find it through stack resources.

In CloudWatch Logs Insights, select the intended environment's ingestion and worker groups. Replace the example event key:

```text
fields @timestamp, action, event_key, request_id, error_type
| filter event_key = "demo#REPLACE_WITH_64_CHARACTER_HASH"
| sort @timestamp asc
| limit 100
```

For exception-class trends in the selected function groups:

```text
filter ispresent(error_type)
| stats count(*) as occurrences by action, error_type
| sort occurrences desc
```

For Gateway status distribution, select its access log group:

```text
fields status
| stats count(*) as requests by status
| sort requests desc
```

The queries inspect metadata rather than raw event bodies. A request rejected before ingestion may have no event key; start with Gateway request ID/status. Replay produces the same event key, which lets operators correlate earlier failures with later delivery.

## Operational evidence

After deployment, confirm actual log delivery, custom metric dimensions, dashboard data and SNS receipt with synthetic traffic. An empty chart is not proof of a healthy pipeline. The [runbook](runbook.md#alarm-triage) describes incident actions; [acceptance](acceptance.md) defines evidence required for promotion. No deployed dashboards, notifications or latency were verified by the recorded local test run.
