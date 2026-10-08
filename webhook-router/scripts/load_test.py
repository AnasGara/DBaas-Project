"""Opt-in deployed-environment acceptance probe. Uses synthetic data; may incur AWS charges."""

import argparse
import concurrent.futures
import getpass
import json
import re
import statistics
import time
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def validate_url(value):
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or not url.hostname
        or not re.fullmatch(r"[a-z0-9]+\.execute-api\.[a-z0-9-]+\.amazonaws\.com", url.hostname)
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.port not in (None, 443)
    ):
        raise ValueError(
            "Use an HTTPS execute-api endpoint without credentials or query parameters"
        )


def run(url, token, event_id):
    validate_url(url)
    data = json.dumps(
        {
            "id": event_id,
            "type": "workflow.trigger",
            "data": {"workflow_id": "acceptance-probe", "customer_id": "synthetic"},
        }
    ).encode()
    request = urllib.request.Request(  # noqa: S310 - HTTPS execute-api host checked above.
        url,
        data=data,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            status = response.status
            body = json.loads(response.read(4096))
    except urllib.error.HTTPError as exc:
        status, body = exc.code, {}
    except (urllib.error.URLError, TimeoutError):
        status, body = 0, {}
    return {
        "status": status,
        "latency_ms": (time.perf_counter() - started) * 1000,
        "duplicate": body.get("duplicate"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--events", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--p95-target-ms", type=float, default=200)
    args = parser.parse_args()
    try:
        validate_url(args.url)
    except ValueError as exc:
        parser.error(str(exc))
    if not 2 <= args.events <= 10000 or not 1 <= args.concurrency <= 100:
        parser.error("Use 2–10000 events and concurrency 1–100")
    token = getpass.getpass("Provider bearer token (not printed): ")
    prefix = "probe-" + str(uuid.uuid4())
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(
            pool.map(lambda i: run(args.url, token, f"{prefix}-{i}"), range(args.events))
        )
    duplicate = run(args.url, token, f"{prefix}-0")
    latencies = sorted(r["latency_ms"] for r in results)
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
    failures = sum(r["status"] != 202 for r in results)
    print(
        json.dumps(
            {
                "events": len(results),
                "failed_acceptances": failures,
                "p50_ms": statistics.median(latencies),
                "p95_ms": p95,
                "duplicate_status": duplicate["status"],
                "deduplicated": duplicate["duplicate"],
                "target_met": p95 < args.p95_target_ms,
            },
            indent=2,
        )
    )
    if (
        failures
        or duplicate["status"] != 200
        or duplicate["duplicate"] is not True
        or p95 >= args.p95_target_ms
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
