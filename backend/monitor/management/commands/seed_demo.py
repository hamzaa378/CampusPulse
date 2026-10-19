"""Cross-database demo fixtures; equivalent to mysql/03_seed_demo.sql."""
from django.core.management.base import BaseCommand
from monitor.models import Rule, Sensor

class Command(BaseCommand):
    help = "Insert three example sensors and two library alert rules without overwriting existing records."

    def handle(self, *args, **kwargs):
        for sensor_id,name,location in [
            ("library-floor-2", "Library Temperature", "Main Library Floor 2"),
            ("cafeteria-hall", "Cafeteria Environment", "Main Cafeteria"),
            ("lab-block-a", "Laboratory Air Quality", "Academic Block A"),
        ]:
            Sensor.objects.get_or_create(sensor_id=sensor_id, defaults={"name":name,"location":location})
        library = Sensor.objects.get(sensor_id="library-floor-2")
        for name,kind,threshold,severity in [
            ("Library hot reading", "instant", "32.0000", "critical"),
            ("Library ten minute mean", "window", "30.0000", "warning"),
        ]:
            Rule.objects.get_or_create(name=name, defaults={
                "sensor":library, "metric_type":"temperature", "kind":kind,
                "operator":"GT", "threshold":threshold, "window_seconds":600,
                "min_samples":2, "severity":severity})
        self.stdout.write(self.style.SUCCESS("Demo sensors and rules ready."))
