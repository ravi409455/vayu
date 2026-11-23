from django.db import migrations

EMPTY = {"schema": 2, "filename": "{{ sys.booking_id }}.pdf", "pages": []}


def start_fresh(apps, schema_editor):
    """The new report designer starts fresh (docs/plan-reports.md): every template's old
    versions go and it gets an empty draft to build again. PDFs already made are kept."""
    Template = apps.get_model("reports", "PdfTemplate")
    Version = apps.get_model("reports", "PdfTemplateVersion")
    Version.objects.all().delete()
    for t in Template.objects.all():
        Version.objects.create(template=t, number=1, status="draft", definition=EMPTY)


class Migration(migrations.Migration):
    dependencies = [("reports", "0003_ops_references")]

    operations = [migrations.RunPython(start_fresh, migrations.RunPython.noop)]
