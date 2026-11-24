"""Reading bundles exported before form types (schema 1): the old "inspection" kind becomes
"custom", and every `ops.<key>` a rule or PDF row can hold becomes `start.<key>` or `end.<key>`."""
from typing import Any

from .system_fields import STARTER_FIELDS, SYSTEM_FIELDS

START_KEYS = {s["key"] for s in SYSTEM_FIELDS["start"]}
END_KEYS = {s["key"] for s in SYSTEM_FIELDS["end"] + STARTER_FIELDS["end"]}


class OldBundleError(ValueError):
    pass


def _side(key: str) -> str:
    if key in START_KEYS:
        return "start"
    if key in END_KEYS:
        return "end"
    raise OldBundleError(f"The bundle refers to ops.{key}, which no longer exists. Re-create "
                         "that rule against the start or end form and export the bundle again.")


def _var(v: Any) -> Any:
    name, rest = (v[0], v[1:]) if isinstance(v, list) and v else (v, None)
    if isinstance(name, str) and name.startswith("ops."):
        name = f"{_side(name[4:].split('.')[0])}.{name[4:]}"
    return [name, *rest] if rest is not None else name


def rewrite_rules(node: Any) -> Any:
    """A copy of any JSON holding rules, with ops.<key> variables renamed."""
    if isinstance(node, dict):
        return {k: (_var(v) if k == "var" else rewrite_rules(v)) for k, v in node.items()}
    if isinstance(node, list):
        return [rewrite_rules(x) for x in node]
    return node


def upgrade_v1(b: dict) -> dict:
    """The schema-2 form of a schema-1 bundle. Raises OldBundleError for what cannot be carried."""
    form = dict(b["form"])
    kind = form.pop("kind", None)
    if kind == "ops":
        raise OldBundleError("This is an old check-in/wrap-up bundle. That form is now split into "
                             "a start form and an end form: export them again from the source.")
    form["type"] = {"inspection": "custom", "booking": "booking"}.get(kind, kind)
    out = {**b, "schema": 2, "form": form}
    version = dict(b["version"])
    version["pages"] = [{k: v for k, v in p.items() if k != "slot"} for p in version["pages"]]
    out["version"] = rewrite_rules(version)
    out["library"] = [{**i, "definition": rewrite_rules(i["definition"])} for i in b["library"]]
    # a schema-1 bundle's report layout was made with the old designer, which the new one does
    # not read: the form comes across and its report is built again (docs/plan-reports.md)
    out["pdf_template"] = None
    if form["type"] == "booking":              # the type is picked from the custom forms now
        for p in out["version"]["pages"]:
            for s in p["sections"]:
                for f in s["fields"]:
                    if f["key"] == "inspection_type" and f["type"] == "master_list":
                        f["type"], f["config"] = "form_choice", {}
        out["master_lists"] = [m for m in b["master_lists"] if m["key"] != "inspection_type"]
    return out
