import re

from django.db import migrations

ONE = re.compile(r"\{\{[^{}]*\}\}")


def rows_to_json(rows):
    out = {}
    for r in rows:
        if "rows" in r:
            out[r["key"]] = rows_to_json(r["rows"])
        elif "fixed" in r:
            out[r["key"]] = r["fixed"]
        else:
            v = r.get("value", "")
            if r.get("as_text") and ONE.fullmatch(v.strip()):
                v = v.strip()[:-2].rstrip() + " | text}}"
            out[r["key"]] = v
    return out


def to_json(apps, schema_editor):
    """A custom body was a list of rows; it is now the JSON document those rows describe."""
    Integration = apps.get_model("integrations", "Integration")
    for i in Integration.objects.filter(body_mode="custom"):
        if isinstance(i.body, dict) and isinstance(i.body.get("rows"), list):
            i.body = rows_to_json(i.body["rows"])
            i.save(update_fields=["body"])


class Migration(migrations.Migration):

    dependencies = [("integrations", "0002_request_designer")]

    operations = [migrations.RunPython(to_json, migrations.RunPython.noop)]
