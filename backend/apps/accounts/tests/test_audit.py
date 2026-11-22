import pytest
from django.db import connection
from freezegun import freeze_time

from apps.accounts.audit import record
from apps.accounts.models import AuditLog, Role

pytestmark = pytest.mark.django_db


def test_record_persists_a_row(make_user):
    actor = make_user(Role.ADMIN)
    row = record(actor, "form.publish", "form", "42", "Published PDI v3")
    row.refresh_from_db()
    assert (row.actor, row.action, row.target_type, row.target_id, row.summary) == (
        actor, "form.publish", "form", "42", "Published PDI v3")
    assert row.created_at is not None


def test_rows_cannot_be_changed_or_deleted(make_user):
    row = record(make_user(Role.ADMIN), "x.y", "x", "1", "s")
    row.summary = "tampered"
    with pytest.raises(RuntimeError):
        row.save()
    with pytest.raises(RuntimeError):
        row.delete()
    with pytest.raises(RuntimeError):
        AuditLog.objects.all().update(summary="tampered")
    with pytest.raises(RuntimeError):
        AuditLog.objects.all().delete()


def test_database_itself_rejects_update_and_delete(make_user):
    record(make_user(Role.ADMIN), "x.y", "x", "1", "s")
    with connection.cursor() as cur, pytest.raises(Exception, match="append-only"):
        cur.execute("UPDATE accounts_auditlog SET summary = 'tampered'")


@pytest.mark.parametrize("role", [Role.OPS, Role.EXPERT])
def test_list_is_admin_only(api_as, role):
    client, _ = api_as(role)
    assert client.get("/api/v1/audit-logs").status_code == 403


def test_list_newest_first_with_filters_and_pagination(api_as, make_user):
    client, admin = api_as(Role.ADMIN)
    other = make_user(Role.OPS)
    with freeze_time("2026-01-01"):
        record(admin, "form.publish", "form", "1", "a")
    with freeze_time("2026-02-01"):
        record(other, "user.create", "user", "2", "b")
    with freeze_time("2026-03-01"):
        record(admin, "user.create", "user", "3", "c")
    body = client.get("/api/v1/audit-logs").json()
    assert [r["summary"] for r in body["results"]] == ["c", "b", "a"]
    assert body["count"] == 3

    def summaries(query):
        return [r["summary"] for r in client.get(f"/api/v1/audit-logs?{query}").json()["results"]]

    assert summaries(f"actor={admin.id}") == ["c", "a"]
    assert summaries("action=user.create") == ["c", "b"]
    ranged = client.get("/api/v1/audit-logs?from=2026-01-15&to=2026-02-15").json()["results"]
    assert [r["summary"] for r in ranged] == ["b"]
