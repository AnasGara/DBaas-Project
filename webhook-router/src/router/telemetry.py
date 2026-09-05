import json
import os
import time

try:
    import resource
except ImportError:  # Windows local development; Lambda runs on Linux.
    resource = None


def log(action, **fields):
    # Deliberately exclude body, credentials, destination URLs and exception messages.
    print(json.dumps({"action": action, **fields}, separators=(",", ":")))


def metric(name, value=1, unit="Count"):
    print(
        json.dumps(
            {
                "_aws": {
                    "Timestamp": int(time.time() * 1000),
                    "CloudWatchMetrics": [
                        {
                            "Namespace": "WebhookRouter",
                            "Dimensions": [["Application", "Environment", "Service"]],
                            "Metrics": [{"Name": name, "Unit": unit}],
                        }
                    ],
                },
                "Application": os.environ.get("APPLICATION_NAME", "webhook-router"),
                "Environment": os.environ.get("ENVIRONMENT", "dev"),
                "Service": os.environ.get("SERVICE", "unknown"),
                name: value,
            },
            separators=(",", ":"),
        )
    )


def memory_metric():
    # Linux ru_maxrss is KiB; this is process peak RSS, not an AWS/Lambda native metric.
    if resource is None:
        return
    allocated = int(os.environ.get("AWS_LAMBDA_FUNCTION_MEMORY_SIZE", "512"))
    metric(
        "MemoryUtilization",
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / allocated * 100,
        "Percent",
    )
