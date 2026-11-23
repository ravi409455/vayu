"""Form types, step 2: the data. kind -> type; the one check-in-and-wrap-up ("ops") form is split
into a start form (check-in) and an end form (wrap-up); every `ops.<key>` a rule can hold becomes
`start.<key>` or `end.<key>`; the booking form's inspection type is picked from the custom forms."""
from django.db import migrations

START_KEYS = {"checkin_gps", "checkin_time", "selfie"}


def rewrite(node, owner):
    """A copy of a rule (or any JSON holding rules) with every ops.<key> variable renamed to
    start.<key> / end.<key>, by which form owns the key."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "var":
                out[k] = _var(v, owner)
            else:
                out[k] = rewrite(v, owner)
        return out
    if isinstance(node, list):
        return [rewrite(x, owner) for x in node]
    return node


def _var(v, owner):
    name, rest = (v[0], v[1:]) if isinstance(v, list) and v else (v, None)
    if isinstance(name, str) and name.startswith("ops."):
        key = name[4:].split(".")[0]
        name = f"{owner.get(key, 'start')}.{name[4:]}"
    return [name, *rest] if rest is not None else name


def rename_in_text(text, owner):
    """For PDF template references such as "ops.payment_mode"."""
    if isinstance(text, str) and text.startswith("ops."):
        return f"{owner.get(text[4:].split('.')[0], 'start')}.{text[4:]}"
    return text


def rewrite_strings(node, owner):
    if isinstance(node, dict):
        return {k: rewrite_strings(v, owner) for k, v in node.items()}
    if isinstance(node, list):
        return [rewrite_strings(x, owner) for x in node]
    return rename_in_text(node, owner)


def free_key(Form, wanted):
    key, n = wanted, 2
    while Form.objects.filter(key=key).exists():
        key, n = f"{wanted}{n}", n + 1
    return key


def split_ops_form(apps, schema_editor):
    Form = apps.get_model("forms", "Form")
    FormVersion = apps.get_model("forms", "FormVersion")
    Page = apps.get_model("forms", "Page")
    Section = apps.get_model("forms", "Section")
    Field = apps.get_model("forms", "Field")
    Check = apps.get_model("forms", "VersionCheck")
    Library = apps.get_model("forms", "LibraryItem")

    Form.objects.filter(kind="booking").update(type="booking")
    Form.objects.filter(kind="inspection").update(type="custom")
    owner: dict[str, str] = {}
    ops = Form.objects.filter(kind="ops").first()
    if ops is not None:
        ops.type, ops.name = "start", "Start (check-in)"
        ops.save()
        end = Form.objects.create(key=free_key(Form, "end"), kind="ops", type="end",
                                  name="End (wrap-up)", is_active=True, inspection_type="")
        for v in FormVersion.objects.filter(form=ops).order_by("number"):
            ev = FormVersion.objects.create(
                form=end, number=v.number, status=v.status, published_at=v.published_at,
                created_at=v.created_at, use_start=True, use_end=True)
            for p in Page.objects.filter(version=v):
                side = "end" if p.slot == "after" else "start"
                for key in Field.objects.filter(section__page=p).values_list("key", flat=True):
                    owner[key] = side
                if side == "end":
                    p.version = ev
                    p.save()
                    Section.objects.filter(page=p).update(version=ev)
                    Field.objects.filter(section__page=p).update(version=ev)
    for k in START_KEYS:
        owner.setdefault(k, "start")
    # the booking form picks the inspection type from the custom forms now
    Field.objects.filter(version__form__type="booking", key="inspection_type").update(
        type="form_choice", config={})

    for f in Field.objects.all():
        f.show_if = rewrite(f.show_if, owner)
        f.required_if = rewrite(f.required_if, owner)
        f.save()
    for f in Field.objects.filter(type="derived"):
        rule = (f.config or {}).get("rule")
        if rule is not None:
            f.config = {**f.config, "rule": rewrite(rule, owner)}
            f.save()
    for model in (Section, Page):
        for o in model.objects.all():
            o.show_if = rewrite(o.show_if, owner)
            o.save()
    for c in Check.objects.all():
        c.rule = rewrite(c.rule, owner)
        c.save()
    for item in Library.objects.all():
        item.definition = rewrite(item.definition, owner)
        item.save()
    MasterList = apps.get_model("forms", "MasterList")
    MasterList.objects.filter(key="inspection_type").delete()      # the forms themselves say it


class Migration(migrations.Migration):
    dependencies = [("forms", "0009_form_type_step1")]
    operations = [migrations.RunPython(split_ops_form, migrations.RunPython.noop)]
