"""Field-level access: per role and booking stage, a field (or its section/page) is hidden, view
or edit. Separate from action permissions (apps/accounts/catalog.py). The most specific layer
that defines a role+stage wins; if none does, the caller's default policy applies."""
from functools import lru_cache
from typing import Any

from .fieldtypes import SYSTEM_FILLED  # the field-type registry

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


def _rows(version_id: int) -> list[tuple[str, str, dict, dict, dict]]:
    """(key, type, field access, section access, page access) of every field of a version."""
    from .models import Field, Page, Section

    pages = {p.id: p.access for p in Page.objects.filter(version_id=version_id)}
    sections = {s.id: (s.access, pages.get(s.page_id, {}))
                for s in Section.objects.filter(version_id=version_id)}
    return [(f.key, f.type, f.access, *sections[f.section_id])
            for f in Field.objects.filter(version_id=version_id)]


def _levels(rows: list[tuple[str, str, dict, dict, dict]], kind: str, role: str,
            stage: str) -> dict[str, str]:
    out = {}
    for key, ftype, f_access, s_access, p_access in rows:
        level = resolve(role, stage, f_access, s_access, p_access)
        if level is None or (role == "expert" and ftype in SYSTEM_FILLED):
            level = default_level(role, stage, kind, ftype)
        out[key] = level
    return out


def levels_for(version, role: str, stage: str) -> dict[str, str]:
    """{field key: hidden|view|edit} for a role at a stage. Experts never get write access to
    system-filled fields, even if a layer says so."""
    return _levels(_rows(version.id), version.form.type, role, stage)


@lru_cache(maxsize=512)
def _published_levels(version_id: int, kind: str, role: str) -> dict[str, dict[str, str]]:
    rows = _rows(version_id)
    return {stage: _levels(rows, kind, role, stage) for stage in STAGES}


def levels_by_stage(version, role: str) -> dict[str, dict[str, str]]:
    """{stage: levels_for(version, role, stage)}. A published version never changes, so its
    answer is kept in memory (bounded); treat it as read-only. A draft is read each time."""
    if version.status == "published":
        return _published_levels(version.id, version.form.type, role)
    rows = _rows(version.id)
    return {stage: _levels(rows, version.form.type, role, stage) for stage in STAGES}


def visible_answers(levels: dict[str, str], answers: dict, role: str) -> dict:
    """Drop answers the role may not see (unknown keys are visible to Admin only)."""
    return {k: v for k, v in answers.items()
            if levels.get(k, "edit" if role == "admin" else "hidden") != "hidden"}


def may_see_submissions(user, form) -> bool:
    """Admin always; others only if the form's "who can see submissions" list names their role."""
    return role_may_see_submissions(user.role, form)


def role_may_see_submissions(role: str, form) -> bool:
    return role == "admin" or role in (form.submission_roles or [])


def hidden_inspection_forms(user) -> list[int]:
    """Ids of custom forms whose submissions this user may not see at all."""
    from .models import Form, FormType

    if user.role == "admin":
        return []
    return [f.id for f in Form.objects.filter(type=FormType.CUSTOM)
            if not may_see_submissions(user, f)]
