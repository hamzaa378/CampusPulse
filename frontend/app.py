"""CampusPulse organizer dashboard. Start: streamlit run frontend/app.py"""
import os
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
API_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000/api").rstrip("/")
METRICS = ["temperature", "air_quality", "occupancy", "humidity", "noise", "other"]
OP_MAP = {">": "GT", ">=": "GTE", "<": "LT", "<=": "LTE", "=": "EQ"}

st.set_page_config(page_title="CampusPulse | GDG Tech", page_icon="📡", layout="wide")
st.markdown("""<style>
.block-container {padding-top:1.4rem;max-width:1400px}
[data-testid="stMetric"] {padding:13px;border:1px solid #c2ccdc55;border-radius:12px}
</style>""", unsafe_allow_html=True)


def call(method, route, data=None, sensor=False, timeout=20):
    headers = {"Accept": "application/json"}
    if sensor:
        key = st.session_state.get("sensor_key", "")
        if key:
            headers["X-Sensor-Key"] = key
    elif st.session_state.get("token"):
        headers["Authorization"] = f"Token {st.session_state['token']}"
    try:
        response = requests.request(method, f"{API_URL}/{route.lstrip('/')}", json=data,
                                    headers=headers, timeout=timeout)
        try:
            payload = response.json()
        except ValueError:
            payload = {"detail": response.text[:1000]}
        if response.status_code >= 400:
            st.error(f"API {response.status_code}: {payload}")
            return None
        return payload
    except requests.RequestException as exc:
        st.error(f"Cannot reach Django API at {API_URL}: {exc}")
        return None


def list_all(endpoint):
    items = call("GET", endpoint)
    if items is None:
        return []
    return items.get("results", []) if isinstance(items, dict) else items


with st.sidebar:
    st.markdown("## 📡 CampusPulse")
    st.caption("GDG Tech · Campus sensor operations")
    st.caption(f"Backend: `{API_URL}`")
    if "token" not in st.session_state:
        st.session_state.token = None
    if "sensor_key" not in st.session_state:
        st.session_state.sensor_key = os.environ.get("SENSOR_API_KEY", "")
    if st.session_state.token:
        st.success(f"Organizer: {st.session_state.get('username', 'authenticated')}")
        if st.button("Log out", use_container_width=True):
            st.session_state.token = None
            st.session_state.username = None
            st.rerun()
    page = st.radio("Workspace", ["Overview", "Sensors", "Alert rules", "Alerts", "Sensor simulator", "Performance lab", "API status"],
                    label_visibility="collapsed")
    st.divider()
    with st.expander("Sensor ingest key", expanded=False):
        st.session_state.sensor_key = st.text_input("X-Sensor-Key", value=st.session_state.sensor_key,
                                                   type="password", help="Used only for simulator ingestion.")

if not st.session_state.token:
    st.title("CampusPulse")
    st.write("Sign in as a Django staff organizer to manage devices, rules and alerts.")
    with st.form("signin"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Sign in", type="primary")
    if submit:
        r = call("POST", "auth/login/", {"username": username, "password": password})
        if r:
            st.session_state.token = r["token"]
            st.session_state.username = r["username"]
            st.rerun()
    st.info("First run: create an organizer with `python manage.py createsuperuser`.")
    st.stop()

if page == "Overview":
    st.title("Campus operations overview")
    data = call("GET", "dashboard/")
    if data:
        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Sensors", data["sensors"])
        c2.metric("Enabled rules", data["enabled_rules"])
        c3.metric("Total readings", data["total_readings"])
        c4.metric("Queued", data["pending_readings"])
        c5.metric("Open alerts", data["alerts"]["open"])
        st.subheader("Alert lifecycle")
        st.bar_chart(pd.Series(data["alerts"], name="Alerts"))
        left,right = st.columns([3,2])
        with left:
            st.subheader("Most recent alerts")
            rows = data.get("recent_alerts", [])
            if rows:
                st.dataframe(pd.DataFrame(rows)[["id", "sensor_id", "rule_name", "severity", "status", "trigger_value", "created_at"]],
                             use_container_width=True, hide_index=True)
            else:
                st.info("No alerts yet. Add a rule and send simulated readings.")
        with right:
            st.subheader("Last observations by sensor")
            st.dataframe(pd.DataFrame(data.get("sensor_metrics", [])), use_container_width=True, hide_index=True)
        st.subheader("Recent reading series")
        recent = call("GET", "readings/?limit=300")
        if recent:
            df = pd.DataFrame(recent)
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            options = sorted(df["sensorId"].unique())
            selected = st.selectbox("Sensor", options)
            sub = df[df["sensorId"] == selected]
            sub = sub.pivot_table(index="timestamp", columns="type", values="value", aggfunc="mean")
            st.line_chart(sub.sort_index())
        if st.button("Process one alert-worker batch now (test mode)"):
            result = call("POST", "worker/process-once/", {"limit": 500})
            if result:
                st.success(result)

elif page == "Sensors":
    st.title("Registered sensors")
    sensors = list_all("sensors/?page_size=100")
    if sensors:
        st.dataframe(pd.DataFrame(sensors)[["id", "sensor_id", "name", "location", "is_active"]],
                     use_container_width=True, hide_index=True)
    with st.expander("Register new sensor", expanded=True):
        with st.form("new_sensor", clear_on_submit=True):
            c1,c2 = st.columns(2)
            sensor_id = c1.text_input("Sensor ID", placeholder="library-floor-2")
            name = c2.text_input("Display name", placeholder="Library temperature")
            location = st.text_input("Campus location")
            active = st.checkbox("Active", value=True)
            if st.form_submit_button("Register sensor", type="primary"):
                result = call("POST", "sensors/", {"sensor_id": sensor_id, "name": name,
                                                     "location": location, "is_active": active})
                if result:
                    st.success("Sensor registered. Refresh to see changes.")
    if sensors:
        st.subheader("Enable or disable an existing sensor")
        chosen = st.selectbox("Choose sensor", sensors, format_func=lambda x:f"{x['sensor_id']} ({'active' if x['is_active'] else 'inactive'})")
        enable = st.checkbox("Active state", value=chosen["is_active"], key=f"sensor_{chosen['id']}")
        if st.button("Update sensor"):
            if call("PATCH", f"sensors/{chosen['id']}/", {"is_active": enable}):
                st.success("Sensor updated")

elif page == "Alert rules":
    st.title("Alert rules")
    sensors = list_all("sensors/?page_size=100")
    rules = list_all("rules/?page_size=100")
    if rules:
        st.dataframe(pd.DataFrame(rules)[["id", "name", "sensor_id", "metric_type", "kind", "operator", "threshold", "enabled"]],
                     use_container_width=True, hide_index=True)
    st.subheader("Create or edit a rule")
    options = {"Create new rule": None}
    options.update({f"#{r['id']} · {r['name']}": r for r in rules})
    picked = st.selectbox("Rule to edit", list(options))
    selected = options[picked]
    with st.form("rule_form"):
        name = st.text_input("Rule name", value=selected["name"] if selected else "High temperature")
        sensor_options = {"All sensors": None}
        sensor_options.update({f"{s['sensor_id']} · {s['location']}": s["id"] for s in sensors})
        match_label = next((label for label, id_ in sensor_options.items() if selected and id_ == selected["sensor"]), "All sensors")
        sensor_label = st.selectbox("Sensor scope", list(sensor_options), index=list(sensor_options).index(match_label))
        c1,c2,c3 = st.columns(3)
        metric = c1.selectbox("Metric", METRICS, index=METRICS.index(selected["metric_type"]) if selected else 0)
        kind = c2.selectbox("Evaluation", ["instant", "window"], index=["instant", "window"].index(selected["kind"]) if selected else 0)
        severity = c3.selectbox("Severity", ["info", "warning", "critical"],
                                index=["info", "warning", "critical"].index(selected["severity"]) if selected else 1)
        c4,c5,c6 = st.columns(3)
        old_op = next((label for label, val in OP_MAP.items() if selected and val == selected["operator"]), ">")
        op = c4.selectbox("Condition", list(OP_MAP), index=list(OP_MAP).index(old_op))
        threshold = c5.number_input("Threshold", value=float(selected["threshold"]) if selected else 32.0, step=0.5)
        enabled = c6.checkbox("Enabled", value=selected["enabled"] if selected else True)
        c7,c8 = st.columns(2)
        window = c7.number_input("Rolling window in seconds", min_value=30, max_value=86400,
                                 value=int(selected["window_seconds"]) if selected else 600)
        samples = c8.number_input("Minimum window samples", min_value=1, max_value=100000,
                                  value=int(selected["min_samples"]) if selected else 2)
        if st.form_submit_button("Save alert rule", type="primary"):
            payload = {"name": name, "sensor": sensor_options[sensor_label], "metric_type": metric,
                       "kind": kind, "operator": OP_MAP[op], "threshold": f"{threshold:.4f}",
                       "window_seconds": int(window), "min_samples": int(samples),
                       "severity": severity, "enabled": enabled}
            route = "rules/" if selected is None else f"rules/{selected['id']}/"
            result = call("POST" if selected is None else "PATCH", route, payload)
            if result:
                st.success("Rule saved. Incoming queued readings will use current rules.")

elif page == "Alerts":
    st.title("Alert management")
    filter_ = st.selectbox("Alert status", ["all", "open", "acknowledged", "resolved"])
    route = "alerts/" if filter_ == "all" else f"alerts/?status={filter_}"
    alerts = list_all(route)
    if alerts:
        st.dataframe(pd.DataFrame(alerts)[["id", "sensor_id", "rule_name", "metric_type", "severity", "status", "trigger_value", "created_at"]],
                     use_container_width=True, hide_index=True)
        candidate = st.selectbox("Choose alert", alerts, format_func=lambda x:
                                 f"#{x['id']} · {x['sensor_id']} · {x['rule_name']} · {x['status']}")
        st.info(candidate["message"])
        c1,c2 = st.columns(2)
        if c1.button("Acknowledge", disabled=candidate["status"] != "open", type="primary"):
            if call("POST", f"alerts/{candidate['id']}/acknowledge/"):
                st.success("Acknowledged")
                st.rerun()
        if c2.button("Resolve", disabled=candidate["status"] == "resolved"):
            if call("POST", f"alerts/{candidate['id']}/resolve/"):
                st.success("Resolved")
                st.rerun()
    else:
        st.info("No matching alerts.")

elif page == "Sensor simulator":
    st.title("Sensor simulator & ingestion test")
    st.write("Generate readings and send a real POST request to the Django batch ingestion API.")
    sensors = [x for x in list_all("sensors/?page_size=100") if x["is_active"]]
    if not sensors:
        st.warning("Register and enable at least one sensor first.")
    else:
        with st.form("sim_form"):
            sensor = st.selectbox("Sensor", sensors, format_func=lambda x:x["sensor_id"])
            c1,c2,c3 = st.columns(3)
            metric = c1.selectbox("Metric type", METRICS)
            count = c2.number_input("Batch size", min_value=1, max_value=10000, value=100, step=100)
            base = c3.number_input("Base value", value=34.0, step=0.5)
            variation = st.slider("Random fluctuation (+/-)", 0.0, 20.0, 2.0)
            use_key = st.checkbox("Use sensor API key (instead of organizer token)", value=False)
            if st.form_submit_button("Send batch", type="primary"):
                now = datetime.now(timezone.utc)
                # Microseconds keep sequential readings distinct, especially for 10k/second.
                data = []
                for i in range(int(count)):
                    stamped = now - timedelta(seconds=(int(count) - 1 - i) / max(int(count), 1))
                    data.append({"sensorId":sensor["sensor_id"], "type":metric,
                                 "value":round(base + random.uniform(-variation, variation), 4),
                                 "timestamp":stamped.isoformat()})
                t0 = time.perf_counter()
                result = call("POST", "readings/batch/", {"readings":data}, sensor=use_key, timeout=120)
                elapsed = time.perf_counter() - t0
                if result:
                    st.success(f"Server accepted request in {elapsed:.3f}s (client wall time).")
                    st.json(result)
                    st.session_state.last_ingest_diagnostics = result
                    st.metric("Observed client requests/sec", f"{int(count)/max(elapsed,0.0001):,.1f}")
                    st.caption("This is a single-batch measurement, not a verified sustained-throughput claim.")
        if st.button("Process queued readings now (up to 500)"):
            result = call("POST", "worker/process-once/", {"limit": 500})
            if result:
                st.json(result)
        st.warning("For automatic background processing, run `python manage.py run_alert_worker` in a separate terminal.")

elif page == "Performance lab":
    st.title("Ingestion performance lab")
    st.caption("Live MySQL-backed counters + measured benchmark reports. This page does not fabricate speed claims.")
    dashboard = call("GET", "dashboard/")
    if dashboard:
        a, b, c, d = st.columns(4)
        a.metric("Total readings", f"{dashboard.get('total_readings', 0):,}")
        b.metric("Pending queue", f"{dashboard.get('pending_readings', 0):,}")
        c.metric("Active sensors", dashboard.get("active_sensors", 0))
        d.metric("Enabled rules", dashboard.get("enabled_rules", 0))
    st.subheader("Last ingestion: server-stage timings")
    diagnostic = st.session_state.get("last_ingest_diagnostics")
    if diagnostic and diagnostic.get("timings_ms"):
        st.caption(f"Backend path: {diagnostic.get('engine', 'unknown')}")
        stages = diagnostic["timings_ms"]
        df = pd.DataFrame([{"stage": key, "duration_ms": value} for key, value in stages.items() if key != "total"])
        st.bar_chart(df.set_index("stage"))
        st.metric("Server-ingest elapsed", f"{stages.get('total', 0):.2f} ms")
    else:
        st.info("Submit a batch from Sensor simulator to view server stage timings for that request.")

    st.subheader("Compare actual V1 and V2 results")
    st.caption("The baseline below is the measured 19 Oct 2026 V1 run on your machine, not an estimate.")
    baseline_path = Path(__file__).resolve().parents[1] / "docs" / "V1_MEASURED_BASELINE.json"
    baseline = None
    try:
        import json
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        st.warning("Bundled V1 baseline unavailable")
    measured_v1 = baseline["main_batch"]["client_wall_seconds"] if baseline else None
    uploaded = st.file_uploader("Upload your newly measured results/v2_10k.json", type="json")
    if measured_v1 is not None:
        st.metric("V1 10,000-reading client time", f"{measured_v1:.3f} s")
    if uploaded is not None:
        try:
            import json
            from statistics import median
            data = json.loads(uploaded.getvalue())
            runs = data["runs"]
            if not runs or any(run["readings_sent"] != 10000 for run in runs):
                st.error("Upload a benchmark containing only 10,000-reading single-request runs.")
            else:
                durations = [float(run["client_wall_seconds"]) for run in runs]
                med = median(durations)
                a, b, c = st.columns(3)
                a.metric("V2 median client time", f"{med:.3f} s", delta=f"{(measured_v1-med)/measured_v1*100:.1f}% faster" if measured_v1 else None)
                b.metric("V2 observed throughput", f"{10000/med:,.0f}/s")
                c.metric("1 second target", "PASS" if all(t <= 1.0 for t in durations) else "NOT MET")
                if measured_v1 is not None:
                    st.bar_chart(pd.DataFrame({"seconds": [measured_v1, med]}, index=["V1", "V2 median"]))
                detailed = [{"run": r["run"], "client_seconds": r["client_wall_seconds"],
                             "engine": r.get("engine", "not reported"),
                             "server_total_ms": (r.get("server_timings_ms") or {}).get("total")} for r in runs]
                st.dataframe(pd.DataFrame(detailed), use_container_width=True, hide_index=True)
        except (KeyError, ValueError, TypeError, ZeroDivisionError) as exc:
            st.error(f"Invalid measured benchmark file: {exc}")
    st.subheader("Reproduce the benchmark")
    st.code("python scripts/load_test.py --base-url http://127.0.0.1:8010/api --count 10000 --repeat 3 --output results/v2_10k.json", language="powershell")
    st.code("python scripts/compare_benchmarks.py --before docs/V1_MEASURED_BASELINE.json --after results/v2_10k.json", language="powershell")
    st.caption("Client time includes network/JSON overhead. Worker queue drainage is verified separately, not inferred from HTTP 202.")

elif page == "API status":
    st.title("Backend status & testing")
    st.json(call("GET", "health/") or {"status": "unreachable"})
    st.subheader("Authentication")
    st.json(call("GET", "auth/me/") or {"authenticated": False})
    st.subheader("Quick routes")
    st.code("""GET    /api/health/
POST   /api/auth/login/
GET    /api/sensors/
GET    /api/rules/
POST   /api/readings/
POST   /api/readings/batch/
GET    /api/dashboard/
GET    /api/alerts/
POST   /api/alerts/{id}/acknowledge/
POST   /api/alerts/{id}/resolve/
POST   /api/worker/process-once/""")
