"""Plan batch 2 (H-08): before one open draft per expert per booking becomes a rule, close the
extra drafts that exist today. The newest draft of each expert on a booking stays open; older ones
are marked released (what force-release now does)."""
from django.db import migrations


def close_extra_drafts(apps, schema_editor):
    Inspection = apps.get_model("bookings", "Inspection")
    seen = set()
    for i in Inspection.objects.filter(status="draft").order_by("-created_at"):
        pair = (i.booking_id, i.expert_id)
        if pair in seen:
            i.status = "released"
            i.save(update_fields=["status"])
        seen.add(pair)


def reopen(apps, schema_editor):
    # back to before the rule: every released draft was an open draft (the rule is undone first)
    apps.get_model("bookings", "Inspection").objects.filter(status="released").update(
        status="draft")


class Migration(migrations.Migration):
    dependencies = [("bookings", "0008_timing")]
    operations = [migrations.RunPython(close_extra_drafts, reopen)]
