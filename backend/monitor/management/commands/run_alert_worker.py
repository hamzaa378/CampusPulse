"""Start separately from Django server: python manage.py run_alert_worker"""
import time
from django.core.management.base import BaseCommand
from monitor.processor import process_batch

class Command(BaseCommand):
    help = "Process pending sensor readings and create alerts (one worker recommended for v1)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--poll-seconds", type=float, default=0.5)

    def handle(self, *args, **options):
        self.stdout.write("CampusPulse worker running. Ctrl+C to stop.")
        try:
            while True:
                result = process_batch(limit=options["batch_size"])
                if result["processed"]:
                    self.stdout.write(f"Processed={result['processed']} candidate_alerts={result['alert_candidates']} pending={result['pending']}")
                if options["once"]:
                    break
                if not result["processed"]:
                    time.sleep(max(0.1, options["poll_seconds"]))
        except KeyboardInterrupt:
            self.stdout.write("Worker stopped.")
