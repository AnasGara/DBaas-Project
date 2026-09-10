import http.client
import ipaddress
import json
import os
import socket
import ssl
from urllib.parse import urlsplit

from router.config import client
from router.errors import ConfigurationError, DeliveryError
from router.validation import canonical


def endpoint_parts(endpoint):
    try:
        url = urlsplit(endpoint)
        allowed = {
            h.strip().lower()
            for h in os.environ.get("ALLOWED_DESTINATION_HOSTS", "").split(",")
            if h.strip()
        }
        if url.scheme != "https" or not url.hostname or url.hostname.lower() not in allowed:
            raise ConfigurationError("Destination must be HTTPS on an explicitly allowed host")
        if url.username or url.password or url.fragment or url.port not in (None, 443) or url.query:
            raise ConfigurationError(
                "Credentials, query strings, fragments and non-443 ports are forbidden"
            )
        if any(ord(c) < 33 or ord(c) > 126 for c in endpoint) or "\\" in endpoint:
            raise ConfigurationError("Invalid destination URL")
        return url
    except ValueError as exc:
        raise ConfigurationError("Invalid destination URL") from exc


def safe_addresses(host):
    networks = [
        ipaddress.ip_network(c.strip())
        for c in os.environ.get("ALLOWED_PRIVATE_CIDRS", "").split(",")
        if c.strip()
    ]
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses:
        raise DeliveryError("DNS returned no addresses")
    for _family, _socktype, _proto, _, address in addresses:
        ip = ipaddress.ip_address(address[0])
        if (
            ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or ip.is_reserved
        ):
            raise ConfigurationError("Forbidden destination address")
        if not ip.is_global and not any(ip in network for network in networks):
            raise ConfigurationError("Private destination requires an explicit allowed network")
    return addresses


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to a validated DNS result while retaining hostname TLS verification."""

    def connect(self):
        last_error = None
        for family, socktype, proto, _, address in safe_addresses(self.host):
            sock = socket.socket(family, socktype, proto)
            sock.settimeout(self.timeout)
            try:
                sock.connect(address)
                self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
                return
            except OSError as exc:
                sock.close()
                last_error = exc
        raise DeliveryError("Cannot establish destination connection") from last_error


def send(item):
    route = json.loads(item["route_json"])
    url = endpoint_parts(route["endpoint"])
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "WebhookRouter/1.0",
        "Idempotency-Key": item["pk"],
        "X-Webhook-Event-ID": item["event_id"],
        "X-Webhook-Event-Type": item["event_type"],
    }
    secret_arn = route.get("auth_secret_arn")
    if secret_arn:
        prefix = os.environ.get("DESTINATION_SECRET_PREFIX_ARN", "")
        if not prefix or not secret_arn.startswith(prefix):
            raise ConfigurationError("Destination secret is outside the permitted prefix")
        secret = json.loads(
            client("secretsmanager").get_secret_value(
                SecretId=secret_arn, VersionStage="AWSCURRENT"
            )["SecretString"]
        )
        bearer = secret.get("bearer_token")
        if (
            not isinstance(bearer, str)
            or not bearer
            or any(ord(c) < 33 or ord(c) > 126 for c in bearer)
        ):
            raise ConfigurationError("Invalid destination credential")
        headers["Authorization"] = "Bearer " + bearer
    body = item["delivery_json"].encode("utf-8")
    connection = PinnedHTTPSConnection(
        url.hostname, timeout=5, context=ssl.create_default_context()
    )
    try:
        connection.request("POST", url.path or "/", body=body, headers=headers)
        response = connection.getresponse()
        # Never follow redirects or log/read arbitrary destination response bodies.
        if not 200 <= response.status < 300:
            raise DeliveryError("Downstream returned a non-success status")
    finally:
        connection.close()


def validate_route_endpoint(route):
    endpoint_parts(route["endpoint"])
    secret_arn = route.get("auth_secret_arn")
    prefix = os.environ.get("DESTINATION_SECRET_PREFIX_ARN", "")
    if secret_arn and (not prefix or not secret_arn.startswith(prefix)):
        raise ConfigurationError("Destination secret is outside the permitted prefix")
    canonical(route)
