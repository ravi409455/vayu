"""The server's own records for a load-test run (docs/plan-load-test.md), read through the app,
so it works with Postgres on the server and with a managed database alike. Test servers only.

    manage.py loadtest_records files  < file ids    →  id,verified (unix s),status   (verified.csv)
    manage.py loadtest_records stages < booking ids →  id,stage                        (stages.csv)

IDs come one per line on stdin (a run has thousands)."""
import csv
import sys

from django.core.management.base import BaseCommand, CommandError

from apps.platform import loadtest


class Command(BaseCommand):
    help = "Print a load-test run's file checks or booking stages as CSV (test servers only)."

    def add_arguments(self, parser):
        parser.add_argument("what", choices=["files", "stages"])

    def handle(self, *args, what, **options):
        from apps.bookings.models import Booking
        from apps.media.models import MediaAsset

        try:
            loadtest.check_test_server()
        except loadtest.Refused as e:
            raise CommandError(str(e)) from e
        ids = [line.strip() for line in sys.stdin if line.strip()]
        out = csv.writer(self.stdout)
        for i in range(0, len(ids), 1000):
            chunk = ids[i:i + 1000]
            if what == "files":
                for pk, at, status in MediaAsset.objects.filter(id__in=chunk).values_list(
                        "id", "verified_at", "status"):
                    out.writerow([pk, f"{at.timestamp():.3f}" if at else "", status])
            else:
                for pk, stage in Booking.objects.filter(id__in=chunk).values_list("id", "stage"):
                    out.writerow([pk, stage])
