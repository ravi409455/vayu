from django.db import migrations, models


def first_event(apps, schema_editor):
    """One integration = one event: keep the first one of the old list."""
    Integration = apps.get_model("integrations", "Integration")
    for i in Integration.objects.all():
        i.event = (i.events or ["booking.updated"])[0]
        i.save(update_fields=["event"])


class Migration(migrations.Migration):

    dependencies = [("integrations", "0001_initial")]

    operations = [
        migrations.AddField("integration", "event", models.CharField(max_length=40, default="")),
        migrations.AddField("integration", "method",
                            models.CharField(max_length=6, default="POST")),
        migrations.AddField("integration", "query", models.JSONField(default=list)),
        migrations.AddField("integration", "headers", models.JSONField(default=list)),
        migrations.AddField("integration", "body_mode",
                            models.CharField(max_length=10, default="standard")),
        migrations.AddField("integration", "body", models.JSONField(default=dict)),
        migrations.RunPython(first_event, migrations.RunPython.noop),
        migrations.RemoveField("integration", "events"),
        migrations.RemoveField("integration", "template"),
        migrations.RemoveField("integration", "secret"),
        migrations.AlterField("integration", "url", models.CharField(max_length=500)),
    ]
