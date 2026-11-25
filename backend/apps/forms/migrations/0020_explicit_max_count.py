"""Plan batch 4 (F-010): a photo / video / file field without its own maximum now takes 1 file
(it took 10 / 3 / 5). Fields and library items that relied on the old default get it written in,
so nothing in use changes. Not reversed: afterwards nobody can tell a maximum written here from one
an Admin set to the same number, and keeping them changes nothing."""
from django.db import migrations

OLD = {"photo": 10, "video": 3, "file": 5}


def write_old_default(apps, schema_editor):
    Field = apps.get_model("forms", "Field")
    for f in Field.objects.filter(type__in=OLD):
        if "max_count" not in (f.config or {}):
            f.config = {**(f.config or {}), "max_count": OLD[f.type]}
            f.save(update_fields=["config"])
    LibraryItem = apps.get_model("forms", "LibraryItem")
    for item in LibraryItem.objects.all():
        d = item.definition or {}
        fields = d.get("fields") if item.kind == "section" else [d]
        changed = False
        for spec in fields or []:
            if spec.get("type") in OLD and "max_count" not in (spec.get("config") or {}):
                spec["config"] = {**(spec.get("config") or {}), "max_count": OLD[spec["type"]]}
                changed = True
        if changed:
            item.definition = d
            item.save(update_fields=["definition"])


class Migration(migrations.Migration):
    dependencies = [("forms", "0019_payment_fields_ordinary")]
    operations = [migrations.RunPython(write_old_default, migrations.RunPython.noop)]
