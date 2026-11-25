"""F-045: rating categories name their sections by the permanent section key, not the title (a
renamed section no longer drops out of its rating). Reversible: keys go back to titles."""
from django.db import migrations


def _swap(apps, to_key: bool) -> None:
    FormVersion = apps.get_model("forms", "FormVersion")
    Section = apps.get_model("forms", "Section")
    for v in FormVersion.objects.exclude(rating_config={}).iterator():
        cats = (v.rating_config or {}).get("categories")
        if not isinstance(cats, list):
            continue
        rows = list(Section.objects.filter(version=v).values_list("key", "title"))
        lookup = {t: k for k, t in rows} if to_key else {k: t for k, t in rows}
        new = [{**c, "sections": [lookup.get(s, s) for s in c.get("sections") or []]}
               if isinstance(c, dict) else c for c in cats]
        if new != cats:
            v.rating_config = {**v.rating_config, "categories": new}
            v.save(update_fields=["rating_config"])


def to_keys(apps, schema_editor):
    _swap(apps, True)


def to_titles(apps, schema_editor):
    _swap(apps, False)


class Migration(migrations.Migration):
    dependencies = [("forms", "0020_explicit_max_count")]
    operations = [migrations.RunPython(to_keys, to_titles)]
