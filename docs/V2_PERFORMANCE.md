# Performance engineering and evaluation — CampusPulse V2

## Evidence-based result ledger

| Scenario | HTTP response | Reading count | Client time | Throughput | Conclusion |
|---|---|---:|---:|---:|---|
| V1 warm-up, 2026-10-19 | 202 | 100 | 0.043071 s | 2,321.75/s | Passed persistence test |
| V1 single HTTP batch, 2026-10-19 | 202 | 10,000 | **1.405263 s** | **7,116.11/s** | **Failed one-second target** |
| V2 single HTTP batch | Unmeasured | 10,000 planned | Pending | Pending | Must test on local MySQL |
| V2 multiple concurrent batches | Unmeasured | 10,000 planned | Pending | Pending | Separate workload from single-batch goal |

V1 integrity evidence: `monitor_reading` total 10,110; processed 10,110; pending 0. Rules generated 4,946 instant alerts and one window alert. The earlier 10-record live test produced exactly 10 instant plus one rolling-window alert and the `open → acknowledged → resolved` audit sequence.

**Never substitute static checks or guessed timings for real results.** This version's predicted speedup is a hypothesis until benchmarked.

## V2 architectural changes

- Parsing uses DRF's JSON body parser unchanged; a single Python pass validates sensors/metrics, decimal precision and date-times instead of 10,000 DRF `Serializer` instances.
- Database checks retrieve only `event_id`, `sensor_id`, `metric_type`, `value`, `recorded_at` in chunks of 2,000, not full models and related Sensor objects in chunks of 500.
- On MySQL, parameterized multi-VALUES SQL uses a native multi-row `INSERT ... ON DUPLICATE KEY UPDATE` route; it avoids constructing 10,000 Django Reading model objects. The duplicate-key clause permits identical events and rejects concurrent payload conflicts (NULL value on a NOT NULL column triggers transaction rollback). No schema change.
- The `202` is sent only once the atomic DB transaction commits. After that the single background worker performs expensive alert evaluation.
- Worker logic and the existing queue indexes remain unchanged, so performance improvements focus on ingestion without destabilizing window correctness.
- `CAMPUS_INGEST_MODE=legacy` recovers the original DRF/ORM ingestion path without reverting database state. Use it as a feature flag for a matched control benchmark.

## Profiling fields

Fast batch responses add an `engine` field (`mysql_native_bulk` on MySQL, `orm_bulk` in SQLite tests) and durations:

- `validation`: input decoding and validation **after** DRF JSON parsing has completed
- `lookup`: sensor resolution and event-ID database lookups
- `prepare`: create Python insert row tuples
- `insert_commit`: MySQL/ORM insert transaction including commit
- `total`: overall application ingestion path from `ingest()` entry to committed database write

The client script measures whole POST round trip, **including HTTP, JSON serialization and Django/DRF overhead**. These are different durations; do not add or compare them as if identical.

## Repeatable protocol

1. Record MySQL row count and pending queue before the run; back up important data and use synthetic events.
2. Stop other local CPU/GPU-heavy work if possible. Run with one worker, and separately test without a worker (not directly comparable).
3. Warm up using 100 events. Use 10,000 rows in one POST and repeat at least three times; save each report and its full settings.
4. Report median, min, max, one-second pass for **every** measured run. Inspect the response engine and `timings_ms` to identify JSON vs validation vs DB bottlenecks.
5. Independently verify all accepted rows appeared, queue drained, and alert rules ran. Pending count 0 **at end** is necessary; receipt alone doesn't prove alert processing.
6. Compare same stack, hardware and database settings. For production relevance, use Waitress instead of Django's dev server and repeat.
7. Run the separate `concurrent_burst.py` test (example 4 concurrent workers × 500-reading batches). Measure wall time and P95; do not conflate 10k readings in one HTTP body with 10k sensors making separate HTTP calls.
8. Test idempotent retries, conflicting concurrent IDs, empty/invalid/oversized batches, SQL failure recovery and worker restart on real MySQL; do not rely solely on SQLite CI tests.

## Correctness and honest limitations

- MySQL `ON DUPLICATE KEY` matches the existing unique `event_id`; no migrations or DDL rewrite are required. SQL `VALUES()` in the duplicate clause is supported on MySQL 8.0.45 but flagged deprecated in newer versions; an alias-form migration may be needed later.
- SQLite regression tests use ORM writes; the native MySQL path, trigger audit and performance need live MySQL testing. The project uses a V1 fallback for quick rollback.
- A `202` confirms the **transaction returned successfully**; benchmark scripts should still reconcile database counts. Rule evaluation is deliberately asynchronous, not part of the HTTP latency number.
- Single-POST throughput does not guarantee sustained 10,000 requests/s. MySQL resource contention, network, packet size, workers, and hardware determine results.
- The V2 alert worker retains one-worker rolling-window semantics. Late or out-of-order historic readings may affect windows; parallel workers require partitioning and ordering to maintain correctness.
- Extra alerts from replayed windows are deduplicated per rule/sensor/UTC time bucket. A continuously satisfied instant rule creates one alert per reading; this is intended but can create alert floods.
- No direct speedup claim will be added until user-run V2 result JSON is supplied.
