# Leakage-Aware and Explainable ML for IEEE 802.11 Intrusion Detection (AWID3)

Reproducibility package for the paper *"Leakage-Aware and Explainable Machine
Learning for IEEE 802.11 Intrusion Detection: A Rigorous Multi-Class Evaluation
on AWID3"* (R. Taş, OSTIM Technical University).

This repository contains everything needed to (1) **reproduce every result and
figure** in the paper on the AWID3 dataset, and (2) **run the detector on live
802.11 traffic** captured from a real wireless environment.

> **Core finding.** Naive sampling of the full AWID3 corpus produces
> *capture-environment leakage* — attack and benign frames come from different
> capture sessions, so a model (even logistic regression) reaches ~1.00 macro-F1
> without learning any attack signal. Under a leakage-controlled protocol the
> honest result is **0.976 macro-F1** over 14 classes. We quantify the leakage,
> report an explainable baseline, and release the code so others can verify it.

## Headline results (real AWID3, leakage-controlled)

| Metric | Value |
|---|---|
| Best model (XGBoost) | macro-F1 **0.976**, ROC-AUC 0.9998, accuracy 0.987 |
| Unseen-attack (AutoEncoder, benign-only training) | ROC-AUC **0.991**, 92% detection, ~5% FPR |
| Feature ablation | ~15–20 features reach the plateau |
| Inference | **4.7 µs/sample** (~2.1×10⁵ samples/s, CPU) |
| Leakage demonstration | naive full-archive sampling → ~1.00 (misleading) |

Figures are in `data/reports/figures/`; numeric reports in `data/reports/*.json`.

## GUI — one-click control panel (WifiIDS)

Prefer buttons to the command line? Launch the desktop control panel:

```bash
.\.venv\Scripts\python.exe wifiids_gui.py     # or double-click WifiIDS.bat on Windows
```

`WifiIDS` is a tabbed Tkinter app (no extra dependencies) that runs every step
with **Start** buttons: **1. Environment** (save settings, check Docker, start
infrastructure, verify), **2. Dataset** (build), **3. Analysis** (benchmark,
feature selection, figures, unseen-attack detection, SHAP, hybrid), and **4. Real-Time &
Dashboard** (start the live monitor, open Grafana, generate the SOC dashboard).
All parameters are editable (pre-filled with working defaults), and a live log
pane shows output plus friendly warnings such as *"Docker engine not running"* or
*"metrics port already in use"*. Settings can be saved to `.env`.

## Quick runbook — run in order

Copy/paste these after completing **Setup** (Section 2) and placing the AWID3
CSVs (Section 3.1). Each step prints a `RESULT: PASS` line on success.

```bash
# --- A) Reproduce the paper (offline, needs only the CSV) ---
python scripts/build_awid3.py --root AWID3_5csv --out data/datasets/awid3_real.csv   # 1. build dataset
python scripts/benchmark.py         --csv data/datasets/awid3_real.csv --cv 5         # 2. model benchmark
python scripts/feature_select.py    --csv data/datasets/awid3_real.csv                # 3. feature ranking
python scripts/scientific_benchmark.py                                               # 4. ROC/PR/confusion/ablation (300 DPI)
python scripts/reviewer_evidence.py                                                # 4b. leakage attribution + bootstrap CIs + local SHAP
python scripts/demo_phase11.py      --csv data/datasets/awid3_real.csv                # 5. unseen-attack anomaly detection
python scripts/demo_phase12.py      --csv data/datasets/awid3_real.csv                # 6. SHAP explanations
python scripts/train_hybrid.py      --csv data/datasets/awid3_real.csv --epochs 25    # 7. hybrid CNN+Transformer

# --- B) Real-time monitoring + live Grafana dashboard ---
docker compose up -d                                                                  # 8. Kafka/Prometheus/Grafana/MLflow
python scripts/live_monitor.py --loop --rate 300 --metrics-port 9464                  # 9. live alerts + metrics (Ctrl+C to stop)
#     open Grafana:  http://localhost:3000   (admin / admin)
#     dashboard:     "Wireless IDS - Real-Time Alerts"  (auto-provisioned)
python scripts/dashboard.py                                                           # 10. static SOC dashboard -> data/reports/soc_dashboard.html
```

> Step 9 runs the model on a live stream of real AWID3 traffic and exports
> Prometheus metrics on port **9464**; Grafana (started in step 8) shows them
> live. On real sensor hardware, replace step 9 with
> `python scripts/run_sensor.py --source capture --iface <mon-iface>` plus the
> pipeline services (Section 4.4).

## Repository layout

```
src/wids/                 Python package
  config.py               settings from environment / .env
  connections.py          Kafka, Redis, MSSQL, Elasticsearch, RabbitMQ clients
  schema.py               MSSQL tables (sensors, sessions, detections, responses)
  sensors/                capture: SensorAgent, registry, frames, Scapy capture
  streaming/              feature extraction (343 feats), inference, sink
  dataset/                AWID3 loader + synthetic dataset builder
  feature_selection/      MI, ANOVA, RF, permutation, LASSO, RFE, PCA
  benchmark/              multi-model benchmark runner
  models/                 hybrid CNN+Transformer, GNN, training + XAI(saliency)
  anomaly/                unseen-attack detectors (IF, OCSVM, AE, VAE, DeepSVDD)
  xai/                    SHAP explainer + reasoning reports
  response/              policy engine + action executors (dry-run by default)
scripts/                  runnable entry points (see below)
config/                   Prometheus + Grafana provisioning
deploy/                   Dockerfile, Helm chart, plain K8s manifests
data/reports/             figures + JSON result summaries
docker-compose.yml        Kafka, Prometheus, Grafana, MLflow
requirements*.txt         core / ML / capture dependencies
```

## 1. Prerequisites

- **Python 3.11**
- **Docker + Docker Compose** (for Kafka/Prometheus/Grafana/MLflow)
- **ODBC Driver 18 for SQL Server** (for MSSQL via `pyodbc`)
- Optional data stores if you use them: **Redis**, **Microsoft SQL Server /
  LocalDB**, **Elasticsearch 8/9**. These are configurable in `.env`; the
  reproduction experiments below need none of them (they read CSV files).
- For **live capture** (Section 4): a monitor-mode-capable Wi-Fi adapter
  (e.g., Intel AX210, RTL8812AU) with **Npcap** (Windows) or **libpcap** (Linux).

## 2. Setup

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt          # core (kafka, redis, es, pyodbc, ...)
pip install -r requirements-ml.txt       # ML stack (numpy, pandas, sklearn, torch-cpu, xgboost, lightgbm, shap)
cp .env.example .env                     # then edit endpoints/credentials
```

`requirements-ml.txt` installs **CPU** builds of PyTorch/TensorFlow (no GPU is
required to reproduce the paper). Also `pip install matplotlib scapy` if not
already pulled in (matplotlib for figures, scapy for capture).

## 3. Reproducing the paper (AWID3)

### 3.1 Get the dataset

AWID3 is not redistributed here. Download it from the official source
(University of the Aegean, https://icsdweb.aegean.gr/awid/ ) or a mirror
(Kaggle: https://www.kaggle.com/datasets/suumia/awid3-dataset ), and place the
per-attack-category CSV folders under, e.g., `AWID3_5csv/` (the curated reduced
set) or `AWID3_archive/CSV/` (the full 254-feature corpus).

**Dataset sources (all public):**

| Dataset | Type | Source |
|---|---|---|
| AWID3 | 802.11 wireless | https://icsdweb.aegean.gr/awid/ · https://www.kaggle.com/datasets/suumia/awid3-dataset |
| CIC-IDS-2017 | wired IP flows | https://www.kaggle.com/datasets/chethuhn/network-intrusion-dataset |
| CSE-CIC-IDS2018 | wired IP flows | https://www.kaggle.com/datasets/solarmainframe/ids-intrusion-csv |

CIC-IDS-2017/2018 are used only for the cross-dataset generalization check
(Section VII-B of the paper); they are wired flow-based datasets, not 802.11.

### 3.2 Build the leakage-controlled dataset

```bash
python scripts/build_awid3.py --root AWID3_5csv --out data/datasets/awid3_real.csv
```

This resolves the `Label` column by name, **removes leakage columns**
(timestamps, TSF, MAC-time, frame numbers, MAC/IP addresses, sequence/ACK counters — ports are kept),
drops constants, and balances classes → 74,270 rows, 34 features, 14 classes.

Exact feature list: `config/leakage_controlled_features.txt`
Source code: https://github.com/ruhitas/WifiSecurity

### 3.3 Run the experiments

```bash
python scripts/benchmark.py            --csv data/datasets/awid3_real.csv --cv 5   # Table III
python scripts/feature_select.py       --csv data/datasets/awid3_real.csv          # consensus ranking
python scripts/train_hybrid.py         --csv data/datasets/awid3_real.csv          # CNN+Transformer + XAI
python scripts/demo_phase11.py         --csv data/datasets/awid3_real.csv          # unseen-attack (Table VI)
python scripts/demo_phase12.py         --csv data/datasets/awid3_real.csv          # SHAP reasoning reports
python scripts/scientific_benchmark.py                                            # ROC/PR/confusion/ablation @300 DPI
```

Outputs land in `data/reports/` (JSON summaries) and `data/reports/figures/`
(PNG figures at 300 DPI).

### 3.4 Reproduce the leakage demonstration

```bash
# naive per-category sampling of the FULL archive -> inflated ~1.00 F1
python scripts/build_awid3.py --root AWID3_archive/CSV --out data/datasets/awid3_full.csv \
       --files-per-cat 20 --normal-cap 40000 --attack-cap 12000
python scripts/benchmark.py --csv data/datasets/awid3_full.csv --cv 5
# compare against the curated result from 3.2/3.3 (0.976) — see Table IV
```

## 4. Using it on a REAL environment (live 802.11 capture)

The same pipeline that is evaluated on AWID3 runs on live traffic. Data flows:

```
sensor(s) --Kafka--> feature extraction --> inference --> detections --> sink/response
```

### 4.1 Start the infrastructure

```bash
docker compose up -d          # Kafka (:29092), Prometheus, Grafana, MLflow
python scripts/create_topics.py
python scripts/verify_env.py  # checks Kafka/Redis/MSSQL/Elasticsearch reachability
```

### 4.2 Capture capability check

```bash
python scripts/capture_check.py   # reports scapy, interfaces, monitor-mode guidance
```

Live monitor-mode capture needs a compatible adapter and Npcap/libpcap. On a
Linux sensor with an AX210/RTL8812AU you typically enable monitor mode with
`airmon-ng start wlan0` (or `iw dev wlan0 set type monitor`).

### 4.3 Run a sensor (three source options)

```bash
# a) live capture from a monitor-mode interface
python scripts/run_sensor.py --id sensor-01 --source capture --iface "wlan0mon"

# b) replay a pcap (e.g., AWID3 captures) through the same parser
python scripts/run_sensor.py --id sensor-01 --source replay --pcap data/sample.pcap

# c) synthetic frames (no hardware, for wiring tests)
python scripts/run_sensor.py --id sensor-01 --source synthetic --rate 50
```

Each sensor registers itself, streams frames tagged with its `sensor_id`, and
emits heartbeats. Multiple sensors feed one central server — run
`python scripts/sensor_status.py` to see the fleet.

### 4.4 Run the detection pipeline services

```bash
python scripts/run_feature_extractor.py   # raw-frames  -> feature-vectors
python scripts/run_inference.py           # feature-vectors -> detections
python scripts/run_sink.py                # detections -> MSSQL + Elasticsearch + alerts
python scripts/run_response.py            # policy-gated response (dry-run by default)
```

`run_response.py` performs **dry-run** mitigations by default (it logs what it
*would* do). Real enforcement (deauth / MAC block / VLAN quarantine) requires a
WLAN-controller/firewall endpoint and the `--live` flag; use with care.

Notes for a live deployment:
- The 343-feature extractor (`src/wids/streaming/features.py`) works on real
  parsed frames as well as AWID3 replay.
- Point `WIDS_MSSQL_*`, `WIDS_REDIS_URL`, `WIDS_ES_*`, `WIDS_KAFKA_BOOTSTRAP`
  in `.env` at your own services.
- Elasticsearch indices use the `wids-` prefix so they never collide with other
  applications on a shared cluster.

### 4.6 Offline workflow: capture a PCAP, then analyze it

If you do not want to run the full streaming stack, you can capture to a file and
analyze it offline. This is the simplest way to work with real traffic.

**1) Capture 802.11 frames** (needs a monitor-mode-capable adapter):

```bash
# Linux (recommended for real 802.11 monitor mode):
sudo airmon-ng start wlan0                 # creates wlan0mon
sudo tcpdump -i wlan0mon -w normal.pcap    # or capture in Wireshark on wlan0mon
#  ... generate/collect traffic, Ctrl-C to stop ...
```

Wireshark works too: select the monitor-mode interface and save as `.pcapng`.
Ordinary Wi-Fi cards in *managed* mode capture only your own decrypted IP
traffic, not raw 802.11 management/control frames — monitor mode is required to
reproduce AWID3-style features (beacons, deauth, probe, RTS/CTS, ...).

**2) Convert the PCAP to a features CSV** (300+ features per window):

```bash
python scripts/pcap_to_csv.py --pcap normal.pcap --label normal --out normal.csv
python scripts/pcap_to_csv.py --pcap deauth.pcap --label deauth --out deauth.csv
```

**3) Build a labeled set and analyze it:**

```bash
# concatenate per-class CSVs (same columns) into one training set, then:
python scripts/analyze_dataset.py --csv combined.csv --label label
```

### 4.7 Analyzing another dataset (not AWID3)

`scripts/analyze_dataset.py` runs the full model benchmark on **any** labeled
dataset — AWID3, CIC-IDS-2017, CSE-CIC-IDS2018, or your own captured-and-labeled
data. It reads **CSV or Parquet** (a single file or a whole folder), auto-detects
the label column, keeps numeric features, one-hot encodes small categorical
columns, drops id/time/MAC/meta columns and zero-variance features, then prints a
ranked model table plus the best model's confusion matrix. The report is written
to `data/reports/analyze_<name>.json`. (Parquet needs `pyarrow`; see
`requirements-ml.txt`.)

```bash
python scripts/analyze_dataset.py --csv data/datasets/awid3_real.csv
python scripts/analyze_dataset.py --csv mydata.csv --label attack_type --cv 5

# a whole folder (CSV or Parquet, concatenated) with a row cap for large sets:
python scripts/analyze_dataset.py --csv CICIDS      --sample 24000 --cv 3   # CIC-IDS-2017 (CSV)
python scripts/analyze_dataset.py --csv CICIDS2018  --sample 24000 --cv 3   # CSE-CIC-IDS2018 (Parquet)
```

Example — CIC-IDS-2017 (`--csv CICIDS --sample 24000`): the tool concatenates the
eight day files, cleans 79 columns down to 70 features over 8 classes, and ranks
the suite with **XGBoost at macro-F1 ~0.98 (ROC-AUC ~1.0)**. It handles the
dataset's quirks automatically (whitespace in column names, infinite values in
the flow-rate columns, and non-ASCII characters in the web-attack labels).

All of the above is also available without the command line from the GUI tab
**"5. Live Capture & Custom Data"** (capability check, PCAP → CSV, analyze
dataset).

### 4.5 Real-time monitoring and SOC dashboard

To watch the collect → analyze → alert loop live (real AWID3 traffic replayed as
a live stream when monitor-mode capture is unavailable):

```bash
# console demo (fixed duration)
python scripts/live_monitor.py --seconds 15 --rate 250

# continuous, with Prometheus metrics for the live Grafana dashboard
docker compose up -d                                       # Prometheus + Grafana
python scripts/live_monitor.py --loop --rate 300 --metrics-port 9464

# static HTML SOC dashboard from the MSSQL alert store
python scripts/dashboard.py                                # -> data/reports/soc_dashboard.html
```

`live_monitor.py` scores each record on arrival, raises an alert for attacks above
the confidence threshold, prints a rolling status feed, persists alerts to the
MSSQL `detection_events` table, and (with `--metrics-port`) exports Prometheus
counters (`wids_records_total`, `wids_alerts_total{attack_type}`,
`wids_throughput_rps`, ...).

**Live Grafana dashboard.** With `docker compose up -d` running and
`live_monitor.py --metrics-port 9464` streaming, open **http://localhost:3000**
(`admin` / `admin`) and pick **"Wireless IDS - Real-Time Alerts"** — it is
auto-provisioned (`config/grafana/provisioning/`) and refreshes every 5 s with
records analyzed, alerts raised, throughput, and an alerts-by-attack-type donut.
Prometheus scrapes the monitor at `host.docker.internal:9464`
(`config/prometheus.yml`).

`dashboard.py` also renders a self-contained SOC dashboard (KPIs, alerts-by-type,
recent alerts) to `data/reports/soc_dashboard.html`. On real sensor hardware the
live stream is replaced by `run_sensor.py --source capture` with no other change.

## 5. Internal deployment / product testing

For a containerized internal test:

```bash
docker build -f deploy/Dockerfile -t wids:latest .
# Kubernetes (Helm):
helm install wids deploy/helm/wids --namespace wids --create-namespace \
     --set secret.WIDS_ES_PASSWORD=... --set secret.WIDS_MSSQL_PASSWORD=...
# or plain manifests:
kubectl apply -f deploy/k8s/wids-rendered.yaml
```

Each pipeline service is a Deployment with a HorizontalPodAutoscaler. One image
runs any service, selected by the `WIDS_SERVICE` environment variable
(`feature-extractor | inference | response | sink`). See `deploy/README.md`.

## 6. Configuration

All settings come from environment variables / `.env` (see `.env.example`).
Never commit real credentials. LocalDB is host-only; for container access use a
networked SQL Server instance with TCP enabled.

## 7. Honesty / limitations

Results are on AWID3. Identifier and timestamp columns are removed to prevent
leakage, so scores are lower than some published numbers that retain them — this
is intentional. Realistic confusions (Deauth vs. Disas) and hard classes
(Website_spoofing for anomaly detection) are reported, not hidden. The GNN and
multi-sensor components are demonstrated on synthetic/graph-structured data;
extending them to live captures is future work.

## 8. Citation

```
R. Taş, "Leakage-Aware and Explainable Machine Learning for IEEE 802.11
Intrusion Detection: A Rigorous Multi-Class Evaluation on AWID3," 2026.
```

## License

Released under the MIT License — see `LICENSE`.
