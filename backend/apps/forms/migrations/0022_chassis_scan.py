"""The built-in chassis number is a scan field (owner, 2026-11-26): the phone reads it off the
chassis plate. Published versions are never edited in the builder; this one input setting is set
on every existing chassis number field."""
from django.db import migrations


def scan(apps, schema_editor):
    Field = apps.get_model("forms", "Field")
    for f in Field.objects.filter(key="chassis_no", type="short_text", is_system=True):
        if "scan" not in (f.config or {}):
            Field.objects.filter(pk=f.pk).update(config={**(f.config or {}), "scan": True})


class Migration(migrations.Migration):
    dependencies = [("forms", "0021_ratings_by_section_key")]
    operations = [migrations.RunPython(scan, migrations.RunPython.noop)]
