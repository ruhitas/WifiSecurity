# Wireless IDS + AI Platform

Distributed, real-time Wireless (802.11) Intrusion Detection with a hybrid,
explainable AI pipeline. See the **Software Architecture Document**
(`Software_Architecture_Document.docx`) for the full design, and the
**Literature Review** (`Wireless_IDS_Literature_Review.docx`) for the research
grounding.

## Phase 2 — Development environment

The platform reuses data services already installed on this host and provisions
the rest with Docker Compose.

| Component | How it runs | Endpoint |
|-----------|-------------|----------|
| MSSQL (SQL Server 2019 Express) | **existing host service** | `localhost\SQLEXPRESS` |
| Redis 8.2 | **existing** (Docker) | `localhost:6379` |
| Elasticsearch 9.1.4 | **existing** (shared node) | `https://localhost:9200` (prefix `wids-`) |
| Kafka (KRaft) | docker-compose | `localhost:29092` |
| Kafka UI | docker-compose | http://localhost:8081 |
| Prometheus | docker-compose | http://localhost:9090 |
| Grafana | docker-compose | http://localhost:3000 (admin/admin) |
| MLflow | docker-compose | http://localhost:5000 |

### Quick start

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

This copies `.env.example` → `.env`, starts the infra containers, creates a
Python `.venv`, installs core dependencies, creates the Kafka topics, and runs a
full environment verification.

### Manual steps

```powershell
copy .env.example .env          # then edit ES credentials
docker compose up -d
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\create_topics.py
python scripts\verify_env.py
```

## Environment notes (important)

- **No GPU on this machine.** The ML stack (`requirements-ml.txt`) installs
  **CPU** builds of PyTorch/TensorFlow. GPU-accelerated training/inference
  (Phases 9–10) requires NVIDIA hardware or a cloud node.
- **MSSQL TCP is disabled by default.** Host-side Python reaches SQLEXPRESS over
  named pipe/shared memory (works out of the box). For a *container* to reach
  MSSQL, enable TCP/IP in SQL Server Configuration Manager (and open the port /
  start SQL Browser), then point it at `host.docker.internal`.
- **Elasticsearch is a shared node** (other apps' indices live there). All our
  indices use the `wids-` prefix and `number_of_replicas=0`. Set
  `WIDS_ES_PASSWORD` in `.env` (ES 9.x has TLS + auth enabled).
- **Disk:** keep an eye on free space — below ~5% free, Elasticsearch marks all
  indices read-only (flood-stage watermark). A dedicated data volume for
  capture/streaming is recommended.

## Kafka topics

`wids.raw-frames`, `wids.feature-vectors`, `wids.detections`,
`wids.responses`, `wids.audit` (see SAD §5.2 / §8.1).

## Phase 3 — Multi-sensor fabric

Distributed sensors (Sensor 1..N) register in MSSQL, emit Redis heartbeats, and
stream frames tagged with their `sensor_id` to Kafka, so the central server can
correlate across sensors (Phase 7).

```powershell
python scripts\init_db.py            # create sensors / capture_sessions tables
python scripts\demo_phase3.py        # run 3 sensors -> central consumer (verify)
python scripts\sensor_status.py      # show registry + live status
python scripts\run_sensor.py --id sensor-01 --location "Floor 1" --rate 20
```

## Phase 4 — Packet capture engine

802.11 capture via Scapy, behind the same frame-source interface as the sensor.

```powershell
python scripts\capture_check.py                                   # capability + interfaces
python scripts\demo_phase4.py                                     # craft pcap -> parse -> stream (verify)
python scripts\run_sensor.py --id s1 --source replay --pcap data\sample_80211.pcap
python scripts\run_sensor.py --id s1 --source capture --iface "Wi-Fi"   # live (needs monitor-mode NIC)
```

Sources: `synthetic` (default, no hardware), `replay` (any .pcap — including
AWID3 for Phase 7), `capture` (live monitor mode — needs a compatible NIC +
Npcap/libpcap). Live monitor-mode capture is **not** available on every laptop
Wi-Fi card; the sensor hardware (AX210 / RTL8812AU on Linux) is the target for
live capture.

## Phase 5 — Streaming pipeline

Real-time chain: `raw-frames → feature extraction (windowed) → feature-vectors →
inference → detections → sink (MSSQL detection_events + Elasticsearch wids-*)`.
Phase 5 ships ~14 features and a transparent rule-based inference stub; Phase 6
adds the 300+ feature set and Phases 9–10 the hybrid model ensemble.

```powershell
# each service runs standalone (separate terminals) ...
python scripts\run_feature_extractor.py
python scripts\run_inference.py
python scripts\run_sink.py
# ... or run the whole pipeline + an injected deauth flood as one verification:
python scripts\demo_phase5.py
```

## Phase 6 — Feature extraction (300+)

`wids.streaming.features.compute_features` produces **343 features** per window
across the SAD §8.4 categories: frame/type/subtype counts & rates, 22 descriptive
statistics over 12 numeric quantities (RSSI, length, inter-frame timing, per-entity
distributions, degrees…), entropy, vendor/OUI, and **graph/BSSID relational
features** (for the GNN). Same interface as Phase 5, so the pipeline uses it
automatically.

```powershell
python scripts\demo_phase6.py     # prints feature count + category breakdown + separation
```

## Phase 7 — Dataset builder

Assembles a labeled, unified feature dataset from synthetic normal traffic,
generated multi-class attacks (deauth / disassoc / auth / probe / beacon floods)
and — optionally — real capture files (AWID3 via `--pcap`). Output is a CSV +
JSON manifest under `data/datasets/`, ready for Phase 8/9.

```powershell
python scripts\build_dataset.py --windows 80 --window-size 60 --name wids_dataset_v1
python scripts\build_dataset.py --pcap data\awid3_deauth.pcap --pcap-label deauth_flood
```

Produces e.g. 480 rows x 343 features across 6 balanced classes.

## Phase 8 — Feature selection

Runs Mutual Information, ANOVA-F, Random-Forest importance, Permutation
importance, L1/LASSO and RFE on the dataset, reports a **consensus ranking**,
the PCA dimensionality (e.g. 61 components for 95% variance), and writes a report
plus a selected-feature subset for Phase 9/10.

```powershell
python scripts\feature_select.py --select 40
# -> data/reports/feature_selection_report.json + selected_features.json
```

## Phase 9 — Model benchmark

Benchmarks 10 classical + boosting classifiers (LogisticRegression, KNN, SVM,
DecisionTree, RandomForest, ExtraTrees, GradientBoosting, MLP, XGBoost, LightGBM)
with stratified CV — accuracy / precision / recall / F1 / ROC-AUC plus training
time and per-sample inference latency — ranks them, and builds a confusion matrix
for the best model.

```powershell
python scripts\benchmark.py --cv 5              # all features
python scripts\benchmark.py --cv 5 --selected  # Phase-8 selected subset
# -> data/reports/benchmark.json + benchmark.csv
```

> **Note:** on the *synthetic* dataset most models score ~1.0 F1 because the
> generated classes are trivially separable. These numbers validate the harness,
> **not** detection quality. Feed real data (AWID3 via `build_dataset.py --pcap`)
> for meaningful results — this is the "accuracy saturation" caveat from the
> literature review. Deep models (CNN/Transformer/GNN) come in Phase 10.

## Phase 10 — Hybrid AI (CNN + Transformer + GNN + XAI)

* **HybridNet** (`wids.models.hybrid`): a 1D-CNN branch + a Transformer
  self-attention branch over the feature vector, fused into a classifier, with
  gradient-based (input×gradient) XAI and attention read-out.
* **GNN** (`wids.models.gnn`): a from-scratch GCN over the per-window
  station↔BSSID graph (built from raw frames) — the relational novelty.

```powershell
python scripts\train_hybrid.py --epochs 60   # CNN+Transformer + per-class XAI
python scripts\demo_gnn.py                    # GCN on the station<->BSSID graph
```

> On synthetic data HybridNet reaches ~1.0 F1 (trivially separable — validates
> the model, not detection quality). The GNN reaches ~0.81 F1 over 6 classes
> from graph structure alone, which is the more realistic signal. Feed AWID3 for
> meaningful evaluation.

## Phase 11 — Zero-day detection

Unsupervised detectors (`wids.anomaly`) — Isolation Forest, One-Class SVM,
AutoEncoder, VAE, Deep SVDD — trained on **normal traffic only**, flagging
attacks never seen in training.

```powershell
python scripts\demo_phase11.py   # ROC-AUC + detection% + false-positive% per detector
```

> On the synthetic set the best detectors reach ROC-AUC ~0.96 with 100% attack
> detection, confirming the capability. **However** false-positive rates are high
> because only ~56 normal windows are available for training — the anomaly
> threshold doesn't generalise. Real/large normal baselines + validation-based
> thresholding are needed for deployment; the ranking (AUC) is already strong.

## Phase 12 — Explainable AI

`wids.xai.Explainer` produces an operator-facing **reasoning report** per
detection: SHAP feature contributions (from-scratch LIME fallback if SHAP is
unavailable), the confidence score, and a plain-language explanation, plus global
feature importance.

```powershell
python scripts\demo_phase12.py   # per-class reasoning reports + global importance
```

Example: *"Classified as 'deauth_flood' with 87% confidence. Main drivers (SHAP):
deauth_rate (+0.10), sub_deauth_count (+0.10), deauth_count (+0.08)."*

## Phase 13 — Autonomous response

Policy-gated, auditable mitigation (`wids.response`). A PolicyEngine gates by
confidence/severity; pluggable executors run MAC block / disable AP / firewall /
VLAN quarantine (dry-run by default), SIEM forward (to `wids.audit`) and RabbitMQ
notifications. Every action is persisted to MSSQL `response_actions` and can be
overridden/rolled back by an analyst.

```powershell
python scripts\run_response.py         # service: wids.detections -> actions (dry-run)
python scripts\run_response.py --live  # disable dry-run (needs real endpoints)
python scripts\demo_phase13.py         # high/medium/benign -> gated actions + override
```

> Enforcement is **dry-run** until a real WLC/firewall endpoint is wired.
> Notifications use the existing RabbitMQ; on this host the AMQP listener (5672)
> is inactive (only management 15672 / dist 25672), so notifications currently
> skip gracefully — enable the AMQP listener to activate them.

## Phase 14 — Cloud native (Docker / Helm / Kubernetes)

`deploy/` contains a Dockerfile (one image, service chosen by `WIDS_SERVICE`), a
Helm chart (`deploy/helm/wids`) and plain manifests (`deploy/k8s`). Each pipeline
service is a Deployment + HorizontalPodAutoscaler (SAD §10 model). Validated with
`helm lint` / `helm template`. See `deploy/README.md`.

```bash
docker build -f deploy/Dockerfile -t wids:0.14.0 .
helm install wids deploy/helm/wids --namespace wids --create-namespace
```

## Real AWID3 data & Phase 16 — Scientific benchmark

The whole analysis runs on the **real AWID3** dataset, not just synthetic data:

```powershell
python scripts\build_awid3.py                                  # AWID3_5csv -> data/datasets/awid3_real.csv
python scripts\benchmark.py       --csv data\datasets\awid3_real.csv
python scripts\feature_select.py  --csv data\datasets\awid3_real.csv
python scripts\train_hybrid.py    --csv data\datasets\awid3_real.csv
python scripts\demo_phase11.py    --csv data\datasets\awid3_real.csv   # zero-day
python scripts\demo_phase12.py    --csv data\datasets\awid3_real.csv   # XAI
python scripts\scientific_benchmark.py                          # ROC/PR/confusion/ablation figures
```

Headline real-AWID3 results (74k rows, 14 classes, leakage columns removed):

| Metric | Value |
|---|---|
| Best model | XGBoost — macro-F1 **0.976**, ROC-AUC 0.9998 |
| Zero-day (AutoEncoder) | ROC-AUC **0.991**, 92% detection, ~5% FPR |
| Hybrid CNN+Transformer | macro-F1 0.929 |
| Inference latency / throughput | **4.8 µs/sample · ~209k samples/s** |
| Ablation | ~15–20 features reach the F1 plateau |

Figures (paper-ready) are written to `data/reports/figures/` (confusion matrix,
ROC, PR, per-class F1, model comparison, feature importance, ablation).

> Identifier/timestamp/MAC columns are dropped to avoid leakage, so scores are
> honest (some leaky-feature papers report inflated numbers). Realistic
> confusions (Deauth↔Disas) and hard classes (Website_spoofing for anomaly
> detection) are reported, not hidden.

## Layout

```
docker-compose.yml        infra services
config/                   prometheus + grafana provisioning
src/wids/                 config + connection helpers
scripts/                  setup, topic creation, verification
requirements.txt          core connectivity deps
requirements-ml.txt       ML stack (CPU), installed on demand
```
