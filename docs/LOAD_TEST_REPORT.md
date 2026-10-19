# Load-test status and actual observed measurements

Read `V2_PERFORMANCE.md` for the methodology, reproducible CLI commands, validation limits and V2 status.

The user ran the complete V1 single-request burst locally on 2026-10-19:

- 100-reading warm-up: 0.043071 s, 2,321.75 readings/s, HTTP 202.
- 10,000-reading burst: **1.405263 s**, **7,116.11 readings/s**, HTTP 202.
- MySQL total readings after both tests: 10,110, all processed, 0 pending.
- One-second target **not met** by V1.
- Detailed evidence: `V1_MEASURED_BASELINE.json`.

**V2 performance is UNMEASURED.** Test it against the user's actual MySQL server, save `results/v2_10k.json` and run `scripts/compare_benchmarks.py`; do not publish a performance improvement claim until the new result is available.
