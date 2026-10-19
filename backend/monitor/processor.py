"""Durable alert worker: reads pending DB records and processes windows chronologically.

Window semantics: rolling lookback [t - window_seconds, t], min_samples; at most
one alert per fixed UTC time bucket / rule / sensor. This avoids alert storms.
For reproducibility run ONE worker when window rules are enabled in v1.
"""
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone as utc_timezone
from decimal import Decimal
import hashlib
from django.db import transaction
from django.utils import timezone
from .models import Alert, AlertAudit, Reading, Rule


def compare(value, operator, threshold):
    return {"GT": lambda: value > threshold, "GTE": lambda: value >= threshold,
            "LT": lambda: value < threshold, "LTE": lambda: value <= threshold,
            "EQ": lambda: value == threshold}[operator]()


def audit_python(alert, old_status, actor=None):
    """Only for SQLite / tests; MySQL status triggers maintain the same audit table."""
    from django.db import connection
    if connection.vendor != "mysql":
        AlertAudit.objects.create(alert=alert, old_status=old_status,
                                  new_status=alert.status, actor=actor)


def _alert(rule, reading, metric, *, key, start=None, end=None):
    return Alert(dedupe_key=hashlib.sha256(key.encode()).hexdigest(),
                 rule=rule, sensor=reading.sensor, reading=reading,
                 metric_type=reading.metric_type, kind=rule.kind,
                 severity=rule.severity, trigger_value=metric, threshold=rule.threshold,
                 message=f"{rule.name}: {reading.sensor.sensor_id} {reading.metric_type} "
                         f"{metric:.4f} {rule.operator} {rule.threshold:.4f}",
                 window_start=start, window_end=end, occurred_at=reading.recorded_at)


@transaction.atomic
def process_batch(limit=500):
    limit = max(1, min(int(limit), 2000))
    readings = list(Reading.objects.select_for_update(skip_locked=True)
                    .filter(processed_at__isnull=True).select_related("sensor")
                    .order_by("recorded_at", "id")[:limit])
    if not readings:
        return {"processed": 0, "alert_candidates": 0, "pending": 0}
    rules_by_metric = defaultdict(list)
    for rule in Rule.objects.filter(enabled=True):
        rules_by_metric[rule.metric_type].append(rule)
    first_seen = {}
    for r in readings:
        first_seen.setdefault((r.sensor_id, r.metric_type), r.recorded_at)
    window_state = {}
    alerts = []
    local_keys = set()
    for reading in readings:
        for rule in rules_by_metric.get(reading.metric_type, []):
            if rule.sensor_id and rule.sensor_id != reading.sensor_id:
                continue
            if rule.kind == "instant":
                if compare(reading.value, rule.operator, rule.threshold):
                    key = f"i:{rule.pk}:{reading.pk}"
                    new = _alert(rule, reading, reading.value, key=key)
                    if new.dedupe_key not in local_keys:
                        alerts.append(new)
                        local_keys.add(new.dedupe_key)
                continue
            state_key = (reading.sensor_id, reading.metric_type, rule.pk)
            if state_key not in window_state:
                first_time = first_seen[(reading.sensor_id, reading.metric_type)]
                earlier = Reading.objects.filter(sensor_id=reading.sensor_id,
                         metric_type=reading.metric_type, processed_at__isnull=False,
                         recorded_at__gte=first_time - timedelta(seconds=rule.window_seconds),
                         recorded_at__lt=first_time).order_by("recorded_at", "id").values_list("recorded_at", "value")
                q = deque(earlier)
                s = sum((v for _, v in q), Decimal("0"))
                window_state[state_key] = [q, s]
            q, running_sum = window_state[state_key]
            q.append((reading.recorded_at, reading.value))
            running_sum += reading.value
            cutoff = reading.recorded_at - timedelta(seconds=rule.window_seconds)
            while q and q[0][0] < cutoff:
                _, previous_value = q.popleft()
                running_sum -= previous_value
            window_state[state_key][1] = running_sum
            if len(q) < rule.min_samples:
                continue
            average = running_sum / Decimal(len(q))
            if compare(average, rule.operator, rule.threshold):
                # Time-window dedupe: one alert for each sensor/rule/aligned UTC bucket.
                bucket = int(reading.recorded_at.timestamp()) // rule.window_seconds * rule.window_seconds
                start = datetime.fromtimestamp(bucket, tz=utc_timezone.utc)
                end = start + timedelta(seconds=rule.window_seconds)
                new = _alert(rule, reading, average.quantize(Decimal("0.0001")),
                             key=f"w:{rule.pk}:{reading.sensor_id}:{bucket}", start=start, end=end)
                if new.dedupe_key not in local_keys:
                    alerts.append(new)
                    local_keys.add(new.dedupe_key)
    if alerts:
        Alert.objects.bulk_create(alerts, batch_size=500, ignore_conflicts=True)
        # MySQL triggers create audit rows; SQLite test mode requires application audit.
        from django.db import connection
        if connection.vendor != "mysql":
            existing = Alert.objects.filter(dedupe_key__in=list(local_keys))
            audited = set(AlertAudit.objects.filter(alert__in=existing).values_list("alert_id", flat=True))
            AlertAudit.objects.bulk_create([AlertAudit(alert=a, new_status="open") for a in existing if a.pk not in audited])
    Reading.objects.filter(pk__in=[r.pk for r in readings]).update(processed_at=timezone.now())
    return {"processed": len(readings), "alert_candidates": len(alerts),
            "pending": Reading.objects.filter(processed_at__isnull=True).count()}
