import os
from functools import lru_cache

import boto3
from botocore.config import Config

MAX_PAYLOAD_BYTES = 65536
MAX_ROUTE_BYTES = 16384
LEASE_SECONDS = 60
SHARD_COUNT = 16
SDK_CONFIG = Config(
    connect_timeout=2, read_timeout=3, retries={"mode": "standard", "total_max_attempts": 2}
)


@lru_cache
def client(service):
    return boto3.client(service, config=SDK_CONFIG)


@lru_cache
def table(name):
    return boto3.resource("dynamodb", config=SDK_CONFIG).Table(os.environ[name])


def reset_clients():
    client.cache_clear()
    table.cache_clear()
