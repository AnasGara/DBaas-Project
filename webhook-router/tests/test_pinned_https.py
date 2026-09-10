import json
import socket

import boto3
import pytest

from router import transport
from router.errors import ConfigurationError, DeliveryError


def test_connect_uses_checked_ip_but_original_tls_hostname(monkeypatch):
    observed = {}

    class Socket:
        def settimeout(self, value):
            observed["timeout"] = value

        def connect(self, address):
            observed["address"] = address

        def close(self):
            observed["closed"] = True

    class TLS:
        @staticmethod
        def wrap_socket(sock, server_hostname):
            observed["sni"] = server_hostname
            return sock

    connection = transport.PinnedHTTPSConnection("hooks.example.com", timeout=5)
    connection._context = TLS()
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))],
    )
    monkeypatch.setattr(socket, "socket", lambda *a: Socket())
    connection.connect()
    assert observed["address"] == ("8.8.8.8", 443)
    assert observed["sni"] == "hooks.example.com"
    assert observed["timeout"] == 5
    connection.close()


def test_mixed_public_and_metadata_dns_fails_closed(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))
            for ip in ("8.8.8.8", "169.254.169.254")
        ],
    )
    with pytest.raises(ConfigurationError):
        transport.safe_addresses("hooks.example.com")


def test_connect_closes_failed_socket(monkeypatch):
    closed = []

    class Socket:
        def settimeout(self, value):
            pass

        def connect(self, address):
            raise OSError("connect failed")

        def close(self):
            closed.append(True)

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))],
    )
    monkeypatch.setattr(socket, "socket", lambda *a: Socket())
    with pytest.raises(DeliveryError):
        transport.PinnedHTTPSConnection("hooks.example.com", timeout=5).connect()
    assert closed == [True]


def test_destination_secret_is_scoped_and_provider_token_is_not_forwarded(monkeypatch):
    secret = boto3.client("secretsmanager").create_secret(
        Name="webhook-router/destinations/service",
        SecretString='{"bearer_token":"destination-only"}',
    )["ARN"]
    sent = []

    class Connection:
        def __init__(self, *a, **k):
            pass

        def request(self, *a, **k):
            sent.append(k)

        def getresponse(self):
            return type("Response", (), {"status": 204})()

        def close(self):
            pass

    monkeypatch.setattr(transport, "PinnedHTTPSConnection", Connection)
    item = {
        "pk": "acme#hash",
        "event_id": "id-1",
        "event_type": "workflow.trigger",
        "route_json": json.dumps(
            {"endpoint": "https://hooks.example.com/path", "auth_secret_arn": secret}
        ),
        "delivery_json": "{}",
    }
    transport.send(item)
    assert sent[0]["headers"]["Authorization"] == "Bearer destination-only"
    item["route_json"] = json.dumps(
        {
            "endpoint": "https://hooks.example.com/path",
            "auth_secret_arn": "arn:aws:secretsmanager:eu-west-3:123456789012:secret:unapproved",
        }
    )
    with pytest.raises(ConfigurationError):
        transport.send(item)
    assert len(sent) == 1
