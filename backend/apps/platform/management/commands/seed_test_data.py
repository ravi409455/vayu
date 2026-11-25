"""Wipes a TEST server and fills it for outside testers: the real setup (setup_platform), three
tester logins (admin, ops, expert) with the password you give, a small team, and bookings for
the last 3 days and today covering every flow, and the short Field tour form (every field
type once) with one job for the tester expert. See apps/platform/setup/testdata.py.

    VAYU_SERVER_KIND=test VAYU_SERVER_NAME=<name> python manage.py seed_test_data \\
        --confirm <name> --password '<tester password>'

Refuses on production (VAYU_SERVER_KIND not test/local), without the server's name typed back,
and when it finds bookings it did not make (they may be real)."""
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.platform.setup import testdata


class Command(BaseCommand):
    help = "Wipe a test server and fill it with test data (never on production)."

    def add_arguments(self, parser):
        parser.add_argument("--confirm", default="", help="this server's name (VAYU_SERVER_NAME)")
        parser.add_argument("--password", default="",
                            help="password of the tester logins (at least 10 characters)")

    def handle(self, *args, confirm="", password="", **options):
        try:
            testdata.check_can_wipe(confirm)
        except testdata.Guard as e:
            raise CommandError(str(e)) from e
        if len(password) < 10:
            raise CommandError("Give the testers' password with --password (10+ characters).")
        testdata.wipe()
        with transaction.atomic():
            users = testdata.make_users(password)
            call_command("setup_platform", verbosity=0)
            testdata.field_tour(users["admin"])
            bl = testdata.Builder(users)
            made = testdata.build_days(bl)
            testdata.ops_review(bl, [r for k, v in made.items() if k.startswith("completed")
                                     for r in v])
            extra = testdata.admin_bits(users["admin"])
        self.stdout.write("Bookings made:")
        for what, refs in made.items():
            self.stdout.write(f"  {what}: {', '.join(refs)}")
        for line in extra:
            self.stdout.write(f"  {line}")
        self.stdout.write(self.style.SUCCESS(
            "Test data ready. Logins: admin, ops, expert (password as given); team: ops2, "
            "expert2 … expert7 (same password)."))
