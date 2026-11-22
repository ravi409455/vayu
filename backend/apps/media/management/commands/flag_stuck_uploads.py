from django.core.management.base import BaseCommand

from apps.core import events
from apps.media.services import stuck_uploads


class Command(BaseCommand):
    help = "Raise one alert.stuck_upload event per upload still unfinished after the limit."

    def handle(self, *args, **options):
        n = 0
        for a in stuck_uploads().filter(stuck_alerted=False):
            events.emit("alert.stuck_upload", booking=str(a.booking_id), media=str(a.id),
                        field_key=a.field_key)
            a.stuck_alerted = True
            a.save(update_fields=["stuck_alerted"])
            n += 1
        self.stdout.write(f"{n} stuck upload(s) flagged")
