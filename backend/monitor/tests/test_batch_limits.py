from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from monitor.models import Sensor, Reading

@override_settings(SENSOR_API_KEY="x" * 40)
class BatchLimitTests(TestCase):
    def setUp(self):
        Sensor.objects.create(sensor_id="sensor-1", name="One", location="Lab")
        self.client = APIClient()
        self.client.credentials(HTTP_X_SENSOR_KEY="x" * 40)

    def test_oversized_batch_rejected_without_writes(self):
        stamp = (timezone.now() - timedelta(minutes=1)).isoformat()
        sample = {"sensorId":"sensor-1", "type":"temperature", "value":33,
                  "timestamp":stamp}
        response = self.client.post("/api/readings/batch/", {"readings":[sample] * 10001}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Reading.objects.count(), 0)
