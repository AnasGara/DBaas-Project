# Production acceptance gate

Local verification is not proof of deployed readiness. Run these gates in staging and retain evidence before production promotion:

| Gate | Expected evidence |
|---|---|
| Deploy/logging | Correct account/region, successful changeset, access logs without Authorization/body |
| Authentication | Wrong/missing token rejected; disabled/rotated token rejected; valid tenant accepted |
| Isolation | Vapi-only token cannot submit workflows; a tenant cannot select another tenant's routes |
| Validation | Invalid JSON/schema, duplicate keys, oversized data and synchronous Vapi events rejected without state writes |
| Dynamic routing | No code redeploy needed; new events use version 2; accepted events retain version 1 |
| Deduplication | Identical retry acknowledged; one accepted record; conflicting content returns 409 |
| Ambiguous delivery | Receiver commits, response is lost, retry with same key produces no second business effect |
| Outages | Destination outage causes retries/DLQ; repair/replay works; disabled stream is recovered through outbox reconciliation |
| Network | Metadata/redirect/unapproved/private destinations blocked; explicitly approved VPC destination reachable |
| Notifications | Forced native-error, application-error, API4XX and DLQ alarms arrive through confirmed SNS subscription |
| Performance | Actual cold/warm p50/p95, acceptance/429 rates, message age and delivery lag under expected burst load |
| Recovery/cost | PITR and retention-aware replay practiced; owner and response time documented; cost projection approved |

Opt-in probe (synthetic requests, billable AWS usage):

```powershell
python scripts/load_test.py --url https://<api-id>.execute-api.eu-west-3.amazonaws.com/staging/webhooks --events 100 --concurrency 10 --p95-target-ms 200
```

Configure a safe test destination with workflow_id/customer_id fields; never load-test a real business workflow. The token is read with a hidden prompt. The probe measures client p50/p95, acceptance and duplicate acknowledgements; CloudWatch and receiver records are needed to verify delivery effects/alarms. It exits nonzero on failed acceptance, deduplication or latency target. It has not been run against AWS by this task.

The 70% integration-time reduction requires a measured baseline study. No such improvement, sustained sub-200ms latency, deployment, uptime or production certification is fabricated here.
