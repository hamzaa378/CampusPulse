# SINGLE PROJECT HANDOVER — CampusPulse V2 (2026-10-19)

This is the canonical continuation guide. Read this before modifying the project in another chat or on another machine.

## Mission

GDG Tech Wildcard Entry **Backend Task 1**: campus sensor ingestion, instant and 10-minute/window thresholds, customizable rules, alert lifecycle, sensor simulator, **10,000 readings in one second design target**, and load-test report. Stack **MySQL 8.0 + Django 5.2 REST + Streamlit**, Windows 11 local testing, dedicated API port 8010.

## Verified V1 checkpoint (user's real machine)

- MySQL 8.0.45, Django 5.2.17, Python environment `C:\EduSphereVenv` working.
- Schema installed with `monitor.0001_initial` migrated. MySQL routine import succeeded: **4 triggers, 4 stored procedures, 2 functions, 4 views**, one cursor in `sp_refresh_daily_summary`.
- Organizer `hamza`, sensors `library-floor-2`, `cafeteria-hall`, `lab-block-a`; rules `Library hot reading`, `Library ten minute mean` seeded.
- Ten V1 Django SQLite tests passed in 2.154 seconds.
- Streamlit authentication and API correct on `http://127.0.0.1:8010/api`; different unrelated backend on port 8000 returned 422/404 earlier; do not point frontend there.
- 10 temperature readings of 35.0 created exactly **10 instant + 1 rolling-window alert**. Alert #11 transitioned open → acknowledged → resolved; audit trigger recorded all three states and actor ID 1. Daily summary cursor produced 10, avg/min/max 35.0000.
- V1 100-reading warmup: 0.043071s, HTTP 202; V1 10,000 reading single POST: **1.405263s**, **7,116.11 readings/s**, HTTP 202; 10,110 total records, all processed, pending 0; 4,946 instant plus one rolling-window alerts after benchmark. **One-second target not met.** These results are copied verbatim to `docs/V1_MEASURED_BASELINE.json`.
- V2 changes have passed *static source checks only* in the authoring environment; **V2 runtime tests, native MySQL branch and new performance are NOT verified yet**.

## V2 changes

- `backend/monitor/fast_validation.py` new one-pass strict validation and deterministic ID generation; no schema changes.
- `backend/monitor/services.py` now supports `CAMPUS_INGEST_MODE=fast` (default, optimized) and `legacy` (full original V1 ingestion path). Projected existing-event lookups, parameterized 2,000-row multi-VALUES MySQL insert, conditional upsert for concurrency conflicts, server timing stages in 202 response.
- `backend/campus_monitor/settings.py` adds the feature flag.
- `backend/monitor/tests/test_fast_ingest.py` adds fast/legacy tests for retries, values, payload conflicts, atomic reject, hash IDs, malformed input.
- `frontend/app.py` adds **Performance lab**: live queue metrics, latest V2 server profiling and uploaded measured JSON comparison with the V1 benchmark. Existing frontend routes unchanged.
- `scripts/load_test.py` records per-run `engine` and `server_timings_ms`.
- `scripts/concurrent_burst.py` separate multi-request concurrent throughput test; `scripts/compare_benchmarks.py` V1/V2 real-report comparison.
- `mysql/05_v2_readonly_health.sql` read-only data, alert, index and queue health checks.
- `docs/ARCHITECTURE.md`, `docs/V2_PERFORMANCE.md`, baseline JSON, GitHub workflow and refreshed README.

## Existing database and migration state

**Never run schema creation SQL on an already populated database.** Current database `gdg_campus_monitor`, SQL root accounts not required for normal API, current app account `gdg_monitor_app`. Django migrations remain identical to V1. Same triggers, routines and views; V2 does not require database rebuild. `mysql/01_schema_mysql.sql` is reference only. SQLite `DB_ENGINE=sqlite` is for isolated tests, not the production data.

## Next tests: precise commands

1. Extract ZIP next to V1, stop old processes, copy secret V1 `.env` into V2. Set `CAMPUS_INGEST_MODE=fast` if wanted; default is fast.
2. Activate `C:\EduSphereVenv\Scripts\Activate.ps1`, `pip install -r requirements.txt` from V2 root.
3. `cd backend; python manage.py check; python manage.py migrate --plan; python manage.py showmigrations monitor` (expect `[X] 0001_initial`); then **isolated** tests `$env:DB_ENGINE="sqlite"; python manage.py test monitor.tests -v 2; Remove-Item Env:DB_ENGINE`.
4. Backend server: `python manage.py runserver 127.0.0.1:8010` from backend root; check `Invoke-RestMethod http://127.0.0.1:8010/api/health/`.
5. Single alert worker: `python manage.py run_alert_worker --batch-size 500 --poll-seconds 0.5`, separate terminal backend root.
6. Streamlit in V2 root with `$env:API_BASE_URL="http://127.0.0.1:8010/api"; python -m streamlit run frontend/app.py`.
7. From V2 root, warmup `python scripts/load_test.py --base-url http://127.0.0.1:8010/api --count 100 --repeat 1 --output results/v2_warmup.json` and 10k `python scripts/load_test.py --base-url http://127.0.0.1:8010/api --count 10000 --repeat 3 --output results/v2_10k.json`.
8. Compare `python scripts/compare_benchmarks.py --before docs/V1_MEASURED_BASELINE.json --after results/v2_10k.json`.
9. Optional production-like Windows server: stop `runserver`, execute `waitress-serve --listen=127.0.0.1:8010 --threads=8 campus_monitor.wsgi:application` from backend folder. Re-test same conditions.
10. In MySQL CLI `SOURCE C:/Users/hamza/Downloads/GDG_CampusPulse_V2/mysql/05_v2_readonly_health.sql;`, verify pending 0 eventually. Record batch HTTP times, stage timings, database totals, negative case responses and any errors.

## Constraints and known risks

- **V2 performance unmeasured**. The one-second target cannot be claimed based on code or local SQLite tests. Need a user-run benchmark report before final submission.
- V2 MySQL native conditional upsert must be verified on user's MySQL 8.0.45 with existing triggers and DB permissions. MySQL 8's `VALUES()` in upsert is supported but deprecated.
- Fast validation is custom; compare parity against `ReadingInSerializer` when extending metrics or adding field constraints. Normalizes timezone to UTC and decimals to 4 places. DRF JSON parsing is still prior overhead.
- One worker for correct window semantics. Late/out-of-order events are not fully handled by V2.
- MySQL native path not exercised by SQLite tests. Concurrency races need independent live tests.
- Alert floods for instant rule on sustained conditions are an intentional current rule behavior, not a quiet alert-state collapse.
- `.env`, secrets, private keys, database dumps and tokens must never be committed.

## Required continuation decision

Review **actual** V2 `results/v2_10k.json` and `results/performance_comparison.md`. If client time remains over 1s, use `server_timings_ms` to identify the bottleneck and only then consider JSON parser changes, worker isolation, staging/queue tables, MySQL configuration or API deployment changes. Preserve tested migrations and provide a versioned ZIP/documentation at each checkpoint.
