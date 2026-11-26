"""The small helpers behind the cover's checkpoint count and the photo captions (PR 28), covered
here so the reports gate (100% branch coverage) sees every branch without a database."""
from types import SimpleNamespace as NS

from apps.reports.context import _as_list, _ops_only, _shown


def field(field_access=None, section_access=None, page_access=None):
    return NS(access=field_access, section=NS(access=section_access, page=NS(access=page_access)))


def hidden():
    return {"expert": {"in_progress": "hidden"}}


def shown():
    return {"expert": {"in_progress": "edit"}}


def test_ops_only_reads_the_nearest_layer_that_says_something():
    assert _ops_only(field()) is False                                  # nobody says anything
    assert _ops_only(field(page_access=hidden())) is True               # the page hides it
    assert _ops_only(field(section_access=hidden())) is True            # the section hides it
    assert _ops_only(field(shown(), section_access=hidden())) is False  # the field overrides
    assert _ops_only(field({"ops": {}}, page_access=hidden())) is True  # no expert rule: next layer


def test_as_list_wraps_a_single_answer():
    assert _as_list(["a", "b"]) == ["a", "b"]
    assert _as_list("a") == ["a"]
    assert _as_list(None) == [None]


def test_shown_drops_a_trailing_images_or_photos_word():
    assert _shown("Front Bumper Images") == "Front Bumper"
    assert _shown("Tyre photo") == "Tyre"
    assert _shown("Images") == "Images"                                 # nothing would be left
    assert _shown("Odometer") == "Odometer"
