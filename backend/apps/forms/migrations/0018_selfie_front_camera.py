"""The check-in selfie opens the front camera (owner, 2026-11-24). Published versions are never
edited in the builder; this one display-only setting is set on every existing selfie field."""
from django.db import migrations


def front(apps, schema_editor):
    Field = apps.get_model("forms", "Field")
    for f in Field.objects.filter(key="selfie", type="photo", is_system=True):
        if "camera" not in (f.config or {}):
            Field.objects.filter(pk=f.pk).update(config={**(f.config or {}), "camera": "front"})


class Migration(migrations.Migration):
    dependencies = [("forms", "0017_key_checks")]
    operations = [migrations.RunPython(front, migrations.RunPython.noop)]
