import pytest
from django.core.management import call_command

from apps.accounts.models import AuditLog, Role
from apps.forms.models import MasterList
from apps.forms.services import item_label

pytestmark = pytest.mark.django_db


def make_list(admin, key="city", name="City"):
    return admin.post("/api/v1/master-lists", {"key": key, "name": name}, format="json")


def add_item(admin, list_key, key, label, order=0):
    return admin.post(f"/api/v1/master-lists/{list_key}/items",
                      {"key": key, "label": label, "order": order}, format="json")


def test_admin_creates_list_and_items(admin):
    assert make_list(admin).status_code == 201
    assert add_item(admin, "city", "noida", "Noida", 2).status_code == 201
    assert add_item(admin, "city", "delhi", "Delhi", 1).status_code == 201
    items = admin.get("/api/v1/master-lists/city/items").json()
    assert [i["key"] for i in items] == ["delhi", "noida"]  # by order


@pytest.mark.parametrize("key", ["City", "1city", "ci ty", "", "c" * 65])
def test_list_key_must_be_lowercase_slug(admin, key):
    assert make_list(admin, key=key).status_code == 400


def test_duplicate_list_or_item_key_rejected(admin):
    make_list(admin)
    assert make_list(admin).status_code == 400
    add_item(admin, "city", "delhi", "Delhi")
    assert add_item(admin, "city", "delhi", "Delhi 2").status_code == 400


def test_reorder_and_relabel_items(admin):
    make_list(admin)
    a = add_item(admin, "city", "delhi", "Delhi", 1).json()
    add_item(admin, "city", "noida", "Noida", 2)
    admin.patch(f"/api/v1/master-list-items/{a['id']}", {"order": 3, "label": "New Delhi"},
                format="json")
    items = admin.get("/api/v1/master-lists/city/items").json()
    assert [(i["key"], i["label"]) for i in items] == [("noida", "Noida"), ("delhi", "New Delhi")]


def test_item_key_cannot_change(admin):
    make_list(admin)
    a = add_item(admin, "city", "delhi", "Delhi").json()
    r = admin.patch(f"/api/v1/master-list-items/{a['id']}", {"key": "dilli"}, format="json")
    assert r.status_code == 400


def test_archived_items_hidden_but_labels_still_resolve(admin):
    make_list(admin)
    a = add_item(admin, "city", "delhi", "Delhi").json()
    admin.patch(f"/api/v1/master-list-items/{a['id']}", {"archived": True}, format="json")
    assert admin.get("/api/v1/master-lists/city/items").json() == []
    assert len(admin.get("/api/v1/master-lists/city/items?include_archived=1").json()) == 1
    assert item_label("city", "delhi") == "Delhi"


def test_items_are_never_deleted(admin):
    make_list(admin)
    a = add_item(admin, "city", "delhi", "Delhi").json()
    assert admin.delete(f"/api/v1/master-list-items/{a['id']}").status_code == 405
    assert admin.delete("/api/v1/master-lists/city").status_code == 405


@pytest.mark.parametrize("role", [Role.OPS, Role.EXPERT])
def test_only_admin_mutates_but_everyone_reads(api_as, admin, role):
    make_list(admin)
    a = add_item(admin, "city", "delhi", "Delhi").json()
    client, _ = api_as(role)
    assert make_list(client, key="other").status_code == 403
    assert add_item(client, "city", "noida", "Noida").status_code == 403
    assert client.patch(f"/api/v1/master-list-items/{a['id']}", {"label": "x"},
                        format="json").status_code == 403
    assert client.get("/api/v1/master-lists/city/items").status_code == 200


def test_mutations_are_audited(admin):
    make_list(admin)
    a = add_item(admin, "city", "delhi", "Delhi").json()
    admin.patch(f"/api/v1/master-list-items/{a['id']}", {"label": "Dilli"}, format="json")
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {"master_list.create", "master_list.item_create", "master_list.item_update"} <= actions


def test_seed_command_is_idempotent_and_has_launch_lists():
    call_command("seed_master_lists")
    call_command("seed_master_lists")
    keys = set(MasterList.objects.values_list("key", flat=True))
    assert {"city", "car_make_model", "cancel_reason", "reschedule_reason", "ops_status",
            "inspection_type"} <= keys
    cancel = set(MasterList.objects.get(key="cancel_reason").items.values_list("key", flat=True))
    assert "on_arrival" in cancel
    types = set(MasterList.objects.get(key="inspection_type").items.values_list("key", flat=True))
    assert types == {"pdi", "used_car", "ev"}
    assert MasterList.objects.get(key="cancel_reason").items.count() == len(cancel)  # no dupes
