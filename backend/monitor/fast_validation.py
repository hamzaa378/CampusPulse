"""Fast, strict, single-pass sensor reading validation.

Keep API contracts compatible with ReadingInSerializer. Invalid batch never gets
written. No third-party JSON/vector validator or database schema change.
"""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from django.utils import timezone as django_timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError

from .models import METRICS

METRIC_NAMES = frozenset(name for name, _ in METRICS)
SLUG = re.compile(r"^[A-Za-z0-9_-]+$")
QUANTUM = Decimal("0.0001")


def normalize_batch(payload):
    """Return ordered unique (event ID, sensorId, metric, Decimal, UTC datetime).

    Deduplication occurs before any INSERT. Errors contain the reading index so
    organizers can repair the batch without searching a 10,000-row payload.
    """
    if not isinstance(payload, list) or not payload:
        raise ValidationError({"readings": "Supply a nonempty list of readings."})
    if len(payload) > 10000:
        raise ValidationError({"readings": "A batch may contain at most 10000 readings."})
    cutoff = django_timezone.now() + timedelta(minutes=5)
    unique = {}
    for index, record in enumerate(payload):
        try:
            if not isinstance(record, dict):
                raise ValueError("Each reading must be a JSON object")
            sensor = record.get("sensorId")
            if not isinstance(sensor, str) or not (1 <= len(sensor) <= 80) or not SLUG.fullmatch(sensor):
                raise ValueError("sensorId must be a slug with at most 80 characters")
            metric = record.get("type")
            if metric not in METRIC_NAMES:
                raise ValueError("Invalid metric type")
            raw_value = record.get("value")
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float, str, Decimal)):
                raise ValueError("value must be a decimal number")
            try:
                number = Decimal(str(raw_value))
                if not number.is_finite():
                    raise ValueError("value must be finite")
                # DRF DecimalField(max_digits=14, decimal_places=4): reject
                # surplus fractional digits instead of silently rounding them.
                sign, digits, exponent = number.as_tuple()
                decimals = max(-exponent, 0)
                whole = max(len(digits) + exponent, 0)
                if decimals > 4 or whole > 10 or whole + decimals > 14:
                    raise ValueError("value supports at most 14 digits, including 4 decimals")
                number = number.quantize(QUANTUM)
            except (InvalidOperation, OverflowError) as exc:
                raise ValueError("value must be a valid decimal number") from exc
            raw_time = record.get("timestamp")
            if isinstance(raw_time, datetime):
                stamped = raw_time
            elif isinstance(raw_time, str):
                stamped = parse_datetime(raw_time)
            else:
                stamped = None
            if stamped is None:
                raise ValueError("timestamp must be an ISO-8601 date-time")
            if django_timezone.is_naive(stamped):
                stamped = stamped.replace(tzinfo=timezone.utc)
            stamped = stamped.astimezone(timezone.utc)
            if stamped > cutoff:
                raise ValueError("Timestamp is more than five minutes in the future")
            event_id = record.get("eventId")
            if event_id is not None:
                if not isinstance(event_id, str) or not (1 <= len(event_id.strip()) <= 64):
                    raise ValueError("eventId must contain 1-64 characters")
                event_id = event_id.strip()
            else:
                canonical = json.dumps([sensor, metric, str(number), stamped.isoformat()],
                                       separators=(",", ":"))
                event_id = hashlib.sha256(canonical.encode()).hexdigest()
            signature = (sensor, metric, number, stamped)
            previous = unique.get(event_id)
            if previous is not None and previous != signature:
                raise ValueError(f"Conflicting payloads for duplicate event ID: {event_id}")
            if previous is None:
                unique[event_id] = signature
        except (TypeError, ValueError) as exc:
            raise ValidationError({"readings": {str(index): str(exc)}}) from exc
    return unique
