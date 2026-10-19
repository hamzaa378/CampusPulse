"""Batch ingestion: validation once, DB persistence in bulk, asynchronous evaluation later."""
import hashlib
import json
from datetime import timezone as dt_timezone
from django.db import transaction
from rest_framework.exceptions import ValidationError
from .models import Reading, Sensor
from .serializers import ReadingInSerializer

MAX_BATCH = 10000


def ingest(payload):
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
                                    str(record["value"]), record["timestamp"].astimezone(dt_timezone.utc).isoformat()],
                                   separators=(",", ":"))
            key = hashlib.sha256(canonical.encode()).hexdigest()
        # Identical event IDs with DIFFERENT payloads in the same batch are invalid.
        signature = (record["sensorId"], record["type"], record["value"], record["timestamp"])
        if key in unique and unique[key][0] != signature:
            raise ValidationError({"eventId": f"Conflicting payloads for duplicate event ID: {key}"})
        unique[key] = (signature, record)
    keys = list(unique)
    # MySQL imposes no practical problem with <=10k IDs; chunk queries for SQLite parameter limits.
    existing = set()
    for start in range(0, len(keys), 500):
        previous = Reading.objects.filter(event_id__in=keys[start:start + 500]).select_related("sensor")
        for saved in previous:
            signature, record = unique[saved.event_id]
            if (saved.sensor.sensor_id, saved.metric_type, saved.value, saved.recorded_at) != signature:
                raise ValidationError({"eventId": f"Event ID {saved.event_id} already exists with different data."})
            existing.add(saved.event_id)
    pending = [Reading(event_id=k, sensor=sensors[r["sensorId"]], metric_type=r["type"],
                       value=r["value"], recorded_at=r["timestamp"])
               for k, (_, r) in unique.items() if k not in existing]
    with transaction.atomic():
        # Unique event_id prevents duplicate records on concurrent retries. Only errors already
        # covered by serializer/FK checks should be ignored; use strict MySQL SQL mode.
        if pending:
            Reading.objects.bulk_create(pending, batch_size=1000, ignore_conflicts=True)
    # Another writer may race; 'new_candidates' is intentionally not called 'inserted'.
    return {"received": len(payload), "unique_in_request": len(keys),
            "already_present": len(existing), "new_candidates": len(pending),
            "status": "durably_queued", "note": "Rules are evaluated by the alert worker."}
