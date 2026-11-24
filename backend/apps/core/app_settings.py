"""Settings Admin changes on the web Settings page. Each key has defaults and a validator;
a missing row or a missing field falls back to the default."""
from rest_framework.exceptions import ValidationError

from .models import Setting

DEFAULTS: dict[str, dict] = {
    "timing": {"late_grace_minutes": 15, "min_minutes_default": 30,
               "min_minutes_by_type": {"pdi": 30, "used_car": 45, "ev": 40}},
}
MAX_MINUTES = 24 * 60


def _minutes(name: str, v) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= MAX_MINUTES:
        raise ValidationError({name: f"Use whole minutes from 0 to {MAX_MINUTES}."})
    return v


def _clean_timing(v: dict) -> dict:
    by_type = v.get("min_minutes_by_type", {})
    if not isinstance(by_type, dict):
        raise ValidationError({"min_minutes_by_type": "Use {type: minutes}."})
    return {"late_grace_minutes": _minutes("late_grace_minutes", v.get("late_grace_minutes")),
            "min_minutes_default": _minutes("min_minutes_default", v.get("min_minutes_default")),
            "min_minutes_by_type": {str(k): _minutes(f"min_minutes_by_type.{k}", m)
                                    for k, m in by_type.items()}}


CLEANERS = {"timing": _clean_timing}


def get(key: str) -> dict:
    row = Setting.objects.filter(key=key).first()
    return {**DEFAULTS[key], **(row.value if row else {})}


def put(key: str, value) -> tuple[dict, dict]:
    """Validate and save; returns (old, new)."""
    if not isinstance(value, dict):
        raise ValidationError({"detail": "Send a JSON object."})
    old, new = get(key), CLEANERS[key](value)
    Setting.objects.update_or_create(key=key, defaults={"value": new})
    return old, new
