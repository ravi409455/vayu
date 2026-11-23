from django.db import migrations


def remove_grants(apps, schema_editor):
    """users.manage (create, edit, deactivate users, reset passwords) can no longer be given to
    another role: any existing grant is removed."""
    apps.get_model("accounts", "RolePermission").objects.filter(permission="users.manage").delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_profile_fields")]
    operations = [migrations.RunPython(remove_grants, migrations.RunPython.noop)]
