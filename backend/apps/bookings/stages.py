STAGES = ("draft", "assigned", "in_progress", "submitted", "completed", "cancelled")
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
