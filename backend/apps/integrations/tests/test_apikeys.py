import hashlib
import json

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog, User
from apps.bookings.models import Booking
from apps.bookings.tests.conftest import answers, create
from apps.bookings.tests.test_submissions import GOOD, assign, start, submit
from apps.integrations import apikeys
from apps.integrations.models import ApiKey, Delivery

from .conftest import HOOK, make

pytestmark = pytest.mark.django_db
ALL = {"forms": {"booking": ["*"]}}


def new_key(env, scope=ALL, **over):
    r = env.admin.post("/api/v1/api-keys", {"name": "ERP", "scope": scope, **over}, format="json")
    assert r.status_code == 201, r.json()
    return r.json()


def client(key):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Api-Key {key['key']}")
    return c


# ---------------------------------------------------------------- managing keys

def test_a_key_is_shown_once_stored_hashed_with_a_visible_prefix(env):
    k = new_key(env)
    assert k["key"].startswith(f"vk_{k['prefix']}_") and k["allow_delete"] is False
    row = ApiKey.objects.get()
    assert row.key_hash == hashlib.sha256(k["key"].encode()).hexdigest()
    assert k["key"] not in json.dumps(
        [env.admin.get("/api/v1/api-keys").json(), env.admin.get(f"/api/v1/api-keys/{k['id']}").json()])
    assert env.admin.get("/api/v1/api-keys").json()[0]["prefix"] == k["prefix"]


def test_only_admin_manages_keys_and_everything_is_audited(env):
    for c in (env.ops, env.expert):
        assert c.get("/api/v1/api-keys").status_code == 403
        assert c.post("/api/v1/api-keys", {}, format="json").status_code == 403
    k = new_key(env, allow_delete=True)
    env.admin.patch(f"/api/v1/api-keys/{k['id']}", {"name": "ERP2", "allow_delete": False},
                    format="json")
    env.admin.post(f"/api/v1/api-keys/{k['id']}/revoke")
    summaries = " | ".join(AuditLog.objects.filter(action__startswith="api_key.")
                           .values_list("summary", flat=True))
    assert "with DELETE" in summaries and "Updated API key ERP2" in summaries
    assert "Revoked" in summaries and k["key"] not in summaries


@pytest.mark.parametrize("scope", [None, {}, {"forms": {}}, {"forms": []}, {"x": 1},
                                   {"forms": {"ghost": ["*"]}}, {"forms": {"booking": []}},
                                   {"forms": {"booking": ["nope_field"]}},
                                   {"forms": {"booking": "customer_name"}},
                                   {"forms": {"booking": [1]}}])
def test_bad_scopes_are_refused(env, scope):
    r = env.admin.post("/api/v1/api-keys", {"name": "x", "scope": scope}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_SCOPE"


@pytest.mark.parametrize("body,code", [({"name": ""}, "INVALID_NAME"), ({"name": 5}, "INVALID_NAME"),
                                       ({"allow_delete": "yes"}, "INVALID_TOGGLE")])
def test_bad_key_bodies_are_refused(env, body, code):
    r = env.admin.post("/api/v1/api-keys", {"name": "x", "scope": ALL, **body}, format="json")
    assert r.status_code == 400 and r.json()["code"] == code


def test_patch_validation_and_revoked_keys_are_frozen(env):
    k = new_key(env)
    url = f"/api/v1/api-keys/{k['id']}"
    assert env.admin.patch(url, {"name": ""}, format="json").status_code == 400
    assert env.admin.patch(url, {"allow_delete": 1}, format="json").status_code == 400
    assert env.admin.patch(url, {"scope": {"forms": {"booking": ["city"]}}},
                           format="json").json()["scope"] == {"forms": {"booking": ["city"]}}
    env.admin.post(url + "/revoke")
    env.admin.post(url + "/revoke")                               # twice is harmless
    assert AuditLog.objects.filter(action="api_key.revoke").count() == 1
    assert env.admin.patch(url, {"name": "x"}, format="json").status_code == 409


# ---------------------------------------------------------------- authentication

def test_requests_need_a_valid_unrevoked_key(env, booking):
    k = new_key(env)
    assert APIClient().get("/api/v1/ext/bookings").status_code in (401, 403)
    assert env.admin.get("/api/v1/ext/bookings").status_code == 403         # a session is not a key
    bad = APIClient()
    bad.credentials(HTTP_AUTHORIZATION="Api-Key vk_deadbeef_wrong")
    assert bad.get("/api/v1/ext/bookings").status_code == 401
    odd = APIClient()
    odd.credentials(HTTP_AUTHORIZATION="Api-Key short")
    assert odd.get("/api/v1/ext/bookings").status_code == 401
    wrong_secret = APIClient()
    wrong_secret.credentials(HTTP_AUTHORIZATION=f"Api-Key vk_{k['prefix']}_nope")
    assert wrong_secret.get("/api/v1/ext/bookings").status_code == 401
    via_header = APIClient()
    via_header.credentials(HTTP_X_API_KEY=k["key"])
    assert via_header.get("/api/v1/ext/bookings").status_code == 200
    assert client(k).get("/api/v1/ext/bookings").status_code == 200
    assert ApiKey.objects.get().last_used_at is not None
    env.admin.post(f"/api/v1/api-keys/{k['id']}/revoke")
    r = client(k).get("/api/v1/ext/bookings")                                # revoke is immediate
    assert r.status_code == 401


def test_the_service_identity_cannot_sign_in_and_is_not_an_admin_for_last_admin_rules(env):
    u = apikeys.service_user()
    assert apikeys.service_user().pk == u.pk
    assert u.is_active is False and not u.has_usable_password()
    login = APIClient().post("/api/v1/auth/login", {"username": u.username, "password": "x",
                                                    "client": "web"}, format="json")
    assert login.status_code in (401, 403)
    assert User.objects.filter(role="admin", is_active=True).exclude(pk=u.pk).exists()


# ---------------------------------------------------------------- reading and writing

def test_lookup_by_internal_id_or_booking_id(env, booking):
    c = client(new_key(env))
    by_id = c.get(f"/api/v1/ext/bookings/{booking['id']}").json()
    by_ref = c.get("/api/v1/ext/bookings/sa37926").json()                   # case-insensitive
    assert by_id == by_ref and by_id["id"] == booking["id"] and by_id["booking_id"] == "SA37926"
    assert by_id["data"]["customer_name"] == "Asha" and by_id["stage"] == "draft"
    err = c.get("/api/v1/ext/bookings/ghost")
    assert err.status_code == 404 and err.json()["code"] == "NOT_FOUND"


def test_listing_filters_and_scopes_the_data(env, booking):
    create(env.ops, booking_id="B2", city="delhi", inspection_type="ev")
    c = client(new_key(env, {"forms": {"booking": ["booking_id", "city"]}}))
    page = c.get("/api/v1/ext/bookings").json()
    assert page["count"] == 2
    assert all(set(r["data"]) <= {"booking_id", "city"} for r in page["results"])
    assert c.get("/api/v1/ext/bookings?type=ev").json()["count"] == 1
    assert c.get("/api/v1/ext/bookings?stage=draft&city=delhi").json()["count"] == 2
    assert c.get("/api/v1/ext/bookings?search=b2").json()["count"] == 1
    assert c.get("/api/v1/ext/bookings?stage=cancelled").json()["count"] == 0


def test_a_key_without_the_booking_form_in_scope_sees_nothing(ienv, booking):
    c = client(new_key(ienv, {"forms": {"pdi": ["*"]}}))
    for path in ("/api/v1/ext/bookings", f"/api/v1/ext/bookings/{booking['id']}"):
        r = c.get(path)
        assert r.status_code == 403 and r.json()["code"] == "OUT_OF_SCOPE"
    assert c.post("/api/v1/ext/bookings", {"answers": answers()}, format="json").status_code == 403


def test_create_update_with_field_keys(env):
    c = client(new_key(env))
    r = c.post("/api/v1/ext/bookings", {"answers": answers(booking_id="API1")}, format="json")
    assert r.status_code == 201 and r.json()["booking_id"] == "API1"
    assert AuditLog.objects.filter(action="api.booking.create").exists()
    r = c.patch("/api/v1/ext/bookings/API1", {"answers": {"customer_name": "Renamed"}},
                format="json")
    assert r.json()["data"]["customer_name"] == "Renamed"
    assert c.post("/api/v1/ext/bookings", {"answers": answers(booking_id="API1")},
                  format="json").json()["code"] == "DUPLICATE_BOOKING_ID"
    assert c.post("/api/v1/ext/bookings", {"answers": "x"}, format="json").status_code == 400
    assert c.post("/api/v1/ext/bookings", {"answers": {"city": "nowhere"}},
                  format="json").status_code == 400
    assert c.patch("/api/v1/ext/bookings/API1", {"answers": []}, format="json").status_code == 400


def test_out_of_scope_writes_are_403_and_list_the_keys(env, booking):
    c = client(new_key(env, {"forms": {"booking": ["city", "address"]}}))
    r = c.patch(f"/api/v1/ext/bookings/{booking['id']}", {"answers": {
        "city": "delhi", "customer_name": "Hacker", "customer_phone": "1"}}, format="json")
    assert r.status_code == 403 and r.json()["code"] == "OUT_OF_SCOPE"
    assert r.json()["keys"] == ["customer_name", "customer_phone"]
    assert Booking.objects.get(pk=booking["id"]).customer_name == "Asha"        # nothing written
    ok = c.patch(f"/api/v1/ext/bookings/{booking['id']}", {"answers": {"address": "New road 5"}},
                 format="json")
    assert ok.status_code == 200
    assert c.post("/api/v1/ext/bookings", {"answers": answers()}, format="json").status_code == 403


def test_a_stale_row_version_is_a_409_and_actions_only_fields_are_refused(env, booking):
    c = client(new_key(env))
    url = f"/api/v1/ext/bookings/{booking['id']}"
    c.patch(url, {"answers": {"city": "delhi", "address": "Z"}}, format="json")
    stale = c.patch(url, {"answers": {"address": "Y"}, "row_version": 0}, format="json")
    assert stale.status_code == 409 and stale.json()["code"] == "STALE_BOOKING"
    current = c.get(url).json()["row_version"]
    assert c.patch(url, {"answers": {"address": "Y"}, "row_version": current},
                   format="json").status_code == 200
    assert c.patch(url, {"answers": {"assigned_expert": env.expert_user.id}},
                   format="json").json()["code"] == "USE_ACTION"


def test_delete_is_off_by_default_and_audited_when_granted(env, booking):
    off = client(new_key(env))
    r = off.delete(f"/api/v1/ext/bookings/{booking['id']}")
    assert r.status_code == 403 and r.json()["code"] == "DELETE_NOT_ALLOWED"
    assert Booking.objects.filter(pk=booking["id"]).exists()
    on = new_key(env, allow_delete=True)
    assert client(on).delete(f"/api/v1/ext/bookings/{booking['id']}").status_code == 204
    assert not Booking.objects.filter(pk=booking["id"]).exists()
    log = AuditLog.objects.filter(action="api.booking.delete").get()
    assert on["prefix"] in log.summary and log.actor.username == "api-key-service"
    assert client(on).delete("/api/v1/ext/bookings/ghost").status_code == 404


def test_delete_still_needs_the_form_in_scope(ienv, booking):
    k = new_key(ienv, {"forms": {"pdi": ["*"]}}, allow_delete=True)
    assert client(k).delete(f"/api/v1/ext/bookings/{booking['id']}").status_code == 403


def test_bulk_patch_reports_per_item_failures(env, booking):
    create(env.ops, booking_id="B2")
    c = client(new_key(env, {"forms": {"booking": ["city", "address"]}}))
    r = c.post("/api/v1/ext/bookings/bulk", {"items": [
        {"ref": "SA37926", "answers": {"address": "One"}},
        {"ref": "B2", "answers": {"customer_name": "Nope"}},          # out of scope
        {"ref": "ghost", "answers": {"address": "x"}},               # unknown booking
        {"ref": "B2", "answers": {"city": "nowhere"}},               # invalid value
        {"ref": 7, "answers": {}},                                   # bad item
        "junk",
        {"ref": "B2", "answers": {"address": "Two"}}]}, format="json")
    out = r.json()
    assert r.status_code == 200 and out["failed"] == 5
    assert [x["ok"] for x in out["results"]] == [True, False, False, False, False, False, True]
    assert out["results"][1]["error"]["code"] == "OUT_OF_SCOPE"
    assert out["results"][1]["error"]["keys"] == ["customer_name"]
    assert out["results"][2]["error"]["code"] == "NOT_FOUND"
    assert out["results"][3]["error"]["code"] == "INVALID_ANSWERS"
    assert Booking.objects.get(booking_id="B2").answers["address"] == "Two"   # others went through
    assert Booking.objects.get(booking_id="SA37926").answers["address"] == "One"


@pytest.mark.parametrize("items", [None, [], "x", [{"ref": "a"}] * 101])
def test_bulk_needs_between_1_and_100_items(env, items):
    c = client(new_key(env))
    assert c.post("/api/v1/ext/bookings/bulk", {"items": items}, format="json").status_code == 400


# ---------------------------------------------------------------- inspections through the API

def test_inspection_read_and_write_are_scoped_by_field(ienv, booking):
    assign(ienv, booking)
    start(ienv.expert, booking)
    submit(ienv.expert, booking)
    c = client(new_key(ienv, {"forms": {"booking": ["*"], "pdi": ["door", "odometer"]}}))
    got = c.get(f"/api/v1/ext/bookings/{booking['id']}/inspection").json()
    assert got["data"] == {"door": "ok", "odometer": 45} and got["status"] == "submitted"
    r = c.patch(f"/api/v1/ext/bookings/{booking['id']}/inspection",
                {"answers": {"odometer": 99}}, format="json")
    assert r.status_code == 200 and r.json()["data"]["odometer"] == 99
    out = c.patch(f"/api/v1/ext/bookings/{booking['id']}/inspection",
                  {"answers": {"chassis_no": "X"}}, format="json")
    assert out.status_code == 403 and out.json()["keys"] == ["chassis_no"]
    assert c.patch(f"/api/v1/ext/bookings/{booking['id']}/inspection", {"answers": 5},
                   format="json").status_code == 400
    cur = c.get(f"/api/v1/ext/bookings/{booking['id']}/inspection").json()["row_version"]
    assert c.patch(f"/api/v1/ext/bookings/{booking['id']}/inspection", {
        "answers": {"odometer": 100}, "row_version": cur - 1}, format="json").status_code == 409
    assert c.patch(f"/api/v1/ext/bookings/{booking['id']}/inspection", {
        "answers": {"odometer": 100}, "row_version": cur}, format="json").status_code == 200


def test_inspection_needs_the_form_in_scope_and_an_inspection(ienv, booking):
    c = client(new_key(ienv, {"forms": {"booking": ["*"]}}))
    assert c.get(f"/api/v1/ext/bookings/{booking['id']}/inspection").status_code == 403
    d = client(new_key(ienv, {"forms": {"pdi": ["*"]}}))
    r = d.get(f"/api/v1/ext/bookings/{booking['id']}/inspection")
    assert r.status_code == 404 and r.json()["code"] == "NO_INSPECTION"
    assert GOOD


# ---------------------------------------------------------------- API writes fire webhooks

def test_api_writes_and_bulk_updates_fire_webhooks(env, http, booking):
    from apps.integrations.tests.conftest import booking_form_id

    make(env, booking_form_id(), events=["booking.created", "booking.updated",
                                         "booking.deleted"])
    c = client(new_key(env, ALL, allow_delete=True))
    c.post("/api/v1/ext/bookings", {"answers": answers(booking_id="W1")}, format="json")
    c.patch("/api/v1/ext/bookings/W1", {"answers": {"address": "A1"}}, format="json")
    c.post("/api/v1/ext/bookings/bulk", {"items": [{"ref": "W1", "answers": {"address": "A2"}},
                                                    {"ref": "SA37926",
                                                     "answers": {"address": "A3"}}]},
           format="json")
    c.delete("/api/v1/ext/bookings/W1")
    got = [(json.loads(x.request.body)["event"], json.loads(x.request.body)["booking"]["booking_id"])
           for x in http.calls if x.request.url == HOOK]
    assert got == [("booking.created", "W1"), ("booking.updated", "W1"),
                   ("booking.updated", "W1"), ("booking.updated", "SA37926"),
                   ("booking.deleted", "W1")]
    assert Delivery.objects.count() == 5


# ---------------------------------------------------------------- API docs

def test_swagger_is_admin_only_and_describes_the_api(env):
    assert env.admin.get("/api/v1/docs").status_code == 200
    schema = env.admin.get("/api/v1/schema")
    assert schema.status_code == 200 and b"/api/v1/ext/bookings" in schema.content
    for c in (env.ops, env.expert):
        assert c.get("/api/v1/docs").status_code == 403
        assert c.get("/api/v1/schema").status_code == 403


def test_a_booking_type_without_an_active_form_cannot_be_reached_through_the_api(ienv, booking):
    from apps.forms.models import Form

    Form.objects.filter(kind="inspection").update(is_active=False)
    c = client(new_key(ienv, {"forms": {"booking": ["*"]}}))
    assert c.get(f"/api/v1/ext/bookings/{booking['id']}/inspection").status_code == 403
