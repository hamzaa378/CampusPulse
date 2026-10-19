# Architecture, database design and reliability decisions

## Data path

```
Sensor simulator / HTTP client
       |   X-Sensor-Key
       v
Django API -> serializer -> sensor authorization -> deduplication -> MySQL monitor_reading
                                                                  |
                                                   Pending: processed_at IS NULL
                                                                  |
                                             run_alert_worker (separate process)
                                                                  |
                                           instant / rolling average evaluation
                                                                  |
                                            MySQL monitor_alert (+ audit trigger)
                                                                  |
                                         Django staff REST API -> Streamlit UI
```

All payload processing happens after a database transaction commits. A worker crash before commit rolls back both alerts and progress, allowing restart to safely retry readings. Unique event IDs and unique dedupe keys prevent duplicate records and repeated alerts on retries. SQLite tests use Python audit writes when native MySQL triggers are not present. MySQL deployment must install stored routines and triggers after migrations.

## Domain tables

1. **monitor_sensor**: identity, location, active flag.
2. **monitor_rule**: sensor/metric scope, comparison, instant vs window, severity, enabled.
3. **monitor_reading**: durable sensor data and worker progress, unique event ID.
4. **monitor_alert**: triggered incident, rule snapshot, lifecycle, unique alert key.
5. **monitor_alert_audit**: append-only open/acknowledge/resolve transitions.
6. **monitor_daily_summary**: offline cursor-procedure-derived daily aggregates.

Django's `auth_user`, `authtoken_token`, etc. are created by its built-in migrations. MySQL uses InnoDB transactions and UTC timestamps. Foreign keys enforce link integrity. Queue index `(processed_at, recorded_at, id)` supports selection of unprocessed records. Time-series index `(sensor_id, metric_type, recorded_at)` supports window history. Unique constraints enforce ingestion and alert idempotency.

## SQL programming objects

- **Functions**: `fn_rule_matches` (pure operator comparison), `fn_alert_priority` (severity/status order).
- **Triggers**: `trg_rule_validate_insert`, `trg_rule_validate_update`, `trg_alert_open_audit`, `trg_alert_state_audit`.
- **Procedures**: `sp_acknowledge_alert`, `sp_resolve_alert` (transactional), `sp_sensor_alert_counts`, `sp_refresh_daily_summary` (CURSOR loop over sensors).
- **Views**: `vw_sensor_latest`, `vw_alert_overview`, `vw_rule_health`, `vw_sensor_daily_summary`.

Django owns request/state transitions so serializer permissions and API errors stay consistent. Database procedures also permit direct SQL demonstrations; both paths write to the same tables and fire the same audit triggers. Rule comparison in Python mirrors `fn_rule_matches` to avoid SQL calls per incoming sample.

## Burst handling and performance tradeoffs

The API allows *a single request with up to 10,000 readings*. Input is validated before writes, checked against registered active sensors in one query, deduplicated using unique event IDs, and inserted in batches of 1000. Alert processing is not on the HTTP request path. This allows independent measurement and tuning of ingest rate and alert-processing lag.

Do not equate accepting a 10k payload with achieving 10k **sustained** insertions per second. The load-test reports client wall time, network effects and server persistence. An actual benchmark needs a local/remote HTTP client, real MySQL, hardware/environment description, DB instrumentation, repeated trials and background worker metrics. V1 uses Django bulk insert + MySQL indexes rather than Kafka/Redis or distributed sharding.

## Rolling-window definition

For each `(sensor, metric, rule)` maintain a deque with readings in `[current_time - window_seconds, current_time]`. On each new reading, add it, evict values older than the window, and compute `sum / count` with Decimal arithmetic. `min_samples` prevents alerts from one weak reading. Grouping rules by metric avoids evaluating irrelevant rules.

The earliest pending reading in the worker chunk loads matching *already processed* historical measurements once per `(sensor, metric, rule)` state. Batch records are processed in recorded timestamp order. An alert is created once per `(rule,sensor, UTC-aligned time bucket)`, not once per qualifying sample. **Late out-of-order measurements across worker batches may cause different averages than a globally sorted replay**; watermarks/recompute support is an explicitly deferred V2 improvement. The worker should run as one instance in V1 for consistency of time windows. New rules apply only to readings still queued.

## Security

- Sensor writes require configured strong `X-Sensor-Key` or a staff token.
- Staff login uses Django password hashing, account state and DRF auth tokens.
- Default endpoints require token; public endpoints are only health and login.
- Django serializers validate types, size, timestamp and numeric precision.
- Keep `.env` private, disable DEBUG outside local testing, use HTTPS, narrow allowed hosts.
- To revoke a token: delete/recreate the user's DRF token. Shared sensor key is V1; per-sensor API keys can come in V2.
- The SQL bootstrap grants runtime account DDL and ROUTINE privileges for one-time setup; production should use distinct DB migrator and restricted runtime credentials.

## Recovery

The DB is the queue. An API restart does not lose already committed readings; the worker restarts and resumes from `processed_at IS NULL`. Transactional row selection and alert dedupe avoid double effects. Failed entire batches remain pending because the worker transaction rolls back. Long-running poison inputs need a dead-letter table/retry counter in V2.
