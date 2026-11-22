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
