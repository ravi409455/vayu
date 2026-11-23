import pytest

from apps.accounts.models import Role
from apps.forms.models import FormVersion, VersionStatus


@pytest.fixture
def admin(api_as):
    client, _ = api_as(Role.ADMIN)
    return client


@pytest.fixture
def make_form(admin):
    def _make(key="pdi", kind="inspection", name=None):
        if kind in ("booking", "start", "end"):            # these exist from the start
            from apps.forms.models import Form

            return admin.get(f"/api/v1/forms/{Form.objects.get(type=kind).id}").json()
        r = admin.post("/api/v1/forms", {"key": key, "name": name or key.upper()},
                       format="json")
        assert r.status_code == 201, r.json()
        return r.json()

    return _make


@pytest.fixture
def tree(admin):
    def _tree(version_id):
        return admin.get(f"/api/v1/form-versions/{version_id}").json()

    return _tree


@pytest.fixture
def add_field(admin):
    def _add(section_id, key, type="short_text", **extra):
        body = {"key": key, "label": key.replace("_", " ").title(), "type": type, **extra}
        return admin.post(f"/api/v1/sections/{section_id}/fields", body, format="json")

    return _add


def publish(version_id):
    """Phase 2 stand-in for the real publish flow (Phase 3)."""
    FormVersion.objects.filter(pk=version_id).update(status=VersionStatus.PUBLISHED)
