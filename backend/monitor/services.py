"""V2 durable ingestion: fast validation, projection-only dedupe, native MySQL writes.

The database remains the queue: a 202 is returned *after* a transaction commits.
The worker processes rows independently. V1 compatibility is available through
CAMPUS_INGEST_MODE=legacy for an A/B performance comparison and rollback.
"""
import time
from datetime import timezone as utc_timezone

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .fast_validation import normalize_batch
from .models import Reading, Sensor

MAX_BATCH = 10000


def ingest(payload):
    if getattr(settings, "CAMPUS_INGEST_MODE", "fast") == "legacy":
        return _ingest_legacy(payload)
    start = time.perf_counter()
    unique = normalize_batch(payload)
    validated = time.perf_counter()

    names = {signature[0] for signature in unique.values()}
    sensors = dict(Sensor.objects.filter(sensor_id__in=names, is_active=True)
                   .values_list("sensor_id", "id"))
    missing = sorted(names - set(sensors))
    if missing:
        raise ValidationError({"sensorId": f"Unknown or inactive sensors: {missing[:20]}"})
    keys = list(unique)
    existing = set()
    # values_list avoids the previous per-reading Sensor join and model creation.
    # SQLite's bind-variable limit can be lower; MySQL benefits from 2k chunks.
    lookup_chunk = 500 if connection.vendor == "sqlite" else 2000
    for offset in range(0, len(keys), lookup_chunk):
        found = Reading.objects.filter(event_id__in=keys[offset:offset + lookup_chunk]).values_list(
            "event_id", "sensor_id", "metric_type", "value", "recorded_at")
        for event_id, sensor_pk, metric, value, stamped in found:
            sensor, expected_metric, expected_value, expected_time = unique[event_id]
            if (sensor_pk != sensors[sensor] or metric != expected_metric or
                value != expected_value or stamped != expected_time):
                raise ValidationError({"eventId": f"Event ID {event_id} already exists with different data."})
            existing.add(event_id)
    looked_up = time.perf_counter()
    pending = [(event_id, sensors[sensor], metric, value, stamped)
               for event_id, (sensor, metric, value, stamped) in unique.items()
               if event_id not in existing]
    prepared = time.perf_counter()

    if pending:
        with transaction.atomic():
            if connection.vendor == "mysql":
                _insert_mysql(pending)
                engine = "mysql_native_bulk"
            else:
                _insert_orm(pending)
                engine = "orm_bulk"
    else:
        engine = "mysql_native_bulk" if connection.vendor == "mysql" else "orm_bulk"
    committed = time.perf_counter()
    return {
        "received": len(payload),
        "unique_in_request": len(unique),
        "already_present": len(existing),
        "new_candidates": len(pending),
        "status": "durably_queued",
        "note": "Rules are evaluated asynchronously by the alert worker.",
        "engine": engine,
        "timings_ms": {
            "validation": round((validated - start) * 1000, 3),
            "lookup": round((looked_up - validated) * 1000, 3),
            "prepare": round((prepared - looked_up) * 1000, 3),
            "insert_commit": round((committed - prepared) * 1000, 3),
            "total": round((committed - start) * 1000, 3),
        },
    }


def _insert_mysql(pending):
    """Explicit multi-VALUES inserts: at most 5 DB INSERT statements for 10k rows.

    Parameterized writes; no SQL string interpolation of sensor input. An
    idempotent duplicate is a no-op; a conflicting concurrent duplicate
    attempts a NULL write to event_id, which rolls back the full transaction.
    Do not use INSERT IGNORE, which can hide other constraint errors.
    """
    received = timezone.now().astimezone(utc_timezone.utc).replace(tzinfo=None)
    prefix = ("INSERT INTO monitor_reading "
              "(event_id, sensor_id, metric_type, value, recorded_at, received_at, processed_at) VALUES ")
    suffix = (" ON DUPLICATE KEY UPDATE event_id = IF("
              "sensor_id <=> VALUES(sensor_id) AND metric_type <=> VALUES(metric_type) "
              "AND value <=> VALUES(value) AND recorded_at <=> VALUES(recorded_at), "
              "event_id, NULL)")
    row_sql = "(%s, %s, %s, %s, %s, %s, NULL)"
    with connection.cursor() as cursor:
        for i in range(0, len(pending), 2000):
            rows = [(eid, sensor_pk, metric, value,
                     stamped.astimezone(utc_timezone.utc).replace(tzinfo=None), received)
                    for eid, sensor_pk, metric, value, stamped in pending[i:i + 2000]]
            # Explicit VALUES batching avoids dependence on driver-specific
            # executemany regex optimizations. Only placeholder templates and
            # constant SQL identifiers are concatenated, never user input.
            statement = prefix + ",".join([row_sql] * len(rows)) + suffix
            cursor.execute(statement, [arg for row in rows for arg in row])
            if cursor.rowcount != len(rows):
                # A concurrent insertion may have won the unique event_id race.
                # Verify identical payload rather than silently discarding a
                # conflicting event ID. This branch is not used on fresh bursts.
                expected = {eid: (pk, metric, value, stamped) for eid, pk, metric, value, stamped, _ in rows}
                recovered = Reading.objects.filter(event_id__in=list(expected)).values_list(
                    "event_id", "sensor_id", "metric_type", "value", "recorded_at")
                count = 0
                for eid, pk, metric, value, recorded in recovered:
                    count += 1
                    original = expected[eid]
                    recorded_utc = recorded.astimezone(utc_timezone.utc).replace(tzinfo=None)
                    if original != (pk, metric, value, recorded_utc):
                        raise ValidationError({"eventId": f"Concurrent conflict for event ID {eid}"})
                if count != len(rows):
                    raise ValidationError({"readings": "Database did not persist every accepted event."})


def _insert_orm(pending):
    objects = [Reading(event_id=eid, sensor_id=pk, metric_type=metric,
                       value=value, recorded_at=stamped)
               for eid, pk, metric, value, stamped in pending]
    Reading.objects.bulk_create(objects, batch_size=1000, ignore_conflicts=True)


def _ingest_legacy(payload):
    """Original V1 behavior, for controlled A/B runs and quick rollback."""
    import hashlib
    import json
    from rest_framework.exceptions import ValidationError
    from .serializers import ReadingInSerializer
    if not isinstance(payload, list) or not payload:
        raise ValidationError({"readings": "Supply a nonempty list of readings."})
    if len(payload) > MAX_BATCH:
        raise ValidationError({"readings": f"A batch may contain at most {MAX_BATCH} readings."})
    serializer = ReadingInSerializer(data=payload, many=True)
    serializer.is_valid(raise_exception=True)
    records = serializer.validated_data
    names = {record["sensorId"] for record in records}
    sensors = {s.sensor_id: s for s in Sensor.objects.filter(sensor_id__in=names, is_active=True)}
    missing = sorted(names - set(sensors))
    if missing:
        raise ValidationError({"sensorId": f"Unknown or inactive sensors: {missing[:20]}"})
    unique = {}
    for record in records:
        if "eventId" in record:
            key = record["eventId"]
        else:
            canonical = json.dumps([record["sensorId"], record["type"],
                                    str(record["value"]), record["timestamp"].astimezone(utc_timezone.utc).isoformat()],
                                   separators=(",", ":"))
            key = hashlib.sha256(canonical.encode()).hexdigest()
        signature = (record["sensorId"], record["type"], record["value"], record["timestamp"])
        if key in unique and unique[key][0] != signature:
            raise ValidationError({"eventId": f"Conflicting payloads for duplicate event ID: {key}"})
        unique[key] = (signature, record)
    keys = list(unique)
    existing = set()
    for offset in range(0, len(keys), 500):
        saved_rows = Reading.objects.filter(event_id__in=keys[offset:offset + 500]).select_related("sensor")
        for saved in saved_rows:
            signature, _ = unique[saved.event_id]
            if (saved.sensor.sensor_id, saved.metric_type, saved.value, saved.recorded_at) != signature:
                raise ValidationError({"eventId": f"Event ID {saved.event_id} already exists with different data."})
            existing.add(saved.event_id)
    pending = [Reading(event_id=event_id, sensor=sensors[rec["sensorId"]],
                       metric_type=rec["type"], value=rec["value"], recorded_at=rec["timestamp"])
               for event_id, (_, rec) in unique.items() if event_id not in existing]
    with transaction.atomic():
        if pending:
            Reading.objects.bulk_create(pending, batch_size=1000, ignore_conflicts=True)
    return {"received": len(payload), "unique_in_request": len(keys),
            "already_present": len(existing), "new_candidates": len(pending),
            "status": "durably_queued", "note": "Rules are evaluated by the alert worker.",
            "engine": "legacy_serializer_orm"}
