"""Verify the Phase 2 development environment end to end.

Checks the docker-compose services (Kafka, Prometheus, Grafana, MLflow) and the
existing host services (Redis, MSSQL, Elasticsearch). Prints a status table and
exits non-zero if a CRITICAL service is unreachable.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import requests  # noqa: E402
from wids.config import settings  # noqa: E402

requests.packages.urllib3.disable_warnings()  # type: ignore

results = []  # (service, status, detail, critical)


def record(service, ok, detail, critical=True, warn=False):
    status = "WARN" if warn else ("PASS" if ok else "FAIL")
    results.append((service, status, detail, critical))


def check_kafka():
    try:
        from wids.connections import get_kafka_admin
        admin = get_kafka_admin()
        topics = sorted(t for t in admin.list_topics() if not t.startswith("__"))
        record("Kafka", True, f"{settings.kafka_bootstrap} · topics: {', '.join(topics) or '(none yet)'}")
    except Exception as e:
        record("Kafka", False, f"{settings.kafka_bootstrap} · {e}")


def check_redis():
    try:
        from wids.connections import get_redis
        r = get_redis()
        pong = r.ping()
        info = r.info("server")
        record("Redis", bool(pong), f"{settings.redis_url} · v{info.get('redis_version','?')}")
    except Exception as e:
        record("Redis", False, f"{settings.redis_url} · {e}")


def check_mssql():
    try:
        from wids.connections import get_mssql
        conn = get_mssql(database="master")
        cur = conn.cursor()
        cur.execute("SELECT SERVERPROPERTY('ProductVersion'), SERVERPROPERTY('Edition')")
        ver, edition = cur.fetchone()
        # ensure the 'wids' database exists (best effort)
        cur.execute("SELECT database_id FROM sys.databases WHERE name = ?", settings.mssql_database)
        exists = cur.fetchone() is not None
        db = settings.mssql_database
        note = f"{db} DB present" if exists else f"{db} DB missing"
        if not exists:
            try:
                conn.autocommit = True
                cur.execute(f"CREATE DATABASE [{db}]")
                note = f"{db} DB created"
            except Exception as ce:
                note = f"{db} DB missing (create failed: {ce})"
        record("MSSQL", True, f"{settings.mssql_server} · {edition} {ver} · {note}")
        conn.close()
    except Exception as e:
        record("MSSQL", False, f"{settings.mssql_server} · {e}")


def check_es():
    try:
        from wids.connections import get_es
        es = get_es()
        info = es.info()
        health = es.cluster.health()
        ver = info["version"]["number"]
        detail = f"{settings.es_url} · v{ver} · health={health.get('status')} · prefix='{settings.es_index_prefix}'"
        record("Elasticsearch", True, detail)
    except Exception as e:
        msg = str(e)
        # No credentials is a configuration gap, not a hard failure for Phase 2.
        warn = ("401" in msg or "authentication" in msg.lower() or not settings.es_password)
        record("Elasticsearch", False, f"{settings.es_url} · {msg[:120]}"
               + (" (set WIDS_ES_PASSWORD in .env)" if warn else ""),
               critical=False, warn=warn)


def check_http(name, url, path, critical=True):
    try:
        r = requests.get(url + path, timeout=5, verify=False)
        ok = r.status_code < 500
        record(name, ok, f"{url} · HTTP {r.status_code}", critical=critical)
    except Exception as e:
        record(name, False, f"{url} · {e}", critical=critical)


def main() -> int:
    check_kafka()
    check_redis()
    check_mssql()
    check_es()
    check_http("Prometheus", settings.prometheus_url, "/-/ready")
    check_http("Grafana", settings.grafana_url, "/api/health")
    check_http("MLflow", settings.mlflow_url, "/health", critical=False)

    print("\n  Wireless IDS — environment verification")
    print("  " + "-" * 78)
    print(f"  {'SERVICE':<16}{'STATUS':<8}DETAIL")
    print("  " + "-" * 78)
    for service, status, detail, _ in results:
        print(f"  {service:<16}{status:<8}{detail}")
    print("  " + "-" * 78)

    failed = [r for r in results if r[1] == "FAIL" and r[3]]
    warned = [r for r in results if r[1] in ("FAIL", "WARN") and not r[3]]
    if failed:
        print(f"\n  {len(failed)} critical service(s) unreachable: "
              + ", ".join(r[0] for r in failed))
        return 1
    if warned:
        print(f"\n  OK (with {len(warned)} non-critical warning(s): "
              + ", ".join(r[0] for r in warned) + ")")
    else:
        print("\n  All services reachable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
