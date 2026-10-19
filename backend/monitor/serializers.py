"""Public REST payload contracts and validation."""
from datetime import timedelta, timezone as dt_timezone
from decimal import Decimal
from rest_framework import serializers
from django.utils import timezone
from .models import Sensor, Rule, Alert, Reading, METRICS


class SensorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sensor
        fields = ["id", "sensor_id", "name", "location", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class RuleSerializer(serializers.ModelSerializer):
    sensor_id = serializers.CharField(source="sensor.sensor_id", read_only=True)

    class Meta:
        model = Rule
        fields = ["id", "name", "sensor", "sensor_id", "metric_type", "kind", "operator",
                  "threshold", "window_seconds", "min_samples", "severity", "enabled", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        kind = attrs.get("kind", getattr(self.instance, "kind", "instant"))
        window = attrs.get("window_seconds", getattr(self.instance, "window_seconds", 600))
        min_samples = attrs.get("min_samples", getattr(self.instance, "min_samples", 2))
        if kind == "window" and not (30 <= window <= 86400):
            raise serializers.ValidationError({"window_seconds": "Must be between 30 and 86400."})
        if kind == "window" and min_samples < 1:
            raise serializers.ValidationError({"min_samples": "Must be positive."})
        return attrs


class AlertSerializer(serializers.ModelSerializer):
    sensor_id = serializers.CharField(source="sensor.sensor_id", read_only=True)
    rule_name = serializers.CharField(source="rule.name", read_only=True)
    class Meta:
        model = Alert
        fields = ["id", "sensor_id", "rule", "rule_name", "metric_type", "kind", "severity",
                  "status", "trigger_value", "threshold", "message", "window_start", "window_end",
                  "occurred_at", "created_at", "acknowledged_at", "resolved_at"]
        read_only_fields = fields


class ReadingInSerializer(serializers.Serializer):
    eventId = serializers.CharField(max_length=64, required=False, allow_blank=False)
    sensorId = serializers.SlugField(max_length=80)
    type = serializers.ChoiceField(choices=METRICS)
    value = serializers.DecimalField(max_digits=14, decimal_places=4)
    timestamp = serializers.DateTimeField(default_timezone=dt_timezone.utc)

    def validate_timestamp(self, value):
        if value > timezone.now() + timedelta(minutes=5):
            raise serializers.ValidationError("Timestamp is more than five minutes in the future.")
        return value


class ReadingOutSerializer(serializers.ModelSerializer):
    sensorId = serializers.CharField(source="sensor.sensor_id")
    type = serializers.CharField(source="metric_type")
    timestamp = serializers.DateTimeField(source="recorded_at")
    class Meta:
        model = Reading
        fields = ["id", "event_id", "sensorId", "type", "value", "timestamp", "received_at", "processed_at"]
