from types import SimpleNamespace

import pytest

from apps.core.concurrency import check_row_version
from apps.core.errors import CodedError


def test_a_save_from_the_current_version_passes():
    check_row_version(SimpleNamespace(row_version=3), 3, "STALE_X", "Changed.")


def test_an_old_copy_is_refused_with_the_current_version_and_who_changed_it():
    obj = SimpleNamespace(row_version=4, last_change={"by": "Priya", "at": "t", "keys": ["city"]})
    with pytest.raises(CodedError) as e:
        check_row_version(obj, 3, "STALE_X", "Changed.", who=True)
    assert e.value.status_code == 409
    assert e.value.detail == {"code": "STALE_X", "detail": "Changed.", "changed_by": "Priya",
                              "changed_at": "t", "changed_keys": ["city"], "row_version": 4}


def test_another_version_field_is_named_in_the_error():
    with pytest.raises(CodedError) as e:
        check_row_version(SimpleNamespace(revision=2), 1, "STALE_Y", "Changed.", field="revision")
    assert e.value.detail == {"code": "STALE_Y", "detail": "Changed.", "revision": 2}
