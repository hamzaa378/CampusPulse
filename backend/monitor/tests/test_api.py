"""Run in self-contained SQLite CI mode: DB_ENGINE=sqlite python manage.py test"""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from monitor.models import Alert, AlertAudit, Reading, Rule, Sensor
from monitor.processor import compare, process_batch

KEY = "x" * 40

@override_settings(SENSOR_API_KEY=KEY)
class CampusPulseTests(TestCase):
    def setUp(self):
        self.sensor = Sensor.objects.create(sensor_id="library-floor-2", name="Library", location="Floor 2")
        self.user = get_user_model().objects.create_user(username="operator", password="super_safe_pass_123", is_staff=True)
        self.client = APIClient()
        self.stamped = timezone.now() - timedelta(minutes=2)

    def record(self, value=34, second=0, event_id=None):
        payload = {"sensorId":"library-floor-2", "type":"temperature", "value":str(value),
                   "timestamp": (self.stamped + timedelta(seconds=second)).isoformat()}
        if event_id:
            payload["eventId"] = event_id
        return payload

    def auth(self):
        self.client.force_authenticate(user=self.user)

    def test_authentication_and_permissions(self):
        self.assertEqual(self.client.get("/api/sensors/").status_code, 401)
        self.assertEqual(self.client.post("/api/readings/", self.record(), format="json").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login/", {"username":"operator", "password":"bad"}).status_code, 401)
        logged = self.client.post("/api/auth/login/", {"username":"operator", "password":"super_safe_pass_123"})
        self.assertEqual(logged.status_code, 200)
        self.assertTrue(logged.data["token"])
        self.auth()
        self.assertEqual(self.client.get("/api/dashboard/").status_code, 200)

    def test_sensor_key_and_idempotency(self):
        self.client.credentials(HTTP_X_SENSOR_KEY=KEY)
        data = self.record()
        r = self.client.post("/api/readings/", data, format="json")
        self.assertEqual(r.status_code, 202)
        self.assertEqual(self.client.post("/api/readings/", data, format="json").status_code, 202)
        self.assertEqual(Reading.objects.count(), 1)
        self.assertEqual(Reading.objects.filter(processed_at__isnull=True).count(), 1)

    def test_atomic_batch_validation(self):
        self.client.credentials(HTTP_X_SENSOR_KEY=KEY)
        data = [self.record(34, 0), self.record(35, 1)]
        data[1]["sensorId"] = "missing-sensor"
        r = self.client.post("/api/readings/batch/", {"readings":data}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Reading.objects.count(), 0)

    def test_rule_instant_lifecycle_and_audit(self):
        rule = Rule.objects.create(name="Heat", sensor=self.sensor, metric_type="temperature",
                                   threshold=32, kind="instant")
        self.client.credentials(HTTP_X_SENSOR_KEY=KEY)
        self.client.post("/api/readings/", self.record(34), format="json")
        result = process_batch()
        self.assertEqual(result["processed"], 1)
        self.assertEqual(Alert.objects.count(), 1)
        self.assertEqual(AlertAudit.objects.count(), 1)
        self.auth()
        pk = Alert.objects.first().pk
        self.assertEqual(self.client.post(f"/api/alerts/{pk}/acknowledge/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/alerts/{pk}/resolve/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/alerts/{pk}/acknowledge/").status_code, 409)
        self.assertEqual(AlertAudit.objects.filter(alert_id=pk).count(), 3)
        self.assertEqual(Alert.objects.get(pk=pk).status, "resolved")

    def test_window_rule_minimum_samples_and_deduplication(self):
        Rule.objects.create(name="Hot 10m average", sensor=self.sensor, metric_type="temperature",
                            threshold=30, kind="window", operator="GT", window_seconds=600, min_samples=2)
        self.client.credentials(HTTP_X_SENSOR_KEY=KEY)
        payload = [self.record(32, 0),self.record(34, 1),self.record(35, 2)]
        self.assertEqual(self.client.post("/api/readings/batch/", {"readings":payload}, format="json").status_code, 202)
        result = process_batch()
        self.assertEqual(result["processed"], 3)
        self.assertEqual(Alert.objects.count(), 1)
        self.assertEqual(Alert.objects.first().kind, "window")
        self.assertEqual(process_batch()["processed"], 0)

    def test_disabled_rule_never_alerts(self):
        Rule.objects.create(name="Inactive", sensor=self.sensor, metric_type="temperature",
                            threshold=10, kind="instant", enabled=False)
        self.client.credentials(HTTP_X_SENSOR_KEY=KEY)
        self.client.post("/api/readings/", self.record(), format="json")
        process_batch()
        self.assertEqual(Alert.objects.count(), 0)

    def test_preserve_sensor_history_on_delete(self):
        self.client.credentials(HTTP_X_SENSOR_KEY=KEY)
        self.client.post("/api/readings/", self.record(), format="json")
        self.auth()
        response = self.client.delete(f"/api/sensors/{self.sensor.pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Sensor.objects.filter(pk=self.sensor.pk).exists())

    def test_event_id_payload_collision_is_rejected(self):
        self.client.credentials(HTTP_X_SENSOR_KEY=KEY)
        first = self.record(34, event_id="edge-1")
        second = self.record(36, event_id="edge-1")
        self.assertEqual(self.client.post("/api/readings/", first, format="json").status_code, 202)
        self.assertEqual(self.client.post("/api/readings/", second, format="json").status_code, 400)
        self.assertEqual(Reading.objects.count(), 1)

    def test_rule_comparator(self):
        for operator, expected in [("GT",True),("GTE",True),("LT",False),
                                   ("LTE",False),("EQ",False)]:
            self.assertEqual(compare(34,operator,30), expected)
