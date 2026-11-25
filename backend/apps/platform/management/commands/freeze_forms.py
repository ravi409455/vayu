"""One time (local only): converts the Clappia read-out (apps/platform/setup/data) into our six form
files (apps/platform/setup/frozen/*.json), with the agreed clean-ups and photo rules. After that the
files are ours: edit them (or the forms in the builder), never re-run this over hand edits
without reviewing the diff."""
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.platform.setup import convert, forms


class Command(BaseCommand):
    help = "Write the form files from the Clappia read-out (one time, local only)."

    def handle(self, *args, **options):
        if settings.SERVER_KIND != "local":
            raise CommandError("freeze_forms writes source files: run it locally only.")
        forms.FROZEN.mkdir(exist_ok=True)
        out: dict[str, tuple[dict, dict]] = {
            "booking": (convert.booking(), {}), "start": (convert.start(), {}),
            "end": (convert.end(), {})}
        for key, *_ in forms.INSPECTIONS:
            out[key] = convert.inspection(key)
        for name, (spec, extra) in out.items():
            notes = spec.pop("problems", [])
            spec.pop("app", None)
            data = {"made_from": f"Clappia read-out {name} (docs/clappia)", "notes": notes,
                    "spec": spec, "extra": extra}
            (forms.FROZEN / f"{name}.json").write_text(
                json.dumps(data, indent=1, ensure_ascii=False) + "\n")
            n = sum(len(s["fields"]) for p in spec["pages"] for s in p["sections"])
            self.stdout.write(f"  {name}: {n} fields")
