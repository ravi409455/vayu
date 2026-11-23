import re

from django.db import migrations, models


def backfill(apps, schema_editor):
    """Every existing section gets a key made from its title, unique in its version. Versions of
    one form with the same section title get the same key, so 'Driver side' stays 'driver_side'
    across them."""
    Section = apps.get_model("forms", "Section")
    taken: dict[int, set[str]] = {}
    for s in Section.objects.order_by("version_id", "order", "id"):
        base = re.sub(r"[^a-z0-9]+", "_", s.title.lower()).strip("_")[:55] or "section"
        base = base if base[0].isalpha() else f"s_{base}"[:55]
        used = taken.setdefault(s.version_id, set())
        key, n = base, 2
        while key in used:
            key, n = f"{base}_{n}", n + 1
        used.add(key)
        Section.objects.filter(pk=s.pk).update(key=key)   # plain update: published versions too


class Migration(migrations.Migration):
    dependencies = [("forms", "0014_library_history_and_admin_only")]

    operations = [
        migrations.AddField(model_name="section", name="key",
                            field=models.CharField(blank=True, max_length=63)),
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="section",
            constraint=models.UniqueConstraint(fields=("version", "key"),
                                               name="section_key_per_version")),
    ]
