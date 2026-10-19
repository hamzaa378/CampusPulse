# CampusPulse V2 — GDG Tech Wildcard Entry, Backend Task 1

**MySQL 8 · Django 5.2 REST API · Streamlit · durable background alert worker**

CampusPulse ingests campus sensor readings, evaluates instant thresholds and rolling-window averages, and gives organizers an authenticated alert-management dashboard. V2 is an **optimized, rollback-capable performance release** based on the live-tested V1; existing database tables, triggers, stored procedures, views and alerts are preserved.

**Actual V1 baseline, measured on Windows + MySQL 8.0.45, 2026-10-19:** 10,000 readings accepted with HTTP 202 in **1.405263 s** (7,116.11 readings/s). All 10,110 cumulative readings were subsequently processed and pending queue = 0. **V1 did not pass the one-second challenge target. V2 has not yet been benchmarked on the user's machine and is NOT claimed to achieve it.** See `docs/V1_MEASURED_BASELINE.json` and `docs/V2_PERFORMANCE.md`.

## What's different in V2

1. **Dual ingestion engines:** `CAMPUS_INGEST_MODE=fast` enables single-pass Python validation and native parameterized MySQL multi-row insertion; `legacy` restores the exact V1 serializer/ORM route for rollback or comparison. Both return HTTP 202 only after transaction commit.
2. **Efficient duplicate lookups:** `values_list()` fetches only event IDs and four signature fields instead of constructing and joining a model per existing event. Prepared multi-row SQL is parameterized.
3. **Safer race handling:** no `INSERT IGNORE` in the fast MySQL path. Concurrent attempts with a matching event ID but conflicting payload fail as a database constraint error and roll back; identical retries are no-op updates. Existing stored event ID comparisons still reject mismatches before insert.
4. **Measurable pipeline:** response includes `engine` and `timings_ms` for validation, lookup, object prep, insert/commit and total server-side ingestion. Client-side request time includes all HTTP overhead.
5. **Performance lab and tooling:** Streamlit page compares **actual** user-supplied V1 results against a new V2 JSON report. Scripts test single-batch and concurrent requests, with per-run report export and a Markdown comparison generator.
6. **Expanded regression tests, read-only SQL verification and GitHub documentation.**

## Project map

```text
backend/
  campus_monitor/settings.py       # MySQL credentials + fast/legacy engine switch
  monitor/fast_validation.py       # fast path input validation
  monitor/services.py              # dispatcher, MySQL bulk insert, legacy fallback
  monitor/processor.py             # unchanged durable alert evaluator
  monitor/models.py                # unchanged MySQL schema mapping
  monitor/migrations/0001_initial.py  # existing canonical schema
  monitor/tests/                  # V1 + V2 regression tests
frontend/app.py                   # dashboard + V2 Performance lab
mysql/02_programmability.sql     # existing triggers/procedures/functions/cursor/views
mysql/05_v2_readonly_health.sql  # safe performance and data checks
scripts/load_test.py              # one HTTP request, 1-10,000 readings
scripts/concurrent_burst.py       # many concurrent HTTP batches
scripts/compare_benchmarks.py     # measured performance report generator
docs/V1_MEASURED_BASELINE.json     # known V1 results, no invented V2 result
docs/V2_PERFORMANCE.md            # methodology, limitations, next steps
docs/HANDOVER.md                  # single continuation / recovery guide
.github/workflows/tests.yml       # CI regression tests on SQLite
```

## Upgrade EXISTING working V1 (recommended)

**Do not reset `gdg_campus_monitor`; do not rerun 00_create_database.sql or 01_schema_mysql.sql.** V2 adds **no migration** and requires no MySQL routine reinstall. Keep backups before benchmarking.

1. Extract this V2 ZIP into a NEW directory, such as `C:\Users\hamza\Downloads\GDG_CampusPulse_V2`. Do not overwrite V1; it remains your rollback snapshot.
2. Stop the V1 **Django server, alert worker and Streamlit process** with Ctrl+C. Do not stop MySQL or another project on port 8000.
3. Activate the working virtual environment and enter V2 root:

   ```powershell
   C:\EduSphereVenv\Scripts\Activate.ps1
   cd C:\Users\hamza\Downloads\GDG_CampusPulse_V2
   python -m pip install -r requirements.txt
   ```

4. Copy ONLY the local, secret `.env` configuration **from your V1 folder** to V2; never upload it to GitHub:

   ```powershell
   Copy-Item "..\GDG_CampusPulse_V1_Complete_Source\.env" ".env"
   ```

   If the V1 `.env` is missing, copy `.env.example`, set unique passwords and API key, and check your MySQL `gdg_monitor_app` credentials. Confirm the `DB_NAME=gdg_campus_monitor`. Add `CAMPUS_INGEST_MODE=fast` (fast is the default).

5. Check V2 against your existing MySQL database:

   ```powershell
   cd backend
   python manage.py check
   python manage.py migrate --plan
   python manage.py showmigrations monitor
   ```

   `monitor.0001_initial` should already be marked `[X]`; V2 introduces no migration. **Do not run `createsuperuser` or `seed_demo` again.** Account `hamza`, three sensors and two rules were verified in V1.

## Start the full stack (separate PowerShell terminals)

**1. Backend** (use port 8010; port 8000 belonged to a different API in the initial test):

```powershell
C:\EduSphereVenv\Scripts\Activate.ps1
cd C:\Users\hamza\Downloads\GDG_CampusPulse_V2\backend
python manage.py runserver 127.0.0.1:8010
```

For a more realistic Windows WSGI comparison, STOP `runserver` and instead use (only **one** server process at a time):

```powershell
waitress-serve --listen=127.0.0.1:8010 --threads=8 campus_monitor.wsgi:application
```

**2. Background worker** (keep one worker for predictable V2 rolling-window semantics):

```powershell
C:\EduSphereVenv\Scripts\Activate.ps1
cd C:\Users\hamza\Downloads\GDG_CampusPulse_V2\backend
python manage.py run_alert_worker --batch-size 500 --poll-seconds 0.5
```

**3. Streamlit** (ensure it points at the Django 8010 API):

```powershell
C:\EduSphereVenv\Scripts\Activate.ps1
cd C:\Users\hamza\Downloads\GDG_CampusPulse_V2
$env:API_BASE_URL="http://127.0.0.1:8010/api"
python -m streamlit run frontend/app.py
```

Visit `http://localhost:8501`, sign in as your existing organizer and open **Performance lab**. Check API health:

```powershell
Invoke-RestMethod http://127.0.0.1:8010/api/health/
```

## Run tests without touching MySQL data

```powershell
cd backend
$env:DB_ENGINE="sqlite"
python manage.py test monitor.tests -v 2
Remove-Item Env:DB_ENGINE
```

Tests use an isolated temporary SQLite database. This checks most API semantics, **not** the MySQL native SQL branch; that needs separate live testing and backed-up MySQL. Don't set `DB_ENGINE=sqlite` in the running MySQL server.

## Measure fast V2 (writes real data)

From V2 root, after Django server and MySQL connection are running:

```powershell
python scripts/load_test.py --base-url http://127.0.0.1:8010/api --count 100 --repeat 1 --output results/v2_warmup.json
python scripts/load_test.py --base-url http://127.0.0.1:8010/api --count 10000 --repeat 3 --output results/v2_10k.json
python scripts/compare_benchmarks.py --before docs/V1_MEASURED_BASELINE.json --after results/v2_10k.json --output results/performance_comparison.md
```

Use MySQL CLI to verify eventual processing (the worker may take time):

```sql
USE gdg_campus_monitor;
SELECT COUNT(*) AS total, SUM(processed_at IS NULL) AS pending,
       SUM(processed_at IS NOT NULL) AS processed FROM monitor_reading;
```

Run a **separate** concurrent workload if needed:

```powershell
python scripts/concurrent_burst.py --base-url http://127.0.0.1:8010/api --count 10000 --batch-size 500 --workers 4 --output results/v2_concurrent.json
```

### Controlled V1 vs V2 engine A/B (same V2 source)

Stop the API server; set `$env:CAMPUS_INGEST_MODE="legacy"` in the server terminal and restart, benchmark and save `results/legacy_retest.json`. Then `Remove-Item Env:CAMPUS_INGEST_MODE`, restart into fast engine, run same benchmark and save `results/fast_retest.json`. The two runs should use the same server type, hardware, worker settings and sample size. Env vars set in the **load-test terminal do not switch the running server**. Do not report medians from different deployment types as an apples-to-apples improvement.

## Submission / safety checklist

- Include source, `README.md`, `docs/ARCHITECTURE.md`, `docs/HANDOVER.md`, `docs/V2_PERFORMANCE.md` and the verified SQL scripts.
- Add **your actual V2 benchmark** and integrity logs to the GitHub submission if you are comfortable publishing them (synthetic data only); files in `results/` are ignored by default, so intentionally copy sanitized evidence into a tracked `docs/` file if desired.
- Exclude `.env`, venv folders, database exports, passwords, auth tokens, private sensor keys, and device addresses.
- For nonlocal deployment: HTTPS, proper authentication/security settings, quotas, monitoring, backups, and a real production WSGI/ASGI server are required. The provided demo is not a production-ready internet service.

Other documentation: `docs/API_REFERENCE.md`, `docs/ARCHITECTURE.md`, `docs/V2_PERFORMANCE.md`, `docs/HANDOVER.md`.
