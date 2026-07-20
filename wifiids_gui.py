"""WifiIDS - Wireless Intrusion Detection Control Panel (GUI).

A single-window, tabbed desktop app that lets an end user run the whole pipeline
with Start buttons: set up the environment, build the dataset, run the analysis
experiments, and launch real-time monitoring with a live Grafana dashboard.
Parameters are editable (pre-filled with sensible defaults) and every action
streams its output to the log pane, including friendly warnings such as
"Docker engine not running" or "port already in use".

Run with the project's virtual environment:
    .\.venv\Scripts\python.exe wifiids_gui.py
"""
import os
import queue
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import ttk, scrolledtext

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON = str(VENV_PY) if VENV_PY.exists() else sys.executable

# default parameters = our current working values (end user can change them)
# maps GUI field keys <-> .env variable names
ENV_KEYS = {
    "kafka": "WIDS_KAFKA_BOOTSTRAP",
    "redis": "WIDS_REDIS_URL",
    "mssql_driver": "WIDS_MSSQL_DRIVER",
    "mssql_server": "WIDS_MSSQL_SERVER",
    "mssql_db": "WIDS_MSSQL_DATABASE",
    "es_url": "WIDS_ES_URL",
    "es_user": "WIDS_ES_USERNAME",
    "es_pass": "WIDS_ES_PASSWORD",
}

DEFAULTS = {
    "kafka": "localhost:29092",
    "redis": "redis://localhost:6379/0",
    "mssql_driver": "ODBC Driver 18 for SQL Server",
    "mssql_server": r"(localdb)\MSSQLLocalDB",
    "mssql_db": "WirelesSecureDB",
    "es_url": "https://localhost:9200",
    "es_user": "elastic",
    "es_pass": "",
    "awid_root": "AWID3_5csv",
    "dataset_csv": r"data\datasets\awid3_real.csv",
    "normal_cap": "20000",
    "attack_cap": "8000",
    "cv": "5",
    "epochs": "25",
    "rate": "300",
    "threshold": "0.90",
    "seconds": "15",
    "metrics_port": "9464",
    "pcap_in": r"data\captures\capture.pcap",
    "pcap_out": r"data\datasets\capture_features.csv",
    "pcap_window": "40",
    "pcap_label": "",
    "custom_csv": r"data\datasets\awid3_real.csv",
    "custom_label": "",
    "custom_sample": "0",
}


def load_env_file(path):
    """Read an existing .env file into a {GUI-key: value} dict (best effort)."""
    values = {}
    if not path.exists():
        return values
    rev = {v: k for k, v in ENV_KEYS.items()}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, val = line.split("=", 1)
        gui_key = rev.get(name.strip())
        if gui_key:
            values[gui_key] = val.strip()
    return values


class WifiIDS(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WifiIDS - Wireless Intrusion Detection Control Panel")
        self.geometry("1080x760")
        self.minsize(900, 640)
        # open maximized (full screen) on first launch
        try:
            self.state("zoomed")          # Windows / most platforms
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)   # some Linux WMs
            except tk.TclError:
                pass
        self.proc = None
        self.q = queue.Queue()
        # start from defaults, then override with any saved .env values
        merged = dict(DEFAULTS)
        saved = load_env_file(ROOT / ".env")
        merged.update({k: v for k, v in saved.items() if v != ""})
        self.vars = {k: tk.StringVar(value=merged.get(k, DEFAULTS.get(k, ""))) for k in DEFAULTS}
        self.loop_var = tk.BooleanVar(value=True)
        self.rebuild_var = tk.BooleanVar(value=False)
        self.fast_var = tk.BooleanVar(value=False)
        self._build_ui()
        self.after(80, self._drain_log)
        self.log(f"WifiIDS ready. Python: {PYTHON}", "info")
        self.log(f"Project root: {ROOT}", "info")
        if saved:
            loaded = ", ".join(sorted(saved))
            self.log(f"Loaded saved settings from .env ({loaded}).", "ok")
            if saved.get("es_pass"):
                self.log("Elasticsearch password loaded from .env.", "ok")

    # ---------------- UI ----------------
    def _build_ui(self):
        top = ttk.Frame(self, padding=6); top.pack(fill="x")
        ttk.Label(top, text="WifiIDS", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Label(top, text="  Wireless (IEEE 802.11) Intrusion Detection - control panel",
                  foreground="#555").pack(side="left")
        self.status = ttk.Label(top, text="idle", foreground="#0a7"); self.status.pack(side="right")

        nb = ttk.Notebook(self); nb.pack(fill="both", expand=False, padx=8, pady=(0, 6))
        nb.add(self._tab_env(nb), text="1. Environment")
        nb.add(self._tab_dataset(nb), text="2. Dataset")
        nb.add(self._tab_analysis(nb), text="3. Analysis")
        nb.add(self._tab_realtime(nb), text="4. Real-Time & Dashboard")
        nb.add(self._tab_capture(nb), text="5. Live Capture & Custom Data")

        # log area (always visible)
        lf = ttk.LabelFrame(self, text="Log", padding=4); lf.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        bar = ttk.Frame(lf); bar.pack(fill="x")
        ttk.Button(bar, text="Stop running task", command=self.stop).pack(side="left")
        ttk.Button(bar, text="Clear log", command=lambda: self.logbox.delete("1.0", "end")).pack(side="left", padx=6)
        self.logbox = scrolledtext.ScrolledText(lf, height=16, bg="#0f1720", fg="#d5dde5",
                                                insertbackground="#d5dde5", font=("Consolas", 9))
        self.logbox.pack(fill="both", expand=True, pady=(4, 0))
        for tag, col in {"error": "#ff6b6b", "warn": "#e6a100", "ok": "#3ddc84", "info": "#7aa2d6"}.items():
            self.logbox.tag_config(tag, foreground=col)

    def _field(self, parent, label, key, row, width=42, show=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=3)
        e = ttk.Entry(parent, textvariable=self.vars[key], width=width, show=show)
        e.grid(row=row, column=1, sticky="w", padx=6, pady=3)
        return e

    def _notes(self, parent, title, items):
        """A titled panel (packed on the right) listing name -> explanation pairs."""
        lf = ttk.LabelFrame(parent, text=title, padding=8)
        lf.pack(fill="both", expand=True)
        for i, (name, desc) in enumerate(items):
            ttk.Label(lf, text=name, font=("Segoe UI", 9, "bold"),
                      foreground="#0072B2").grid(row=2 * i, column=0, sticky="w", pady=(4, 0))
            ttk.Label(lf, text=desc, foreground="#555", wraplength=430,
                      justify="left").grid(row=2 * i + 1, column=0, sticky="w", padx=(10, 0))
        return lf

    def _split(self, nb):
        """Return (outer, left, right): left holds controls, right holds the notes."""
        outer = ttk.Frame(nb, padding=8)
        outer.columnconfigure(0, weight=0)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)
        left = ttk.Frame(outer); left.grid(row=0, column=0, sticky="nw")
        right = ttk.Frame(outer); right.grid(row=0, column=1, sticky="nsew", padx=(24, 0))
        return outer, left, right

    def _tab_env(self, nb):
        outer, f, right = self._split(nb)
        self._field(f, "Kafka bootstrap", "kafka", 0)
        self._field(f, "Redis URL", "redis", 1)
        self._field(f, "MSSQL driver", "mssql_driver", 2)
        self._field(f, "MSSQL server", "mssql_server", 3)
        self._field(f, "MSSQL database", "mssql_db", 4)
        ttk.Label(f, text="MSSQL uses Windows authentication (Trusted Connection) - no DB "
                  "user/password needed. Change server/database above, then Save settings.",
                  foreground="#777", wraplength=360, justify="left").grid(
            row=5, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 4))
        self._field(f, "Elasticsearch URL", "es_url", 6)
        self._field(f, "Elasticsearch user", "es_user", 7)
        self._field(f, "Elasticsearch password", "es_pass", 8, show="*")
        ttk.Label(f, text="Elasticsearch is OPTIONAL (archives alerts/logs). Leave the password "
                  "empty if unused - dataset, benchmark and monitor all run without it.",
                  foreground="#777", wraplength=360, justify="left").grid(
            row=9, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 4))
        btns = ttk.Frame(f); btns.grid(row=10, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(btns, text="Save settings (.env)", command=self.save_env).pack(side="left", padx=4)
        ttk.Button(btns, text="Check Docker", command=self.check_docker).pack(side="left", padx=4)
        ttk.Button(btns, text="Start infrastructure", command=self.start_infra).pack(side="left", padx=4)
        btns2 = ttk.Frame(f); btns2.grid(row=11, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(btns2, text="Create Kafka topics",
                   command=lambda: self.run_py("create_topics.py", [])).pack(side="left", padx=4)
        ttk.Button(btns2, text="Verify environment",
                   command=lambda: self.run_py("verify_env.py", [])).pack(side="left", padx=4)
        self._notes(right, "What each button does", [
            ("Save settings (.env)",
             "Writes the values above to the project .env file so every script and a future "
             "launch of this app reuse them. Passwords stay only in .env (never in the code)."),
            ("Check Docker",
             "Asks the Docker engine for its version. If it is not running you get a clear "
             "message telling you to start Docker Desktop and retry."),
            ("Start infrastructure",
             "Runs 'docker compose up -d' to bring up Kafka, Prometheus, Grafana and MLflow "
             "as background containers (they auto-restart after a reboot)."),
            ("Create Kafka topics",
             "Creates the five WIDS topics (raw-frames, feature-vectors, detections, "
             "responses, audit). Safe to re-run - existing topics are left as they are."),
            ("Verify environment",
             "Checks every service (Kafka, Redis, MSSQL, Elasticsearch, Prometheus, Grafana, "
             "MLflow) and prints a PASS/WARN/FAIL table so you know what is ready."),
        ])
        return outer

    def _tab_dataset(self, nb):
        outer, f, right = self._split(nb)
        self._field(f, "AWID3 CSV root folder", "awid_root", 0)
        self._field(f, "Output dataset CSV", "dataset_csv", 1)
        self._field(f, "Normal cap", "normal_cap", 2, width=12)
        self._field(f, "Attack cap (per class)", "attack_cap", 3, width=12)
        ttk.Checkbutton(f, text="Rebuild (delete existing dataset and recreate it)",
                        variable=self.rebuild_var).grid(row=4, column=0, columnspan=2, sticky="w", padx=6, pady=(8, 0))
        ttk.Button(f, text="Build dataset", command=self.build_dataset).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self._notes(right, "What this does and what result to expect", [
            ("Build dataset",
             "Reads the raw AWID3 per-attack CSVs, samples up to the caps you set per class, "
             "cleans and encodes them, and writes one curated training CSV (our reference build "
             "is 74,270 rows, 40 features, 14 classes)."),
            ("Built only once",
             "If the output CSV already exists it is skipped, so you do not rebuild on every "
             "run. Tick 'Rebuild' to delete and regenerate it (e.g. after changing the caps)."),
            ("Getting the raw data",
             "Download AWID3 from https://icsdweb.aegean.gr/awid/ and point the root folder at "
             "its per-attack CSV directories."),
        ])
        return outer

    def _tab_analysis(self, nb):
        outer, f, right = self._split(nb)
        self._field(f, "Dataset CSV", "dataset_csv", 0)
        self._field(f, "CV folds", "cv", 1, width=10)
        self._field(f, "Hybrid epochs", "epochs", 2, width=10)
        g = ttk.Frame(f); g.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(g, text="Model benchmark",
                   command=lambda: self.run_py("benchmark.py", ["--csv", self.g("dataset_csv"), "--cv", self.g("cv")])).pack(side="left", padx=4)
        ttk.Button(g, text="Feature selection",
                   command=lambda: self.run_py("feature_select.py", ["--csv", self.g("dataset_csv")])).pack(side="left", padx=4)
        ttk.Button(g, text="Scientific figures",
                   command=lambda: self.run_py("scientific_benchmark.py", [])).pack(side="left", padx=4)
        g2 = ttk.Frame(f); g2.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(g2, text="Zero-day detection",
                   command=lambda: self.run_py("demo_phase11.py", ["--csv", self.g("dataset_csv")])).pack(side="left", padx=4)
        ttk.Button(g2, text="Explainability (SHAP)",
                   command=lambda: self.run_py("demo_phase12.py", ["--csv", self.g("dataset_csv")])).pack(side="left", padx=4)
        ttk.Button(g2, text="Train hybrid model",
                   command=lambda: self.run_py("train_hybrid.py", ["--csv", self.g("dataset_csv"), "--epochs", self.g("epochs")])).pack(side="left", padx=4)
        self._notes(right, "What each analysis does and what result to expect", [
            ("Model benchmark",
             "Trains ~10 classifiers with stratified k-fold cross-validation and reports "
             "accuracy, macro precision/recall/F1, ROC-AUC, training time and per-sample "
             "latency. Output: comparison table + confusion matrix in data/reports/. "
             "Best model is typically XGBoost (macro-F1 ~0.976, ROC-AUC ~0.9998)."),
            ("Feature selection",
             "Ranks the 40 features by importance and finds the smallest subset that keeps "
             "accuracy. Output: ranking + an F1-vs-#features curve. Accuracy usually plateaus "
             "around 15-20 features, so most can be dropped with almost no loss."),
            ("Scientific figures",
             "Regenerates all paper-quality figures at 300 DPI (per-class F1, ROC curves, "
             "confusion matrix, feature-count curve). Output: PNGs in data/reports/figures/."),
            ("Zero-day detection",
             "Trains an AutoEncoder on NORMAL traffic only, then flags attacks as "
             "reconstruction-error anomalies (unsupervised - catches unseen attacks). "
             "Output: ROC-AUC ~0.99 at roughly a 5% false-positive rate."),
            ("Explainability (SHAP)",
             "Computes SHAP values to show which features drive each detection. Output: global "
             "importance + per-class summary plots. Top features are domain-consistent "
             "(rate, timing and signal fields), which builds trust in the model."),
            ("Train hybrid model",
             "Trains the deep CNN+Transformer model over the chosen epochs. Slower than the "
             "tree models. Output: a saved model plus accuracy / macro-F1 (~0.93)."),
        ])
        return outer

    def _tab_realtime(self, nb):
        outer, f, right = self._split(nb)
        self._field(f, "Dataset CSV", "dataset_csv", 0)
        self._field(f, "Rate (records/sec)", "rate", 1, width=10)
        self._field(f, "Alert confidence threshold", "threshold", 2, width=10)
        self._field(f, "Duration (sec, if not looping)", "seconds", 3, width=10)
        self._field(f, "Metrics port", "metrics_port", 4, width=10)
        ttk.Checkbutton(f, text="Loop continuously (for the live dashboard)",
                        variable=self.loop_var).grid(row=5, column=1, sticky="w", padx=6)
        g = ttk.Frame(f); g.grid(row=6, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(g, text="Start real-time monitor", command=self.start_monitor).pack(side="left", padx=4)
        ttk.Button(g, text="Open Grafana dashboard",
                   command=lambda: webbrowser.open("http://localhost:3000")).pack(side="left", padx=4)
        ttk.Button(g, text="Generate SOC dashboard (HTML)",
                   command=lambda: self.run_py("dashboard.py", [])).pack(side="left", padx=4)
        ttk.Label(f, text="Grafana: http://localhost:3000  (admin / admin) -> "
                  "\"Wireless IDS - Real-Time Alerts\". Live 802.11 capture needs a monitor-mode "
                  "adapter; without one this replays real AWID3 traffic as a live stream.",
                  foreground="#777", wraplength=360, justify="left").grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(12, 0))
        self._notes(right, "What each action does and what result to expect", [
            ("Start real-time monitor",
             "Trains an XGBoost model on the dataset, then replays held-out rows as a live "
             "stream at the chosen rate. Raises an alert whenever the attack confidence is at "
             "or above the threshold, writes every event to MSSQL (detection_events) and "
             "publishes Prometheus metrics on the metrics port (records, alerts by type, "
             "throughput, last-alert confidence). Use 'Loop continuously' to keep it feeding "
             "the live dashboard."),
            ("Open Grafana dashboard",
             "Opens the live SOC dashboard in your browser: total records, total alerts, "
             "throughput (records/sec), alerts-per-second and an alerts-by-attack-type donut, "
             "all refreshing in real time from the metrics above."),
            ("Generate SOC dashboard (HTML)",
             "Builds a single self-contained HTML report from the stored detection_events "
             "(recent alerts, counts per attack type). Shareable offline - no server needed."),
        ])
        return outer

    def _tab_capture(self, nb):
        outer, f, right = self._split(nb)
        r = 0
        ttk.Label(f, text="A) Check this machine's capture capability", font=("Segoe UI", 9, "bold")).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(0, 2)); r += 1
        ttk.Button(f, text="Check capture capability",
                   command=lambda: self.run_py("capture_check.py", [])).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(0, 10)); r += 1

        ttk.Label(f, text="B) Convert a captured PCAP to a features CSV", font=("Segoe UI", 9, "bold")).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(4, 2)); r += 1
        self._field(f, "PCAP file (.pcap/.pcapng)", "pcap_in", r); r += 1
        self._field(f, "Output features CSV", "pcap_out", r); r += 1
        self._field(f, "Window (frames)", "pcap_window", r, width=10); r += 1
        self._field(f, "Label for all rows (optional)", "pcap_label", r, width=20); r += 1
        ttk.Button(f, text="Convert PCAP to features CSV", command=self.convert_pcap).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(2, 10)); r += 1

        ttk.Label(f, text="C) Analyze any labeled CSV dataset (file or folder)", font=("Segoe UI", 9, "bold")).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(4, 2)); r += 1
        self._field(f, "Dataset CSV or folder", "custom_csv", r); r += 1
        self._field(f, "Label column (blank = auto)", "custom_label", r, width=20); r += 1
        self._field(f, "Sample rows (0 = all)", "custom_sample", r, width=12); r += 1
        self._field(f, "CV folds", "cv", r, width=10); r += 1
        ttk.Checkbutton(f, text="Fast models only (tree/boosting - for very large datasets)",
                        variable=self.fast_var).grid(row=r, column=0, columnspan=2, sticky="w", padx=6, pady=(2, 0)); r += 1
        ttk.Button(f, text="Analyze dataset", command=self.analyze_custom).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(2, 0)); r += 1

        self._notes(right, "Real-network data & other datasets", [
            ("Check capture capability",
             "Lists your network interfaces and whether Scapy/Npcap is present. Live 802.11 "
             "capture needs a monitor-mode-capable adapter (best on Linux + e.g. Intel AX210 "
             "or an Alfa card). Ordinary Wi-Fi cards in managed mode cannot record 802.11 "
             "headers."),
            ("Collecting the data",
             "Put the adapter in monitor mode (Linux: airmon-ng start wlan0) and capture with "
             "Wireshark, tcpdump or airodump-ng, saving a .pcap/.pcapng. On this Windows "
             "laptop capture is limited; collect on a Linux sensor and copy the file here."),
            ("Convert PCAP to features CSV",
             "Parses the .pcap, groups frames into windows and computes the 300+ feature "
             "vector per window. Capture normal and attack traffic separately, set a Label "
             "for each, then concatenate the CSVs into one labeled training set."),
            ("Analyze dataset",
             "Runs the full model benchmark on ANY labeled dataset (AWID3, CIC-IDS-2017, "
             "CSE-CIC-IDS2018, or your own captured+labeled data). Reads CSV or Parquet - a "
             "single file OR a folder (all files concatenated). Auto-detects the label "
             "column, cleans features (inf/NaN, id/time columns), and prints a ranked table "
             "+ best-model confusion matrix. For large sets use 'Sample rows' to cap the "
             "size. Report saved to data/reports/analyze_<name>.json. Tested on CICIDS: "
             "XGBoost macro-F1 ~0.98."),
            ("Live streaming option",
             "For a continuous live feed use the Kafka pipeline: run_sensor.py --source "
             "capture --iface <NIC> -> run_feature_extractor.py -> run_inference.py. See the "
             "README section 'Real-network data collection'."),
        ])
        return outer

    # ---------------- helpers ----------------
    def g(self, key):
        return self.vars[key].get().strip()

    def log(self, msg, level="info"):
        self.q.put((msg, level))

    def _drain_log(self):
        try:
            while True:
                msg, level = self.q.get_nowait()
                self.logbox.insert("end", msg + "\n", level)
                self.logbox.see("end")
        except queue.Empty:
            pass
        self.after(80, self._drain_log)

    def _env(self):
        e = dict(os.environ)
        e.update({
            "WIDS_KAFKA_BOOTSTRAP": self.g("kafka"),
            "WIDS_REDIS_URL": self.g("redis"),
            "WIDS_MSSQL_DRIVER": self.g("mssql_driver"),
            "WIDS_MSSQL_SERVER": self.g("mssql_server"),
            "WIDS_MSSQL_DATABASE": self.g("mssql_db"),
            "WIDS_ES_URL": self.g("es_url"),
            "WIDS_ES_USERNAME": self.g("es_user"),
            "WIDS_ES_PASSWORD": self.g("es_pass"),
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
        })
        return e

    def save_env(self):
        lines = [
            f"WIDS_KAFKA_BOOTSTRAP={self.g('kafka')}",
            f"WIDS_REDIS_URL={self.g('redis')}",
            f"WIDS_MSSQL_DRIVER={self.g('mssql_driver')}",
            f"WIDS_MSSQL_SERVER={self.g('mssql_server')}",
            f"WIDS_MSSQL_DATABASE={self.g('mssql_db')}",
            "WIDS_MSSQL_ENCRYPT=no", "WIDS_MSSQL_TRUST_CERT=yes",
            f"WIDS_ES_URL={self.g('es_url')}",
            f"WIDS_ES_USERNAME={self.g('es_user')}",
            f"WIDS_ES_PASSWORD={self.g('es_pass')}",
            "WIDS_ES_VERIFY_CERTS=false", "WIDS_ES_INDEX_PREFIX=wids-",
        ]
        (ROOT / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.log("Saved settings to .env", "ok")

    def check_docker(self):
        try:
            r = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"],
                               capture_output=True, text=True, timeout=12)
            if r.returncode == 0:
                self.log(f"Docker engine OK (server {r.stdout.strip()}).", "ok")
                return True
            self.log("ERROR: Docker is installed but the engine is not responding. "
                     "Start Docker Desktop, wait ~30s, then retry.", "error")
        except FileNotFoundError:
            self.log("ERROR: Docker not found. Install Docker Desktop.", "error")
        except Exception as e:
            self.log(f"ERROR: Docker check failed: {e}. Start Docker Desktop and retry.", "error")
        return False

    def port_free(self, port):
        try:
            s = socket.socket(); s.bind(("127.0.0.1", int(port))); s.close(); return True
        except Exception:
            return False

    # ---------------- task runner ----------------
    def run_cmd(self, argv, title):
        if self.proc is not None and self.proc.poll() is None:
            self.log("WARNING: a task is already running. Stop it first.", "warn")
            return
        self.log(f"$ {' '.join(argv)}", "info")
        self.status.config(text=f"running: {title}", foreground="#e6a100")

        def worker():
            try:
                self.proc = subprocess.Popen(argv, cwd=str(ROOT), env=self._env(),
                                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                             text=True, bufsize=1,
                                             encoding="utf-8", errors="replace")
            except FileNotFoundError as e:
                self.log(f"ERROR: cannot run ({e}).", "error")
                self.status.config(text="idle", foreground="#0a7"); return
            for line in self.proc.stdout:
                line = line.rstrip("\n")
                low = line.lower()
                lvl = ("error" if ("error" in low or "traceback" in low or "fail" in low)
                       else "warn" if "warn" in low
                       else "ok" if ("pass" in low or "result:" in low) else "info")
                self.log("  " + line, lvl)
            rc = self.proc.wait()
            self.log(f"[{title}] finished (exit {rc})", "ok" if rc == 0 else "error")
            self.status.config(text="idle", foreground="#0a7")

        threading.Thread(target=worker, daemon=True).start()

    def run_py(self, script, args):
        self.run_cmd([PYTHON, str(SCRIPTS / script)] + args, script.replace(".py", ""))

    def build_dataset(self):
        out = ROOT / self.g("dataset_csv")
        if out.exists():
            if self.rebuild_var.get():
                try:
                    out.unlink()
                    self.log(f"Rebuild enabled: deleted existing {out.name}, regenerating...", "warn")
                except Exception as e:
                    self.log(f"ERROR: could not delete {out}: {e}", "error")
                    return
            else:
                self.log(f"Dataset already exists at {out} - skipping (delete to rebuild). "
                         "Tick 'Rebuild' to delete and recreate it.", "warn")
                return
        self.run_py("build_awid3.py",
                    ["--root", self.g("awid_root"), "--out", self.g("dataset_csv"),
                     "--normal-cap", self.g("normal_cap"), "--attack-cap", self.g("attack_cap")])

    def convert_pcap(self):
        pcap = ROOT / self.g("pcap_in")
        if not pcap.exists():
            self.log(f"WARNING: PCAP not found at {pcap}. Capture one first (see the notes) "
                     "or fix the path.", "warn")
            return
        args = ["--pcap", self.g("pcap_in"), "--out", self.g("pcap_out"),
                "--window", self.g("pcap_window")]
        label = self.g("pcap_label")
        if label:
            args += ["--label", label]
        self.run_py("pcap_to_csv.py", args)

    def analyze_custom(self):
        csv = ROOT / self.g("custom_csv")
        if not csv.exists():
            self.log(f"WARNING: dataset not found at {csv}.", "warn")
            return
        args = ["--csv", self.g("custom_csv"), "--cv", self.g("cv")]
        label = self.g("custom_label")
        if label:
            args += ["--label", label]
        sample = self.g("custom_sample")
        if sample and sample != "0":
            args += ["--sample", sample]
        if self.fast_var.get():
            args.append("--fast")
        self.run_py("analyze_dataset.py", args)

    def start_infra(self):
        if not self.check_docker():
            return
        self.run_cmd(["docker", "compose", "up", "-d"], "docker compose up")

    def start_monitor(self):
        csv = ROOT / self.g("dataset_csv")
        if not csv.exists():
            self.log(f"WARNING: dataset not found at {csv}. Run 'Build dataset' first.", "warn")
            return
        port = self.g("metrics_port")
        if not self.port_free(port):
            self.log(f"WARNING: metrics port {port} is already in use. "
                     "Choose another port or stop the process using it.", "warn")
        args = ["--csv", self.g("dataset_csv"), "--rate", self.g("rate"),
                "--threshold", self.g("threshold"), "--metrics-port", port]
        if self.loop_var.get():
            args.append("--loop")
        else:
            args += ["--seconds", self.g("seconds")]
        self.run_py("live_monitor.py", args)

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            self.log("Stop requested for the running task.", "warn")
        else:
            self.log("No task is currently running.", "info")


if __name__ == "__main__":
    WifiIDS().mainloop()
