from django.db import migrations


def slot(apps, schema_editor):
    Page = apps.get_model("forms", "Page")
    for p in Page.objects.filter(version__form__kind="ops"):
        p.slot = "before" if "check" in p.title.lower() else "after"
        p.save(update_fields=["slot"])


class Migration(migrations.Migration):
    dependencies = [("forms", "0007_form_visibility_slots_assets")]
    operations = [migrations.RunPython(slot, migrations.RunPython.noop)]
