"""Design-time validation of each field type's config (what the admin sets up)."""
import pytest

from apps.forms.models import MasterList

pytestmark = pytest.mark.django_db

OPTS = [{"key": "ok", "label": "Ok"},
        {"key": "dent", "label": "Dent", "is_defect": True, "severity": "major"}]

VALID = [
    ("single_choice", {"options": OPTS}),
    ("single_choice", {"options": OPTS, "display": "dropdown"}),
    ("multi_choice", {"options": OPTS}),
    ("yes_no", {}),
    ("master_list", {"list": "city"}),
    ("user_picker", {"role": "expert"}),
    ("short_text", {}),
    ("short_text", {"scan": True}),
    ("short_text", {"max_length": 17, "pattern": "[A-HJ-NPR-Z0-9]{17}",
                    "pattern_message": "17-character VIN"}),
    ("long_text", {"max_length": 2000}),
    ("number", {"unit": "mm", "min": 0, "max": 20, "decimals": 1}),
    ("currency", {}),
    ("phone", {}),
    ("date", {}), ("time", {}), ("datetime", {}), ("gps", {}),
    ("photo", {"min_count": 1, "max_count": 4}),
    ("video", {"max_count": 2}),
    ("file", {"max_count": 3, "allowed": ["image", "pdf"]}),
    ("signature", {}),
    ("derived", {"rule": {"some": [{"var": "_defects"}, {"in": [{"var": ""}, ["a"]]}]},
                 "true_label": "Found", "false_label": "Not Found"}),
    ("rating", {"category": "engine"}),
]

INVALID = [
    ("short_text", {"scan": "yes"}),
    ("long_text", {"scan": True}),
    ("single_choice", {}),                                         # options required
    ("single_choice", {"options": []}),
    ("single_choice", {"options": [{"key": "ok", "label": "Ok"},
                                   {"key": "ok", "label": "Dup"}]}),  # duplicate keys
    ("single_choice", {"options": [{"key": "Bad Key", "label": "x"}]}),
    ("single_choice", {"options": [{"key": "ok", "label": ""}]}),
    # severity without defect, then defect without severity
    ("single_choice", {"options": [{"key": "x", "label": "x", "severity": "major"}]}),
    ("single_choice", {"options": [{"key": "x", "label": "x", "is_defect": True}]}),
    ("single_choice", {"options": [{"key": "x", "label": "x", "is_defect": True,
                                    "severity": "fatal"}]}),
    ("single_choice", {"options": OPTS, "display": "carousel"}),
    ("master_list", {"list": "nope"}),
    ("master_list", {}),
    ("user_picker", {"role": "superuser"}),
    ("short_text", {"max_length": 0}),
    ("short_text", {"pattern": "("}),                              # bad regex
    ("number", {"min": 10, "max": 1}),
    ("number", {"decimals": 9}),
    ("photo", {"min_count": 5, "max_count": 2}),
    ("photo", {"max_count": 99}),
    ("file", {"allowed": ["exe"]}),
    ("derived", {"true_label": "Found", "false_label": "Not Found"}),  # rule required
    ("rating", {}),
    ("short_text", {"maxlength": 10}),                            # unknown key (typo)
]


@pytest.fixture
def section(make_form, tree, admin):
    MasterList.objects.create(key="city", name="City")
    return tree(make_form()["draft_version"]["id"])["pages"][0]["sections"][0]["id"]


@pytest.mark.parametrize("type,config", VALID)
def test_valid_configs_accepted(section, add_field, type, config):
    r = add_field(section, "f_" + type, type=type, config=config)
    assert r.status_code == 201, r.json()


@pytest.mark.parametrize("type,config", INVALID)
def test_invalid_configs_rejected(section, add_field, type, config):
    r = add_field(section, "f_" + type, type=type, config=config)
    assert r.status_code == 400 and r.json()["code"] == "INVALID_CONFIG", r.json()


def test_config_is_also_validated_on_update(section, add_field, admin):
    f = add_field(section, "depth", type="number", config={"min": 0}).json()
    r = admin.patch(f"/api/v1/fields/{f['id']}", {"config": {"min": 5, "max": 1}}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_CONFIG"
