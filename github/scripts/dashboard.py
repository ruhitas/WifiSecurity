"""Generate a self-contained SOC dashboard (HTML) from MSSQL detection_events.

Reads the live alerts persisted by the pipeline / live_monitor and renders KPIs,
an alerts-by-attack-type chart, and a recent-alerts table into a single HTML file
that can be opened or shared internally (no external dependencies).
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.connections import get_mssql  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "reports" / "soc_dashboard.html"
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9",
           "#F0E442", "#999999", "#882255", "#44AA99", "#DDCC77", "#AA4499", "#117733"]


def fetch():
    conn = get_mssql(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*), AVG(confidence) FROM detection_events")
    total, avgconf = cur.fetchone()
    cur.execute("SELECT attack_type, COUNT(*) FROM detection_events GROUP BY attack_type ORDER BY COUNT(*) DESC")
    by_type = cur.fetchall()
    cur.execute("SELECT DISTINCT sensor_id FROM detection_events")
    sensors = [r[0] for r in cur.fetchall()]
    cur.execute("""SELECT TOP 15 attack_type, sensor_id, confidence, created_at
                   FROM detection_events ORDER BY created_at DESC""")
    recent = cur.fetchall()
    conn.close()
    return total or 0, float(avgconf or 0), by_type, sensors, recent


def build_html(total, avgconf, by_type, sensors, recent):
    maxc = max((c for _, c in by_type), default=1)
    bars = "".join(
        f'<div class="bar"><span class="lbl">{t}</span>'
        f'<span class="track"><span class="fill" style="width:{max(2,int(100*c/maxc))}%;background:{PALETTE[i%len(PALETTE)]}"></span></span>'
        f'<span class="val">{c}</span></div>'
        for i, (t, c) in enumerate(by_type))
    rows = "".join(
        f"<tr><td><span class='sev'></span>{t}</td><td>{s}</td><td>{conf:.2f}</td><td>{ts}</td></tr>"
        for t, s, conf, ts in recent)
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>WIDS SOC Dashboard</title>
<style>
 body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#0f1720;color:#e6edf3}}
 header{{background:#111c2b;padding:18px 26px;border-bottom:2px solid #0072B2}}
 h1{{margin:0;font-size:20px;color:#58a6ff}} .sub{{color:#8b98a5;font-size:13px}}
 .kpis{{display:flex;gap:16px;padding:22px 26px;flex-wrap:wrap}}
 .kpi{{background:#152233;border:1px solid #22344a;border-radius:10px;padding:16px 22px;min-width:150px}}
 .kpi .n{{font-size:30px;font-weight:700;color:#fff}} .kpi .k{{color:#8b98a5;font-size:12px;text-transform:uppercase;letter-spacing:.05em}}
 .grid{{display:grid;grid-template-columns:1fr 1fr;gap:22px;padding:0 26px 26px}}
 .card{{background:#152233;border:1px solid #22344a;border-radius:10px;padding:18px}}
 .card h2{{margin:0 0 14px;font-size:15px;color:#c9d6e3}}
 .bar{{display:flex;align-items:center;gap:10px;margin:7px 0;font-size:13px}}
 .bar .lbl{{width:130px;color:#c9d6e3}} .bar .track{{flex:1;background:#0f1720;border-radius:5px;height:16px;overflow:hidden}}
 .bar .fill{{display:block;height:100%}} .bar .val{{width:52px;text-align:right;color:#8b98a5}}
 table{{width:100%;border-collapse:collapse;font-size:13px}}
 th,td{{text-align:left;padding:7px 8px;border-bottom:1px solid #22344a}} th{{color:#8b98a5;font-weight:600}}
 .sev{{display:inline-block;width:8px;height:8px;border-radius:50%;background:#D55E00;margin-right:8px}}
 @media(max-width:820px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body>
<header><h1>&#128225; Wireless IDS &mdash; SOC Dashboard</h1>
<div class='sub'>IEEE 802.11 intrusion alerts &middot; source: MSSQL detection_events &middot; sensors: {', '.join(sensors) or '-'}</div></header>
<div class='kpis'>
 <div class='kpi'><div class='n'>{total}</div><div class='k'>Total alerts</div></div>
 <div class='kpi'><div class='n'>{len(by_type)}</div><div class='k'>Attack types</div></div>
 <div class='kpi'><div class='n'>{avgconf:.2f}</div><div class='k'>Avg confidence</div></div>
 <div class='kpi'><div class='n'>{len(sensors)}</div><div class='k'>Sensors</div></div>
</div>
<div class='grid'>
 <div class='card'><h2>Alerts by attack type</h2>{bars}</div>
 <div class='card'><h2>Recent alerts</h2><table><tr><th>Attack</th><th>Sensor</th><th>Conf.</th><th>Time (UTC)</th></tr>{rows}</table></div>
</div></body></html>"""


def main():
    total, avgconf, by_type, sensors, recent = fetch()
    OUT.write_text(build_html(total, avgconf, by_type, sensors, recent), encoding="utf-8")
    print(f"SOC dashboard written: {OUT}")
    print(f"total alerts={total} avg_conf={avgconf:.3f} attack_types={len(by_type)} sensors={sensors}")
    print("by type:", ", ".join(f"{t}:{c}" for t, c in by_type))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
