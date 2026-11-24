"""Filter bookings by an answer in their inspection (owner, 2026-11-24): generic, for any choice or
yes/no field the person may see, e.g. "Payment verified?: not filled" or "Pay later". Nothing here
knows about payments; payments are ordinary wrap-up fields."""
from django.db.models import Exists, OuterRef, Q
from rest_framework.exceptions import ValidationError

from apps.forms.access import STAGES, hidden_inspection_forms, levels_for
from apps.forms.models import Field, Form, FormType, FormVersion

from .models import Inspection
from .submissions import latest_published

TYPES = ("single_choice", "multi_choice", "yes_no")
NOT_FILLED = "__none__"
PARTS = {FormType.START: "start", FormType.CUSTOM: "inspection", FormType.END: "end"}
FORM_WORD = {FormType.START: "Check-in", FormType.END: "Wrap-up"}


def fields_for(user, inspection_type: str | None = None) -> list[dict]:
    """The fields this person may filter by: in the forms in use now, not hidden from them once a
    job is done. A key used by several inspection forms is one row (its choices joined).
    [inspection_type]: only that type's inspection questions (plus the check-in and wrap-up,
    which every type shares), as Ops pick a type first."""
    return [{k: v for k, v in r.items() if k != "forms"} for r in _rows(user, inspection_type)]


def _rows(user, inspection_type: str | None = None) -> list[dict]:
    """fields_for, plus per row the forms where the field is visible to this person ("forms"):
    the filter looks only at inspections made with those, never at a form that hides it."""
    hidden_forms = set(hidden_inspection_forms(user))
    rows: dict[str, dict] = {}
    for form in Form.objects.filter(is_active=True, type__in=list(PARTS)).order_by("type", "name"):
        if form.id in hidden_forms:
            continue
        other_type = form.type == FormType.CUSTOM and form.inspection_type != inspection_type
        if inspection_type and other_type:
            continue
        version = latest_published(form)
        if version is None:
            continue
        levels = {} if user.role == "admin" else levels_for(version, user.role, "completed")
        part = PARTS[form.type]
        for f in Field.objects.filter(version=version, type__in=TYPES).order_by(
                "section__page__order", "section__order", "order", "id"):
            if user.role != "admin" and levels.get(f.key, "hidden") == "hidden":
                continue
            choices = [o for o in f.config.get("options") or []
                       if isinstance(o, dict) and "key" in o]
            options = ([{"value": "true", "label": "Yes"}, {"value": "false", "label": "No"}]
                       if f.type == "yes_no" else
                       [{"value": o["key"], "label": o.get("label", o["key"])} for o in choices])
            row = rows.setdefault(f"{part}.{f.key}", {
                "field": f"{part}.{f.key}", "label": f.label, "type": f.type, "options": [],
                "form": FORM_WORD.get(form.type, form.name), "forms": []})
            row["forms"].append(form.id)
            known = {o["value"] for o in row["options"]}
            row["options"] += [o for o in options if o["value"] not in known]
            if form.name not in row["form"] and form.type == FormType.CUSTOM:
                row["form"] += f", {form.name}"
    return list(rows.values())


def apply(qs, user, field: str, value: str, own: bool = False):
    """Bookings whose submitted inspection has this answer (or, NOT_FILLED, has none). Only an
    inspection where this person could see the field counts: its own form version, at the
    booking's stage now; [own]: only their own inspections (submissions.view "own")."""
    row = next((r for r in _rows(user) if r["field"] == field), None)
    if row is None:
        raise ValidationError({"answer": "Choose a field from the list."})
    part, key = field.split(".", 1)
    path = f"answers__{part}__{key}"
    pinned = {"inspection": "form_version", "start": "start_version", "end": "end_version"}[part]
    done = Inspection.objects.filter(booking=OuterRef("pk"), status="submitted",
                                     **{f"{pinned}__form_id__in": row["forms"]})
    if own:
        done = done.filter(expert=user)
    done = done.filter(_visible(user, pinned, row["forms"], key))
    if value == NOT_FILLED:
        filled = done.filter(**{f"answers__{part}__has_key": key}).exclude(**{path: None}) \
            .exclude(**{path: []})
        return qs.filter(Exists(done)).exclude(Exists(filled))
    if value not in {o["value"] for o in row["options"]}:
        raise ValidationError({"value": "Choose one of the field's answers."})
    if row["type"] == "yes_no":
        match = done.filter(**{path: value == "true"})
    elif row["type"] == "multi_choice":
        match = done.filter(**{f"{path}__contains": [value]})
    else:
        match = done.filter(**{path: value})
    return qs.filter(Exists(match))


def _visible(user, pinned: str, forms: list[int], key: str) -> Q:
    """Inspections whose own form version shows `key` to this person at the booking's stage now.
    Fails closed: a version or stage where it is hidden (or absent) never matches."""
    if user.role == "admin":
        return Q()
    allowed = Q(pk__in=[])
    for version in FormVersion.objects.filter(form_id__in=forms, status="published"):
        stages = [st for st in STAGES
                  if levels_for(version, user.role, st).get(key, "hidden") != "hidden"]
        if stages:
            allowed |= Q(**{f"{pinned}_id": version.id}, booking__stage__in=stages)
    return allowed
