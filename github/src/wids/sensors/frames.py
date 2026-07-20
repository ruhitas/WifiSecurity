"""Frame model and frame sources.

A *frame source* is any iterable yielding raw-frame dicts. Phase 3 ships a
SyntheticFrameSource so the multi-sensor pipeline can be exercised end to end;
Phase 4 adds a real 802.11 capture source with the same interface.
"""
from __future__ import annotations

import random
import time
from typing import Iterator

# attack scenarios: bias the window toward a flooded subtype
ATTACK_SUBTYPE = {
    "deauth_flood": ("mgmt", "deauth"),
    "disassoc_flood": ("mgmt", "disassoc"),
    "auth_flood": ("mgmt", "auth"),
    "assoc_flood": ("mgmt", "assoc_req"),
    "probe_flood": ("mgmt", "probe_req"),
    "beacon_flood": ("mgmt", "beacon"),
}

# 802.11 frame type/subtype samples (type.subtype names)
_SUBTYPES = [
    ("mgmt", "beacon"), ("mgmt", "probe_req"), ("mgmt", "probe_resp"),
    ("mgmt", "auth"), ("mgmt", "assoc_req"), ("mgmt", "deauth"),
    ("ctrl", "rts"), ("ctrl", "cts"), ("ctrl", "ack"),
    ("data", "qos_data"), ("data", "null"),
]


def _mac(rng: random.Random) -> str:
    return ":".join(f"{rng.randint(0, 255):02x}" for _ in range(6))


class FrameSource:
    """Base interface: iterate() yields raw-frame dicts (without sensor tags)."""

    source_name = "base"

    def iterate(self) -> Iterator[dict]:  # pragma: no cover - interface
        raise NotImplementedError


class SyntheticFrameSource(FrameSource):
    """Emit plausible 802.11 frame metadata for pipeline testing (NOT capture).

    Marked source='synthetic' so downstream consumers never mistake it for real
    captured traffic. Replace with the Phase 4 capture source for live data.
    """

    source_name = "synthetic"

    def __init__(self, channel: int = 6, seed: int | None = None,
                 attack: str | None = None):
        self.channel = channel
        self._rng = random.Random(seed)
        # attack scenario: currently 'deauth_flood' (biases toward deauth frames)
        self.attack = attack
        # a small, stable set of BSSIDs/stations so graphs look realistic later
        self._bssids = [_mac(self._rng) for _ in range(3)]
        self._stations = [_mac(self._rng) for _ in range(8)]

    def iterate(self) -> Iterator[dict]:
        rng = self._rng
        seq = 0
        while True:
            seq += 1
            if self.attack in ATTACK_SUBTYPE and rng.random() < 0.9:
                ftype, subtype = ATTACK_SUBTYPE[self.attack]
            else:
                ftype, subtype = rng.choice(_SUBTYPES)
            bssid = rng.choice(self._bssids)
            src = rng.choice(self._stations + self._bssids)
            dst = rng.choice(self._stations + ["ff:ff:ff:ff:ff:ff"])
            yield {
                "seq": seq,
                "ts": time.time(),
                "channel": self.channel,
                "type": ftype,
                "subtype": subtype,
                "src": src,
                "dst": dst,
                "bssid": bssid,
                "rssi": rng.randint(-90, -30),
                "length": rng.randint(40, 1500),
                "retry": rng.random() < 0.08,
                "source": self.source_name,
            }
