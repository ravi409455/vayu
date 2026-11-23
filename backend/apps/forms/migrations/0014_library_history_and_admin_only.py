from django.db import migrations


def backfill(apps, schema_editor):
    """One history row for the revision every existing item is at, and library.edit becomes
    Admin-only (any grant to another role is removed)."""
    Item = apps.get_model("forms", "LibraryItem")
    Revision = apps.get_model("forms", "LibraryRevision")
    for item in Item.objects.all():
        Revision.objects.get_or_create(item=item, revision=item.revision, defaults={
            "name": item.name, "definition": item.definition, "changed_keys": [], "by": ""})
    apps.get_model("accounts", "RolePermission").objects.filter(permission="library.edit").delete()


class Migration(migrations.Migration):
    dependencies = [("forms", "0013_library_revisions"),
                    ("accounts", "0005_ops_may_delete_drafts")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
