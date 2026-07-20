"""Phase 4 demo / verification of the capture engine.

Because live monitor-mode capture needs compatible hardware, this demo proves
the capture->parse->stream path deterministically: it crafts a small but real
802.11 pcap with Scapy (beacon / deauth / data / probe frames), replays it
through a SensorAgent (PcapReplaySource) to Kafka, then consumes and shows the
parsed frames — exercising Scapy's actual Dot11 dissection end to end.
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kafka import KafkaConsumer  # noqa: E402
from wids.config import settings  # noqa: E402
from wids.sensors import SensorAgent  # noqa: E402
from wids.sensors.agent import RAW_TOPIC  # noqa: E402
from wids.sensors.capture import PcapReplaySource  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"
PCAP = DATA / "sample_80211.pcap"


def craft_pcap():
    from scapy.all import (RadioTap, Dot11, Dot11Beacon, Dot11Deauth, Dot11Elt,
                           Dot11ProbeReq, wrpcap)
    ap = "00:11:22:33:44:55"
    sta = "66:77:88:99:aa:bb"
    bcast = "ff:ff:ff:ff:ff:ff"
    pkts = []
    # beacon
    pkts.append(RadioTap() / Dot11(type=0, subtype=8, addr1=bcast, addr2=ap, addr3=ap)
                / Dot11Beacon() / Dot11Elt(ID=0, info="TestAP"))
    # probe request
    pkts.append(RadioTap() / Dot11(type=0, subtype=4, addr1=bcast, addr2=sta, addr3=bcast)
                / Dot11ProbeReq() / Dot11Elt(ID=0, info=""))
    # deauth (attack-relevant)
    for _ in range(3):
        pkts.append(RadioTap() / Dot11(type=0, subtype=12, addr1=sta, addr2=ap, addr3=ap)
                    / Dot11Deauth(reason=7))
    # data frames
    for _ in range(5):
        pkts.append(RadioTap() / Dot11(type=2, subtype=0, addr1=ap, addr2=sta, addr3=ap))
    DATA.mkdir(exist_ok=True)
    wrpcap(str(PCAP), pkts)
    return len(pkts)


def main() -> int:
    print("== Phase 4 capture-engine demo ==")
    n = craft_pcap()
    print(f"Crafted {n} real 802.11 frames -> {PCAP}")

    # replay the pcap through a sensor (real Scapy Dot11 parsing) to Kafka
    agent = SensorAgent("sensor-capture-01", name="capture-demo",
                        location="lab", nic_chipset="pcap", channel=6)
    sent = agent.run(PcapReplaySource(str(PCAP)), rate_hz=0)
    print(f"Sensor parsed & streamed {sent} 802.11 frames to {RAW_TOPIC}")

    # consume and show what the central server received
    consumer = KafkaConsumer(
        RAW_TOPIC,
        bootstrap_servers=settings.kafka_bootstrap,
        group_id="wids-phase4-demo",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=5000,
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
    )
    subtypes = Counter()
    samples = []
    for msg in consumer:
        v = msg.value
        if v.get("source") != "pcap-replay":
            continue  # ignore synthetic frames from earlier demos
        subtypes[v["subtype"]] += 1
        if len(samples) < 6:
            samples.append(v)
    consumer.close()

    print("\n  Parsed 802.11 frames (from Scapy dissection)")
    print("  " + "-" * 70)
    print(f"  {'TYPE':<6}{'SUBTYPE':<12}{'SRC':<20}{'BSSID':<20}")
    print("  " + "-" * 70)
    for s in samples:
        print(f"  {s['type']:<6}{s['subtype']:<12}{str(s['src']):<20}{str(s['bssid']):<20}")
    print("  " + "-" * 70)
    print("  subtype counts:", dict(subtypes))

    ok = subtypes.get("deauth", 0) >= 3 and subtypes.get("beacon", 0) >= 1
    print("\nRESULT:", "PASS - capture->parse->stream works (deauth+beacon dissected)"
          if ok else "FAIL - expected frames not parsed")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
