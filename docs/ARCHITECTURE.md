# Architecture — CampusPulse V2

## Data path

```text
    real sensors / simulator / CLI load-test
                       |
             API key or organizer token
                       |
                 Django + DRF
                       |
            V2 fast input validator
                       |
           unique eventId + sensor map
                       |
    existing event signature projections (MySQL)
                       |
      atomic native MySQL batch insert / no-op for retries
                       |
              MySQL monitor_reading
       (processed_at IS NULL is durable queue)
                       |
               SINGLE rule worker
          |                            |
   instant comparison          rolling deque + UTC bucket
          |                            |
          +------ monitor_alert -------+
                         |
              MySQL insert/update triggers
                         |
                 monitor_alert_audit
                         |
              Django management API
                         |
            Streamlit organizer dashboard
       + Performance Lab / imported JSON reports
```

## Storage and SQL constraints

Django migration `monitor/0001_initial.py` owns schema creation. The SQL mirror `mysql/01_schema_mysql.sql` is for reviewers/fresh-install documentation, **not** a second migration to run against a populated database. V2 has no schema changes. MySQL programmable objects remain **4 triggers, 4 procedures (1 cursor), 2 functions, 4 views**. SQL `05_v2_readonly_health.sql` shows non-destructive verification queries.

- Unique `monitor_reading.event_id`: idempotency
- Index `(processed_at, recorded_at, id)`: queued worker selection
- Index `(sensor_id, metric_type, recorded_at)`: rolling-window history
- Unique alert `dedupe_key`: avoid repeated alert creation
- Alert status audit triggers: create and transition history
- Daily summary cursor procedure: aggregate a date across active sensors

## Reliability contracts

1. Invalid or partially invalid batches are rejected before any rows are inserted.
2. Sensor keys cannot administer rules or alerts; staff token required.
3. The API returns 202 after a database transaction commits, before the worker handles alerts.
4. Retries with the same event identity/payload are no-op; differing existing payloads are rejected.
5. On MySQL, two requests racing on an event ID use conditional `ON DUPLICATE KEY UPDATE`; a conflicting concurrent payload causes a non-null constraint failure and full transaction rollback. Matching payloads no-op.
6. A worker crash can leave rows pending, recoverable by restarting the worker; database commits for alerts and `processed_at` occur in one transaction.
7. Alert worker is intentionally one process in V2 for predictable time-window order. `SELECT FOR UPDATE SKIP LOCKED` is present, but that by itself does not make parallel-window aggregation order-safe.
8. The `legacy` ingestion switch is an operational rollback path; it does not drop or alter tables.

## Optimization trade-offs

- Faster specialized validation is less general than DRF field validation. Regression tests validate supported metrics, ISO datetimes, numeric precision and failure cases. Unexpected new fields or future serializer rules must also be added to the fast validator.
- Native `executemany()` decreases Python object overhead but couples fast path to MySQL. SQLite always uses ORM `bulk_create` for portable tests.
- The system uses the same indexed MySQL table as a durable processing queue: simple to deploy and recover, but not a replacement for a partitioned streaming system under sustained multi-node load.
- The client benchmark includes JSON and HTTP time; server timing stages only cover work after request parsing.

## Security and production boundaries

Protect `.env`, database credentials, organizer tokens and sensor keys. Use HTTPS in any remotely accessible installation, tighten `ALLOWED_HOSTS`, disable Django DEBUG, add input rate limiting/observability/backups, and use a WSGI/ASGI application server rather than exposing Django `runserver`. These are development/research demonstrators, not audited production services.
