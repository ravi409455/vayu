from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    """Form types, step 3: drop the old columns and add the new rules."""

    dependencies = [("forms", "0010_form_type_data")]
    operations = [
        migrations.RemoveField(model_name="form", name="kind"),
        migrations.RemoveField(model_name="page", name="slot"),
        migrations.AddConstraint(model_name="form", constraint=models.UniqueConstraint(
            fields=("type",), condition=Q(type__in=["booking", "start", "end"]),
            name="one_system_form_per_type")),
        migrations.AddConstraint(model_name="form", constraint=models.UniqueConstraint(
            fields=("inspection_type",),
            condition=Q(is_active=True, type="custom") & ~Q(inspection_type=""),
            name="one_active_form_per_inspection_type")),
    ]
