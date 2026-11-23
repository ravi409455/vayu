"""Form types: PDF templates refer to `start.<key>` / `end.<key>` instead of `ops.<key>`."""
from django.db import migrations

START_KEYS = {"checkin_gps", "checkin_time", "selfie"}


def rewrite(node, owner):
    if isinstance(node, dict):
        return {k: rewrite(v, owner) for k, v in node.items()}
    if isinstance(node, list):
        return [rewrite(x, owner) for x in node]
    if isinstance(node, str) and node.startswith("ops."):
        return f"{owner.get(node[4:].split('.')[0], 'start')}.{node[4:]}"
    return node


def rename(apps, schema_editor):
    Field = apps.get_model("forms", "Field")
    Version = apps.get_model("reports", "PdfTemplateVersion")
    owner = {k: "start" for k in START_KEYS}
    for side in ("start", "end"):
        for key in Field.objects.filter(version__form__type=side).values_list("key", flat=True):
            owner[key] = side
    for v in Version.objects.all():
        v.definition = rewrite(v.definition, owner)
        v.save()


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0002_render_started"),
        ("forms", "0012_alter_field_type_alter_fieldkey_type_alter_form_type"),
    ]
    operations = [migrations.RunPython(rename, migrations.RunPython.noop)]
