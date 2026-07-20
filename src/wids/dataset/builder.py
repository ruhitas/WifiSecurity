"""Build a labeled, unified feature dataset."""
from __future__ import annotations

import csv
import json
import time
from collections import Counter
from itertools import islice
from pathlib import Path

from ..sensors.frames import SyntheticFrameSource
from ..streaming.features import compute_features, feature_names

# (label, attack_scenario_or_None) — normal + generated multi-class attacks
DEFAULT_CLASSES = [
    ("normal", None),
    ("deauth_flood", "deauth_flood"),
    ("disassoc_flood", "disassoc_flood"),
    ("auth_flood", "auth_flood"),
    ("probe_flood", "probe_flood"),
    ("beacon_flood", "beacon_flood"),
]

META_COLS = ["label", "source", "window_index", "feature_set_ver"]


class DatasetBuilder:
    def __init__(self, window_size: int = 60, seed: int = 100):
        self.window_size = window_size
        self.seed = seed
        self.rows: list[dict] = []

    def _window_rows(self, label, source_iter_factory, n_windows, source_tag):
        for i in range(n_windows):
            src = source_iter_factory(i)
            frames = list(islice(src.iterate(), self.window_size))
            feats = compute_features(frames)
            feats["label"] = label
            feats["source"] = source_tag
            feats["window_index"] = i
            self.rows.append(feats)

    def add_generated(self, classes=DEFAULT_CLASSES, n_windows: int = 80, channel: int = 6):
        """Generate synthetic normal + attack windows for each class."""
        for label, attack in classes:
            base = self.seed + hash(label) % 1000

            def factory(i, attack=attack, base=base, channel=channel):
                return SyntheticFrameSource(channel=channel, seed=base + i, attack=attack)

            tag = "synthetic" if attack is None else "generated"
            self._window_rows(label, factory, n_windows, tag)
        return self

    def add_pcap(self, path: str, label: str, n_windows: int | None = None):
        """Ingest a capture file (e.g. AWID3) as windows of the given label.

        Requires scapy (Phase 4). Windows are cut sequentially from the file.
        """
        from ..sensors.capture import PcapReplaySource
        reader = PcapReplaySource(path)
        it = reader.iterate()
        i = 0
        while n_windows is None or i < n_windows:
            frames = list(islice(it, self.window_size))
            if len(frames) < self.window_size:
                break
            feats = compute_features(frames)
            feats["label"] = label
            feats["source"] = "pcap"
            feats["window_index"] = i
            self.rows.append(feats)
            i += 1
        return self

    # -- output ------------------------------------------------------------
    def columns(self) -> list[str]:
        return META_COLS + feature_names()

    def write_csv(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        cols = self.columns()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for row in self.rows:
                w.writerow(row)
        return path

    def write_manifest(self, csv_path: str | Path, created_ts: float | None = None) -> Path:
        csv_path = Path(csv_path)
        manifest = {
            "csv": csv_path.name,
            "created_utc": created_ts if created_ts is not None else time.time(),
            "n_rows": len(self.rows),
            "n_features": len(feature_names()),
            "window_size": self.window_size,
            "feature_set_ver": self.rows[0]["feature_set_ver"] if self.rows else None,
            "class_distribution": dict(Counter(r["label"] for r in self.rows)),
            "source_distribution": dict(Counter(r["source"] for r in self.rows)),
        }
        mpath = csv_path.with_suffix(".manifest.json")
        mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return mpath

    def summary(self) -> dict:
        return {
            "rows": len(self.rows),
            "features": len(feature_names()),
            "classes": dict(Counter(r["label"] for r in self.rows)),
        }
