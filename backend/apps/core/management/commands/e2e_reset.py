"""Browser tests only: empty the e2e database and bucket, then create the three users and the
master lists. Refuses to run unless the settings module is the e2e one."""
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role, User
from apps.forms.models import MasterList, MasterListItem

PASSWORD = "Passw0rd-e2e"
USERS = [("admin", Role.ADMIN, "Asha Admin"), ("ops", Role.OPS, "Priya Ops"),
         ("expert", Role.EXPERT, "Ravi Expert"), ("expert2", Role.EXPERT, "Meera Expert")]
ITEMS = {"city": [("delhi", "Delhi"), ("pune", "Pune")],
         "car_make_model": [("maruti_victoris", "Maruti Victoris"), ("tata_nexon", "Tata Nexon")]}


class Command(BaseCommand):
    def handle(self, *args, **options):
        from apps.core.setup.testdata import WIPEABLE, remember_kind, stored_kind

        if settings.SETTINGS_MODULE != "vayu.settings.e2e":
            raise CommandError("e2e_reset only runs with DJANGO_SETTINGS_MODULE=vayu.settings.e2e")
        # the settings module alone can point at any database (F-213)
        if "e2e" not in settings.DATABASES["default"]["NAME"] or stored_kind() not in (
                None, *WIPEABLE):
            raise CommandError("e2e_reset only wipes an e2e database. Nothing was changed.")
        import boto3

        from apps.media import storage

        call_command("flush", interactive=False, verbosity=0)
        remember_kind()
        client = storage.client()
        try:
            client.create_bucket(Bucket=settings.S3_BUCKET)
        except client.exceptions.ClientError:
            pass
        client.put_bucket_cors(Bucket=settings.S3_BUCKET, CORSConfiguration={"CORSRules": [{
            "AllowedOrigins": ["*"], "AllowedMethods": ["GET", "PUT", "POST", "HEAD"],
            "AllowedHeaders": ["*"], "ExposeHeaders": ["ETag"]}]})
        for page in boto3.client("s3", endpoint_url=settings.S3_ENDPOINT_URL,
                                 aws_access_key_id="test", aws_secret_access_key="test",
                                 region_name="us-east-1").get_paginator("list_objects_v2").paginate(
                                     Bucket=settings.S3_BUCKET):
            for o in page.get("Contents", []):
                client.delete_object(Bucket=settings.S3_BUCKET, Key=o["Key"])
        from apps.accounts.catalog import DEFAULTS
        from apps.accounts.models import RolePermission

        for role, grants in DEFAULTS.items():       # flush removed what the migration seeded
            for key, scope in grants.items():
                RolePermission.objects.get_or_create(role=role, permission=key,
                                                     defaults={"scope": scope})
        from apps.forms.services import ensure_system_forms

        ensure_system_forms()
        call_command("seed_master_lists", verbosity=0)
        for key, items in ITEMS.items():
            lst = MasterList.objects.get(key=key)
            for n, (k, label) in enumerate(items):
                MasterListItem.objects.get_or_create(list=lst, key=k, defaults={"label": label,
                                                                                "order": n})
        for username, role, name in USERS:
            User.objects.create_user(username=username, password=PASSWORD, role=role, name=name,
                                     must_change_password=False)
        self.stdout.write("e2e reset done")
