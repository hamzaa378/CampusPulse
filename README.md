# CampusPulse · GDG Tech Wildcard Entry

**Backend Task 1 — Campus Sensor Monitoring and Alerts**

A functional V1 project with **MySQL 8 + Django REST Framework + Streamlit**. Sensors post individual readings or batches of up to 10,000 items. Django persists readings into indexed MySQL tables; a durable, independently running worker processes instant thresholds and rolling-window averages; organizers review alerts in Streamlit.

> V1 source is complete enough for integration testing, but **10,000 readings in one second is a performance target, not a proven benchmark**. See `docs/LOAD_TEST_REPORT.md` and run the supplied measurement script against your own MySQL server. Full live testing could not be performed inside the artifact-authoring environment because dependencies and a MySQL instance are unavailable.

## What is implemented

- API-key-protected single and bulk ingestion, strict serializer validation, event-ID idempotency, indexed durable pending queue, and batch-size limits.
- Sensor registration, activation/deactivation; staff-only token login.
- Rule create, read, edit, delete; enable/disable; instant or rolling-average conditions; configurable comparator, threshold, severity, sample minimum, sensor-specific/global scope.
- Dedicated worker command + manual processing endpoint for demos; transactionally creates alerts and marks readings processed.
- Open → acknowledged → resolved alert lifecycle with audit trail, enforced by SQL triggers for MySQL (application fallback for SQLite tests).
- MySQL database creation script, six application table DDL definitions, four triggers, two deterministic functions, four procedures (one uses a cursor), four views, SQL seed and verification scripts.
- Streamlit overview, sensor manager, rule editor, alerts, simulator, and API health screen.
- Django API tests, independent simulator, measured 10,000-reading burst script, setup and design docs.

## Prerequisites

- **Windows 10/11 or Linux**, Python **3.11–3.13**, MySQL **8.0+** running locally, and Git (optional).
- MySQL CLI (`mysql.exe`) and an administrator account. `mysqlclient` has precompiled wheels on many Python/platform combinations; if installation fails on Windows, install a supported Python release and MySQL development dependencies.
- The Streamlit dashboard is for organizers, not a public internet-exposed site. Use HTTPS and a process supervisor for nonlocal deployment.

## 1. Initial setup in PowerShell

```powershell
cd GDG_CampusPulse_V1
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`: change **DJANGO_SECRET_KEY**, **DB_PASSWORD**, and **SENSOR_API_KEY** to long nondefault secrets. Leave `DB_ENGINE=mysql`. Keep secrets out of Git.

## 2. Create MySQL database and user

Edit passwords in `mysql/00_create_database.sql` to match `.env`. Open terminal as a MySQL administrator:

```powershell
mysql -u root -p < mysql/00_create_database.sql
```

**PowerShell note:** PowerShell 7 does not support `<` input redirection. Use `cmd /c "mysql -u root -p < mysql\00_create_database.sql"` or open Command Prompt. If `mysql` is not recognized, add `C:\Program Files\MySQL\MySQL Server 8.0\bin` (adjust version) to PATH, or run `mysql.exe` with its full path.

## 3. Install Django schema, routines, views, demo content

```powershell
cd backend
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo
cd ..
cmd /c "mysql -u root -p gdg_campus_monitor < mysql\02_programmability.sql"
```

`python manage.py migrate` **creates the actual tables**, using the committed `monitor/migrations/0001_initial.py` and built-in Django auth migrations. The full MySQL **CREATE TABLE** statements are supplied in `mysql/01_schema_mysql.sql` for independent SQL review or SQL-first recreation. **Do not run the schema DDL and then blindly run normal migrations**; migration history must match the existing schema. The canonical installation above is deliberate and avoids duplicate table conflicts.

The routine SQL must be installed before demonstrating MySQL audit triggers and views. MySQL triggers fire on all database writes, including writes made by Django.

### Confirm the SQL objects

```powershell
cmd /c "mysql -u root -p gdg_campus_monitor < mysql\04_verification.sql"
```

## 4. Run the three processes (three terminals)

Use `.venv` in each terminal. From the project root:

**Terminal A — Django API**

```powershell
cd backend
python manage.py runserver 127.0.0.1:8000
```

**Terminal B — reliable background alert worker**

```powershell
cd backend
python manage.py run_alert_worker --batch-size 500 --poll-seconds 0.5
```

**Terminal C — Streamlit UI**

```powershell
streamlit run frontend/app.py
```

Open the displayed Streamlit URL (normally `http://localhost:8501`). Log in using the Django superuser. Register sensors/rules on the dashboard, or use the demo seed data. The UI's **Sensor simulator** can send real requests to Django. The **Alerts** page can acknowledge and resolve generated alerts.

## 5. Run automated functional tests

For independent tests that **do not change or require your MySQL database**, set SQLite only in the test process:

```powershell
cd backend
$env:DB_ENGINE="sqlite"
python manage.py test monitor.tests -v 2
Remove-Item Env:DB_ENGINE
```

These tests cover permissions, API key, duplicate detection, bad-batch rejection, instant alerts, rolling windows, disabled rules, and alert lifecycle. **SQLite tests cannot prove MySQL trigger syntax or MySQL 10k/s performance**; those need the SQL verification and performance run on your host.

## 6. Run simulator and record REAL load-test results

From the root (separate terminal; worker and API running):

```powershell
python scripts/simulator.py --rounds 30 --interval 1
python scripts/load_test.py --count 10000 --repeat 3
```

Inspect `results/load_test.json` and record machine hardware, MySQL settings, HTTP duration, server logs and CPU before claiming a 10,000-reading/sec result. One HTTP request containing 10,000 readings is **not** proof of sustained 10,000/sec capacity. The background worker has a separate processing-rate measurement. The script does not fabricate numbers.

## Minimal API example

**Individual reading** (a sensor does not need an organizer login):

```http
POST /api/readings/
X-Sensor-Key: YOUR_LONG_SECRET
Content-Type: application/json

{"sensorId":"library-floor-2","type":"temperature","value":34.5,"timestamp":"2026-10-19T10:30:00Z"}
```

**Batch reading**:

```http
POST /api/readings/batch/
X-Sensor-Key: YOUR_LONG_SECRET
Content-Type: application/json

{"readings":[{"sensorId":"library-floor-2","type":"temperature","value":35.1,"timestamp":"2026-10-19T10:30:01Z"}]}
```

Organizer token:

```http
POST /api/auth/login/
Content-Type: application/json

{"username":"YOUR_SUPERUSER","password":"YOUR_PASSWORD"}
```

Use `Authorization: Token <returned-token>` for sensor/rule/alert/dashboard management requests. All relevant endpoints are listed in `docs/API_REFERENCE.md`.

## Project tree

```text
GDG_CampusPulse_V1/
├─ .env.example / .gitignore / requirements.txt
├─ README.md
├─ backend/
│  ├─ manage.py
│  ├─ campus_monitor/{settings,urls,asgi,wsgi}.py
│  └─ monitor/
│     ├─ models.py / serializers.py / services.py / processor.py / views.py
│     ├─ migrations/0001_initial.py
│     ├─ management/commands/{run_alert_worker,seed_demo}.py
│     └─ tests/{test_api,test_batch_limits}.py
├─ frontend/app.py
├─ mysql/
│  ├─ 00_create_database.sql
│  ├─ 01_schema_mysql.sql
│  ├─ 02_programmability.sql
│  ├─ 03_seed_demo.sql
│  └─ 04_verification.sql
├─ scripts/{simulator,load_test}.py
└─ docs/{ARCHITECTURE,API_REFERENCE,LOAD_TEST_REPORT,HANDOVER}.md
```

## Known V1 limitations and next-stage work

1. Ingestion is **synchronous MySQL bulk persistence** and background evaluation; Redis/Kafka, partitioning, backpressure, server-side queue lag alerting, worker supervision and HA are out of scope for V1. One worker is recommended for correct chronological window semantics; multiworker race-free window aggregates are V2 work.
2. For a window rule, at most **one alert per aligned UTC bucket** is generated; this deliberate dedupe does not emit one alert on every qualifying sample. An alert is emitted at the first qualifying observation within the bucket.
3. Pending records use the current active rule configuration when processed; rule versioning, event-time watermarking and late-arrival corrections are future work.
4. `bulk_create(ignore_conflicts=True)` enforces idempotency but `new_candidates` is not an exact concurrent-insert count; it reports records not already observed before insert. Clients should check queued/processed metrics for authoritative counts.
5. MySQL triggers must be explicitly installed by running `mysql/02_programmability.sql`. Test DBs created from migrations alone do not contain stored routines.
6. SQL reference schema is not an alternative to Django's full migration history; it assumes Django auth tables already exist.
7. Streamlit V1 loads the first configured page of sensors/rules and a limited number of alerts. Add server-side filtering/pagination controls for large fleets.

**See `docs/HANDOVER.md` to continue the project with all setup, files, constraints and next actions in one place.** Static generation checks are recorded in `docs/STATIC_VERIFICATION.md` and can be repeated with `python scripts/static_check.py`.
