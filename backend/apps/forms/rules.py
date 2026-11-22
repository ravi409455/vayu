"""Vayu's form logic on top of JsonLogic. Semantics: /shared/rule-vectors/SCHEMA.md (normative;
the TypeScript and Kotlin adapters implement the same thing and run the same test cases)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import jsonlogic_rs

from .fieldtypes import AnswerError, ConfigError, clean_answer, is_empty, validate_config

FORMS = ("booking", "ops", "inspection")
# Deliberately small. Everything form logic needs (conditions, "is empty", defect counts) fits in
# these. Arithmetic other than "+" (used to count inside reduce), string and min/max operators are
# banned: the Python and JS libraries disagree on null handling there, and no form needs them.
ALLOWED_OPS = {"var", "==", "!=", "===", "!==", "<", "<=", ">", ">=", "!", "!!", "and", "or", "if",
               "in", "some", "all", "none", "filter", "reduce", "+"}
BANNED_OPS = {"missing", "missing_some", "-", "*", "/", "%", "min", "max", "cat", "substr", "map"}
ITERATING_OPS = {"some", "all", "none", "filter", "reduce"}
CHOICE_TYPES = {"single_choice", "multi_choice"}
SYSTEM_FILLED = {"derived", "rating"}
SPECIAL_VARS = {"_today", "_defects"}


# ------------------------------------------------------------------ evaluation

def evaluate(rule: Any, data: Any) -> Any:
    """Never raises: a rule that cannot apply to the data (wrong types, nulls) yields null, the
    same as the TypeScript adapter. (jsonlogic-rs raises ValueError where json-logic-js returns a
    value; found by differential fuzzing.)"""
    try:
        return jsonlogic_rs.apply(rule, data)
    except Exception:  # noqa: BLE001
        return None
    except BaseException as e:  # a Rust panic must not take the worker down
        if type(e).__name__ == "PanicException":
            return None
        raise


def truthy(rule: Any, data: dict) -> bool:
    return True if rule is None else bool(evaluate({"!!": [rule]}, data))


@dataclass
class Container:
    id: str
    kind: str
    parent: str | None = None
    visible: bool = True
    show_if: Any = None


@dataclass
class FieldSpec:
    key: str
    type: str
    section: str
    visible: bool = True
    show_if: Any = None
    required: bool = False
    required_if: Any = None
    options: list = field(default_factory=list)
    rule: Any = None


@dataclass
class CheckSpec:
    rule: Any
    message: str
    fields: list[str]
    id: Any = None


@dataclass
class FormSpec:
    form: str
    containers: list[Container]
    fields: list[FieldSpec]
    checks: list[CheckSpec] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> FormSpec:
        return cls(form=d["form"],
                   containers=[Container(**c) for c in d.get("containers", [])],
                   fields=[FieldSpec(**f) for f in d.get("fields", [])],
                   checks=[CheckSpec(**c) for c in d.get("checks", [])])


@dataclass
class Result:
    visible: dict[str, bool]
    required: dict[str, bool]
    errors: dict[str, str]
    derived: dict[str, Any]
    defects: list[str]


def _is_defect(f: FieldSpec, value: Any) -> bool:
    if f.type not in CHOICE_TYPES or value is None:
        return False
    defect_keys = {o["key"] for o in f.options if o.get("is_defect")}
    chosen = value if isinstance(value, list) else [value]
    return any(v in defect_keys for v in chosen)


def evaluate_form(spec: FormSpec, answers: dict, today: str,
                  overrides: dict | None = None) -> Result:
    own = spec.form
    base = {f: {k: (None if is_empty(v) else v) for k, v in (answers.get(f) or {}).items()}
            for f in FORMS}
    values = {f.key: base[own].get(f.key) for f in spec.fields}
    containers = {c.id: c for c in spec.containers}

    def build_data(vis: dict[str, bool]) -> dict:
        shown = {k: (v if vis[k] else None) for k, v in values.items()}
        defects = sorted(f"{own}.{f.key}" for f in spec.fields
                         if vis[f.key] and _is_defect(f, values[f.key]))
        return {**base, own: shown, "_today": today, "_defects": defects}

    def container_visible(cid: str | None, data: dict, memo: dict[str, bool]) -> bool:
        if cid is None:
            return True
        if cid not in memo:
            c = containers[cid]
            memo[cid] = (c.visible and container_visible(c.parent, data, memo)
                         and truthy(c.show_if, data))
        return memo[cid]

    visible = {f.key: True for f in spec.fields}
    for _ in range(len(spec.fields) + len(spec.containers) + 2):
        data = build_data(visible)
        memo: dict[str, bool] = {}
        new = {f.key: f.visible and container_visible(f.section, data, memo)
               and truthy(f.show_if, data) for f in spec.fields}
        if new == visible:
            break
        visible = new
    else:
        raise RuntimeError("Visibility did not settle: the form has a rule cycle.")

    data = build_data(visible)
    overrides = overrides or {}
    derived: dict[str, Any] = {}
    for f in spec.fields:
        if f.type == "derived":
            if not visible[f.key]:
                derived[f.key] = None
            elif overrides.get(f.key) is not None:
                derived[f.key] = overrides[f.key]
            else:
                derived[f.key] = truthy(f.rule, data)

    required = {f.key: visible[f.key] and (f.required or (f.required_if is not None
                                                           and truthy(f.required_if, data)))
                for f in spec.fields}
    errors = {k: "required" for k, req in required.items() if req and values[k] is None}
    for check in spec.checks:
        if all(visible.get(k) and values.get(k) is not None for k in check.fields) \
                and not truthy(check.rule, data):
            for k in check.fields:
                errors.setdefault(k, "check_failed")
    return Result(visible=visible, required=required, errors=errors, derived=derived,
                  defects=data["_defects"])


# ------------------------------------------------------------------ from the database

def spec_from_version(version) -> FormSpec:
    from .models import Field, Page, Section, VersionCheck

    containers = [Container(id=f"p{p.id}", kind="page", visible=p.visible, show_if=p.show_if)
                  for p in Page.objects.filter(version=version)]
    containers += [Container(id=f"s{s.id}", kind="section", parent=f"p{s.page_id}",
                             visible=s.visible, show_if=s.show_if)
                   for s in Section.objects.filter(version=version)]
    fields = [FieldSpec(key=f.key, type=f.type, section=f"s{f.section_id}", visible=f.visible,
                        show_if=f.show_if, required=f.required, required_if=f.required_if,
                        options=f.config.get("options", []), rule=f.config.get("rule"))
              for f in Field.objects.filter(version=version)]
    checks = [CheckSpec(rule=c.rule, message=c.message, fields=c.fields, id=c.id)
              for c in VersionCheck.objects.filter(version=version)]
    return FormSpec(form=version.form.kind, containers=containers, fields=fields, checks=checks)


def validate_answers(version, answers: dict, today: str,
                     overrides: dict | None = None) -> tuple[dict, dict]:
    """Full server-side validation of one form's answers. Returns (cleaned, errors).

    Type errors win over rule errors; answers to hidden fields are dropped unchecked."""
    from .models import Field

    own = version.form.kind
    fields = {f.key: f for f in Field.objects.filter(version=version)}
    raw = answers.get(own) or {}
    errors: dict[str, str] = {k: "UNKNOWN_FIELD" for k in raw if k not in fields}
    if errors:
        return {}, errors
    cleaned: dict[str, Any] = {}
    type_errors: dict[str, str] = {}
    for key, value in raw.items():
        if is_empty(value):
            continue
        try:
            cleaned[key] = clean_answer(fields[key], value)
        except AnswerError as e:
            type_errors[key] = e.code
    result = evaluate_form(spec_from_version(version), {**answers, own: cleaned}, today,
                           overrides)
    visible_type_errors = {k: c for k, c in type_errors.items() if result.visible[k]}
    cleaned = {k: v for k, v in cleaned.items() if result.visible[k]}
    return cleaned, {**result.errors, **visible_type_errors}


# ------------------------------------------------------------------ design time

@dataclass
class Issue:
    path: str
    code: str
    message: str
    ref: str = ""  # for reference problems: the qualified name, e.g. booking.fuel_type


def rule_syntax_issues(rule: Any, path: str) -> list[Issue]:
    out: list[Issue] = []

    def walk(node: Any, p: str) -> None:
        if not isinstance(node, dict):  # scalars are literals; lists are handled by callers
            return
        if len(node) != 1:
            out.append(Issue(p, "INVALID_RULE", "Use exactly one operator per object."))
            return
        op, args = next(iter(node.items()))
        if op in BANNED_OPS:
            hint = (" Use {\"!\": [{\"var\": ...}]} to test for empty."
                    if op.startswith("missing") else "")
            out.append(Issue(p, "BANNED_OPERATOR", f"'{op}' is not supported in rules.{hint}"))
            return
        if op not in ALLOWED_OPS:
            out.append(Issue(p, "UNKNOWN_OPERATOR", f"Unknown operator '{op}'."))
            return
        if op == "var":
            name = args[0] if isinstance(args, list) and args else args
            if (isinstance(args, list) and len(args) > 2) or not isinstance(name, str):
                out.append(Issue(p, "INVALID_RULE", "var needs a field name."))
            return
        arglist = args if isinstance(args, list) else [args]
        if op in ("and", "or") and not arglist:
            out.append(Issue(p, "EMPTY_OPERATOR", f"'{op}' needs at least one condition."))
        for i, a in enumerate(arglist):
            ap = f"{p}.{op}[{i}]"
            if isinstance(a, list):
                if any(isinstance(x, dict | list) for x in a):
                    out.append(Issue(ap, "NESTED_IN_ARRAY",
                                     "Lists inside rules may only hold plain values."))
            else:
                walk(a, ap)

    if isinstance(rule, list):
        return [Issue(path, "INVALID_RULE", "A rule must be an object with one operator.")]
    walk(rule, path)
    return out


def rule_vars(rule: Any) -> set[str]:
    """Variable names a rule reads from the top-level data (not loop-local ones)."""
    found: set[str] = set()

    def walk(node: Any, top: bool) -> None:
        if isinstance(node, list):
            for x in node:
                walk(x, top)
            return
        if not isinstance(node, dict) or len(node) != 1:
            return
        op, args = next(iter(node.items()))
        if op == "var":
            name = args[0] if isinstance(args, list) and args else args
            if top and isinstance(name, str):
                found.add(name)
            return
        arglist = args if isinstance(args, list) else [args]
        for i, a in enumerate(arglist):
            walk(a, top and not (op in ITERATING_OPS and i == 1))

    walk(rule, True)
    return found


def _known_fields(version) -> dict[str, dict[str, str]]:
    """form kind -> {key: type} for the version being validated and the active booking/ops
    forms' latest versions (draft if any)."""
    from .models import Field, Form, FormVersion

    known = {version.form.kind: dict(Field.objects.filter(version=version)
                                     .values_list("key", "type"))}
    for kind in ("booking", "ops"):
        if kind == version.form.kind:
            continue
        form = Form.objects.filter(kind=kind, is_active=True).first()
        latest = form and FormVersion.objects.filter(form=form).order_by("-number").first()
        if latest:
            known[kind] = dict(Field.objects.filter(version=latest).values_list("key", "type"))
    return known


def _reference_issues(rule: Any, path: str, known: dict) -> list[Issue]:
    issues = []
    for name in sorted(rule_vars(rule)):
        if name in SPECIAL_VARS:
            continue
        form, _, rest = name.partition(".")
        key = rest.split(".")[0]
        ftype = known.get(form, {}).get(key)
        if ftype is None:
            issues.append(Issue(path, "UNKNOWN_FIELD", f"'{name}' is not a known field "
                                "(use form.key, e.g. inspection.door or booking.city).", ref=name))
        elif ftype in SYSTEM_FILLED:
            issues.append(Issue(path, "SYSTEM_FIELD_IN_RULE",
                                f"'{name}' is filled by the system and cannot drive rules.",
                                ref=name))
    return issues


def _cycle_issues(version, own: str) -> list[Issue]:
    from .models import Field

    fields = list(Field.objects.filter(version=version).select_related("section__page"))
    defect_choices = {f.key for f in fields if f.type in CHOICE_TYPES
                      and any(o.get("is_defect") for o in f.config.get("options", []))}
    deps: dict[str, set[str]] = {}
    for f in fields:
        refs: set[str] = set()
        for rule in (f.show_if, f.section.show_if, f.section.page.show_if):
            refs |= rule_vars(rule)
        keys = {r.split(".")[1] for r in refs if r.startswith(own + ".") and "." in r}
        if "_defects" in refs:
            keys |= defect_choices
        deps[f.key] = keys

    issues, state = [], {}

    def visit(k: str) -> bool:
        state[k] = "busy"
        for d in deps.get(k, ()):
            if state.get(d) == "busy" or (state.get(d) is None and d in deps and visit(d)):
                state[k] = "done"
                return True
        state[k] = "done"
        return False

    for k in deps:
        if state.get(k) is None and visit(k):
            issues.append(Issue(f"fields.{k}.show_if", "CYCLE",
                                "Visibility rules depend on each other in a loop."))
    return issues


def validate_version(version) -> list[Issue]:
    from .models import Field, Page, Section, VersionCheck

    own = version.form.kind
    known = _known_fields(version)
    issues: list[Issue] = []

    def check_rule(rule: Any, path: str) -> None:
        if rule is None:
            return
        syntax = rule_syntax_issues(rule, path)
        issues.extend(syntax or _reference_issues(rule, path, known))

    for p in Page.objects.filter(version=version):
        check_rule(p.show_if, f"pages.{p.id}.show_if")
    for s in Section.objects.filter(version=version):
        check_rule(s.show_if, f"sections.{s.id}.show_if")
    for f in Field.objects.filter(version=version):
        try:
            validate_config(f.type, f.config)
        except ConfigError as e:
            issues.append(Issue(f"fields.{f.key}.config", "INVALID_CONFIG", str(e)))
        check_rule(f.show_if, f"fields.{f.key}.show_if")
        check_rule(f.required_if, f"fields.{f.key}.required_if")
        if f.type == "derived":
            check_rule(f.config.get("rule"), f"fields.{f.key}.config.rule")
    for c in VersionCheck.objects.filter(version=version):
        check_rule(c.rule, f"checks.{c.id}.rule")
        for k in c.fields:
            if k not in known[own]:
                issues.append(Issue(f"checks.{c.id}.fields", "UNKNOWN_FIELD",
                                    f"'{k}' is not a field of this form."))
    issues.extend(_cycle_issues(version, own))
    return issues


def dependent_issues(version) -> list[Issue]:
    """Publishing a booking/ops form must not break rules of the live versions of other forms that
    read its fields (e.g. an inspection rule on booking.fuel_type). Returns those breakages."""
    from .models import Form, FormVersion, VersionStatus

    kind = version.form.kind
    out: list[Issue] = []
    for form in Form.objects.filter(is_active=True).exclude(kind=kind):
        live = FormVersion.objects.filter(form=form, status=VersionStatus.PUBLISHED) \
            .order_by("-number").first()
        if live is None:
            continue
        for issue in validate_version(live):
            if issue.code in ("UNKNOWN_FIELD", "SYSTEM_FIELD_IN_RULE") \
                    and issue.ref.startswith(kind + "."):
                out.append(Issue(f"forms.{form.key}.{issue.path}", issue.code,
                                 f"Form '{form.key}' (live v{live.number}) uses {issue.ref}, "
                                 "which this version would remove or change.", ref=issue.ref))
    return out
