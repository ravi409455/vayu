from django.core.management.base import BaseCommand

from apps.forms.models import MasterList, MasterListItem

# City and car make/model start empty here; setup_platform fills them (apps/platform/setup/
# lists.py) and admins edit them. Never overwrites admin edits.
LISTS = {
    "city": ("City", []),
    "car_make_model": ("Car make/model", []),
    "cancel_reason": ("Cancel reason", [
        ("customer_cancelled", "Customer cancelled"), ("on_arrival", "Cancelled on arrival"),
        ("car_not_available", "Car not available"), ("duplicate", "Duplicate booking"),
        ("other", "Other")]),
    "reschedule_reason": ("Reschedule reason", [
        ("customer_request", "Customer request"), ("expert_unavailable", "Expert unavailable"),
        ("car_not_ready", "Car not ready"), ("other", "Other")]),
    "ops_status": ("Ops status", [
        ("done", "Done"), ("cancelled_on_arrival", "Cancelled on arrival"),
        ("pay_pending", "Payment pending"), ("disputed", "Disputed")]),
}


class Command(BaseCommand):
    help = "Create the launch master lists (idempotent)."

    def handle(self, *args, **options):
        for key, (name, items) in LISTS.items():
            lst, _ = MasterList.objects.get_or_create(key=key, defaults={"name": name})
            for order, (item_key, label) in enumerate(items):
                MasterListItem.objects.get_or_create(list=lst, key=item_key,
                                                     defaults={"label": label, "order": order})
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(LISTS)} master lists."))
