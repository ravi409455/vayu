"""The job was moved to another expert while the first one inspected it offline (owner's rule,
2026-11-24): the first expert's work still arrives. If the new expert never began, the job goes
back to the first one (no conflict, the new one is told); if both inspected, Ops choose."""
import uuid

import pytest

from apps.accounts.models import Role
from apps.bookings.models import Booking
from apps.bookings.tests.test_submissions import assign, start
from apps.forms.models import FormVersion
from apps.media.tests.conftest import upload
from apps.media.tests.test_upload import menv  # noqa: F401
from apps.notify.models import Notification

from .conftest import jpeg

pytestmark = pytest.mark.django_db


@pytest.fixture
def moved(menv):
    from django.utils import timezone
    from rest_framework.test import APIClient

    from apps.bookings.tests.conftest import create
    b = create(menv.ops, booking_id="OFF1", inspection_date=timezone.localdate().isoformat()).json()
    assign(menv, b)                                   # Ravi's job; he goes offline, never syncs
    sana = menv.make_user(Role.EXPERT, username="sana")
    assign(menv, b, sana)                             # Ops move it to Sana meanwhile
    sana_client = APIClient()
    sana_client.force_authenticate(sana)
    version = FormVersion.objects.filter(form__key="pdi", status="published").latest("id").id
    return menv, b, sana, sana_client, version


def submit_offline(env, b, version, **media):
    body = {"client_submission_uuid": str(uuid.uuid4()), "form_version": version,
            "answers": {"inspection": {"chassis_no": "MA3YPKCSKTJ273129", **media}}}
    return env.expert.post(f"/api/v1/bookings/{b['id']}/submit", body, format="json")


def test_sana_never_began_so_the_job_goes_back_to_ravi(moved, settings):
    env, b, sana, _, version = moved
    photo = upload(env.expert, b["id"], jpeg(), settings)          # his offline photo still goes
    assert photo.status_code == 200, photo.json()
    r = start(env.expert, b)
    assert r.status_code == 409 and r.json()["code"] == "NOT_ASSIGNED"
    Notification.objects.all().delete()
    r = submit_offline(env, b, version, photo_a=[photo.json()["id"]])
    assert r.status_code == 200, r.json()
    got = Booking.objects.get(pk=b["id"])
    assert got.assigned_expert_id == env.expert_user.id and got.conflict == ""
    assert got.stage == "completed"                                # his photo had arrived
    assert [n.title for n in Notification.objects.filter(user=sana)] == ["OFF1 moved to another expert"]
    assert not Notification.objects.filter(kind="problem").exists()    # no conflict for Ops
    assert not Notification.objects.filter(user=env.expert_user).exists()   # not about his own act


def test_both_inspected_so_ops_choose(moved, settings):
    env, b, sana, sana_client, version = moved
    assert start(sana_client, b).status_code in (200, 201)       # Sana began on site
    r = submit_offline(env, b, version)
    assert r.status_code == 200, r.json()
    got = Booking.objects.get(pk=b["id"])
    assert got.conflict == "TWO_EXPERTS" and got.assigned_expert_id == sana.id
    assert Notification.objects.filter(kind="problem", title="Two experts inspected OFF1").exists()


def test_an_expert_who_never_had_the_job_still_cannot_send_to_it(moved, settings):
    env, b, _, _, version = moved
    from rest_framework.test import APIClient
    stranger = APIClient()
    stranger.force_authenticate(env.make_user(Role.EXPERT, username="outsider"))
    from .conftest import initiate_body
    assert stranger.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg()),
                         format="json").status_code == 404
    body = {"client_submission_uuid": str(uuid.uuid4()), "form_version": version,
            "answers": {"inspection": {"chassis_no": "MA3YPKCSKTJ273129"}}}
    assert stranger.post(f"/api/v1/bookings/{b['id']}/submit", body,
                         format="json").status_code == 404
    # Ravi still cannot see it in his lists: delivering is not seeing
    assert all(j["id"] != b["id"] for j in env.expert.get("/api/v1/bookings").json()["results"])


def test_the_moved_job_stays_in_ravis_sync_so_he_can_submit_or_discard(moved):
    env, b, _, sana_client, _ = moved
    from django.utils import timezone
    Booking.objects.filter(pk=b["id"]).update(inspection_date=timezone.localdate())
    jobs = {j["id"]: j for j in env.expert.get("/api/v1/sync/jobs").json()["jobs"]}
    assert jobs[b["id"]]["assigned_to_me"] is False and jobs[b["id"]]["my_draft"] is None
    assert b["id"] in {j["id"] for j in sana_client.get("/api/v1/sync/jobs").json()["jobs"]}
    Booking.objects.filter(pk=b["id"]).update(stage="completed")     # done: not listed for Ravi
    assert b["id"] not in {j["id"] for j in env.expert.get("/api/v1/sync/jobs").json()["jobs"]}


def test_the_moved_route_is_only_for_open_recent_jobs_and_own_files(moved, settings):
    env, b, sana, sana_client, version = moved
    from datetime import timedelta

    from django.utils import timezone

    from .conftest import initiate_body
    hers = upload(sana_client, b["id"], jpeg(), settings).json()["id"]      # Sana's own photo
    assert env.expert.delete(f"/api/v1/media/{hers}").status_code == 404   # never Ravi's to touch
    Booking.objects.filter(pk=b["id"]).update(stage="completed")          # finished: closed to him
    assert env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg()),
                           format="json").status_code == 404
    Booking.objects.filter(pk=b["id"]).update(stage="assigned",
                                              inspection_date=timezone.localdate() - timedelta(days=8))
    assert submit_offline(env, b, version).status_code == 404               # too long ago


def test_each_expert_has_their_own_photo_places(moved, settings):
    env, b, sana, sana_client, _ = moved
    for _ in range(2):                                # photo_a takes 2: Sana fills hers
        assert upload(sana_client, b["id"], jpeg(), settings).status_code == 200
    assert upload(env.expert, b["id"], jpeg(), settings).status_code == 200   # Ravi still can


def test_a_job_moved_long_ago_is_no_longer_listed(moved):
    env, b, _, _, _ = moved
    from datetime import timedelta

    from django.utils import timezone

    from apps.bookings.models import BookingActivity
    BookingActivity.objects.filter(booking_id=b["id"]).update(at=timezone.now() - timedelta(days=3))
    assert b["id"] not in {j["id"] for j in env.expert.get("/api/v1/sync/jobs").json()["jobs"]}
