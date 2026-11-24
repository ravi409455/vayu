from django.db import migrations


def grant(apps, schema_editor):
    RolePermission = apps.get_model("accounts", "RolePermission")
    for key in ("settings.view", "bookings.review_timing"):
        RolePermission.objects.get_or_create(role="ops", permission=key, defaults={"scope": "all"})


class Migration(migrations.Migration):
    dependencies = [("accounts", "0008_device_heartbeat")]
    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
