import pytest
from django.core.management import call_command

from apps.accounts.models import Role
from apps.forms.models import Form, FormVersion, MasterList, MasterListItem


@pytest.fixture
def env(db, api_as, make_user):
    """Seeded lists + a published booking form + one client per role."""
    call_command("seed_master_lists")
    MasterListItem.objects.create(list=MasterList.objects.get(key="city"), key="delhi",
                                  label="Delhi")
    MasterListItem.objects.create(list=MasterList.objects.get(key="car_make_model"),
                                  key="maruti_victoris", label="Maruti Victoris")
    admin, admin_user = api_as(Role.ADMIN)
    r = admin.post("/api/v1/forms", {"key": "booking", "kind": "booking", "name": "Booking"},
                   format="json")
    v = r.json()["draft_version"]["id"]
    assert admin.post(f"/api/v1/form-versions/{v}/publish",
                      {"row_version": admin.get(f"/api/v1/form-versions/{v}").json()["row_version"]},
                      format="json").status_code == 200
    ops, ops_user = api_as(Role.OPS)
    expert, expert_user = api_as(Role.EXPERT)
    return type("Env", (), {"admin": admin, "admin_user": admin_user, "ops": ops,
                            "ops_user": ops_user, "expert": expert, "expert_user": expert_user,
                            "make_user": staticmethod(make_user)})


BASE = {"booking_id": "SA37926", "customer_name": "Asha", "customer_phone": "9876543210",
        "address": "12 MG Road", "city": "delhi", "inspection_date": "2026-10-14",
        "inspection_time": "15:30", "inspection_type": "pdi", "car_make_model": "maruti_victoris"}


def answers(**over):
    return {**BASE, **over}


def create(client, **over):
    return client.post("/api/v1/bookings", {"answers": answers(**over)}, format="json")


@pytest.fixture
def booking(env):
    r = create(env.ops)
    assert r.status_code == 201, r.json()
    return r.json()


__all__ = ["env", "booking", "create", "answers", "BASE", "Form", "FormVersion"]
