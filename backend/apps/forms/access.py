"""Field-level access: per role and booking stage, a field (or its section/page) is hidden, view
or edit. Separate from action permissions (apps/accounts/catalog.py). The most specific layer
that defines a role+stage wins; if none does, the caller's default policy applies."""
from typing import Any

ROLES = ("expert", "ops", "admin")
STAGES = ("draft", "assigned", "in_progress", "submitted", "completed", "cancelled")
LEVELS = ("hidden", "view", "edit")


def validate_access(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("access must be an object: {role: {stage: level}}.")
    for role, stages in value.items():
        if role not in ROLES:
            raise ValueError(f"Unknown role '{role}'.")
        if not isinstance(stages, dict):
            raise ValueError(f"access.{role} must be an object: {{stage: level}}.")
        for stage, level in stages.items():
            if stage not in STAGES:
                raise ValueError(f"Unknown stage '{stage}'.")
            if not isinstance(level, str) or level not in LEVELS:
                raise ValueError(f"Level must be one of {', '.join(LEVELS)}.")


def resolve(role: str, stage: str, *layers: dict) -> str | None:
    """Level from the first layer (field, section, page) that defines this role and stage."""
    for layer in layers:
        level = (layer or {}).get(role, {}).get(stage)
        if level is not None:
            return level
    return None


SYSTEM_FILLED = ("derived", "rating")


def default_level(role: str, stage: str, kind: str, ftype: str) -> str:
    """Used when no layer (field/section/page) defines this role and stage."""
    system_filled = ftype in SYSTEM_FILLED
    if role == "admin":
        return "edit"
    if role == "ops":
        return "view" if system_filled else "edit"
    if system_filled:
        return "hidden"                      # experts never see ratings or Key Checks
    if kind == "booking":
        seen = stage in ("assigned", "in_progress", "submitted", "completed")
        return "view" if seen else "hidden"
    if stage == "in_progress":
        return "edit"
    return "view" if stage in ("submitted", "completed") else "hidden"


def levels_for(version, role: str, stage: str) -> dict[str, str]:
    """{field key: hidden|view|edit} for a role at a stage. Experts never get write access to
    system-filled fields, even if a layer says so."""
    from .models import Field, Page, Section

    kind = version.form.kind
    pages = {p.id: p.access for p in Page.objects.filter(version=version)}
    sections = {s.id: (s.access, pages.get(s.page_id, {}))
                for s in Section.objects.filter(version=version)}
    out = {}
    for f in Field.objects.filter(version=version):
        s_access, p_access = sections[f.section_id]
        level = resolve(role, stage, f.access, s_access, p_access)
        if level is None or (role == "expert" and f.type in SYSTEM_FILLED):
            level = default_level(role, stage, kind, f.type)
        out[f.key] = level
    return out


def visible_answers(levels: dict[str, str], answers: dict, role: str) -> dict:
    """Drop answers the role may not see (unknown keys are visible to Admin only)."""
    return {k: v for k, v in answers.items()
            if levels.get(k, "edit" if role == "admin" else "hidden") != "hidden"}
