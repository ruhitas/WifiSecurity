"""Centralised configuration loaded from environment / .env.

All settings have sensible local-development defaults matching the existing
host services on this machine (MSSQL SQLEXPRESS, Redis on 6379, Elasticsearch
9.1.4 on 9200) and the docker-compose infrastructure (Kafka, MLflow, etc.).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
    # Load .env from the project root if present.
    _root = Path(__file__).resolve().parents[2]
    load_dotenv(_root / ".env")
except Exception:  # dotenv optional
    pass


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Kafka (docker-compose)
    kafka_bootstrap: str = os.getenv("WIDS_KAFKA_BOOTSTRAP", "localhost:29092")

    # Redis (existing host service)
    redis_url: str = os.getenv("WIDS_REDIS_URL", "redis://localhost:6379/0")

    # MSSQL (existing host service — SQL Server 2019 Express)
    mssql_driver: str = os.getenv("WIDS_MSSQL_DRIVER", "ODBC Driver 18 for SQL Server")
    mssql_server: str = os.getenv("WIDS_MSSQL_SERVER", r"localhost\SQLEXPRESS")
    mssql_database: str = os.getenv("WIDS_MSSQL_DATABASE", "wids")
    mssql_user: str = os.getenv("WIDS_MSSQL_USER", "")
    mssql_password: str = os.getenv("WIDS_MSSQL_PASSWORD", "")
    mssql_encrypt: str = os.getenv("WIDS_MSSQL_ENCRYPT", "no")
    mssql_trust_cert: str = os.getenv("WIDS_MSSQL_TRUST_CERT", "yes")

    # Elasticsearch (existing host service — ES 9.1.4, shared node)
    es_url: str = os.getenv("WIDS_ES_URL", "https://localhost:9200")
    es_username: str = os.getenv("WIDS_ES_USERNAME", "elastic")
    es_password: str = os.getenv("WIDS_ES_PASSWORD", "")
    es_verify_certs: bool = field(default_factory=lambda: _b("WIDS_ES_VERIFY_CERTS", False))
    es_index_prefix: str = os.getenv("WIDS_ES_INDEX_PREFIX", "wids-")

    # Observability / MLOps (docker-compose)
    prometheus_url: str = os.getenv("WIDS_PROMETHEUS_URL", "http://localhost:9090")
    grafana_url: str = os.getenv("WIDS_GRAFANA_URL", "http://localhost:3000")
    mlflow_url: str = os.getenv("WIDS_MLFLOW_URL", "http://localhost:5000")

    # RabbitMQ (existing host service) — notification / response-out path
    rabbitmq_host: str = os.getenv("WIDS_RABBITMQ_HOST", "localhost")
    rabbitmq_port: int = int(os.getenv("WIDS_RABBITMQ_PORT", "5672"))
    rabbitmq_user: str = os.getenv("WIDS_RABBITMQ_USER", "admin")
    rabbitmq_password: str = os.getenv("WIDS_RABBITMQ_PASSWORD", "")
    rabbitmq_notify_queue: str = os.getenv("WIDS_RABBITMQ_NOTIFY_QUEUE", "wids.notifications")

    def mssql_connection_string(self, database: str | None = None) -> str:
        db = database or self.mssql_database
        parts = [
            f"DRIVER={{{self.mssql_driver}}}",
            f"SERVER={self.mssql_server}",
            f"DATABASE={db}",
            f"Encrypt={self.mssql_encrypt}",
            f"TrustServerCertificate={self.mssql_trust_cert}",
        ]
        if self.mssql_user:
            parts.append(f"UID={self.mssql_user}")
            parts.append(f"PWD={self.mssql_password}")
        else:
            parts.append("Trusted_Connection=yes")
        return ";".join(parts) + ";"

    def es_index(self, name: str) -> str:
        return f"{self.es_index_prefix}{name}"


settings = Settings()
