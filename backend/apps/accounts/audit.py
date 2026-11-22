from .models import AuditLog


def record(actor, action: str, target_type: str, target_id: str | int, summary: str) -> AuditLog:
    return AuditLog.objects.create(
        actor=actor, action=action, target_type=target_type, target_id=str(target_id),
        summary=summary,
    )
