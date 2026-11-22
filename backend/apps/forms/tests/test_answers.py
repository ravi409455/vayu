"""Runtime validation of one answer against its field (rules/required live in test_rules)."""
import pytest

from apps.accounts.models import Role
from apps.forms.fieldtypes import AnswerError, clean_answer, is_empty
from apps.forms.models import Field, MasterList, MasterListItem

pytestmark = pytest.mark.django_db

OPTS = [{"key": "ok", "label": "Ok"},
        {"key": "dent", "label": "Dent", "is_defect": True, "severity": "major"}]


def f(type, **config):
    return Field(key="k", label="K", type=type, config=config)  # unsaved: validation only


def ok(field, value, expected=None, **kw):
    assert clean_answer(field, value, **kw) == (value if expected is None else expected)


def bad(field, value, code, **kw):
    with pytest.raises(AnswerError) as e:
        clean_answer(field, value, **kw)
    assert e.value.code == code


@pytest.mark.parametrize("value", [None, "", "   ", [], {}])
def test_empty_values(value):
    assert is_empty(value)


@pytest.mark.parametrize("value", [0, False, "0", ["x"], {"lat": 0}])
def test_non_empty_values(value):
    assert not is_empty(value)


def test_single_choice():
    ok(f("single_choice", options=OPTS), "dent")
    bad(f("single_choice", options=OPTS), "scratch", "INVALID_OPTION")
    bad(f("single_choice", options=OPTS), ["ok"], "INVALID_TYPE")


def test_multi_choice():
    ok(f("multi_choice", options=OPTS), ["ok", "dent"])
    bad(f("multi_choice", options=OPTS), ["ok", "ok"], "DUPLICATE_OPTION")
    bad(f("multi_choice", options=OPTS), ["nope"], "INVALID_OPTION")
    bad(f("multi_choice", options=OPTS), "ok", "INVALID_TYPE")


@pytest.mark.parametrize("value", [True, False])
def test_yes_no_accepts_booleans(value):
    ok(f("yes_no"), value)


@pytest.mark.parametrize("value", ["yes", 1, 0, "true"])
def test_yes_no_rejects_non_booleans(value):
    bad(f("yes_no"), value, "INVALID_TYPE")


def test_master_list_rejects_unknown_and_archived_items():
    lst = MasterList.objects.create(key="city", name="City")
    MasterListItem.objects.create(list=lst, key="delhi", label="Delhi")
    MasterListItem.objects.create(list=lst, key="old", label="Old", archived=True)
    field = f("master_list", list="city")
    ok(field, "delhi")
    bad(field, "mumbai", "INVALID_OPTION")
    bad(field, "old", "ARCHIVED_OPTION")


def test_user_picker_only_active_users_of_the_role(make_user):
    expert = make_user(Role.EXPERT)
    ops = make_user(Role.OPS)
    gone = make_user(Role.EXPERT, is_active=False)
    field = f("user_picker", role="expert")
    ok(field, expert.id)
    bad(field, ops.id, "INVALID_USER")
    bad(field, gone.id, "INVALID_USER")
    bad(field, 999999, "INVALID_USER")
    bad(field, str(expert.id), "INVALID_TYPE")


def test_short_text_strips_limits_and_matches_pattern():
    ok(f("short_text"), "  MA3YPKCSKTJ273129 ", "MA3YPKCSKTJ273129")
    bad(f("short_text", max_length=5), "123456", "TOO_LONG")
    vin = f("short_text", pattern="[A-HJ-NPR-Z0-9]{17}")
    ok(vin, "MA3YPKCSKTJ273129")
    bad(vin, "MA3YPKCSKTJ27312O", "PATTERN_MISMATCH")  # letter O is not allowed in VINs
    bad(f("short_text"), 42, "INVALID_TYPE")


def test_catastrophic_regex_times_out_instead_of_hanging():
    evil = f("short_text", pattern="(a+)+$", max_length=500)
    bad(evil, "a" * 40 + "!", "PATTERN_TIMEOUT")


def test_long_text():
    ok(f("long_text", max_length=10), "line1\nline2", "line1\nline2")
    bad(f("long_text", max_length=10), "x" * 11, "TOO_LONG")


@pytest.mark.parametrize("value,decimals,expected", [(7, 0, 7), (7.4, 1, 7.4), (0, 0, 0),
                                                     ("7.4", 1, 7.4)])
def test_number_accepts(value, decimals, expected):
    ok(f("number", min=0, max=20, decimals=decimals), value, expected)


@pytest.mark.parametrize("value,code", [(21, "OUT_OF_RANGE"), (-1, "OUT_OF_RANGE"),
                                        (7.45, "TOO_MANY_DECIMALS"), ("abc", "INVALID_TYPE"),
                                        (True, "INVALID_TYPE"), (float("nan"), "INVALID_TYPE")])
def test_number_rejects(value, code):
    bad(f("number", min=0, max=20, decimals=1), value, code)


def test_currency():
    ok(f("currency"), 1500, 1500)
    ok(f("currency"), "1499.50", 1499.5)
    bad(f("currency"), -1, "OUT_OF_RANGE")
    bad(f("currency"), 10.555, "TOO_MANY_DECIMALS")


@pytest.mark.parametrize("raw", ["9876543210", "+91 98765 43210", "+919876543210",
                                 "098765-43210", "919876543210"])
def test_phone_normalises_indian_mobiles(raw):
    ok(f("phone"), raw, "+919876543210")


@pytest.mark.parametrize("raw", ["5876543210", "98765", "+1 2025550123", "phone", 9876543210])
def test_phone_rejects(raw):
    bad(f("phone"), raw, "INVALID_PHONE" if isinstance(raw, str) else "INVALID_TYPE")


def test_date_time_datetime():
    ok(f("date"), "2026-10-14")
    bad(f("date"), "2026-02-30", "INVALID_DATE")
    bad(f("date"), "14-10-2026", "INVALID_DATE")
    ok(f("time"), "15:29")
    ok(f("time"), "15:29:59", "15:29")
    bad(f("time"), "25:00", "INVALID_TIME")
    ok(f("datetime"), "2026-10-14T15:29:00+05:30", "2026-10-14T15:29:00+05:30")
    ok(f("datetime"), "2026-10-14T09:59:00Z", "2026-10-14T15:29:00+05:30")  # stored in IST
    bad(f("datetime"), "2026-10-14T15:29:00", "NAIVE_DATETIME")


def test_gps():
    ok(f("gps"), {"lat": 28.6, "lng": 77.2, "accuracy": 12.5})
    ok(f("gps"), {"lat": 28.6, "lng": 77.2})
    bad(f("gps"), {"lat": 91, "lng": 77.2}, "INVALID_GPS")
    bad(f("gps"), {"lat": 28.6}, "INVALID_GPS")
    bad(f("gps"), {"lat": 28.6, "lng": 77.2, "alt": 3}, "INVALID_GPS")
    bad(f("gps"), [28.6, 77.2], "INVALID_GPS")


UUID1, UUID2, UUID3 = ("11111111-1111-4111-8111-111111111111",
                       "22222222-2222-4222-8222-222222222222",
                       "33333333-3333-4333-8333-333333333333")


def test_media_counts_and_ids():
    photos = f("photo", min_count=1, max_count=2)
    ok(photos, [UUID1, UUID2])
    bad(photos, [UUID1, UUID2, UUID3], "TOO_MANY")
    bad(f("photo", min_count=2, max_count=4), [UUID1], "TOO_FEW")
    bad(photos, ["not-a-uuid"], "INVALID_MEDIA_ID")
    bad(photos, [UUID1, UUID1], "DUPLICATE_MEDIA")
    bad(photos, UUID1, "INVALID_TYPE")
    ok(f("video", max_count=1), [UUID1])
    ok(f("file", max_count=3), [UUID1])
    ok(f("signature"), UUID1)
    bad(f("signature"), [UUID1], "INVALID_TYPE")


def test_system_filled_fields_reject_normal_writes_but_accept_overrides():
    derived = f("derived", rule={"var": "x"}, true_label="Found", false_label="Not Found")
    rating = f("rating", category="engine")
    bad(derived, True, "SYSTEM_FILLED")
    bad(rating, 4, "SYSTEM_FILLED")
    ok(derived, False, override=True)
    ok(rating, 4, override=True)
    bad(rating, 6, "OUT_OF_RANGE", override=True)
    bad(rating, 0, "OUT_OF_RANGE", override=True)
    bad(derived, "maybe", "INVALID_TYPE", override=True)
