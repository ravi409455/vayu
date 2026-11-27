"""Plan batch 4: what experts and Ops are told, and pushes that keep going."""
from datetime import timedelta
from unittest import mock

import pytest
import requests
from django.utils import timezone

from apps.accounts.models import Device
from apps.bookings.models import Booking
from apps.bookings.tests.conftest import booking, env  # noqa: F401
from apps.bookings.tests.test_submissions import assign, ienv, start, started, submit  # noqa: F401
from apps.forms.models import Field
from apps.media.tests.conftest import s3  # noqa: F401
from apps.notify import push as fcm
from apps.notify import tasks
from apps.notify.models import Notification

pytestmark = pytest.mark.django_db


def _edit(env, b, **answers):
    rv = Booking.objects.get(pk=b["id"]).row_version
    r = env.ops.patch(f"/api/v1/bookings/{b['id']}", {"answers": answers, "row_version": rv},
                      format="json")
    assert r.status_code == 200, r.json()


def _mine(user):
    return list(Notification.objects.filter(user=user).order_by("id").values_list(
        "kind", "title", "body"))


def test_a_force_released_expert_is_told(started):
    env, booking, _ = started
    env.ops.post(f"/api/v1/bookings/{booking['id']}/force-release")
    released = [n for n in _mine(env.expert_user) if n[0] == "released"]
    assert released == [("released", "Lead released by Ops · SA37926",
                         "Your draft there is closed. Start the lead again to carry on.")]


def test_expert_notices_show_labels_not_raw_keys(env, booking):
    from apps.forms.models import MasterList, MasterListItem

    MasterListItem.objects.create(list=MasterList.objects.get(key="city"), key="pune",
                                  label="Pune")
    assign(env, booking)
    _edit(env, booking, city="pune")
    changed = [n for n in _mine(env.expert_user) if n[0] == "changed"]
    assert changed[-1][2] == "City: Delhi → Pune"


def test_expert_notices_never_carry_fields_hidden_from_them(env, booking):
    Field.objects.filter(key__in=("address", "customer_name"),
                         version__form__type="booking").update(
        access={"expert": {"assigned": "hidden"}})
    assign(env, booking)
    Notification.objects.all().delete()
    _edit(env, booking, address="Aundh")
    assert _mine(env.expert_user) == []                     # not even that it changed
    _edit(env, booking, address="Baner", inspection_time="16:00")
    (kind, _, body), = _mine(env.expert_user)
    assert "Aundh" not in body and "Baner" not in body and "Asha" not in body


def test_a_new_lead_leaves_out_a_customer_name_experts_may_not_see(env, booking):
    Field.objects.filter(key="customer_name", version__form__type="booking").update(
        access={"expert": {"assigned": "hidden"}})
    assign(env, booking)
    (_, title, body), = _mine(env.expert_user)
    assert title == "New lead · Wed 14 Oct, 3:30 pm" and "Asha" not in body


def test_submitted_then_completed_reach_ops_in_order(started):
    env, booking, _ = started
    submit(env.expert, booking)
    titles = [t for _, t, _ in _mine(env.ops_user)]
    assert titles.index("Inspection submitted · SA37926") < titles.index("Inspection completed · SA37926")


# ---------------------------------------------------------------- pushes (F-140, F-141)

def test_one_network_error_never_stops_the_rest_of_a_push_batch(env, booking, settings):
    Device.objects.create(user=env.expert_user, push_token="a", push_token_at=timezone.now())
    Device.objects.create(user=env.expert_user, push_token="b", push_token_at=timezone.now())
    calls = []

    def post(url, **kw):
        calls.append(kw.get("json", {}).get("message", {}).get("token"))
        if len(calls) == 1:
            raise requests.ConnectionError("dns")
        return mock.Mock(status_code=200, text="")

    with mock.patch.object(fcm, "credential", return_value={"project_id": "p"}), \
            mock.patch.object(fcm, "_access_token", return_value="t"), \
            mock.patch.object(fcm.requests, "post", side_effect=post):
        assign(env, booking)
    assert sorted(calls) == ["a", "b"]                          # the second still went
    assert set(Device.objects.values_list("push_token", flat=True)) == {"a", "b"}   # kept


def test_an_earlier_users_device_on_the_same_phone_gets_no_pushes(env, booking):
    earlier = env.make_user("expert", username="earlier")
    Device.objects.create(user=earlier, push_token="phone", push_token_at=timezone.now()
                          - timedelta(days=1))
    Device.objects.create(user=env.expert_user, push_token="phone", push_token_at=timezone.now())
    sent: list[str] = []

    def send(token, data):
        sent.append(token)
        return True

    with mock.patch.object(fcm, "credential", return_value={"project_id": "p"}), \
            mock.patch.object(fcm, "send", side_effect=send):
        assign(env, booking)                                    # the expert who holds it now
        n = Notification.objects.create(user=earlier, kind="x", title="for the earlier user")
        tasks.push([n.id])
    assert sent == ["phone"]                                    # only the newest holder


def test_each_notice_keeps_how_its_push_went(env, booking):
    """F-247."""
    Device.objects.create(user=env.expert_user, push_token="ok", push_token_at=timezone.now())
    Device.objects.create(user=env.expert_user, push_token="dead", push_token_at=timezone.now())
    with mock.patch.object(fcm, "credential", return_value={"project_id": "p"}), \
            mock.patch.object(fcm, "send", side_effect=lambda t, d: t == "ok"):
        assign(env, booking)
    n = Notification.objects.get(user=env.expert_user)
    assert (n.pushed, n.push_failed) == (1, 1)
