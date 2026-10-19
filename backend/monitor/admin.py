from django.contrib import admin
from .models import Sensor, Rule, Reading, Alert, AlertAudit, DailySensorSummary

@admin.register(Sensor)
class SensorAdmin(admin.ModelAdmin):
    list_display = ("sensor_id", "name", "location", "is_active")
    search_fields = ("sensor_id", "name", "location")

@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = ("name", "metric_type", "kind", "operator", "threshold", "enabled")
    list_filter = ("enabled", "metric_type", "kind")

@admin.register(Reading)
class ReadingAdmin(admin.ModelAdmin):
    list_display = ("event_id", "sensor", "metric_type", "value", "recorded_at", "processed_at")
    list_filter = ("metric_type",)
    search_fields = ("event_id", "sensor__sensor_id")

@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("id", "sensor", "rule", "severity", "status", "created_at")
    list_filter = ("status", "severity")

admin.site.register(AlertAudit)
admin.site.register(DailySensorSummary)
