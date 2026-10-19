#!/usr/bin/env python3
"""Compare REAL V1/V2 results; never manufacture throughput improvements."""
import argparse
import json
from pathlib import Path


def measure(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "runs" in data:
        runs = data["runs"]
        if not runs:
            raise ValueError(f"{path}: no measured runs")
        seconds = [float(r["client_wall_seconds"]) for r in runs]
        counts = [int(r["readings_sent"]) for r in runs]
        if len(set(counts)) != 1:
            raise ValueError("Refusing to compare different readings counts in one report")
        import statistics
        return counts[0], statistics.median(seconds)
    if "main_batch" in data:
        return int(data["main_batch"]["count"]), float(data["main_batch"]["client_wall_seconds"])
    raise ValueError(f"{path}: unrecognized measured report")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--before", default="docs/V1_MEASURED_BASELINE.json")
    p.add_argument("--after", default="results/v2_10k.json")
    p.add_argument("--output", default="results/performance_comparison.md")
    args = p.parse_args()
    try:
        n0, v0 = measure(args.before)
        n1, v1 = measure(args.after)
        if n0 != n1:
            raise ValueError("Benchmark counts differ. Compare the same batch size.")
        improvement = (v0 - v1) / v0 * 100
        text = ("# Measured performance comparison\n\n"
                f"- Baseline file: `{args.before}`\n"
                f"- V2 file: `{args.after}`\n"
                f"- Size: {n0:,} readings per HTTP request\n"
                f"- V1 median/client duration: **{v0:.6f} s**\n"
                f"- V2 median/client duration: **{v1:.6f} s**\n"
                f"- Relative reduction in duration: **{improvement:.2f}%**\n"
                f"- V2 observed throughput: **{n1/v1:,.2f} readings/s**\n"
                f"- One-second single-request target: **{'PASS' if v1 <= 1.0 else 'NOT YET MET'}**\n\n"
                "Interpretation: client-observed single HTTP batch durations, not sustainable "
                "10k independent requests/s. Same hardware/DB/server conditions are needed "
                "for a valid A/B comparison. Backend processing finishes asynchronously.\n")
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        print(text)
        print(f"Written: {destination}")
    except (ValueError, FileNotFoundError, KeyError) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
