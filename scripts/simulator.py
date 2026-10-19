#!/usr/bin/env python
"""Independent sensor simulator. Simulates multiple sensor patterns via the REST API."""
import argparse
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

PATTERNS = {
    "library-floor-2": ("temperature", 31.0, 4.0),
    "cafeteria-hall": ("occupancy", 90.0, 25.0),
    "lab-block-a": ("air_quality", 75.0, 15.0),
}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rounds", type=int, default=30)
    p.add_argument("--interval", type=float, default=1.0)
    args = p.parse_args()
    endpoint = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000/api").rstrip("/")
    key = os.environ.get("SENSOR_API_KEY", "")
    if not key:
        p.error("Set SENSOR_API_KEY in .env")
    for i in range(args.rounds):
        now = datetime.now(timezone.utc).isoformat()
        readings = [{"sensorId": name,"type":metric,"value":round(base+random.uniform(-spread,spread),4),
                     "timestamp":now} for name,(metric,base,spread) in PATTERNS.items()]
        result = requests.post(f"{endpoint}/readings/batch/", json={"readings":readings},
                               headers={"X-Sensor-Key":key}, timeout=20)
        print(f"round={i+1} http={result.status_code} result={result.text[:250]}")
        result.raise_for_status()
        if i + 1 < args.rounds:
            time.sleep(args.interval)

if __name__ == "__main__":
    main()
