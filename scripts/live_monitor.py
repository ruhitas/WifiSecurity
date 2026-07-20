"""Real-time monitoring: stream AWID3 traffic through the trained model and raise
live alerts, optionally exposing Prometheus metrics for a Grafana dashboard.

Monitor-mode 802.11 capture is not available on every host, so this replays real
AWID3 records as a live stream (the role a sensor plays on real hardware): each
record is scored on arrival, attacks above the confidence threshold raise an
alert, alerts are persisted to MSSQL, and counters are exported to Prometheus.

Examples:
    python scripts/live_monitor.py --seconds 15 --rate 250
    python scripts/live_monitor.py --loop --rate 300 --metrics-port 8000   # for Grafana
"""
import argparse
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402
from sklearn.preprocessing import LabelEncoder  # noqa: E402
from xgboost import XGBClassifier  # noqa: E402

from wids.feature_selection import load_dataset  # noqa: E402
from wids.feature_selection.selectors import drop_low_variance  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "data" / "datasets" / "awid3_real.csv"))
    ap.add_argument("--seconds", type=float, default=15.0)
    ap.add_argument("--rate", type=int, default=250)
    ap.add_argument("--threshold", type=float, default=0.90)
    ap.add_argument("--no-db", action="store_true")
    ap.add_argument("--metrics-port", type=int, default=0, help="Prometheus metrics port (0=off)")
    ap.add_argument("--loop", action="store_true", help="stream forever (re-shuffle) until Ctrl+C")
    args = ap.parse_args()

    print("== Wireless IDS - real-time monitor (AWID3 live replay) ==")
    X, y = load_dataset(args.csv); X, _ = drop_low_variance(X)
    names = list(X.columns)
    le = LabelEncoder().fit(y); ye = le.transform(y)
    Xtr, Xst, ytr, yst = train_test_split(X.values, ye, test_size=0.25, stratify=ye, random_state=7)
    print(f"Training detector on {len(Xtr)} records ({len(names)} features, {len(le.classes_)} classes)...")
    model = XGBClassifier(n_estimators=300, tree_method="hist", eval_metric="mlogloss", random_state=7)
    model.fit(Xtr, ytr)
    topfeat = [names[i] for i in np.argsort(model.feature_importances_)[::-1][:3]]
    classes = list(le.classes_)
    normal_idx = classes.index("Normal") if "Normal" in classes else -1

    # Prometheus metrics (optional)
    M = None
    if args.metrics_port:
        from prometheus_client import start_http_server, Counter as PC, Gauge as PG
        start_http_server(args.metrics_port)
        M = {"rec": PC("wids_records_total", "records analyzed"),
             "al": PC("wids_alerts_total", "alerts raised", ["attack_type"]),
             "thr": PG("wids_throughput_rps", "records/sec"),
             "conf": PG("wids_last_alert_confidence", "confidence of last alert"),
             "rate_al": PG("wids_alerts_per_sec", "alerts/sec")}
        print(f"Prometheus metrics: http://localhost:{args.metrics_port}/metrics")

    rng = np.random.RandomState(1)
    order = rng.permutation(len(Xst)); Xst, yst = Xst[order], yst[order]

    conn = None
    if not args.no_db:
        try:
            from wids.schema import ensure_schema
            from wids.connections import get_mssql
            ensure_schema(); conn = get_mssql(); conn.autocommit = True
        except Exception as e:
            print(f"[warn] MSSQL unavailable: {str(e)[:80]}")

    mode = "loop (Ctrl+C to stop)" if args.loop else f"{args.seconds:.0f}s"
    print(f"\nStreaming live at ~{args.rate} rec/s for {mode} (alert conf>={args.threshold})...\n")
    print("  TIME     RECS   RATE     ALERTS   TOP ATTACK TYPES (window)")
    print("  " + "-" * 74)

    interval = 1.0 / args.rate
    t0 = time.perf_counter(); last = t0; last_al = 0
    processed = alerts = tp = fp = 0
    seen = set(); win = Counter(); lat = []
    i = 0
    try:
        while args.loop or (time.perf_counter() - t0 < args.seconds):
            if i >= len(Xst):
                if not args.loop:
                    break
                o = rng.permutation(len(Xst)); Xst, yst = Xst[o], yst[o]; i = 0
            row = Xst[i:i+1]
            ts = time.perf_counter()
            proba = model.predict_proba(row)[0]
            lat.append((time.perf_counter() - ts) * 1e6)
            c = int(np.argmax(proba)); conf = float(proba[c])
            processed += 1
            if M: M["rec"].inc()
            if c != normal_idx and conf >= args.threshold:
                alerts += 1; label = classes[c]; win[label] += 1
                if yst[i] != normal_idx: tp += 1
                else: fp += 1
                if M: M["al"].labels(label).inc(); M["conf"].set(round(conf, 4))
                if label not in seen:
                    seen.add(label)
                    print(f"  [ALERT {time.perf_counter()-t0:5.1f}s] {label:<16} conf={conf:.2f} "
                          f"drivers={', '.join(topfeat)}")
                if conn is not None:
                    try:
                        conn.cursor().execute(
                            "INSERT INTO detection_events (event_id,sensor_id,attack_type,score,confidence,created_at) "
                            "VALUES (?,?,?,?,?,SYSUTCDATETIME())",
                            str(uuid.uuid4()), "live-stream", label, round(conf, 4), round(conf, 4))
                    except Exception:
                        pass
            now = time.perf_counter()
            if now - last >= 1.0:
                rate = processed / (now - t0)
                if M: M["thr"].set(round(rate, 1)); M["rate_al"].set(alerts - last_al)
                last_al = alerts
                print(f"  {now-t0:5.1f}s  {processed:6d}  {rate:6.0f}/s {alerts:7d}   "
                      + ", ".join(f"{k}:{v}" for k, v in win.most_common(3)))
                last = now; win = Counter()
            i += 1
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n  stopped by user")

    dur = time.perf_counter() - t0
    print("  " + "-" * 74)
    print(f"\n  SUMMARY  (real-time replay of real AWID3 traffic)")
    print(f"  records analyzed : {processed} in {dur:.1f}s ({processed/max(dur,1e-9):.0f} rec/s)")
    print(f"  alerts raised    : {alerts}  (true {tp}, false {fp}, precision {tp/max(1,tp+fp):.3f})")
    if lat:
        print(f"  per-record latency: {np.mean(lat):.1f} us (median {np.median(lat):.1f})")
    print(f"  attack types seen: {', '.join(sorted(seen))}")
    if conn is not None:
        cur = conn.cursor(); cur.execute("SELECT COUNT(*) FROM detection_events WHERE sensor_id='live-stream'")
        print(f"  alerts persisted to MSSQL: {cur.fetchone()[0]} total"); conn.close()
    print("\nRESULT: PASS - live collect -> analyze -> alert loop working" if alerts else "\nRESULT: no alerts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
