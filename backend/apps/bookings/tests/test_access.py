"""Field-level access: defaults, layer precedence, and enforcement on booking reads/writes."""
import pytest

from apps.bookings.stages import STAGES
from apps.forms.access import ROLES, levels_for
from apps.forms.models import Form, FormVersion

from .conftest import create

pytestmark = pytest.mark.django_db


@pytest.fixture
def v2(env):
    """Booking form v2 with extra fields that carry explicit access."""
    admin = env.admin
    form = Form.objects.get(kind="booking")
    d = admin.post(f"/api/v1/forms/{form.id}/drafts").json()["id"]
    t = admin.get(f"/api/v1/form-versions/{d}").json()
    sec = t["pages"][0]["sections"][0]["id"]

    def add(key, type="short_text", **kw):
        r = admin.post(f"/api/v1/sections/{sec}/fields",
                       {"key": key, "label": key, "type": type, **kw}, format="json")
        assert r.status_code == 201, r.json()

    add("extra_conveyance", type="currency", access={"expert": {s: "hidden" for s in STAGES}})
    add("ops_note", access={"ops": {"draft": "view"}, "expert": {"in_progress": "edit"}})
    add("plain_note")
    add("flag", type="derived", config={"rule": {"!!": [{"var": "_defects"}]},
                                        "true_label": "Y", "false_label": "N"})
    add("grade", type="rating", config={"category": "engine"})
    admin.patch(f"/api/v1/form-versions/{d}/rating-config", {"config": {"categories": [
        {"key": "engine", "label": "E", "sections": ["Section 1"]}]}}, format="json")
    rv = admin.get(f"/api/v1/form-versions/{d}").json()["row_version"]
    assert admin.post(f"/api/v1/form-versions/{d}/publish", {"row_version": rv},
                      format="json").status_code == 200
    return FormVersion.objects.get(pk=d)


def level(v, role, stage, key):
    return levels_for(v, role, stage)[key]


@pytest.mark.parametrize("stage", STAGES)
def test_defaults_admin_edits_everything_ops_everything_but_system_filled(v2, stage):
    assert level(v2, "admin", stage, "plain_note") == "edit"
    assert level(v2, "ops", stage, "plain_note") == "edit"
    assert level(v2, "ops", stage, "flag") == "view" and level(v2, "ops", stage, "grade") == "view"


@pytest.mark.parametrize("stage", STAGES)
def test_experts_never_see_system_filled_fields(v2, stage):
    assert level(v2, "expert", stage, "flag") == "hidden"
    assert level(v2, "expert", stage, "grade") == "hidden"


@pytest.mark.parametrize("stage,expected", [("draft", "hidden"), ("assigned", "view"),
                                            ("in_progress", "view"), ("submitted", "view"),
                                            ("completed", "view"), ("cancelled", "hidden")])
def test_expert_default_on_the_booking_form_is_read_only(v2, stage, expected):
    assert level(v2, "expert", stage, "plain_note") == expected


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("stage", STAGES)
def test_explicit_field_access_beats_defaults(v2, role, stage):
    expected = "hidden" if role == "expert" else ("edit" if role == "admin" else "edit")
    assert level(v2, role, stage, "extra_conveyance") == expected


def test_explicit_levels_apply_only_to_the_stage_they_name(v2):
    assert level(v2, "ops", "draft", "ops_note") == "view"
    assert level(v2, "ops", "assigned", "ops_note") == "edit"       # falls to default
    assert level(v2, "expert", "in_progress", "ops_note") == "edit"
    assert level(v2, "expert", "submitted", "ops_note") == "view"


def test_section_and_page_layers_are_used_when_the_field_defines_nothing(env, v2):
    admin = env.admin
    sec = v2.form.versions.get(pk=v2.pk)
    d = admin.post(f"/api/v1/forms/{v2.form_id}/drafts").json()["id"]
    t = admin.get(f"/api/v1/form-versions/{d}").json()
    page, section = t["pages"][0], t["pages"][0]["sections"][0]
    admin.patch(f"/api/v1/pages/{page['id']}", {"access": {"ops": {"completed": "hidden"}}},
                format="json")
    admin.patch(f"/api/v1/sections/{section['id']}",
                {"access": {"ops": {"completed": "view", "cancelled": "view"}}}, format="json")
    v3 = FormVersion.objects.get(pk=d)
    assert level(v3, "ops", "completed", "plain_note") == "view"     # section beats page
    assert level(v3, "ops", "cancelled", "plain_note") == "view"     # section only
    assert level(v3, "ops", "draft", "plain_note") == "edit"         # nothing -> default
    assert sec is not None


def test_levels_cover_every_field_of_the_version(v2):
    from apps.forms.models import Field

    assert set(levels_for(v2, "ops", "draft")) == set(
        Field.objects.filter(version=v2).values_list("key", flat=True))


# ---------------------------------------------------------------- enforcement on bookings

def test_reads_hide_fields_the_role_cannot_see(env, v2):
    b = create(env.ops, extra_conveyance=120).json()
    assert b["answers"]["extra_conveyance"] == 120
    env.ops.post(f"/api/v1/bookings/{b['id']}/assign", {"expert": env.expert_user.id},
                 format="json")
    seen = env.expert.get(f"/api/v1/bookings/{b['id']}").json()["answers"]
    assert "extra_conveyance" not in seen and seen["customer_name"] == "Asha"
    listed = env.expert.get("/api/v1/bookings").json()["results"][0]["answers"]
    assert "extra_conveyance" not in listed


def test_writes_to_read_only_fields_are_refused_listing_the_keys(env, v2):
    b = create(env.ops).json()
    url = f"/api/v1/bookings/{b['id']}"
    r = env.ops.patch(url, {"answers": {"ops_note": "x"}, "row_version": 0}, format="json")
    assert r.status_code == 403 and r.json()["code"] == "FIELD_ACCESS"  # ops_note: view in draft
    assert r.json()["keys"] == ["ops_note"]
    ok = env.admin.patch(url, {"answers": {"ops_note": "x"}, "row_version": 0}, format="json")
    assert ok.status_code == 200


def test_system_filled_fields_cannot_be_written_through_a_booking_edit(env, v2):
    b = create(env.ops).json()
    r = env.ops.patch(f"/api/v1/bookings/{b['id']}", {"answers": {"grade": 4}, "row_version": 0},
                      format="json")
    assert r.status_code == 403 and r.json()["keys"] == ["grade"]


def test_unchanged_read_only_values_may_be_resent(env, v2):
    """A UI resends the whole form; only real changes to read-only fields are refused."""
    b = create(env.admin).json()
    url = f"/api/v1/bookings/{b['id']}"
    env.admin.patch(url, {"answers": {"ops_note": "keep"}, "row_version": 0}, format="json")
    r = env.ops.patch(url, {"answers": {"ops_note": "keep", "address": "New"}, "row_version": 1},
                      format="json")
    assert r.status_code == 200


@pytest.mark.parametrize("stage,expected", [("draft", "hidden"), ("assigned", "hidden"),
                                            ("in_progress", "edit"), ("submitted", "view"),
                                            ("completed", "view"), ("cancelled", "hidden")])
@pytest.mark.parametrize("kind", ["inspection", "ops"])
def test_expert_defaults_on_inspection_and_ops_forms(kind, stage, expected):
    from apps.forms.access import default_level

    assert default_level("expert", stage, kind, "short_text") == expected


def test_listing_several_bookings_computes_levels_once_per_stage(env, v2, django_assert_max_num_queries):
    for i in range(4):
        create(env.ops, booking_id=f"SB{i}")
    with django_assert_max_num_queries(30):
        r = env.ops.get("/api/v1/bookings")
    assert len(r.json()["results"]) == 4


def test_serializer_without_a_request_returns_everything(env, booking):
    from apps.bookings.models import Booking
    from apps.bookings.serializers import BookingSerializer

    data = BookingSerializer(Booking.objects.get(pk=booking["id"])).data
    assert data["answers"]["customer_name"] == "Asha"
