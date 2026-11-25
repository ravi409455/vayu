"""Booking stages and inspection statuses, and which stage may follow which."""
from django.db import models


class Stage(models.TextChoices):
    """A booking's stage (F-008); compares equal to its plain string."""
    DRAFT = "draft"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InspectionStatus(models.TextChoices):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    SUPERSEDED = "superseded"        # Ops kept the other one in a conflict
    RELEASED = "released"            # force-released while a draft; may still arrive


STAGES = tuple(Stage.values)
_LEGAL = {
    "draft": {"assigned", "cancelled"},
    "assigned": {"assigned", "in_progress", "cancelled"},       # assigned->assigned = reassign
    "in_progress": {"submitted", "assigned", "cancelled"},      # ->assigned = force-release
    "submitted": {"completed"},
    "completed": set(),
    "cancelled": set(),
}


def can_transition(frm: str, to: str) -> bool:
    return to in _LEGAL[frm]
