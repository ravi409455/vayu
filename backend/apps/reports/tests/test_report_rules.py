"""Plan batch 2: the customer's report is right.

C-01 the report keeps the counted inspection during a conflict; F-219 nothing re-renders by
itself (out of date + Regenerate); F-220 purged photos freeze the last PDF; H-18 a failed later
render keeps the verify page; R-09 ZIP links last 30 days from the first PDF; H-06 the customer
ZIP holds only the counted inspection's files; C-02 "Not able to check" keys; F-119 the layout of
the inspection's form version; F-118 the render claims before it reads.
"""
import json
import uuid
from datetime import timedelta
from pathlib import Path
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking, Inspection
from apps.bookings.tests.conftest import custom_form, publish_draft
from apps.bookings.tests.test_submissions import start
from apps.core import events
from apps.media.models import MediaAsset, MediaZip
from apps.reports import context, tasks
from apps.reports.models import PdfTemplateVersion, Report, ReportRender

from .test_reports import DEFN, complete_job, one_page, pdf_text, renv, set_template, source  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def done(renv, settings):
    set_template(renv)
    b = complete_job(renv, settings=settings)               # 2 photo_a + 1 door_photo (dent)
    return renv, b, Report.objects.get(booking_id=b["id"])


def _other_expert(env, name="sana"):
    user = env.make_user("expert", username=name)
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


def _late_submit(env, b, settings, odometer=99999):
    """Ops moved the job from expert A to Sana, who finished it; A's offline work then arrives."""
    sana, sc = _other_expert(env)
    Booking.objects.filter(pk=b["id"]).update(assigned_expert=sana)     # moved away from A
    insp = Inspection.objects.get(booking_id=b["id"])
    Inspection.objects.filter(pk=insp.pk).update(expert=sana)          # Sana's inspection
    start(env.expert, b)                                               # refused: not assigned
    Inspection.objects.create(booking_id=b["id"], expert=env.expert_user,
                              form_version=insp.form_version, client_start_uuid=uuid.uuid4())
    body = {"client_submission_uuid": str(uuid.uuid4()), "answers": {"inspection": {
        "chassis_no": "MA3YPKCSKTJ273129", "door": "ok", "odometer": odometer}}}
    r = env.expert.post(f"/api/v1/bookings/{b['id']}/submit", body, format="json")
    assert r.status_code == 200, r.json()
    return sana


# ---------------------------------------------------------------- C-01 conflicts

def test_a_late_submit_in_conflict_never_reaches_the_customers_report(done, settings):
    env, b, r = done
    with events.capture() as seen:
        _late_submit(env, b, settings)
    booking = Booking.objects.get(pk=b["id"])
    assert booking.conflict == "TWO_EXPERTS" and booking.stage == "completed"
    now = Report.objects.get(pk=r.pk)
    assert now.revision == 1 and "pdf.ready" not in [n for n, _ in seen]     # the old report
    text, _ = pdf_text(b["id"])
    assert "45 km" in text and "99999" not in text
    verify = APIClient().get(f"/api/v1/verify/{r.token}").json()
    assert verify["valid"] is True and verify["revision"] == 1
    info = env.ops.get(f"/api/v1/bookings/{b['id']}/report").json()
    assert info["regenerate"] == {"allowed": False, "reason": "Choose which inspection counts "
                                                              "first."}
    late = Inspection.objects.get(booking_id=b["id"], expert=env.expert_user)
    with events.capture() as seen:
        assert env.ops.post(f"/api/v1/bookings/{b['id']}/resolve-conflict",
                            {"inspection": str(late.id)}, format="json").status_code == 200
    assert [n for n, _ in seen].count("pdf.ready") == 1                     # made once, from it
    text, _ = pdf_text(b["id"])
    assert "99999 km" in text


def test_a_first_completion_in_conflict_has_no_report_until_ops_choose(renv, settings):
    set_template(renv)
    b = complete_job(renv, booking_id="CF1", door="ok", photos=0, settings=settings)
    Report.objects.all().delete()
    Booking.objects.filter(pk=b["id"]).update(stage="submitted", conflict="TWO_EXPERTS")
    assert tasks.render_report(b["id"]) == "skipped"                  # nothing counts yet
    assert not Report.objects.exists()
    keep = Inspection.objects.get(booking_id=b["id"])
    renv.ops.post(f"/api/v1/bookings/{b['id']}/resolve-conflict", {"inspection": str(keep.id)},
                  format="json")
    assert Report.objects.get(booking_id=b["id"]).revision == 1         # made once, by itself


def test_a_conflict_that_arrives_while_a_render_waits_stops_it(done):
    env, b, r = done
    real = tasks._finds
    calls = []

    def conflict_after_claim(booking):
        calls.append(1)
        if len(calls) == 2:          # read again after the claim (F-118): a conflict arrived
            Booking.objects.filter(pk=booking.pk).update(conflict="RELEASED_DRAFT_ARRIVED")
            booking.refresh_from_db()
            return None, None
        return real(booking)

    with mock.patch.object(tasks, "_finds", side_effect=conflict_after_claim):
        assert tasks.render_report(b["id"]) == "skipped"
    now = Report.objects.get(pk=r.pk)
    assert now.revision == 1 and now.render_started_at is None          # claim given back


# ---------------------------------------------------------------- F-219 nothing re-renders itself

def test_every_change_only_marks_the_report_out_of_date(done, settings):
    env, b, r = done
    from apps.reports.handlers import on_event

    with mock.patch("apps.reports.tasks.render_report.delay") as render:
        for name in ("booking.updated", "media.deleted", "inspection.updated"):
            Report.objects.filter(pk=r.pk).update(stale=False)
            on_event(name, {"booking": b["id"]})
            assert Report.objects.get(pk=r.pk).stale is True
        on_event("booking.created", {"booking": b["id"]})               # not about the report
        assert env.ops.patch(f"/api/v1/bookings/{b['id']}", {
            "answers": {"customer_name": "Asha K"},
            "row_version": Booking.objects.get(pk=b["id"]).row_version},
            format="json").status_code == 200
    render.assert_not_called()
    assert Report.objects.get(pk=r.pk).revision == 1


def test_a_file_ops_add_after_completion_marks_the_report_out_of_date(done, settings):
    from apps.media.tasks import verify_asset

    env, b, r = done
    asset = MediaAsset.objects.filter(booking_id=b["id"], field_key="photo_a")[0]
    MediaAsset.objects.filter(pk=asset.pk).update(status="uploaded")    # it arrives only now
    with mock.patch("apps.reports.tasks.render_report.delay") as render:
        assert verify_asset(str(asset.pk)) == "verified"
    render.assert_not_called()
    assert Report.objects.get(pk=r.pk).stale is True


def test_the_sweep_retries_failed_and_killed_renders_only(done):
    env, b, r = done
    Report.objects.filter(pk=r.pk).update(stale=True)
    with mock.patch("apps.reports.tasks.render_report.delay") as render:
        assert tasks.sweep_reports() == 0                                # out of date: Ops decide
        Report.objects.filter(pk=r.pk).update(retry_at=timezone.now() - timedelta(seconds=1))
        assert tasks.sweep_reports() == 1
        Report.objects.filter(pk=r.pk).update(retry_at=None, render_started_at=(
            timezone.now() - tasks.STUCK_AFTER - timedelta(seconds=5)))
        assert tasks.sweep_reports() == 1
    assert render.call_count == 2


@pytest.mark.parametrize("why", ["not_completed", "busy"])
def test_regenerate_is_refused_with_its_reason(done, why):
    env, b, r = done
    if why == "not_completed":
        Booking.objects.filter(pk=b["id"]).update(stage="submitted")
    else:
        Report.objects.filter(pk=r.pk).update(render_started_at=timezone.now())
    out = env.ops.post(f"/api/v1/bookings/{b['id']}/report/regenerate")
    assert out.status_code == 409 and out.json()["code"] == "CANNOT_REGENERATE"
    info = env.ops.get(f"/api/v1/bookings/{b['id']}/report").json()
    assert info["regenerate"]["allowed"] is False and info["regenerate"]["reason"]


def test_regenerate_needs_the_edit_permission_and_works_without_a_report_row(done):
    env, b, r = done
    assert env.expert.post(f"/api/v1/bookings/{b['id']}/report/regenerate").status_code == 403
    Report.objects.all().delete()                  # its first render never left a row
    assert env.ops.post(f"/api/v1/bookings/{b['id']}/report/regenerate").status_code == 202
    assert Report.objects.get(booking_id=b["id"]).status == "ready"


# ---------------------------------------------------------------- F-220 purged photos

def test_once_its_photos_are_purged_the_last_pdf_is_kept_and_regenerate_says_why(done):
    env, b, r = done
    MediaAsset.objects.filter(booking_id=b["id"], kind="photo").update(status="purged")
    info = env.ops.get(f"/api/v1/bookings/{b['id']}/report").json()
    assert info["regenerate"]["allowed"] is False
    assert "retention" in info["regenerate"]["reason"] and info["url"]   # the old PDF stays
    out = env.ops.post(f"/api/v1/bookings/{b['id']}/report/regenerate")
    assert out.status_code == 409
    assert Report.objects.get(pk=r.pk).revision == 1


# ---------------------------------------------------------------- H-18 the verify page

def test_a_later_render_that_fails_keeps_the_report_genuine(done, monkeypatch):
    env, b, r = done
    from apps.reports import render

    monkeypatch.setattr(render, "render_pdf", mock.Mock(side_effect=RuntimeError("boom")))
    with events.capture() as seen:
        assert tasks.render_report(b["id"]) == "failed"
        assert tasks.render_report(b["id"]) == "failed"
    now = Report.objects.get(pk=r.pk)
    assert now.status == "ready" and now.key == r.key and now.error == "render_failed"
    assert now.stale is True                  # the last PDF is out of date until one succeeds
    assert [n for n, _ in seen].count("alert.pdf_failed") == 1             # told once
    verify = APIClient().get(f"/api/v1/verify/{r.token}")
    assert verify.status_code == 200 and verify.json()["valid"] is True
    problems = env.ops.get("/api/v1/problems/reports").json()
    assert [{k: p[k] for k in ("booking", "status", "error", "problem")} for p in problems] == [
        {"booking": b["id"], "status": "ready", "error": "render_failed", "problem": "failed"}]
    last = ReportRender.objects.filter(report=r, ok=False).latest("finished_at").finished_at
    assert problems[0]["at"] == last.isoformat().replace("+00:00", "Z")  # when it last failed
    monkeypatch.undo()
    assert tasks.render_report(b["id"]) == "ready"
    assert Report.objects.get(pk=r.pk).error == "" and not env.ops.get(
        "/api/v1/problems/reports").json()


def test_the_migration_turns_reports_that_still_have_a_pdf_back_to_ready(done):
    from importlib import import_module

    from django.apps import apps as django_apps

    env, b, r = done
    Report.objects.filter(pk=r.pk).update(status="failed", error="render_failed",
                                          first_generated_at=None)
    m = import_module("apps.reports.migrations.0007_report_first_pdf_and_failures")
    m.forward(django_apps, None)
    now = Report.objects.get(pk=r.pk)
    assert now.status == "ready" and now.first_generated_at == now.generated_at
    m.backward(django_apps, None)
    assert Report.objects.get(pk=r.pk).status == "failed"


# ---------------------------------------------------------------- R-09 / H-06 ZIP links

def test_photo_and_video_links_last_30_days_from_the_first_pdf(done):
    env, b, r = done
    assert r.first_generated_at is not None
    assert APIClient().get(f"/api/v1/verify/{r.token}/photos").status_code == 200
    Report.objects.filter(pk=r.pk).update(
        first_generated_at=timezone.now() - timedelta(days=31))
    gone = APIClient().get(f"/api/v1/verify/{r.token}/photos")
    assert gone.status_code == 410 and gone.json()["code"] == "LINK_EXPIRED"
    sv = source(b, token=r.token).values()["sys"]
    assert sv["photos_url"] == "" and sv["videos_url"] == "" and sv["photo_count"] == "3"
    assert APIClient().get(f"/api/v1/verify/{r.token}").status_code == 200   # QR keeps working
    # a PDF made now leaves the button out instead of printing a dead link
    from apps.reports import render

    src = source(b, token=r.token)
    page = one_page({"type": "button", "link": "photos", "label": "All photos"},
                    {"type": "button", "link": "verify", "label": "Check it"})
    html = render.render_html(context.build(src, page), page, src.values())
    assert "All photos" not in html and "Check it" in html
    first = Report.objects.get(pk=r.pk).first_generated_at
    assert first is not None and first < timezone.now() - timedelta(days=30)


def test_regenerating_keeps_the_first_pdf_date(done):
    env, b, r = done
    assert env.ops.post(f"/api/v1/bookings/{b['id']}/report/regenerate").status_code == 202
    now = Report.objects.get(pk=r.pk)
    assert now.revision == 2 and now.first_generated_at == r.first_generated_at


def test_the_customer_zip_holds_only_the_counted_inspections_files(done, settings):
    env, b, r = done
    from apps.media.tests.conftest import initiate_body, jpeg, put_parts

    # an Ops upload no answer uses (a closed tab)
    data = jpeg(color=(9, 9, 9))
    init = env.ops.post("/api/v1/media/initiate", initiate_body(b["id"], data), format="json")
    if init.status_code in (200, 201):
        parts = put_parts(init.json(), data, settings)
        env.ops.post(f"/api/v1/media/{init.json()['id']}/complete", {"parts": parts},
                     format="json")
    sv = source(b, token=r.token).values()["sys"]
    assert sv["photo_count"] == "3"
    body = APIClient().get(f"/api/v1/verify/{r.token}/photos").json()
    assert body["count"] == 3
    insp = Inspection.objects.get(booking_id=b["id"])
    named = {*insp.answers["inspection"]["photo_a"], *insp.answers["inspection"]["door_photo"]}
    assert set(MediaZip.objects.get().only) == named


def test_no_photos_left_on_the_counted_inspection_says_so(done):
    env, b, r = done
    MediaAsset.objects.filter(booking_id=b["id"]).update(status="purged")
    gone = APIClient().get(f"/api/v1/verify/{r.token}/photos")
    assert gone.status_code == 410 and gone.json()["code"] == "MEDIA_REMOVED"
    none = APIClient().get(f"/api/v1/verify/{r.token}/videos")
    assert none.status_code == 404 and none.json()["code"] == "NO_MEDIA"


# ---------------------------------------------------------------- C-02 "Not able to check"

def test_not_able_to_check_counts_the_key_the_real_forms_use(renv, settings):
    set_template(renv)
    from apps.forms.models import Field

    f = Field.objects.get(key="door", version__status="published")
    Field.objects.filter(pk=f.pk).update(config={**f.config, "options": [
        *f.config["options"], {"key": "not_able_to_check", "label": "Not Able to Check"}]})
    b = complete_job(renv, booking_id="NC1", door="not_able_to_check", photos=0, settings=settings)
    sv = source(b).values()["sys"]
    assert sv["not_checked"] == "1" and sv["not_checked_list"] == "door"
    assert "not_checked" in context.flags(source(b), "inspection.door",
                                          source(b).cell("inspection.door"))


def test_the_frozen_forms_name_not_able_to_check_with_keys_the_report_reads():
    frozen = Path(__file__).resolve().parents[2] / "platform" / "setup" / "frozen"
    found = 0
    for name in ("pdi", "used_car", "ev"):
        text = (frozen / f"{name}.json").read_text()
        for opt in _options(json.loads(text)):
            if opt.get("label", "").strip().lower() in ("not able to check", "not checked"):
                assert opt["key"] in context.NOT_CHECKED, (name, opt)
                found += 1
    assert found > 40                       # pdi 21+, used car 16+, ev 18 at the review


def _options(node):
    if isinstance(node, dict):
        if isinstance(node.get("options"), list):
            yield from (o for o in node["options"] if isinstance(o, dict))
        for v in node.values():
            yield from _options(v)
    elif isinstance(node, list):
        for v in node:
            yield from _options(v)


# ---------------------------------------------------------------- F-119 the layout of its version

def test_an_inspection_on_an_older_form_version_keeps_the_layout_made_for_it(done):
    env, b, r = done
    insp = Inspection.objects.get(booking_id=b["id"])
    first = PdfTemplateVersion.objects.get(status="published")
    assert tasks.published_template(Booking.objects.get(pk=b["id"]), insp) == first
    # the Admin publishes a new form version, then a new layout for it
    form = custom_form(env.admin, "pdi")
    publish_draft(env.admin, form["id"])
    later = env.admin.post(f"/api/v1/pdf-templates/{first.template_id}/drafts")
    assert later.status_code == 201, later.json()
    newer = PdfTemplateVersion.objects.get(status="draft")
    newer.definition, newer.status, newer.number = DEFN, "published", 2
    newer.published_at = timezone.now() + timedelta(seconds=1)
    newer.save()
    booking = Booking.objects.get(pk=b["id"])
    assert tasks.published_template(booking, insp) == first             # made for its version
    PdfTemplateVersion.objects.filter(pk=first.pk).update(
        published_at=timezone.now() + timedelta(days=1))                # no layout that old
    assert tasks.published_template(booking, insp) == first             # the oldest one then
    new_insp = Inspection(form_version=form_versions_latest(), booking=booking)
    assert tasks.published_template(booking, new_insp) == newer


def form_versions_latest():
    from apps.forms.models import FormVersion

    return FormVersion.objects.filter(form__key="pdi", status="published").order_by(
        "-number").first()


def test_a_purge_job_removes_the_jpeg_copy_too(done, settings):
    from apps.media import storage
    from apps.media.tasks import purge_expired

    env, b, r = done
    a = MediaAsset.objects.filter(booking_id=b["id"], kind="photo")[0]
    storage.put("copies/x.jpg", b"x", "image/jpeg")
    MediaAsset.objects.filter(pk=a.pk).update(jpeg_key="copies/x.jpg",
                                              created_at=timezone.now() - timedelta(days=31))
    from apps.core import app_settings

    app_settings.put("media", {"photo_days": 30, "video_days": 0})
    assert purge_expired() >= 1
    assert not storage.exists("copies/x.jpg")


def test_an_out_of_date_report_is_in_needs_you_with_since_when_and_tells_nobody(done):
    """REQUIREMENTS §9 "edited but not regenerated": the problem list only, no bell or push."""
    from apps.notify.models import Notification

    env, b, r = done
    assert env.ops.get("/api/v1/problems/reports").json() == []
    before = Notification.objects.count()
    insp = Inspection.objects.get(booking_id=b["id"])
    env.ops.patch(f"/api/v1/inspections/{insp.id}", {
        "answers": {"inspection": {"odometer": 99}}, "row_version": 0}, format="json")
    first = Report.objects.get(pk=r.pk).stale_since
    env.ops.patch(f"/api/v1/inspections/{insp.id}", {
        "answers": {"inspection": {"odometer": 98}}, "row_version": 1}, format="json")
    assert Report.objects.get(pk=r.pk).stale_since == first            # since the first change
    (row,) = env.ops.get("/api/v1/problems/reports").json()
    assert row["problem"] == "out_of_date" and row["booking_id"] == "SA37926"
    assert row["out_of_date_since"] and row["status"] == "ready"
    assert row["at"] == row["out_of_date_since"]                        # since it went out of date
    assert not Notification.objects.filter(pk__gt=0, kind="problem").exclude(
        title__startswith="SA37926 completed").count() > before          # no new problem notice
    assert env.ops.post(f"/api/v1/bookings/{b['id']}/report/regenerate").status_code == 202
    assert env.ops.get("/api/v1/problems/reports").json() == []
    assert Report.objects.get(pk=r.pk).stale_since is None


def test_problems_name_failed_and_stuck_renders(done):
    env, b, r = done
    Report.objects.filter(pk=r.pk).update(error="render_failed")
    assert env.ops.get("/api/v1/problems/reports").json()[0]["problem"] == "failed"
    started = timezone.now() - tasks.STUCK_AFTER - timedelta(seconds=5)
    Report.objects.filter(pk=r.pk).update(error="", render_started_at=started)
    (row,) = env.ops.get("/api/v1/problems/reports").json()
    assert row["problem"] == "stuck"
    assert row["at"] == started.isoformat().replace("+00:00", "Z")       # when its render began


# ---------------------------------------------------------------- H-5 a lost first report

def _lose_the_first_report(b, minutes=11):
    Report.objects.filter(booking_id=b["id"]).delete()             # the first render never ran
    Inspection.objects.filter(booking_id=b["id"]).update(
        submitted_at=timezone.now() - timedelta(minutes=minutes))


def test_a_first_report_that_never_came_is_made_by_the_sweep(done):
    env, b, _ = done
    _lose_the_first_report(b, minutes=1)
    with mock.patch("apps.reports.tasks.render_report.delay") as render:
        assert tasks.sweep_reports() == 0                       # its render may still be queued
    _lose_the_first_report(b)
    assert tasks.sweep_reports() == 1
    assert Report.objects.get(booking_id=b["id"]).status == "ready"
    _lose_the_first_report(b, minutes=60 * 24 * 3)                  # too old: Ops only
    with mock.patch("apps.reports.tasks.render_report.delay") as render:
        assert tasks.sweep_reports() == 0
    render.assert_not_called()


def test_the_catch_up_never_makes_a_second_revision(done):
    env, b, r = done
    assert tasks.render_report(b["id"], first_only=True) == "skipped"
    assert Report.objects.get(pk=r.pk).revision == r.revision


def test_problems_name_a_completed_booking_with_no_report(done):
    env, b, _ = done
    _lose_the_first_report(b)
    (row,) = env.ops.get("/api/v1/problems/reports").json()
    assert row["problem"] == "missing" and row["booking"] == b["id"]
    from apps.bookings.models import Inspection
    sent = Inspection.objects.filter(booking_id=b["id"], status="submitted").latest("submitted_at")
    assert row["at"] == sent.submitted_at.isoformat().replace("+00:00", "Z")   # when it was sent
    Booking.objects.filter(pk=b["id"]).update(conflict="TWO_EXPERTS")   # Ops choose first
    assert env.ops.get("/api/v1/problems/reports").json() == []


def test_an_out_of_date_report_in_conflict_is_not_offered_for_regenerate(done):
    """L-5: during a conflict the server refuses Regenerate, so Needs you does not offer it."""
    env, b, r = done
    Report.objects.filter(pk=r.pk).update(stale=True)
    assert env.ops.get("/api/v1/problems/reports").json()[0]["problem"] == "out_of_date"
    Booking.objects.filter(pk=b["id"]).update(conflict="TWO_EXPERTS")
    assert env.ops.get("/api/v1/problems/reports").json() == []
