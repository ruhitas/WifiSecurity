"""Connection helpers for the platform's data services.

These wrap the existing host services (Redis, MSSQL, Elasticsearch) and the
docker-compose Kafka broker with the settings from :mod:`wids.config`.
"""
from __future__ import annotations

from .config import settings


def get_redis():
    import redis
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def get_mssql(database: str | None = None):
    """Return a live pyodbc connection to MSSQL (SQLEXPRESS)."""
    import pyodbc
    return pyodbc.connect(settings.mssql_connection_string(database), timeout=5)


def get_es():
    """Return an Elasticsearch client for the shared ES 9.x node.

    All platform indices use the ``wids-`` prefix (see settings.es_index).
    """
    from elasticsearch import Elasticsearch
    import warnings
    if not settings.es_verify_certs:
        try:  # silence self-signed cert warnings in dev
            from urllib3.exceptions import InsecureRequestWarning
            warnings.simplefilter("ignore", InsecureRequestWarning)
        except Exception:
            pass
    auth = None
    if settings.es_password:
        auth = (settings.es_username, settings.es_password)
    return Elasticsearch(
        settings.es_url,
        basic_auth=auth,
        verify_certs=settings.es_verify_certs,
        request_timeout=5,
    )


def get_kafka_admin():
    from kafka.admin import KafkaAdminClient
    return KafkaAdminClient(
        bootstrap_servers=settings.kafka_bootstrap,
        client_id="wids-admin",
        request_timeout_ms=5000,
    )


def get_kafka_producer():
    from kafka import KafkaProducer
    import json
    return KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )


def get_rabbitmq():
    """Blocking connection to the existing RabbitMQ broker."""
    import pika
    creds = pika.PlainCredentials(settings.rabbitmq_user, settings.rabbitmq_password)
    params = pika.ConnectionParameters(
        host=settings.rabbitmq_host, port=settings.rabbitmq_port,
        credentials=creds, connection_attempts=1, socket_timeout=2,
        blocked_connection_timeout=2,
    )
    return pika.BlockingConnection(params)
