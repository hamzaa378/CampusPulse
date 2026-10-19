"""Schema source of truth: Django migrations. SQL reference mirrors these models."""
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

METRICS = [(m, m.replace("_", " ").title()) for m in (
    "temperature", "air_quality", "occupancy", "humidity", "noise", "other"
)]
OPERATORS = [(m, m) for m in ("GT", "GTE", "LT", "LTE", "EQ")]


class Sensor(models.Model):
    sensor_id = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    location = models.CharField(max_length=160)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "monitor_sensor"
        ordering = ["sensor_id"]

    def __str__(self):
        return self.sensor_id


class Rule(models.Model):
    KIND = [("instant", "Single reading"), ("window", "Rolling average")]
    name = models.CharField(max_length=120)
    sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE, null=True, blank=True,
                               related_name="rules")
    metric_type = models.CharField(max_length=24, choices=METRICS)
    kind = models.CharField(max_length=12, choices=KIND, default="instant")
    operator = models.CharField(max_length=4, choices=OPERATORS, default="GT")
    threshold = models.DecimalField(max_digits=14, decimal_places=4)
    window_seconds = models.PositiveIntegerField(default=600, validators=[MinValueValidator(30), MaxValueValidator(86400)])
    min_samples = models.PositiveIntegerField(default=2, validators=[MinValueValidator(1), MaxValueValidator(100000)])
    severity = models.CharField(max_length=12, choices=[("info", "Info"), ("warning", "Warning"),
                                                       ("critical", "Critical")], default="warning")
    enabled = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "monitor_rule"
        indexes = [models.Index(fields=["enabled", "metric_type"], name="mon_rule_metric_idx")]
        ordering = ["id"]

    def __str__(self):
        return self.name


class Reading(models.Model):
    event_id = models.CharField(max_length=64, unique=True)
    sensor = models.ForeignKey(Sensor, on_delete=models.PROTECT, related_name="readings")
    metric_type = models.CharField(max_length=24, choices=METRICS)
    value = models.DecimalField(max_digits=14, decimal_places=4)
    recorded_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "monitor_reading"
        indexes = [
            models.Index(fields=["processed_at", "recorded_at", "id"], name="mon_read_queue_idx"),
            models.Index(fields=["sensor", "metric_type", "recorded_at"], name="mon_read_timeseries_idx"),
        ]
        ordering = ["-recorded_at"]


class Alert(models.Model):
    STATUS = [("open", "Open"), ("acknowledged", "Acknowledged"), ("resolved", "Resolved")]
    dedupe_key = models.CharField(max_length=64, unique=True)
    rule = models.ForeignKey(Rule, on_delete=models.PROTECT, related_name="alerts")
    sensor = models.ForeignKey(Sensor, on_delete=models.PROTECT, related_name="alerts")
    reading = models.ForeignKey(Reading, on_delete=models.SET_NULL, null=True, blank=True)
    metric_type = models.CharField(max_length=24)
    kind = models.CharField(max_length=12)
    severity = models.CharField(max_length=12)
    status = models.CharField(max_length=16, choices=STATUS, default="open")
    trigger_value = models.DecimalField(max_digits=14, decimal_places=4)
    threshold = models.DecimalField(max_digits=14, decimal_places=4)
    message = models.CharField(max_length=300)
    window_start = models.DateTimeField(null=True, blank=True)
    window_end = models.DateTimeField(null=True, blank=True)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="acknowledged_alerts",
                                        on_delete=models.SET_NULL, null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="resolved_alerts",
                                    on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "monitor_alert"
        indexes = [models.Index(fields=["status", "-created_at"], name="mon_alert_status_idx"),
                   models.Index(fields=["sensor", "-created_at"], name="mon_alert_sensor_idx")]
        ordering = ["-created_at"]


class AlertAudit(models.Model):
    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name="audit_events")
    old_status = models.CharField(max_length=16, null=True, blank=True)
    new_status = models.CharField(max_length=16)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "monitor_alert_audit"
        indexes = [models.Index(fields=["alert", "changed_at"], name="mon_audit_alert_idx")]


class DailySensorSummary(models.Model):
    sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE)
    metric_type = models.CharField(max_length=24)
    day = models.DateField()
    reading_count = models.PositiveIntegerField(default=0)
    avg_value = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    min_value = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    max_value = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    refreshed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "monitor_daily_summary"
        constraints = [models.UniqueConstraint(fields=["sensor", "metric_type", "day"], name="mon_daily_unique")]
