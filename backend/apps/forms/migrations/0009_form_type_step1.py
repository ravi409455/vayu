from django.db import migrations, models


class Migration(migrations.Migration):
    """Form types, step 1: add the new columns beside the old ones (data moves in 0010)."""

    dependencies = [("forms", "0008_slot_existing_ops_pages")]
    operations = [
        migrations.RemoveConstraint(model_name="form", name="one_active_booking_and_ops_form"),
        migrations.RemoveConstraint(model_name="form", name="one_active_form_per_inspection_type"),
        migrations.AddField(model_name="form", name="type", field=models.CharField(
            max_length=16, default="", choices=[("booking", "booking"), ("start", "start"),
                                                 ("end", "end"), ("custom", "custom")]),
            preserve_default=False),
        migrations.AddField(model_name="formversion", name="use_start",
                            field=models.BooleanField(default=True)),
        migrations.AddField(model_name="formversion", name="use_end",
                            field=models.BooleanField(default=True)),
    ]
