"""Form types: an inspection's `ops` answers become `start` and `end` answers (by which of the
two forms owns the key), and each inspection pins the start / end versions it went through."""
from django.db import migrations

START_KEYS = {"checkin_gps", "checkin_time", "selfie"}


def split_answers(apps, schema_editor):
    Inspection = apps.get_model("bookings", "Inspection")
    Field = apps.get_model("forms", "Field")
    FormVersion = apps.get_model("forms", "FormVersion")
    owner = {k: "start" for k in START_KEYS}
    for side in ("start", "end"):
        for key in Field.objects.filter(version__form__type=side).values_list("key", flat=True):
            owner[key] = side
    latest = {}
    for side in ("start", "end"):
        latest[side] = (FormVersion.objects.filter(form__type=side, status="published")
                        .order_by("-number").first())
    for insp in Inspection.objects.all():
        ops = insp.answers.get("ops")
        answers = {k: v for k, v in insp.answers.items() if k != "ops"}
        answers.setdefault("inspection", {})
        answers["start"], answers["end"] = {}, {}
        for key, value in (ops or {}).items():
            answers[owner.get(key, "start")][key] = value
        insp.answers = answers
        # what the expert saw was the live start / end form at the time: the best we know now
        insp.start_version = latest["start"] if ops is not None else None
        insp.end_version = latest["end"] if ops is not None else None
        insp.save()


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0005_inspection_end_version_inspection_start_version"),
        ("forms", "0012_alter_field_type_alter_fieldkey_type_alter_form_type"),
    ]
    operations = [migrations.RunPython(split_answers, migrations.RunPython.noop)]
