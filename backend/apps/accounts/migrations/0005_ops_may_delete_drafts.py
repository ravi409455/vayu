from django.db import migrations


def grant(apps, schema_editor):
    RolePermission = apps.get_model("accounts", "RolePermission")
    RolePermission.objects.get_or_create(role="ops", permission="bookings.delete",
                                         defaults={"scope": "all"})


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_seed_role_permissions")]
    # Ops may delete bookings, but the service only lets them delete untouched drafts
    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
