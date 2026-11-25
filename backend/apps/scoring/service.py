"""Scoring of a stored inspection: Key Checks, category ratings, overall, with Ops overrides."""
from typing import Any

from django.utils import timezone

from apps.forms.models import Field
from apps.forms.rules import evaluate_form, spec_from_version

from . import keychecks
from .engine import DEFAULT_CONFIG, WORDS, category_value, overall_result

CHOICE = ("single_choice", "multi_choice")


def _cfg(version) -> dict:
    cfg = version.rating_config or {}
    return {"categories": cfg.get("categories", []),
            "deductions": cfg.get("deductions", DEFAULT_CONFIG["deductions"]),
            "thresholds": cfg.get("thresholds", DEFAULT_CONFIG["thresholds"])}


def section_keys(version, cfg: dict) -> dict:
    """The rating config with each category's sections named by their permanent key (F-045). A
    section given by its title (an older client, a setup file) is turned into its key; a name
    that matches no section is left as it is for publish validation to report."""
    from apps.forms.models import Section

    rows = list(Section.objects.filter(version=version).values_list("key", "title"))
    keys, by_title = {k for k, _ in rows}, {t: k for k, t in rows}
    cats = (cfg or {}).get("categories")
    if not isinstance(cats, list):
        return cfg
    return {**cfg, "categories": [
        {**c, "sections": [s if s in keys else by_title.get(s, s) for s in c.get("sections") or []]}
        if isinstance(c, dict) else c for c in cats]}


def compute(insp) -> dict:
    version, cfg = insp.form_version, _cfg(insp.form_version)
    overrides = insp.overrides or {}
    answers = {"inspection": insp.answers.get("inspection") or {},
               "start": insp.answers.get("start") or {}, "end": insp.answers.get("end") or {},
               "booking": insp.booking.answers}
    day = (timezone.localtime(insp.submitted_at).date().isoformat() if insp.submitted_at
           else timezone.localdate().isoformat())
    result = evaluate_form(spec_from_version(version), answers, day, overrides.get("derived", {}))
    by_section = {s: c["key"] for c in cfg["categories"] for s in c["sections"]}
    severities: dict[str, list[str]] = {c["key"]: [] for c in cfg["categories"]}
    any_critical = False
    fields = list(Field.objects.filter(version=version).select_related("section"))
    for f in fields:
        value = answers["inspection"].get(f.key)
        if f.type not in CHOICE or value is None or not result.visible.get(f.key):
            continue
        options = {o["key"]: o for o in f.config.get("options", [])}
        for chosen in (value if isinstance(value, list) else [value]):
            option = options.get(chosen)
            if option and option.get("is_defect"):
                any_critical |= option["severity"] == "critical"
                if f.section.key in by_section:
                    severities[by_section[f.section.key]].append(option["severity"])
    given = overrides.get("ratings", {})
    ratings: dict[str, dict] = {}
    for c in cfg["categories"]:
        suggested = category_value(severities[c["key"]], cfg["deductions"], c.get("cap"))
        value = given.get(c["key"]) or suggested
        ratings[c["key"]] = {"suggested": suggested, "value": value,
                             "overridden": given.get(c["key"]) is not None}
    values = [r["value"] for r in ratings.values()]
    final = overall_result(values, cfg["thresholds"], any_critical)
    suggested_word = overall_result([r["suggested"] for r in ratings.values()],
                                    cfg["thresholds"], any_critical)["word"]
    word = overrides.get("overall") or final["word"]
    return {
        "key_checks": _key_checks(insp, version, result.data, fields, overrides),
        "derived": result.derived, "defects": result.defects, "ratings": ratings,
        "overall": {"average": final["average"], "word": word, "suggested_word": suggested_word,
                    "overridden": overrides.get("overall") is not None},
        "fields": {f.key: ratings[f.config["category"]]["value"] for f in fields
                   if f.type == "rating" and f.config.get("category") in ratings
                   and result.visible.get(f.key)},
    }


def _key_checks(insp, version, data: dict, fields: list, overrides: dict) -> dict:
    """key -> {auto, value, edited}: the worked-out text, what shows (Ops' text wins) and whether
    Ops wrote it."""
    from apps.bookings.services import booking_form_version

    items = version.key_checks or []
    if not items:
        return {}
    by_part = {"inspection": {f.key: f for f in fields}}
    for part, v in (("start", insp.start_version), ("end", insp.end_version),
                    ("booking", booking_form_version())):
        by_part[part] = {f.key: f for f in Field.objects.filter(version=v)} if v else {}
    auto = keychecks.auto_values(items, data, by_part)
    given = overrides.get("key_checks", {})
    return {k: {"auto": a, "value": given.get(k, a), "edited": k in given}
            for k, a in auto.items()}


def recompute(insp) -> None:
    insp.scores = compute(insp)
    insp.save(update_fields=["scores"])


def validate_overrides(version, body: Any) -> None:
    """Raises ValueError. Values may be None to clear an override."""
    if not isinstance(body, dict) or set(body) - {"ratings", "derived", "overall", "key_checks"}:
        raise ValueError("Send ratings, derived, overall and/or key_checks.")
    categories = {c["key"] for c in _cfg(version)["categories"]}
    derived = set(Field.objects.filter(version=version, type="derived")
                  .values_list("key", flat=True))
    ratings = body.get("ratings", {})
    if not isinstance(ratings, dict):
        raise ValueError("ratings must be an object.")
    for key, v in ratings.items():
        if key not in categories:
            raise ValueError(f"Unknown rating category '{key}'.")
        if v is not None and (not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 5):
            raise ValueError("Ratings are whole numbers from 1 to 5.")
    checks = body.get("derived", {})
    if not isinstance(checks, dict):
        raise ValueError("derived must be an object.")
    for key, v in checks.items():
        if key not in derived:
            raise ValueError(f"'{key}' is not a Key Check of this form.")
        if v is not None and not isinstance(v, bool):
            raise ValueError("Key Checks are true or false.")
    texts = body.get("key_checks", {})
    known = {kc["key"] for kc in version.key_checks or []}
    if not isinstance(texts, dict):
        raise ValueError("key_checks must be an object.")
    for key, v in texts.items():
        if key not in known:
            raise ValueError(f"'{key}' is not a Key Check of this form.")
        if v is not None and (not isinstance(v, str) or len(v) > keychecks.MAX_TEXT):
            raise ValueError(f"A Key Check is text of at most {keychecks.MAX_TEXT} characters.")
    if body.get("overall") is not None and body["overall"] not in WORDS:
        raise ValueError(f"overall must be one of {', '.join(WORDS)}.")


def apply_overrides(current: dict, body: dict) -> dict:
    out = {"ratings": dict(current.get("ratings", {})), "derived": dict(current.get("derived", {})),
           "key_checks": dict(current.get("key_checks", {}))}
    if "overall" in current:
        out["overall"] = current["overall"]
    for group in ("ratings", "derived", "key_checks"):
        for key, v in (body.get(group) or {}).items():
            if v is None:
                out[group].pop(key, None)
            else:
                out[group][key] = v
    if not out["key_checks"]:
        del out["key_checks"]                  # nothing typed: keep the stored shape small
    if "overall" in body:
        if body["overall"] is None:
            out.pop("overall", None)
        else:
            out["overall"] = body["overall"]
    return out


def config_issues(version) -> list[tuple[str, str, str]]:
    """(path, code, message) problems of a version's rating config, for publish validation."""
    from apps.forms.models import Section

    cfg = section_keys(version, _cfg(version))
    keys = set(Section.objects.filter(version=version).values_list("key", flat=True))
    out = []
    for c in cfg["categories"]:
        for t in c["sections"]:
            if t not in keys:
                out.append((f"rating_config.categories.{c['key']}", "UNKNOWN_SECTION",
                            f"Category '{c['key']}' uses section '{t}' which does not exist."))
    known = {c["key"] for c in cfg["categories"]}
    for f in Field.objects.filter(version=version, type="rating"):
        if f.config.get("category") not in known:
            out.append((f"fields.{f.key}.config", "UNKNOWN_CATEGORY",
                        f"Rating field '{f.key}' uses category '{f.config.get('category')}' "
                        "which is not in the rating config."))
    return out
