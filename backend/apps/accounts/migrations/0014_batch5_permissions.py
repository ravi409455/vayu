"""Plan batch 5 permission changes, in the plan §5 order.

1. Remove grants of permissions that are now Admin-only (F-054, R-34). Not reversed: they can no
   longer be granted, so putting them back would grant nothing.
2. users.sign_out_devices off by default for Ops (F-223). Reversed by granting it again.
3. Drop the unused submissions.delete (R-23). Not reversed: the permission no longer exists.
"""
from django.db import migrations

ADMIN_ONLY = ("api_keys.manage", "integrations.manage", "forms.edit", "forms.publish",
              "forms.promote", "pdf_templates.edit", "master_lists.manage")


def admin_only(apps, schema_editor):
    apps.get_model("accounts", "RolePermission").objects.filter(
        permission__in=ADMIN_ONLY).delete()


def sign_out_off(apps, schema_editor):
    apps.get_model("accounts", "RolePermission").objects.filter(
        role="ops", permission="users.sign_out_devices").delete()


def sign_out_on(apps, schema_editor):
    apps.get_model("accounts", "RolePermission").objects.get_or_create(
        role="ops", permission="users.sign_out_devices", defaults={"scope": "all"})


def drop_submissions_delete(apps, schema_editor):
    apps.get_model("accounts", "RolePermission").objects.filter(
        permission="submissions.delete").delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0013_drop_payment_permissions"),
                    ("reports", "0007_report_first_pdf_and_failures")]   # plan §5 order
    operations = [migrations.RunPython(admin_only, migrations.RunPython.noop),
                  migrations.RunPython(sign_out_off, sign_out_on),
                  migrations.RunPython(drop_submissions_delete, migrations.RunPython.noop)]
