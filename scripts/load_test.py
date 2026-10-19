#!/usr/bin/env python
"""Client-side burst measurement. Does NOT invent/pass performance claims.

Example: python scripts/load_test.py --count 10000 --repeat 3
Uses /api/readings/batch/; run worker independently if desired.
"""
import argparse
import json
import os
import statistics
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def main():
    p = argparse.ArgumentParser(description="Actual sensor ingestion burst measurement")
    p.add_argument("--base-url", default=os.environ.get("API_BASE_URL", "http://127.0.0.1:8000/api"))
    p.add_argument("--sensor", default="library-floor-2")
    p.add_argument("--count", type=int, default=10000)
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--output", default="results/load_test.json")
    args = p.parse_args()
    if args.count < 1 or args.count > 10000 or args.repeat < 1:
        p.error("count must be 1..10000 and repeat must be >=1")
    key = os.environ.get("SENSOR_API_KEY", "")
    if not key:
        p.error("Set SENSOR_API_KEY in .env")
    results = []
    for run in range(args.repeat):
        now = datetime.now(timezone.utc)
        readings = [
            {"eventId": uuid.uuid4().hex, "sensorId": args.sensor, "type": "temperature",
             "value": round(29 + (i % 120) / 20, 4),
             "timestamp": (now - timedelta(seconds=(args.count - i - 1) / max(args.count, 1))).isoformat()}
            for i in range(args.count)
        ]
        payload_bytes = len(json.dumps({"readings": readings}, separators=(",", ":")).encode())
        t0 = time.perf_counter()
        try:
            response = requests.post(f"{args.base_url.rstrip('/')}/readings/batch/", json={"readings":readings},
                                     headers={"X-Sensor-Key":key}, timeout=args.timeout)
            elapsed = time.perf_counter() - t0
            response.raise_for_status()
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"Run {run+1} failed: {exc}", file=sys.stderr)
            return 1
        point = {"run":run+1, "readings_sent":args.count,"http_status":response.status_code,
                 "client_wall_seconds":round(elapsed,6),
                 "client_observed_readings_per_second":round(args.count/max(elapsed,1e-9),2),
                 "payload_bytes":payload_bytes,"response":body}
        results.append(point)
        print(json.dumps(point, indent=2))
    times = [r["client_wall_seconds"] for r in results]
    report = {
        "measurement": "End-to-end client wall time for a single HTTP POST containing N readings",
        "limitations": ["Not a server-only throughput benchmark", "Does not measure background alert evaluation latency",
                        "Results depend on hardware, MySQL configuration and network",
                        "10k/s target is met only if the actual observed measurement supports it"],
        "target_10k_readings_in_one_second": args.count == 10000,
        "passes_one_second_target_all_runs": args.count == 10000 and all(t <= 1.0 for t in times),
        "median_seconds":round(statistics.median(times),6),
        "max_seconds":round(max(times),6), "min_seconds":round(min(times),6),
        "runs":results,
        "measured_utc":datetime.now(timezone.utc).isoformat(),
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Report saved to {destination}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
