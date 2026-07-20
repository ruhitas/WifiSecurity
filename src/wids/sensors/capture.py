"""802.11 packet-capture sources (Phase 4).

Two frame sources implement the same interface as the synthetic source, so a
SensorAgent can stream real traffic with no other change:

* ``CaptureFrameSource`` — live monitor-mode capture (needs a monitor-capable
  NIC + Npcap/libpcap). Used on real sensor hardware.
* ``PcapReplaySource`` — replay 802.11 frames from a .pcap/.pcapng file (e.g.
  AWID3 captures, Phase 7), giving a hardware-independent, deterministic source.

Both parse frames into the platform's raw-frame schema using Scapy's Dot11
dissection.
"""
from __future__ import annotations

import queue
import time
from typing import Iterator, Optional

from .frames import FrameSource

_TYPE = {0: "mgmt", 1: "ctrl", 2: "data"}
_SUBTYPE = {
    (0, 0): "assoc_req", (0, 1): "assoc_resp", (0, 4): "probe_req",
    (0, 5): "probe_resp", (0, 8): "beacon", (0, 10): "disassoc",
    (0, 11): "auth", (0, 12): "deauth",
    (1, 11): "rts", (1, 12): "cts", (1, 13): "ack",
    (2, 0): "data", (2, 4): "null", (2, 8): "qos_data",
}


def _import_scapy():
    try:
        from scapy.all import Dot11, RadioTap  # noqa: F401
        import scapy.all as scapy
        return scapy
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "scapy is required for capture/replay. Install with: "
            "pip install -r requirements-capture.txt"
        ) from e


def _rssi(pkt, RadioTap) -> Optional[int]:
    try:
        if pkt.haslayer(RadioTap):
            v = getattr(pkt[RadioTap], "dBm_AntSignal", None)
            return int(v) if v is not None else None
    except Exception:
        pass
    return None


def _channel(pkt, RadioTap) -> Optional[int]:
    try:
        if pkt.haslayer(RadioTap):
            freq = getattr(pkt[RadioTap], "ChannelFrequency", None)
            if freq:
                return (int(freq) - 2407) // 5  # 2.4 GHz mapping
    except Exception:
        pass
    return None


def parse_dot11(pkt, scapy, seq: int) -> Optional[dict]:
    """Parse a Scapy packet into a raw-frame dict, or None if not 802.11."""
    Dot11 = scapy.Dot11
    RadioTap = scapy.RadioTap
    if not pkt.haslayer(Dot11):
        return None
    d = pkt.getlayer(Dot11)
    t, st = int(d.type), int(d.subtype)
    try:
        retry = bool(int(d.FCfield) & 0x08)
    except Exception:
        retry = False
    return {
        "seq": seq,
        "ts": float(getattr(pkt, "time", time.time())),
        "channel": _channel(pkt, RadioTap),
        "type": _TYPE.get(t, f"type{t}"),
        "subtype": _SUBTYPE.get((t, st), f"{_TYPE.get(t,'?')}-sub{st}"),
        "src": d.addr2,
        "dst": d.addr1,
        "bssid": d.addr3,
        "rssi": _rssi(pkt, RadioTap),
        "length": len(pkt),
        "retry": retry,
        "source": "capture",
    }


class PcapReplaySource(FrameSource):
    """Replay 802.11 frames from a capture file."""

    source_name = "pcap-replay"

    def __init__(self, path: str, loop: bool = False):
        self.path = path
        self.loop = loop
        self._scapy = _import_scapy()

    def iterate(self) -> Iterator[dict]:
        scapy = self._scapy
        seq = 0
        while True:
            with scapy.PcapReader(self.path) as reader:
                for pkt in reader:
                    seq += 1
                    frame = parse_dot11(pkt, scapy, seq)
                    if frame is not None:
                        frame["source"] = "pcap-replay"
                        yield frame
            if not self.loop:
                break


class CaptureFrameSource(FrameSource):
    """Live monitor-mode 802.11 capture via Scapy AsyncSniffer.

    Requires a monitor-mode-capable interface and Npcap (Windows) / libpcap
    (Linux). On hardware without monitor mode this yields nothing useful; use
    PcapReplaySource for hardware-independent testing.
    """

    source_name = "capture"

    def __init__(self, iface: str, monitor: bool = True):
        self.iface = iface
        self.monitor = monitor
        self._scapy = _import_scapy()

    def iterate(self) -> Iterator[dict]:
        scapy = self._scapy
        q: "queue.Queue" = queue.Queue(maxsize=10000)
        sniffer = scapy.AsyncSniffer(
            iface=self.iface, monitor=self.monitor, store=False,
            prn=lambda p: q.put(p),
        )
        sniffer.start()
        seq = 0
        try:
            while True:
                pkt = q.get()
                seq += 1
                frame = parse_dot11(pkt, scapy, seq)
                if frame is not None:
                    yield frame
        finally:
            try:
                sniffer.stop()
            except Exception:
                pass


def list_interfaces() -> list[str]:
    scapy = _import_scapy()
    try:
        return [str(i) for i in scapy.get_if_list()]
    except Exception:
        return []


def capability_report() -> dict:
    """Best-effort report of live-capture capability on this host."""
    info: dict = {"scapy": False, "interfaces": [], "note": ""}
    try:
        scapy = _import_scapy()
        info["scapy"] = True
        info["scapy_version"] = getattr(scapy, "__version__", "?")
        info["interfaces"] = list_interfaces()
    except Exception as e:
        info["note"] = str(e)
        return info
    import platform
    info["platform"] = platform.system()
    info["note"] = (
        "Live 802.11 monitor-mode capture requires a compatible NIC and "
        "Npcap (Windows) / libpcap (Linux). If unavailable, use PcapReplaySource."
    )
    return info
