"""Payment is ordinary wrap-up form fields (owner, 2026-11-24): who fills or sees them is set on the
fields, so the two payment permissions, never used, are removed."""
from django.db import migrations


def drop(apps, schema_editor):
    apps.get_model("accounts", "RolePermission").objects.filter(
        permission__in=("payments.record", "payments.verify")).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0012_device_push_token_at")]
    operations = [migrations.RunPython(drop, migrations.RunPython.noop)]
