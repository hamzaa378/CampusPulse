#!/usr/bin/env python3
"""Generate exactly N synthetic readings across concurrent HTTP batch requests.

Separate from the single-POST performance target. Reports time-to-202, not
worker completion. Distinct eventIds prevent accidental replay collisions.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import statistics
import time
import uuid

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def percentiles(numbers, p):
    ordered = sorted(numbers)
    return ordered[min(len(ordered) - 1, max(0, int((len(ordered) - 1) * p + .5)))]


def main():
    p = argparse.ArgumentParser(description="Concurrent multi-POST burst test")
    p.add_argument("--base-url", default=os.getenv("API_BASE_URL", "http://127.0.0.1:8010/api"))
    p.add_argument("--count", type=int, default=10000)
    p.add_argument("--batch-size", type=int, default=500)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--sensor", default="library-floor-2")
    p.add_argument("--output", default="results/v2_concurrent.json")
    p.add_argument("--timeout", type=int, default=120)
    args = p.parse_args()
    if not 1 <= args.count <= 100000 or not 1 <= args.batch_size <= 10000 or not 1 <= args.workers <= 64:
        p.error("count 1..100000, batch-size 1..10000, workers 1..64")
    key = os.environ.get("SENSOR_API_KEY", "")
    if len(key) < 16:
        p.error("Provide a valid SENSOR_API_KEY in .env")
    now = datetime.now(timezone.utc)
    seed = uuid.uuid4().hex[:12]
    payload = [{"eventId": f"{seed}-{i}", "sensorId": args.sensor,
                "type": "temperature", "value": round(29 + i % 120 / 20, 4),
                "timestamp": (now - timedelta(seconds=(args.count - i - 1) / args.count)).isoformat()}
               for i in range(args.count)]
    groups = [payload[i:i + args.batch_size] for i in range(0, len(payload), args.batch_size)]
    url = f"{args.base_url.rstrip('/')}/readings/batch/"

    def post(batch_num, readings):
        started = time.perf_counter()
        try:
            # Per thread: no shared requests.Session (avoids cross-thread session mutation).
            r = requests.post(url, json={"readings": readings}, headers={"X-Sensor-Key": key}, timeout=args.timeout)
            elapsed = time.perf_counter() - started
            data = r.json()
            good = r.status_code == 202 and data.get("received") == len(readings)
            return {"batch": batch_num, "size": len(readings), "status": r.status_code,
                    "elapsed_seconds": round(elapsed, 6), "ok": good,
                    "server_timings_ms": data.get("timings_ms"),
                    "error": None if good else str(data)[:500]}
        except (requests.RequestException, ValueError) as exc:
            return {"batch": batch_num, "size": len(readings), "ok": False, "error": str(exc)}

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = [pool.submit(post, i, batch) for i, batch in enumerate(groups)]
        results = [f.result() for f in as_completed(jobs)]
    wall = time.perf_counter() - started
    times = [r["elapsed_seconds"] for r in results if r["ok"]]
    received = sum(r["size"] for r in results if r["ok"])
    report = {"scenario": "concurrent HTTP batches", "measured_at": datetime.now(timezone.utc).isoformat(),
              "sensor": args.sensor, "requested": args.count, "accepted": received,
              "http_batches": len(groups), "concurrency": args.workers,
              "batch_size": args.batch_size, "wall_seconds": round(wall, 6),
              "observed_accepted_per_second": round(received / max(wall, 1e-9), 2),
              "request_median_seconds": round(statistics.median(times), 6) if times else None,
              "request_p95_seconds": round(percentiles(times, .95), 6) if times else None,
              "all_batches_accepted": received == args.count and all(x["ok"] for x in results),
              "limitations": "Receipt confirms durable queueing, not background processing; verify MySQL afterward.",
              "runs": sorted(results, key=lambda x: x["batch"])}
    dst = Path(args.output)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "runs"}, indent=2))
    print(f"Saved {dst}")
    return 0 if report["all_batches_accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
