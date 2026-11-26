"""Delete the load test's files from the file bucket (docs/plan-load-test.md). Test servers only.

    python manage.py loadtest_cleanup

Only files of bookings whose ID starts with LT- (made by loadtest_prepare and the load script).
perf/cloud.sh runs it before destroying a throwaway server (its bucket is staging's)."""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.platform import loadtest


class Command(BaseCommand):
    help = "Delete the load test's files from the bucket (test servers only)."

    def handle(self, *args, **options):
        try:
            out = loadtest.cleanup()
        except loadtest.Refused as e:
            raise CommandError(str(e)) from e
        self.stdout.write(json.dumps(out))
        if out["left_in_their_folders"]:
            raise CommandError("Some files are still in the bucket: run it again.")
