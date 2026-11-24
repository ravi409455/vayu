from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies: list = []
    operations = [
        migrations.CreateModel(
            name="Setting",
            fields=[
                ("key", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("value", models.JSONField(default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
