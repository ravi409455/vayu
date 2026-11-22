"""Key Checks and rating suggestions on real inspections, with Ops overrides."""
import uuid

import pytest

from apps.bookings.models import Inspection

from .conftest import create
from .test_submissions import assign, publish_form, start

pytestmark = pytest.mark.django_db
V = lambda k: {"var": k}  # noqa: E731
CHOICES = [{"key": "ok", "label": "Ok"},
           {"key": "scratch", "label": "Scratch", "is_defect": True, "severity": "minor"},
           {"key": "dent", "label": "Dent", "is_defect": True, "severity": "major"},
           {"key": "broken", "label": "Broken", "is_defect": True, "severity": "critical"}]
CFG = {"categories": [{"key": "engine", "label": "Engine", "sections": ["Engine"]},
                      {"key": "exterior", "label": "Exterior", "sections": ["Exterior"]}]}


@pytest.fixture
def senv(env):
    admin = env.admin
    form = admin.post("/api/v1/forms", {"key": "pdi", "kind": "inspection", "name": "PDI",
                                        "inspection_type": "pdi"}, format="json").json()
    v = form["draft_version"]["id"]
    page = admin.get(f"/api/v1/form-versions/{v}").json()["pages"][0]

    def section(title):
        return admin.post(f"/api/v1/pages/{page['id']}/sections", {"title": title},
                          format="json").json()["id"]

    def add(sec, key, type="single_choice", **kw):
        cfg = kw.pop("config", {"options": CHOICES} if type == "single_choice" else {})
        r = admin.post(f"/api/v1/sections/{sec}/fields", {"key": key, "label": key, "type": type,
                                                          "config": cfg, **kw}, format="json")
        assert r.status_code == 201, r.json()

    eng, ext, interior = section("Engine"), section("Exterior"), section("Interior")
    add(interior, "seat")  # a section that feeds no rating category
    add(eng, "eng_oil")
    add(eng, "eng_noise")
    add(ext, "door")
    add(ext, "bonnet", show_if={"==": [V("inspection.door"), "dent"]})
    add(ext, "paint")
    add(ext, "engine_rating", "rating", config={"category": "engine"})
    add(ext, "exterior_rating", "rating", config={"category": "exterior"})
    add(ext, "dents_found", "derived", config={
        "rule": {"some": [V("_defects"), {"in": [V(""), ["inspection.door", "inspection.paint"]]}]},
        "true_label": "Found", "false_label": "Not Found"})
    r = admin.patch(f"/api/v1/form-versions/{v}/rating-config", {"config": CFG}, format="json")
    assert r.status_code == 200, r.json()
    publish_form(admin, form["id"])
    env.form_id, env.version_id = form["id"], v
    return env


def run(env, answers, **kw):
    b = create(env.ops, booking_id="SC" + uuid.uuid4().hex[:6]).json()
    assign(env, b)
    start(env.expert, b)
    body = {"client_submission_uuid": str(uuid.uuid4()),
            "answers": {"inspection": {"chassis_no": "MA3YPKCSKTJ273129", **answers}}, **kw}
    r = env.expert.post(f"/api/v1/bookings/{b['id']}/submit", body, format="json")
    assert r.status_code == 200, r.json()
    return b, Inspection.objects.get(booking_id=b["id"])


def scores(insp):
    insp.refresh_from_db()
    return insp.scores


# ---------------------------------------------------------------- config API

def test_rating_config_is_stored_returned_and_copied_to_new_drafts(senv):
    t = senv.admin.get(f"/api/v1/form-versions/{senv.version_id}").json()
    assert t["rating_config"]["categories"][0]["key"] == "engine"
    d = senv.admin.post(f"/api/v1/forms/{senv.form_id}/drafts").json()["id"]
    assert senv.admin.get(f"/api/v1/form-versions/{d}").json()["rating_config"] == CFG


def test_rating_config_is_validated_and_draft_only(senv):
    d = senv.admin.post(f"/api/v1/forms/{senv.form_id}/drafts").json()["id"]
    bad = senv.admin.patch(f"/api/v1/form-versions/{d}/rating-config",
                           {"config": {"deductions": {"minor": 2, "major": 1, "critical": 3}}},
                           format="json")
    assert bad.status_code == 400 and bad.json()["code"] == "INVALID_RATING_CONFIG"
    published = senv.admin.patch(f"/api/v1/form-versions/{senv.version_id}/rating-config",
                                 {"config": CFG}, format="json")
    assert published.status_code == 409 and published.json()["code"] == "VERSION_PUBLISHED"
    assert senv.ops.patch(f"/api/v1/form-versions/{d}/rating-config", {"config": CFG},
                          format="json").status_code == 403
    assert senv.admin.patch(f"/api/v1/form-versions/{d}/rating-config", {},
                            format="json").status_code == 400


def test_publish_checks_that_rated_sections_and_categories_exist(senv):
    d = senv.admin.post(f"/api/v1/forms/{senv.form_id}/drafts").json()["id"]
    cfg = {"categories": [{"key": "engine", "label": "E", "sections": ["No such section"]}]}
    senv.admin.patch(f"/api/v1/form-versions/{d}/rating-config", {"config": cfg}, format="json")
    issues = {(i["path"], i["code"]) for i in
              senv.admin.post(f"/api/v1/form-versions/{d}/validate").json()["issues"]}
    assert ("rating_config.categories.engine", "UNKNOWN_SECTION") in issues
    assert ("fields.exterior_rating.config", "UNKNOWN_CATEGORY") in issues  # category removed


# ---------------------------------------------------------------- scoring on submit

def test_ratings_overall_and_key_checks_are_computed_on_submit(senv):
    _, insp = run(senv, {"eng_oil": "ok", "eng_noise": "ok", "door": "dent", "paint": "scratch"})
    s = scores(insp)
    # exterior: door dent (major 1) + paint scratch (minor .25) -> 3.75 -> 4; engine: 5
    assert s["ratings"]["engine"]["value"] == 5 and s["ratings"]["exterior"]["value"] == 4
    assert s["overall"]["average"] == 4.5 and s["overall"]["word"] == "excellent"
    assert s["derived"]["dents_found"] is True
    assert s["fields"] == {"engine_rating": 5, "exterior_rating": 4}


def test_a_critical_defect_caps_the_overall_at_average(senv):
    _, insp = run(senv, {"eng_noise": "broken", "door": "ok"})
    s = scores(insp)
    assert s["ratings"]["engine"]["value"] == 2 and s["ratings"]["exterior"]["value"] == 5
    assert s["overall"]["average"] == 3.5          # 'good' by the numbers...
    assert s["overall"]["word"] == "average"       # ...capped because of the critical defect


def test_hidden_and_unanswered_fields_never_count(senv):
    # bonnet is only shown when the door is dented, so its scratch is dropped, not counted
    _, insp = run(senv, {"door": "ok", "bonnet": "scratch"})
    s = scores(insp)
    assert s["ratings"]["exterior"]["value"] == 5 and s["derived"]["dents_found"] is False
    assert s["defects"] == []


def test_without_a_rating_config_only_key_checks_are_computed(env):
    admin = env.admin
    form = admin.post("/api/v1/forms", {"key": "pdi", "kind": "inspection", "name": "PDI",
                                        "inspection_type": "pdi"}, format="json").json()
    publish_form(admin, form["id"])
    _, insp = run(env, {})
    s = scores(insp)
    assert s["ratings"] == {} and s["overall"] == {"average": None, "word": None,
                                                    "suggested_word": None, "overridden": False}


def test_experts_never_see_scores(senv):
    b, insp = run(senv, {"door": "dent"})
    r = senv.expert.get(f"/api/v1/inspections/{insp.id}").json()
    assert "scores" not in r and "overrides" not in r
    assert senv.ops.get(f"/api/v1/inspections/{insp.id}").json()["scores"]["ratings"]
    sub = senv.expert.post(f"/api/v1/bookings/{b['id']}/submit", {
        "client_submission_uuid": str(insp.client_submission_uuid),
        "answers": {}}, format="json").json()
    assert "scores" not in sub["inspection"]


# ---------------------------------------------------------------- overrides and recalculation

def override(client, insp, body, row_version=None):
    insp.refresh_from_db()
    return client.patch(f"/api/v1/inspections/{insp.id}/overrides",
                        {**body, "row_version": insp.row_version if row_version is None
                         else row_version}, format="json")


def test_ops_override_ratings_overall_and_key_checks(senv):
    _, insp = run(senv, {"door": "dent", "paint": "scratch"})
    r = override(senv.ops, insp, {"ratings": {"exterior": 2}, "derived": {"dents_found": False},
                                  "overall": "good"})
    assert r.status_code == 200
    s = scores(insp)
    assert s["ratings"]["exterior"] == {"suggested": 4, "value": 2, "overridden": True}
    assert s["fields"]["exterior_rating"] == 2
    assert s["derived"]["dents_found"] is False
    assert s["overall"]["word"] == "good" and s["overall"]["overridden"] is True
    assert s["overall"]["suggested_word"] == "excellent"   # from the suggested values, 5 and 4
    assert insp.overrides == {"ratings": {"exterior": 2}, "derived": {"dents_found": False},
                              "overall": "good"}


def test_a_category_override_feeds_the_overall_average(senv):
    _, insp = run(senv, {"door": "ok"})
    assert scores(insp)["overall"]["word"] == "excellent"
    override(senv.ops, insp, {"ratings": {"exterior": 1, "engine": 2}})
    assert scores(insp)["overall"]["average"] == 1.5 and scores(insp)["overall"]["word"] == "bad"


def test_recalculation_after_an_edit_keeps_overrides_and_updates_the_rest(senv):
    _, insp = run(senv, {"door": "dent", "paint": "scratch", "eng_oil": "scratch"})
    override(senv.ops, insp, {"ratings": {"exterior": 5}})
    insp.refresh_from_db()
    r = senv.ops.patch(f"/api/v1/inspections/{insp.id}", {
        "answers": {"inspection": {"eng_oil": "dent"}}, "row_version": insp.row_version},
        format="json")
    assert r.status_code == 200
    s = scores(insp)
    assert s["ratings"]["engine"]["value"] == 4             # recalculated: 5 - 1
    assert s["ratings"]["exterior"]["value"] == 5           # Ops override survived
    assert s["ratings"]["exterior"]["suggested"] == 4


def test_clearing_an_override_rederives_it(senv):
    _, insp = run(senv, {"door": "dent"})
    override(senv.ops, insp, {"ratings": {"exterior": 1}, "overall": "bad"})
    assert scores(insp)["ratings"]["exterior"]["value"] == 1
    override(senv.ops, insp, {"ratings": {"exterior": None}, "overall": None})
    s = scores(insp)
    assert s["ratings"]["exterior"] == {"suggested": 4, "value": 4, "overridden": False}
    assert s["overall"]["overridden"] is False
    assert insp.overrides == {"ratings": {}, "derived": {}}


@pytest.mark.parametrize("body", [
    {"ratings": {"nope": 3}}, {"ratings": {"exterior": 0}}, {"ratings": {"exterior": 6}},
    {"ratings": {"exterior": "4"}}, {"ratings": {"exterior": True}}, {"ratings": []},
    {"derived": {"ghost": True}}, {"derived": {"dents_found": "yes"}}, {"derived": []},
    {"overall": "superb"}, {"overall": 3}, {"surprise": 1},
])
def test_invalid_overrides_are_rejected(senv, body):
    _, insp = run(senv, {})
    r = override(senv.ops, insp, body)
    assert r.status_code == 400 and r.json()["code"] == "INVALID_OVERRIDES"


def test_override_needs_permission_row_version_and_fresh_data(senv):
    _, insp = run(senv, {})
    assert override(senv.expert, insp, {"overall": "good"}).status_code == 403
    insp.refresh_from_db()
    assert senv.ops.patch(f"/api/v1/inspections/{insp.id}/overrides", {"overall": "good"},
                          format="json").status_code == 400
    ok = override(senv.ops, insp, {"overall": "good"})
    assert ok.status_code == 200
    stale = senv.admin.patch(f"/api/v1/inspections/{insp.id}/overrides",
                             {"overall": "bad", "row_version": 0}, format="json")
    assert stale.status_code == 409 and stale.json()["changed_by"] == senv.ops_user.username


def test_override_permission_can_be_revoked_from_ops(senv):
    from apps.accounts.catalog import DEFAULTS

    _, insp = run(senv, {})
    perms = {k: v for k, v in DEFAULTS["ops"].items() if k != "ratings.override"}
    senv.admin.put("/api/v1/roles/ops/permissions", {"permissions": perms}, format="json")
    assert override(senv.ops, insp, {"overall": "good"}).status_code == 403


def test_a_critical_defect_in_an_unrated_section_still_caps_the_overall(senv):
    _, insp = run(senv, {"eng_oil": "ok", "door": "ok", "seat": "broken"})
    s = scores(insp)
    assert s["ratings"]["engine"]["value"] == 5 and s["ratings"]["exterior"]["value"] == 5
    assert s["overall"]["average"] == 5.0 and s["overall"]["word"] == "average"
    assert s["defects"] == ["inspection.seat"]


# ---------------------------------------------------------------- review fixes: no leaks past field access

def test_experts_do_not_receive_the_scoring_rules_in_their_form(senv):
    b = create(senv.ops, booking_id="SC10").json()
    assign(senv, b)
    form = start(senv.expert, b).json()["form"]
    assert "rating_config" not in form


def test_scores_hide_key_checks_and_rating_fields_the_role_may_not_see(senv):
    from apps.forms.models import Field

    _, insp = run(senv, {"door": "dent"})
    Field.objects.filter(version=insp.form_version, key="dents_found").update(
        access={"ops": {s: "hidden" for s in ("submitted", "completed", "draft", "assigned",
                                              "in_progress", "cancelled")}})
    Field.objects.filter(version=insp.form_version, key="engine_rating").update(
        access={"ops": {s: "hidden" for s in ("submitted", "completed", "draft", "assigned",
                                              "in_progress", "cancelled")}})
    seen = senv.ops.get(f"/api/v1/inspections/{insp.id}").json()["scores"]
    assert "dents_found" not in seen["derived"] and "engine_rating" not in seen["fields"]
    assert "exterior_rating" in seen["fields"]
    assert senv.admin.get(f"/api/v1/inspections/{insp.id}").json()["scores"]["derived"]
    assert "dents_found" in senv.admin.get(f"/api/v1/inspections/{insp.id}").json()["scores"]["derived"]
