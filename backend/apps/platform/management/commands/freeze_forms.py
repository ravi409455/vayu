"""One time (local only): converts the Clappia read-out (apps/platform/setup/data) into our six form
files and the library file (apps/platform/setup/frozen/*.json), with the agreed clean-ups, photo
rules and shared sections. After that the files are ours: edit them (or the forms in the
builder), never re-run this over hand edits without reviewing the diff."""
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.platform.setup import common, convert, forms


class Command(BaseCommand):
    help = "Write the form files from the Clappia read-out (one time, local only)."

    def handle(self, *args, **options):
        if settings.SERVER_KIND != "local":
            raise CommandError("freeze_forms writes source files: run it locally only.")
        forms.FROZEN.mkdir(exist_ok=True)
        out: dict[str, tuple[dict, dict]] = {
            "booking": (convert.booking(), {}), "start": (convert.start(), {}),
            "end": (convert.end(), {})}
        made = {key: convert.inspection(key) for key, *_ in forms.INSPECTIONS}
        # what the three forms share goes to the library; the forms are rebuilt on it
        library, shared, notes = common.share({k: spec for k, (spec, _) in made.items()},
                                               convert.delay())
        for key, (spec, extra) in made.items():
            for cat in extra["rating_config"]["categories"]:
                cat["sections"] = common.with_children(cat["sections"], shared[key])
            out[key] = ({**shared[key], "problems": spec.get("problems", [])}, extra)
        (forms.FROZEN / "library.json").write_text(json.dumps(
            {"made_from": "what the PDI, Used Car and EV forms share (setup/common.py)",
             "notes": notes, **library}, indent=1, ensure_ascii=False) + "\n")
        self.stdout.write(f"  library: {len(library['sections'])} sections, "
                          f"{len(library['fields'])} fields")
        for name, (spec, extra) in out.items():
            notes = spec.pop("problems", [])
            spec.pop("app", None)
            data = {"made_from": f"Clappia read-out {name} (docs/clappia)", "notes": notes,
                    "spec": spec, "extra": extra}
            (forms.FROZEN / f"{name}.json").write_text(
                json.dumps(data, indent=1, ensure_ascii=False) + "\n")
            n = sum(len(s["fields"]) for p in spec["pages"] for s in p["sections"])
            self.stdout.write(f"  {name}: {n} fields")
