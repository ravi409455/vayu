from django.db import migrations
from django.db.models import Value
from django.db.models.functions import Replace


def rename(apps, schema_editor):
    # experts now call it a lead (docs/plan-leads-bookings-words.md): the bell must not mix words
    apps.get_model("notify", "Notification").objects.filter(
        kind="assigned", title__startswith="New job: ").update(
        title=Replace("title", Value("New job: "), Value("New lead: ")))


class Migration(migrations.Migration):
    dependencies = [("notify", "0001_initial")]
    operations = [migrations.RunPython(rename, migrations.RunPython.noop)]
