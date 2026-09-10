import json
import socket

import pytest

from router import transport
from router.errors import ConfigurationError, DeliveryError


@pytest.mark.parametrize(
    "url",
    [
        "http://hooks.example.com/",
        "https://evil.example/",
        "https://user:password@hooks.example.com/",
        "https://hooks.example.com:444/",
        "https://hooks.example.com/#fragment",
        "https://hooks.example.com/?token=secret",
        "https://hooks.example.com/\r\nInjected:yes",
    ],
)
def test_endpoint_allowlist_and_url_guards(url):
    with pytest.raises(ConfigurationError):
        transport.endpoint_parts(url)


@pytest.mark.parametrize("address", ["127.0.0.1", "169.254.169.254", "10.0.0.1", "::1", "0.0.0.0"])
def test_dns_cannot_escape_allowed_public_network(monkeypatch, address):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))],
    )
    with pytest.raises(ConfigurationError):
        transport.safe_addresses("hooks.example.com")


def test_private_routing_requires_explicit_network(monkeypatch):
    monkeypatch.setenv("ALLOWED_PRIVATE_CIDRS", "10.20.0.0/16")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.20.1.2", 443))],
    )
    assert transport.safe_addresses("hooks.example.com")


def test_stable_idempotency_headers_no_redirects(monkeypatch):
    sent = []

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            sent.append(kwargs)

        def getresponse(self):
            return type("Response", (), {"status": 302})()

        def close(self):
            pass

    monkeypatch.setattr(transport, "PinnedHTTPSConnection", FakeConnection)
    item = {
        "pk": "acme#hash",
        "event_id": "event-1",
        "event_type": "workflow.trigger",
        "route_json": json.dumps({"endpoint": "https://hooks.example.com/"}),
        "delivery_json": "{}",
    }
    with pytest.raises(DeliveryError):
        transport.send(item)
    assert sent[0]["headers"]["Idempotency-Key"] == "acme#hash"
    assert "Authorization" not in sent[0]["headers"]
