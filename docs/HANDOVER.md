# SINGLE PROJECT HANDOVER — CampusPulse V1

## Goal and brief

GDG TECH Wildcard Entry, Backend Task 1, page 6: ingest campus sensor readings individually and in batches, be designed for 10,000 readings/s burst, let organizers configure instant and time-window rules, create alerts and manage acknowledgement/resolution, add simulator, deliver load-test report and reliability discussion.

**Selected stack:** MySQL 8 (not Oracle SQL*Plus), Python Django 5.2/DRF, Streamlit. Windows-oriented setup in repository root `README.md`.

## Current checkpoint

- Full app source, initial Django migration, SQL DDL mirror, SQL stored routines and views, Streamlit dashboard, example sensor simulator, load-test measurement script, test suite and documentation are packaged.
- **Static compile/syntax, SQL declaration checks and model/migration field-name alignment only are possible in source authoring environment.** Real Django import, migration execution, SQL runtime execution, UI click-testing and measured MySQL load testing must be performed on user's machine. Read `docs/LOAD_TEST_REPORT.md`; no unmeasured performance claims.
- V1 deliberately separates DB persistence from background rule evaluation. This is a substantial first working iteration, not a completed production rollout.

## Environment setup

1. Install Python 3.11–3.13 and MySQL 8; create venv and run `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env`; configure MySQL credentials and two secrets.
3. Execute `mysql/00_create_database.sql` after changing passwords.
4. Execute `cd backend; python manage.py migrate; python manage.py createsuperuser; python manage.py seed_demo`.
5. Execute `mysql/02_programmability.sql` using MySQL CLI.
6. In separate terminals run `python backend/manage.py runserver`, `python backend/manage.py run_alert_worker`, `streamlit run frontend/app.py` (commands best run with `cd backend` for Django).
7. Run `DB_ENGINE=sqlite python manage.py test monitor.tests` for portable tests, then actual MySQL SQL verification/load tests.

## Critical file responsibilities

- `backend/monitor/models.py`: six app models, indexes and relations.
- `backend/monitor/migrations/0001_initial.py`: primary schema installation history.
- `backend/monitor/serializers.py`: validated reading and management payloads.
- `backend/monitor/services.py`: ingest/batch verification, SHA256 event IDs, dedupe, bulk MySQL writes.
- `backend/monitor/processor.py`: chronological pending selection, rolling deques, alert creation, SQLite audit fallback.
- `backend/monitor/views.py`: endpoints, token auth, sensor key, lifecycle.
- `backend/monitor/management/commands/run_alert_worker.py`: durable worker loop.
- `backend/monitor/management/commands/seed_demo.py`: portable test fixtures.
- `backend/monitor/tests/*`: functional API tests.
- `frontend/app.py`: Streamlit demo UI and sensor simulator.
- `mysql/00_create_database.sql`: database and grants.
- `mysql/01_schema_mysql.sql`: explicit CREATE TABLE reference; never apply before ordinary migrations.
- `mysql/02_programmability.sql`: DB triggers, functions, procedures/cursor, views.
- `mysql/03_seed_demo.sql`: optional SQL data seed alternative.
- `mysql/04_verification.sql`: SQL existence and behavior checks.
- `scripts/load_test.py`: live latency/throughput measurements saved only after test run.
- `scripts/simulator.py`: multi-sensor synthetic event generator.
- `docs/ARCHITECTURE.md`, `docs/API_REFERENCE.md`, `docs/LOAD_TEST_REPORT.md`: decisions and reproduction.

## Functional testing checklist

- [ ] Install required packages on user PC
- [ ] Run Django migrations against MySQL
- [ ] Verify 6 app tables + default Django tables
- [ ] Install MySQL stored routines, triggers and views without errors
- [ ] Create organizer and seed sensors/rules
- [ ] Log in to Streamlit
- [ ] Send a single reading and verify it appears in MySQL
- [ ] Send a batch and verify idempotency
- [ ] Run worker and verify instant threshold alert
- [ ] Send 2+ consecutive samples and verify one rolling-window alert per bucket
- [ ] Acknowledge, then resolve an alert, checking audit rows
- [ ] Stop worker/server, submit/restart, verify durable queue recovery
- [ ] Measure 10k burst three times and save report (not yet measured)
- [ ] Test invalid API key, invalid metric, unknown sensor, disabled rule

## Invariants, risks, and next action

- Django migrations are canonical schema owner. SQL DDL mirror is separate; do not double-install.
- One worker is recommended for V1. Out-of-order late-arrival windows and concurrency need V2 support.
- Manual retries rely on event IDs and alert dedupe keys.
- `new_candidates` is not exact concurrent insertion count; no DB commit may be inferred on failed request.
- Status audit via MySQL trigger requires SQL 02 installed. SQLite tests use Python fallback.
- Use only synthetic data for initial verification, do not expose dev server online.
- Do not claim benchmark passed until measured on real MySQL.

**Recommended next session:** user runs setup locally and provides migration output, MySQL routine import output and Django test output. Fix any OS-specific install issues first, then verify end-to-end API/UI, then execute benchmark and optimize based on measured bottlenecks.
