from django.db import migrations


def drop(apps, schema_editor):
    # reports are made again by themselves on every change: nobody regenerates by hand
    apps.get_model("accounts", "RolePermission").objects.filter(
        permission="reports.regenerate").delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0009_timing_permissions")]
    operations = [migrations.RunPython(drop, migrations.RunPython.noop)]
