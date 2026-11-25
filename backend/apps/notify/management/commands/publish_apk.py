import hashlib
import os

from django.core.management.base import BaseCommand, CommandError

from apps.media import storage
from apps.notify.models import AppRelease


class Command(BaseCommand):
    help = "Upload a signed release APK and offer it as the latest app version."

    def add_arguments(self, parser):
        parser.add_argument("apk")
        parser.add_argument("--version-code", type=int, required=True)
        parser.add_argument("--version-name", required=True)
        parser.add_argument("--notes", default="", help="What's new, one change per line")

    def handle(self, apk, version_code, version_name, notes, **_):
        if not os.path.isfile(apk) or not apk.endswith(".apk"):
            raise CommandError(f"Not an APK file: {apk}")
        latest = AppRelease.objects.order_by("-version_code").first()
        if latest and version_code <= latest.version_code:
            raise CommandError(f"Version code must be above {latest.version_code}.")
        digest = hashlib.sha256()
        with open(apk, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
        key = f"app/vayu-{version_code}.apk"
        storage.upload_file(apk, key, "application/vnd.android.package-archive")
        AppRelease.objects.create(version_code=version_code, version_name=version_name,
                                  file_key=key, size=os.path.getsize(apk),
                                  sha256=digest.hexdigest(), notes=notes.replace("\\n", "\n"))
        from apps.accounts import audit

        audit.record(None, "app.publish", "app_release", version_code,         # F-232
                     f"Published Vayu {version_name} ({version_code})")
        self.stdout.write(f"Published Vayu {version_name} ({version_code}).")
