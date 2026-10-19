"""V2 ingestion parity, negative cases, exact retries and rollback semantics."""
from datetime import timedelta, timezone as utc_timezone
from decimal import Decimal
from django.test import TestCase, override_settings
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient
from monitor.models import Reading, Sensor

KEY = "x" * 40


@override_settings(SENSOR_API_KEY=KEY, CAMPUS_INGEST_MODE="fast")
class FastIngestTests(TestCase):
    def setUp(self):
        Sensor.objects.create(sensor_id="sensor-x", name="Sensor X", location="Library")
        self.client = APIClient()
        self.client.credentials(HTTP_X_SENSOR_KEY=KEY)
        self.time = (timezone.now() - timedelta(minutes=1)).replace(microsecond=123456)

    def sample(self, **changes):
        row = {"sensorId": "sensor-x", "type": "temperature", "value": "34.5000",
               "timestamp": self.time.isoformat(), "eventId": "event-x"}
        row.update(changes)
        return row

    def send(self, *rows):
        return self.client.post("/api/readings/batch/", {"readings": list(rows)}, format="json")

    def test_fast_path_accepts_and_reports_timings(self):
        response = self.send(self.sample())
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(response.data["engine"], "mysql_native_bulk" if
                         connection.vendor == "mysql" else "orm_bulk")
        self.assertGreaterEqual(response.data["timings_ms"]["total"], 0)
        self.assertEqual(Reading.objects.count(), 1)
        saved = Reading.objects.get()
        self.assertEqual(saved.value, Decimal("34.5000"))

    def test_replay_and_timestamp_timezone_equivalence(self):
        original = self.sample()
        self.assertEqual(self.send(original).status_code, 202)
        offset = self.time.astimezone(utc_timezone(timedelta(hours=5, minutes=30)))
        second = self.sample(timestamp=offset.isoformat(), value=34.5)
        result = self.send(second)
        self.assertEqual(result.status_code, 202, result.data)
        self.assertEqual(result.data["already_present"], 1)
        self.assertEqual(Reading.objects.count(), 1)

    def test_duplicate_inside_batch_collapses(self):
        response = self.send(self.sample(), self.sample())
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(response.data["received"], 2)
        self.assertEqual(response.data["unique_in_request"], 1)
        self.assertEqual(Reading.objects.count(), 1)

    def test_duplicate_id_different_value_rejected(self):
        response = self.send(self.sample(), self.sample(value="36.0"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Reading.objects.count(), 0)
        self.assertEqual(self.send(self.sample()).status_code, 202)
        self.assertEqual(self.send(self.sample(value="36.0")).status_code, 400)
        self.assertEqual(Reading.objects.count(), 1)

    def test_atomic_invalid_batch(self):
        response = self.send(self.sample(), self.sample(eventId="event-y", sensorId="missing"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Reading.objects.count(), 0)

    def test_strict_payload_validation(self):
        invalid = [
            {"value": "Infinity"}, {"value": "12.12345"}, {"value": "100000000000"},
            {"value": True}, {"sensorId": "bad sensor"}, {"type": "invalid"},
            {"eventId": "  "}, {"timestamp": "nope"},
            {"timestamp": (timezone.now() + timedelta(minutes=10)).isoformat()},
        ]
        for changes in invalid:
            with self.subTest(changes=changes):
                self.assertEqual(self.send(self.sample(**changes)).status_code, 400)
        self.assertEqual(Reading.objects.count(), 0)

    def test_auto_generated_hash_idempotent(self):
        row = self.sample()
        row.pop("eventId")
        first = self.send(row)
        second = self.send(row)
        self.assertEqual(first.status_code, 202, first.data)
        self.assertEqual(second.status_code, 202, second.data)
        self.assertEqual(Reading.objects.count(), 1)


@override_settings(SENSOR_API_KEY=KEY, CAMPUS_INGEST_MODE="legacy")
class LegacyRollbackTest(TestCase):
    def test_toggle_preserves_old_engine(self):
        Sensor.objects.create(sensor_id="sensor-x", name="X", location="Library")
        client = APIClient()
        client.credentials(HTTP_X_SENSOR_KEY=KEY)
        result = client.post("/api/readings/", {
            "sensorId": "sensor-x", "type": "temperature", "value": "35.0",
            "timestamp": (timezone.now() - timedelta(minutes=1)).isoformat(),
        }, format="json")
        self.assertEqual(result.status_code, 202, result.data)
        self.assertEqual(result.data["engine"], "legacy_serializer_orm")
