"""Key Checks: short facts about an inspection that Ops review (e.g. "Accident history").

Admin sets them up per form version (``FormVersion.key_checks``, an ordered list). Experts never
see or fill them. Each one works out a value as text:

- text / number / date: its default (number and date only hint at the format);
- linked: the answers of one or more fields, joined with a separator or put into a template
  such as "{inspection.fuel_type} · {inspection.odometer} km"; the default when all are empty;
- rule: a Yes/No rule over the answers, shown with its two labels.

Ops may replace any value with their own text (``Inspection.overrides["key_checks"]``); that text
stays until they reset it, even if the answers change later.
"""
import re
from functools import partial
from typing import Any

from apps.forms.models import KEY_RE

TYPES = ("text", "number", "date", "linked", "rule")
PARTS = ("inspection", "start", "end", "booking")
MAX_TEXT = 500
PLACEHOLDER = re.compile(r"\{([a-z0-9_]+(?:\.[a-z0-9_]+)?)\}")
COMMON = {"key", "label", "type", "default", "in_report"}
EXTRA = {"text": set(), "number": set(), "date": set(),
         "linked": {"fields", "combine", "separator", "template"},
         "rule": {"rule", "true_label", "false_label"}}


def ref_of(name: str) -> str:
    """A template placeholder or field pick: "fuel_type" means "inspection.fuel_type"."""
    return name if "." in name else f"inspection.{name}"


def _text(v: Any, field: str, limit: int = MAX_TEXT, required: bool = False) -> str:
    if not isinstance(v, str) or len(v) > limit or (required and not v.strip()):
        raise ValueError(f"{field} must be text of at most {limit} characters"
                         f"{' and not empty' if required else ''}.")
    return v


def validate(items: Any) -> None:
    """The shape of a version's Key Checks. Raises ValueError. Field references are checked on
    publish (``issues``), when the form's fields are final."""
    if not isinstance(items, list) or len(items) > 100:
        raise ValueError("key_checks must be a list of at most 100 Key Checks.")
    seen: set[str] = set()
    for i, kc in enumerate(items):
        where = f"Key Check {i + 1}"
        if not isinstance(kc, dict) or kc.get("type") not in TYPES:
            raise ValueError(f"{where}: type must be one of {', '.join(TYPES)}.")
        unknown = set(kc) - COMMON - EXTRA[kc["type"]]
        if unknown:
            raise ValueError(f"{where}: unknown setting {', '.join(sorted(unknown))}.")
        key = kc.get("key")
        if not isinstance(key, str) or not KEY_RE.fullmatch(key) or key in seen:
            raise ValueError(f"{where}: the key must be unique, 2 to 63 lowercase letters, digits "
                             "or _, starting with a letter.")
        seen.add(key)
        _text(kc.get("label"), f"{where}: label", 120, required=True)
        _text(kc.get("default", ""), f"{where}: default")
        if not isinstance(kc.get("in_report", True), bool):
            raise ValueError(f"{where}: in_report must be true or false.")
        if kc["type"] == "linked":
            fields = kc.get("fields")
            if (not isinstance(fields, list) or not 1 <= len(fields) <= 20
                    or not all(isinstance(f, str) and PLACEHOLDER.fullmatch(f"{{{f}}}")
                               for f in fields)):
                raise ValueError(f"{where}: pick 1 to 20 fields.")
            if kc.get("combine", "join") not in ("join", "template"):
                raise ValueError(f"{where}: combine must be join or template.")
            _text(kc.get("separator", ", "), f"{where}: separator", 10)
            if kc.get("combine") == "template":
                template = _text(kc.get("template"), f"{where}: template", required=True)
                picked = {ref_of(f) for f in fields}
                stray = {ref_of(n) for n in PLACEHOLDER.findall(template)} - picked
                if stray:
                    raise ValueError(f"{where}: the template uses {', '.join(sorted(stray))}, "
                                     "which is not one of the picked fields.")
        if kc["type"] == "rule":
            if not isinstance(kc.get("rule"), dict) or not kc["rule"]:
                raise ValueError(f"{where}: the rule is required.")
            for k in ("true_label", "false_label"):
                _text(kc.get(k, ""), f"{where}: {k}", 60)


def issues(version) -> list[tuple[str, str, str]]:
    """(path, code, message) for publish: linked fields must exist and hold an answer (not a
    photo or a system value); rules must be valid."""
    from apps.forms.rules import (
        MEDIA,
        SYSTEM_FILLED,
        _known_fields,
        _reference_issues,
        rule_syntax_issues,
    )

    known = _known_fields(version)
    own = version.form.ns
    out: list[tuple[str, str, str]] = []
    try:
        validate(version.key_checks or [])
    except ValueError as e:
        return [("key_checks", "INVALID_KEY_CHECKS", str(e))]
    for kc in version.key_checks or []:
        path = f"key_checks.{kc['key']}"
        if kc["type"] == "linked":
            for name in kc["fields"]:
                part, _, key = ref_of(name).partition(".")
                ftype = known.get(own if part == "inspection" else part, {}).get(key)
                if ftype is None or ftype in MEDIA or ftype in SYSTEM_FILLED:
                    out.append((f"{path}.fields", "UNKNOWN_FIELD",
                                f"Key Check '{kc['label']}' uses '{name}', which is not a field "
                                "with an answer."))
        if kc["type"] == "rule":
            found = rule_syntax_issues(kc["rule"], f"{path}.rule") or _reference_issues(
                kc["rule"], f"{path}.rule", known)
            out.extend((i.path, i.code, i.message) for i in found)
    return out


def _fill(texts: dict[str, str], m: re.Match) -> str:
    return texts.get(ref_of(m.group(1)), "")


def auto_values(items: list[dict], data: dict, fields: dict[str, dict]) -> dict[str, str]:
    """key -> the worked-out value (text) of each Key Check. ``data`` is what the form's rules
    saw (hidden fields are empty); ``fields`` is part -> {key: Field}."""
    from apps.forms.rules import truthy
    from apps.reports.context import display

    def text(name: str) -> str:
        part, _, key = ref_of(name).partition(".")
        return display(fields.get(part, {}).get(key), (data.get(part) or {}).get(key))[0]

    out: dict[str, str] = {}
    for kc in items:
        default = kc.get("default", "")
        if kc["type"] == "linked":
            texts = {ref_of(f): text(f) for f in kc["fields"]}
            if not any(texts.values()):
                value = default
            elif kc.get("combine") == "template":
                value = PLACEHOLDER.sub(partial(_fill, texts), kc["template"])
            else:
                value = kc.get("separator", ", ").join(t for t in texts.values() if t)
        elif kc["type"] == "rule":
            yes = truthy(kc["rule"], data)
            value = (kc.get("true_label") or "Yes") if yes else (kc.get("false_label") or "No")
        else:
            value = default
        out[kc["key"]] = value
    return out
