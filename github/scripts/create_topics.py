"""Create the platform's core Kafka topics (idempotent).

Topics follow the SAD data-plane contracts (section 5.2 / 8.1).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kafka.admin import NewTopic  # noqa: E402
from kafka.errors import TopicAlreadyExistsError  # noqa: E402
from wids.connections import get_kafka_admin  # noqa: E402

TOPICS = [
    ("wids.raw-frames", 6),
    ("wids.feature-vectors", 6),
    ("wids.detections", 3),
    ("wids.responses", 1),
    ("wids.audit", 1),
]


def main() -> int:
    admin = get_kafka_admin()
    existing = set(admin.list_topics())
    to_create = [
        NewTopic(name=n, num_partitions=p, replication_factor=1)
        for n, p in TOPICS
        if n not in existing
    ]
    if not to_create:
        print("All topics already exist:", ", ".join(n for n, _ in TOPICS))
        return 0
    try:
        admin.create_topics(new_topics=to_create, validate_only=False)
    except TopicAlreadyExistsError:
        pass
    print("Created topics:", ", ".join(t.name for t in to_create))
    print("All topics:", ", ".join(sorted(set(admin.list_topics()))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
