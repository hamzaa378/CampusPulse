# REST API contract

Base: `http://127.0.0.1:8010/api` (V2 recommended development port).

Authentication: organizer API uses `Authorization: Token <token>`. Sensor ingestion uses `X-Sensor-Key: <secret>` (>=16 characters) or staff token. Organizer accounts must have `is_staff=True`. Unknown and inactive sensors are rejected for ingestion. Both ingest routes return `202 Accepted` after MySQL persistence, not after rule evaluation.

| Method | Route | Authentication | Meaning |
|---|---|---|---|
| GET | `/health/` | Public | Liveness only, not a database readiness check |
| POST | `/auth/login/` | Staff username/password | Return API token |
| GET | `/auth/me/` | Staff token | Logged-in profile |
| GET/POST | `/sensors/` | Staff token | List/create sensors |
| GET/PATCH/DELETE | `/sensors/{id}/` | Staff token | Manage one sensor |
| GET/POST | `/rules/` | Staff token | List/create alert rules |
| GET/PATCH/DELETE | `/rules/{id}/` | Staff token | Manage a rule |
| POST | `/readings/` | Sensor key or staff token | Submit one reading |
| POST | `/readings/batch/` | Sensor key or staff token | Batch max 10,000 (`{"readings":[...]}` or a top-level JSON array) |
| GET | `/readings/?sensor=x&type=temperature&limit=100` | Staff token | Most recent readings |
| GET | `/dashboard/` | Staff token | Sensor, queue, rule, alert statistics |
| GET | `/alerts/?status=open` | Staff token | Alerts, filter by status or `sensor` |
| POST | `/alerts/{id}/acknowledge/` | Staff token | Open → acknowledged |
| POST | `/alerts/{id}/resolve/` | Staff token | Open/acknowledged → resolved |
| POST | `/worker/process-once/` | Staff token | Process one pending batch for testing (`{"limit":500}`) |

## Reading structure

```json
{"eventId":"optional-unique-id", "sensorId":"library-floor-2", "type":"temperature", "value":34.5, "timestamp":"2026-10-19T10:30:00Z"}
```

`eventId` may be omitted: the server hashes canonical sensor ID, metric, normalized Decimal value and UTC timestamp into a deterministic ID to make network retries idempotent. For repeated measurements at identical timestamps and values, provide distinct stable `eventId`s to avoid unintended deduplication. Max future timestamp = 5 minutes. Valid metrics: `temperature`, `air_quality`, `occupancy`, `humidity`, `noise`, `other`.

Batch response sample:

```json
{"received":1,"unique_in_request":1,"already_present":0,"new_candidates":1,"status":"durably_queued","engine":"mysql_native_bulk","timings_ms":{"validation":0.2,"lookup":1.1,"prepare":0.1,"insert_commit":1.8,"total":3.2},"note":"Rules are evaluated asynchronously by the alert worker."}
```

Timing numbers in the example are illustrative, NOT real benchmarks. On V2, `CAMPUS_INGEST_MODE=legacy` removes `timings_ms`; use the real benchmark output for speed claims. The `new_candidates` number is not a concurrency-safe exact inserted row count because the DB may discard conflicting IDs during concurrent writes. A `202` means the server completed the DB insert transaction.

## Rule creation example

```json
{"name":"Library hot 10-minute mean","sensor":1,"metric_type":"temperature",
 "kind":"window","operator":"GT","threshold":"32.0000",
 "window_seconds":600,"min_samples":2,"severity":"critical","enabled":true}
```

`kind`: `instant` or `window`. `operator`: `GT`/`GTE`/`LT`/`LTE`/`EQ`. `sensor` can be null to apply to all sensors reporting this metric. Rolling window includes observations from `t-window_seconds` through `t` inclusive, with one event per fixed UTC time bucket when breached. The worker evaluates only when a reading arrives; no cron rule execution for windows with no incoming readings.

## HTTP errors

- 400: malformed value, invalid sensor ID, invalid timestamp or bad rule state.
- 401: missing/invalid credentials (staff routes or ingest key).
- 403: authenticated user lacks staff permissions.
- 404: nonexistent resource.
- 409: invalid alert state transition.
- 202: reading request durably queued, not yet evaluated.
