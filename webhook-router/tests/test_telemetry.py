import json

from router import telemetry


def test_memory_metric_is_explicit_process_peak_not_native_lambda_metric(monkeypatch, capsys):
    class Resource:
        RUSAGE_SELF = 0

        @staticmethod
        def getrusage(who):
            return type("Usage", (), {"ru_maxrss": 128 * 1024})()

    monkeypatch.setattr(telemetry, "resource", Resource)
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_MEMORY_SIZE", "512")
    telemetry.memory_metric()
    result = json.loads(capsys.readouterr().out)
    assert result["MemoryUtilization"] == 25
    assert result["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "WebhookRouter"
