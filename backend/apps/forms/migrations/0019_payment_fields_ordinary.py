"""Payment is ordinary wrap-up form fields (owner, 2026-11-24): the four payment fields that were
locked system fields become fields the Admin may change or remove. Answers are untouched."""
from django.db import migrations

KEYS = ("taking_payment", "payment_mode", "payment_amount", "payment_screenshot")


def unlock(apps, schema_editor):
    Field = apps.get_model("forms", "Field")
    Field.objects.filter(is_system=True, key__in=KEYS, version__form__type="end").update(
        is_system=False)


class Migration(migrations.Migration):
    dependencies = [("forms", "0018_selfie_front_camera")]
    operations = [migrations.RunPython(unlock, migrations.RunPython.noop)]
