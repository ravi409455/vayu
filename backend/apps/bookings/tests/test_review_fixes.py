from unittest import mock

import pytest

from apps.bookings import submissions
from apps.core.errors import CodedError

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("bad", [{"inspection": "x"}, {"ops": [1]}, "x", [1], 5])
def test_answers_must_be_objects(bad):
    with pytest.raises(CodedError) as e:
        submissions.check_shape(bad)
    assert e.value.detail == {"code": "INVALID_ANSWERS", "detail": mock.ANY}


@pytest.mark.parametrize("ok", [{}, {"inspection": {}}, {"inspection": None, "ops": {"a": 1}}])
def test_well_formed_answers_pass(ok):
    submissions.check_shape(ok)


def test_the_expert_filter_needs_a_user_id(env):
    assert env.ops.get("/api/v1/bookings?expert=abc").status_code == 400
    assert env.ops.get(f"/api/v1/bookings?expert={env.expert_user.id}").status_code == 200
