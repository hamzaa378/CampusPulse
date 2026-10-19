# Manually authored initial migration, equivalent to monitor.models v1.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators

class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="Sensor", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("sensor_id", models.SlugField(max_length=80, unique=True)),
            ("name", models.CharField(max_length=120)),
            ("location", models.CharField(max_length=160)),
            ("is_active", models.BooleanField(default=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
        ], options={"db_table": "monitor_sensor", "ordering": ["sensor_id"]}),
        migrations.CreateModel(name="Rule", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("name", models.CharField(max_length=120)),
            ("metric_type", models.CharField(choices=[("temperature", "Temperature"), ("air_quality", "Air Quality"), ("occupancy", "Occupancy"), ("humidity", "Humidity"), ("noise", "Noise"), ("other", "Other")], max_length=24)),
            ("kind", models.CharField(choices=[("instant", "Single reading"), ("window", "Rolling average")], default="instant", max_length=12)),
            ("operator", models.CharField(choices=[("GT", "GT"), ("GTE", "GTE"), ("LT", "LT"), ("LTE", "LTE"), ("EQ", "EQ")], default="GT", max_length=4)),
            ("threshold", models.DecimalField(decimal_places=4, max_digits=14)),
            ("window_seconds", models.PositiveIntegerField(default=600, validators=[django.core.validators.MinValueValidator(30), django.core.validators.MaxValueValidator(86400)])),
            ("min_samples", models.PositiveIntegerField(default=2, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(100000)])),
            ("severity", models.CharField(choices=[("info", "Info"), ("warning", "Warning"), ("critical", "Critical")], default="warning", max_length=12)),
            ("enabled", models.BooleanField(default=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ("sensor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="rules", to="monitor.sensor")),
        ], options={"db_table": "monitor_rule", "ordering": ["id"], "indexes": [models.Index(fields=["enabled", "metric_type"], name="mon_rule_metric_idx")]}),
        migrations.CreateModel(name="Reading", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("event_id", models.CharField(max_length=64, unique=True)),
            ("metric_type", models.CharField(choices=[("temperature", "Temperature"), ("air_quality", "Air Quality"), ("occupancy", "Occupancy"), ("humidity", "Humidity"), ("noise", "Noise"), ("other", "Other")], max_length=24)),
            ("value", models.DecimalField(decimal_places=4, max_digits=14)),
            ("recorded_at", models.DateTimeField()),
            ("received_at", models.DateTimeField(auto_now_add=True)),
            ("processed_at", models.DateTimeField(blank=True, null=True)),
            ("sensor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="readings", to="monitor.sensor")),
        ], options={"db_table": "monitor_reading", "ordering": ["-recorded_at"], "indexes": [
            models.Index(fields=["processed_at", "recorded_at", "id"], name="mon_read_queue_idx"),
            models.Index(fields=["sensor", "metric_type", "recorded_at"], name="mon_read_timeseries_idx")]}),
        migrations.CreateModel(name="Alert", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("dedupe_key", models.CharField(max_length=64, unique=True)),
            ("metric_type", models.CharField(max_length=24)),
            ("kind", models.CharField(max_length=12)),
            ("severity", models.CharField(max_length=12)),
            ("status", models.CharField(choices=[("open", "Open"), ("acknowledged", "Acknowledged"), ("resolved", "Resolved")], default="open", max_length=16)),
            ("trigger_value", models.DecimalField(decimal_places=4, max_digits=14)),
            ("threshold", models.DecimalField(decimal_places=4, max_digits=14)),
            ("message", models.CharField(max_length=300)),
            ("window_start", models.DateTimeField(blank=True, null=True)),
            ("window_end", models.DateTimeField(blank=True, null=True)),
            ("occurred_at", models.DateTimeField()),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
            ("resolved_at", models.DateTimeField(blank=True, null=True)),
            ("acknowledged_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="acknowledged_alerts", to=settings.AUTH_USER_MODEL)),
            ("resolved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="resolved_alerts", to=settings.AUTH_USER_MODEL)),
            ("reading", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="monitor.reading")),
            ("rule", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="alerts", to="monitor.rule")),
            ("sensor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="alerts", to="monitor.sensor")),
        ], options={"db_table": "monitor_alert", "ordering": ["-created_at"], "indexes": [
            models.Index(fields=["status", "-created_at"], name="mon_alert_status_idx"),
            models.Index(fields=["sensor", "-created_at"], name="mon_alert_sensor_idx")]}),
        migrations.CreateModel(name="AlertAudit", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("old_status", models.CharField(blank=True, max_length=16, null=True)),
            ("new_status", models.CharField(max_length=16)),
            ("changed_at", models.DateTimeField(auto_now_add=True)),
            ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ("alert", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="audit_events", to="monitor.alert")),
        ], options={"db_table": "monitor_alert_audit", "indexes": [models.Index(fields=["alert", "changed_at"], name="mon_audit_alert_idx")]}),
        migrations.CreateModel(name="DailySensorSummary", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("metric_type", models.CharField(max_length=24)),
            ("day", models.DateField()),
            ("reading_count", models.PositiveIntegerField(default=0)),
            ("avg_value", models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True)),
            ("min_value", models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True)),
            ("max_value", models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True)),
            ("refreshed_at", models.DateTimeField(auto_now=True)),
            ("sensor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="monitor.sensor")),
        ], options={"db_table": "monitor_daily_summary", "constraints": [models.UniqueConstraint(fields=("sensor", "metric_type", "day"), name="mon_daily_unique")]}),
    ]
